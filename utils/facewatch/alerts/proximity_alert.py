from .base import Alert


class ProximityAlert(Alert):
    enter_sec_key = "proximity_alert_sec"
    exit_sec_key  = "proximity_clear_sec"

    def _fired_message(self) -> str:
        return "Too close to camera. Please move back."

    def _cleared_message(self) -> str:
        return "Distance OK."
