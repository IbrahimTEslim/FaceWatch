"""
Smoke tests for Step 7: alerts/
Run from project root:
    python.exe tests\test_step7_alerts.py
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "utils", "facewatch"))

from unittest.mock import MagicMock
from alerts.base import Alert, AlertEvent, AlertStatus
from alerts.gaze_alert import GazeAlert
from alerts.proximity_alert import ProximityAlert
from alerts.registry import build_alerts


# ── helpers ───────────────────────────────────────────────────────────────────

def _config(enter_sec: float, exit_sec: float, enter_key: str, exit_key: str):
    cfg = MagicMock()
    cfg.get.side_effect = lambda k: {
        enter_key: enter_sec,
        exit_key: exit_sec,
        "notifications_enabled": False,
    }[k]
    return cfg


def _gaze_config(enter=10.0, exit=3.0):
    return _config(enter, exit, "gaze_alert_sec", "gaze_return_sec")


def _prox_config(enter=5.0, exit=8.0):
    return _config(enter, exit, "proximity_alert_sec", "proximity_clear_sec")


# ── base state machine tests ──────────────────────────────────────────────────

def test_alert_does_not_fire_before_threshold():
    alert = GazeAlert()
    cfg = _gaze_config(enter=3.0)
    for _ in range(2):
        event = alert.update(True, 1.0, cfg)
    assert not alert.active
    assert event.status == AlertStatus.NONE
    print("  [OK] Alert does not fire before enter_sec threshold")


def test_alert_fires_at_threshold():
    alert = GazeAlert()
    cfg = _gaze_config(enter=3.0)
    event = None
    for _ in range(3):
        event = alert.update(True, 1.0, cfg)
    assert alert.active
    assert event.status == AlertStatus.FIRED
    print("  [OK] Alert fires after enter_sec exceeded")


def test_enter_timer_resets_on_false_condition():
    alert = GazeAlert()
    cfg = _gaze_config(enter=3.0)
    alert.update(True, 2.0, cfg)   # 2s in
    alert.update(False, 0.1, cfg)  # condition clears — timer resets
    for _ in range(2):
        event = alert.update(True, 1.0, cfg)
    assert not alert.active  # only 2s accumulated, not 4s
    print("  [OK] Enter timer resets when condition becomes false")


def test_alert_does_not_clear_before_exit_threshold():
    alert = GazeAlert()
    cfg = _gaze_config(enter=3.0, exit=5.0)
    for _ in range(3):
        alert.update(True, 1.0, cfg)
    assert alert.active
    for _ in range(3):
        event = alert.update(False, 1.0, cfg)
    assert alert.active  # only 3s, need 5s
    assert event.status == AlertStatus.NONE
    print("  [OK] Alert does not clear before exit_sec threshold")


def test_alert_clears_at_exit_threshold():
    alert = GazeAlert()
    cfg = _gaze_config(enter=3.0, exit=3.0)
    for _ in range(3):
        alert.update(True, 1.0, cfg)
    event = None
    for _ in range(3):
        event = alert.update(False, 1.0, cfg)
    assert not alert.active
    assert event.status == AlertStatus.CLEARED
    print("  [OK] Alert clears after exit_sec exceeded")


def test_exit_timer_resets_if_condition_returns():
    alert = GazeAlert()
    cfg = _gaze_config(enter=3.0, exit=5.0)
    for _ in range(3):
        alert.update(True, 1.0, cfg)
    alert.update(False, 3.0, cfg)  # 3s toward clearing
    alert.update(True, 0.1, cfg)   # condition returns — exit timer resets
    for _ in range(3):
        event = alert.update(False, 1.0, cfg)
    assert alert.active  # only 3s since reset, need 5s
    print("  [OK] Exit timer resets when condition returns during clearing")


def test_alert_can_refire_after_clearing():
    alert = GazeAlert()
    cfg = _gaze_config(enter=3.0, exit=3.0)
    for _ in range(3):
        alert.update(True, 1.0, cfg)
    for _ in range(3):
        alert.update(False, 1.0, cfg)
    assert not alert.active
    event = None
    for _ in range(3):
        event = alert.update(True, 1.0, cfg)
    assert alert.active
    assert event.status == AlertStatus.FIRED
    print("  [OK] Alert can refire after being cleared")


# ── concrete alert tests ──────────────────────────────────────────────────────

def test_gaze_alert_messages():
    alert = GazeAlert()
    cfg = _gaze_config(enter=3.0, exit=3.0)
    event = None
    for _ in range(3):
        event = alert.update(True, 1.0, cfg)
    assert "looking away" in event.message.lower()
    for _ in range(3):
        event = alert.update(False, 1.0, cfg)
    assert "gaze" in event.message.lower()
    print("  [OK] GazeAlert fired/cleared messages are correct")


def test_proximity_alert_fires():
    alert = ProximityAlert()
    cfg = _prox_config(enter=3.0, exit=5.0)
    event = None
    for _ in range(3):
        event = alert.update(True, 1.0, cfg)
    assert alert.active
    assert event.status == AlertStatus.FIRED
    assert "close" in event.message.lower()
    print("  [OK] ProximityAlert fires with correct message")


def test_registry_builds_both_alerts():
    alerts = build_alerts()
    types = [type(a).__name__ for a in alerts]
    expected = {"GazeAlert", "ProximityAlert", "EyeStrainAlert",
                "FatigueOnsetAlert", "WorkReminderAlert"}
    assert set(types) == expected, types
    assert len(alerts) == len(expected)
    print(f"  [OK] Registry builds {len(alerts)} alerts: {types}")


# ── runner ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\nStep 7 — Alerts Smoke Tests\n")

    tests = [
        test_alert_does_not_fire_before_threshold,
        test_alert_fires_at_threshold,
        test_enter_timer_resets_on_false_condition,
        test_alert_does_not_clear_before_exit_threshold,
        test_alert_clears_at_exit_threshold,
        test_exit_timer_resets_if_condition_returns,
        test_alert_can_refire_after_clearing,
        test_gaze_alert_messages,
        test_proximity_alert_fires,
        test_registry_builds_both_alerts,
    ]

    passed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {t.__name__}: {e}")

    print(f"\n{passed}/{len(tests)} tests passed")
