import sys
import os
import time
import argparse
import threading
import multiprocessing

os.environ["TF_CPP_MIN_LOG_LEVEL"]  = "3"
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"
os.environ["GLOG_minloglevel"]       = "3"

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
from analysis.gaze import GazeTracker, GazeState
from analysis.distance import DistanceEstimator
from analysis.focus import compute_focus_score

from alerts.base import ALERT_LOGGABLE, AlertStatus, AlertPriority, AlertType
from alerts.context_builder import build_alert_context
from alerts.manager import AlertManager

from demographics.analyzer import DemographicsAnalyzer
from demographics.face_width import DEFAULT_FACE_WIDTH_CM

from calibration.store import CalibrationStore
from calibration.wizard import FocalWizard, GazeWizard, WizardState
from calibration.gaze_estimator import PtgazeEstimator

from ui.renderer import Renderer
from ui.input_handler import InputHandler, Action
from ui.text_input import TextInput
from ui.mouse_handler import MouseHandler, MouseAction
from ui.alert_overlay import AlertOverlay
from ui.calibration_overlay import CalibrationOverlay
from ui.screen import detect_screen_size
from ui.settings import open_settings
from reporting import Reporter

from storage.db.connection import now_utc
from startup import ensure_models


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="FaceWatch")
    parser.add_argument("--camera",    type=int,  default=None)
    parser.add_argument("--calibrate", action="store_true")
    parser.add_argument("--refresh-demographics", type=str, metavar="NAME", default=None)
    parser.add_argument("--reset-config", action="store_true")
    parser.add_argument("--port",      type=int,  default=None)
    parser.add_argument("--db",        type=str,  default="facewatch.db", metavar="PATH",
                        help="SQLite database file (default: facewatch.db)")
    return parser.parse_args()


def _seed_config(db: Database) -> None:
    for key, value, type_, description, category in DEFAULTS:
        db.seed_config(key, str(value), type_, description, category)


def _open_camera(camera_idx: int) -> tuple[cv2.VideoCapture, int, int]:
    """
    Open the webcam and return (cap, frame_w, frame_h). The size is taken from
    an actual frame — some backends report 0 for CAP_PROP_* before the first read.
    Exits if the camera can't be opened.
    """
    cap = cv2.VideoCapture(camera_idx)
    if not cap.isOpened():
        print(f"[ERROR] Cannot open camera {camera_idx}")
        sys.exit(1)
    for _ in range(10):
        ok, frame = cap.read()
        if ok and frame is not None:
            h, w = frame.shape[:2]
            return cap, w, h
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if w <= 0 or h <= 0:
        print(f"[ERROR] Camera {camera_idx} returned no frames")
        sys.exit(1)
    return cap, w, h


def _crop(frame: np.ndarray, bbox: list[float]) -> np.ndarray:
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = [int(v) for v in bbox]
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w, x2), min(h, y2)
    return frame[y1:y2, x1:x2]


def _blendshapes_dict(result, face_idx: int) -> dict[str, float]:
    if not result or not result.face_blendshapes or face_idx < 0 or face_idx >= len(result.face_blendshapes):
        return {}
    return {bs.category_name: bs.score for bs in result.face_blendshapes[face_idx]}


def _landmarks_list(result, face_idx: int) -> list:
    if not result or not result.face_landmarks or face_idx < 0 or face_idx >= len(result.face_landmarks):
        return []
    return result.face_landmarks[face_idx]


def _iou(a: list[float], b: list[float]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    if inter == 0:
        return 0.0
    area_a = (ax2 - ax1) * (ay2 - ay1)
    area_b = (bx2 - bx1) * (by2 - by1)
    return inter / (area_a + area_b - inter)


def _match_tracks_to_mp(result, tracks: dict[int, list[float]],
                        frame_w: int, frame_h: int) -> dict[int, int]:
    """Returns {track_id: mediapipe_face_index} matched by highest IoU."""
    if not result or not result.face_landmarks:
        return {}
    mp_bboxes = []
    for lms in result.face_landmarks:
        xs = [lm.x * frame_w for lm in lms]
        ys = [lm.y * frame_h for lm in lms]
        mp_bboxes.append([min(xs), min(ys), max(xs), max(ys)])

    mapping: dict[int, int] = {}
    for track_id, bbox in tracks.items():
        best_idx, best_iou = -1, 0.0
        for i, mp_bbox in enumerate(mp_bboxes):
            score = _iou(bbox, mp_bbox)
            if score > best_iou:
                best_iou = score
                best_idx = i
        if best_idx >= 0 and best_iou > 0.1:
            mapping[track_id] = best_idx
    return mapping


def _match_ptgaze_to_tracks(
    ptgaze_results: list, tracks: dict[int, list[float]],
) -> dict[int, tuple]:
    """Returns {track_id: (face, hit)} matched by highest IoU."""
    if not ptgaze_results:
        return {}
    mapping: dict[int, tuple] = {}
    for track_id, bbox in tracks.items():
        best_fh, best_iou = None, 0.0
        for face, hit in ptgaze_results:
            # face.bbox is shape (2,2): [[x_min, y_min], [x_max, y_max]]
            pt_bbox = [face.bbox[0][0], face.bbox[0][1], face.bbox[1][0], face.bbox[1][1]]
            score = _iou(bbox, pt_bbox)
            if score > best_iou:
                best_iou = score
                best_fh  = (face, hit)
        if best_fh is not None and best_iou > 0.1:
            mapping[track_id] = best_fh
    return mapping


def run() -> None:
    args = _parse_args()

    # ── Init storage ──────────────────────────────────────────────────────────
    db_path = args.db
    db      = Database(db_path)
    _seed_config(db)
    config = ConfigStore(db)

    if args.reset_config:
        for key, value, *_ in DEFAULTS:
            db.set_config(key, str(value))

    ensure_models(config.get("face_landmarker_model_path"))

    # Start the calibration overlay first: its Qt process boots in parallel with
    # model loading below, then reports the screen size gaze is measured in.
    cal_overlay = CalibrationOverlay()
    cal_overlay.start()

    # ── Camera ────────────────────────────────────────────────────────────────
    # Opened before the gaze estimator: ptgaze's camera model needs the real
    # frame size (focal length and principal point are derived from it).
    camera_idx = args.camera if args.camera is not None else config.get("camera_index")
    cap, frame_w, frame_h = _open_camera(camera_idx)

    # ── Init modules ──────────────────────────────────────────────────────────
    ptgaze_estimator = PtgazeEstimator(frame_w, frame_h)
    calibration   = CalibrationStore(db)
    detector      = FaceDetector(config)
    tracker       = FaceTracker()
    recognizer    = FaceRecognizer(db, config)
    distance      = DistanceEstimator()
    demo          = DemographicsAnalyzer(db, config)
    alert_manager = AlertManager()
    renderer      = Renderer(config)
    input_handler = InputHandler(config)
    mouse         = MouseHandler()
    overlay     = AlertOverlay(config)
    overlay.start()
    screen_w, screen_h = detect_screen_size(cal_overlay)
    report_port = args.port if args.port is not None else config.get("report_port")
    reporter = Reporter(
        db_path=db_path,
        port=report_port,
        report_times=config.get("report_times"),
    )
    reporter.start()

    # Per-track state
    expressions_map:  dict[int, list[Expression]] = {}
    gaze_map:         dict[int, GazeTracker]       = {}
    gaze_states:      dict[int, GazeState]         = {}
    _session_start:   dict[int, float]             = {}
    _last_absent:     dict[int, float]             = {}
    text_input:       TextInput | None             = None
    pending_action:  MouseAction                  = MouseAction.NONE
    pending_track:   int | None                   = None
    _gaze_pointer_ids: set[int] = set()  # face_ids with pointer enabled
    focal_wizard:    FocalWizard | None           = None
    gaze_wizard:     GazeWizard | None            = None
    cal_input:       TextInput | None             = None
    cal_pick_mode:   bool                         = False
    cal_gaze_tid:    int | None                   = None
    cal_gaze_rows:   int | None                   = None
    cal_gaze_input:  TextInput | None             = None  # rows then cols
    show_help:       bool                         = False

    last_stats_time = time.time()
    last_time       = time.time()

    cv2.namedWindow("FaceWatch")
    cv2.setMouseCallback("FaceWatch", mouse.callback)

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        frame = cv2.flip(frame, 1)
        now = time.time()
        dt  = now - last_time
        last_time = now

        # ── Detect + Track ────────────────────────────────────────────────────
        result = detector.detect(frame)

        detections = []
        if result and result.face_landmarks:
            for i, lms in enumerate(result.face_landmarks):
                xs = [lm.x * frame_w for lm in lms]
                ys = [lm.y * frame.shape[0] for lm in lms]
                detections.append([min(xs), min(ys), max(xs), max(ys), 1.0])

        tracks = tracker.update(detections)
        active_track_ids = set(tracks.keys())
        frame_h = frame.shape[0]
        mp_map       = _match_tracks_to_mp(result, tracks, frame_w, frame_h)
        ptgaze_results = ptgaze_estimator.estimate(frame)
        ptgaze_map   = _match_ptgaze_to_tracks(ptgaze_results, tracks)

        # Clean up disappeared tracks
        for tid in list(expressions_map.keys()):
            if tid not in active_track_ids:
                expressions_map.pop(tid)
                gaze_map.pop(tid, None)
                gaze_states.pop(tid, None)
                alert_manager.drop(tid)
                recognizer.drop_track(tid)
                _last_absent[tid] = now
                _session_start.pop(tid, None)

        # ── Per-track analysis ────────────────────────────────────────────────
        for i, (track_id, bbox) in enumerate(tracks.items()):
            # Init per-track state on first sight
            if track_id not in expressions_map:
                expressions_map[track_id] = build_expressions()
                gaze_map[track_id]        = GazeTracker(screen_w, screen_h)
                _session_start[track_id]  = now

            crop = _crop(frame, bbox)
            if crop.size > 0:
                recognizer.submit(track_id, crop)

            identity = recognizer.get_identity(track_id)
            if identity.status == "known" and identity.face_id is not None:
                demo.maybe_run(identity.face_id, crop)

            blendshapes = _blendshapes_dict(result, mp_map.get(track_id, -1))
            landmarks   = _landmarks_list(result, mp_map.get(track_id, -1))

            for expr in expressions_map[track_id]:
                expr.update(blendshapes, landmarks, config)

            gaze_hit = ptgaze_map.get(track_id, (None, None))[1]
            gaze_state = gaze_map[track_id].update(gaze_hit, dt, config, calibration, identity.face_id)
            gaze_states[track_id] = gaze_state

            face_width = demo.get_face_width(identity.face_id) if identity.face_id else DEFAULT_FACE_WIDTH_CM
            focal_length_px = calibration.get("focal_length_px")
            dist_cm = distance.estimate(landmarks, face_width, focal_length_px, frame_w)

            ctx = build_alert_context(
                expressions=expressions_map[track_id],
                session_start=_session_start.get(track_id, now),
                last_absent=_last_absent.get(track_id, None),
                gaze_on_screen=gaze_state.on_screen_or_unknown,
                dist_cm=dist_cm,
                config=config,
                now=now,
            )
            events = alert_manager.update(track_id, ctx, dt)
            for event in events:
                if event.status in ALERT_LOGGABLE:
                    db.log_audit(f"alert_{event.status.value}", {"message": event.message})

        # ── Stats write ───────────────────────────────────────────────────────
        interval_sec: int = config.get("stats_interval_sec")
        if now - last_stats_time >= interval_sec:
            app, title = get_active_app()
            track_list = list(tracks.keys())
            # Pop for every track (known or not) so each interval starts from zero.
            gaze_off_interval = {
                tid: min(gaze_map[tid].pop_interval_off_sec(), float(interval_sec))
                for tid in track_list if tid in gaze_map
            }
            for track_id in track_list:
                identity = recognizer.get_identity(track_id)
                if identity.status != "known" or identity.face_id is None:
                    continue
                if not db.get_face_by_id(identity.face_id):
                    continue

                exprs      = expressions_map[track_id]
                face_width = demo.get_face_width(identity.face_id)
                lms        = _landmarks_list(result, mp_map.get(track_id, -1))
                dist_cm    = distance.estimate(lms, face_width, calibration.get("focal_length_px"), frame_w)
                gaze_off   = gaze_off_interval.get(track_id, 0.0)

                expr_stats = {e.name: e.get_interval_stats() for e in exprs}
                total_f    = expr_stats.get("blink_left", {}).get("total_frames", 1) or 1
                drowsy_f   = expr_stats.get("drowsy",     {}).get("active_frames", 0)
                neutral_f  = expr_stats.get("neutral",    {}).get("active_frames", 0)
                drowsy_pct = drowsy_f / total_f

                focus = compute_focus_score(
                    gaze_off_sec=gaze_off,
                    interval_sec=interval_sec,
                    drowsy_pct=drowsy_pct,
                    angry_count=expr_stats.get("angry",     {}).get("count", 0),
                    surprised_count=expr_stats.get("surprised", {}).get("count", 0),
                    distance_cm=dist_cm,
                    config=config,
                )

                proximity_alerts = alert_manager.count_active_by_type(track_id, AlertType.PROXIMITY)

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
                    "gaze_off_sec":        round(gaze_off, 2),
                    "proximity_alerts":    proximity_alerts,
                    "focus_score":         focus,
                    "active_app":          app,
                    "active_window_title": title,
                    "app_category":        get_app_category(app),
                }

                db.write_stats(identity.face_id, row)
                db.update_face_last_seen(identity.face_id)

            last_stats_time = now

        identities_snap = {tid: recognizer.get_identity(tid) for tid in tracks}
        distances_snap: dict[int, float] = {}
        focus_snap:     dict[int, float] = {}
        alert_snap:     dict[int, bool]  = {}
        demo_snap:      dict[int, dict | None] = {}
        for tid, bbox in tracks.items():
            ident = identities_snap[tid]
            fw    = demo.get_face_width(ident.face_id) if ident.face_id else DEFAULT_FACE_WIDTH_CM
            lms   = _landmarks_list(result, mp_map.get(tid, -1))
            distances_snap[tid] = distance.estimate(lms, fw, calibration.get("focal_length_px"), frame_w)
            alert_snap[tid] = alert_manager.active(tid)
            demo_snap[tid]  = demo.get_demographics(ident.face_id) if ident.face_id else None

        overlay.set_active_priorities(alert_manager.active_priorities())
        mouse.update_tracks(tracks, identities_snap)

        # ── Gaze pointers ───────────────────────────────────────────────
        for tid, gs in gaze_states.items():
            ident   = identities_snap.get(tid)
            face_id = ident.face_id if ident else None
            if face_id not in _gaze_pointer_ids:
                continue
            cal_overlay.show_gaze(face_id, gs.screen_x, gs.screen_y)

        frame = renderer.draw(
            frame, tracks, identities_snap, gaze_states,
            expressions_map, distances_snap, focus_snap, alert_snap,
            demo_snap, calibration,
        )
        mouse.draw_menu(frame)
        renderer.draw_watermark(frame)
        if show_help:
            renderer.draw_help_overlay(frame)

        # ── Text input overlay ────────────────────────────────────────────────
        if text_input and text_input.active:
            text_input.draw(frame)

        # ── Calibration wizard draw ────────────────────────────────────────────────
        if focal_wizard is not None:
            cal_lms   = _landmarks_list(result, next(iter(mp_map.values()), -1)) if mp_map else []
            wiz_state = focal_wizard.feed(cal_lms, frame_w)
            inp_text  = cal_input.value if cal_input else ""
            renderer.draw_calibration_step1(frame, wiz_state, inp_text)
            if cal_input and cal_input.active:
                cal_input.draw(frame)
            if wiz_state.done:
                focal_wizard = None
                cal_input    = None

        if cal_gaze_input is not None:
            prompt = "Grid rows (default 3):" if cal_gaze_rows is None else "Grid cols (default 3):"
            renderer.draw_calibration_grid_input(frame, prompt, cal_gaze_input.value)

        if gaze_wizard is not None:
            cal_tid = next(iter(mp_map.keys()), None)
            cal_gs  = gaze_states.get(cal_tid) if cal_tid else None
            sx = cal_gs.screen_x if cal_gs else 0.0
            sy = cal_gs.screen_y if cal_gs else 0.0
            wiz_state = gaze_wizard.feed(ptgaze_results, sx, sy)
            # After training, force GazeTracker to reload the new model
            if gaze_wizard.model_ready and cal_tid is not None and cal_tid in gaze_map:
                gaze_map[cal_tid].reset_model()
            cal_overlay.show(
                wiz_state.samples, wiz_state.needed,
                wiz_state.instruction, wiz_state.accepted,
                dot_rx=wiz_state.dot_rx, dot_ry=wiz_state.dot_ry,
                phase_t=wiz_state.phase_t, is_tune=wiz_state.is_tune,
            )
            # Show gaze pointer automatically during tune so user can see where they're looking
            if wiz_state.is_tune and cal_gs and cal_gs.face_present:
                ident = identities_snap.get(cal_tid)
                if ident and ident.face_id:
                    cal_overlay.show_gaze(ident.face_id, sx, sy)
            elif not wiz_state.is_tune:
                # Hide any active gaze pointer outside tune phase
                ident = identities_snap.get(cal_tid) if cal_tid else None
                if ident and ident.face_id:
                    cal_overlay.hide_gaze(ident.face_id)
            if wiz_state.done or wiz_state.cancelled:
                cal_overlay.hide()
                ident = identities_snap.get(cal_tid) if cal_tid else None
                if ident and ident.face_id:
                    cal_overlay.hide_gaze(ident.face_id)
                gaze_wizard = None

        # ── Display ─────────────────────────────────────────────────────────────────
        cv2.imshow("FaceWatch", frame)
        key    = cv2.waitKey(1) & 0xFF
        action = input_handler.handle(key)

        # ESC cancels active gaze wizard
        if key == 27 and gaze_wizard is not None:
            gaze_wizard.cancel()

        # ── Input handling ───────────────────────────────────────────────────────────────
        if focal_wizard is not None and cal_input and cal_input.active and key not in (0, 255):
            cal_input.feed(key)
            if cal_input.confirmed:
                try:
                    focal_wizard.set_distance_cm(float(cal_input.value))
                except ValueError:
                    cal_input.set_error("Enter a number.")
                else:
                    cal_input = None
            elif cal_input.cancelled:
                focal_wizard = None
                cal_input    = None
        elif cal_gaze_input is not None and key not in (0, 255):
            cal_gaze_input.feed(key)
            if cal_gaze_input.confirmed:
                try:
                    val = int(cal_gaze_input.value) if cal_gaze_input.value.strip() else 3
                    val = max(2, min(val, 10))  # 1 row/col = collinear targets, no 2-D fit
                except ValueError:
                    cal_gaze_input.set_error("Enter a number (2-10).")
                    val = None
                if val is not None:
                    if cal_gaze_rows is None:
                        cal_gaze_rows  = val
                        cal_gaze_input = TextInput("Grid cols (default 3):")
                    else:
                        cols = val
                        gaze_wizard = GazeWizard(
                            calibration, recognizer.get_identity(cal_gaze_tid).face_id,
                            gaze_map[cal_gaze_tid]._smoother,
                            screen_w, screen_h,
                            rows=cal_gaze_rows, cols=cols,
                        )
                        cal_overlay.start()
                        cal_gaze_input = None
                        cal_gaze_rows  = None
                        cal_gaze_tid   = None
            elif cal_gaze_input.cancelled:
                cal_gaze_input = None
                cal_gaze_rows  = None
                cal_gaze_tid   = None
        elif text_input and text_input.active:
            text_input.feed(key)
            if text_input.confirmed:
                name    = text_input.normalized
                display = text_input.value
                existing = db.get_face_by_name(name)
                if existing and pending_action in (MouseAction.REGISTER, MouseAction.RENAME):
                    text_input.set_error(f"Name '{display}' already exists.")
                else:
                    if pending_action == MouseAction.REGISTER and pending_track is not None:
                        crop = _crop(frame, tracks[pending_track]) if pending_track in tracks else np.zeros((1,1,3), dtype=np.uint8)
                        recognizer.register(pending_track, display, crop)
                    elif pending_action == MouseAction.RENAME and pending_track is not None:
                        identity = recognizer.get_identity(pending_track)
                        if identity.face_id:
                            db.rename_face(identity.face_id, name, display)
                            recognizer.rename_track(pending_track, identity.face_id)
                    elif pending_action == MouseAction.REASSIGN and pending_track is not None:
                        known = db.get_face_by_name(name)
                        if known:
                            recognizer.hard_reassign(pending_track, known["id"], display)
                        else:
                            text_input.set_error(f"No known face named '{display}'.")
                    if text_input.confirmed:
                        text_input     = None
                        pending_action = MouseAction.NONE
                        pending_track  = None
            elif text_input.cancelled:
                text_input     = None
                pending_action = MouseAction.NONE
                pending_track  = None
        else:
            mev = mouse.get_event()
            if mev.action == MouseAction.REGISTER:
                known_names    = [f["display_name"] for f in db.get_all_known_faces()]
                text_input     = TextInput("Register face — enter name:", known_names)
                pending_action = MouseAction.REGISTER
                pending_track  = mev.track_id
            elif mev.action == MouseAction.RENAME:
                text_input     = TextInput("Rename face — enter new name:")
                pending_action = MouseAction.RENAME
                pending_track  = mev.track_id
            elif mev.action == MouseAction.REASSIGN:
                known_names    = [f["display_name"] for f in db.get_all_known_faces()]
                text_input     = TextInput("Reassign to known face:", known_names)
                pending_action = MouseAction.REASSIGN
                pending_track  = mev.track_id
            elif mev.action == MouseAction.DELETE:
                if mev.track_id is not None:
                    identity = recognizer.get_identity(mev.track_id)
                    if identity.face_id:
                        db.delete_face(identity.face_id)
                        recognizer.force_reidentify(mev.track_id)
            elif mev.action == MouseAction.REIDENTIFY:
                if mev.track_id is not None:
                    recognizer.force_reidentify(mev.track_id)
            elif mev.action == MouseAction.CALIBRATE_DISTANCE:
                if mev.track_id is not None:
                    ident        = recognizer.get_identity(mev.track_id)
                    face_width   = demo.get_face_width(ident.face_id) if ident.face_id else DEFAULT_FACE_WIDTH_CM
                    focal_wizard = FocalWizard(calibration, face_width)
                    cal_input    = TextInput("Distance from camera (cm):")
                    cal_pick_mode = False
            elif mev.action == MouseAction.TOGGLE_GAZE_POINTER:
                if mev.track_id is not None:
                    ident = recognizer.get_identity(mev.track_id)
                    if ident.face_id:
                        if ident.face_id in _gaze_pointer_ids:
                            _gaze_pointer_ids.discard(ident.face_id)
                            cal_overlay.hide_gaze(ident.face_id)
                        else:
                            _gaze_pointer_ids.add(ident.face_id)
            elif mev.action == MouseAction.CALIBRATE_GAZE:
                if mev.track_id is not None:
                    ident = recognizer.get_identity(mev.track_id)
                    if ident.face_id and ident.status == "known" and mev.track_id in gaze_map:
                        cal_gaze_tid   = mev.track_id
                        cal_gaze_rows  = None
                        cal_gaze_input = TextInput("Grid rows (default 3):")

            if action == Action.QUIT:
                break
            elif action == Action.TOGGLE_DEBUG:
                renderer.toggle_debug()
            elif action == Action.FORCE_STATS:
                last_stats_time = 0
            elif action == Action.FORCE_REIDENTIFY:
                for tid in tracks:
                    if recognizer.get_identity(tid).status != "known":
                        recognizer.force_reidentify(tid)
            elif action == Action.OPEN_SETTINGS:
                open_settings(db_path, quit_key=config.get("key_quit"))
            elif action == Action.OPEN_REPORT:
                import webbrowser
                webbrowser.open(f"http://localhost:{report_port}")
            elif action == Action.TOGGLE_HELP:
                show_help = not show_help
            elif action == Action.CALIBRATE:
                if len(tracks) == 1:
                    tid          = next(iter(tracks))
                    ident        = recognizer.get_identity(tid)
                    face_width   = demo.get_face_width(ident.face_id) if ident.face_id else DEFAULT_FACE_WIDTH_CM
                    focal_wizard = FocalWizard(calibration, face_width)
                    cal_input    = TextInput("Distance from camera (cm):")
                else:
                    cal_pick_mode = True

    cap.release()
    cv2.destroyAllWindows()
    overlay.stop()
    cal_overlay.stop()
    db.log_audit("session_end", {"reason": "user_quit"})
    db.close()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    run()
