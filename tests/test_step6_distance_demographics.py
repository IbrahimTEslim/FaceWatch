"""
Smoke tests for Step 6: analysis/distance.py + demographics/
Run from project root:
    python.exe tests\test_step6_distance_demographics.py
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "utils", "facewatch"))

from unittest.mock import MagicMock, patch
from demographics.face_width import estimate_face_width_cm
from demographics.analyzer import DemographicsAnalyzer, _DEFAULT_FACE_WIDTH_CM
from analysis.distance import DistanceEstimator


# ── helpers ───────────────────────────────────────────────────────────────────

def _landmark(x: float, y: float = 0.5):
    lm = MagicMock()
    lm.x = x
    lm.y = y
    return lm


def _make_landmarks(left_x: float, right_x: float, count: int = 478) -> list:
    lms = [_landmark(0.5) for _ in range(count)]
    lms[234] = _landmark(left_x)
    lms[454] = _landmark(right_x)
    return lms


def _config(**kwargs):
    cfg = MagicMock()
    cfg.get.side_effect = lambda k: kwargs[k]
    return cfg


# ── face_width tests ──────────────────────────────────────────────────────────

def test_face_width_adult_male():
    w = estimate_face_width_cm(30, "Man")
    assert w == 14.0
    print(f"  [OK] Adult male face width = {w}cm")


def test_face_width_adult_female():
    w = estimate_face_width_cm(25, "Woman")
    assert w == 13.5
    print(f"  [OK] Adult female face width = {w}cm")


def test_face_width_child():
    w = estimate_face_width_cm(7, "Man")
    assert w == 11.5
    print(f"  [OK] Child (age 7) face width = {w}cm")


def test_face_width_teen_female():
    w = estimate_face_width_cm(15, "Woman")
    assert w == 12.7
    print(f"  [OK] Teen female face width = {w}cm")


# ── distance tests ────────────────────────────────────────────────────────────

def test_distance_formula():
    estimator = DistanceEstimator()
    # cheeks at x=0.3 and x=0.7 on a 1000px wide frame → pixel_width=400
    lms = _make_landmarks(0.3, 0.7)
    dist = estimator.estimate(lms, face_width_cm=14.0, focal_length_px=800.0, frame_w=1000)
    expected = (14.0 * 800.0) / 400.0  # = 28.0
    assert abs(dist - expected) < 0.01
    print(f"  [OK] Distance formula correct ({dist:.1f}cm)")


def test_distance_no_landmarks():
    estimator = DistanceEstimator()
    dist = estimator.estimate([], face_width_cm=14.0, focal_length_px=800.0, frame_w=1000)
    assert dist == -1.0
    print("  [OK] Returns -1.0 when no landmarks")


def test_distance_zero_pixel_width():
    estimator = DistanceEstimator()
    lms = _make_landmarks(0.5, 0.5)  # same x → pixel_width=0
    dist = estimator.estimate(lms, face_width_cm=14.0, focal_length_px=800.0, frame_w=1000)
    assert dist == -1.0
    print("  [OK] Returns -1.0 when pixel_width is zero")


# ── analyzer tests ────────────────────────────────────────────────────────────

def test_analyzer_get_face_width_default_when_no_record():
    db = MagicMock()
    db.get_demographics.return_value = None
    analyzer = DemographicsAnalyzer(db, MagicMock())
    w = analyzer.get_face_width(1)
    assert w == _DEFAULT_FACE_WIDTH_CM
    print(f"  [OK] get_face_width returns default ({w}cm) when no DB record")


def test_analyzer_get_face_width_from_db():
    db = MagicMock()
    db.get_demographics.return_value = {"face_width_cm": 13.5, "last_updated": "2024-01-01T00:00:00Z"}
    analyzer = DemographicsAnalyzer(db, MagicMock())
    w = analyzer.get_face_width(1)
    assert w == 13.5
    print(f"  [OK] get_face_width returns stored value ({w}cm)")


def test_analyzer_maybe_run_triggers_on_no_record():
    db = MagicMock()
    db.get_demographics.return_value = None
    analyzer = DemographicsAnalyzer(db, _config(demographics_refresh_days=7))
    import numpy as np
    crop = MagicMock(spec=np.ndarray)
    with patch.object(analyzer, "_run_async") as mock_run:
        analyzer.maybe_run(1, crop)
        mock_run.assert_called_once_with(1, crop)
    print("  [OK] maybe_run triggers analysis when no record exists")


def test_analyzer_maybe_run_skips_when_fresh():
    db = MagicMock()
    from datetime import datetime, timezone
    fresh_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    db.get_demographics.return_value = {"face_width_cm": 14.0, "last_updated": fresh_ts}
    analyzer = DemographicsAnalyzer(db, _config(demographics_refresh_days=7))
    import numpy as np
    crop = MagicMock(spec=np.ndarray)
    with patch.object(analyzer, "_run_async") as mock_run:
        analyzer.maybe_run(1, crop)
        mock_run.assert_not_called()
    print("  [OK] maybe_run skips analysis when record is fresh")


def test_analyzer_maybe_run_triggers_when_stale():
    db = MagicMock()
    db.get_demographics.return_value = {
        "face_width_cm": 14.0,
        "last_updated": "2020-01-01T00:00:00Z"  # very old
    }
    analyzer = DemographicsAnalyzer(db, _config(demographics_refresh_days=7))
    import numpy as np
    crop = MagicMock(spec=np.ndarray)
    with patch.object(analyzer, "_run_async") as mock_run:
        analyzer.maybe_run(1, crop)
        mock_run.assert_called_once_with(1, crop)
    print("  [OK] maybe_run triggers analysis when record is stale")


# ── runner ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\nStep 6 — Distance + Demographics Smoke Tests\n")

    tests = [
        test_face_width_adult_male,
        test_face_width_adult_female,
        test_face_width_child,
        test_face_width_teen_female,
        test_distance_formula,
        test_distance_no_landmarks,
        test_distance_zero_pixel_width,
        test_analyzer_get_face_width_default_when_no_record,
        test_analyzer_get_face_width_from_db,
        test_analyzer_maybe_run_triggers_on_no_record,
        test_analyzer_maybe_run_skips_when_fresh,
        test_analyzer_maybe_run_triggers_when_stale,
    ]

    passed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {t.__name__}: {e}")

    print(f"\n{passed}/{len(tests)} tests passed")
