import multiprocessing
import sys
from dataclasses import dataclass


@dataclass
class OverlayColors:
    crosshair_idle:   tuple  # RGB
    crosshair_active: tuple  # RGB
    text:             tuple  # RGB
    bar_bg:           tuple  # RGB
    bar_fill:         tuple  # RGB


_CROSSHAIR_SIZE = 40
_DOT_RADIUS     = 8
_BAR_W          = 300
_BAR_H          = 12


def _run_calibration_overlay(conn, colors: OverlayColors) -> None:
    from PyQt6.QtCore import Qt, QTimer, QRect
    from PyQt6.QtGui import QColor, QPainter, QPen, QBrush, QFont
    from PyQt6.QtWidgets import QApplication, QWidget

    app    = QApplication(sys.argv)
    screen = app.primaryScreen().geometry()
    cx     = screen.width()  // 2
    cy     = screen.height() // 2

    visible = False
    state: dict = {
        "samples":     0,
        "needed":      30,
        "instruction": "Look straight at the center of your screen and hold still.",
        "accepted":    False,
    }

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
            if not visible:
                return
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            self._draw_background(painter)
            self._draw_crosshair(painter)
            self._draw_progress(painter)
            self._draw_instruction(painter)
            painter.end()

        def _draw_background(self, painter: QPainter):
            pw, ph = 500, 220
            px = cx - pw // 2
            py = cy - 80
            painter.setBrush(QBrush(QColor(10, 10, 10, 180)))
            painter.setPen(QPen(QColor(0, 220, 180, 180), 1))
            painter.drawRoundedRect(px, py, pw, ph, 12, 12)
            font = QFont("Arial", 14)
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QColor(0, 220, 180, 230))
            painter.drawText(
                QRect(px, py + 16, pw, 30),
                Qt.AlignmentFlag.AlignCenter,
                "GAZE CALIBRATION",
            )

        def _draw_crosshair(self, painter: QPainter):
            color = colors.crosshair_active if state.get("accepted") else colors.crosshair_idle
            c = QColor(*color, 200)
            painter.setPen(QPen(c, 2))
            painter.drawLine(cx - _CROSSHAIR_SIZE, cy, cx + _CROSSHAIR_SIZE, cy)
            painter.drawLine(cx, cy - _CROSSHAIR_SIZE, cx, cy + _CROSSHAIR_SIZE)
            painter.setBrush(QBrush(QColor(*color, 220)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(cx - _DOT_RADIUS, cy - _DOT_RADIUS,
                                _DOT_RADIUS * 2, _DOT_RADIUS * 2)

        def _draw_progress(self, painter: QPainter):
            samples = state.get("samples", 0)
            needed  = state.get("needed", 1)
            bx = cx - _BAR_W // 2
            by = cy + 60
            painter.setBrush(QBrush(QColor(*colors.bar_bg, 160)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(bx, by, _BAR_W, _BAR_H, 4, 4)
            filled = int(_BAR_W * min(1.0, samples / needed))
            if filled > 0:
                painter.setBrush(QBrush(QColor(*colors.bar_fill, 220)))
                painter.drawRoundedRect(bx, by, filled, _BAR_H, 4, 4)
            font = QFont("Arial", 11)
            painter.setFont(font)
            painter.setPen(QColor(*colors.text, 200))
            painter.drawText(
                QRect(bx, by + _BAR_H + 6, _BAR_W, 20),
                Qt.AlignmentFlag.AlignCenter,
                f"{samples} / {needed}",
            )

        def _draw_instruction(self, painter: QPainter):
            font = QFont("Arial", 13)
            painter.setFont(font)
            painter.setPen(QColor(*colors.text, 220))
            painter.drawText(
                QRect(cx - 300, cy + 100, 600, 30),
                Qt.AlignmentFlag.AlignCenter,
                state.get("instruction", ""),
            )

    win = Window()

    def tick():
        nonlocal visible, state
        while conn.poll():
            msg = conn.recv()
            if msg is None:
                app.quit()
                return
            visible = msg.get("visible", False)
            if "samples" in msg:
                state = msg
        win.update()

    timer = QTimer()
    timer.timeout.connect(tick)
    timer.start(1000 // 30)
    app.exec()


class CalibrationOverlay:
    def __init__(self):
        self._colors = OverlayColors(
            crosshair_idle   = (160, 160, 160),
            crosshair_active = (0,   220, 180),
            text             = (255, 255, 255),
            bar_bg           = (60,  60,  60),
            bar_fill         = (0,   220, 180),
        )
        self._parent_conn, self._child_conn = multiprocessing.Pipe()
        self._process: multiprocessing.Process | None = None

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

    def show(self, samples: int, needed: int, instruction: str, accepted: bool) -> None:
        if not (self._process and self._process.is_alive()):
            return
        try:
            self._parent_conn.send({
                "visible":     True,
                "samples":     samples,
                "needed":      needed,
                "instruction": instruction,
                "accepted":    accepted,
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
