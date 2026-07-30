def apps_summary(conn, face_id: int, date: str) -> dict:
    """Time spent per app category and top 5 apps for a day."""
    cat_rows = conn.execute("""
        SELECT app_category,
               SUM(interval_sec) AS total_sec
        FROM stats
        WHERE face_id = ? AND date(timestamp) = ?
          AND app_category IS NOT NULL
        GROUP BY app_category
        ORDER BY total_sec DESC
    """, (face_id, date)).fetchall()

    app_rows = conn.execute("""
        SELECT active_app,
               app_category,
               SUM(interval_sec) AS total_sec
        FROM stats
        WHERE face_id = ? AND date(timestamp) = ?
          AND active_app IS NOT NULL AND active_app != 'unknown'
        GROUP BY active_app
        ORDER BY total_sec DESC
        LIMIT 5
    """, (face_id, date)).fetchall()

    return {
        "categories": [r["app_category"] for r in cat_rows],
        "cat_seconds": [r["total_sec"]   for r in cat_rows],
        "top_apps": [
            {
                "name":     r["active_app"],
                "category": r["app_category"],
                "seconds":  r["total_sec"],
                "minutes":  round(r["total_sec"] / 60, 1),
            }
            for r in app_rows
        ],
    }
