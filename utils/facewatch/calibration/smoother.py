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
    Ported verbatim from eyetrax KalmanSmoother + KalmanEMASmoother.

    ema_alpha=0.0 disables EMA (pure Kalman).
    ema_alpha closer to 1.0 = stronger smoothing / more lag.
    """

    def __init__(self, ema_alpha: float = 0.25):
        self._kf        = _make_kalman()
        self._ema_alpha = ema_alpha
        self._ema_x: float | None = None
        self._ema_y: float | None = None

    def tune_from_variance(self, var_x: float, var_y: float) -> None:
        """Adjust measurementNoiseCov from observed gaze variance at tune points."""
        self._kf.measurementNoiseCov = np.array(
            [[max(var_x, 1e-4), 0], [0, max(var_y, 1e-4)]], dtype=np.float32
        )

    def step(self, sx: float, sy: float) -> tuple[float, float]:
        meas = np.array([[sx], [sy]], dtype=np.float32)

        if not np.any(self._kf.statePost):
            self._kf.statePre[:2]  = meas
            self._kf.statePost[:2] = meas

        pred = self._kf.predict()
        self._kf.correct(meas)
        kx, ky = float(pred[0, 0]), float(pred[1, 0])

        a = self._ema_alpha
        if a == 0.0:
            return kx, ky

        if self._ema_x is None:
            self._ema_x, self._ema_y = kx, ky
        else:
            self._ema_x = a * self._ema_x + (1.0 - a) * kx
            self._ema_y = a * self._ema_y + (1.0 - a) * ky

        return self._ema_x, self._ema_y
