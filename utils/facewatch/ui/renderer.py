import cv2
import numpy as np

from core.recognizer import Identity
from analysis.gaze import GazeState
from analysis.expressions.base import Expression

# Colors (BGR)
_GREEN  = (0, 220, 0)
_RED    = (0, 0, 220)
_YELLOW = (0, 200, 220)
_WHITE  = (255, 255, 255)
_GRAY   = (160, 160, 160)

_FONT       = cv2.FONT_HERSHEY_SIMPLEX
_FONT_SMALL = 0.45
_FONT_NORM  = 0.55
_THICKNESS  = 1


def _put(frame: np.ndarray, text: str, x: int, y: int,
         color: tuple = _WHITE, scale: float = _FONT_SMALL) -> int:
    """Draw text, return next y position."""
    cv2.putText(frame, text, (x, y), _FONT, scale, color, _THICKNESS, cv2.LINE_AA)
    return y + int(scale * 30 + 4)


class Renderer:
    def __init__(self):
        self._debug: bool = False

    def toggle_debug(self) -> None:
        self._debug = not self._debug

    def draw(
        self,
        frame: np.ndarray,
        tracks: dict[int, list[float]],
        identities: dict[int, Identity],
        gaze_states: dict[int, GazeState],
        expressions: dict[int, list[Expression]],
        distances: dict[int, float],
        focus_scores: dict[int, float],
        alert_active: dict[int, bool],
    ) -> np.ndarray:
        for track_id, bbox in tracks.items():
            identity   = identities.get(track_id, Identity())
            gaze       = gaze_states.get(track_id)
            dist       = distances.get(track_id, -1.0)
            alert      = alert_active.get(track_id, False)

            x1, y1, x2, y2 = [int(v) for v in bbox]
            box_color = _RED if alert else _GREEN
            cv2.rectangle(frame, (x1, y1), (x2, y2), box_color, _THICKNESS)

            # Name + status
            label = identity.name if identity.status == "known" else identity.status
            y = _put(frame, label, x1, max(y1 - 8, 12), box_color, _FONT_NORM)

            # Distance
            dist_text = f"{dist:.0f} cm" if dist > 0 else "dist: --"
            y = _put(frame, dist_text, x1, y1 + 18)

            # Gaze alert
            if gaze and gaze.alert_active:
                _put(frame, "! LOOK AWAY", x1, y1 + 36, _RED)

            # Debug overlay
            if self._debug:
                self._draw_debug(frame, x1, y2 + 14, track_id,
                                 expressions, focus_scores, gaze)

        return frame

    def _draw_debug(
        self,
        frame: np.ndarray,
        x: int,
        y: int,
        track_id: int,
        expressions: dict[int, list[Expression]],
        focus_scores: dict[int, float],
        gaze: GazeState | None,
    ) -> None:
        focus = focus_scores.get(track_id, -1.0)
        if focus >= 0:
            y = _put(frame, f"focus: {focus:.0f}", x, y, _YELLOW)

        if gaze:
            y = _put(frame, f"gaze: {gaze.direction} ({gaze.off_screen_sec:.1f}s)", x, y, _GRAY)

        for expr in expressions.get(track_id, []):
            color = expr.color if expr.active else _GRAY
            y = _put(frame, f"{expr.name}: {expr.value:.2f}", x, y, color)
