import time

import mediapipe as mp
import numpy as np
from mediapipe.tasks.python.vision import FaceLandmarker, FaceLandmarkerOptions, RunningMode
from mediapipe.tasks.python.vision import FaceLandmarkerResult

from storage.config_store import ConfigStore


class FaceDetector:
    def __init__(self, config: ConfigStore):
        self._last_ts_ms: int = 0

        model_path = config.get("face_landmarker_model_path")
        num_faces  = config.get("max_faces")
        options = FaceLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=model_path),
            running_mode=RunningMode.VIDEO,
            num_faces=num_faces,
            output_face_blendshapes=True,
            output_facial_transformation_matrixes=True,
        )
        self._landmarker = FaceLandmarker.create_from_options(options)

    def detect(self, frame_bgr: np.ndarray) -> FaceLandmarkerResult | None:
        rgb = frame_bgr[:, :, ::-1]
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))
        ts_ms = int(time.time() * 1000)
        if ts_ms <= self._last_ts_ms:
            ts_ms = self._last_ts_ms + 1
        self._last_ts_ms = ts_ms
        return self._landmarker.detect_for_video(mp_image, ts_ms)

    def close(self) -> None:
        self._landmarker.close()
