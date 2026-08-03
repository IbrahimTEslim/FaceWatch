def gaze_summary(conn, face_id: int, date: str) -> dict:
    """Total gaze off-screen time and % of monitored session for a day."""
    row = conn.execute("""
        SELECT SUM(MIN(gaze_off_sec, interval_sec))     AS total_off,
               SUM(interval_sec)                        AS total_monitored
        FROM stats
        WHERE face_id = ? AND date(timestamp) = ?
    """, (face_id, date)).fetchone()

    total_off       = round(row["total_off"] or 0.0, 1)
    total_monitored = row["total_monitored"] or 1
    pct_off         = round(total_off / total_monitored * 100, 1)

    rows = conn.execute("""
        SELECT strftime('%H', timestamp)                    AS hour,
               SUM(MIN(gaze_off_sec, interval_sec))         AS off_sec
        FROM stats
        WHERE face_id = ? AND date(timestamp) = ?
        GROUP BY hour ORDER BY hour
    """, (face_id, date)).fetchall()

    return {
        "total_off_sec":    total_off,
        "total_monitored":  total_monitored,
        "pct_off":          pct_off,
        "hours":            [r["hour"]           for r in rows],
        "off_per_hour":     [round(r["off_sec"] or 0.0, 1) for r in rows],
    }
