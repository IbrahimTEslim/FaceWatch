from .focus       import focus_summary, focus_history
from .gaze        import gaze_summary
from .expressions import expressions_summary
from .distance    import distance_summary
from .apps        import apps_summary
from .alerts      import alerts_summary
from reporting.insights import build_insights


def build_report_data(conn, face_id: int, date: str) -> dict:
    """
    Aggregate all stats for face_id on date.
    Returns a single dict passed to templates and the JSON endpoint.
    """
    return {
        "face_id":       face_id,
        "date":          date,
        "focus":         focus_summary(conn, face_id, date),
        "focus_history": focus_history(conn, face_id),
        "gaze":          gaze_summary(conn, face_id, date),
        "expressions":   expressions_summary(conn, face_id, date),
        "distance":      distance_summary(conn, face_id, date),
        "apps":          apps_summary(conn, face_id, date),
        "alerts":        alerts_summary(conn, face_id, date),
        "insights":      build_insights(conn, face_id, date),
    }


def get_known_faces(conn) -> list[dict]:
    """Returns all known faces for the face selector."""
    rows = conn.execute(
        "SELECT id, display_name, last_seen FROM faces ORDER BY display_name"
    ).fetchall()
    return [{"id": r["id"], "name": r["display_name"], "last_seen": r["last_seen"]} for r in rows]


def get_available_dates(conn, face_id: int) -> list[str]:
    """Returns distinct dates that have stats for this face, newest first."""
    rows = conn.execute("""
        SELECT DISTINCT date(timestamp) AS day
        FROM stats WHERE face_id = ?
        ORDER BY day DESC
        LIMIT 90
    """, (face_id,)).fetchall()
    return [r["day"] for r in rows]
