import numpy as np
from sort_tracker import Sort


class FaceTracker:
    def __init__(self, max_age: int = 30, min_hits: int = 3):
        self._sort = Sort(max_age=max_age, min_hits=min_hits)

    def update(self, detections: list[list[float]]) -> dict[int, list[float]]:
        """
        detections: [[x1, y1, x2, y2, score], ...]
        returns:    {track_id: [x1, y1, x2, y2]}
        """
        if detections:
            dets = np.array(detections, dtype=float)
        else:
            dets = np.empty((0, 5))

        tracks = self._sort.update(dets)
        return {int(t[4]): t[:4].tolist() for t in tracks}
