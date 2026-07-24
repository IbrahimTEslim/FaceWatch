from .base import Alert, AlertType, AlertPriority, AlertContext


class ProximityAlert(Alert):
    enter_sec_key      = "proximity_alert_sec"
    exit_sec_key       = "proximity_clear_sec"
    alert_type         = AlertType.PROXIMITY
    priority           = AlertPriority.HIGH
    notification_title = "FaceWatch — Proximity Alert"

    def is_condition_met(self, ctx: AlertContext) -> bool:
        return ctx.dist_cm > 0 and ctx.dist_cm < ctx.config.get("proximity_alert_cm")

    def _fired_message(self) -> str:
        return "Too close to camera. Please move back."

    def _cleared_message(self) -> str:
        return "Distance OK."
