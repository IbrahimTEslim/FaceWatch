from datetime import datetime
from reporting.insights.base import Insight


class ScreenPresence(Insight):
    id    = "screen_presence"
    scope = "daily"

    def compute(self, conn, face_id: int, date: str, config) -> dict | None:
        row = conn.execute("""
            SELECT MIN(timestamp) AS first_seen,
                   MAX(timestamp) AS last_seen,
                   SUM(interval_sec) AS monitored_sec
            FROM stats
            WHERE face_id = ? AND date(timestamp) = ?
        """, (face_id, date)).fetchone()

        if not row or not row["monitored_sec"]:
            return None

        try:
            wall_sec = (
                datetime.fromisoformat(row["last_seen"][:19]) -
                datetime.fromisoformat(row["first_seen"][:19])
            ).total_seconds()
        except Exception:
            return None

        if wall_sec < 60:
            return None

        monitored_sec = row["monitored_sec"]
        present_pct   = round(min(100.0, monitored_sec / wall_sec * 100.0), 1)
        absent_pct    = round(100.0 - present_pct, 1)

        return {
            "id":           self.id,
            "present_pct":  present_pct,
            "absent_pct":   absent_pct,
            "monitored_sec": monitored_sec,
            "summary":      f"Present {present_pct}%, Away {absent_pct}%",
        }
