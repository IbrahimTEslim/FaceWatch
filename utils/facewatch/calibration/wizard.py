import threading
import time
from dataclasses import dataclass
from enum import Enum, auto

import numpy as np

import cv2

from calibration.store import CalibrationStore
from calibration.smoother import GazeSmoother
from calibration.eye_features import extract_features, BlinkDetector
from calibration.ridge_correction import Sample, train_correction, apply_affine
from demographics.face_width import DEFAULT_FACE_WIDTH_CM

_LEFT_CHEEK    = 234
_RIGHT_CHEEK   = 454
_FOCAL_SAMPLES = 30

_MARGIN_RATIO         = 0.10
_INTRO_SEC            = 4.0
_PULSE_SEC            = 1.0
_CAPTURE_SEC          = 1.5
_TUNE_PROXIMITY_RATIO = 0.20
_TUNE_COLLECT_SEC     = 0.5
_TUNE_INITIAL_DELAY   = 0.5
_DEFAULT_ROWS         = 3
_DEFAULT_COLS         = 3


def _grid_points(sw: int, sh: int, rows: int, cols: int) -> list[tuple[int, int]]:
    """Serpentine grid ported from eyetrax compute_grid_points_from_shape."""
    mx = int(sw * _MARGIN_RATIO)
    my = int(sh * _MARGIN_RATIO)
    gw, gh   = sw - 2 * mx, sh - 2 * my
    step_x   = 0 if cols <= 1 else gw / (cols - 1)
    step_y   = 0 if rows <= 1 else gh / (rows - 1)
    indices  = []
    for r in range(rows):
        cols_range = range(cols) if r % 2 == 0 else range(cols - 1, -1, -1)
        indices.extend((r, c) for c in cols_range)
    return [(mx + int(c * step_x), my + int(r * step_y)) for r, c in indices]


def fit_gaze_affine(raw_pts, scr_pts) -> np.ndarray | None:
    """
    Fit the 2x3 affine mapping ray-hit (cm) -> screen (px) from per-dot medians.

    Uses least-median-of-squares: robust to a minority of bad dots (user looked
    elsewhere) without a pixel threshold to tune. A synthetic benchmark (9-point
    grid, 30-150 px gaze noise, with/without one bad dot) gave 3-4x lower mean
    screen error than the previous RANSAC with a 3 px threshold — which, given
    real gaze noise, kept only ~3 points. Falls back to plain least squares.
    Returns None when the points can't determine an affine map.
    """
    raw = np.asarray(raw_pts, dtype=np.float64).reshape(-1, 2)
    scr = np.asarray(scr_pts, dtype=np.float64).reshape(-1, 2)
    if len(raw) < 3 or len(raw) != len(scr):
        return None
    A = np.hstack([raw, np.ones((len(raw), 1))])
    if np.linalg.matrix_rank(A) < 3:
        return None  # collinear hits/targets — mapping undetermined

    M, _ = cv2.estimateAffine2D(raw.astype(np.float32), scr.astype(np.float32),
                                method=cv2.LMEDS)
    if M is None or not np.all(np.isfinite(M)):
        X, *_ = np.linalg.lstsq(A, scr, rcond=None)
        M = X.T
    return M.astype(np.float64)


_ADAPTIVE_MARGIN_RATIO = 0.08
_ADAPTIVE_CANDIDATES   = 30
_ADAPTIVE_REFIT_EVERY  = 10


def blue_noise_points(sw: int, sh: int, n: int, existing: list[tuple[int, int]] = (),
                      rng: np.random.Generator | None = None) -> list[tuple[int, int]]:
    """
    n well-spread screen points (best-candidate blue noise, as in eyetrax's
    adaptive calibration): each new point is the candidate farthest from all
    points so far, including `existing` (the grid), so extra points fill gaps.
    """
    rng = rng or np.random.default_rng()
    mx, my = int(sw * _ADAPTIVE_MARGIN_RATIO), int(sh * _ADAPTIVE_MARGIN_RATIO)
    placed = [tuple(p) for p in existing]
    out: list[tuple[int, int]] = []
    for _ in range(max(0, n)):
        cand = np.column_stack([rng.integers(mx, sw - mx + 1, _ADAPTIVE_CANDIDATES),
                                rng.integers(my, sh - my + 1, _ADAPTIVE_CANDIDATES)])
        if placed:
            d2 = ((cand[:, None, :] - np.array(placed)[None, :, :]) ** 2).sum(-1).min(axis=1)
            best = cand[int(np.argmax(d2))]
        else:
            best = cand[0]
        pt = (int(best[0]), int(best[1]))
        placed.append(pt)
        out.append(pt)
    return out


def _tune_points(sw: int, sh: int) -> list[tuple[int, int]]:
    return [
        (sw // 2,     sh // 4),
        (sw // 4,     3 * sh // 4),
        (3 * sw // 4, 3 * sh // 4),
    ]


class _Phase(Enum):
    INTRO        = auto()
    WAITING      = auto()
    PULSE        = auto()
    CAPTURE      = auto()
    TRAINING     = auto()
    TRAINING_CORRECTION = auto()
    TUNE_PULSE   = auto()
    TUNE_CAPTURE = auto()
    DONE         = auto()


@dataclass
class WizardState:
    samples:     int
    needed:      int
    instruction: str
    accepted:    bool
    done:        bool
    cancelled:   bool  = False
    dot_rx:      float | None = None
    dot_ry:      float | None = None
    phase_t:     float = 0.0
    is_tune:     bool  = False
    show_gaze:   bool  = False   # show the live gaze pointer (adaptive points)


class FocalWizard:
    """Collects focal_length_px. Caller must call set_distance_cm() first."""

    def __init__(self, store: CalibrationStore, face_width_cm: float = DEFAULT_FACE_WIDTH_CM):
        self._store          = store
        self._face_width_cm  = face_width_cm
        self._samples:       list = []
        self._distance_cm:   float | None = None
        self._stable_window: list = []

    def set_distance_cm(self, distance_cm: float) -> None:
        self._distance_cm = distance_cm

    def feed(self, landmarks: list, frame_w: int) -> WizardState:
        if self._distance_cm is None:
            return WizardState(
                samples=0, needed=_FOCAL_SAMPLES,
                instruction="Type your distance from the camera in cm, then press Enter.",
                accepted=False, done=False,
            )

        accepted = False
        if landmarks and len(landmarks) > _RIGHT_CHEEK:
            nose = landmarks[1]
            self._stable_window.append((nose.x, nose.y))
            if len(self._stable_window) > 5:
                self._stable_window.pop(0)
            if len(self._stable_window) == 5:
                xs  = [p[0] for p in self._stable_window]
                ys  = [p[1] for p in self._stable_window]
                mx  = sum(xs) / 5
                my  = sum(ys) / 5
                var = sum((x - mx) ** 2 + (y - my) ** 2 for x, y in self._stable_window) / 5
                accepted = var < 5e-6
            if accepted:
                lx = landmarks[_LEFT_CHEEK].x  * frame_w
                rx = landmarks[_RIGHT_CHEEK].x * frame_w
                px_width = abs(rx - lx)
                if px_width >= 1.0:
                    self._samples.append((px_width * self._distance_cm) / self._face_width_cm)

        if len(self._samples) >= _FOCAL_SAMPLES:
            self._store.set("focal_length_px", sum(self._samples) / len(self._samples))
            return WizardState(
                samples=_FOCAL_SAMPLES, needed=_FOCAL_SAMPLES,
                instruction="Focal length calibrated.",
                accepted=accepted, done=True,
            )

        return WizardState(
            samples=len(self._samples), needed=_FOCAL_SAMPLES,
            instruction=f"Sit at {self._distance_cm:.0f} cm and hold still.",
            accepted=accepted, done=False,
        )


class GazeWizard:
    """
    9-point calibration + Kalman tune pass, fully feed-driven.
    Engine calls feed(ptgaze_results, sx, sy, landmarks) every frame.
    ptgaze_results is the calibrating face's PtgazeEstimator result — already computed by engine.
    sx/sy are current smoothed gaze predictions in pixels — only used during tune phase.
    landmarks are the calibrating face's MediaPipe landmarks — only used when
    ridge_enabled (optional eyetrax correction, calibration/ridge_correction.py).
    On completion, fitted affine M saved to CalibrationStore; with ridge_enabled
    the correction is trained in a background thread and saved only if it
    beats affine-only on held-out dots (else any old correction is removed).
    Smoother is tuned in-place. `report` summarises the calibration.
    """

    def __init__(self, store: CalibrationStore, face_id: int,
                 smoother: GazeSmoother, sw: int, sh: int,
                 rows: int = _DEFAULT_ROWS, cols: int = _DEFAULT_COLS,
                 ridge_enabled: bool = False, adaptive_points: int = 0):
        self._store        = store
        self._face_id      = face_id
        self._smoother     = smoother
        self._sw, self._sh = sw, sh
        self._ridge_enabled = ridge_enabled
        self._blink         = BlinkDetector()
        self._cur_feats: np.ndarray | None = None   # this frame's eye features (None on blink)
        self._frame_samples: list[Sample] = []      # per-frame samples for the correction
        self._tune_samples:  list[tuple]  = []      # (target, hit, feats) for held-out check
        self._train_thread:  threading.Thread | None = None
        self._train_result:  tuple | None = None
        self._correction     = None
        self._report: dict   = {"correction_enabled": ridge_enabled,
                                "adaptive_points": max(0, adaptive_points)}

        grid           = _grid_points(sw, sh, rows, cols)
        self._n_grid   = len(grid)
        self._pts      = grid + blue_noise_points(sw, sh, adaptive_points, existing=grid)
        self._tune_pts = _tune_points(sw, sh)
        self._pt_idx   = 0
        self._phase    = _Phase.INTRO
        self._phase_start = time.monotonic()

        self._raw_pts: list[np.ndarray]    = []  # ray_hit medians
        self._scr_pts: list[list[float]]   = []  # screen pixel targets
        self._dot_samples: list[tuple]     = []  # ray_hit samples for current dot
        self._affine_M: np.ndarray | None  = None
        self._cancelled = False
        self._model_ready = False  # True for one frame after training completes

        self._tune_idx        = 0
        self._tune_gaze:      list[list[float]] = []
        self._tune_start:     float | None = None
        self._tune_collecting = False
        self._tune_col_start: float | None = None
        self._all_tune_gaze:  list[list[float]] = []
        self._tune_point_samples: list[tuple] = []

    @property
    def face_id(self) -> int:
        return self._face_id

    def cancel(self) -> None:
        self._cancelled = True

    @property
    def model_ready(self) -> bool:
        """True for one call after training completes — engine uses this to reset GazeTracker cache."""
        if self._model_ready:
            self._model_ready = False
            return True
        return False

    @property
    def report(self) -> dict:
        """Calibration summary (dots used, correction CV result, tune-point errors)."""
        return dict(self._report)

    def _frame_features(self, landmarks: list | None) -> np.ndarray | None:
        if not self._ridge_enabled or not landmarks:
            return None
        if self._blink.is_blinking(landmarks):   # also keeps the EAR baseline current
            return None
        feats, _ = extract_features(landmarks)
        return feats

    def _rx(self, x: int) -> float:
        return x / self._sw

    def _ry(self, y: int) -> float:
        return y / self._sh

    def feed(self, ptgaze_results: list,
             sx: float = 0.0, sy: float = 0.0,
             landmarks: list | None = None) -> WizardState:
        if self._cancelled:
            return WizardState(
                samples=0, needed=len(self._pts),
                instruction="Calibration cancelled.",
                accepted=False, done=False, cancelled=True,
            )
        now     = time.monotonic()
        elapsed = now - self._phase_start
        self._cur_feats = self._frame_features(landmarks)
        if self._phase == _Phase.INTRO:        return self._phase_intro(now, elapsed)
        if self._phase == _Phase.WAITING:      return self._phase_waiting(now, ptgaze_results)
        if self._phase == _Phase.PULSE:        return self._phase_pulse(now, elapsed)
        if self._phase == _Phase.CAPTURE:      return self._phase_capture(now, elapsed, ptgaze_results)
        if self._phase == _Phase.TRAINING:     return self._phase_training(now)
        if self._phase == _Phase.TRAINING_CORRECTION: return self._phase_training_correction(now)
        if self._phase == _Phase.TUNE_PULSE:   return self._phase_tune_pulse(now, elapsed)
        if self._phase == _Phase.TUNE_CAPTURE: return self._phase_tune_capture(now, sx, sy, ptgaze_results)
        return WizardState(
            samples=len(self._pts), needed=len(self._pts),
            instruction=self._done_message(),
            accepted=False, done=True,
        )

    def _done_message(self) -> str:
        aff = self._report.get("tune_affine_err_px")
        cor = self._report.get("tune_corrected_err_px")
        if aff is None:
            return "Gaze calibration complete."
        if cor is None:
            return f"Gaze calibration complete. Check error ~{aff:.0f}px."
        return f"Gaze calibration complete. Check error ~{aff:.0f}px affine, ~{cor:.0f}px corrected."

    def _phase_intro(self, now: float, elapsed: float) -> WizardState:
        if elapsed >= _INTRO_SEC:
            self._phase = _Phase.WAITING
            self._phase_start = now
        return WizardState(
            samples=0, needed=len(self._pts),
            instruction=f"{len(self._pts)}-point gaze calibration. Look at each dot as it appears and hold still.",
            accepted=False, done=False,
        )

    def _phase_waiting(self, now: float, ptgaze_results: list) -> WizardState:
        if ptgaze_results:
            self._phase = _Phase.PULSE
            self._phase_start = now
        return WizardState(
            samples=0, needed=len(self._pts),
            instruction="Look at the screen and hold still...",
            accepted=False, done=False,
        )

    def _in_adaptive(self) -> bool:
        return self._pt_idx >= self._n_grid

    def _point_label(self) -> str:
        if self._in_adaptive():
            n_extra = len(self._pts) - self._n_grid
            return f"Extra point {self._pt_idx - self._n_grid + 1} of {n_extra}"
        return f"Point {self._pt_idx + 1} of {self._n_grid}"

    def _maybe_interim_refit(self) -> None:
        """
        Adaptive points: refit after the grid and every few extra points so the
        live gaze pointer improves while the user continues.
        """
        idx = self._pt_idx
        if not (self._n_grid <= idx < len(self._pts)):
            return
        if (idx - self._n_grid) % _ADAPTIVE_REFIT_EVERY or len(self._raw_pts) < 4:
            return
        M = fit_gaze_affine(self._raw_pts, self._scr_pts)
        if M is None:
            return
        if self._affine_M is None:
            # the old correction was learned against the previous affine
            self._store.delete_gaze_correction(self._face_id)
        self._affine_M = M
        self._store.save_gaze_model(self._face_id, M)
        self._model_ready = True

    def _phase_pulse(self, now: float, elapsed: float) -> WizardState:
        x, y = self._pts[self._pt_idx]
        if elapsed >= _PULSE_SEC:
            self._phase = _Phase.CAPTURE
            self._phase_start = now
        return WizardState(
            samples=self._pt_idx, needed=len(self._pts),
            instruction=f"{self._point_label()} — look at the dot",
            accepted=False, done=False,
            dot_rx=self._rx(x), dot_ry=self._ry(y),
            phase_t=min(elapsed / _PULSE_SEC, 1.0),
            show_gaze=self._in_adaptive(),
        )

    def _phase_capture(self, now: float, elapsed: float, ptgaze_results: list) -> WizardState:
        x, y = self._pts[self._pt_idx]
        label, show_gaze = self._point_label(), self._in_adaptive()
        for _, hit in ptgaze_results:
            if hit is not None:
                self._dot_samples.append(hit)
                if self._cur_feats is not None:
                    self._frame_samples.append(Sample(
                        dot=self._pt_idx, target=np.array([x, y], dtype=np.float64),
                        hit=np.asarray(hit, dtype=np.float64), features=self._cur_feats))
        if elapsed >= _CAPTURE_SEC:
            if len(self._dot_samples) >= 5:
                med = np.median(self._dot_samples, axis=0)
                self._raw_pts.append(med)
                self._scr_pts.append([float(x), float(y)])
            self._dot_samples = []
            self._pt_idx += 1
            self._maybe_interim_refit()
            self._phase = _Phase.PULSE if self._pt_idx < len(self._pts) else _Phase.TRAINING
            self._phase_start = now
        return WizardState(
            samples=self._pt_idx, needed=len(self._pts),
            instruction=f"{label} — hold still",
            accepted=True, done=False,
            dot_rx=self._rx(x), dot_ry=self._ry(y),
            phase_t=min(elapsed / _CAPTURE_SEC, 1.0),
            show_gaze=show_gaze,
        )

    def _phase_training(self, now: float) -> WizardState:
        M = None
        if len(self._raw_pts) >= 4:
            M = fit_gaze_affine(self._raw_pts, self._scr_pts)
            if M is not None:
                self._affine_M = M
                self._store.save_gaze_model(self._face_id, M)
        self._report["affine_dots"] = len(self._raw_pts)
        self._report["affine_saved"] = M is not None

        if M is not None and self._ridge_enabled:
            samples = list(self._frame_samples)
            self._train_thread = threading.Thread(
                target=self._train_correction_worker, args=(samples, M), daemon=True)
            self._train_thread.start()
            self._phase = _Phase.TRAINING_CORRECTION
            self._phase_start = now
            return WizardState(
                samples=len(self._pts), needed=len(self._pts),
                instruction="Calibrated! Training gaze correction...",
                accepted=False, done=False,
            )
        if M is not None:
            # A correction learned against the previous affine no longer applies.
            self._store.delete_gaze_correction(self._face_id)
        return self._start_tune(now)

    def _train_correction_worker(self, samples: list, M: np.ndarray) -> None:
        try:
            self._train_result = train_correction(samples, fit_gaze_affine, M)
        except Exception as e:  # never let the correction break calibration
            self._train_result = (None, {"accepted": False, "reason": f"error: {e}"})

    def _phase_training_correction(self, now: float) -> WizardState:
        if self._train_thread is not None and self._train_thread.is_alive():
            return WizardState(
                samples=len(self._pts), needed=len(self._pts),
                instruction="Calibrated! Training gaze correction...",
                accepted=False, done=False,
            )
        model, rep = self._train_result or (None, {"accepted": False, "reason": "no result"})
        rep = rep if isinstance(rep, dict) else rep.as_dict()
        if model is not None:
            self._store.save_gaze_correction(self._face_id, model, rep)
            self._correction = model
        else:
            self._store.delete_gaze_correction(self._face_id)
        self._report["correction"] = rep
        return self._start_tune(now)

    def _start_tune(self, now: float) -> WizardState:
        self._model_ready = True
        self._phase = _Phase.TUNE_PULSE
        self._phase_start = now
        self._tune_idx = 0
        return WizardState(
            samples=len(self._pts), needed=len(self._pts),
            instruction="Calibrated! Now fine-tuning...",
            accepted=False, done=False,
        )

    def _phase_tune_pulse(self, now: float, elapsed: float) -> WizardState:
        x, y = self._tune_pts[self._tune_idx]
        if elapsed >= _PULSE_SEC:
            self._phase = _Phase.TUNE_CAPTURE
            self._phase_start = now
            self._tune_start      = None
            self._tune_collecting = False
            self._tune_col_start  = None
            self._tune_gaze       = []
        return WizardState(
            samples=self._tune_idx, needed=len(self._tune_pts),
            instruction=f"Tune point {self._tune_idx + 1} of {len(self._tune_pts)} — look at the dot",
            accepted=False, done=False,
            dot_rx=self._rx(x), dot_ry=self._ry(y),
            phase_t=min(elapsed / _PULSE_SEC, 1.0),
            is_tune=True,
        )

    def _phase_tune_capture(self, now: float, sx: float, sy: float,
                            ptgaze_results: list | None = None) -> WizardState:
        x, y = self._tune_pts[self._tune_idx]
        prox = self._sw * _TUNE_PROXIMITY_RATIO
        near = (sx - x) ** 2 + (sy - y) ** 2 <= prox ** 2
        if near:
            if self._tune_start is None:
                self._tune_start = now
            if not self._tune_collecting and now - self._tune_start >= _TUNE_INITIAL_DELAY:
                self._tune_collecting = True
                self._tune_col_start  = now
                self._tune_point_samples = []
            if self._tune_collecting:
                self._tune_gaze.append([sx, sy])
                for _, hit in (ptgaze_results or []):
                    if hit is not None:
                        self._tune_point_samples.append(
                            (np.array([x, y], dtype=np.float64), np.asarray(hit, dtype=np.float64),
                             self._cur_feats))
                if now - self._tune_col_start >= _TUNE_COLLECT_SEC:
                    self._all_tune_gaze.extend(self._tune_gaze)
                    self._tune_samples.extend(self._tune_point_samples)
                    self._tune_idx += 1
                    if self._tune_idx >= len(self._tune_pts):
                        self._finish_tune()
                        self._phase = _Phase.DONE
                    else:
                        self._phase = _Phase.TUNE_PULSE
                    self._phase_start = now
        else:
            self._tune_start      = None
            self._tune_collecting = False
            self._tune_col_start  = None
            self._tune_gaze       = []
            self._tune_point_samples = []
        return WizardState(
            samples=self._tune_idx, needed=len(self._tune_pts),
            instruction=f"Tune point {self._tune_idx + 1} of {len(self._tune_pts)} — look at the dot",
            accepted=self._tune_collecting, done=False,
            dot_rx=self._rx(x), dot_ry=self._ry(y),
            phase_t=min((now - self._tune_col_start) / _TUNE_COLLECT_SEC, 1.0)
                    if self._tune_collecting else 0.0,
            is_tune=True,
        )

    def _finish_tune(self) -> None:
        self._report_tune_errors()
        pts = np.array(self._all_tune_gaze)
        if pts.shape[0] < 2:
            return
        var = np.var(pts, axis=0)
        self._smoother.tune_from_variance(float(var[0]), float(var[1]))

    def _report_tune_errors(self) -> None:
        """
        Unsmoothed error at the tune dots, which were not used for training:
        a held-out check of the affine model (and of the correction, if any).
        """
        if self._affine_M is None or not self._tune_samples:
            return
        aff, cor = [], []
        for target, hit, feats in self._tune_samples:
            p = apply_affine(self._affine_M, hit)[0]
            aff.append(np.linalg.norm(p - target))
            if self._correction is not None and feats is not None:
                cor.append(np.linalg.norm(p + self._correction.predict(feats) - target))
        self._report["tune_affine_err_px"] = round(float(np.median(aff)), 1)
        if cor:
            self._report["tune_corrected_err_px"] = round(float(np.median(cor)), 1)
