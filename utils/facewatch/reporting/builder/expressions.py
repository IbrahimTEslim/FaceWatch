def expressions_summary(conn, face_id: int, date: str) -> dict:
    """Expression breakdown % and blink rate per hour for a day."""
    row = conn.execute("""
        SELECT SUM(neutral_pct * interval_sec) / SUM(interval_sec) AS neutral,
               SUM(drowsy_pct  * interval_sec) / SUM(interval_sec) AS drowsy,
               SUM(smile_count)                                     AS smiles,
               SUM(angry_count)                                     AS angry,
               SUM(surprised_count)                                 AS surprised,
               SUM(blink_left)                                      AS blink_left,
               SUM(blink_right)                                     AS blink_right,
               SUM(interval_sec)                                    AS total_sec
        FROM stats
        WHERE face_id = ? AND date(timestamp) = ?
    """, (face_id, date)).fetchone()

    total_min = (row["total_sec"] or 1) / 60.0

    rows = conn.execute("""
        SELECT strftime('%H', timestamp) AS hour,
               SUM(blink_left)           AS bl,
               SUM(blink_right)          AS br
        FROM stats
        WHERE face_id = ? AND date(timestamp) = ?
        GROUP BY hour ORDER BY hour
    """, (face_id, date)).fetchall()

    return {
        "neutral_pct":   round(row["neutral"]   or 0.0, 1),
        "drowsy_pct":    round(row["drowsy"]    or 0.0, 1),
        "smile_count":   row["smiles"]    or 0,
        "angry_count":   row["angry"]     or 0,
        "surprised_count": row["surprised"] or 0,
        "blink_left_total":  row["blink_left"]  or 0,
        "blink_right_total": row["blink_right"] or 0,
        "blink_rate_per_min": round((row["blink_left"] or 0) / total_min, 1),
        "hours":         [r["hour"] for r in rows],
        "blink_left_hourly":  [r["bl"] or 0 for r in rows],
        "blink_right_hourly": [r["br"] or 0 for r in rows],
    }
