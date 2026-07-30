from reporting.insights.base import Insight


class BestFocusHour(Insight):
    id    = "best_focus_hour"
    scope = "daily"

    def compute(self, conn, face_id: int, date: str, config) -> dict | None:
        rows = conn.execute("""
            SELECT strftime('%H', timestamp)                            AS hour,
                   SUM(focus_score * interval_sec) / SUM(interval_sec) AS avg_focus,
                   SUM(interval_sec)                                    AS total_sec
            FROM stats
            WHERE face_id = ? AND date(timestamp) = ?
            GROUP BY hour
            HAVING total_sec >= 60
            ORDER BY avg_focus DESC
            LIMIT 1
        """, (face_id, date)).fetchone()

        if not rows:
            return None

        score = round(rows["avg_focus"], 1)
        hour  = int(rows["hour"])
        label = f"{hour:02d}:00–{hour+1:02d}:00"

        return {
            "id":      self.id,
            "hour":    hour,
            "label":   label,
            "score":   score,
            "summary": f"Best focus at {label} ({score}/100)",
        }
