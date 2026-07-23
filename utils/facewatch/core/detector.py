import threading

import mediapipe as mp
import numpy as np
from mediapipe.tasks.python.vision import FaceLandmarker, FaceLandmarkerOptions, RunningMode
from mediapipe.tasks.python.vision import FaceLandmarkerResult

from storage.config_store import ConfigStore


class FaceDetector:
    def __init__(self, config: ConfigStore):
        self._lock = threading.Lock()
        self._latest: FaceLandmarkerResult | None = None
        self._timestamp_ms: int = 0

        model_path = config.get("face_landmarker_model_path")
        num_faces  = config.get("max_faces")
        options = FaceLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=model_path),
            running_mode=RunningMode.LIVE_STREAM,
            num_faces=num_faces,
            output_face_blendshapes=True,
            output_facial_transformation_matrixes=True,
            result_callback=self._on_result,
        )
        self._landmarker = FaceLandmarker.create_from_options(options)

    def detect(self, frame_bgr: np.ndarray) -> None:
        self._timestamp_ms += 33
        rgb = frame_bgr[:, :, ::-1]
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))
        self._landmarker.detect_async(mp_image, self._timestamp_ms)

    @property
    def latest_result(self) -> FaceLandmarkerResult | None:
        with self._lock:
            return self._latest

    def close(self) -> None:
        self._landmarker.close()

    def _on_result(self, result: FaceLandmarkerResult, output_image: mp.Image, timestamp_ms: int) -> None:
        with self._lock:
            self._latest = result
