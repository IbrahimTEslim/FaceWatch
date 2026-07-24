import io
import sqlite3
import threading

import numpy as np

SCHEMA_VERSION = 2


def now_utc() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Connection:
    def __init__(self, db_path: str):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._create_schema()
        self._run_migrations()

    def _create_schema(self) -> None:
        stmts = [
            """CREATE TABLE IF NOT EXISTS faces (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                name         TEXT UNIQUE NOT NULL,
                display_name TEXT NOT NULL,
                status       TEXT NOT NULL DEFAULT 'unknown',
                created_at   TEXT NOT NULL,
                last_seen    TEXT
            )""",
            """CREATE TABLE IF NOT EXISTS embeddings (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                face_id    INTEGER NOT NULL REFERENCES faces(id) ON DELETE CASCADE,
                data       BLOB NOT NULL,
                created_at TEXT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS demographics (
                face_id       INTEGER PRIMARY KEY REFERENCES faces(id) ON DELETE CASCADE,
                age_estimate  INTEGER,
                gender        TEXT,
                race          TEXT,
                face_width_cm REAL,
                confidence    REAL,
                last_updated  TEXT
            )""",
            """CREATE TABLE IF NOT EXISTS stats (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                face_id             INTEGER NOT NULL REFERENCES faces(id) ON DELETE CASCADE,
                timestamp           TEXT NOT NULL,
                interval_sec        INTEGER NOT NULL,
                blink_left          INTEGER DEFAULT 0,
                blink_right         INTEGER DEFAULT 0,
                smile_count         INTEGER DEFAULT 0,
                angry_count         INTEGER DEFAULT 0,
                surprised_count     INTEGER DEFAULT 0,
                neutral_pct         REAL DEFAULT 0.0,
                drowsy_pct          REAL DEFAULT 0.0,
                distance_cm         REAL,
                gaze_off_sec        REAL DEFAULT 0.0,
                proximity_alerts    INTEGER DEFAULT 0,
                focus_score         REAL DEFAULT 0.0,
                active_app          TEXT,
                active_window_title TEXT,
                app_category        TEXT
            )""",
            """CREATE TABLE IF NOT EXISTS config (
                key         TEXT PRIMARY KEY,
                value       TEXT NOT NULL,
                type        TEXT NOT NULL,
                description TEXT,
                category    TEXT
            )""",
            """CREATE TABLE IF NOT EXISTS calibration (
                key           TEXT PRIMARY KEY,
                value         REAL NOT NULL,
                calibrated_at TEXT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS audit_log (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp  TEXT NOT NULL,
                event_type TEXT NOT NULL,
                details    TEXT
            )""",
            "CREATE INDEX IF NOT EXISTS idx_stats_face_id   ON stats(face_id)",
            "CREATE INDEX IF NOT EXISTS idx_stats_timestamp ON stats(timestamp)",
            "CREATE INDEX IF NOT EXISTS idx_stats_app       ON stats(active_app)",
            "CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp)",
        ]
        with self.lock:
            for stmt in stmts:
                self.conn.execute(stmt)
            self.conn.commit()

    def _run_migrations(self) -> None:
        version = self.conn.execute("PRAGMA user_version").fetchone()[0]
        if version < 2:
            with self.lock:
                cols = [r[1] for r in self.conn.execute("PRAGMA table_info(faces)").fetchall()]
                if "display_name" not in cols:
                    self.conn.execute(
                        "ALTER TABLE faces ADD COLUMN display_name TEXT NOT NULL DEFAULT ''"
                    )
                    self.conn.execute(
                        "UPDATE faces SET display_name=name WHERE display_name=''"
                    )
                self.conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
                self.conn.commit()

    @staticmethod
    def array_to_blob(arr: np.ndarray) -> bytes:
        buf = io.BytesIO()
        np.save(buf, arr)
        return buf.getvalue()

    @staticmethod
    def blob_to_array(blob: bytes) -> np.ndarray:
        return np.load(io.BytesIO(blob))
