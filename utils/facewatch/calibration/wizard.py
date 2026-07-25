from dataclasses import dataclass
from calibration.store import CalibrationStore
from calibration.sample_collector import SampleCollector
from demographics.face_width import DEFAULT_FACE_WIDTH_CM

_LEFT_CHEEK     = 234
_RIGHT_CHEEK    = 454
_SAMPLES_NEEDED = 30


@dataclass
class WizardState:
    samples:     int
    needed:      int
    instruction: str
    accepted:    bool
    done:        bool


class FocalWizard:
    """
    Collects focal_length_px.
    Caller must call set_distance_cm() before samples are accepted.
    """

    def __init__(self, store: CalibrationStore, face_width_cm: float = DEFAULT_FACE_WIDTH_CM):
        self._store         = store
        self._face_width_cm = face_width_cm
        self._collector     = SampleCollector()
        self._samples:      list[float] = []
        self._distance_cm:  float | None = None

    def set_distance_cm(self, distance_cm: float) -> None:
        self._distance_cm = distance_cm

    def feed(self, landmarks: list, frame_w: int) -> WizardState:
        if self._distance_cm is None:
            return WizardState(
                samples=0, needed=_SAMPLES_NEEDED,
                instruction="Type your distance from the camera in cm, then press Enter.",
                accepted=False, done=False,
            )

        result = self._collector.evaluate(landmarks)
        if result.accepted and landmarks and len(landmarks) > _RIGHT_CHEEK:
            lx = landmarks[_LEFT_CHEEK].x * frame_w
            rx = landmarks[_RIGHT_CHEEK].x * frame_w
            px_width = abs(rx - lx)
            if px_width >= 1.0:
                self._samples.append((px_width * self._distance_cm) / self._face_width_cm)

        if len(self._samples) >= _SAMPLES_NEEDED:
            self._store.set("focal_length_px", sum(self._samples) / len(self._samples))
            return WizardState(
                samples=_SAMPLES_NEEDED, needed=_SAMPLES_NEEDED,
                instruction="Focal length calibrated.",
                accepted=result.accepted, done=True,
            )

        return WizardState(
            samples=len(self._samples), needed=_SAMPLES_NEEDED,
            instruction=f"Sit at {self._distance_cm:.0f} cm and hold still.",
            accepted=result.accepted, done=False,
        )


class GazeWizard:
    """
    Collects gaze_center_h/v for a specific face_id.
    Saves to per-face table via CalibrationStore.save_gaze_center().
    """

    def __init__(self, store: CalibrationStore, face_id: int):
        self._store     = store
        self._face_id   = face_id
        self._collector = SampleCollector()
        self._h_samples: list[float] = []
        self._v_samples: list[float] = []

    def feed(self, landmarks: list) -> WizardState:
        result = self._collector.evaluate(landmarks)
        if result.accepted:
            self._h_samples.append(result.iris_h)
            self._v_samples.append(result.iris_v)

        if len(self._h_samples) >= _SAMPLES_NEEDED:
            h = sum(self._h_samples) / len(self._h_samples)
            v = sum(self._v_samples) / len(self._v_samples)
            self._store.save_gaze_center(self._face_id, h, v)
            return WizardState(
                samples=_SAMPLES_NEEDED, needed=_SAMPLES_NEEDED,
                instruction="Gaze calibration complete.",
                accepted=result.accepted, done=True,
            )

        return WizardState(
            samples=len(self._h_samples), needed=_SAMPLES_NEEDED,
            instruction="Look straight at the center of your screen and hold still.",
            accepted=result.accepted, done=False,
        )
