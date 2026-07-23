from .connection import Connection, now_utc


class FaceQueries:
    def __init__(self, cx: Connection):
        self._cx = cx

    def upsert_face(self, name: str, display_name: str, status: str) -> int:
        with self._cx.lock:
            self._cx.conn.execute(
                "INSERT OR IGNORE INTO faces (name, display_name, status, created_at) VALUES (?,?,?,?)",
                (name, display_name, status, now_utc()),
            )
            self._cx.conn.commit()
        row = self._cx.conn.execute("SELECT id FROM faces WHERE name=?", (name,)).fetchone()
        return row["id"]

    def get_face_by_name(self, name: str) -> dict | None:
        row = self._cx.conn.execute("SELECT * FROM faces WHERE name=?", (name,)).fetchone()
        return dict(row) if row else None

    def get_face_by_id(self, face_id: int) -> dict | None:
        row = self._cx.conn.execute("SELECT * FROM faces WHERE id=?", (face_id,)).fetchone()
        return dict(row) if row else None

    def get_all_known_faces(self) -> list[dict]:
        rows = self._cx.conn.execute("SELECT * FROM faces WHERE status='known'").fetchall()
        return [dict(r) for r in rows]

    def get_all_unknown_faces(self) -> list[dict]:
        rows = self._cx.conn.execute(
            "SELECT * FROM faces WHERE status='unknown' AND name LIKE 'unknown_%'"
        ).fetchall()
        return [dict(r) for r in rows]

    def update_face_last_seen(self, face_id: int) -> None:
        with self._cx.lock:
            self._cx.conn.execute("UPDATE faces SET last_seen=? WHERE id=?", (now_utc(), face_id))
            self._cx.conn.commit()

    def update_face_status(self, face_id: int, status: str) -> None:
        with self._cx.lock:
            self._cx.conn.execute("UPDATE faces SET status=? WHERE id=?", (status, face_id))
            self._cx.conn.commit()

    def rename_face(self, face_id: int, name: str, display_name: str) -> None:
        with self._cx.lock:
            self._cx.conn.execute(
                "UPDATE faces SET name=?, display_name=? WHERE id=?",
                (name, display_name, face_id),
            )
            self._cx.conn.commit()

    def delete_face(self, face_id: int) -> None:
        with self._cx.lock:
            self._cx.conn.execute("DELETE FROM faces WHERE id=?", (face_id,))
            self._cx.conn.commit()

    def add_embedding(self, face_id: int, blob: bytes) -> None:
        with self._cx.lock:
            self._cx.conn.execute(
                "INSERT INTO embeddings (face_id, data, created_at) VALUES (?,?,?)",
                (face_id, blob, now_utc()),
            )
            self._cx.conn.commit()

    def get_embeddings(self, face_id: int) -> list[bytes]:
        rows = self._cx.conn.execute(
            "SELECT data FROM embeddings WHERE face_id=?", (face_id,)
        ).fetchall()
        return [r["data"] for r in rows]

    def get_embeddings_with_ids(self, face_id: int) -> list[tuple[int, bytes]]:
        rows = self._cx.conn.execute(
            "SELECT id, data FROM embeddings WHERE face_id=?", (face_id,)
        ).fetchall()
        return [(r["id"], r["data"]) for r in rows]

    def delete_embedding_by_id(self, embedding_id: int) -> None:
        with self._cx.lock:
            self._cx.conn.execute("DELETE FROM embeddings WHERE id=?", (embedding_id,))
            self._cx.conn.commit()

    def count_embeddings(self, face_id: int) -> int:
        row = self._cx.conn.execute(
            "SELECT COUNT(*) as c FROM embeddings WHERE face_id=?", (face_id,)
        ).fetchone()
        return row["c"]

    def delete_oldest_embedding(self, face_id: int) -> None:
        with self._cx.lock:
            self._cx.conn.execute(
                "DELETE FROM embeddings WHERE id=("
                "SELECT id FROM embeddings WHERE face_id=? ORDER BY created_at ASC LIMIT 1)",
                (face_id,),
            )
            self._cx.conn.commit()
