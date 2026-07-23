import sys
import time
import argparse

import cv2
import numpy as np

from storage.db import Database
from storage.config_store import ConfigStore
from storage.app_tracker import get_active_app, get_app_category
from config_defaults import DEFAULTS

from core.detector import FaceDetector
from core.tracker import FaceTracker
from core.recognizer import FaceRecognizer, Identity

from analysis.expressions.registry import build_expressions
from analysis.expressions.base import Expression
from analysis.gaze import GazeTracker
from analysis.distance import DistanceEstimator
from analysis.focus import compute_focus_score

from alerts.registry import build_alerts
from alerts.base import ALERT_LOGGABLE, AlertContext

from demographics.analyzer import DemographicsAnalyzer
from demographics.face_width import DEFAULT_FACE_WIDTH_CM

from calibration.store import CalibrationStore

from ui.renderer import Renderer
from ui.input_handler import InputHandler, Action

from storage.db.connection import now_utc


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="FaceWatch")
    parser.add_argument("--camera",    type=int,  default=None)
    parser.add_argument("--calibrate", action="store_true")
    parser.add_argument("--refresh-demographics", type=str, metavar="NAME", default=None)
    parser.add_argument("--reset-config", action="store_true")
    parser.add_argument("--port",      type=int,  default=None)
    return parser.parse_args()


def _seed_config(db: Database) -> None:
    for key, value, type_, description, category in DEFAULTS:
        db.seed_config(key, str(value), type_, description, category)


def _crop(frame: np.ndarray, bbox: list[float]) -> np.ndarray:
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = [int(v) for v in bbox]
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w, x2), min(h, y2)
    return frame[y1:y2, x1:x2]


def _blendshapes_dict(result, face_idx: int) -> dict[str, float]:
    if not result or not result.face_blendshapes or face_idx >= len(result.face_blendshapes):
        return {}
    return {bs.category_name: bs.score for bs in result.face_blendshapes[face_idx]}


def _landmarks_list(result, face_idx: int) -> list:
    if not result or not result.face_landmarks or face_idx >= len(result.face_landmarks):
        return []
    return result.face_landmarks[face_idx]



def run() -> None:
    args = _parse_args()

    # ── Init storage ──────────────────────────────────────────────────────────
    db     = Database("facewatch.db")
    _seed_config(db)
    config = ConfigStore(db)

    if args.reset_config:
        for key, value, *_ in DEFAULTS:
            db.set_config(key, str(value))

    # ── Init modules ──────────────────────────────────────────────────────────
    camera_idx  = args.camera if args.camera is not None else config.get("camera_index")
    calibration = CalibrationStore(db)
    detector    = FaceDetector(config)
    tracker     = FaceTracker()
    recognizer  = FaceRecognizer(db, config)
    distance    = DistanceEstimator()
    demo        = DemographicsAnalyzer(db, config)
    alerts      = build_alerts()
    renderer    = Renderer()
    input_handler = InputHandler(config)

    # Per-track state
    expressions_map: dict[int, list[Expression]] = {}
    gaze_map:        dict[int, GazeTracker]       = {}

    # ── Camera ────────────────────────────────────────────────────────────────
    cap = cv2.VideoCapture(camera_idx)
    if not cap.isOpened():
        print(f"[ERROR] Cannot open camera {camera_idx}")
        sys.exit(1)

    frame_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    last_stats_time = time.time()
    last_time       = time.time()

    print("[FaceWatch] Running. Press 'q' to quit.")

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        frame = cv2.flip(frame, 1)
        now = time.time()
        dt  = now - last_time
        last_time = now

        # ── Detect + Track ────────────────────────────────────────────────────
        detector.detect(frame)
        result = detector.latest_result

        detections = []
        if result and result.face_landmarks:
            for i, lms in enumerate(result.face_landmarks):
                xs = [lm.x * frame_w for lm in lms]
                ys = [lm.y * frame.shape[0] for lm in lms]
                detections.append([min(xs), min(ys), max(xs), max(ys), 1.0])

        tracks = tracker.update(detections)
        active_track_ids = set(tracks.keys())

        # Clean up disappeared tracks
        for tid in list(expressions_map.keys()):
            if tid not in active_track_ids:
                expressions_map.pop(tid)
                gaze_map.pop(tid, None)
                recognizer.drop_track(tid)

        # ── Per-track analysis ────────────────────────────────────────────────
        for i, (track_id, bbox) in enumerate(tracks.items()):
            # Init per-track state on first sight
            if track_id not in expressions_map:
                expressions_map[track_id] = build_expressions()
                gaze_map[track_id]        = GazeTracker()

            crop = _crop(frame, bbox)
            if crop.size > 0:
                recognizer.submit(track_id, crop)

            identity = recognizer.get_identity(track_id)
            if identity.status == "known" and identity.face_id is not None:
                demo.maybe_run(identity.face_id, crop)

            blendshapes = _blendshapes_dict(result, i)
            landmarks   = _landmarks_list(result, i)

            for expr in expressions_map[track_id]:
                expr.update(blendshapes, landmarks, config)

            gaze_state = gaze_map[track_id].update(landmarks, dt, config, calibration)

            face_width = demo.get_face_width(identity.face_id) if identity.face_id else DEFAULT_FACE_WIDTH_CM
            focal_length_px = calibration.get("focal_length_px")
            dist_cm = distance.estimate(landmarks, face_width, focal_length_px, frame_w)

            # ── Alerts ────────────────────────────────────────────────────────
            ctx = AlertContext(gaze_on_screen=gaze_state.on_screen, dist_cm=dist_cm, config=config)
            for alert in alerts:
                condition = alert.is_condition_met(ctx)
                event = alert.update(condition, dt, config)
                if event.status in ALERT_LOGGABLE:
                    db.log_audit(f"alert_{event.status}", {"message": event.message})

        # ── Stats write ───────────────────────────────────────────────────────
        interval_sec: int = config.get("stats_interval_sec")
        if now - last_stats_time >= interval_sec:
            app, title = get_active_app()
            track_list = list(tracks.keys())
            for track_id in track_list:
                identity = recognizer.get_identity(track_id)
                if identity.status != "known" or identity.face_id is None:
                    continue

                exprs      = expressions_map[track_id]
                face_width = demo.get_face_width(identity.face_id)
                lms        = _landmarks_list(result, track_list.index(track_id))
                dist_cm    = distance.estimate(lms, face_width, _DEFAULT_FOCAL_LENGTH_PX, frame_w)
                gaze_state = gaze_map[track_id].update([], 0.0, config, calibration)

                expr_stats = {e.name: e.get_interval_stats() for e in exprs}
                total_f    = expr_stats.get("blink_left", {}).get("total_frames", 1) or 1
                drowsy_f   = expr_stats.get("drowsy",     {}).get("active_frames", 0)
                neutral_f  = expr_stats.get("neutral",    {}).get("active_frames", 0)
                drowsy_pct = drowsy_f / total_f

                focus = compute_focus_score(
                    gaze_off_sec=gaze_map[track_id]._off_screen_timer,
                    interval_sec=interval_sec,
                    drowsy_pct=drowsy_pct,
                    angry_count=expr_stats.get("angry",     {}).get("count", 0),
                    surprised_count=expr_stats.get("surprised", {}).get("count", 0),
                    distance_cm=dist_cm,
                    config=config,
                )

                proximity_alerts = sum(1 for a in alerts if a.active and a.alert_type.value == "proximity")

                row = {
                    "timestamp":           now_utc(),
                    "interval_sec":        interval_sec,
                    "blink_left":          expr_stats.get("blink_left",  {}).get("count", 0),
                    "blink_right":         expr_stats.get("blink_right", {}).get("count", 0),
                    "smile_count":         expr_stats.get("smile",       {}).get("count", 0),
                    "angry_count":         expr_stats.get("angry",       {}).get("count", 0),
                    "surprised_count":     expr_stats.get("surprised",   {}).get("count", 0),
                    "neutral_pct":         round(neutral_f  / total_f * 100, 1),
                    "drowsy_pct":          round(drowsy_pct * 100, 1),
                    "distance_cm":         dist_cm,
                    "gaze_off_sec":        gaze_state.off_screen_sec,
                    "proximity_alerts":    proximity_alerts,
                    "focus_score":         focus,
                    "active_app":          app,
                    "active_window_title": title,
                    "app_category":        get_app_category(app),
                }

                db.write_stats(identity.face_id, row)
                db.update_face_last_seen(identity.face_id)

            last_stats_time = now

        # ── Collect per-track state for renderer ─────────────────────────────
        identities_snap  = {tid: recognizer.get_identity(tid) for tid in tracks}
        gaze_snap        = dict(gaze_map)
        distances_snap   = {}
        focus_snap: dict[int, float] = {}
        alert_snap: dict[int, bool]  = {}
        for tid, bbox in tracks.items():
            ident = identities_snap[tid]
            fw    = demo.get_face_width(ident.face_id) if ident.face_id else DEFAULT_FACE_WIDTH_CM
            lms   = _landmarks_list(result, list(tracks.keys()).index(tid))
            distances_snap[tid] = distance.estimate(lms, fw, calibration.get("focal_length_px"), frame_w)
            alert_snap[tid] = any(a.active for a in alerts)

        frame = renderer.draw(
            frame, tracks, identities_snap, gaze_snap,
            expressions_map, distances_snap, focus_snap, alert_snap,
        )

        # ── Display + input ───────────────────────────────────────────────────
        cv2.imshow("FaceWatch", frame)
        action = input_handler.handle(cv2.waitKey(1) & 0xFF)

        if action == Action.QUIT:
            break
        elif action == Action.TOGGLE_DEBUG:
            renderer.toggle_debug()
        elif action == Action.FORCE_STATS:
            last_stats_time = 0  # force stats on next iteration
        elif action == Action.CALIBRATE:
            pass  # TODO: launch calibration wizard flow
        elif action == Action.REGISTER:
            pass  # TODO: launch face registration flow

    cap.release()
    cv2.destroyAllWindows()
    db.log_audit("session_end", {"reason": "user_quit"})
    db.close()


if __name__ == "__main__":
    run()
