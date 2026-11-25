import numpy as np
from dataclasses import dataclass

from storage.config_store import ConfigStore
from calibration.store import CalibrationStore
from calibration.smoother import GazeSmoother


@dataclass
class GazeState:
    face_present:   bool  = False
    # True only when this frame produced a calibrated screen estimate.
    # When False, screen_x/screen_y/on_screen/direction carry no information:
    # the face is uncalibrated or no gaze ray was available this frame.
    tracking:       bool  = False
    screen_x:       float = 0.0
    screen_y:       float = 0.0
    direction:      str   = "unknown"
    on_screen:      bool  = False
    off_screen_sec: float = 0.0
    alert_active:   bool  = False
    clearing_sec:   float = 0.0

    @property
    def on_screen_or_unknown(self) -> bool | None:
        """on_screen when tracking, else None (gaze unknown)."""
        return self.on_screen if self.tracking else None


def _direction(sx: float, sy: float, sw: int, sh: int) -> str:
    if sy < 0:   return "up"
    if sy > sh:  return "down"
    if sx < 0:   return "left"
    if sx > sw:  return "right"
    return "center"


class GazeTracker:
    def __init__(self, screen_w: int, screen_h: int, smoother: GazeSmoother | None = None):
        """screen_w/screen_h: primary screen size in overlay pixels (see ui.screen)."""
        self._sw, self._sh = screen_w, screen_h
        self._off_screen_timer: float = 0.0
        self._return_timer:     float = 0.0
        self._alert_active:     bool  = False
        self._interval_off_sec: float = 0.0   # tracked off-screen time since last pop
        self._affine_M                = None  # 2x3 numpy array
        self._affine_face_id: int | None = None
        self._smoother                = smoother if smoother is not None else GazeSmoother()

    def pop_interval_off_sec(self) -> float:
        """
        Seconds of tracked off-screen gaze since the previous call, then reset.
        Used for the per-interval stats row and Focus Score. Unlike the alert
        timer (off_screen_sec), this never decays while looking back.
        """
        value, self._interval_off_sec = self._interval_off_sec, 0.0
        return value

    def reset_model(self) -> None:
        """Force affine matrix reload on next frame."""
        self._affine_M = None
        self._affine_face_id = None

    def update(self, hit: tuple[float, float] | None, dt: float, config: ConfigStore,
               calibration: CalibrationStore | None = None,
               face_id: int | None = None) -> GazeState:
        """
        hit is (x_cm, y_cm) from ray_hit(), already computed by engine.
        Frames without a usable estimate (no face_id, no calibration, no hit)
        leave all timers untouched — unknown gaze is neither on nor off screen.
        """
        if face_id is None:
            return GazeState(
                face_present=False,
                alert_active=self._alert_active,
                off_screen_sec=self._off_screen_timer,
            )

        alert_sec:  float = config.get("gaze_alert_sec")
        return_sec: float = config.get("gaze_return_sec")
        margin_x:   int   = config.get("gaze_edge_margin_x_px")
        margin_y:   int   = config.get("gaze_edge_margin_y_px")
        sw, sh = self._sw, self._sh

        if face_id != self._affine_face_id:
            loaded = calibration.load_gaze_model(face_id) if calibration else None
            self._affine_M = loaded if isinstance(loaded, np.ndarray) and loaded.shape == (2, 3) else None
            self._affine_face_id = face_id

        if self._affine_M is None or hit is None:
            return GazeState(
                face_present=True,
                direction="unknown",
                on_screen=False,
                off_screen_sec=self._off_screen_timer,
                alert_active=self._alert_active,
            )

        uv = self._affine_M @ np.array([hit[0], hit[1], 1.0], dtype=np.float64)
        self._smoother.ema_alpha = config.get("gaze_smoothing")
        sx, sy = self._smoother.step(float(uv[0]), float(uv[1]))

        looking_at_screen = (
            -margin_x <= sx <= sw + margin_x and
            -margin_y <= sy <= sh + margin_y
        )
        direction = _direction(sx, sy, sw, sh)

        if not looking_at_screen:
            self._interval_off_sec += dt

        if not self._alert_active:
            if looking_at_screen:
                self._off_screen_timer = max(0.0, self._off_screen_timer - dt)
            else:
                self._off_screen_timer += dt
                if self._off_screen_timer >= alert_sec:
                    self._alert_active = True
                    self._return_timer = 0.0
        else:
            if not looking_at_screen:
                self._off_screen_timer += dt
                self._return_timer = 0.0
            else:
                self._return_timer += dt
                if self._return_timer >= return_sec:
                    self._alert_active = False
                    self._off_screen_timer = 0.0
                    self._return_timer = 0.0

        return GazeState(
            face_present=True,
            tracking=True,
            screen_x=sx,
            screen_y=sy,
            direction=direction,
            on_screen=looking_at_screen,
            off_screen_sec=self._off_screen_timer,
            alert_active=self._alert_active,
            clearing_sec=max(0.0, return_sec - self._return_timer) if self._alert_active else 0.0,
        )
