from reporting.insights.base import Insight


class ConsistencyScore(Insight):
    id    = "consistency_score"
    scope = "weekly"

    def compute(self, conn, face_id: int, date: str, config) -> dict | None:
        rows = conn.execute("""
            SELECT date(timestamp)                                        AS day,
                   SUM(focus_score * interval_sec) / SUM(interval_sec)   AS avg_focus
            FROM stats
            WHERE face_id = ?
              AND date(timestamp) BETWEEN date(?, '-6 days') AND date(?)
            GROUP BY day
            ORDER BY day
        """, (face_id, date, date)).fetchall()

        if len(rows) < 3:
            return None

        scores = [r["avg_focus"] for r in rows]
        days   = [r["day"] for r in rows]
        mean   = sum(scores) / len(scores)
        stddev = round((sum((s - mean) ** 2 for s in scores) / len(scores)) ** 0.5, 1)

        # consistency 0-100: 0 stddev = 100, stddev >= 30 = 0
        consistency = round(max(0.0, 100.0 - (stddev / 30.0) * 100.0), 1)

        outliers = [
            {"day": d, "score": round(s, 1)}
            for d, s in zip(days, scores)
            if abs(s - mean) > stddev * 1.5
        ]

        return {
            "id":           self.id,
            "consistency":  consistency,
            "stddev":       stddev,
            "days":         days,
            "scores":       [round(s, 1) for s in scores],
            "outliers":     outliers,
            "summary":      f"Consistency {consistency}/100 over {len(rows)} days",
        }
