import json

from storage.db import Database
from calibration.ridge_correction import RidgeCorrection

_DEFAULTS = {
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

    def save_gaze_model(self, face_id: int, model) -> None:
        self._db.save_gaze_model(face_id, model)

    def load_gaze_model(self, face_id: int):
        model, calibrated_at = self._db.load_gaze_model(face_id)
        return model

    def save_gaze_correction(self, face_id: int, model: RidgeCorrection, report: dict) -> None:
        self._db.save_gaze_correction(face_id, model.to_bytes(), json.dumps(report))

    def load_gaze_correction(self, face_id: int) -> RidgeCorrection | None:
        """None if absent or unreadable (a bad blob must never break gaze tracking)."""
        blob, _ = self._db.load_gaze_correction(face_id)
        if blob is None:
            return None
        try:
            return RidgeCorrection.from_bytes(blob)
        except Exception:
            return None

    def delete_gaze_correction(self, face_id: int) -> None:
        self._db.delete_gaze_correction(face_id)

    def is_gaze_calibrated(self, face_id: int) -> str | None:
        _, calibrated_at = self._db.load_gaze_model(face_id)
        return calibrated_at
