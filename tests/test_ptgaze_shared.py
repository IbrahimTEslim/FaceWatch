r"""
Tests for ptgaze reusing FaceDetector landmarks (setting ptgaze_shared_landmarks).
Run from project root:
    venv\Scripts\python.exe tests\test_ptgaze_shared.py
"""
import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "utils", "facewatch"))

import engine


class _FakeEstimator:
    def __init__(self):
        self.own_calls = 0
        self.shared_calls = []

    def estimate(self, frame):
        self.own_calls += 1
        face = SimpleNamespace(bbox=np.array([[10, 10], [110, 110]]))
        return [(face, (1.0, 2.0))]

    def estimate_from_landmarks(self, frame, lists):
        self.shared_calls.append(list(lists))
        return [(None, None) if lm == "bad" else (SimpleNamespace(src=lm), (float(len(lm)), 0.0))
                for lm in lists]


def test_own_detection_path_unchanged():
    est = _FakeEstimator()
    out = engine._estimate_gaze(est, None, None, {5: [12, 12, 108, 108]}, {}, shared=False)
    assert est.own_calls == 1 and not est.shared_calls
    assert out[5][1] == (1.0, 2.0)
    print("  [OK] shared=False: ptgaze's own detection + IoU matching (unchanged)")


def test_shared_maps_through_mp_index():
    est = _FakeEstimator()
    result = SimpleNamespace(face_landmarks=["aa", "bbbb", "ccc"])
    out = engine._estimate_gaze(est, None, result, {7: [0, 0, 1, 1], 9: [0, 0, 1, 1]},
                                {7: 2, 9: 0}, shared=True)
    assert est.own_calls == 0
    assert est.shared_calls == [["aa", "ccc"]]          # only landmark sets that belong to tracks
    assert out[7][0].src == "ccc" and out[9][0].src == "aa"
    print("  [OK] shared=True: no second detector, results mapped by landmark index")


def test_shared_skips_bad_and_empty():
    est = _FakeEstimator()
    result = SimpleNamespace(face_landmarks=["bad", "ok"])
    out = engine._estimate_gaze(est, None, result, {}, {1: 0, 2: 1}, shared=True)
    assert 1 not in out and out[2][0].src == "ok"
    assert engine._estimate_gaze(est, None, None, {}, {1: 0}, shared=True) == {}
    assert engine._estimate_gaze(est, None, SimpleNamespace(face_landmarks=[]), {}, {}, shared=True) == {}
    print("  [OK] shared=True: unusable landmark sets and empty frames give no gaze")


def test_real_models_identical_gaze():
    """Same FaceLandmarker model on the same frame -> identical ptgaze result."""
    img_path = os.path.join(ROOT, "venv", "Lib", "site-packages", "matplotlib", "mpl-data",
                            "sample_data", "grace_hopper.jpg")
    if not os.path.exists(img_path):
        print("  [OK] (skipped: sample portrait not available)")
        return
    import cv2
    from core.detector import FaceDetector
    from calibration.gaze_estimator import PtgazeEstimator

    cwd = os.getcwd()
    os.chdir(ROOT)
    try:
        img = cv2.resize(cv2.imread(img_path), None, fx=0.55, fy=0.55)
        frame = np.zeros((480, 640, 3), np.uint8)
        h, w = min(480, img.shape[0]), min(640, img.shape[1])
        frame[:h, (640 - w) // 2:(640 - w) // 2 + w] = img[:h, :w]
        cfg = MagicMock()
        cfg.get.side_effect = lambda k: {"face_landmarker_model_path": "models/face_landmarker.task",
                                         "max_faces": 10}[k]
        det, pt = FaceDetector(cfg), PtgazeEstimator(640, 480)
        for _ in range(3):
            res = det.detect(frame)
            own = pt.estimate(frame)
        shared = pt.estimate_from_landmarks(frame, res.face_landmarks)
    finally:
        os.chdir(cwd)
    assert len(own) == len(shared) == 1
    (f1, h1), (f2, h2) = own[0], shared[0]
    assert np.allclose(f1.landmarks, f2.landmarks, atol=0.5)
    assert np.allclose(f1.gaze_vector, f2.gaze_vector, atol=1e-3) and np.allclose(h1, h2, atol=1e-2)
    print(f"  [OK] real models: shared-landmark gaze identical to ptgaze's own (hit {np.round(h2, 3)})")


def test_cached_checkpoint_needs_no_network():
    """FaceWatch claims to run fully offline; loading the cached gaze model must not hit the Hub."""
    import socket
    from huggingface_hub import hf_hub_download
    from calibration.gaze_estimator import mpiifacegaze_checkpoint, _MPIIFACEGAZE_REPO, _MPIIFACEGAZE_FILE
    try:
        hf_hub_download(_MPIIFACEGAZE_REPO, _MPIIFACEGAZE_FILE, local_files_only=True)
    except Exception:
        print("  [OK] (skipped: gaze model not cached on this machine)")
        return
    attempts = []
    orig = socket.socket.connect

    def blocked(self, addr):
        attempts.append(addr)
        raise OSError("network blocked by test")

    socket.socket.connect = blocked
    try:
        path = mpiifacegaze_checkpoint()
    finally:
        socket.socket.connect = orig
    assert path.exists() and not attempts, attempts
    print("  [OK] cached gaze model loads with zero network connections")


TESTS = [
    test_own_detection_path_unchanged,
    test_shared_maps_through_mp_index,
    test_shared_skips_bad_and_empty,
    test_real_models_identical_gaze,
    test_cached_checkpoint_needs_no_network,
]


if __name__ == "__main__":
    print("\nptgaze Shared Landmarks Tests\n")
    passed = 0
    for t in TESTS:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{passed}/{len(TESTS)} tests passed")
    sys.exit(0 if passed == len(TESTS) else 1)
