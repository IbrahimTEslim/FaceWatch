"""
Tests for engine CLI flags and DB config-key migrations.
Run from project root:
    python.exe tests\test_cli_and_migrations.py
"""
import os
import sqlite3
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "utils", "facewatch"))

from config_defaults import DEFAULTS
from storage.db import Database
from storage.db.connection import SCHEMA_VERSION


def _make_old_db(path: str, version: int, rows: list[tuple[str, str]]) -> None:
    Database(path).close()
    conn = sqlite3.connect(path)
    conn.executemany(
        "INSERT OR REPLACE INTO config (key, value, type, description, category) VALUES (?,?,?,?,?)",
        [(k, v, "str", "", "storage") for k, v in rows],
    )
    conn.execute(f"PRAGMA user_version = {version}")
    conn.commit()
    conn.close()


def test_migration_6_removes_db_path():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "v5.db")
        _make_old_db(path, 5, [("db_path", "facewatch.db"), ("stats_interval_sec", "5")])
        db = Database(path)
        try:
            assert db.get_config("db_path") is None
            assert db.get_config("stats_interval_sec") == "5"
            assert db._cx.conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        finally:
            db.close()
    print("  [OK] migration 6 drops db_path, keeps other config")


def test_fresh_db_reaches_schema_version():
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(os.path.join(tmp, "fresh.db"))
        try:
            assert db._cx.conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        finally:
            db.close()
    print(f"  [OK] fresh DB migrates to schema version {SCHEMA_VERSION}")


def test_removed_keys_not_in_defaults():
    keys = {row[0] for row in DEFAULTS}
    for removed in ("db_path", "screen_w_px", "screen_h_px"):
        assert removed not in keys, removed
    print("  [OK] removed keys are not seeded again")


def test_cli_db_flag():
    import engine
    with patch.object(sys, "argv", ["main.py"]):
        assert engine._parse_args().db == "facewatch.db"
    with patch.object(sys, "argv", ["main.py", "--db", "other.db"]):
        assert engine._parse_args().db == "other.db"
    print("  [OK] --db defaults to facewatch.db and accepts a path")


TESTS = [
    test_migration_6_removes_db_path,
    test_fresh_db_reaches_schema_version,
    test_removed_keys_not_in_defaults,
    test_cli_db_flag,
]


if __name__ == "__main__":
    print("\nCLI + Migration Tests\n")
    passed = 0
    for t in TESTS:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{passed}/{len(TESTS)} tests passed")
    sys.exit(0 if passed == len(TESTS) else 1)
