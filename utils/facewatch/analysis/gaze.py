from dataclasses import dataclass

from storage.config_store import ConfigStore
from calibration.store import CalibrationStore
from calibration.gaze_estimator import extract_features, BlinkDetector
from calibration.smoother import GazeSmoother


@dataclass
class GazeState:
    face_present:   bool  = False
    screen_x:       float = 0.0
    screen_y:       float = 0.0
    direction:      str   = "unknown"
    on_screen:      bool  = False
    off_screen_sec: float = 0.0
    alert_active:   bool  = False
    clearing_sec:   float = 0.0


def _direction(sx: float, sy: float, sw: int, sh: int) -> str:
    if sy < 0:   return "up"
    if sy > sh:  return "down"
    if sx < 0:   return "left"
    if sx > sw:  return "right"
    return "center"


class GazeTracker:
    def __init__(self):
        self._off_screen_timer: float = 0.0
        self._return_timer:     float = 0.0
        self._alert_active:     bool  = False
        self._model                   = None
        self._model_face_id:    int | None = None
        self._blink_detector          = BlinkDetector()
        self._smoother                = GazeSmoother()

    def reset_model(self) -> None:
        """Force model reload on next frame."""
        self._model = None
        self._model_face_id = None

    def update(self, landmarks: list, dt: float, config: ConfigStore,
               calibration: CalibrationStore | None = None,
               face_id: int | None = None) -> GazeState:
        if not landmarks:
            return GazeState(
                face_present=False,
                alert_active=self._alert_active,
                off_screen_sec=self._off_screen_timer,
            )

        alert_sec:  float = config.get("gaze_alert_sec")
        return_sec: float = config.get("gaze_return_sec")
        margin_px:  float = config.get("gaze_edge_margin_px")
        sw:         int   = config.get("screen_w_px")
        sh:         int   = config.get("screen_h_px")

        if face_id != self._model_face_id:
            self._model = calibration.load_gaze_model(face_id) if (calibration and face_id is not None) else None
            self._model_face_id = face_id

        if self._blink_detector.is_blinking(landmarks):
            return GazeState(
                face_present=True,
                direction="unknown",
                on_screen=self._alert_active is False,
                off_screen_sec=self._off_screen_timer,
                alert_active=self._alert_active,
            )

        features, _ = extract_features(landmarks)

        if self._model is None or features is None:
            return GazeState(
                face_present=True,
                direction="unknown",
                on_screen=False,
                off_screen_sec=self._off_screen_timer,
                alert_active=self._alert_active,
            )

        raw_sx, raw_sy = self._model.predict(features)
        sx, sy         = self._smoother.step(raw_sx, raw_sy)

        looking_at_screen = (
            -margin_px <= sx <= sw + margin_px and
            -margin_px <= sy <= sh + margin_px
        )
        direction = _direction(sx, sy, sw, sh)

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
            screen_x=sx,
            screen_y=sy,
            direction=direction,
            on_screen=looking_at_screen,
            off_screen_sec=self._off_screen_timer,
            alert_active=self._alert_active,
            clearing_sec=max(0.0, return_sec - self._return_timer) if self._alert_active else 0.0,
        )
