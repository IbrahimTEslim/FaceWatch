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


def test_port_flag_is_used():
    """--port used to be parsed but ignored; both report server and 'open report' must use it."""
    import inspect
    import engine
    src = inspect.getsource(engine.run)
    assert 'report_port = args.port if args.port is not None else config.get("report_port")' in src
    assert "port=report_port" in src
    assert 'f"http://localhost:{report_port}"' in src
    assert 'config.get("report_port")' not in src.replace(
        'args.port if args.port is not None else config.get("report_port")', "")
    with patch.object(sys, "argv", ["main.py", "--port", "9000"]):
        assert engine._parse_args().port == 9000
    print("  [OK] --port is wired to the report server and the open-report key")


def test_config_reload_sees_settings_dialog_writes():
    """The settings dialog writes through its own sqlite connection."""
    from storage.config_store import ConfigStore
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "cfg.db")
        db = Database(path)
        try:
            for key, value, type_, desc, cat in DEFAULTS:
                db.seed_config(key, str(value), type_, desc, cat)
            config = ConfigStore(db)
            assert config.get("gaze_alert_sec") == 10

            other = sqlite3.connect(path, isolation_level=None)
            other.execute("UPDATE config SET value='25' WHERE key='gaze_alert_sec'")
            other.close()

            assert config.get("gaze_alert_sec") == 10  # cached until reload
            config.reload()
            assert config.get("gaze_alert_sec") == 25
        finally:
            db.close()
    print("  [OK] ConfigStore.reload() picks up settings-dialog writes")


def test_track_for_face_picks_the_calibrating_face():
    import engine
    from types import SimpleNamespace as NS
    idents = {4: NS(face_id=None), 7: NS(face_id=2), 9: NS(face_id=5)}
    assert engine._track_for_face(idents, 5) == 9   # not the first track
    assert engine._track_for_face(idents, 3) is None
    assert engine._track_for_face(idents, None) is None
    print("  [OK] gaze wizard is fed the track of the face being calibrated")


def test_gaze_correction_storage():
    import numpy as np
    from calibration.store import CalibrationStore
    from calibration.ridge_correction import RidgeCorrection
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(os.path.join(tmp, "corr.db"))
        try:
            store = CalibrationStore(db)
            fid = db.upsert_face("alice", "Alice", "known")
            assert store.load_gaze_correction(fid) is None

            model = RidgeCorrection(mean=np.zeros(4), scale=np.ones(4), coef=np.ones((4, 2)),
                                    intercept=np.array([1.0, -2.0]), alpha=10.0)
            store.save_gaze_correction(fid, model, {"accepted": True, "affine_err_px": 80.0})
            back = store.load_gaze_correction(fid)
            assert np.allclose(back.predict(np.ones(4)), [5.0, 2.0])
            _, report = db.load_gaze_correction(fid)
            assert '"affine_err_px": 80.0' in report

            db._cx.conn.execute("UPDATE face_gaze_correction SET model_blob=? WHERE face_id=?", (b"junk", fid))
            assert store.load_gaze_correction(fid) is None   # unreadable -> affine only

            store.save_gaze_correction(fid, model, {})
            db.delete_face(fid)                              # cascade
            assert db.load_gaze_correction(fid) == (None, None)
        finally:
            db.close()
    print("  [OK] gaze correction save/load, bad blob -> None, cascade on face delete")


def test_migration_7_from_v6():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "v6.db")
        Database(path).close()
        conn = sqlite3.connect(path)
        conn.execute("DROP TABLE face_gaze_correction")
        conn.execute("PRAGMA user_version = 6")
        conn.commit(); conn.close()
        db = Database(path)
        try:
            tables = {r[0] for r in db._cx.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            assert "face_gaze_correction" in tables and "face_gaze_model" in tables
        finally:
            db.close()
    print("  [OK] migration 7 adds face_gaze_correction to a v6 DB")


TESTS = [
    test_migration_6_removes_db_path,
    test_fresh_db_reaches_schema_version,
    test_removed_keys_not_in_defaults,
    test_cli_db_flag,
    test_port_flag_is_used,
    test_config_reload_sees_settings_dialog_writes,
    test_track_for_face_picks_the_calibrating_face,
    test_gaze_correction_storage,
    test_migration_7_from_v6,
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
