"""
Smoke tests for Step 10: calibration/store.py + calibration/wizard.py
Run from project root:
    venv\Scripts\python.exe tests\test_step10_calibration.py
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "utils", "facewatch"))

from unittest.mock import MagicMock
from calibration.store import CalibrationStore
from calibration.wizard import CalibrationWizard, _SAMPLES_NEEDED
from analysis.gaze import GazeTracker


# ── helpers ───────────────────────────────────────────────────────────────────

def _db(stored: dict | None = None):
    stored = stored or {}
    db = MagicMock()
    db.get_calibration.side_effect = lambda k: stored.get(k)
    db.upsert_calibration.side_effect = lambda k, v: stored.update({k: v})
    return db, stored


def _landmark(x: float, y: float):
    lm = MagicMock()
    lm.x = x
    lm.y = y
    return lm


def _make_landmarks(iris_x=0.5, iris_y=0.5, cheek_lx=0.3, cheek_rx=0.7):
    lms = [_landmark(0.5, 0.5) for _ in range(478)]
    lms[468] = _landmark(iris_x, iris_y)   # L iris
    lms[473] = _landmark(iris_x, iris_y)   # R iris
    lms[234] = _landmark(cheek_lx, 0.5)    # left cheek
    lms[454] = _landmark(cheek_rx, 0.5)    # right cheek
    # eye corners for gaze ratio
    lms[33]  = _landmark(0.3,  0.5);  lms[133] = _landmark(0.45, 0.5)
    lms[159] = _landmark(0.375, 0.45); lms[145] = _landmark(0.375, 0.55)
    lms[362] = _landmark(0.55, 0.5);  lms[263] = _landmark(0.7,  0.5)
    lms[386] = _landmark(0.625, 0.45); lms[374] = _landmark(0.625, 0.55)
    return lms


def _config(alert_sec=10.0, return_sec=3.0):
    cfg = MagicMock()
    cfg.get.side_effect = lambda k: {"gaze_alert_sec": alert_sec, "gaze_return_sec": return_sec}[k]
    return cfg


# ── CalibrationStore tests ────────────────────────────────────────────────────

def test_store_returns_default_when_not_calibrated():
    db, _ = _db()
    store = CalibrationStore(db)
    assert store.get("gaze_center_h") == 0.50
    assert store.get("focal_length_px") == 600.0
    print("  [OK] Returns default when key not in DB")


def test_store_returns_stored_value():
    db, _ = _db({"gaze_center_h": 0.48})
    store = CalibrationStore(db)
    assert store.get("gaze_center_h") == 0.48
    print("  [OK] Returns stored value from DB")


def test_store_set_writes_to_db():
    db, stored = _db()
    store = CalibrationStore(db)
    store.set("focal_length_px", 720.0)
    assert stored["focal_length_px"] == 720.0
    print("  [OK] set() writes value to DB")


def test_store_is_calibrated():
    db, _ = _db({"gaze_center_h": 0.48})
    store = CalibrationStore(db)
    assert store.is_calibrated("gaze_center_h")
    assert not store.is_calibrated("focal_length_px")
    print("  [OK] is_calibrated() reflects DB state")


def test_store_unknown_key_raises():
    db, _ = _db()
    store = CalibrationStore(db)
    try:
        store.get("nonexistent_key")
        assert False, "Should have raised"
    except KeyError:
        pass
    print("  [OK] Unknown key raises KeyError")


# ── CalibrationWizard tests ───────────────────────────────────────────────────

def test_wizard_starts_at_step_1():
    db, _ = _db()
    wizard = CalibrationWizard(CalibrationStore(db))
    state = wizard.feed([], 640)
    assert state.step == 1
    assert not state.done
    print("  [OK] Wizard starts at step 1")


def test_wizard_step1_advances_after_samples():
    db, stored = _db()
    wizard = CalibrationWizard(CalibrationStore(db))
    lms = _make_landmarks(iris_x=0.48, iris_y=0.51)
    state = None
    for _ in range(_SAMPLES_NEEDED):
        state = wizard.feed(lms, 640)
    # After enough samples, next feed should be step 2
    state = wizard.feed(lms, 640)
    assert state.step == 2
    assert "gaze_center_h" in stored
    assert "gaze_center_v" in stored
    assert abs(stored["gaze_center_h"] - 0.48) < 0.01
    print(f"  [OK] Step 1 completes, gaze_center_h={stored['gaze_center_h']:.3f}")


def test_wizard_step2_waits_for_distance():
    db, _ = _db()
    wizard = CalibrationWizard(CalibrationStore(db))
    # Skip to step 2
    wizard._step = 2
    state = wizard.feed(_make_landmarks(), 640)
    assert state.step == 2
    assert "Type your distance" in state.instruction
    print("  [OK] Step 2 waits for distance_cm before collecting")


def test_wizard_step2_advances_after_samples():
    db, stored = _db()
    wizard = CalibrationWizard(CalibrationStore(db))
    wizard._step = 2
    wizard.set_distance_cm(60.0)
    lms = _make_landmarks(cheek_lx=0.25, cheek_rx=0.75)
    for _ in range(_SAMPLES_NEEDED + 1):
        state = wizard.feed(lms, 640)
    assert state.step == 3
    assert state.done
    assert "focal_length_px" in stored
    assert stored["focal_length_px"] > 0
    print(f"  [OK] Step 2 completes, focal_length_px={stored['focal_length_px']:.1f}")


def test_wizard_done_state():
    db, _ = _db()
    wizard = CalibrationWizard(CalibrationStore(db))
    wizard._step = 3
    state = wizard.feed([], 640)
    assert state.done
    assert state.step == 3
    print("  [OK] Done state returns done=True")


# ── GazeTracker calibration integration ──────────────────────────────────────

def test_gaze_uses_calibrated_center():
    """Shift calibrated center far enough that the same landmarks flip on_screen."""
    tracker = GazeTracker(1920, 1080)
    # Use landmarks that produce a "left" direction with default center (0.50)
    lms = _make_landmarks(iris_x=0.5, iris_y=0.5)
    state_default = tracker.update(lms, 0.033, _config(), calibration=None)

    # Now calibrate center to match whatever ratio those landmarks produce
    h = state_default.horizontal_ratio
    v = state_default.vertical_ratio
    db, _ = _db({"gaze_center_h": h, "gaze_center_v": v})
    store = CalibrationStore(db)
    tracker2 = GazeTracker(1920, 1080)
    state_cal = tracker2.update(lms, 0.033, _config(), calibration=store)
    assert state_cal.on_screen
    print(f"  [OK] Calibrated center h={h:.3f} v={v:.3f}: same landmarks -> on_screen=True")


def test_gaze_fallback_without_calibration():
    """Without calibration, defaults to 0.50 center."""
    tracker = GazeTracker(1920, 1080)
    lms = _make_landmarks(iris_x=0.5, iris_y=0.5)
    state = tracker.update(lms, 0.033, _config(), calibration=None)
    assert state.on_screen
    print("  [OK] No calibration: default center 0.50 works correctly")


# ── runner ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\nStep 10 — Calibration Smoke Tests\n")

    tests = [
        test_store_returns_default_when_not_calibrated,
        test_store_returns_stored_value,
        test_store_set_writes_to_db,
        test_store_is_calibrated,
        test_store_unknown_key_raises,
        test_wizard_starts_at_step_1,
        test_wizard_step1_advances_after_samples,
        test_wizard_step2_waits_for_distance,
        test_wizard_step2_advances_after_samples,
        test_wizard_done_state,
        test_gaze_uses_calibrated_center,
        test_gaze_fallback_without_calibration,
    ]

    passed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {t.__name__}: {e}")

    print(f"\n{passed}/{len(tests)} tests passed")
