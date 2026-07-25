from dataclasses import dataclass, field
from collections import deque

_L_IRIS      = 468
_R_IRIS      = 473
_IRIS_TOL    = 0.15   # accept iris within ±0.15 of 0.50
_STABLE_WIN  = 5      # frames for variance window
_STABLE_MAX  = 5e-6   # max landmark variance to be considered stable


@dataclass
class SampleResult:
    accepted:  bool
    iris_h:    float
    iris_v:    float
    variance:  float


class SampleCollector:
    """
    Evaluates a single landmark frame.
    Accepts if head is stable AND iris is near screen center.
    """

    def __init__(self):
        self._window: deque[tuple[float, float]] = deque(maxlen=_STABLE_WIN)

    def evaluate(self, landmarks: list) -> SampleResult:
        if not landmarks or len(landmarks) <= _R_IRIS:
            return SampleResult(accepted=False, iris_h=0.0, iris_v=0.0, variance=1.0)

        iris_h = (landmarks[_L_IRIS].x + landmarks[_R_IRIS].x) / 2.0
        iris_v = (landmarks[_L_IRIS].y + landmarks[_R_IRIS].y) / 2.0

        nose = landmarks[1]
        self._window.append((nose.x, nose.y))

        variance = 0.0
        if len(self._window) == _STABLE_WIN:
            xs = [p[0] for p in self._window]
            ys = [p[1] for p in self._window]
            mx = sum(xs) / _STABLE_WIN
            my = sum(ys) / _STABLE_WIN
            variance = sum((x - mx) ** 2 + (y - my) ** 2 for x, y in self._window) / _STABLE_WIN

        stable      = len(self._window) == _STABLE_WIN and variance < _STABLE_MAX
        iris_ok     = abs(iris_h - 0.50) < _IRIS_TOL and abs(iris_v - 0.50) < _IRIS_TOL
        accepted    = stable and iris_ok

        return SampleResult(accepted=accepted, iris_h=iris_h, iris_v=iris_v, variance=variance)
