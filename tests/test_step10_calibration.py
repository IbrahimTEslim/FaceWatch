r"""
Tests for Step 10: calibration/store.py + FocalWizard / GazeWizard basics.
(GazeWizard's full run and the affine fit are covered in test_gaze_calibration_fit.py.)
Run from project root:
    venv\Scripts\python.exe tests\test_step10_calibration.py
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "utils", "facewatch"))

from unittest.mock import MagicMock

import numpy as np

from calibration.store import CalibrationStore
from calibration.wizard import FocalWizard, GazeWizard, _FOCAL_SAMPLES


# ── helpers ───────────────────────────────────────────────────────────────────

def _db(stored: dict | None = None, gaze_models: dict | None = None):
    stored = {} if stored is None else stored
    gaze_models = {} if gaze_models is None else gaze_models
    db = MagicMock()
    db.get_calibration.side_effect = lambda k: stored.get(k)
    db.upsert_calibration.side_effect = lambda k, v: stored.update({k: v})
    db.save_gaze_model.side_effect = lambda fid, m: gaze_models.update({fid: (m, "2026-01-01T00:00:00")})
    db.load_gaze_model.side_effect = lambda fid: gaze_models.get(fid, (None, None))
    return db, stored


def _landmark(x: float, y: float):
    lm = MagicMock()
    lm.x = x
    lm.y = y
    return lm


def _face(cheek_lx=0.25, cheek_rx=0.75, nose=(0.5, 0.5)):
    lms = [_landmark(0.5, 0.5) for _ in range(478)]
    lms[1]   = _landmark(*nose)
    lms[234] = _landmark(cheek_lx, 0.5)
    lms[454] = _landmark(cheek_rx, 0.5)
    return lms


# ── CalibrationStore ─────────────────────────────────────────────────────────

def test_store_returns_default_when_not_calibrated():
    store = CalibrationStore(_db()[0])
    assert store.get("focal_length_px") == 600.0
    assert not store.is_calibrated("focal_length_px")
    print("  [OK] focal_length_px defaults to 600 when not calibrated")


def test_store_set_and_get():
    db, stored = _db()
    store = CalibrationStore(db)
    store.set("focal_length_px", 720.0)
    assert stored["focal_length_px"] == 720.0
    assert store.get("focal_length_px") == 720.0 and store.is_calibrated("focal_length_px")
    print("  [OK] set() writes and get() reads focal_length_px")


def test_store_unknown_key_raises():
    store = CalibrationStore(_db()[0])
    for call in (lambda: store.get("nope"), lambda: store.set("nope", 1.0)):
        try:
            call()
            assert False, "should have raised"
        except KeyError:
            pass
    print("  [OK] unknown keys raise KeyError")


def test_store_gaze_model_roundtrip():
    store = CalibrationStore(_db()[0])
    assert store.load_gaze_model(3) is None and store.is_gaze_calibrated(3) is None
    M = np.array([[1.0, 0.0, 5.0], [0.0, 1.0, 7.0]])
    store.save_gaze_model(3, M)
    assert np.array_equal(store.load_gaze_model(3), M)
    assert store.is_gaze_calibrated(3)
    print("  [OK] gaze model save/load/is_gaze_calibrated")


# ── FocalWizard ──────────────────────────────────────────────────────────────

def test_focal_waits_for_distance():
    wiz = FocalWizard(CalibrationStore(_db()[0]), face_width_cm=14.0)
    state = wiz.feed(_face(), 640)
    assert not state.done and "distance" in state.instruction.lower()
    print("  [OK] FocalWizard waits for the distance first")


def test_focal_computes_focal_length():
    db, stored = _db()
    wiz = FocalWizard(CalibrationStore(db), face_width_cm=14.0)
    wiz.set_distance_cm(60.0)
    state = None
    for _ in range(_FOCAL_SAMPLES + 10):
        state = wiz.feed(_face(cheek_lx=0.25, cheek_rx=0.75), 640)
        if state.done:
            break
    assert state.done
    expected = (0.5 * 640) * 60.0 / 14.0   # px_width * distance / face_width
    assert abs(stored["focal_length_px"] - expected) < 1e-6, stored
    print(f"  [OK] focal length = {stored['focal_length_px']:.1f}px from stable samples")


def test_focal_ignores_moving_head():
    db, stored = _db()
    wiz = FocalWizard(CalibrationStore(db), face_width_cm=14.0)
    wiz.set_distance_cm(60.0)
    for i in range(_FOCAL_SAMPLES * 3):
        state = wiz.feed(_face(nose=(0.5 + 0.02 * (i % 2), 0.5)), 640)
    assert not state.done and "focal_length_px" not in stored
    print("  [OK] moving head yields no focal samples")


# ── GazeWizard basics ────────────────────────────────────────────────────────

def test_gaze_wizard_cancel():
    wiz = GazeWizard(CalibrationStore(_db()[0]), face_id=1, smoother=MagicMock(), sw=1536, sh=960)
    wiz.cancel()
    state = wiz.feed([])
    assert state.cancelled and not state.done
    print("  [OK] GazeWizard.cancel() reports cancelled")


def test_gaze_wizard_grid_size():
    wiz = GazeWizard(CalibrationStore(_db()[0]), face_id=1, smoother=MagicMock(),
                     sw=1536, sh=960, rows=4, cols=5)
    assert len(wiz._pts) == 20
    xs = sorted({x for x, _ in wiz._pts}); ys = sorted({y for _, y in wiz._pts})
    assert len(xs) == 5 and len(ys) == 4
    assert all(0 < x < 1536 for x in xs) and all(0 < y < 960 for y in ys)
    print("  [OK] rows x cols grid inside the screen margins")


TESTS = [
    test_store_returns_default_when_not_calibrated,
    test_store_set_and_get,
    test_store_unknown_key_raises,
    test_store_gaze_model_roundtrip,
    test_focal_waits_for_distance,
    test_focal_computes_focal_length,
    test_focal_ignores_moving_head,
    test_gaze_wizard_cancel,
    test_gaze_wizard_grid_size,
]


if __name__ == "__main__":
    print("\nStep 10 — Calibration Tests\n")
    passed = 0
    for t in TESTS:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{passed}/{len(TESTS)} tests passed")
    sys.exit(0 if passed == len(TESTS) else 1)
