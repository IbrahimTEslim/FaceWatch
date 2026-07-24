import cv2
import numpy as np

from core.recognizer import Identity
from analysis.gaze import GazeState
from analysis.expressions.base import Expression
from storage.config_store import ConfigStore

# Colors (BGR)
_GREEN   = (0, 220, 0)
_RED     = (0, 0, 220)
_WHITE   = (255, 255, 255)
_GRAY    = (160, 160, 160)
_ACCENT  = (0, 220, 180)
_DIM     = (40, 40, 40)
_CARD_BG = (22, 22, 22)
_SEP     = (55, 55, 55)


def _parse_bgr(value: str) -> tuple:
    b, g, r = [int(x) for x in value.split(",")]
    return (b, g, r)

_FONT      = cv2.FONT_HERSHEY_SIMPLEX
_FONT_NORM = 0.55
_FONT_SM   = 0.42
_FONT_XS   = 0.36
_THICK     = 1

_CARD_W    = 260
_CARD_H    = 520
_CARD_PAD  = 12
_WIN_NAME  = "FaceWatch Debug"


def _put(img: np.ndarray, text: str, x: int, y: int,
         color: tuple = _WHITE, scale: float = _FONT_SM) -> int:
    cv2.putText(img, text, (x, y), _FONT, scale, color, _THICK, cv2.LINE_AA)
    return y + int(scale * 28 + 4)


def _bar(img: np.ndarray, x: int, y: int, w: int, value: float,
         color: tuple, h: int = 6) -> int:
    cv2.rectangle(img, (x, y), (x + w, y + h), _SEP, -1)
    filled = int(w * max(0.0, min(1.0, value)))
    if filled > 0:
        cv2.rectangle(img, (x, y), (x + filled, y + h), color, -1)
    return y + h + 6


class Renderer:
    def __init__(self, config: ConfigStore):
        self._debug: bool = False
        self._color_known       = _parse_bgr(config.get("box_color_known"))
        self._color_identifying = _parse_bgr(config.get("box_color_identifying"))
        self._color_unknown     = _parse_bgr(config.get("box_color_unknown"))

    def _status_color(self, status: str) -> tuple:
        if status == "known":        return self._color_known
        if status == "identifying":  return self._color_identifying
        return self._color_unknown

    def toggle_debug(self) -> None:
        self._debug = not self._debug
        if not self._debug:
            try:
                cv2.destroyWindow(_WIN_NAME)
            except Exception:
                pass

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
        demographics: dict[int, dict | None] | None = None,
    ) -> np.ndarray:
        for track_id, bbox in tracks.items():
            identity = identities.get(track_id, Identity())
            gaze     = gaze_states.get(track_id)
            dist     = distances.get(track_id, -1.0)
            alert    = alert_active.get(track_id, False)

            x1, y1, x2, y2 = [int(v) for v in bbox]
            box_color = _RED if alert else self._status_color(identity.status)
            cv2.rectangle(frame, (x1, y1), (x2, y2), box_color, _THICK)

            label = identity.display_name if identity.status == "known" else identity.status
            _put(frame, label, x1, max(y1 - 8, 12), box_color, _FONT_NORM)

            dist_text = f"{dist:.0f} cm" if dist > 0 else "dist: --"
            _put(frame, dist_text, x1, y1 + 18)

            if gaze and gaze.alert_active:
                _put(frame, "! LOOK AWAY", x1, y1 + 36, _RED)

        if self._debug:
            self._draw_debug_window(
                tracks, identities, gaze_states, expressions,
                distances, focus_scores, demographics or {},
            )

        return frame

    # ── Debug window ──────────────────────────────────────────────────────────

    def _draw_debug_window(
        self,
        tracks: dict[int, list[float]],
        identities: dict[int, Identity],
        gaze_states: dict[int, GazeState],
        expressions: dict[int, list[Expression]],
        distances: dict[int, float],
        focus_scores: dict[int, float],
        demographics: dict[int, dict | None],
    ) -> None:
        cols     = 3
        n        = len(tracks)
        n_cols   = min(n, cols)
        n_rows   = max(1, (n + cols - 1) // cols)
        card_h   = _CARD_H
        win_w    = _CARD_W * n_cols + _CARD_PAD * (n_cols + 1)
        win_h    = _CARD_H * n_rows + _CARD_PAD * (n_rows + 1)
        canvas   = np.full((win_h, win_w, 3), 14, dtype=np.uint8)

        for idx, track_id in enumerate(tracks):
            row = idx // cols
            col = idx % cols
            cx  = _CARD_PAD + col * (_CARD_W + _CARD_PAD)
            cy  = _CARD_PAD + row * (card_h + _CARD_PAD)
            self._draw_card(canvas, cx, cy, track_id,
                            identities, gaze_states, expressions,
                            distances, focus_scores, demographics)

        cv2.imshow(_WIN_NAME, canvas)

    def _draw_card(
        self,
        canvas: np.ndarray,
        cx: int, cy: int,
        track_id: int,
        identities: dict[int, Identity],
        gaze_states: dict[int, GazeState],
        expressions: dict[int, list[Expression]],
        distances: dict[int, float],
        focus_scores: dict[int, float],
        demographics: dict[int, dict | None],
    ) -> None:
        ch = _CARD_H - _CARD_PAD * 2
        # Card background
        identity = identities.get(track_id, Identity())
        border_color = self._status_color(identity.status)
        cv2.rectangle(canvas, (cx, cy), (cx + _CARD_W, cy + ch), _CARD_BG, -1)
        cv2.rectangle(canvas, (cx, cy), (cx + _CARD_W, cy + ch), border_color, 1)

        gaze     = gaze_states.get(track_id)
        dist     = distances.get(track_id, -1.0)
        focus    = focus_scores.get(track_id, -1.0)
        demo     = demographics.get(track_id)
        exprs    = expressions.get(track_id, [])

        p  = cx + _CARD_PAD
        y  = cy + 20

        # ── Header ────────────────────────────────────────────────────────────
        label = identity.display_name if identity.status == "known" else f"Track {track_id}"
        y = _put(canvas, label, p, y, _ACCENT, _FONT_NORM)
        status_color = _GREEN if identity.status == "known" else _GRAY
        y = _put(canvas, identity.status.upper(), p, y, status_color, _FONT_XS)
        cv2.line(canvas, (cx + 6, y), (cx + _CARD_W - 6, y), _SEP, 1)
        y += 8

        # ── Focus score ───────────────────────────────────────────────────────
        if focus >= 0:
            focus_color = _GREEN if focus >= 70 else (_YELLOW if focus >= 40 else _RED)
            y = _put(canvas, f"Focus  {focus:.0f}/100", p, y, focus_color, _FONT_SM)
            y = _bar(canvas, p, y, _CARD_W - _CARD_PAD * 2, focus / 100, focus_color)

        # ── Distance ──────────────────────────────────────────────────────────
        dist_str = f"{dist:.0f} cm" if dist > 0 else "--"
        y = _put(canvas, f"Distance   {dist_str}", p, y, _WHITE, _FONT_SM)

        # ── Gaze ──────────────────────────────────────────────────────────────
        if gaze:
            gaze_color = _GREEN if gaze.on_screen else _RED
            y = _put(canvas, f"Gaze   {gaze.direction}  ({gaze.off_screen_sec:.1f}s off)", p, y, gaze_color, _FONT_SM)

        cv2.line(canvas, (cx + 6, y), (cx + _CARD_W - 6, y), _SEP, 1)
        y += 8

        # ── Demographics ──────────────────────────────────────────────────────
        if demo:
            y = _put(canvas, "DEMOGRAPHICS", p, y, _ACCENT, _FONT_XS)
            age    = demo.get("age_estimate", "?")
            gender = demo.get("gender", "?")
            race   = demo.get("race", "?")
            fw     = demo.get("face_width_cm")
            y = _put(canvas, f"Age     {age}", p, y, _WHITE, _FONT_SM)
            y = _put(canvas, f"Gender  {gender}", p, y, _WHITE, _FONT_SM)
            y = _put(canvas, f"Race    {race}", p, y, _WHITE, _FONT_SM)
            if fw:
                y = _put(canvas, f"Face W  {fw:.1f} cm", p, y, _WHITE, _FONT_SM)
        else:
            y = _put(canvas, "Demographics: pending...", p, y, _GRAY, _FONT_XS)

        cv2.line(canvas, (cx + 6, y), (cx + _CARD_W - 6, y), _SEP, 1)
        y += 8

        # ── Expressions ───────────────────────────────────────────────────────
        y = _put(canvas, "EXPRESSIONS", p, y, _ACCENT, _FONT_XS)
        for expr in exprs:
            color = expr.color if expr.active else _GRAY
            label = f"{expr.name:<12} {expr.value:.2f}"
            y = _put(canvas, label, p, y, color, _FONT_XS)
            y = _bar(canvas, p, y - 4, _CARD_W - _CARD_PAD * 2, expr.value, color, h=4)
            y += 10
            if y > cy + ch - 20:
                break
