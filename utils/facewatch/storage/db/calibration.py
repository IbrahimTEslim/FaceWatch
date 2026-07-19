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
