import json

from .connection import Connection, now_utc


class AuditQueries:
    def __init__(self, cx: Connection):
        self._cx = cx

    def log_audit(self, event_type: str, details: dict | None = None) -> None:
        with self._cx.lock:
            self._cx.conn.execute(
                "INSERT INTO audit_log (timestamp, event_type, details) VALUES (?,?,?)",
                (now_utc(), event_type, json.dumps(details) if details else None),
            )
            self._cx.conn.commit()

    def get_audit_log(self, date: str) -> list[dict]:
        rows = self._cx.conn.execute(
            "SELECT * FROM audit_log WHERE timestamp LIKE ? ORDER BY timestamp",
            (f"{date}%",),
        ).fetchall()
        return [dict(r) for r in rows]
