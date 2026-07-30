import time
from collections import deque

from .base import Alert, AlertType, AlertPriority, AlertContext


class FatigueOnsetAlert(Alert):
    enter_sec_key      = "fatigue_onset_alert_sec"
    exit_sec_key       = "fatigue_onset_clear_sec"
    alert_type         = AlertType.FATIGUE
    priority           = AlertPriority.MEDIUM
    notification_title = "FaceWatch — Fatigue Onset"

    def __init__(self):
        super().__init__()
        self._window: deque[tuple[float, float]] = deque()  # (timestamp, perclos)

    def _perclos_rising(self, ctx: AlertContext) -> bool:
        window_sec = ctx.config.get("fatigue_onset_window_sec")
        min_rise   = ctx.config.get("fatigue_onset_min_rise")
        now        = time.monotonic()

        self._window.append((now, ctx.perclos))
        cutoff = now - window_sec
        while self._window and self._window[0][0] < cutoff:
            self._window.popleft()

        if len(self._window) < 2:
            return False

        rise = self._window[-1][1] - self._window[0][1]
        return rise >= min_rise

    def is_condition_met(self, ctx: AlertContext) -> bool:
        min_session = ctx.config.get("fatigue_onset_min_session")
        return ctx.session_sec >= min_session and self._perclos_rising(ctx)

    def _fired_message(self) -> str:
        return "Signs of fatigue increasing. Consider a short break."

    def _cleared_message(self) -> str:
        return "Fatigue signs reduced."
