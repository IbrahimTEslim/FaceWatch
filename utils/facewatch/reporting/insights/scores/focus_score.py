from reporting.insights.base import Insight


class FocusScore(Insight):
    id    = "focus_score"
    scope = "score"

    def compute(self, conn, face_id: int, date: str, config) -> dict | None:
        row = conn.execute("""
            SELECT SUM(focus_score * interval_sec) / SUM(interval_sec) AS score,
                   SUM(interval_sec)                                    AS total_sec
            FROM stats
            WHERE face_id = ? AND date(timestamp) = ?
        """, (face_id, date)).fetchone()

        if not row or not row["total_sec"]:
            return None

        score = round(row["score"] or 0.0, 1)
        return {
            "id":        self.id,
            "score":     score,
            "label":     "Focus Score",
            "out_of":    100,
            "color":     "green" if score >= 70 else "orange" if score >= 40 else "red",
            "summary":   f"{score}/100",
        }
