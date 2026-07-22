# Cheekbone landmark indices (MediaPipe 478-point model)
# 234 = left cheekbone, 454 = right cheekbone — most stable horizontal pair
_LEFT_CHEEK  = 234
_RIGHT_CHEEK = 454


class DistanceEstimator:
    def estimate(self, landmarks: list, face_width_cm: float,
                 focal_length_px: float, frame_w: int) -> float:
        """
        Returns distance in cm using the known-size formula:
            distance_cm = (face_width_cm * focal_length_px) / pixel_width_px

        pixel_width_px is the distance between cheekbone landmarks 234 and 454,
        scaled to frame pixel coordinates.

        Returns -1.0 if landmarks unavailable or pixel_width is zero.
        """
        if not landmarks or len(landmarks) <= _RIGHT_CHEEK:
            return -1.0

        lx = landmarks[_LEFT_CHEEK].x * frame_w
        rx = landmarks[_RIGHT_CHEEK].x * frame_w
        pixel_width = abs(rx - lx)

        if pixel_width < 1.0:
            return -1.0

        return (face_width_cm * focal_length_px) / pixel_width
