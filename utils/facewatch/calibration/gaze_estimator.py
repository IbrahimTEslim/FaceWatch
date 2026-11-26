import numpy as np


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

    def __init__(self, frame_w: int, frame_h: int):
        """
        frame_w/frame_h: actual camera frame size. ptgaze's dummy camera model
        uses focal = frame_w and principal point = frame centre, so a wrong size
        skews head pose and the gaze ray.
        """
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
        cfg.gaze_estimator.dummy_camera_size = [int(frame_w), int(frame_h)]
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
