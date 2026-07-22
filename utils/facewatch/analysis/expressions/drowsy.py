import time
from collections import deque

from .base import Expression
from storage.config_store import ConfigStore

_EYE_CLOSED_THRESHOLD = 0.8


class Drowsy(Expression):
    name = "drowsy"
    color = (128, 0, 255)
    threshold_key = "expr_threshold_drowsy"
    cooldown_sec = 0.0
    count_events = False

    def __init__(self):
        super().__init__()
        self._window: deque[tuple[float, bool]] = deque()

    def compute_activation(self, blendshapes: dict[str, float], landmarks: list) -> float:
        # Not used directly — update() is overridden
        return 0.0

    def update(self, blendshapes: dict[str, float], landmarks: list, config: ConfigStore) -> None:
        window_sec: int = config.get("drowsy_window_sec")
        threshold: float = config.get(self.threshold_key)
        now = time.monotonic()

        avg_blink = (blendshapes.get("eyeBlinkLeft", 0.0) + blendshapes.get("eyeBlinkRight", 0.0)) / 2.0
        is_closed = avg_blink > _EYE_CLOSED_THRESHOLD
        self._window.append((now, is_closed))

        cutoff = now - window_sec
        while self._window and self._window[0][0] < cutoff:
            self._window.popleft()

        total = len(self._window)
        closed = sum(1 for _, c in self._window if c)
        perclos = closed / total if total > 0 else 0.0

        self._current_value = perclos
        was_active = self._active
        self._active = perclos >= threshold

        if self._active and not was_active:
            self._activation_start = now

        self._interval_total_frames += 1
        if self._active:
            self._interval_active_frames += 1
