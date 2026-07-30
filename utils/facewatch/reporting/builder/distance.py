def distance_summary(conn, face_id: int, date: str) -> dict:
    """Average distance per hour and proximity alert count for a day."""
    row = conn.execute("""
        SELECT AVG(distance_cm)       AS avg_dist,
               MIN(distance_cm)       AS min_dist,
               SUM(proximity_alerts)  AS total_alerts
        FROM stats
        WHERE face_id = ? AND date(timestamp) = ?
    """, (face_id, date)).fetchone()

    rows = conn.execute("""
        SELECT strftime('%H', timestamp) AS hour,
               AVG(distance_cm)          AS avg_dist
        FROM stats
        WHERE face_id = ? AND date(timestamp) = ?
        GROUP BY hour ORDER BY hour
    """, (face_id, date)).fetchall()

    return {
        "avg_cm":          round(row["avg_dist"]    or 0.0, 1),
        "min_cm":          round(row["min_dist"]    or 0.0, 1),
        "proximity_alerts": row["total_alerts"] or 0,
        "hours":           [r["hour"]                        for r in rows],
        "dist_per_hour":   [round(r["avg_dist"] or 0.0, 1)  for r in rows],
    }
