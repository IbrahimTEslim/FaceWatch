from datetime import datetime
from reporting.insights.base import Insight


def _fmt(sec: float) -> str:
    sec = int(sec)
    if sec < 60:
        return f"{sec}s"
    if sec < 3600:
        return f"{sec // 60}m {sec % 60:02d}s"
    return f"{sec // 3600}h {(sec % 3600) // 60:02d}m"


class DistractionDuration(Insight):
    id    = "distraction_duration"
    scope = "daily"

    def compute(self, conn, face_id: int, date: str, config) -> dict | None:
        rows = conn.execute("""
            SELECT timestamp, interval_sec, gaze_off_sec
            FROM stats
            WHERE face_id = ? AND date(timestamp) = ?
            ORDER BY timestamp
        """, (face_id, date)).fetchall()

        if not rows:
            return None

        gap_threshold = (rows[0]["interval_sec"] or 5) * 2
        episodes      = []
        cur_sec       = 0.0

        for prev, curr in zip(rows, rows[1:]):
            if prev["gaze_off_sec"] > 0:
                cur_sec += prev["gaze_off_sec"]

            try:
                gap = (
                    datetime.fromisoformat(curr["timestamp"][:19]) -
                    datetime.fromisoformat(prev["timestamp"][:19])
                ).total_seconds()
            except Exception:
                gap = 0

            episode_broken = gap > gap_threshold or curr["gaze_off_sec"] == 0
            if episode_broken and cur_sec > 0:
                episodes.append(cur_sec)
                cur_sec = 0.0

        # handle last row
        if rows[-1]["gaze_off_sec"] > 0:
            cur_sec += rows[-1]["gaze_off_sec"]
        if cur_sec > 0:
            episodes.append(cur_sec)

        if not episodes:
            return None

        count   = len(episodes)
        avg_sec = round(sum(episodes) / count, 1)
        longest = round(max(episodes), 1)

        return {
            "id":          self.id,
            "count":       count,
            "avg_sec":     avg_sec,
            "longest_sec": longest,
            "avg_fmt":     _fmt(avg_sec),
            "longest_fmt": _fmt(longest),
            "summary":     f"{count} distractions, avg {_fmt(avg_sec)}, longest {_fmt(longest)}",
        }
