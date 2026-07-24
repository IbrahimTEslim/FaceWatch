import cv2
import numpy as np

# Modern dark overlay palette
_BG         = (20, 20, 20)
_BORDER     = (0, 200, 160)       # teal glow
_ACCENT     = (0, 220, 180)
_TEXT       = (240, 240, 240)
_HINT       = (120, 120, 120)
_MATCH_BG   = (35, 35, 35)
_MATCH_SEL  = (0, 160, 120)
_ERROR      = (60, 80, 220)

_FONT       = cv2.FONT_HERSHEY_SIMPLEX
_ALPHA      = 0.82


class TextInput:
    """
    Key-by-key text input rendered as a modern overlay panel.

    Usage:
        feed(key_code)  — returns True while active
        draw(frame)     — renders panel onto frame in-place
        confirmed       — True when Enter pressed with non-empty buffer
        cancelled       — True when Escape pressed
        value           — current typed string (display_name)
        normalized      — lowercased stripped value (name key)
    """

    def __init__(self, prompt: str, suggestions: list[str] | None = None):
        self._prompt      = prompt
        self._buffer      = ""
        self._confirmed   = False
        self._cancelled   = False
        self._error       = ""
        self._suggestions = suggestions or []
        self._filtered:   list[str] = []
        self._sel_idx:    int       = -1   # -1 = none selected

    # ── public ────────────────────────────────────────────────────────────────

    @property
    def confirmed(self) -> bool:
        return self._confirmed

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    @property
    def active(self) -> bool:
        return not self._confirmed and not self._cancelled

    @property
    def value(self) -> str:
        if self._sel_idx >= 0 and self._sel_idx < len(self._filtered):
            return self._filtered[self._sel_idx]
        return self._buffer

    @property
    def normalized(self) -> str:
        return self.value.strip().lower()

    def set_error(self, msg: str) -> None:
        self._error = msg
        self._confirmed = False

    def feed(self, key_code: int) -> None:
        if not self.active:
            return

        if key_code == 13:    # Enter
            if self.value.strip():
                self._confirmed = True
            return

        if key_code == 27:    # Escape
            self._cancelled = True
            return

        if key_code == 8 or key_code == 127:   # Backspace
            self._buffer    = self._buffer[:-1]
            self._sel_idx   = -1
            self._error     = ""
            self._update_filter()
            return

        if key_code == 0 or key_code == 255:   # special / no key
            return

        # Arrow keys for suggestion navigation
        if key_code == 82:    # up arrow (cv2 special)
            self._sel_idx = max(-1, self._sel_idx - 1)
            return
        if key_code == 84:    # down arrow
            if self._filtered:
                self._sel_idx = min(len(self._filtered) - 1, self._sel_idx + 1)
            return

        if 32 <= key_code <= 126:
            self._buffer  += chr(key_code)
            self._sel_idx  = -1
            self._error    = ""
            self._update_filter()

    def draw(self, frame: np.ndarray) -> None:
        fh, fw = frame.shape[:2]

        panel_w = min(480, fw - 40)
        rows    = 3 + min(len(self._filtered), 5)
        panel_h = rows * 36 + 24
        px      = (fw - panel_w) // 2
        py      = (fh - panel_h) // 2

        overlay = frame.copy()

        # Background panel
        cv2.rectangle(overlay, (px, py), (px + panel_w, py + panel_h), _BG, -1)
        cv2.addWeighted(overlay, _ALPHA, frame, 1 - _ALPHA, 0, frame)

        # Glow border
        cv2.rectangle(frame, (px - 1, py - 1),
                      (px + panel_w + 1, py + panel_h + 1), _BORDER, 2)

        # Prompt
        y = py + 28
        cv2.putText(frame, self._prompt, (px + 16, y),
                    _FONT, 0.55, _ACCENT, 1, cv2.LINE_AA)

        # Input box
        y += 32
        box_y1, box_y2 = y - 20, y + 10
        cv2.rectangle(frame, (px + 12, box_y1), (px + panel_w - 12, box_y2), _BORDER, 1)
        display = self._buffer + "|"
        cv2.putText(frame, display, (px + 18, y),
                    _FONT, 0.55, _TEXT, 1, cv2.LINE_AA)

        # Error
        if self._error:
            y += 28
            cv2.putText(frame, self._error, (px + 16, y),
                        _FONT, 0.42, _ERROR, 1, cv2.LINE_AA)

        # Suggestions
        if self._filtered:
            y += 28
            cv2.putText(frame, "Suggestions", (px + 16, y),
                        _FONT, 0.38, _HINT, 1, cv2.LINE_AA)
            for i, name in enumerate(self._filtered[:5]):
                y += 26
                is_sel = i == self._sel_idx
                if is_sel:
                    cv2.rectangle(frame, (px + 12, y - 18),
                                  (px + panel_w - 12, y + 6), _MATCH_SEL, -1)
                color = _TEXT if is_sel else _HINT
                cv2.putText(frame, name, (px + 18, y),
                            _FONT, 0.45, color, 1, cv2.LINE_AA)

        # Hint
        hint_y = py + panel_h - 10
        cv2.putText(frame, "Enter to confirm   Esc to cancel   arrows to navigate",
                    (px + 16, hint_y), _FONT, 0.33, _HINT, 1, cv2.LINE_AA)

    # ── internal ──────────────────────────────────────────────────────────────

    def _update_filter(self) -> None:
        q = self._buffer.strip().lower()
        if not q:
            self._filtered = list(self._suggestions)
        else:
            self._filtered = [s for s in self._suggestions if q in s.lower()]
