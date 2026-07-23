"""
Smoke tests for Step 9: engine stats wiring
- analysis/focus.py
- core/recognizer.py Identity + per-track state
Run from project root:
    python.exe tests\test_step9_engine_stats.py
"""
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "utils", "facewatch"))

from unittest.mock import MagicMock, patch
import numpy as np
from analysis.focus import compute_focus_score
from core.recognizer import FaceRecognizer, Identity


# ── helpers ───────────────────────────────────────────────────────────────────

def _config(**kwargs):
    defaults = {
        "focus_weight_gaze":        0.40,
        "focus_weight_drowsy":      0.30,
        "focus_weight_distraction": 0.20,
        "focus_weight_posture":     0.10,
        "focus_posture_min_cm":     45.0,
        "focus_posture_max_cm":     90.0,
    }
    defaults.update(kwargs)
    cfg = MagicMock()
    cfg.get.side_effect = lambda k: defaults[k]
    return cfg


# ── focus score tests ─────────────────────────────────────────────────────────

def test_focus_perfect_score():
    score = compute_focus_score(
        gaze_off_sec=0.0, interval_sec=5,
        drowsy_pct=0.0, angry_count=0, surprised_count=0,
        distance_cm=60.0, config=_config(),
    )
    assert score == 100.0
    print(f"  [OK] Perfect conditions → focus score = {score}")


def test_focus_zero_score():
    score = compute_focus_score(
        gaze_off_sec=5.0, interval_sec=5,
        drowsy_pct=1.0, angry_count=5, surprised_count=5,
        distance_cm=200.0, config=_config(),
    )
    assert score == 0.0
    print(f"  [OK] Worst conditions → focus score = {score}")


def test_focus_gaze_penalty():
    # 50% of interval looking away
    score = compute_focus_score(
        gaze_off_sec=2.5, interval_sec=5,
        drowsy_pct=0.0, angry_count=0, surprised_count=0,
        distance_cm=60.0, config=_config(),
    )
    # gaze_score=0.5, others=1.0 → 0.5*0.4 + 1.0*0.3 + 1.0*0.2 + 1.0*0.1 = 0.8 → 80.0
    assert abs(score - 80.0) < 0.1
    print(f"  [OK] 50% gaze off → focus score = {score}")


def test_focus_bad_posture():
    score_good = compute_focus_score(
        gaze_off_sec=0, interval_sec=5, drowsy_pct=0,
        angry_count=0, surprised_count=0, distance_cm=60.0, config=_config(),
    )
    score_bad = compute_focus_score(
        gaze_off_sec=0, interval_sec=5, drowsy_pct=0,
        angry_count=0, surprised_count=0, distance_cm=20.0, config=_config(),
    )
    assert score_good > score_bad
    print(f"  [OK] Bad posture reduces score: {score_good} → {score_bad}")


def test_focus_unknown_distance_neutral():
    score_known = compute_focus_score(
        gaze_off_sec=0, interval_sec=5, drowsy_pct=0,
        angry_count=0, surprised_count=0, distance_cm=60.0, config=_config(),
    )
    score_unknown = compute_focus_score(
        gaze_off_sec=0, interval_sec=5, drowsy_pct=0,
        angry_count=0, surprised_count=0, distance_cm=-1.0, config=_config(),
    )
    assert score_unknown < score_known  # 0.5 posture penalty applied
    print(f"  [OK] Unknown distance applies neutral penalty: {score_unknown}")


# ── Identity + recognizer state tests ────────────────────────────────────────

def test_identity_default_is_pending():
    db = MagicMock()
    cfg = MagicMock()
    r = FaceRecognizer(db, cfg)
    identity = r.get_identity(99)
    assert identity.status == "pending"
    assert identity.face_id is None
    print("  [OK] Unknown track_id returns pending Identity")


def test_drop_track_removes_state():
    db = MagicMock()
    cfg = MagicMock()
    r = FaceRecognizer(db, cfg)
    # Manually inject identity
    from core.recognizer import Identity
    r._identities[1] = Identity(face_id=1, name="Alice", status="known")
    r.drop_track(1)
    assert r.get_identity(1).status == "pending"
    print("  [OK] drop_track removes identity state")


def test_submit_sets_pending_and_resolves():
    db = MagicMock()
    db.get_all_known_faces.return_value = []
    db.get_face_by_id.return_value = {"name": "Alice"}
    cfg = MagicMock()
    cfg.get.side_effect = lambda k: {
        "recognition_threshold": 0.6,
        "recognition_match_strategy": "best_single",
    }[k]

    r = FaceRecognizer(db, cfg)
    crop = np.zeros((100, 100, 3), dtype=np.uint8)

    import core.recognizer as mod
    orig = mod._embed
    mod._embed = lambda _: np.ones(512, dtype=np.float32) / np.sqrt(512)

    r.submit(1, crop)
    time.sleep(0.3)  # wait for background thread

    mod._embed = orig
    identity = r.get_identity(1)
    assert identity.status == "unknown"  # no known faces in DB → unknown
    assert 1 not in r._pending
    print("  [OK] submit resolves to unknown when no known faces in DB")


# ── runner ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\nStep 9 — Engine Stats Smoke Tests\n")

    tests = [
        test_focus_perfect_score,
        test_focus_zero_score,
        test_focus_gaze_penalty,
        test_focus_bad_posture,
        test_focus_unknown_distance_neutral,
        test_identity_default_is_pending,
        test_drop_track_removes_state,
        test_submit_sets_pending_and_resolves,
    ]

    passed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {t.__name__}: {e}")

    print(f"\n{passed}/{len(tests)} tests passed")
