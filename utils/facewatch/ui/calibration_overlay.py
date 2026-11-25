import multiprocessing
import sys
import time
from dataclasses import dataclass


@dataclass
class OverlayColors:
    dot_idle:   tuple  # RGB — pulse phase
    dot_active: tuple  # RGB — capture phase / tune collecting
    text:       tuple  # RGB
    bar_bg:     tuple  # RGB
    bar_fill:   tuple  # RGB


_DOT_RADIUS = 18
_ARC_RADIUS = 36
_BAR_W      = 300
_BAR_H      = 12
_PULSE_MIN  = 12
_PULSE_MAX  = 24


def _run_calibration_overlay(conn, colors: OverlayColors) -> None:
    import math
    from PyQt6.QtCore import Qt, QTimer, QRect, QRectF
    from PyQt6.QtGui import QColor, QPainter, QPen, QBrush, QFont
    from PyQt6.QtWidgets import QApplication, QWidget

    app    = QApplication(sys.argv)
    screen = app.primaryScreen().geometry()
    sw, sh = screen.width(), screen.height()
    cx, cy = sw // 2, sh // 2
    conn.send({"type": "screen", "w": sw, "h": sh})

    visible = False
    state: dict = {
        "samples": 0, "needed": 9,
        "instruction": "", "accepted": False,
        "dot_rx": None, "dot_ry": None,   # normalized 0-1 ratios
        "phase_t": 0.0, "is_tune": False,
    }
    gaze_targets: dict = {}
    gaze_current: dict = {}
    _SMOOTH = 0.12

    class Window(QWidget):
        def __init__(self):
            super().__init__()
            self.setGeometry(screen)
            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint |
                Qt.WindowType.WindowStaysOnTopHint |
                Qt.WindowType.Tool |
                Qt.WindowType.WindowTransparentForInput
            )
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            self.show()

        def paintEvent(self, _):
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            if visible:
                # Full black background during calibration
                painter.setBrush(QBrush(QColor(0, 0, 0, 255)))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRect(0, 0, sw, sh)
                self._draw_dot(painter)
                self._draw_info_panel(painter)
            for fid, pos in list(gaze_current.items()):
                if fid in gaze_targets:
                    self._draw_gaze_pointer(painter, int(pos[0]), int(pos[1]))
            painter.end()

        def _draw_dot(self, painter: QPainter):
            rx = state.get("dot_rx")
            ry = state.get("dot_ry")
            if rx is None or ry is None:
                return
            dx       = int(rx * sw)
            dy       = int(ry * sh)
            accepted = state.get("accepted", False)
            phase_t  = state.get("phase_t", 0.0)

            if not accepted:
                radius = _PULSE_MIN + int((_PULSE_MAX - _PULSE_MIN) * abs(math.sin(phase_t * math.pi * 2)))
            else:
                radius = _DOT_RADIUS

            dot_color = colors.dot_active if accepted else colors.dot_idle
            painter.setBrush(QBrush(QColor(*dot_color, 220)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(dx - radius, dy - radius, radius * 2, radius * 2)

            if accepted and phase_t > 0.0:
                arc_span = int(360 * (1.0 - phase_t) * 16)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(QColor(255, 255, 255, 200), 3))
                rect = QRectF(dx - _ARC_RADIUS, dy - _ARC_RADIUS,
                              _ARC_RADIUS * 2, _ARC_RADIUS * 2)
                painter.drawArc(rect, 90 * 16, arc_span)

        def _draw_info_panel(self, painter: QPainter):
            samples = state.get("samples", 0)
            needed  = state.get("needed", 1)
            instr   = state.get("instruction", "")
            is_tune = state.get("is_tune", False)
            title   = "TUNE" if is_tune else "GAZE CALIBRATION"

            pw, ph = 500, 160
            px = cx - pw // 2
            py = sh - ph - 40

            painter.setBrush(QBrush(QColor(20, 20, 20, 230)))
            painter.setPen(QPen(QColor(0, 220, 180, 200), 1))
            painter.drawRoundedRect(px, py, pw, ph, 12, 12)

            font = QFont("Arial", 13)
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QColor(0, 220, 180, 230))
            painter.drawText(QRect(px, py + 14, pw, 28),
                             Qt.AlignmentFlag.AlignCenter, title)

            bx = px + 20
            by = py + 52
            bw = pw - 40
            painter.setBrush(QBrush(QColor(*colors.bar_bg, 160)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(bx, by, bw, _BAR_H, 4, 4)
            filled = int(bw * min(1.0, samples / max(needed, 1)))
            if filled > 0:
                painter.setBrush(QBrush(QColor(*colors.bar_fill, 220)))
                painter.drawRoundedRect(bx, by, filled, _BAR_H, 4, 4)

            font2 = QFont("Arial", 11)
            painter.setFont(font2)
            painter.setPen(QColor(*colors.text, 200))
            painter.drawText(QRect(bx, by + _BAR_H + 6, bw, 20),
                             Qt.AlignmentFlag.AlignCenter, f"{samples} / {needed}")

            font3 = QFont("Arial", 12)
            painter.setFont(font3)
            painter.setPen(QColor(*colors.text, 220))
            painter.drawText(QRect(px, py + 110, pw, 30),
                             Qt.AlignmentFlag.AlignCenter, instr)

        def _draw_gaze_pointer(self, painter: QPainter, gx: int, gy: int):
            r = 8
            painter.setBrush(QBrush(QColor(255, 80, 80, 200)))
            painter.setPen(QPen(QColor(255, 255, 255, 180), 1))
            painter.drawEllipse(gx - r, gy - r, r * 2, r * 2)

    win = Window()

    def tick():
        nonlocal visible, state
        while conn.poll():
            msg = conn.recv()
            if msg is None:
                app.quit()
                return
            if msg.get("type") == "gaze":
                fid = msg["face_id"]
                if msg["visible"]:
                    tx, ty = msg["x"], msg["y"]
                    gaze_targets[fid] = {"x": tx, "y": ty}
                    if fid not in gaze_current:
                        gaze_current[fid] = [float(tx), float(ty)]
                else:
                    gaze_targets.pop(fid, None)
                    gaze_current.pop(fid, None)
            else:
                visible = msg.get("visible", False)
                if "samples" in msg:
                    state = msg
        for fid, target in list(gaze_targets.items()):
            cur = gaze_current[fid]
            cur[0] += (target["x"] - cur[0]) * _SMOOTH
            cur[1] += (target["y"] - cur[1]) * _SMOOTH
        win.update()

    timer = QTimer()
    timer.timeout.connect(tick)
    timer.start(1000 // 30)
    app.exec()


class CalibrationOverlay:
    def __init__(self):
        self._colors = OverlayColors(
            dot_idle   = (160, 160, 160),
            dot_active = (0,   220, 180),
            text       = (255, 255, 255),
            bar_bg     = (60,  60,  60),
            bar_fill   = (0,   220, 180),
        )
        self._parent_conn, self._child_conn = multiprocessing.Pipe()
        self._process: multiprocessing.Process | None = None
        self._screen_size: tuple[int, int] | None = None

    def screen_size(self, timeout: float = 30.0) -> tuple[int, int] | None:
        """
        Primary screen (w, h) in the overlay's drawing pixels, as reported by the
        overlay process once Qt is up. Blocks up to `timeout` on the first call;
        cached afterwards. None if the overlay never reported.
        """
        if self._screen_size is not None:
            return self._screen_size
        if not (self._process and self._process.is_alive()):
            return None
        deadline = time.monotonic() + timeout
        try:
            while (remaining := deadline - time.monotonic()) > 0:
                if not self._parent_conn.poll(remaining):
                    break
                msg = self._parent_conn.recv()
                if isinstance(msg, dict) and msg.get("type") == "screen":
                    self._screen_size = (int(msg["w"]), int(msg["h"]))
                    break
        except (EOFError, OSError):
            pass
        return self._screen_size

    def start(self) -> None:
        if self._process and self._process.is_alive():
            return
        self._process = multiprocessing.Process(
            target=_run_calibration_overlay,
            args=(self._child_conn, self._colors),
            daemon=True,
        )
        self._process.start()

    def stop(self) -> None:
        if self._process and self._process.is_alive():
            self._process.terminate()
            self._process.join(timeout=2)

    def show(self, samples: int, needed: int, instruction: str, accepted: bool,
             dot_rx: float | None = None, dot_ry: float | None = None,
             phase_t: float = 0.0, is_tune: bool = False) -> None:
        if not (self._process and self._process.is_alive()):
            return
        try:
            self._parent_conn.send({
                "visible":     True,
                "samples":     samples,
                "needed":      needed,
                "instruction": instruction,
                "accepted":    accepted,
                "dot_rx":      dot_rx,
                "dot_ry":      dot_ry,
                "phase_t":     phase_t,
                "is_tune":     is_tune,
            })
        except Exception:
            pass

    def hide(self) -> None:
        if not (self._process and self._process.is_alive()):
            return
        try:
            self._parent_conn.send({"visible": False})
        except Exception:
            pass

    def show_gaze(self, face_id: int, sx: float, sy: float) -> None:
        if not (self._process and self._process.is_alive()):
            return
        try:
            self._parent_conn.send({
                "type": "gaze", "face_id": face_id,
                "visible": True, "x": int(sx), "y": int(sy),
            })
        except Exception:
            pass

    def hide_gaze(self, face_id: int) -> None:
        if not (self._process and self._process.is_alive()):
            return
        try:
            self._parent_conn.send({"type": "gaze", "face_id": face_id,
                                    "visible": False, "x": 0, "y": 0})
        except Exception:
            pass
