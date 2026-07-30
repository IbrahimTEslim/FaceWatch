def focus_summary(conn, face_id: int, date: str) -> dict:
    """Hourly focus scores for a given day + daily average."""
    rows = conn.execute("""
        SELECT strftime('%H', timestamp)                              AS hour,
               SUM(focus_score * interval_sec) / SUM(interval_sec)   AS avg_focus
        FROM stats
        WHERE face_id = ? AND date(timestamp) = ?
        GROUP BY hour
        ORDER BY hour
    """, (face_id, date)).fetchall()

    hours  = [r["hour"] for r in rows]
    scores = [round(r["avg_focus"], 1) for r in rows]
    avg    = round(sum(s * 1 for s in scores) / len(scores), 1) if scores else 0.0

    return {"hours": hours, "scores": scores, "daily_avg": avg}


def focus_history(conn, face_id: int, days: int = 30) -> dict:
    """Daily average focus score for the last N days."""
    rows = conn.execute("""
        SELECT date(timestamp)                                        AS day,
               SUM(focus_score * interval_sec) / SUM(interval_sec)   AS avg_focus
        FROM stats
        WHERE face_id = ?
          AND date(timestamp) >= date('now', ? || ' days')
        GROUP BY day
        ORDER BY day
    """, (face_id, f"-{days}")).fetchall()

    days_list = [r["day"]       for r in rows]
    scores    = [round(r["avg_focus"], 1) for r in rows]

    best  = max(zip(scores, days_list), default=(0, None))
    worst = min(zip(scores, days_list), default=(0, None))

    return {
        "days":        days_list,
        "scores":      scores,
        "best_day":    {"score": best[0],  "date": best[1]},
        "worst_day":   {"score": worst[0], "date": worst[1]},
    }
