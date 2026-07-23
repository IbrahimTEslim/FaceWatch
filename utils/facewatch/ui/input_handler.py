from enum import Enum, auto
from storage.config_store import ConfigStore


class Action(Enum):
    NONE         = auto()
    QUIT         = auto()
    REGISTER     = auto()
    CALIBRATE    = auto()
    TOGGLE_DEBUG = auto()
    FORCE_STATS  = auto()


_KEY_MAP = {
    "key_quit":        Action.QUIT,
    "key_register":    Action.REGISTER,
    "key_calibrate":   Action.CALIBRATE,
    "key_debug":       Action.TOGGLE_DEBUG,
    "key_force_stats": Action.FORCE_STATS,
}


class InputHandler:
    def __init__(self, config: ConfigStore):
        self._bindings: dict[int, Action] = {
            ord(config.get(cfg_key)): action
            for cfg_key, action in _KEY_MAP.items()
        }

    def handle(self, key_code: int) -> Action:
        return self._bindings.get(key_code, Action.NONE)
