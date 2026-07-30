from datetime import datetime
from reporting.insights.base import Insight


class FirstFatigue(Insight):
    id    = "first_fatigue"
    scope = "daily"

    def compute(self, conn, face_id: int, date: str, config) -> dict | None:
        threshold     = config.get("expr_threshold_drowsy")
        min_sustained = config.get("drowsy_window_sec")

        rows = conn.execute("""
            SELECT timestamp, interval_sec, drowsy_pct
            FROM stats
            WHERE face_id = ? AND date(timestamp) = ?
            ORDER BY timestamp
        """, (face_id, date)).fetchall()

        if not rows:
            return None

        gap_threshold = (rows[0]["interval_sec"] or 5) * 2
        cur_sec       = 0.0
        cur_start     = None

        for prev, curr in zip(rows, rows[1:]):
            is_drowsy = (prev["drowsy_pct"] or 0.0) >= threshold * 100.0

            if is_drowsy:
                if cur_start is None:
                    cur_start = prev["timestamp"]
                cur_sec += prev["interval_sec"] or 0
            
            try:
                gap = (
                    datetime.fromisoformat(curr["timestamp"][:19]) -
                    datetime.fromisoformat(prev["timestamp"][:19])
                ).total_seconds()
            except Exception:
                gap = 0

            episode_broken = gap > gap_threshold or (curr["drowsy_pct"] or 0.0) < threshold * 100.0
            if episode_broken and cur_sec >= min_sustained:
                return {
                    "id":      self.id,
                    "time":    cur_start[:16].replace("T", " "),
                    "duration_sec": round(cur_sec),
                    "summary": f"First fatigue at {cur_start[11:16]}",
                }
            elif episode_broken:
                cur_sec   = 0.0
                cur_start = None

        # check last row
        if (rows[-1]["drowsy_pct"] or 0.0) >= threshold * 100.0:
            if cur_start is None:
                cur_start = rows[-1]["timestamp"]
            cur_sec += rows[-1]["interval_sec"] or 0

        if cur_sec >= min_sustained and cur_start:
            return {
                "id":           self.id,
                "time":         cur_start[:16].replace("T", " "),
                "duration_sec": round(cur_sec),
                "summary":      f"First fatigue at {cur_start[11:16]}",
            }

        return None
