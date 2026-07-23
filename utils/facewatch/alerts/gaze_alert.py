from .base import Alert, AlertType, AlertContext


class GazeAlert(Alert):
    enter_sec_key = "gaze_alert_sec"
    exit_sec_key  = "gaze_return_sec"
    alert_type    = AlertType.GAZE

    def is_condition_met(self, ctx: AlertContext) -> bool:
        return not ctx.gaze_on_screen

    def _fired_message(self) -> str:
        return "You've been looking away from the screen."

    def _cleared_message(self) -> str:
        return "Gaze returned to screen."
