from .base import Alert, AlertType, AlertPriority, AlertContext


class EyeStrainAlert(Alert):
    enter_sec_key      = "eye_strain_alert_sec"
    exit_sec_key       = "eye_strain_clear_sec"
    alert_type         = AlertType.EYE_STRAIN
    priority           = AlertPriority.MEDIUM
    notification_title = "FaceWatch — Eye Strain"

    def is_condition_met(self, ctx: AlertContext) -> bool:
        return ctx.dist_cm > 0 and ctx.dist_cm < ctx.config.get("proximity_alert_cm")

    def _fired_message(self) -> str:
        return "You've been too close to the screen continuously. Move back to reduce eye strain."

    def _cleared_message(self) -> str:
        return "Viewing distance back to normal."
