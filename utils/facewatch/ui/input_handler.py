from enum import Enum, auto
from storage.config_store import ConfigStore


class Action(Enum):
    NONE             = auto()
    QUIT             = auto()
    REGISTER         = auto()
    CALIBRATE        = auto()
    TOGGLE_DEBUG     = auto()
    FORCE_STATS      = auto()
    FORCE_REIDENTIFY = auto()
    OPEN_SETTINGS    = auto()
    OPEN_REPORT      = auto()
    TOGGLE_HELP      = auto()


_KEY_MAP = {
    "key_quit":             Action.QUIT,
    "key_register":         Action.REGISTER,
    "key_calibrate":        Action.CALIBRATE,
    "key_debug":            Action.TOGGLE_DEBUG,
    "key_force_stats":      Action.FORCE_STATS,
    "key_force_reidentify": Action.FORCE_REIDENTIFY,
    "key_settings":         Action.OPEN_SETTINGS,
    "key_report":           Action.OPEN_REPORT,
    "key_help":             Action.TOGGLE_HELP,
}


class InputHandler:
    def __init__(self, config: ConfigStore):
        self._bindings: dict[int, Action] = {
            ord(config.get(cfg_key)): action
            for cfg_key, action in _KEY_MAP.items()
        }

    def handle(self, key_code: int) -> Action:
        return self._bindings.get(key_code, Action.NONE)
