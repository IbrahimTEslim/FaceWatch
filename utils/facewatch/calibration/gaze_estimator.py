import pickle
from collections import deque
import time

import numpy as np
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

# Eye landmark indices (MediaPipe 478-point model with iris)
# Ported verbatim from eyetrax/constants.py
_LEFT_EYE_INDICES = [
    107,  66, 105,  63,  70,
     55,  65,  52,  53,  46,
    468, 469, 470, 471, 472,
    133,  33,
    173, 157, 158, 159, 160, 161, 246,
    155, 154, 153, 145, 144, 163,   7,
    243, 190,  56,  28,  27,  29,  30, 247,
    130,  25, 110,  24,  23,  22,  26, 112,
    244, 189, 221, 222, 223, 224, 225, 113,
    226,  31, 228, 229, 230, 231, 232, 233,
    193, 245, 128, 121, 120, 119, 118, 117,
    111,  35, 124, 143, 156,
]

_RIGHT_EYE_INDICES = [
    336, 296, 334, 293, 300,
    285, 295, 282, 283, 276,
    473, 476, 475, 474, 477,
    362, 263,
    398, 384, 385, 386, 387, 388, 466,
    382, 381, 380, 374, 373, 390, 249,
    463, 414, 286, 258, 257, 259, 260, 467,
    359, 255, 339, 254, 253, 252, 256, 341,
    464, 413, 441, 442, 443, 444, 445, 342,
    446, 261, 448, 449, 450, 451, 452, 453,
    417, 465, 357, 350, 349, 348, 347, 346,
    340, 265, 353, 372, 383,
]

_MUTUAL_INDICES = [
      4,   # Nose
     10,   # Very top
    151,   # Forehead
      9,   # Between brow
    152,   # Chin
    234,   # Very left
    454,   # Very right
     58,   # Left jaw
    288,   # Right jaw
]

_SUBSET_INDICES = _LEFT_EYE_INDICES + _RIGHT_EYE_INDICES + _MUTUAL_INDICES

# Blink detection landmark indices
_L_INNER, _L_OUTER = 133, 33
_L_TOP,   _L_BOTTOM = 159, 145
_R_INNER, _R_OUTER = 362, 263
_R_TOP,   _R_BOTTOM = 386, 374

_EAR_HISTORY_LEN   = 50
_BLINK_RATIO       = 0.8
_MIN_EAR_HISTORY   = 15


def extract_features(landmarks: list) -> tuple[np.ndarray | None, bool]:
    """
    Takes MediaPipe landmarks (already extracted by our detector).
    Returns (feature_vector, blink_detected).
    feature_vector is None if landmarks are insufficient.

    Ported verbatim from eyetrax GazeEstimator.extract_features(),
    minus the camera/MediaPipe detection (we already have landmarks).
    """
    if not landmarks or len(landmarks) <= max(_SUBSET_INDICES):
        return None, False

    all_points = np.array(
        [(lm.x, lm.y, lm.z) for lm in landmarks], dtype=np.float32
    )

    left_corner  = all_points[33]
    right_corner = all_points[263]
    top_of_head  = all_points[10]

    eye_center     = (left_corner + right_corner) / 2.0
    shifted_points = all_points - eye_center

    x_axis  = right_corner - left_corner
    x_axis /= np.linalg.norm(x_axis) + 1e-9

    y_approx  = top_of_head - eye_center
    y_approx /= np.linalg.norm(y_approx) + 1e-9
    y_axis    = y_approx - np.dot(y_approx, x_axis) * x_axis
    y_axis   /= np.linalg.norm(y_axis) + 1e-9

    z_axis  = np.cross(x_axis, y_axis)
    z_axis /= np.linalg.norm(z_axis) + 1e-9

    R              = np.column_stack((x_axis, y_axis, z_axis))
    rotated_points = (R.T @ shifted_points.T).T

    left_corner_rot  = R.T @ (left_corner  - eye_center)
    right_corner_rot = R.T @ (right_corner - eye_center)
    inter_eye_dist   = np.linalg.norm(right_corner_rot - left_corner_rot)
    if inter_eye_dist > 1e-7:
        rotated_points /= inter_eye_dist

    eye_landmarks = rotated_points[_SUBSET_INDICES]
    features      = eye_landmarks.flatten()

    yaw   = np.arctan2(R[1, 0], R[0, 0])
    pitch = np.arctan2(-R[2, 0], np.sqrt(R[2, 1] ** 2 + R[2, 2] ** 2))
    roll  = np.arctan2(R[2, 1], R[2, 2])
    features = np.concatenate([features, [yaw, pitch, roll]])

    return features, False  # blink handled separately by GazeModel


def compute_ear(landmarks: list) -> float:
    """Eye aspect ratio averaged across both eyes."""
    lm = landmarks
    l_inner = np.array([lm[_L_INNER].x, lm[_L_INNER].y])
    l_outer = np.array([lm[_L_OUTER].x, lm[_L_OUTER].y])
    l_top   = np.array([lm[_L_TOP].x,   lm[_L_TOP].y])
    l_bot   = np.array([lm[_L_BOTTOM].x, lm[_L_BOTTOM].y])

    r_inner = np.array([lm[_R_INNER].x, lm[_R_INNER].y])
    r_outer = np.array([lm[_R_OUTER].x, lm[_R_OUTER].y])
    r_top   = np.array([lm[_R_TOP].x,   lm[_R_TOP].y])
    r_bot   = np.array([lm[_R_BOTTOM].x, lm[_R_BOTTOM].y])

    l_ear = np.linalg.norm(l_top - l_bot) / (np.linalg.norm(l_outer - l_inner) + 1e-9)
    r_ear = np.linalg.norm(r_top - r_bot) / (np.linalg.norm(r_outer - r_inner) + 1e-9)
    return (l_ear + r_ear) / 2.0


class GazeModel:
    """
    Ridge regression gaze model with StandardScaler.
    Ported verbatim from eyetrax BaseModel + RidgeModel.
    Serialized via pickle for DB storage.
    """

    def __init__(self, alpha: float = 1.0):
        self._scaler = StandardScaler()
        self._model  = Ridge(alpha=alpha)
        self._trained = False

    def train(self, X: np.ndarray, y: np.ndarray) -> None:
        Xs = self._scaler.fit_transform(X)
        self._model.fit(Xs, y)
        self._trained = True

    def predict(self, features: np.ndarray) -> tuple[float, float]:
        Xs  = self._scaler.transform(features.reshape(1, -1))
        out = self._model.predict(Xs)[0]
        return float(out[0]), float(out[1])

    @property
    def is_trained(self) -> bool:
        return self._trained


class BlinkDetector:
    """
    Stateful per-face blink detector using EAR history.
    Ported verbatim from eyetrax GazeEstimator blink logic.
    """

    def __init__(self):
        self._ear_history: deque[float] = deque(maxlen=_EAR_HISTORY_LEN)

    def is_blinking(self, landmarks: list) -> bool:
        if not landmarks or len(landmarks) <= max(_L_BOTTOM, _R_BOTTOM):
            return False
        ear = compute_ear(landmarks)
        self._ear_history.append(ear)
        if len(self._ear_history) >= _MIN_EAR_HISTORY:
            thr = float(np.mean(self._ear_history)) * _BLINK_RATIO
        else:
            thr = 0.2
        return ear < thr


def ray_hit(face) -> tuple[float, float] | None:
    """Intersect ptgaze gaze ray with Z=0 plane. Returns (x_cm, y_cm) or None."""
    fc = face.center * 100.0
    gv = face.gaze_vector
    if abs(gv[2]) < 1e-6 or gv[2] > 0:
        return None
    t = -fc[2] / gv[2]
    return (fc[0] + t * gv[0], fc[1] + t * gv[1])


class PtgazeEstimator:
    """
    Wraps ptgaze GazeEstimator for full-frame gaze ray estimation.
    Initialized once at engine startup; shared across all GazeTracker instances.
    estimate(frame) returns [(face, hit), ...] for all detected faces,
    where hit is (x_cm, y_cm) or None if the ray doesn't intersect Z=0.
    """

    def __init__(self):
        import pathlib
        import ptgaze
        from omegaconf import OmegaConf
        from ptgaze.gaze_estimator import GazeEstimator
        from ptgaze.utils import (
            download_mpiifacegaze_model,
            download_mediapipe_face_landmarker,
            expanduser_all,
        )
        from ptgaze.config_schema import AppConfig

        package_root = pathlib.Path(ptgaze.__file__).parent.resolve()
        cfg = OmegaConf.load(package_root / "data/configs/mpiifacegaze.yaml")
        cfg = OmegaConf.merge(OmegaConf.structured(AppConfig), cfg)
        cfg.PACKAGE_ROOT = package_root.as_posix()
        cfg.face_detector.mode = "mediapipe"
        cfg.gaze_estimator.use_dummy_camera_params = True
        cfg.gaze_estimator.dummy_camera_size = [640, 480]
        cfg.gaze_estimator.checkpoint = download_mpiifacegaze_model().as_posix()
        download_mediapipe_face_landmarker()
        expanduser_all(cfg)
        OmegaConf.set_readonly(cfg, True)
        self._estimator = GazeEstimator(cfg)

    def estimate(self, frame: np.ndarray) -> list[tuple]:
        """Returns [(face, hit), ...] for all faces found in frame."""
        faces = self._estimator.detect_faces(frame)
        results = []
        for face in faces:
            self._estimator.estimate_gaze(frame, face)
            results.append((face, ray_hit(face)))
        return results
