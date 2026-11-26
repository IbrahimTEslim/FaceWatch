"""
Smoke test for Step 2: core/detector.py + core/tracker.py
Run from project root:
    venv/Scripts/python.exe tests/test_step2_core.py
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "utils", "facewatch"))

import numpy as np
from core.tracker import FaceTracker


def test_tracker_empty(tracker):
    result = tracker.update([])
    assert result == {}, f"Expected empty dict, got {result}"
    print("  [OK] Tracker handles empty detections")


def test_tracker_returns_dict(tracker):
    # min_hits=1 so we get tracks immediately
    dets = [[100, 100, 200, 200, 0.9], [300, 300, 400, 400, 0.8]]
    result = tracker.update(dets)
    assert isinstance(result, dict), "Expected dict"
    for tid, bbox in result.items():
        assert isinstance(tid, int), f"track_id must be int, got {type(tid)}"
        assert len(bbox) == 4, f"bbox must have 4 values, got {len(bbox)}"
    print(f"  [OK] Tracker returns dict[int, list[float]] — {len(result)} track(s)")


def test_tracker_stable_ids(tracker):
    dets = [[100, 100, 200, 200, 0.9]]
    ids_seen = set()
    for _ in range(5):
        result = tracker.update(dets)
        ids_seen.update(result.keys())
    assert len(ids_seen) == 1, f"Expected 1 stable ID, got {ids_seen}"
    print("  [OK] Tracker assigns stable ID across frames")


def test_detector_import():
    # Just verify the import and class are accessible without a model file
    from core.detector import FaceDetector
    assert FaceDetector is not None
    print("  [OK] FaceDetector imports cleanly")


if __name__ == "__main__":
    print("\nStep 2 — Core Smoke Test\n")

    tracker = FaceTracker(max_age=5, min_hits=1)

    tests = [
        lambda: test_tracker_empty(tracker),
        lambda: test_tracker_returns_dict(FaceTracker(max_age=5, min_hits=1)),
        lambda: test_tracker_stable_ids(FaceTracker(max_age=5, min_hits=1)),
        test_detector_import,
    ]

    passed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {e}")

    print(f"\n{passed}/{len(tests)} tests passed")
    sys.exit(0 if passed == len(tests) else 1)
