"""
Smoke test for Step 1: database + config_store + config_defaults
Run from project root:
    """
import sys
import os
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "utils", "facewatch"))

from storage.db import Database
from storage.config_store import ConfigStore
from config_defaults import DEFAULTS


def test_schema_created(db):
    tables = {r[0] for r in db._cx.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    expected = {"faces", "embeddings", "demographics", "stats", "config", "calibration", "audit_log"}
    assert expected.issubset(tables), f"Missing tables: {expected - tables}"
    print("  [OK] All tables created")


def test_config_seed(db):
    for row in DEFAULTS:
        db.seed_config(row[0], row[1], row[2], row[3], row[4])

    # Seeding twice should not overwrite (INSERT OR IGNORE)
    db.seed_config("stats_interval_sec", 999, "int", "should not overwrite", "storage")
    val = db.get_config("stats_interval_sec")
    assert val == "5", f"Expected '5', got '{val}'"
    print("  [OK] Config seeded, INSERT OR IGNORE works")


def test_config_store_get(db):
    config = ConfigStore(db)
    assert config.get("stats_interval_sec") == 5
    assert config.get("recognition_threshold") == 0.60
    assert config.get("report_times") == ["18:00", "21:00"]
    assert config.get("db_path") == "facewatch.db"
    print("  [OK] ConfigStore.get() type casting works")


def test_config_store_set(db):
    config = ConfigStore(db)
    config.set("stats_interval_sec", 10)
    assert config.get("stats_interval_sec") == 10
    print("  [OK] ConfigStore.set() works")


def test_config_reset_to_default(db):
    config = ConfigStore(db)
    config.set("stats_interval_sec", 99)
    config.reset_to_default("stats_interval_sec")
    assert config.get("stats_interval_sec") == 5
    print("  [OK] ConfigStore.reset_to_default() works")


def test_faces(db):
    face_id = db.upsert_face("Ibrahim", "known")
    assert isinstance(face_id, int) and face_id > 0

    # Upsert again — should return same id
    same_id = db.upsert_face("Ibrahim", "known")
    assert same_id == face_id

    face = db.get_face_by_name("Ibrahim")
    assert face["name"] == "Ibrahim"
    assert face["status"] == "known"

    db.update_face_last_seen(face_id)
    db.rename_face(face_id, "Ibrahim_renamed")
    assert db.get_face_by_name("Ibrahim_renamed") is not None

    print("  [OK] Face upsert, get, rename, last_seen work")


def test_embeddings(db):
    face_id = db.upsert_face("EmbedTest", "known")
    arr = np.random.rand(128).astype(np.float32)
    blob = db.array_to_blob(arr)
    db.add_embedding(face_id, blob)

    assert db.count_embeddings(face_id) == 1
    blobs = db.get_embeddings(face_id)
    loaded = db.blob_to_array(blobs[0])
    assert np.allclose(arr, loaded)

    print("  [OK] Embeddings add, count, get, numpy round-trip work")


def test_demographics(db):
    face_id = db.upsert_face("DemoTest", "known")
    db.upsert_demographics(face_id, 28, "Man", "middle eastern", 14.0, 92.5)
    demo = db.get_demographics(face_id)
    assert demo["age_estimate"] == 28
    assert demo["face_width_cm"] == 14.0

    # Upsert again — should update
    db.upsert_demographics(face_id, 29, "Man", "middle eastern", 14.0, 93.0)
    assert db.get_demographics(face_id)["age_estimate"] == 29
    print("  [OK] Demographics upsert and get work")


def test_stats(db):
    face_id = db.upsert_face("StatsTest", "known")
    row = {
        "timestamp": "2024-01-15T14:32:07Z",
        "interval_sec": 5,
        "blink_left": 2, "blink_right": 2,
        "smile_count": 1, "angry_count": 0, "surprised_count": 0,
        "neutral_pct": 80.0, "drowsy_pct": 0.0,
        "distance_cm": 58.3, "gaze_off_sec": 0.5,
        "proximity_alerts": 0, "focus_score": 73.2,
        "active_app": "code.exe", "active_window_title": "FaceWatch", "app_category": "editor",
    }
    db.write_stats(face_id, row)
    results = db.query_stats(face_id, "2024-01-15")
    assert len(results) == 1
    assert results[0]["focus_score"] == 73.2
    print("  [OK] Stats write and query work")


def test_calibration(db):
    db.upsert_calibration("focal_length_px", 847.3)
    assert db.get_calibration("focal_length_px") == 847.3
    db.upsert_calibration("focal_length_px", 900.0)
    assert db.get_calibration("focal_length_px") == 900.0
    assert db.get_calibration("nonexistent") is None
    print("  [OK] Calibration upsert and get work")


def test_audit_log(db):
    db.log_audit("session_start", {"camera": 0})
    db.log_audit("face_registered", {"name": "Ibrahim"})
    logs = db.get_audit_log("2024")  # won't match today's date
    today_logs = db.get_audit_log(
        __import__("datetime").datetime.now(__import__("datetime").timezone.utc).strftime("%Y-%m-%d")
    )
    assert len(today_logs) >= 2
    print("  [OK] Audit log write and query work")


def test_delete_cascade(db):
    face_id = db.upsert_face("DeleteTest", "known")
    db.add_embedding(face_id, db.array_to_blob(np.zeros(128)))
    db.upsert_demographics(face_id, 25, "Man", "asian", 14.0, 88.0)
    db.delete_face(face_id)
    assert db.get_face_by_name("DeleteTest") is None
    assert db.count_embeddings(face_id) == 0
    assert db.get_demographics(face_id) is None
    print("  [OK] Delete cascade works (embeddings + demographics removed)")


if __name__ == "__main__":
    db_path = "test_step1.db"
    if os.path.exists(db_path):
        os.remove(db_path)

    db = Database(db_path)
    print("\nStep 1 — Storage Smoke Test\n")

    tests = [
        test_schema_created,
        test_config_seed,
        test_config_store_get,
        test_config_store_set,
        test_config_reset_to_default,
        test_faces,
        test_embeddings,
        test_demographics,
        test_stats,
        test_calibration,
        test_audit_log,
        test_delete_cascade,
    ]

    passed = 0
    for t in tests:
        try:
            t(db)
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {t.__name__}: {e}")

    db.close()
    os.remove(db_path)
    print(f"\n{passed}/{len(tests)} tests passed")
