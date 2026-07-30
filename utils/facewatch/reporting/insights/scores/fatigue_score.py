from reporting.insights.base import Insight


class FatigueScore(Insight):
    id    = "fatigue_score"
    scope = "score"

    def compute(self, conn, face_id: int, date: str) -> dict | None:
        row = conn.execute("""
            SELECT SUM(drowsy_pct * interval_sec) / SUM(interval_sec) AS avg_drowsy,
                   SUM(interval_sec)                                   AS total_sec
            FROM stats
            WHERE face_id = ? AND date(timestamp) = ?
        """, (face_id, date)).fetchone()

        if not row or not row["total_sec"]:
            return None

        avg_drowsy = row["avg_drowsy"] or 0.0
        score      = round(max(0.0, 100.0 - avg_drowsy), 1)
        return {
            "id":      self.id,
            "score":   score,
            "label":   "Fatigue Score",
            "out_of":  100,
            "color":   "green" if score >= 80 else "orange" if score >= 50 else "red",
            "summary": f"{score}/100",
        }
