from .db import Database
from config_defaults import DEFAULTS


class ConfigStore:
    def __init__(self, db: Database):
        self._db = db

    def get(self, key: str) -> int | float | str | bool | list:
        raw = self._db.get_config(key)
        if raw is None:
            raise KeyError(f"Config key not found: {key}")
        type_ = self._get_type(key)
        return self._cast(raw, type_)

    def set(self, key: str, value) -> None:
        self._db.set_config(key, value)
        self._db.log_audit("config_changed", {"key": key, "value": str(value)})

    def get_all_by_category(self, category: str) -> list[dict]:
        return self._db.get_all_config_by_category(category)

    def reset_to_default(self, key: str) -> None:
        for row in DEFAULTS:
            if row[0] == key:
                self._db.set_config(key, str(row[1]))
                return
        raise KeyError(f"No default found for key: {key}")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get_type(self, key: str) -> str:
        return self._db.get_config_type(key) or "str"

    @staticmethod
    def _cast(value: str, type_: str) -> int | float | str | bool | list:
        if type_ == "int":
            return int(value)
        if type_ == "float":
            return float(value)
        if type_ == "bool":
            return value.lower() in ("1", "true", "yes")
        if type_ == "list":
            return [v.strip() for v in value.split(",") if v.strip()]
        return value
