import cv2
import numpy as np


def _make_kalman(
    process_var: float = 50.0,
    measurement_var: float = 0.2,
) -> cv2.KalmanFilter:
    kf = cv2.KalmanFilter(4, 2)
    kf.transitionMatrix    = np.array(
        [[1, 0, 1, 0],
         [0, 1, 0, 1],
         [0, 0, 1, 0],
         [0, 0, 0, 1]], dtype=np.float32
    )
    kf.measurementMatrix   = np.array([[1, 0, 0, 0], [0, 1, 0, 0]], dtype=np.float32)
    kf.processNoiseCov     = np.eye(4, dtype=np.float32) * process_var
    kf.measurementNoiseCov = np.eye(2, dtype=np.float32) * measurement_var
    kf.errorCovPost        = np.eye(4, dtype=np.float32)
    kf.statePre            = np.zeros((4, 1), np.float32)
    kf.statePost           = np.zeros((4, 1), np.float32)
    return kf


class GazeSmoother:
    """
    Kalman + EMA smoother for predicted gaze (sx, sy).
    One instance per face_id in GazeTracker.
    Based on eyetrax KalmanSmoother + KalmanEMASmoother, but outputs the
    corrected Kalman state rather than the prediction.

    The constant-velocity model uses one time step per frame (dt=1). Noise
    covariances are tuned in those units, so frame-rate changes alter the
    effective smoothing slightly; switching to real dt would need re-tuning.

    ema_alpha=0.0 disables EMA (pure Kalman).
    ema_alpha closer to 1.0 = stronger smoothing / more lag.
    """

    MAX_EMA_ALPHA = 0.95  # 1.0 would freeze the output

    def __init__(self, ema_alpha: float = 0.25):
        self._kf        = _make_kalman()
        self._ema_alpha = 0.0
        self.ema_alpha  = ema_alpha
        self._ema_x: float | None = None
        self._ema_y: float | None = None
        self._initialized = False

    @property
    def ema_alpha(self) -> float:
        return self._ema_alpha

    @ema_alpha.setter
    def ema_alpha(self, value: float) -> None:
        """Clamped to [0, MAX_EMA_ALPHA]. Takes effect on the next step()."""
        self._ema_alpha = min(max(float(value), 0.0), self.MAX_EMA_ALPHA)

    def tune_from_variance(self, var_x: float, var_y: float) -> None:
        """Adjust measurementNoiseCov from observed gaze variance at tune points."""
        self._kf.measurementNoiseCov = np.array(
            [[max(var_x, 1e-4), 0], [0, max(var_y, 1e-4)]], dtype=np.float32
        )

    def step(self, sx: float, sy: float) -> tuple[float, float]:
        meas = np.array([[sx], [sy]], dtype=np.float32)

        if not self._initialized:
            self._kf.statePre[:2]  = meas
            self._kf.statePost[:2] = meas
            self._initialized = True

        # Output the corrected (posterior) estimate. eyetrax returned the prior
        # prediction, which extrapolates from the previous frame and amplifies
        # noise: simulated jitter was up to ~65% higher at the same settle time.
        self._kf.predict()
        post = self._kf.correct(meas)
        kx, ky = float(post[0, 0]), float(post[1, 0])

        a = self._ema_alpha
        if a == 0.0:
            return kx, ky

        if self._ema_x is None:
            self._ema_x, self._ema_y = kx, ky
        else:
            self._ema_x = a * self._ema_x + (1.0 - a) * kx
            self._ema_y = a * self._ema_y + (1.0 - a) * ky

        return self._ema_x, self._ema_y
