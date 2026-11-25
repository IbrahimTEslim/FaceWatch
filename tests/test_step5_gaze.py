"""
Tests for analysis/gaze.py (ptgaze hit -> affine -> screen, hysteresis)
and GazeAlert handling of unknown gaze.
Run from project root:
    python.exe tests\test_step5_gaze.py
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "utils", "facewatch"))

from unittest.mock import MagicMock

import numpy as np

from analysis.gaze import GazeTracker, GazeState
from alerts.base import AlertContext, AlertStatus
from alerts.gaze_alert import GazeAlert


SW, SH = 1920, 1080
CENTER = (960.0, 540.0)
LEFT   = (-500.0, 540.0)   # identity affine -> 500 px left of the screen
FACE   = 1


# ── helpers ───────────────────────────────────────────────────────────────────

class _Passthrough:
    """Smoother stand-in so tests see raw mapped points."""
    def step(self, sx, sy):
        return sx, sy


def _config(alert_sec=10.0, return_sec=3.0):
    cfg = MagicMock()
    cfg.get.side_effect = lambda k: {
        "gaze_alert_sec": alert_sec,
        "gaze_return_sec": return_sec,
        "gaze_edge_margin_x_px": 0,
        "gaze_edge_margin_y_px": 0,
        "notifications_enabled": False,
    }[k]
    return cfg


def _calibrated():
    cal = MagicMock()
    cal.load_gaze_model.return_value = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    return cal


def _uncalibrated():
    cal = MagicMock()
    cal.load_gaze_model.return_value = None
    return cal


def _tracker():
    return GazeTracker(SW, SH, smoother=_Passthrough())


def _feed(tracker, hit, dt, cfg, cal=None, n=1) -> GazeState:
    cal = cal or _calibrated()
    state = None
    for _ in range(n):
        state = tracker.update(hit, dt, cfg, cal, FACE)
    return state


# ── GazeTracker ───────────────────────────────────────────────────────────────

def test_no_face_returns_not_present():
    state = _tracker().update(None, 0.033, _config(), _calibrated(), None)
    assert not state.face_present and not state.tracking
    assert state.on_screen_or_unknown is None
    print("  [OK] No face -> not present, not tracking")


def test_uncalibrated_is_unknown_not_off_screen():
    t, cfg, cal = _tracker(), _config(alert_sec=3.0), _uncalibrated()
    state = _feed(t, CENTER, 1.0, cfg, cal, n=10)
    assert state.face_present and not state.tracking
    assert state.direction == "unknown"
    assert state.on_screen_or_unknown is None
    assert state.off_screen_sec == 0.0 and not state.alert_active
    print("  [OK] Uncalibrated face -> gaze unknown, timers untouched")


def test_missing_hit_is_unknown():
    state = _feed(_tracker(), None, 1.0, _config(), n=5)
    assert state.face_present and not state.tracking
    assert state.on_screen_or_unknown is None and state.off_screen_sec == 0.0
    print("  [OK] Calibrated but no gaze ray -> unknown")


def test_center_gaze_on_screen():
    state = _feed(_tracker(), CENTER, 0.033, _config())
    assert state.tracking and state.on_screen and state.direction == "center"
    assert state.on_screen_or_unknown is True
    print("  [OK] Center gaze -> on screen")


def test_left_gaze_off_screen():
    state = _feed(_tracker(), LEFT, 0.033, _config())
    assert state.tracking and not state.on_screen and state.direction == "left"
    assert state.on_screen_or_unknown is False
    print("  [OK] Left gaze -> off screen")


def test_off_screen_timer_increments():
    state = _feed(_tracker(), LEFT, 1.0, _config(alert_sec=10.0), n=5)
    assert state.off_screen_sec == 5.0 and not state.alert_active
    print(f"  [OK] off_screen_timer increments ({state.off_screen_sec:.1f}s)")


def test_alert_fires_after_threshold():
    state = _feed(_tracker(), LEFT, 1.0, _config(alert_sec=3.0), n=4)
    assert state.alert_active
    print("  [OK] Alert fires after gaze_alert_sec")


def test_timer_decrements_on_return():
    t, cfg = _tracker(), _config(alert_sec=10.0)
    _feed(t, LEFT, 1.0, cfg, n=4)
    state = _feed(t, CENTER, 1.0, cfg, n=2)
    assert state.off_screen_sec == 2.0 and not state.alert_active
    print(f"  [OK] off_screen_timer decrements on return ({state.off_screen_sec:.1f}s)")


def test_brief_glance_back_resets_return_timer():
    t, cfg = _tracker(), _config(alert_sec=3.0, return_sec=3.0)
    _feed(t, LEFT, 1.0, cfg, n=4)
    _feed(t, CENTER, 1.0, cfg, n=2)
    _feed(t, LEFT, 1.0, cfg)
    state = _feed(t, CENTER, 1.0, cfg, n=2)
    assert state.alert_active
    print("  [OK] Brief glance back then away keeps alert active")


def test_alert_clears_after_return_sec():
    t, cfg = _tracker(), _config(alert_sec=3.0, return_sec=3.0)
    _feed(t, LEFT, 1.0, cfg, n=4)
    state = _feed(t, CENTER, 1.0, cfg, n=4)
    assert not state.alert_active and state.off_screen_sec == 0.0
    print("  [OK] Alert clears after gaze_return_sec on screen")


def test_unknown_frames_preserve_alert_state():
    t, cfg = _tracker(), _config(alert_sec=3.0)
    _feed(t, LEFT, 1.0, cfg, n=4)
    before = t._off_screen_timer
    state = _feed(t, None, 1.0, cfg, n=5)
    assert state.alert_active and state.off_screen_sec == before
    print("  [OK] Unknown frames hold alert state and timer")


# ── GazeAlert with unknown gaze ──────────────────────────────────────────────

def _ctx(on_screen, cfg):
    return AlertContext(gaze_on_screen=on_screen, dist_cm=60.0, config=cfg)


def test_gaze_alert_never_fires_while_unknown():
    cfg, alert = _config(alert_sec=10.0), GazeAlert()
    for _ in range(600):  # 60 s of unknown gaze
        ev = alert.update(alert.is_condition_met(_ctx(None, cfg)), 0.1, cfg)
        assert ev.status is AlertStatus.NONE
    assert not alert.active
    print("  [OK] GazeAlert never fires for unknown (uncalibrated) gaze")


def test_gaze_alert_holds_timer_across_unknown():
    cfg, alert = _config(alert_sec=10.0), GazeAlert()
    for _ in range(8):
        alert.update(alert.is_condition_met(_ctx(False, cfg)), 1.0, cfg)
    for _ in range(5):  # tracking dropout — must not reset the 8 s
        alert.update(alert.is_condition_met(_ctx(None, cfg)), 1.0, cfg)
    events = [alert.update(alert.is_condition_met(_ctx(False, cfg)), 1.0, cfg) for _ in range(2)]
    assert alert.active and events[-1].status is AlertStatus.FIRED
    print("  [OK] GazeAlert enter timer survives tracking dropouts")


def test_gaze_alert_on_screen_still_resets():
    cfg, alert = _config(alert_sec=10.0), GazeAlert()
    for _ in range(8):
        alert.update(alert.is_condition_met(_ctx(False, cfg)), 1.0, cfg)
    alert.update(alert.is_condition_met(_ctx(True, cfg)), 1.0, cfg)
    for _ in range(3):
        alert.update(alert.is_condition_met(_ctx(False, cfg)), 1.0, cfg)
    assert not alert.active
    print("  [OK] Looking back on screen still resets the enter timer")


# ── runner ────────────────────────────────────────────────────────────────────

TESTS = [
    test_no_face_returns_not_present,
    test_uncalibrated_is_unknown_not_off_screen,
    test_missing_hit_is_unknown,
    test_center_gaze_on_screen,
    test_left_gaze_off_screen,
    test_off_screen_timer_increments,
    test_alert_fires_after_threshold,
    test_timer_decrements_on_return,
    test_brief_glance_back_resets_return_timer,
    test_alert_clears_after_return_sec,
    test_unknown_frames_preserve_alert_state,
    test_gaze_alert_never_fires_while_unknown,
    test_gaze_alert_holds_timer_across_unknown,
    test_gaze_alert_on_screen_still_resets,
]


if __name__ == "__main__":
    print("\nStep 5 — Gaze Tracker Tests\n")
    passed = 0
    for t in TESTS:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{passed}/{len(TESTS)} tests passed")
    sys.exit(0 if passed == len(TESTS) else 1)
