from storage.db import Database

_DEFAULTS = {
    "gaze_center_h":  0.50,
    "gaze_center_v":  0.50,
    "focal_length_px": 600.0,
}


class CalibrationStore:
    def __init__(self, db: Database):
        self._db = db

    def get(self, key: str) -> float:
        value = self._db.get_calibration(key)
        if value is None:
            if key not in _DEFAULTS:
                raise KeyError(f"Unknown calibration key: {key}")
            return _DEFAULTS[key]
        return value

    def set(self, key: str, value: float) -> None:
        if key not in _DEFAULTS:
            raise KeyError(f"Unknown calibration key: {key}")
        self._db.upsert_calibration(key, value)

    def is_calibrated(self, key: str) -> bool:
        return self._db.get_calibration(key) is not None
