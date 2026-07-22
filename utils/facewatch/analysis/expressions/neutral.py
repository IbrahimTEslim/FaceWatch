from .base import Expression
from storage.config_store import ConfigStore


class Neutral(Expression):
    name = "neutral"
    color = (200, 200, 200)
    threshold_key = "expr_threshold_neutral"
    cooldown_sec = 0.0
    count_events = False

    def __init__(self, others: list[Expression]):
        super().__init__()
        self._others = others

    def compute_activation(self, blendshapes: dict[str, float], landmarks: list) -> float:
        # Returns 1.0 if active, 0.0 if not — threshold check done in update()
        # But neutral logic is: active when all others are inactive
        # We return 1.0 here and let update() compare against threshold_key=0.5 (always passes)
        # Real logic overridden in update()
        return 1.0

    def update(self, blendshapes: dict[str, float], landmarks: list, config: ConfigStore) -> None:
        self._current_value = 0.0
        was_active = self._active
        self._active = all(not e.active for e in self._others)
        self._current_value = 1.0 if self._active else 0.0

        if self._active and not was_active:
            import time
            self._activation_start = time.monotonic()

        self._interval_total_frames += 1
        if self._active:
            self._interval_active_frames += 1
