"""
Tests for the gaze calibration affine fit (calibration/wizard.py: fit_gaze_affine)
and an end-to-end GazeWizard run with simulated ptgaze hits.
Run from project root:
    python.exe tests\test_gaze_calibration_fit.py
"""
import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "utils", "facewatch"))

from calibration import wizard as wizard_mod
from calibration.wizard import GazeWizard, fit_gaze_affine, _grid_points

SW, SH = 1536, 960
RNG = np.random.default_rng(42)

# screen px -> hit cm (what ptgaze would produce); we fit the inverse
_A = np.array([[0.031, 0.002], [-0.001, 0.028]])
_B = np.array([-24.0, -3.0])


def _to_hit(scr):
    return np.asarray(scr, dtype=np.float64) @ _A.T + _B


def _apply(M, raw):
    return np.asarray(raw) @ M[:, :2].T + M[:, 2]


def _screen_error(M) -> float:
    test = np.stack(np.meshgrid(np.linspace(0, SW, 12), np.linspace(0, SH, 8)), -1).reshape(-1, 2)
    return float(np.mean(np.linalg.norm(_apply(M, _to_hit(test)) - test, axis=1)))


def _noisy_hits(scr, noise_px):
    return _to_hit(scr) + RNG.normal(0, noise_px * 0.03 / np.sqrt(2), (len(scr), 2))


# ── fit_gaze_affine ───────────────────────────────────────────────────────────

def test_exact_recovery_without_noise():
    scr = np.array(_grid_points(SW, SH, 3, 3), dtype=np.float64)
    M = fit_gaze_affine(_to_hit(scr), scr)
    assert M is not None and M.shape == (2, 3)
    assert _screen_error(M) < 1.0, _screen_error(M)
    print(f"  [OK] exact recovery without noise ({_screen_error(M):.3f}px)")


def test_robust_to_one_bad_dot():
    scr = np.array(_grid_points(SW, SH, 3, 3), dtype=np.float64)
    raw = _noisy_hits(scr, 30)
    raw[4] += np.array([12.0, -9.0])  # user looked ~400 px away on the center dot
    err = _screen_error(fit_gaze_affine(raw, scr))
    assert err < 60, err
    print(f"  [OK] one bad dot tolerated ({err:.1f}px mean error)")


def test_beats_previous_ransac_3px():
    new_err, old_err = [], []
    for _ in range(200):
        scr = np.array(_grid_points(SW, SH, 3, 3), dtype=np.float64)
        raw = _noisy_hits(scr, 80)
        new_err.append(_screen_error(fit_gaze_affine(raw, scr)))
        M_old, _ = cv2.estimateAffine2D(raw.astype(np.float32), scr.astype(np.float32),
                                        method=cv2.RANSAC, ransacReprojThreshold=3.0, maxIters=2000)
        old_err.append(_screen_error(M_old) if M_old is not None else 1e9)
    new_med, old_med = float(np.median(new_err)), float(np.median(old_err))
    assert new_med < old_med * 0.6, (new_med, old_med)
    print(f"  [OK] median error {new_med:.0f}px vs previous {old_med:.0f}px at 80px noise")


def test_collinear_returns_none():
    scr = np.array(_grid_points(SW, SH, 1, 5), dtype=np.float64)  # one row
    assert fit_gaze_affine(_to_hit(scr), scr) is None
    print("  [OK] collinear targets -> None")


def test_too_few_or_mismatched_returns_none():
    scr = np.array([[0, 0], [100, 0]], dtype=np.float64)
    assert fit_gaze_affine(_to_hit(scr), scr) is None
    scr3 = np.array(_grid_points(SW, SH, 2, 2), dtype=np.float64)
    assert fit_gaze_affine(_to_hit(scr3)[:3], scr3) is None
    print("  [OK] <3 points or mismatched lengths -> None")


# ── GazeWizard end to end (fake clock, simulated ptgaze) ─────────────────────

class _Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def test_wizard_end_to_end_saves_accurate_model():
    clock = _Clock()
    store = MagicMock()
    smoother = MagicMock()
    with patch.object(wizard_mod.time, "monotonic", clock):
        wiz = GazeWizard(store, face_id=7, smoother=smoother, sw=SW, sh=SH, rows=3, cols=3)
        face = SimpleNamespace()
        state = None
        for _ in range(20000):
            # current calibration dot -> simulated noisy ptgaze hit
            idx = min(wiz._pt_idx, len(wiz._pts) - 1)
            hit = tuple(_noisy_hits(np.array([wiz._pts[idx]], dtype=np.float64), 40)[0])
            # during tune, pretend smoothed gaze sits on the tune dot
            tx, ty = wiz._tune_pts[min(wiz._tune_idx, len(wiz._tune_pts) - 1)]
            state = wiz.feed([(face, hit)], tx + RNG.normal(0, 5), ty + RNG.normal(0, 5))
            if state.done:
                break
            clock.t += 1 / 30
    assert state is not None and state.done, state
    assert store.save_gaze_model.called
    face_id, M = store.save_gaze_model.call_args[0]
    assert face_id == 7 and M.shape == (2, 3)
    err = _screen_error(M)
    assert err < 40, err
    assert smoother.tune_from_variance.called
    print(f"  [OK] wizard completes, saves model with {err:.1f}px mean error, tunes smoother")


TESTS = [
    test_exact_recovery_without_noise,
    test_robust_to_one_bad_dot,
    test_beats_previous_ransac_3px,
    test_collinear_returns_none,
    test_too_few_or_mismatched_returns_none,
    test_wizard_end_to_end_saves_accurate_model,
]


if __name__ == "__main__":
    print("\nGaze Calibration Fit Tests\n")
    passed = 0
    for t in TESTS:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{passed}/{len(TESTS)} tests passed")
    sys.exit(0 if passed == len(TESTS) else 1)
