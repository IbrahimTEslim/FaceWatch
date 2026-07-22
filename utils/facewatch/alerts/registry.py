from .base import Alert
from .gaze_alert import GazeAlert
from .proximity_alert import ProximityAlert


def build_alerts() -> list[Alert]:
    return [
        GazeAlert(),
        ProximityAlert(),
    ]
