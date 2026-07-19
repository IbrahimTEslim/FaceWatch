from .connection import Connection


class ConfigQueries:
    def __init__(self, cx: Connection):
        self._cx = cx

    def seed_config(self, key: str, value, type_: str, description: str, category: str) -> None:
        with self._cx.lock:
            self._cx.conn.execute(
                "INSERT OR IGNORE INTO config (key, value, type, description, category) VALUES (?,?,?,?,?)",
                (key, str(value), type_, description, category),
            )
            self._cx.conn.commit()

    def get_config(self, key: str) -> str | None:
        row = self._cx.conn.execute("SELECT value FROM config WHERE key=?", (key,)).fetchone()
        return row["value"] if row else None

    def get_config_type(self, key: str) -> str | None:
        row = self._cx.conn.execute("SELECT type FROM config WHERE key=?", (key,)).fetchone()
        return row["type"] if row else None

    def set_config(self, key: str, value) -> None:
        with self._cx.lock:
            self._cx.conn.execute("UPDATE config SET value=? WHERE key=?", (str(value), key))
            self._cx.conn.commit()

    def get_all_config_by_category(self, category: str) -> list[dict]:
        rows = self._cx.conn.execute(
            "SELECT key, value, type, description FROM config WHERE category=?", (category,)
        ).fetchall()
        return [dict(r) for r in rows]
