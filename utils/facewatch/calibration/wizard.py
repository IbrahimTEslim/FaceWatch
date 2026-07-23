from dataclasses import dataclass, field
from calibration.store import CalibrationStore
from demographics.face_width import DEFAULT_FACE_WIDTH_CM

# Landmark indices for cheekbones (same as distance.py)
_LEFT_CHEEK  = 234
_RIGHT_CHEEK = 454

# Iris indices (same as gaze.py)
_L_IRIS = 468
_R_IRIS = 473

_SAMPLES_NEEDED = 30


@dataclass
class WizardState:
    step: int        # 1=gaze center, 2=focal length, 3=done
    samples: int
    needed: int
    instruction: str
    done: bool


class CalibrationWizard:
    """
    Step 1 — Look straight at screen center. Collects gaze_center_h/v.
    Step 2 — Sit at your normal distance and type it in. Collects focal_length_px.
    Step 3 — Done.

    Call feed(landmarks, frame_w) each frame.
    Call set_distance_cm(value) once the user has typed their distance.
    """

    def __init__(self, store: CalibrationStore, face_width_cm: float = DEFAULT_FACE_WIDTH_CM):
        self._store = store
        self._face_width_cm = face_width_cm
        self._step = 1
        self._h_samples: list[float] = []
        self._v_samples: list[float] = []
        self._px_samples: list[float] = []
        self._distance_cm: float | None = None

    def set_distance_cm(self, distance_cm: float) -> None:
        self._distance_cm = distance_cm

    def feed(self, landmarks: list, frame_w: int) -> WizardState:
        if self._step == 1:
            return self._collect_gaze_center(landmarks)
        if self._step == 2:
            return self._collect_focal_length(landmarks, frame_w)
        return self._done_state()

    # ------------------------------------------------------------------

    def _collect_gaze_center(self, landmarks: list) -> WizardState:
        if landmarks and len(landmarks) > _R_IRIS:
            h = (landmarks[_L_IRIS].x + landmarks[_R_IRIS].x) / 2.0
            v = (landmarks[_L_IRIS].y + landmarks[_R_IRIS].y) / 2.0
            self._h_samples.append(h)
            self._v_samples.append(v)

        if len(self._h_samples) >= _SAMPLES_NEEDED:
            self._store.set("gaze_center_h", sum(self._h_samples) / len(self._h_samples))
            self._store.set("gaze_center_v", sum(self._v_samples) / len(self._v_samples))
            self._step = 2

        return WizardState(
            step=1,
            samples=len(self._h_samples),
            needed=_SAMPLES_NEEDED,
            instruction="Look straight at the center of your screen.",
            done=False,
        )

    def _collect_focal_length(self, landmarks: list, frame_w: int) -> WizardState:
        if self._distance_cm is None:
            return WizardState(
                step=2,
                samples=0,
                needed=_SAMPLES_NEEDED,
                instruction="Type your distance from the camera in cm, then sit still.",
                done=False,
            )

        if landmarks and len(landmarks) > _RIGHT_CHEEK:
            lx = landmarks[_LEFT_CHEEK].x * frame_w
            rx = landmarks[_RIGHT_CHEEK].x * frame_w
            pixel_width = abs(rx - lx)
            if pixel_width >= 1.0:
                # focal_length_px = pixel_width * distance_cm / face_width_cm
                # face_width_cm unknown here — we store pixel_width * distance_cm
                # and DistanceEstimator divides by face_width_cm at runtime.
                # So: focal_length_px = pixel_width * distance_cm / ASSUMED_FACE_WIDTH
                # We store the raw product and let DistanceEstimator use face_width_cm
                # from demographics. Here we compute focal_length_px assuming a
                # reference face width of 14.0 cm (average adult).
                focal = (pixel_width * self._distance_cm) / self._face_width_cm
                self._px_samples.append(focal)

        if len(self._px_samples) >= _SAMPLES_NEEDED:
            self._store.set("focal_length_px", sum(self._px_samples) / len(self._px_samples))
            self._step = 3

        return WizardState(
            step=2,
            samples=len(self._px_samples),
            needed=_SAMPLES_NEEDED,
            instruction=f"Sit at {self._distance_cm:.0f} cm. Hold still.",
            done=False,
        )

    def _done_state(self) -> WizardState:
        return WizardState(step=3, samples=0, needed=0, instruction="Calibration complete.", done=True)
