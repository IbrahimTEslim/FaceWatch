from dataclasses import dataclass, field

from storage.config_store import ConfigStore

# TODO (step 10): replace hardcoded thresholds with calibration-based offsets from calibration table
_H_LOW  = 0.35
_H_HIGH = 0.65
_V_LOW  = 0.35
_V_HIGH = 0.65

# Iris and eye landmark indices (MediaPipe 478-point model)
_L_OUTER  = 33;  _L_INNER  = 133; _L_TOP  = 159; _L_BOTTOM  = 145; _L_IRIS = 468
_R_OUTER  = 362; _R_INNER  = 263; _R_TOP  = 386; _R_BOTTOM  = 374; _R_IRIS = 473

# TODO: consider adding chronic partial-attention detection. Two approaches:
#
# Approach 1 — Total accumulator:
#   A second counter (_total_off_screen_sec) that only goes up, never down.
#   Resets at each stats interval. If total off-screen time in the last N minutes
#   exceeds a threshold, fire a secondary "low attention" alert.
#   Lives entirely inside GazeTracker. GazeState gets one extra field.
#
# Approach 2 — Rolling ratio (PERCLOS-style):
#   Track (off_screen_frames / total_frames) in a rolling time window (e.g. 60s).
#   If ratio exceeds e.g. 40%, fire a secondary alert.
#   Same deque pattern as Drowsy expression.
#
# Why not done yet:
#   The current bidirectional off_screen_timer handles "clearly looked away for a
#   long time" (continuous distraction). The focus score (step 13) handles chronic
#   partial attention by weighting gaze_on_screen at 40% of the score — a user at
#   50% attention will have a noticeably low focus score without needing a second alert.
#   Both approaches above are purely additive: new fields on GazeState, new internal
#   state in GazeTracker, zero changes outside gaze.py.


@dataclass
class GazeState:
    face_present:      bool  = False
    horizontal_ratio:  float = 0.0
    vertical_ratio:    float = 0.0
    direction:         str   = "unknown"
    on_screen:         bool  = False
    off_screen_sec:    float = 0.0
    alert_active:      bool  = False


def _ratio(iris: float, near: float, far: float) -> float:
    span = far - near
    return (iris - near) / span if abs(span) > 1e-6 else 0.5


def _direction(h: float, v: float) -> str:
    if v < _V_LOW:
        return "up"
    if v > _V_HIGH:
        return "down"
    if h < _H_LOW:
        return "left"
    if h > _H_HIGH:
        return "right"
    return "center"


class GazeTracker:
    def __init__(self):
        self._off_screen_timer: float = 0.0
        self._return_timer:     float = 0.0
        self._alert_active:     bool  = False

    def update(self, landmarks: list, dt: float, config: ConfigStore) -> GazeState:
        if not landmarks:
            # Face not present — pause all timers, return unknown state
            return GazeState(
                face_present=False,
                alert_active=self._alert_active,
                off_screen_sec=self._off_screen_timer,
            )

        alert_sec:  float = config.get("gaze_alert_sec")
        return_sec: float = config.get("gaze_return_sec")

        lm = landmarks
        h = (
            _ratio(lm[_L_IRIS].x, lm[_L_OUTER].x, lm[_L_INNER].x)
            + _ratio(lm[_R_IRIS].x, lm[_R_OUTER].x, lm[_R_INNER].x)
        ) / 2.0
        v = (
            _ratio(lm[_L_IRIS].y, lm[_L_TOP].y, lm[_L_BOTTOM].y)
            + _ratio(lm[_R_IRIS].y, lm[_R_TOP].y, lm[_R_BOTTOM].y)
        ) / 2.0

        direction = _direction(h, v)
        looking_at_screen = direction == "center"

        if not self._alert_active:
            if looking_at_screen:
                self._off_screen_timer = max(0.0, self._off_screen_timer - dt)
            else:
                self._off_screen_timer += dt
                if self._off_screen_timer >= alert_sec:
                    self._alert_active = True
                    self._return_timer = 0.0
        else:
            # Alert active — keep incrementing off_screen_timer for stats
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
            horizontal_ratio=h,
            vertical_ratio=v,
            direction=direction,
            on_screen=looking_at_screen,
            off_screen_sec=self._off_screen_timer,
            alert_active=self._alert_active,
        )
