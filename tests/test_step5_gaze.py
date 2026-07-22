"""
Smoke tests for Step 5: analysis/gaze.py
Run from project root:
    python.exe tests\test_step5_gaze.py
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "utils", "facewatch"))

from unittest.mock import MagicMock
from analysis.gaze import GazeTracker, GazeState


# ── helpers ───────────────────────────────────────────────────────────────────

def _config(alert_sec=10.0, return_sec=3.0):
    cfg = MagicMock()
    cfg.get.side_effect = lambda k: {
        "gaze_alert_sec": alert_sec,
        "gaze_return_sec": return_sec,
    }[k]
    return cfg


def _landmark(x: float, y: float):
    lm = MagicMock()
    lm.x = x
    lm.y = y
    return lm


def _make_landmarks(direction: str) -> list:
    """Build a minimal 478-landmark list for a given gaze direction."""
    lms = [_landmark(0.5, 0.5) for _ in range(478)]

    # Eye corners and lids — fixed
    lms[33]  = _landmark(0.3, 0.5)   # L outer
    lms[133] = _landmark(0.45, 0.5)  # L inner
    lms[159] = _landmark(0.375, 0.45) # L top
    lms[145] = _landmark(0.375, 0.55) # L bottom
    lms[362] = _landmark(0.55, 0.5)  # R outer
    lms[263] = _landmark(0.7, 0.5)   # R inner
    lms[386] = _landmark(0.625, 0.45) # R top
    lms[374] = _landmark(0.625, 0.55) # R bottom

    if direction == "center":
        lms[468] = _landmark(0.375, 0.5)
        lms[473] = _landmark(0.625, 0.5)
    elif direction == "left":
        lms[468] = _landmark(0.31, 0.5)
        lms[473] = _landmark(0.56, 0.5)
    elif direction == "right":
        lms[468] = _landmark(0.44, 0.5)
        lms[473] = _landmark(0.69, 0.5)
    elif direction == "up":
        lms[468] = _landmark(0.375, 0.46)
        lms[473] = _landmark(0.625, 0.46)
    elif direction == "down":
        lms[468] = _landmark(0.375, 0.54)
        lms[473] = _landmark(0.625, 0.54)

    return lms


# ── tests ─────────────────────────────────────────────────────────────────────

def test_no_face_returns_unknown():
    tracker = GazeTracker()
    state = tracker.update([], 0.033, _config())
    assert not state.face_present
    assert state.direction == "unknown"
    assert not state.on_screen
    print("  [OK] No face returns unknown GazeState")


def test_center_gaze_on_screen():
    tracker = GazeTracker()
    state = tracker.update(_make_landmarks("center"), 0.033, _config())
    assert state.face_present
    assert state.direction == "center"
    assert state.on_screen
    print("  [OK] Center gaze → on_screen=True")


def test_left_gaze_off_screen():
    tracker = GazeTracker()
    state = tracker.update(_make_landmarks("left"), 0.033, _config())
    assert state.direction == "left"
    assert not state.on_screen
    print("  [OK] Left gaze → on_screen=False")


def test_off_screen_timer_increments():
    tracker = GazeTracker()
    cfg = _config(alert_sec=10.0)
    for _ in range(5):
        state = tracker.update(_make_landmarks("left"), 1.0, cfg)
    assert state.off_screen_sec == 5.0
    assert not state.alert_active
    print(f"  [OK] off_screen_timer increments correctly ({state.off_screen_sec:.1f}s)")


def test_alert_fires_after_threshold():
    tracker = GazeTracker()
    cfg = _config(alert_sec=3.0)
    for _ in range(4):
        state = tracker.update(_make_landmarks("left"), 1.0, cfg)
    assert state.alert_active
    print("  [OK] Alert fires after gaze_alert_sec exceeded")


def test_timer_decrements_on_return():
    tracker = GazeTracker()
    cfg = _config(alert_sec=10.0)
    # Build up 4s off-screen
    for _ in range(4):
        tracker.update(_make_landmarks("left"), 1.0, cfg)
    # Look back for 2s
    for _ in range(2):
        state = tracker.update(_make_landmarks("center"), 1.0, cfg)
    assert state.off_screen_sec == 2.0
    assert not state.alert_active
    print(f"  [OK] off_screen_timer decrements when looking back ({state.off_screen_sec:.1f}s)")


def test_brief_glance_back_resets_return_timer():
    tracker = GazeTracker()
    cfg = _config(alert_sec=3.0, return_sec=3.0)
    # Trigger alert
    for _ in range(4):
        tracker.update(_make_landmarks("left"), 1.0, cfg)
    # Look back for 2s (not enough to clear)
    for _ in range(2):
        tracker.update(_make_landmarks("center"), 1.0, cfg)
    # Look away again — return timer should reset
    tracker.update(_make_landmarks("left"), 1.0, cfg)
    # Look back for 2s again — still not enough
    for _ in range(2):
        state = tracker.update(_make_landmarks("center"), 1.0, cfg)
    assert state.alert_active
    print("  [OK] Brief glance back then away resets return timer — alert stays active")


def test_alert_clears_after_return_sec():
    tracker = GazeTracker()
    cfg = _config(alert_sec=3.0, return_sec=3.0)
    # Trigger alert
    for _ in range(4):
        tracker.update(_make_landmarks("left"), 1.0, cfg)
    # Look back continuously for return_sec
    for _ in range(4):
        state = tracker.update(_make_landmarks("center"), 1.0, cfg)
    assert not state.alert_active
    assert state.off_screen_sec == 0.0
    print("  [OK] Alert clears after continuous gaze for gaze_return_sec")


def test_off_screen_keeps_incrementing_during_alert():
    tracker = GazeTracker()
    cfg = _config(alert_sec=3.0, return_sec=10.0)
    # Trigger alert
    for _ in range(4):
        tracker.update(_make_landmarks("left"), 1.0, cfg)
    before = tracker._off_screen_timer
    # Keep looking away
    for _ in range(3):
        state = tracker.update(_make_landmarks("left"), 1.0, cfg)
    assert state.off_screen_sec > before
    print(f"  [OK] off_screen_timer keeps incrementing during alert ({state.off_screen_sec:.1f}s)")


def test_no_face_preserves_alert_state():
    tracker = GazeTracker()
    cfg = _config(alert_sec=3.0)
    # Trigger alert
    for _ in range(4):
        tracker.update(_make_landmarks("left"), 1.0, cfg)
    # Face disappears
    state = tracker.update([], 0.033, cfg)
    assert state.alert_active  # alert preserved
    assert not state.face_present
    print("  [OK] Alert state preserved when face disappears")


# ── runner ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\nStep 5 — Gaze Tracker Smoke Tests\n")

    tests = [
        test_no_face_returns_unknown,
        test_center_gaze_on_screen,
        test_left_gaze_off_screen,
        test_off_screen_timer_increments,
        test_alert_fires_after_threshold,
        test_timer_decrements_on_return,
        test_brief_glance_back_resets_return_timer,
        test_alert_clears_after_return_sec,
        test_off_screen_keeps_incrementing_during_alert,
        test_no_face_preserves_alert_state,
    ]

    passed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {t.__name__}: {e}")

    print(f"\n{passed}/{len(tests)} tests passed")
