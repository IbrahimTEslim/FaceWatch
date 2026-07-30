from reporting.insights.base import Insight


class MeaningfulBreaks(Insight):
    id    = "meaningful_breaks"
    scope = "daily"

    def compute(self, conn, face_id: int, date: str, config) -> dict | None:
        break_min_sec = config.get("work_reminder_break_sec")

        rows = conn.execute("""
            SELECT timestamp
            FROM stats
            WHERE face_id = ? AND date(timestamp) = ?
            ORDER BY timestamp
        """, (face_id, date)).fetchall()

        if len(rows) < 2:
            return None

        from datetime import datetime

        breaks = []
        for prev, curr in zip(rows, rows[1:]):
            try:
                t_prev = datetime.fromisoformat(prev["timestamp"][:19])
                t_curr = datetime.fromisoformat(curr["timestamp"][:19])
                gap    = (t_curr - t_prev).total_seconds()
            except Exception:
                continue
            if gap >= break_min_sec:
                breaks.append(gap)

        if not breaks:
            return None

        avg_min = round(sum(breaks) / len(breaks) / 60.0, 1)
        return {
            "id":      self.id,
            "count":   len(breaks),
            "avg_min": avg_min,
            "summary": f"{len(breaks)} break{'s' if len(breaks) != 1 else ''}, avg {avg_min} min",
        }
