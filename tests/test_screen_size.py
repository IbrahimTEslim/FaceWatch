"""
Tests for automatic screen size detection (ui/screen.py, CalibrationOverlay.screen_size,
GazeTracker screen bounds, DB migration 5).
Run from project root:
    python.exe tests\test_screen_size.py
"""
import os
import sqlite3
import sys
import tempfile
from unittest.mock import MagicMock, patch

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "utils", "facewatch"))

from analysis.gaze import GazeTracker
from storage.db import Database
from ui import screen
from ui.calibration_overlay import CalibrationOverlay


# ── helpers ───────────────────────────────────────────────────────────────────

class _AliveProcess:
    def is_alive(self) -> bool:
        return True


def _overlay_with_fake_process() -> CalibrationOverlay:
    """Overlay whose 'child' end we drive by hand instead of spawning Qt."""
    ov = CalibrationOverlay()
    ov._process = _AliveProcess()
    return ov


def _gaze_config():
    cfg = MagicMock()
    cfg.get.side_effect = lambda k: {
        "gaze_alert_sec": 10, "gaze_return_sec": 3,
        "gaze_edge_margin_x_px": 0, "gaze_edge_margin_y_px": 0,
    }[k]
    return cfg


def _identity_calibration():
    cal = MagicMock()
    cal.load_gaze_model.return_value = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    return cal


# ── CalibrationOverlay.screen_size ───────────────────────────────────────────

def test_overlay_reports_size_and_skips_other_messages():
    ov = _overlay_with_fake_process()
    ov._child_conn.send({"type": "something_else"})
    ov._child_conn.send({"type": "screen", "w": 1536, "h": 960})
    assert ov.screen_size(timeout=1.0) == (1536, 960)
    print("  [OK] screen_size() returns reported size, ignoring unrelated messages")


def test_overlay_size_is_cached():
    ov = _overlay_with_fake_process()
    ov._child_conn.send({"type": "screen", "w": 2560, "h": 1440})
    ov.screen_size(timeout=1.0)
    ov._process = None  # even if the overlay dies, the cached value stays
    assert ov.screen_size(timeout=0.1) == (2560, 1440)
    print("  [OK] screen_size() caches the first report")


def test_overlay_times_out_with_none():
    ov = _overlay_with_fake_process()
    assert ov.screen_size(timeout=0.2) is None
    print("  [OK] screen_size() returns None on timeout")


def test_overlay_not_started_returns_none():
    assert CalibrationOverlay().screen_size(timeout=0.2) is None
    print("  [OK] screen_size() returns None when overlay not running")


def test_real_overlay_matches_qt():
    """Spawns the real Qt overlay process and compares with Qt in this process."""
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    g = app.primaryScreen().geometry()
    expected = (g.width(), g.height())

    ov = CalibrationOverlay()
    ov.start()
    try:
        size = ov.screen_size(timeout=30.0)
    finally:
        ov.stop()
    assert size == expected, f"overlay {size} != Qt {expected}"
    print(f"  [OK] real overlay reports {size[0]}x{size[1]} (matches Qt)")


# ── detect_screen_size fallbacks ─────────────────────────────────────────────

def test_detect_prefers_overlay():
    ov = MagicMock()
    ov.screen_size.return_value = (1536, 960)
    with patch.object(screen, "_tk_screen_size", return_value=(1, 1)):
        assert screen.detect_screen_size(ov, timeout=0.1) == (1536, 960)
    print("  [OK] detect_screen_size() prefers the overlay report")


def test_detect_falls_back_to_tk():
    ov = MagicMock()
    ov.screen_size.return_value = None
    with patch.object(screen, "_tk_screen_size", return_value=(1280, 800)):
        assert screen.detect_screen_size(ov, timeout=0.1) == (1280, 800)
    print("  [OK] detect_screen_size() falls back to tkinter")


def test_detect_last_resort():
    ov = MagicMock()
    ov.screen_size.return_value = None
    with patch.object(screen, "_tk_screen_size", return_value=None):
        assert screen.detect_screen_size(ov, timeout=0.1) == (1920, 1080)
    print("  [OK] detect_screen_size() last resort is 1920x1080")


def test_tk_matches_qt_logical_size():
    """Runs after Qt has made this process DPI-aware — tk must still report logical px."""
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    g = app.primaryScreen().geometry()
    size = screen._tk_screen_size()
    assert size == (g.width(), g.height()), f"tk {size} != Qt {(g.width(), g.height())}"
    print(f"  [OK] tkinter fallback reports {size} (matches Qt logical size)")


# ── GazeTracker uses its own screen bounds ───────────────────────────────────

def test_gaze_tracker_uses_constructor_screen_size():
    hit = (1000.0, 500.0)  # identity affine -> screen point (1000, 500)

    small = GazeTracker(800, 600).update(hit, 0.1, _gaze_config(), _identity_calibration(), face_id=1)
    assert not small.on_screen and small.direction == "right", small

    large = GazeTracker(1920, 1080).update(hit, 0.1, _gaze_config(), _identity_calibration(), face_id=1)
    assert large.on_screen and large.direction == "center", large
    print("  [OK] GazeTracker on-screen check uses constructor screen size")


# ── Migration 5 ──────────────────────────────────────────────────────────────

def test_migration_removes_screen_keys():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "v4.db")
        Database(path).close()  # build current schema

        conn = sqlite3.connect(path)
        conn.executemany(
            "INSERT INTO config (key, value, type, description, category) VALUES (?,?,?,?,?)",
            [("screen_w_px", "1920", "int", "w", "gaze"),
             ("screen_h_px", "1080", "int", "h", "gaze"),
             ("gaze_alert_sec", "10", "int", "a", "gaze")],
        )
        conn.execute("PRAGMA user_version = 4")
        conn.commit()
        conn.close()

        db = Database(path)
        try:
            assert db.get_config("screen_w_px") is None
            assert db.get_config("screen_h_px") is None
            assert db.get_config("gaze_alert_sec") == "10"
            version = db._cx.conn.execute("PRAGMA user_version").fetchone()[0]
            assert version == 5, version
        finally:
            db.close()
    print("  [OK] migration 5 drops screen_w_px/screen_h_px, keeps other config")


if __name__ == "__main__":
    print("\nScreen Size Detection Tests\n")

    tests = [
        test_overlay_reports_size_and_skips_other_messages,
        test_overlay_size_is_cached,
        test_overlay_times_out_with_none,
        test_overlay_not_started_returns_none,
        test_real_overlay_matches_qt,
        test_detect_prefers_overlay,
        test_detect_falls_back_to_tk,
        test_detect_last_resort,
        test_tk_matches_qt_logical_size,
        test_gaze_tracker_uses_constructor_screen_size,
        test_migration_removes_screen_keys,
    ]

    passed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {t.__name__}: {type(e).__name__}: {e}")

    print(f"\n{passed}/{len(tests)} tests passed")
    sys.exit(0 if passed == len(tests) else 1)
