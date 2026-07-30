from reporting.insights.base import Insight


class ViewingDistanceTrend(Insight):
    id    = "viewing_distance_trend"
    scope = "daily"

    def compute(self, conn, face_id: int, date: str, config) -> dict | None:
        rows = conn.execute("""
            SELECT strftime('%H', timestamp)                          AS hour,
                   SUM(distance_cm * interval_sec) / SUM(interval_sec) AS avg_dist
            FROM stats
            WHERE face_id = ? AND date(timestamp) = ?
              AND distance_cm > 0
            GROUP BY hour
            ORDER BY hour
        """, (face_id, date)).fetchall()

        if len(rows) < 2:
            return None

        hours     = [r["hour"] for r in rows]
        distances = [round(r["avg_dist"], 1) for r in rows]

        mid       = len(distances) // 2
        first_avg = round(sum(distances[:mid]) / mid, 1)
        second_avg = round(sum(distances[mid:]) / (len(distances) - mid), 1)
        drift_cm  = round(second_avg - first_avg, 1)

        if drift_cm < 0:
            trend = "closer"
        elif drift_cm > 0:
            trend = "further"
        else:
            trend = "stable"

        return {
            "id":         self.id,
            "hours":      hours,
            "distances":  distances,
            "first_avg":  first_avg,
            "second_avg": second_avg,
            "drift_cm":   drift_cm,
            "trend":      trend,
            "summary":    f"Drifting {trend} ({drift_cm:+.1f} cm)" if trend != "stable" else "Distance stable",
        }
