"""
Smoke tests for Step 4: analysis/expressions/
Run from project root:
    python.exe tests\test_step4_expressions.py
"""
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "utils", "facewatch"))

from unittest.mock import MagicMock
from analysis.expressions.blink import BlinkLeft, BlinkRight
from analysis.expressions.smile import Smile
from analysis.expressions.angry import Angry
from analysis.expressions.surprised import Surprised
from analysis.expressions.drowsy import Drowsy
from analysis.expressions.neutral import Neutral
from analysis.expressions.registry import build_expressions


# ── helpers ───────────────────────────────────────────────────────────────────

def _config(overrides: dict = None):
    defaults = {
        "expr_threshold_blink": 0.50,
        "expr_threshold_smile": 0.50,
        "expr_threshold_angry": 0.45,
        "expr_threshold_surprised": 0.40,
        "expr_threshold_neutral": 0.25,
        "expr_threshold_drowsy": 0.15,
        "drowsy_window_sec": 2,
    }
    if overrides:
        defaults.update(overrides)
    cfg = MagicMock()
    cfg.get.side_effect = lambda k: defaults[k]
    return cfg


def _bs(**kwargs) -> dict:
    return kwargs


# ── tests ─────────────────────────────────────────────────────────────────────

def test_blink_activates():
    expr = BlinkLeft()
    cfg = _config()
    expr.update(_bs(eyeBlinkLeft=0.8), [], cfg)
    assert expr.active
    assert expr.count == 1
    print("  [OK] BlinkLeft activates above threshold and counts event")


def test_blink_no_count_within_cooldown():
    expr = BlinkLeft()
    cfg = _config()
    expr.update(_bs(eyeBlinkLeft=0.8), [], cfg)
    expr.update(_bs(eyeBlinkLeft=0.0), [], cfg)  # deactivate
    expr.update(_bs(eyeBlinkLeft=0.8), [], cfg)  # re-activate within cooldown
    assert expr.count == 1
    print("  [OK] BlinkLeft does not double-count within cooldown")


def test_smile_activates():
    expr = Smile()
    cfg = _config()
    expr.update(_bs(mouthSmileLeft=0.7, mouthSmileRight=0.6), [], cfg)
    assert expr.active
    assert abs(expr.value - 0.65) < 1e-6
    print(f"  [OK] Smile activates (value={expr.value:.2f})")


def test_angry_activates():
    expr = Angry()
    cfg = _config()
    expr.update(_bs(browDownLeft=0.6, browDownRight=0.5), [], cfg)
    assert expr.active
    print(f"  [OK] Angry activates (value={expr.value:.2f})")


def test_surprised_activates():
    expr = Surprised()
    cfg = _config()
    expr.update(_bs(browOuterUpLeft=0.6, browOuterUpRight=0.5, browInnerUp=0.7), [], cfg)
    assert expr.active
    print(f"  [OK] Surprised activates (value={expr.value:.2f})")


def test_neutral_active_when_all_others_inactive():
    others = [BlinkLeft(), Smile(), Angry()]
    neutral = Neutral(others)
    cfg = _config()
    # All others inactive
    for e in others:
        e.update(_bs(), [], cfg)
    neutral.update(_bs(), [], cfg)
    assert neutral.active
    print("  [OK] Neutral active when all others inactive")


def test_neutral_inactive_when_any_other_active():
    smile = Smile()
    neutral = Neutral([smile])
    cfg = _config()
    smile.update(_bs(mouthSmileLeft=0.9, mouthSmileRight=0.9), [], cfg)
    neutral.update(_bs(), [], cfg)
    assert not neutral.active
    print("  [OK] Neutral inactive when another expression is active")


def test_drowsy_perclos_below_threshold():
    expr = Drowsy()
    cfg = _config({"expr_threshold_drowsy": 0.15, "drowsy_window_sec": 2})
    # Feed mostly open eyes
    for _ in range(10):
        expr.update(_bs(eyeBlinkLeft=0.1, eyeBlinkRight=0.1), [], cfg)
    assert not expr.active
    print(f"  [OK] Drowsy inactive when eyes mostly open (perclos={expr.value:.2f})")


def test_drowsy_perclos_above_threshold():
    expr = Drowsy()
    cfg = _config({"expr_threshold_drowsy": 0.15, "drowsy_window_sec": 2})
    # Feed mostly closed eyes
    for _ in range(10):
        expr.update(_bs(eyeBlinkLeft=0.9, eyeBlinkRight=0.9), [], cfg)
    assert expr.active
    print(f"  [OK] Drowsy active when eyes mostly closed (perclos={expr.value:.2f})")


def test_get_interval_stats_resets():
    expr = BlinkLeft()
    cfg = _config()
    expr.update(_bs(eyeBlinkLeft=0.8), [], cfg)
    expr.update(_bs(eyeBlinkLeft=0.0), [], cfg)
    stats = expr.get_interval_stats()
    assert stats["count"] == 1
    assert stats["total_frames"] == 2
    # Second call should be zeroed
    stats2 = expr.get_interval_stats()
    assert stats2["count"] == 0
    assert stats2["total_frames"] == 0
    print("  [OK] get_interval_stats returns deltas and resets")


def test_registry_builds_correctly():
    expressions = build_expressions()
    names = [e.name for e in expressions]
    assert "blink_left" in names
    assert "blink_right" in names
    assert "smile" in names
    assert "angry" in names
    assert "surprised" in names
    assert "drowsy" in names
    assert "neutral" in names
    assert names[-1] == "neutral"  # Neutral must be last
    print(f"  [OK] Registry builds {len(expressions)} expressions, Neutral is last")


# ── runner ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\nStep 4 — Expressions Smoke Tests\n")

    tests = [
        test_blink_activates,
        test_blink_no_count_within_cooldown,
        test_smile_activates,
        test_angry_activates,
        test_surprised_activates,
        test_neutral_active_when_all_others_inactive,
        test_neutral_inactive_when_any_other_active,
        test_drowsy_perclos_below_threshold,
        test_drowsy_perclos_above_threshold,
        test_get_interval_stats_resets,
        test_registry_builds_correctly,
    ]

    passed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {t.__name__}: {e}")

    print(f"\n{passed}/{len(tests)} tests passed")
