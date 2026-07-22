import time
from abc import ABC, abstractmethod

from storage.config_store import ConfigStore


class Expression(ABC):
    name: str
    color: tuple
    threshold_key: str
    cooldown_sec: float
    count_events: bool

    def __init__(self):
        self._active: bool = False
        self._count: int = 0
        self._current_value: float = 0.0
        self._last_trigger: float = 0.0
        self._activation_start: float = 0.0
        self._interval_count: int = 0
        self._interval_active_frames: int = 0
        self._interval_total_frames: int = 0

    @abstractmethod
    def compute_activation(self, blendshapes: dict[str, float], landmarks: list) -> float:
        """Return 0.0–1.0 activation value."""

    def update(self, blendshapes: dict[str, float], landmarks: list, config: ConfigStore) -> None:
        threshold: float = config.get(self.threshold_key)
        value = self.compute_activation(blendshapes, landmarks)
        self._current_value = value
        now = time.monotonic()
        was_active = self._active
        self._active = value >= threshold

        if self._active and not was_active:
            self._activation_start = now
            if self.count_events and (now - self._last_trigger) >= self.cooldown_sec:
                self._count += 1
                self._interval_count += 1
                self._last_trigger = now

        self._interval_total_frames += 1
        if self._active:
            self._interval_active_frames += 1

    @property
    def active(self) -> bool:
        return self._active

    @property
    def value(self) -> float:
        return self._current_value

    @property
    def count(self) -> int:
        return self._count

    @property
    def duration(self) -> float:
        if not self._active:
            return 0.0
        return time.monotonic() - self._activation_start

    def reset(self) -> None:
        self._active = False
        self._count = 0
        self._current_value = 0.0
        self._last_trigger = 0.0
        self._activation_start = 0.0
        self._interval_count = 0
        self._interval_active_frames = 0
        self._interval_total_frames = 0

    def get_interval_stats(self) -> dict:
        stats = {
            "count": self._interval_count,
            "active_frames": self._interval_active_frames,
            "total_frames": self._interval_total_frames,
        }
        self._interval_count = 0
        self._interval_active_frames = 0
        self._interval_total_frames = 0
        return stats
