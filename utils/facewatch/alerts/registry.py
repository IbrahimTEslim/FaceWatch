from .base import Alert
from .gaze_alert import GazeAlert
from .proximity_alert import ProximityAlert
from .eye_strain_alert import EyeStrainAlert
from .fatigue_alert import FatigueOnsetAlert
from .work_reminder_alert import WorkReminderAlert


def build_alerts() -> list[Alert]:
    return [
        GazeAlert(),
        ProximityAlert(),
        EyeStrainAlert(),
        FatigueOnsetAlert(),
        WorkReminderAlert(),
    ]
