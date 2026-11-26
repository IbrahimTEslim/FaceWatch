"""
Head-pose-normalised eye landmark features and EAR blink detection, ported from
eyetrax (github.com/ck-zhang/EyeTrax). Used by the optional ridge gaze correction
(calibration/ridge_correction.py).
"""
from collections import deque

import numpy as np

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

    return features, False  # blink handled separately by BlinkDetector


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
