from .connection import Connection


class StatsQueries:
    def __init__(self, cx: Connection):
        self._cx = cx

    def write_stats(self, face_id: int, row: dict) -> None:
        with self._cx.lock:
            self._cx.conn.execute(
                """INSERT INTO stats (face_id, timestamp, interval_sec, blink_left, blink_right,
                   smile_count, angry_count, surprised_count, neutral_pct, drowsy_pct,
                   distance_cm, gaze_off_sec, proximity_alerts, focus_score,
                   active_app, active_window_title, app_category)
                   VALUES (:face_id,:timestamp,:interval_sec,:blink_left,:blink_right,
                   :smile_count,:angry_count,:surprised_count,:neutral_pct,:drowsy_pct,
                   :distance_cm,:gaze_off_sec,:proximity_alerts,:focus_score,
                   :active_app,:active_window_title,:app_category)""",
                {"face_id": face_id, **row},
            )
            self._cx.conn.commit()

    def query_stats(self, face_id: int, date: str) -> list[dict]:
        rows = self._cx.conn.execute(
            "SELECT * FROM stats WHERE face_id=? AND timestamp LIKE ? ORDER BY timestamp",
            (face_id, f"{date}%"),
        ).fetchall()
        return [dict(r) for r in rows]
