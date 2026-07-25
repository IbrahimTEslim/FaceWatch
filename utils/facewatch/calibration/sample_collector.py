from dataclasses import dataclass
from collections import deque

from analysis.gaze import (
    _offset,
    _L_OUTER, _L_INNER, _L_TOP, _L_BOTTOM, _L_IRIS,
    _R_OUTER, _R_INNER, _R_TOP, _R_BOTTOM, _R_IRIS,
)

_STABLE_WIN  = 5
_STABLE_MAX  = 5e-6


@dataclass
class SampleResult:
    accepted:  bool
    iris_h:    float
    iris_v:    float
    variance:  float


class SampleCollector:
    """
    Evaluates a single landmark frame.
    Accepts if head is stable (nose tip variance below threshold).
    """

    def __init__(self):
        self._window: deque[tuple[float, float]] = deque(maxlen=_STABLE_WIN)

    def evaluate(self, landmarks: list) -> SampleResult:
        if not landmarks or len(landmarks) <= _R_IRIS:
            return SampleResult(accepted=False, iris_h=0.0, iris_v=0.0, variance=1.0)

        h = (
            _offset(landmarks[_L_IRIS].x, landmarks[_L_OUTER].x, landmarks[_L_INNER].x)
            + _offset(landmarks[_R_IRIS].x, landmarks[_R_OUTER].x, landmarks[_R_INNER].x)
        ) / 2.0
        v = (
            _offset(landmarks[_L_IRIS].y, landmarks[_L_TOP].y, landmarks[_L_BOTTOM].y)
            + _offset(landmarks[_R_IRIS].y, landmarks[_R_TOP].y, landmarks[_R_BOTTOM].y)
        ) / 2.0

        nose = landmarks[1]
        self._window.append((nose.x, nose.y))

        variance = 0.0
        if len(self._window) == _STABLE_WIN:
            xs = [p[0] for p in self._window]
            ys = [p[1] for p in self._window]
            mx = sum(xs) / _STABLE_WIN
            my = sum(ys) / _STABLE_WIN
            variance = sum((x - mx) ** 2 + (y - my) ** 2 for x, y in self._window) / _STABLE_WIN

        accepted = len(self._window) == _STABLE_WIN and variance < _STABLE_MAX

        return SampleResult(accepted=accepted, iris_h=h, iris_v=v, variance=variance)
