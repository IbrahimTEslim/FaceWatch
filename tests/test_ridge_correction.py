r"""
Tests for calibration/ridge_correction.py and calibration/eye_features.py.
Run from project root:
    venv\Scripts\python.exe tests\test_ridge_correction.py
"""
import os
import sys
import time
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "utils", "facewatch"))

from calibration.eye_features import extract_features, BlinkDetector, _SUBSET_INDICES
from calibration.ridge_correction import (
    Sample, RidgeCorrection, train_correction, apply_affine, MIN_DOTS,
)
from calibration.wizard import fit_gaze_affine, _grid_points

SW, SH = 1536, 960
D_REAL = 3 * len(_SUBSET_INDICES) + 3          # eyetrax feature length
_A = np.array([[0.031, 0.002], [-0.001, 0.028]])   # screen px -> hit cm
_B = np.array([-24.0, -3.0])
_POSE_BIAS = np.array([[1.8, 0.3, 0.0], [0.2, 1.5, 0.4]])  # cm of hit error per unit pose


def _targets(rows, cols):
    return np.array(_grid_points(SW, SH, rows, cols), dtype=np.float64)


def _frames(targets, rng, frames_per_dot=25, pose_bias=True, d=40, noise_cm=0.3):
    """Synthetic calibration frames. features[:3] = head pose; the rest is noise."""
    out = []
    for k, t in enumerate(targets):
        for _ in range(frames_per_dot):
            pose = rng.normal(0, 1, 3)
            hit = t @ _A.T + _B + rng.normal(0, noise_cm, 2)
            if pose_bias:
                hit = hit + _POSE_BIAS @ pose
            feats = np.concatenate([pose + rng.normal(0, 0.05, 3), rng.normal(0, 1, d - 3)])
            out.append(Sample(dot=k, target=t, hit=hit, features=feats))
    return out


def _final_affine(samples):
    dots = sorted({s.dot for s in samples})
    hits = np.array([np.median([s.hit for s in samples if s.dot == k], axis=0) for k in dots])
    tgts = np.array([next(s.target for s in samples if s.dot == k) for k in dots])
    return fit_gaze_affine(hits, tgts)


def _err(samples, M, model=None):
    errs = []
    for s in samples:
        p = apply_affine(M, s.hit)[0]
        if model is not None:
            p = p + model.predict(s.features)
        errs.append(np.linalg.norm(p - s.target))
    return float(np.median(errs))


# ── ridge correction ─────────────────────────────────────────────────────────

def test_learnable_bias_is_accepted_and_generalises():
    rng = np.random.default_rng(0)
    train = _frames(_targets(3, 3), rng)
    M = _final_affine(train)
    model, rep = train_correction(train, fit_gaze_affine, M)
    assert rep.accepted and model is not None, rep
    assert rep.corrected_err_px < 0.6 * rep.affine_err_px, rep

    # fresh frames at screen positions never used for calibration
    test = _frames(_targets(4, 5) + 17.0, np.random.default_rng(1))
    e_aff, e_cor = _err(test, M), _err(test, M, model)
    assert e_cor < 0.6 * e_aff, (e_aff, e_cor)
    print(f"  [OK] learnable bias: held-out {rep.affine_err_px:.0f} -> {rep.corrected_err_px:.0f}px; "
          f"new points {e_aff:.0f} -> {e_cor:.0f}px (alpha={rep.alpha:g})")


def test_uninformative_features_are_rejected():
    rng = np.random.default_rng(2)
    train = _frames(_targets(3, 3), rng, pose_bias=False)
    model, rep = train_correction(train, fit_gaze_affine, _final_affine(train))
    assert model is None and not rep.accepted, rep
    assert rep.affine_err_px is not None and rep.corrected_err_px is not None
    print(f"  [OK] uninformative features rejected (affine {rep.affine_err_px:.0f}px, "
          f"ridge {rep.corrected_err_px:.0f}px)")


def test_too_few_dots_rejected():
    rng = np.random.default_rng(3)
    train = _frames(_targets(2, 2), rng)
    model, rep = train_correction(train, fit_gaze_affine, _final_affine(train))
    assert model is None and not rep.accepted and str(MIN_DOTS) in rep.reason
    print(f"  [OK] fewer than {MIN_DOTS} dots -> no correction ({rep.reason})")


def test_dots_with_too_few_frames_are_ignored():
    rng = np.random.default_rng(4)
    train = _frames(_targets(3, 3), rng, frames_per_dot=3)
    model, rep = train_correction(train, fit_gaze_affine, _final_affine(train))
    assert model is None and rep.n_dots == 0
    print("  [OK] dots with < 5 usable frames are ignored")


def test_serialisation_roundtrip_without_pickle():
    rng = np.random.default_rng(5)
    train = _frames(_targets(3, 3), rng)
    model, _ = train_correction(train, fit_gaze_affine, _final_affine(train))
    blob = model.to_bytes()
    back = RidgeCorrection.from_bytes(blob)   # np.load(allow_pickle=False)
    f = train[0].features
    assert np.allclose(model.predict(f), back.predict(f)) and back.alpha == model.alpha
    print(f"  [OK] to_bytes/from_bytes roundtrip ({len(blob)} bytes, no pickle)")


def test_training_cost_with_real_feature_size():
    rng = np.random.default_rng(6)
    targets = np.array([[rng.uniform(100, SW - 100), rng.uniform(100, SH - 100)] for _ in range(69)])
    train = _frames(targets, rng, frames_per_dot=40, d=D_REAL)
    t0 = time.perf_counter()
    model, rep = train_correction(train, fit_gaze_affine, _final_affine(train))
    dt = time.perf_counter() - t0
    assert rep.accepted and dt < 2.5, (dt, rep)
    print(f"  [OK] 69 dots x 40 frames x {D_REAL} features trains in {dt:.2f}s")


# ── eye features ─────────────────────────────────────────────────────────────

def _landmarks(shift=0.0):
    rng = np.random.default_rng(7)
    pts = rng.uniform(0.3, 0.7, (478, 3))
    pts[33] = [0.40, 0.45, 0.0]; pts[263] = [0.60, 0.45, 0.0]; pts[10] = [0.50, 0.20, 0.0]
    pts[:, 0] += shift
    return [SimpleNamespace(x=p[0], y=p[1], z=p[2]) for p in pts]


def test_features_shape_and_translation_invariance():
    f1, _ = extract_features(_landmarks())
    f2, _ = extract_features(_landmarks(shift=0.05))   # same face moved sideways
    assert f1.shape == (D_REAL,) and np.all(np.isfinite(f1))
    assert np.allclose(f1, f2, atol=1e-5)
    assert extract_features([])[0] is None
    print(f"  [OK] {D_REAL}-d features, invariant to face translation; empty -> None")


def test_blink_detector():
    lms = _landmarks()
    def set_lids(gap):
        for top, bot, x in ((159, 145, 0.43), (386, 374, 0.57)):
            lms[top] = SimpleNamespace(x=x, y=0.45 - gap, z=0.0)
            lms[bot] = SimpleNamespace(x=x, y=0.45 + gap, z=0.0)
    bd = BlinkDetector()
    set_lids(0.012)
    open_states = [bd.is_blinking(lms) for _ in range(30)]
    set_lids(0.002)
    assert not any(open_states[15:]) and bd.is_blinking(lms)
    print("  [OK] BlinkDetector: open eyes not blinking, closed lids detected")


TESTS = [
    test_learnable_bias_is_accepted_and_generalises,
    test_uninformative_features_are_rejected,
    test_too_few_dots_rejected,
    test_dots_with_too_few_frames_are_ignored,
    test_serialisation_roundtrip_without_pickle,
    test_training_cost_with_real_feature_size,
    test_features_shape_and_translation_invariance,
    test_blink_detector,
]


if __name__ == "__main__":
    print("\nRidge Correction Tests\n")
    passed = 0
    for t in TESTS:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{passed}/{len(TESTS)} tests passed")
    sys.exit(0 if passed == len(TESTS) else 1)
