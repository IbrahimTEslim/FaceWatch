import time
from dataclasses import dataclass
from enum import Enum, auto

import numpy as np

import cv2

from calibration.store import CalibrationStore
from calibration.smoother import GazeSmoother
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
    Engine calls feed(ptgaze_results, sx, sy) every frame.
    ptgaze_results is the output of PtgazeEstimator.estimate() — already computed by engine.
    sx/sy are current smoothed gaze predictions in pixels — only used during tune phase.
    On completion, fitted affine M saved to CalibrationStore.
    Smoother is tuned in-place.
    """

    def __init__(self, store: CalibrationStore, face_id: int,
                 smoother: GazeSmoother, sw: int, sh: int,
                 rows: int = _DEFAULT_ROWS, cols: int = _DEFAULT_COLS):
        self._store        = store
        self._face_id      = face_id
        self._smoother     = smoother
        self._sw, self._sh = sw, sh

        self._pts      = _grid_points(sw, sh, rows, cols)
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

    def cancel(self) -> None:
        self._cancelled = True

    @property
    def model_ready(self) -> bool:
        """True for one call after training completes — engine uses this to reset GazeTracker cache."""
        if self._model_ready:
            self._model_ready = False
            return True
        return False

    def _rx(self, x: int) -> float:
        return x / self._sw

    def _ry(self, y: int) -> float:
        return y / self._sh

    def feed(self, ptgaze_results: list,
             sx: float = 0.0, sy: float = 0.0) -> WizardState:
        if self._cancelled:
            return WizardState(
                samples=0, needed=len(self._pts),
                instruction="Calibration cancelled.",
                accepted=False, done=False, cancelled=True,
            )
        now     = time.monotonic()
        elapsed = now - self._phase_start
        if self._phase == _Phase.INTRO:        return self._phase_intro(now, elapsed)
        if self._phase == _Phase.WAITING:      return self._phase_waiting(now, ptgaze_results)
        if self._phase == _Phase.PULSE:        return self._phase_pulse(now, elapsed)
        if self._phase == _Phase.CAPTURE:      return self._phase_capture(now, elapsed, ptgaze_results)
        if self._phase == _Phase.TRAINING:     return self._phase_training(now)
        if self._phase == _Phase.TUNE_PULSE:   return self._phase_tune_pulse(now, elapsed)
        if self._phase == _Phase.TUNE_CAPTURE: return self._phase_tune_capture(now, sx, sy)
        return WizardState(
            samples=len(self._pts), needed=len(self._pts),
            instruction="Gaze calibration complete.",
            accepted=False, done=True,
        )

    def _phase_intro(self, now: float, elapsed: float) -> WizardState:
        if elapsed >= _INTRO_SEC:
            self._phase = _Phase.WAITING
            self._phase_start = now
        return WizardState(
            samples=0, needed=len(self._pts),
            instruction="9-point gaze calibration. Look at each dot as it appears and hold still.",
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

    def _phase_pulse(self, now: float, elapsed: float) -> WizardState:
        x, y = self._pts[self._pt_idx]
        if elapsed >= _PULSE_SEC:
            self._phase = _Phase.CAPTURE
            self._phase_start = now
        return WizardState(
            samples=self._pt_idx, needed=len(self._pts),
            instruction=f"Point {self._pt_idx + 1} of {len(self._pts)} — look at the dot",
            accepted=False, done=False,
            dot_rx=self._rx(x), dot_ry=self._ry(y),
            phase_t=min(elapsed / _PULSE_SEC, 1.0),
        )

    def _phase_capture(self, now: float, elapsed: float, ptgaze_results: list) -> WizardState:
        x, y = self._pts[self._pt_idx]
        for _, hit in ptgaze_results:
            if hit is not None:
                self._dot_samples.append(hit)
        if elapsed >= _CAPTURE_SEC:
            if len(self._dot_samples) >= 5:
                med = np.median(self._dot_samples, axis=0)
                self._raw_pts.append(med)
                self._scr_pts.append([float(x), float(y)])
            self._dot_samples = []
            self._pt_idx += 1
            self._phase = _Phase.PULSE if self._pt_idx < len(self._pts) else _Phase.TRAINING
            self._phase_start = now
        return WizardState(
            samples=self._pt_idx, needed=len(self._pts),
            instruction=f"Point {self._pt_idx + 1} of {len(self._pts)} — hold still",
            accepted=True, done=False,
            dot_rx=self._rx(x), dot_ry=self._ry(y),
            phase_t=min(elapsed / _CAPTURE_SEC, 1.0),
        )

    def _phase_training(self, now: float) -> WizardState:
        if len(self._raw_pts) >= 4:
            raw_arr = np.array(self._raw_pts, dtype=np.float32)
            scr_arr = np.array(self._scr_pts, dtype=np.float32)
            M, _ = cv2.estimateAffine2D(
                raw_arr, scr_arr,
                method=cv2.RANSAC,
                ransacReprojThreshold=3.0,
                maxIters=2000,
            )
            if M is not None:
                self._affine_M = M
                self._store.save_gaze_model(self._face_id, M)
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

    def _phase_tune_capture(self, now: float, sx: float, sy: float) -> WizardState:
        x, y = self._tune_pts[self._tune_idx]
        prox = self._sw * _TUNE_PROXIMITY_RATIO
        near = (sx - x) ** 2 + (sy - y) ** 2 <= prox ** 2
        if near:
            if self._tune_start is None:
                self._tune_start = now
            if not self._tune_collecting and now - self._tune_start >= _TUNE_INITIAL_DELAY:
                self._tune_collecting = True
                self._tune_col_start  = now
            if self._tune_collecting:
                self._tune_gaze.append([sx, sy])
                if now - self._tune_col_start >= _TUNE_COLLECT_SEC:
                    self._all_tune_gaze.extend(self._tune_gaze)
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
        pts = np.array(self._all_tune_gaze)
        if pts.shape[0] < 2:
            return
        var = np.var(pts, axis=0)
        self._smoother.tune_from_variance(float(var[0]), float(var[1]))
