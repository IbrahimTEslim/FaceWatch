from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

from storage.config_store import ConfigStore
from alerts.notifier import notify


class AlertType(Enum):
    GAZE         = "gaze"
    PROXIMITY    = "proximity"
    EYE_STRAIN   = "eye_strain"
    FATIGUE      = "fatigue"
    WORK_REMINDER = "work_reminder"


class AlertPriority(Enum):
    LOW    = "low"
    MEDIUM = "medium"
    HIGH   = "high"


class AlertStatus(Enum):
    FIRED   = "fired"
    CLEARED = "cleared"
    NONE    = "none"


ALERT_LOGGABLE = frozenset({AlertStatus.FIRED, AlertStatus.CLEARED})


@dataclass
class AlertContext:
    gaze_on_screen: bool
    dist_cm:        float
    config:         ConfigStore
    perclos:        float = 0.0
    blink_rate_pm:  float = 0.0
    session_sec:    float = 0.0
    last_break_sec: float = 0.0


@dataclass
class AlertEvent:
    status:  AlertStatus
    message: str


class Alert(ABC):
    def __init__(self):
        self._active:       bool  = False
        self._enter_timer:  float = 0.0
        self._exit_timer:   float = 0.0

    @property
    @abstractmethod
    def enter_sec_key(self) -> str: ...

    @property
    @abstractmethod
    def exit_sec_key(self) -> str: ...

    @property
    @abstractmethod
    def alert_type(self) -> AlertType: ...

    @property
    @abstractmethod
    def priority(self) -> AlertPriority: ...

    @abstractmethod
    def is_condition_met(self, ctx: AlertContext) -> bool:
        """Return True when the alert condition is currently active."""

    @property
    @abstractmethod
    def notification_title(self) -> str: ...

    @abstractmethod
    def _fired_message(self) -> str: ...

    @abstractmethod
    def _cleared_message(self) -> str: ...

    @property
    def active(self) -> bool:
        return self._active

    def update(self, condition: bool, dt: float, config: ConfigStore) -> AlertEvent:
        enter_sec: float = config.get(self.enter_sec_key)
        exit_sec:  float = config.get(self.exit_sec_key)

        if not self._active:
            if condition:
                self._enter_timer += dt
                if self._enter_timer >= enter_sec:
                    self._active = True
                    self._enter_timer = 0.0
                    self._exit_timer  = 0.0
                    notify(self.notification_title, self._fired_message(), config)
                    return AlertEvent(AlertStatus.FIRED, self._fired_message())
            else:
                self._enter_timer = 0.0
        else:
            if not condition:
                self._exit_timer += dt
                if self._exit_timer >= exit_sec:
                    self._active = False
                    self._enter_timer = 0.0
                    self._exit_timer  = 0.0
                    return AlertEvent(AlertStatus.CLEARED, self._cleared_message())
            else:
                self._exit_timer = 0.0

        return AlertEvent(AlertStatus.NONE, "")
