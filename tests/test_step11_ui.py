"""
Smoke tests for Step 11: ui/renderer.py + ui/input_handler.py
Run from project root:
    venv\Scripts\python.exe tests\test_step11_ui.py
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "utils", "facewatch"))

import numpy as np
from unittest.mock import MagicMock

from ui.input_handler import InputHandler, Action
from ui.renderer import Renderer
from core.recognizer import Identity
from analysis.gaze import GazeState


# ── helpers ───────────────────────────────────────────────────────────────────

def _config(**overrides):
    from config_defaults import DEFAULTS
    defaults = {key: value for key, value, *_ in DEFAULTS}  # stays in sync with new keys
    defaults.update(overrides)
    cfg = MagicMock()
    cfg.get.side_effect = lambda k: defaults[k]
    return cfg


def _blank_frame():
    return np.zeros((480, 640, 3), dtype=np.uint8)


# ── InputHandler tests ────────────────────────────────────────────────────────

def test_input_default_keys():
    handler = InputHandler(_config())
    assert handler.handle(ord("q")) == Action.QUIT
    assert handler.handle(ord("r")) == Action.REGISTER
    assert handler.handle(ord("c")) == Action.CALIBRATE
    assert handler.handle(ord("d")) == Action.TOGGLE_DEBUG
    assert handler.handle(ord("s")) == Action.FORCE_STATS
    assert handler.handle(ord("f")) == Action.FORCE_REIDENTIFY
    print("  [OK] Default key bindings map to correct Actions")


def test_input_unknown_key_returns_none():
    handler = InputHandler(_config())
    assert handler.handle(ord("z")) == Action.NONE
    assert handler.handle(255) == Action.NONE
    print("  [OK] Unknown key returns Action.NONE")


def test_input_custom_key_binding():
    handler = InputHandler(_config(key_quit="x"))
    assert handler.handle(ord("x")) == Action.QUIT
    assert handler.handle(ord("q")) == Action.NONE
    print("  [OK] Custom key binding overrides default")


# ── Renderer tests ────────────────────────────────────────────────────────────

def test_renderer_returns_ndarray():
    r = Renderer(_config())
    frame = r.draw(_blank_frame(), {}, {}, {}, {}, {}, {}, {})
    assert isinstance(frame, np.ndarray)
    print("  [OK] draw() returns ndarray on empty tracks")


def test_renderer_draws_known_face():
    r = Renderer(_config())
    tracks = {1: [100.0, 100.0, 200.0, 200.0]}
    identities = {1: Identity(face_id=1, name="alice", display_name="Alice", status="known")}
    gaze = {1: GazeState(face_present=True, on_screen=True)}
    frame = r.draw(_blank_frame(), tracks, identities, gaze, {}, {1: 60.0}, {}, {1: False})
    assert isinstance(frame, np.ndarray)
    print("  [OK] draw() handles known face without error")


def test_renderer_draws_alert():
    r = Renderer(_config())
    tracks = {1: [100.0, 100.0, 200.0, 200.0]}
    identities = {1: Identity(status="unknown")}
    gaze = {1: GazeState(face_present=True, alert_active=True)}
    frame = r.draw(_blank_frame(), tracks, identities, gaze, {}, {1: -1.0}, {}, {1: True})
    assert isinstance(frame, np.ndarray)
    print("  [OK] draw() handles alert state without error")


def test_renderer_debug_toggle():
    r = Renderer(_config())
    assert not r._debug
    r.toggle_debug()
    assert r._debug
    r.toggle_debug()
    assert not r._debug
    print("  [OK] toggle_debug() flips debug flag")


def test_renderer_debug_overlay():
    r = Renderer(_config())
    r.toggle_debug()
    tracks = {1: [50.0, 50.0, 150.0, 150.0]}
    identities = {1: Identity(name="bob", display_name="Bob", status="known")}
    gaze = {1: GazeState(face_present=True, direction="left", off_screen_sec=3.5)}
    demo = {1: {"age_estimate": 30, "gender": "Man", "race": "white", "face_width_cm": 14.0}}
    frame = r.draw(_blank_frame(), tracks, identities, gaze, {1: []}, {1: 55.0}, {1: 82.0}, {1: False}, demo)
    assert isinstance(frame, np.ndarray)
    r.toggle_debug()  # close debug window
    print("  [OK] Debug window draws without error")


# ── runner ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\nStep 11 -- UI Smoke Tests\n")

    tests = [
        test_input_default_keys,
        test_input_unknown_key_returns_none,
        test_input_custom_key_binding,
        test_renderer_returns_ndarray,
        test_renderer_draws_known_face,
        test_renderer_draws_alert,
        test_renderer_debug_toggle,
        test_renderer_debug_overlay,
    ]

    passed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {t.__name__}: {e}")

    print(f"\n{passed}/{len(tests)} tests passed")
