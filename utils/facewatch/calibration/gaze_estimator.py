import pathlib

import numpy as np

# Same checkpoint as ptgaze.utils.download_mpiifacegaze_model()
_MPIIFACEGAZE_REPO = "hysts/ptgaze-mpiifacegaze-resnet-simple"
_MPIIFACEGAZE_FILE = "model.safetensors"


def mpiifacegaze_checkpoint() -> pathlib.Path:
    """
    Path to the ptgaze MPIIFaceGaze checkpoint. Uses the local Hugging Face
    cache when present; only downloads (contacts huggingface.co) on first run.
    ptgaze's own download_mpiifacegaze_model() checks the Hub on every start,
    which sent a network request at each FaceWatch launch.
    """
    from huggingface_hub import hf_hub_download
    try:
        return pathlib.Path(hf_hub_download(_MPIIFACEGAZE_REPO, _MPIIFACEGAZE_FILE, local_files_only=True))
    except Exception:  # not cached yet (error class differs across huggingface_hub versions)
        return pathlib.Path(hf_hub_download(_MPIIFACEGAZE_REPO, _MPIIFACEGAZE_FILE))


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
        import ptgaze
        from omegaconf import OmegaConf
        from ptgaze.gaze_estimator import GazeEstimator
        from ptgaze.utils import download_mediapipe_face_landmarker, expanduser_all
        from ptgaze.config_schema import AppConfig

        package_root = pathlib.Path(ptgaze.__file__).parent.resolve()
        cfg = OmegaConf.load(package_root / "data/configs/mpiifacegaze.yaml")
        cfg = OmegaConf.merge(OmegaConf.structured(AppConfig), cfg)
        cfg.PACKAGE_ROOT = package_root.as_posix()
        cfg.face_detector.mode = "mediapipe"
        cfg.gaze_estimator.use_dummy_camera_params = True
        cfg.gaze_estimator.dummy_camera_size = [int(frame_w), int(frame_h)]
        cfg.gaze_estimator.checkpoint = mpiifacegaze_checkpoint().as_posix()
        download_mediapipe_face_landmarker()   # downloads only if the file is missing
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

    # ptgaze's 3D face model uses the 468-point mesh; FaceLandmarker appends 10 iris points.
    _PTGAZE_NUM_LANDMARKS = 468

    def estimate_from_landmarks(self, frame: np.ndarray, landmark_lists: list) -> list[tuple]:
        """
        Same as estimate(), but reuses MediaPipe FaceLandmarker landmarks the
        engine's FaceDetector already computed for this frame instead of running
        ptgaze's own detector — one landmark pass per frame instead of two.
        Builds ptgaze Face objects exactly as ptgaze's mediapipe mode does
        (first 468 points in pixels, bbox from their extent).
        Returns [(face, hit), ...] in the order of landmark_lists.
        """
        from ptgaze.common import Face

        h, w = frame.shape[:2]
        results = []
        for lms in landmark_lists:
            if len(lms) < self._PTGAZE_NUM_LANDMARKS:
                results.append((None, None))
                continue
            pts = np.array([(p.x * w, p.y * h) for p in lms[: self._PTGAZE_NUM_LANDMARKS]],
                           dtype=np.float64)
            bbox = np.round(np.vstack([pts.min(axis=0), pts.max(axis=0)])).astype(np.int32)
            face = Face(bbox, pts)
            self._estimator.estimate_gaze(frame, face)
            results.append((face, ray_hit(face)))
        return results
