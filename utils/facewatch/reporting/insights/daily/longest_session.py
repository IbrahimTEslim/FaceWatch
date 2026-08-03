from reporting.insights.base import Insight


class LongestSession(Insight):
    id    = "longest_session"
    scope = "daily"

    def compute(self, conn, face_id: int, date: str, config) -> dict | None:
        rows = conn.execute("""
            SELECT timestamp, interval_sec
            FROM stats
            WHERE face_id = ? AND date(timestamp) = ?
            ORDER BY timestamp
        """, (face_id, date)).fetchall()

        if not rows:
            return None

        gap_threshold = (rows[0]["interval_sec"] or 5) * 2

        best_sec  = 0
        best_start = rows[0]["timestamp"]
        cur_sec   = rows[0]["interval_sec"] or 0
        cur_start = rows[0]["timestamp"]

        from datetime import datetime
        fmt = "%Y-%m-%dT%H:%M:%S"

        for prev, curr in zip(rows, rows[1:]):
            try:
                t_prev = datetime.fromisoformat(prev["timestamp"][:19])
                t_curr = datetime.fromisoformat(curr["timestamp"][:19])
                gap    = (t_curr - t_prev).total_seconds()
            except Exception:
                gap = 0

            if gap <= gap_threshold:
                cur_sec += curr["interval_sec"] or 0
            else:
                if cur_sec > best_sec:
                    best_sec   = cur_sec
                    best_start = cur_start
                cur_sec   = curr["interval_sec"] or 0
                cur_start = curr["timestamp"]

        if cur_sec > best_sec:
            best_sec   = cur_sec
            best_start = cur_start

        if best_sec < 60:
            return None

        minutes = best_sec // 60
        return {
            "id":      self.id,
            "minutes": minutes,
            "start":   best_start[:16].replace("T", " "),
            "summary": f"{minutes} min uninterrupted focus",
        }
