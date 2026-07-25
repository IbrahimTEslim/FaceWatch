import time
import cv2
import numpy as np
from enum import Enum, auto
from dataclasses import dataclass, field

# Modern dark overlay palette (matches text_input.py)
_BG       = (20, 20, 20)
_BORDER   = (0, 200, 160)
_ACCENT   = (0, 220, 180)
_TEXT     = (240, 240, 240)
_HINT     = (120, 120, 120)
_HOVER_BG = (40, 40, 40)
_FONT     = cv2.FONT_HERSHEY_SIMPLEX
_ALPHA    = 0.85
_DBL_SEC  = 0.4   # double-click window


class MouseAction(Enum):
    NONE               = auto()
    REGISTER           = auto()   # single click unknown
    RENAME             = auto()   # double click known
    REASSIGN           = auto()   # context menu → reassign
    DELETE             = auto()   # context menu → delete
    REIDENTIFY         = auto()   # context menu → force re-identify
    CALIBRATE_DISTANCE = auto()   # context menu → calibrate focal length
    CALIBRATE_GAZE     = auto()   # context menu → calibrate gaze center (known only)


@dataclass
class MouseEvent:
    action:   MouseAction = MouseAction.NONE
    track_id: int | None  = None


_MENU_ITEMS_KNOWN: list[tuple[str, MouseAction]] = [
    ("Calibrate gaze",    MouseAction.CALIBRATE_GAZE),
    ("Calibrate distance",MouseAction.CALIBRATE_DISTANCE),
    ("Force re-identify", MouseAction.REIDENTIFY),
    ("Reassign to...",    MouseAction.REASSIGN),
    ("Delete face",       MouseAction.DELETE),
]

_MENU_ITEMS_UNKNOWN: list[tuple[str, MouseAction]] = [
    ("Calibrate distance",MouseAction.CALIBRATE_DISTANCE),
    ("Force re-identify", MouseAction.REIDENTIFY),
    ("Reassign to...",    MouseAction.REASSIGN),
    ("Delete face",       MouseAction.DELETE),
]


class MouseHandler:
    def __init__(self):
        self._tracks:      dict[int, list[float]] = {}
        self._identities:  dict                   = {}
        self._event:       MouseEvent             = MouseEvent()
        self._last_click:  tuple[int, float]      = (-1, 0.0)   # (track_id, time)
        self._menu_track:  int | None             = None
        self._menu_pos:    tuple[int, int]        = (0, 0)
        self._menu_open:   bool                   = False
        self._hovered_item: int                   = -1

    def update_tracks(self, tracks: dict[int, list[float]], identities: dict) -> None:
        self._tracks     = tracks
        self._identities = identities

    def get_event(self) -> MouseEvent:
        ev = self._event
        self._event = MouseEvent()
        return ev

    def callback(self, event: int, x: int, y: int, flags: int, param) -> None:
        if event == cv2.EVENT_RBUTTONDOWN:
            self._on_right_click(x, y)
            return

        if event == cv2.EVENT_MOUSEMOVE and self._menu_open:
            self._hovered_item = self._menu_hit(x, y)
            return

        if event == cv2.EVENT_LBUTTONDOWN:
            if self._menu_open:
                self._on_menu_click(x, y)
                return
            self._on_left_click(x, y)

    def draw_menu(self, frame: np.ndarray) -> None:
        if not self._menu_open:
            return

        items   = self._menu_items()
        item_h  = 34
        pad     = 14
        w       = 200
        h       = len(items) * item_h + pad
        mx, my  = self._menu_pos

        # Clamp to frame
        fh, fw  = frame.shape[:2]
        mx      = min(mx, fw - w - 4)
        my      = min(my, fh - h - 4)

        overlay = frame.copy()
        cv2.rectangle(overlay, (mx, my), (mx + w, my + h), _BG, -1)
        cv2.addWeighted(overlay, _ALPHA, frame, 1 - _ALPHA, 0, frame)
        cv2.rectangle(frame, (mx - 1, my - 1), (mx + w + 1, my + h + 1), _BORDER, 1)

        for i, (label, _) in enumerate(items):
            iy1 = my + pad // 2 + i * item_h
            iy2 = iy1 + item_h
            if i == self._hovered_item:
                cv2.rectangle(frame, (mx + 2, iy1), (mx + w - 2, iy2), _HOVER_BG, -1)
            color = _ACCENT if i == self._hovered_item else _TEXT
            cv2.putText(frame, label, (mx + 12, iy1 + 22),
                        _FONT, 0.45, color, 1, cv2.LINE_AA)

    def close_menu(self) -> None:
        self._menu_open    = False
        self._hovered_item = -1
        self._menu_track   = None

    # ── internal ──────────────────────────────────────────────────────────────

    def _menu_items(self) -> list:
        identity = self._identities.get(self._menu_track)
        if identity and identity.status == "known":
            return _MENU_ITEMS_KNOWN
        return _MENU_ITEMS_UNKNOWN

    def _hit_track(self, x: int, y: int) -> int | None:
        for tid, bbox in self._tracks.items():
            x1, y1, x2, y2 = [int(v) for v in bbox]
            if x1 <= x <= x2 and y1 <= y <= y2:
                return tid
        return None

    def _on_left_click(self, x: int, y: int) -> None:
        tid = self._hit_track(x, y)
        if tid is None:
            return

        identity = self._identities.get(tid)
        now      = time.monotonic()
        last_tid, last_t = self._last_click

        is_double = (tid == last_tid and now - last_t <= _DBL_SEC)
        self._last_click = (tid, now)

        if is_double and identity and identity.status == "known":
            self._event = MouseEvent(MouseAction.RENAME, tid)
        elif not is_double and identity and identity.status != "known":
            self._event = MouseEvent(MouseAction.REGISTER, tid)

    def _on_right_click(self, x: int, y: int) -> None:
        tid = self._hit_track(x, y)
        if tid is None:
            self.close_menu()
            return
        self._menu_track  = tid
        self._menu_pos    = (x, y)
        self._menu_open   = True
        self._hovered_item = -1

    def _menu_hit(self, x: int, y: int) -> int:
        item_h = 34
        pad    = 14
        w      = 200
        mx, my = self._menu_pos
        for i in range(len(self._menu_items())):
            iy1 = my + pad // 2 + i * item_h
            iy2 = iy1 + item_h
            if mx <= x <= mx + w and iy1 <= y <= iy2:
                return i
        return -1

    def _on_menu_click(self, x: int, y: int) -> None:
        idx = self._menu_hit(x, y)
        if idx >= 0:
            _, action = self._menu_items()[idx]
            self._event = MouseEvent(action, self._menu_track)
        self.close_menu()
