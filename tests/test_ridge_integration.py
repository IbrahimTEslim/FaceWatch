r"""
Integration tests for the optional ridge gaze correction:
GazeWizard (training, saving/rejecting, held-out tune check) and GazeTracker
(runtime application, setting gate, clamp, blink hold).

Landmark feature extraction is replaced by a stand-in that carries a known
head pose, so the expected behaviour is known exactly.
Run from project root:
    venv\Scripts\python.exe tests\test_ridge_integration.py
"""
import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "utils", "facewatch"))

from analysis import gaze as gaze_mod
from analysis.gaze import GazeTracker
from calibration import wizard as wizard_mod
from calibration.wizard import GazeWizard, _Phase
from calibration.ridge_correction import RidgeCorrection

SW, SH = 1536, 960
_A = np.array([[0.031, 0.002], [-0.001, 0.028]])
_B = np.array([-24.0, -3.0])
_POSE_BIAS = np.array([[1.8, 0.3, 0.0], [0.2, 1.5, 0.4]])


class _FakeBlink:
    def is_blinking(self, lms):
        return bool(getattr(lms, "blink", False))


def _fake_features(lms):
    return (getattr(lms, "feats", None), False)


def _frame(target, rng, pose_bias=True, blink=False):
    pose = rng.normal(0, 1, 3)
    hit = np.asarray(target) @ _A.T + _B + rng.normal(0, 0.3, 2)
    if pose_bias:
        hit = hit + _POSE_BIAS @ pose
    feats = np.concatenate([pose + rng.normal(0, 0.05, 3), rng.normal(0, 1, 37)])
    return tuple(hit), SimpleNamespace(feats=feats, blink=blink)


class _Clock:
    t = 1000.0

    def __call__(self):
        return self.t


def _run_wizard(ridge_enabled, pose_bias=True, seed=0, adaptive=0, states=None):
    rng = np.random.default_rng(seed)
    clock, store = _Clock(), MagicMock()
    with patch.object(wizard_mod.time, "monotonic", clock), \
         patch.object(wizard_mod, "extract_features", _fake_features), \
         patch.object(wizard_mod, "BlinkDetector", _FakeBlink):
        wiz = GazeWizard(store, face_id=7, smoother=MagicMock(), sw=SW, sh=SH,
                         rows=3, cols=3, ridge_enabled=ridge_enabled, adaptive_points=adaptive)
        state = None
        for _ in range(40000):
            if wiz._phase is _Phase.TRAINING_CORRECTION:
                wiz._train_thread.join()
            in_tune = wiz._phase in (_Phase.TUNE_PULSE, _Phase.TUNE_CAPTURE)
            if in_tune:
                target = wiz._tune_pts[min(wiz._tune_idx, len(wiz._tune_pts) - 1)]
            else:
                target = wiz._pts[min(wiz._pt_idx, len(wiz._pts) - 1)]
            hit, lms = _frame(target, rng, pose_bias)
            state = wiz.feed([(object(), hit)], target[0], target[1], landmarks=lms)
            if states is not None:
                states.append((wiz._pt_idx, state, wiz.model_ready))
            if state.done:
                break
            clock.t += 1 / 30
    return wiz, store, state


# ── GazeWizard ───────────────────────────────────────────────────────────────

def test_wizard_trains_and_saves_correction():
    wiz, store, state = _run_wizard(ridge_enabled=True)
    assert state.done
    store.save_gaze_model.assert_called_once()
    store.save_gaze_correction.assert_called_once()
    fid, model, rep = store.save_gaze_correction.call_args[0]
    assert fid == 7 and isinstance(model, RidgeCorrection) and rep["accepted"]
    r = wiz.report
    assert r["correction"]["accepted"] and r["tune_corrected_err_px"] < r["tune_affine_err_px"]
    assert "corrected" in state.instruction
    print(f"  [OK] wizard saves correction; tune check {r['tune_affine_err_px']:.0f}px affine "
          f"-> {r['tune_corrected_err_px']:.0f}px corrected")


def test_wizard_rejects_useless_correction():
    wiz, store, state = _run_wizard(ridge_enabled=True, pose_bias=False, seed=1)
    assert state.done
    store.save_gaze_correction.assert_not_called()
    store.delete_gaze_correction.assert_called_once_with(7)
    assert wiz.report["correction"]["accepted"] is False
    assert "tune_corrected_err_px" not in wiz.report
    print(f"  [OK] useless correction rejected, old one deleted "
          f"({wiz.report['correction']['reason']})")


def test_wizard_disabled_removes_stale_correction():
    wiz, store, state = _run_wizard(ridge_enabled=False, seed=2)
    assert state.done
    store.save_gaze_correction.assert_not_called()
    store.delete_gaze_correction.assert_called_once_with(7)
    assert "correction" not in wiz.report and wiz.report["affine_saved"]
    assert "tune_affine_err_px" in wiz.report
    print("  [OK] correction disabled: affine only, stale correction removed")


def test_wizard_skips_blink_frames():
    rng = np.random.default_rng(3)
    with patch.object(wizard_mod, "extract_features", _fake_features), \
         patch.object(wizard_mod, "BlinkDetector", _FakeBlink):
        wiz = GazeWizard(MagicMock(), face_id=7, smoother=MagicMock(), sw=SW, sh=SH, ridge_enabled=True)
        hit, lms = _frame((100, 100), rng, blink=True)
        assert wiz._frame_features(lms) is None
        hit, lms = _frame((100, 100), rng, blink=False)
        assert wiz._frame_features(lms) is not None
        assert wiz._frame_features(None) is None
    print("  [OK] blink frames give no correction samples")


# ── Adaptive points ──────────────────────────────────────────────────────────

def test_blue_noise_points_fill_gaps():
    grid = wizard_mod._grid_points(SW, SH, 3, 3)
    rng = np.random.default_rng(0)
    pts = wizard_mod.blue_noise_points(SW, SH, 20, existing=grid, rng=rng)
    assert len(pts) == 20
    mx, my = int(SW * 0.08), int(SH * 0.08)
    assert all(mx <= x <= SW - mx and my <= y <= SH - my for x, y in pts)

    def min_gap(points):
        allp = np.array(grid + points, dtype=float)
        d = np.linalg.norm(allp[:, None] - allp[None], axis=-1)
        d[np.diag_indices(len(allp))] = np.inf
        return d.min()

    uniform = [(int(rng.integers(mx, SW - mx)), int(rng.integers(my, SH - my))) for _ in range(20)]
    assert min_gap(pts) > 2 * min_gap(uniform), (min_gap(pts), min_gap(uniform))
    assert wizard_mod.blue_noise_points(SW, SH, 0, existing=grid) == []
    print(f"  [OK] blue-noise points spread out (min gap {min_gap(pts):.0f}px vs "
          f"{min_gap(uniform):.0f}px uniform)")


def test_wizard_adaptive_points_refit_and_live_pointer():
    trace = []
    wiz, store, state = _run_wizard(ridge_enabled=True, adaptive=12, seed=4, states=trace)
    assert state.done and len(wiz._pts) == 21
    # affine saved after the grid (idx 9), after 10 extra points (idx 19), and at the end
    assert store.save_gaze_model.call_count == 3, store.save_gaze_model.call_count
    grid_states  = [s for _, s, _ in trace if s.instruction.startswith("Point ")]
    extra_states = [s for _, s, _ in trace if s.instruction.startswith("Extra point ")]
    assert grid_states and not any(s.show_gaze for s in grid_states)
    assert extra_states and all(s.show_gaze for s in extra_states)
    assert any("Extra point 1 of 12" in s.instruction for s in extra_states)
    assert any("Point 9 of 9" in s.instruction for s in grid_states)
    assert wiz.report["correction"]["n_dots"] == 21 and wiz.report["adaptive_points"] == 12
    print(f"  [OK] 12 adaptive points: refits after grid and every 10, live pointer, "
          f"correction validated on {wiz.report['correction']['n_dots']} dots")


# ── GazeTracker runtime ──────────────────────────────────────────────────────

class _Passthrough:
    ema_alpha = 0.0

    def step(self, sx, sy):
        return sx, sy


def _cfg(enabled):
    values = {"gaze_alert_sec": 10, "gaze_return_sec": 3, "gaze_edge_margin_x_px": 0,
              "gaze_edge_margin_y_px": 0, "gaze_smoothing": 0.0, "gaze_ridge_correction": enabled}
    cfg = MagicMock()
    cfg.get.side_effect = lambda k: values[k]
    return cfg


def _cal(correction):
    cal = MagicMock()
    cal.load_gaze_model.return_value = np.array([[1.0, 0, 0], [0, 1.0, 0]])
    cal.load_gaze_correction.return_value = correction
    return cal


def _const_correction(dx, dy, d=40):
    return RidgeCorrection(mean=np.zeros(d), scale=np.ones(d), coef=np.zeros((d, 2)),
                           intercept=np.array([dx, dy]), alpha=1.0)


def _lms(feats=None, blink=False):
    return SimpleNamespace(feats=np.zeros(40) if feats is None else feats, blink=blink)


def _tracker_update(tracker, cfg, cal, lms, hit=(700.0, 400.0)):
    with patch.object(gaze_mod, "extract_features", _fake_features):
        return tracker.update(hit, 0.03, cfg, cal, 1, landmarks=lms)


def _tracker():
    with patch.object(gaze_mod, "BlinkDetector", _FakeBlink):
        return GazeTracker(SW, SH, smoother=_Passthrough())


def test_tracker_applies_correction_only_when_enabled():
    cal = _cal(_const_correction(50.0, -20.0))
    off = _tracker_update(_tracker(), _cfg(False), cal, _lms())
    on = _tracker_update(_tracker(), _cfg(True), cal, _lms())
    assert (off.screen_x, off.screen_y, off.corrected) == (700.0, 400.0, False)
    assert (on.screen_x, on.screen_y, on.corrected) == (750.0, 380.0, True)
    print("  [OK] correction applied only when gaze_ridge_correction is on")


def test_tracker_without_correction_model_is_affine_only():
    st = _tracker_update(_tracker(), _cfg(True), _cal(None), _lms())
    assert (st.screen_x, st.screen_y, st.corrected) == (700.0, 400.0, False)
    print("  [OK] setting on but no stored correction -> affine only")


def test_tracker_clamps_large_correction():
    st = _tracker_update(_tracker(), _cfg(True), _cal(_const_correction(5000.0, 0.0)), _lms())
    limit = 0.30 * np.hypot(SW, SH)
    assert abs((st.screen_x - 700.0) - limit) < 1e-6, st.screen_x
    print(f"  [OK] correction clamped to {limit:.0f}px")


def test_tracker_holds_last_correction_on_blink():
    d = 40
    coef = np.zeros((d, 2)); coef[0, 0] = 10.0          # dx = 10 * feats[0]
    corr = RidgeCorrection(mean=np.zeros(d), scale=np.ones(d), coef=coef, intercept=np.zeros(2), alpha=1.0)
    t, cfg, cal = _tracker(), _cfg(True), _cal(corr)
    f1 = np.zeros(d); f1[0] = 3.0
    f2 = np.zeros(d); f2[0] = -8.0
    s1 = _tracker_update(t, cfg, cal, _lms(f1))
    s2 = _tracker_update(t, cfg, cal, _lms(f2, blink=True))
    s3 = _tracker_update(t, cfg, cal, None)
    assert s1.screen_x == 730.0 and s2.screen_x == 730.0 and s3.screen_x == 730.0
    print("  [OK] blink / missing landmarks hold the last correction")


def test_tracker_reset_model_reloads_correction():
    cal = _cal(_const_correction(50.0, 0.0))
    t, cfg = _tracker(), _cfg(True)
    _tracker_update(t, cfg, cal, _lms())
    cal.load_gaze_correction.return_value = _const_correction(-30.0, 0.0)
    assert _tracker_update(t, cfg, cal, _lms()).screen_x == 750.0   # cached
    t.reset_model()
    assert _tracker_update(t, cfg, cal, _lms()).screen_x == 670.0   # reloaded
    print("  [OK] reset_model() reloads the correction after recalibration")


TESTS = [
    test_wizard_trains_and_saves_correction,
    test_wizard_rejects_useless_correction,
    test_wizard_disabled_removes_stale_correction,
    test_wizard_skips_blink_frames,
    test_blue_noise_points_fill_gaps,
    test_wizard_adaptive_points_refit_and_live_pointer,
    test_tracker_applies_correction_only_when_enabled,
    test_tracker_without_correction_model_is_affine_only,
    test_tracker_clamps_large_correction,
    test_tracker_holds_last_correction_on_blink,
    test_tracker_reset_model_reloads_correction,
]


if __name__ == "__main__":
    print("\nRidge Correction Integration Tests\n")
    passed = 0
    for t in TESTS:
        try:
            t()
            passed += 1
        except Exception as e:
            import traceback; traceback.print_exc()
            print(f"  [FAIL] {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{passed}/{len(TESTS)} tests passed")
    sys.exit(0 if passed == len(TESTS) else 1)
