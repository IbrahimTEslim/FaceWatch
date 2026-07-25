from storage.db import Database

_DEFAULTS = {
    "gaze_center_h":  0.50,
    "gaze_center_v":  0.50,
    "focal_length_px": 600.0,
}

_GAZE_DEFAULT_H = 0.50
_GAZE_DEFAULT_V = 0.50


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

    def get_gaze_center(self, face_id: int) -> tuple[float, float]:
        row = self._db.get_face_gaze(face_id)
        if row is None:
            return (_GAZE_DEFAULT_H, _GAZE_DEFAULT_V)
        return (row["center_h"], row["center_v"])

    def save_gaze_center(self, face_id: int, h: float, v: float) -> None:
        self._db.insert_face_gaze(face_id, h, v)

    def is_gaze_calibrated(self, face_id: int) -> str | None:
        """Returns calibrated_at string if calibrated, None if using default."""
        row = self._db.get_face_gaze(face_id)
        return row["calibrated_at"] if row else None
