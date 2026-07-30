from reporting.insights.base import Insight


class ErgonomicScore(Insight):
    id    = "ergonomic_score"
    scope = "score"

    def compute(self, conn, face_id: int, date: str, config) -> dict | None:
        safe_min = config.get("focus_posture_min_cm")
        safe_max = config.get("focus_posture_max_cm")

        row = conn.execute("""
            SELECT SUM(
                       CASE
                           WHEN distance_cm BETWEEN ? AND ? THEN interval_sec
                           ELSE 0
                       END
                   )                  AS safe_sec,
                   SUM(interval_sec)  AS total_sec,
                   SUM(proximity_alerts) AS total_alerts
            FROM stats
            WHERE face_id = ? AND date(timestamp) = ?
              AND distance_cm > 0
        """, (safe_min, safe_max, face_id, date)).fetchone()

        if not row or not row["total_sec"]:
            return None

        safe_ratio    = (row["safe_sec"] or 0.0) / row["total_sec"]
        alert_penalty = min(1.0, (row["total_alerts"] or 0) / 20.0) * 0.2
        score         = round(max(0.0, safe_ratio * 100.0 - alert_penalty * 100.0), 1)

        return {
            "id":      self.id,
            "score":   score,
            "label":   "Ergonomic Score",
            "out_of":  100,
            "color":   "green" if score >= 75 else "orange" if score >= 50 else "red",
            "summary": f"{score}/100",
        }
