from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

from storage.config_store import ConfigStore


class AlertType(Enum):
    GAZE      = "gaze"
    PROXIMITY = "proximity"


ALERT_LOGGABLE = frozenset({"fired", "cleared"})


@dataclass
class AlertContext:
    gaze_on_screen: bool
    dist_cm:        float
    config:         ConfigStore


@dataclass
class AlertEvent:
    status:  str   # 'fired' | 'cleared' | 'none'
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

    @abstractmethod
    def is_condition_met(self, ctx: AlertContext) -> bool:
        """Return True when the alert condition is currently active."""

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
                    return AlertEvent("fired", self._fired_message())
            else:
                self._enter_timer = 0.0
        else:
            if not condition:
                self._exit_timer += dt
                if self._exit_timer >= exit_sec:
                    self._active = False
                    self._enter_timer = 0.0
                    self._exit_timer  = 0.0
                    return AlertEvent("cleared", self._cleared_message())
            else:
                self._exit_timer = 0.0

        return AlertEvent("none", "")
