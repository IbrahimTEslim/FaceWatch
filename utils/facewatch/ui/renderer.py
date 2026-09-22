import cv2
import numpy as np

from core.recognizer import Identity
from analysis.gaze import GazeState
from analysis.expressions.base import Expression
from storage.config_store import ConfigStore
from calibration.wizard import WizardState
from calibration.store import CalibrationStore

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
_PANEL_W   = 420
_PANEL_H   = 130


_YELLOW  = (0, 200, 255)


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

    def draw_calibration_grid_input(self, frame: np.ndarray, prompt: str, value: str) -> np.ndarray:
        h, w = frame.shape[:2]
        x = (w - _PANEL_W) // 2
        y = (h - _PANEL_H) // 2
        overlay = frame.copy()
        cv2.rectangle(overlay, (x, y), (x + _PANEL_W, y + _PANEL_H), _CARD_BG, -1)
        cv2.rectangle(overlay, (x, y), (x + _PANEL_W, y + _PANEL_H), _ACCENT, 1)
        cv2.addWeighted(overlay, 0.85, frame, 0.15, 0, frame)
        p  = x + _CARD_PAD
        ty = y + 28
        ty = _put(frame, "CALIBRATION  Grid Setup", p, ty, _ACCENT, _FONT_SM)
        ty = _put(frame, prompt, p, ty, _WHITE, _FONT_XS)
        _put(frame, f"> {value}_", p, ty + 8, _GREEN, _FONT_SM)
        return frame

    def draw_calibration_step1(self, frame: np.ndarray, state: WizardState, input_text: str) -> np.ndarray:
        h, w = frame.shape[:2]
        x = (w - _PANEL_W) // 2
        y = (h - _PANEL_H) // 2
        overlay = frame.copy()
        cv2.rectangle(overlay, (x, y), (x + _PANEL_W, y + _PANEL_H), _CARD_BG, -1)
        cv2.rectangle(overlay, (x, y), (x + _PANEL_W, y + _PANEL_H), _ACCENT, 1)
        cv2.addWeighted(overlay, 0.85, frame, 0.15, 0, frame)
        p  = x + _CARD_PAD
        ty = y + 28
        ty = _put(frame, "CALIBRATION  Focal Length", p, ty, _ACCENT, _FONT_SM)
        ty = _put(frame, state.instruction, p, ty, _WHITE, _FONT_XS)
        if not state.done:
            bar_w = _PANEL_W - _CARD_PAD * 2
            _bar(frame, p, ty + 2, bar_w, state.samples / max(state.needed, 1), _ACCENT)
            cursor = f"> {input_text}_"
            _put(frame, cursor, p, ty + 18, _GREEN, _FONT_SM)
        return frame

    def draw_watermark(self, frame: np.ndarray) -> None:
        h = frame.shape[0]
        cv2.putText(frame, "[H] Help", (10, h - 10), _FONT, _FONT_XS, _GRAY, _THICK, cv2.LINE_AA)

    def draw_help_overlay(self, frame: np.ndarray) -> None:
        h, w = frame.shape[:2]
        entries = [
            ("H",   "Toggle this help screen"),
            ("R",   "Register face under cursor"),
            ("C",   "Start calibration wizard"),
            ("D",   "Toggle debug panel"),
            ("F",   "Force re-identify unknown faces"),
            ("S",   "Force stats write to DB"),
            ("O",   "Open report in browser"),
            (",",   "Open settings window"),
            ("Q",   "Quit FaceWatch"),
            ("",    ""),
            ("Mouse", "Right-click a face box for options:"),
            ("",    "  Register / Rename / Reassign / Delete"),
            ("",    "  Calibrate distance or gaze"),
            ("",    "  Toggle gaze pointer"),
            ("",    ""),
            ("ESC", "Cancel active calibration wizard"),
        ]
        row_h   = 22
        pad     = 16
        col_w   = 90
        panel_w = 460
        panel_h = len(entries) * row_h + pad * 2 + 30
        x = (w - panel_w) // 2
        y = (h - panel_h) // 2

        overlay = frame.copy()
        cv2.rectangle(overlay, (x, y), (x + panel_w, y + panel_h), (18, 18, 18), -1)
        cv2.rectangle(overlay, (x, y), (x + panel_w, y + panel_h), _ACCENT, 1)
        cv2.addWeighted(overlay, 0.88, frame, 0.12, 0, frame)

        ty = y + pad + 18
        cv2.putText(frame, "FaceWatch  Keyboard Shortcuts", (x + pad, ty),
                    _FONT, _FONT_SM, _ACCENT, _THICK, cv2.LINE_AA)
        ty += 6
        cv2.line(frame, (x + pad, ty), (x + panel_w - pad, ty), _SEP, 1)
        ty += 14

        for key, desc in entries:
            if key == "" and desc == "":
                ty += 6
                continue
            if key == "Mouse":
                cv2.putText(frame, desc, (x + pad, ty), _FONT, _FONT_XS, _ACCENT, _THICK, cv2.LINE_AA)
            else:
                cv2.putText(frame, key,  (x + pad, ty),           _FONT, _FONT_XS, _YELLOW, _THICK, cv2.LINE_AA)
                cv2.putText(frame, desc, (x + pad + col_w, ty),   _FONT, _FONT_XS, _WHITE,  _THICK, cv2.LINE_AA)
            ty += row_h

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
        calibration: CalibrationStore | None = None,
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
                if gaze.on_screen:
                    _put(frame, f"clearing {gaze.clearing_sec:.1f}s", x2 - 90, y1 + 18, _GREEN)
                else:
                    _put(frame, "! LOOK AWAY", x1, y1 + 36, _RED)

        if self._debug:
            self._draw_debug_window(
                tracks, identities, gaze_states, expressions,
                distances, focus_scores, demographics or {}, calibration,
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
        calibration: CalibrationStore | None = None,
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
                            distances, focus_scores, demographics, calibration)

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
        calibration: CalibrationStore | None = None,
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

        if calibration and identity.face_id:
            cal_at = calibration.is_gaze_calibrated(identity.face_id)
            if cal_at:
                y = _put(canvas, f"Gaze cal  \u2713 {cal_at[:10]}", p, y, _GREEN, _FONT_XS)
            else:
                y = _put(canvas, "Gaze cal  uncalibrated", p, y, _GRAY, _FONT_XS)

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
