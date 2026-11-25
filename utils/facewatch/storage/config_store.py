from .db import Database
from config_defaults import DEFAULTS

_TYPE_MAP: dict[str, str] = {row[0]: row[2] for row in DEFAULTS}


class ConfigStore:
    def __init__(self, db: Database):
        self._db    = db
        self._cache: dict[str, str] = {}
        self._load_cache()

    def reload(self) -> None:
        """Re-read all values from the DB (e.g. after the settings dialog wrote them)."""
        self._load_cache()

    def _load_cache(self) -> None:
        for key, default, type_, *_ in DEFAULTS:
            raw = self._db.get_config(key)
            self._cache[key] = raw if raw is not None else str(default)

    def get(self, key: str) -> int | float | str | bool | list:
        raw = self._cache.get(key)
        if raw is None:
            raise KeyError(f"Config key not found: {key}")
        return self._cast(raw, _TYPE_MAP.get(key, "str"))

    def set(self, key: str, value) -> None:
        self._db.set_config(key, value)
        self._cache[key] = str(value)
        self._db.log_audit("config_changed", {"key": key, "value": str(value)})

    def get_all_by_category(self, category: str) -> list[dict]:
        return self._db.get_all_config_by_category(category)

    def reset_to_default(self, key: str) -> None:
        for row in DEFAULTS:
            if row[0] == key:
                self._db.set_config(key, str(row[1]))
                self._cache[key] = str(row[1])
                return
        raise KeyError(f"No default found for key: {key}")

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
