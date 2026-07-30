from reporting.insights.base import Insight

_WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


class BestWeekday(Insight):
    id    = "best_weekday"
    scope = "weekly"

    def compute(self, conn, face_id: int, date: str, config) -> dict | None:
        rows = conn.execute("""
            SELECT CAST(strftime('%w', timestamp) AS INTEGER)          AS dow,
                   SUM(focus_score * interval_sec) / SUM(interval_sec) AS avg_focus,
                   COUNT(DISTINCT date(timestamp))                      AS day_count
            FROM stats
            WHERE face_id = ?
            GROUP BY dow
            HAVING day_count >= 2
            ORDER BY dow
        """, (face_id,)).fetchall()

        if len(rows) < 2:
            return None

        # strftime %w: 0=Sunday … 6=Saturday — remap to Monday=0
        def _label(dow: int) -> str:
            return _WEEKDAYS[(dow - 1) % 7]

        scored = sorted(rows, key=lambda r: r["avg_focus"], reverse=True)
        best   = scored[0]
        worst  = scored[-1]

        return {
            "id":         self.id,
            "best_day":   _label(best["dow"]),
            "best_score": round(best["avg_focus"], 1),
            "worst_day":  _label(worst["dow"]),
            "worst_score": round(worst["avg_focus"], 1),
            "days":       [_label(r["dow"]) for r in rows],
            "scores":     [round(r["avg_focus"], 1) for r in rows],
            "summary":    f"Most productive: {_label(best['dow'])} ({round(best['avg_focus'], 1)}/100)",
        }
