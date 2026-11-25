"""
Tests for calibration/smoother.py (GazeSmoother).
Run from project root:
    python.exe tests\test_gaze_smoother.py
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "utils", "facewatch"))

from calibration.smoother import GazeSmoother, _make_kalman


def test_first_output_equals_measurement():
    s = GazeSmoother()
    assert s.step(812.0, 344.0) == (812.0, 344.0)
    print("  [OK] first output equals the first measurement")


def test_constant_input_stays_constant():
    s = GazeSmoother()
    s.tune_from_variance(900.0, 900.0)
    for _ in range(50):
        x, y = s.step(400.0, 300.0)
    assert abs(x - 400.0) < 1e-3 and abs(y - 300.0) < 1e-3
    print("  [OK] constant input converges to itself")


def test_origin_start_does_not_reinitialise():
    """Previously 'not np.any(statePost)' re-initialised whenever state was (0,0,0,0)."""
    s = GazeSmoother(ema_alpha=0.0)
    s.tune_from_variance(3600.0, 3600.0)
    s.step(0.0, 0.0)
    x, _ = s.step(100.0, 0.0)
    assert 0.0 < x < 100.0, x  # smoothed, not snapped to the new measurement
    print(f"  [OK] starting at (0,0) still smooths the next step (x={x:.1f})")


def test_less_jitter_than_raw_measurements_when_tuned():
    rng = np.random.default_rng(3)
    s = GazeSmoother()
    s.tune_from_variance(3600.0, 3600.0)
    outs = [s.step(500 + rng.normal(0, 60), 300 + rng.normal(0, 60))[0] for _ in range(400)]
    jitter = float(np.std(outs[50:]))
    assert jitter < 45, jitter  # raw noise is 60 px
    print(f"  [OK] tuned smoother reduces 60px noise to {jitter:.1f}px")


def test_corrected_output_has_less_jitter_than_prediction():
    """Regression guard for returning the Kalman posterior instead of the prior."""
    rng = np.random.default_rng(4)
    zs = [(500 + rng.normal(0, 60), 300 + rng.normal(0, 60)) for _ in range(400)]

    s = GazeSmoother(ema_alpha=0.0)
    ours = [s.step(*z)[0] for z in zs]

    kf = _make_kalman()
    kf.statePre[:2] = kf.statePost[:2] = np.array([[zs[0][0]], [zs[0][1]]], np.float32)
    prior = []
    for z in zs:
        prior.append(float(kf.predict()[0, 0]))
        kf.correct(np.array([[z[0]], [z[1]]], np.float32))

    assert np.std(ours[50:]) < np.std(prior[50:])
    print(f"  [OK] posterior jitter {np.std(ours[50:]):.1f}px < prior jitter {np.std(prior[50:]):.1f}px")


def test_ema_alpha_is_clamped():
    s = GazeSmoother()
    s.ema_alpha = 1.0
    assert s.ema_alpha == GazeSmoother.MAX_EMA_ALPHA
    s.ema_alpha = -0.3
    assert s.ema_alpha == 0.0
    assert GazeSmoother(ema_alpha=5).ema_alpha == GazeSmoother.MAX_EMA_ALPHA
    print("  [OK] ema_alpha clamped to [0, 0.95]")


def test_higher_smoothing_is_steadier():
    def jitter(alpha):
        rng = np.random.default_rng(5)
        s = GazeSmoother(ema_alpha=alpha)
        s.tune_from_variance(3600.0, 3600.0)
        outs = [s.step(500 + rng.normal(0, 60), 300)[0] for _ in range(400)]
        return float(np.std(outs[50:]))
    j0, j5, j9 = jitter(0.0), jitter(0.5), jitter(0.9)
    assert j0 > j5 > j9, (j0, j5, j9)
    print(f"  [OK] jitter falls as smoothing rises (0: {j0:.1f}, 0.5: {j5:.1f}, 0.9: {j9:.1f} px)")


def test_gaze_tracker_applies_setting_live():
    from unittest.mock import MagicMock
    from analysis.gaze import GazeTracker
    values = {"gaze_alert_sec": 10, "gaze_return_sec": 3, "gaze_edge_margin_x_px": 0,
              "gaze_edge_margin_y_px": 0, "gaze_smoothing": 0.25}
    cfg = MagicMock()
    cfg.get.side_effect = lambda k: values[k]
    cal = MagicMock()
    cal.load_gaze_model.return_value = np.array([[1.0, 0, 0], [0, 1.0, 0]])
    smoother = GazeSmoother()
    t = GazeTracker(1920, 1080, smoother=smoother)
    t.update((100.0, 100.0), 0.03, cfg, cal, 1)
    assert smoother.ema_alpha == 0.25
    values["gaze_smoothing"] = 0.7   # user changes the setting
    t.update((100.0, 100.0), 0.03, cfg, cal, 1)
    assert smoother.ema_alpha == 0.7
    print("  [OK] GazeTracker applies gaze_smoothing changes on the next frame")


TESTS = [
    test_first_output_equals_measurement,
    test_constant_input_stays_constant,
    test_origin_start_does_not_reinitialise,
    test_less_jitter_than_raw_measurements_when_tuned,
    test_corrected_output_has_less_jitter_than_prediction,
    test_ema_alpha_is_clamped,
    test_higher_smoothing_is_steadier,
    test_gaze_tracker_applies_setting_live,
]


if __name__ == "__main__":
    print("\nGaze Smoother Tests\n")
    passed = 0
    for t in TESTS:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{passed}/{len(TESTS)} tests passed")
    sys.exit(0 if passed == len(TESTS) else 1)
