from .base import Alert, AlertType, AlertPriority, AlertContext


class WorkReminderAlert(Alert):
    enter_sec_key      = "work_reminder_alert_sec"
    exit_sec_key       = "work_reminder_clear_sec"
    alert_type         = AlertType.WORK_REMINDER
    priority           = AlertPriority.LOW
    notification_title = "FaceWatch — Break Reminder"

    def is_condition_met(self, ctx: AlertContext) -> bool:
        interval  = ctx.config.get("work_reminder_interval_sec")
        break_min = ctx.config.get("work_reminder_break_sec")
        return ctx.session_sec >= interval and ctx.last_break_sec >= (interval - break_min)

    def _fired_message(self) -> str:
        return "You've been working for 90 minutes. Consider taking a short break."

    def _cleared_message(self) -> str:
        return "Break detected. Good work!"
