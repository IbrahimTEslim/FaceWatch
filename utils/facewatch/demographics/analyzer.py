import threading
from datetime import datetime, timezone

import numpy as np
from deepface import DeepFace

from storage.db import Database
from storage.config_store import ConfigStore
from demographics.face_width import estimate_face_width_cm, DEFAULT_FACE_WIDTH_CM


class DemographicsAnalyzer:
    def __init__(self, db: Database, config: ConfigStore):
        self._db      = db
        self._config  = config
        self._running: set[int] = set()
        self._done:    set[int] = set()   # face_ids with fresh demographics, skip DB read
        self._lock    = threading.Lock()

    def maybe_run(self, face_id: int, face_crop: np.ndarray) -> None:
        """Run analysis if no record exists or weekly refresh is due. No-op if already running or done."""
        with self._lock:
            if face_id in self._running or face_id in self._done:
                return
        row = self._db.get_demographics(face_id)
        if row is None:
            self._run_async(face_id, face_crop)
            return
        refresh_days: int = self._config.get("demographics_refresh_days")
        last = datetime.fromisoformat(row["last_updated"])
        age_sec = (datetime.now() - last).total_seconds()
        if age_sec > refresh_days * 86400:
            self._run_async(face_id, face_crop)

    def force_run(self, face_id: int, face_crop: np.ndarray) -> None:
        """Force re-run regardless of last_updated."""
        self._run_async(face_id, face_crop)

    def get_face_width(self, face_id: int) -> float:
        """Return stored face_width_cm, or global default if not yet analyzed."""
        row = self._db.get_demographics(face_id)
        if row and row["face_width_cm"]:
            return float(row["face_width_cm"])
        return DEFAULT_FACE_WIDTH_CM

    def get_demographics(self, face_id: int) -> dict | None:
        """Return demographics dict or None if not yet analyzed."""
        return self._db.get_demographics(face_id)

    # ------------------------------------------------------------------

    def _run_async(self, face_id: int, face_crop: np.ndarray) -> None:
        with self._lock:
            self._running.add(face_id)
        t = threading.Thread(target=self._analyze, args=(face_id, face_crop), daemon=True)
        t.start()

    def _analyze(self, face_id: int, face_crop: np.ndarray) -> None:
        try:
            result = DeepFace.analyze(
                img_path=face_crop,
                actions=["age", "gender", "race"],
                detector_backend="skip",
                enforce_detection=False,
                silent=True,
            )
            data = result[0]
            age    = int(data["age"])
            gender = str(data["dominant_gender"])
            race   = str(data["dominant_race"])
            conf   = float(data["gender"][gender])
            face_width_cm = estimate_face_width_cm(age, gender)
            self._db.upsert_demographics(face_id, age, gender, race, face_width_cm, conf)
        except Exception:
            pass
        finally:
            with self._lock:
                self._running.discard(face_id)
                self._done.add(face_id)
