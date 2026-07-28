import json


def alerts_summary(conn, face_id: int, date: str) -> dict:
    """Recent alert events and counts by type for a day."""
    rows = conn.execute("""
        SELECT timestamp, event_type, details
        FROM audit_log
        WHERE date(timestamp) = ?
          AND event_type LIKE 'alert_%'
        ORDER BY timestamp DESC
        LIMIT 50
    """, (date,)).fetchall()

    events = []
    counts: dict[str, int] = {}
    for r in rows:
        details = {}
        try:
            details = json.loads(r["details"]) if r["details"] else {}
        except Exception:
            pass
        event_type = r["event_type"].replace("alert_", "")
        counts[event_type] = counts.get(event_type, 0) + 1
        events.append({
            "timestamp":  r["timestamp"][:19].replace("T", " "),
            "type":       event_type,
            "message":    details.get("message", ""),
        })

    return {
        "events":  events,
        "counts":  counts,
        "total":   sum(counts.values()),
    }
