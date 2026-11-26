import pickle

from .connection import Connection, now_utc


class CalibrationQueries:
    def __init__(self, cx: Connection):
        self._cx = cx

    def upsert_calibration(self, key: str, value: float) -> None:
        with self._cx.lock:
            self._cx.conn.execute(
                """INSERT INTO calibration (key, value, calibrated_at) VALUES (?,?,?)
                   ON CONFLICT(key) DO UPDATE SET
                       value=excluded.value,
                       calibrated_at=excluded.calibrated_at""",
                (key, value, now_utc()),
            )
            self._cx.conn.commit()

    def get_calibration(self, key: str) -> float | None:
        row = self._cx.conn.execute(
            "SELECT value FROM calibration WHERE key=?", (key,)
        ).fetchone()
        return row["value"] if row else None

    def save_gaze_model(self, face_id: int, model) -> None:
        blob = pickle.dumps(model)
        with self._cx.lock:
            self._cx.conn.execute(
                """INSERT INTO face_gaze_model (face_id, model_blob, calibrated_at)
                   VALUES (?, ?, ?)
                   ON CONFLICT(face_id) DO UPDATE SET
                       model_blob=excluded.model_blob,
                       calibrated_at=excluded.calibrated_at""",
                (face_id, blob, now_utc()),
            )
            self._cx.conn.commit()

    def load_gaze_model(self, face_id: int):
        row = self._cx.conn.execute(
            "SELECT model_blob, calibrated_at FROM face_gaze_model WHERE face_id=?",
            (face_id,),
        ).fetchone()
        if row is None:
            return None, None
        return pickle.loads(row["model_blob"]), row["calibrated_at"]

    def save_gaze_correction(self, face_id: int, blob: bytes, report_json: str) -> None:
        with self._cx.lock:
            self._cx.conn.execute(
                """INSERT INTO face_gaze_correction (face_id, model_blob, report, calibrated_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(face_id) DO UPDATE SET
                       model_blob=excluded.model_blob,
                       report=excluded.report,
                       calibrated_at=excluded.calibrated_at""",
                (face_id, blob, report_json, now_utc()),
            )
            self._cx.conn.commit()

    def load_gaze_correction(self, face_id: int) -> tuple[bytes | None, str | None]:
        row = self._cx.conn.execute(
            "SELECT model_blob, report FROM face_gaze_correction WHERE face_id=?",
            (face_id,),
        ).fetchone()
        if row is None:
            return None, None
        return bytes(row["model_blob"]), row["report"]

    def delete_gaze_correction(self, face_id: int) -> None:
        with self._cx.lock:
            self._cx.conn.execute(
                "DELETE FROM face_gaze_correction WHERE face_id=?", (face_id,)
            )
            self._cx.conn.commit()

    def delete_gaze_model(self, face_id: int) -> None:
        with self._cx.lock:
            self._cx.conn.execute(
                "DELETE FROM face_gaze_model WHERE face_id=?", (face_id,)
            )
            self._cx.conn.commit()
