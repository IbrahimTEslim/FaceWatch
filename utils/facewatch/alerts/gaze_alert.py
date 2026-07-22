from .base import Alert


class GazeAlert(Alert):
    enter_sec_key = "gaze_alert_sec"
    exit_sec_key  = "gaze_return_sec"

    def _fired_message(self) -> str:
        return "You've been looking away from the screen."

    def _cleared_message(self) -> str:
        return "Gaze returned to screen."
