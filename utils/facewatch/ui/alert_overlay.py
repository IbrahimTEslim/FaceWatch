import math
import multiprocessing
import sys
from dataclasses import dataclass

from alerts.base import AlertPriority
from storage.config_store import ConfigStore


@dataclass
class DrawConfig:
    colors:       dict   # dict[AlertPriority, tuple[int,int,int]] RGB
    border_width: int
    cycle_sec:    float
    max_alpha:    int


def _bgr_to_rgb(bgr_str: str) -> tuple:
    b, g, r = [int(x) for x in bgr_str.split(",")]
    return (r, g, b)


# ── Child process entry point ─────────────────────────────────────────────────

def _run_overlay(conn, cfg: DrawConfig) -> None:
    from PyQt6.QtCore import Qt, QTimer
    from PyQt6.QtGui import QColor, QPainter, QPen
    from PyQt6.QtWidgets import QApplication, QWidget

    app = QApplication(sys.argv)

    active_priorities: set[AlertPriority] = set()
    elapsed = 0.0
    fps     = 30

    screen = app.primaryScreen().geometry()

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
            if not active_priorities:
                return
            pulse  = abs(math.sin(math.pi * elapsed / cfg.cycle_sec))
            alpha  = int(pulse * cfg.max_alpha)
            colors = [cfg.colors[p] for p in AlertPriority if p in active_priorities]

            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            for i, rgb in enumerate(colors):
                offset = i * (cfg.border_width + 2) + cfg.border_width // 2
                c = QColor(*rgb)
                c.setAlpha(alpha)
                painter.setPen(QPen(c, cfg.border_width))
                painter.drawRect(offset, offset,
                                 self.width()  - offset * 2,
                                 self.height() - offset * 2)
            painter.end()

    win = Window()

    def tick():
        nonlocal active_priorities, elapsed
        while conn.poll():
            active_priorities = conn.recv()
            if not active_priorities:
                elapsed = 0.0
        if active_priorities:
            elapsed += 1.0 / fps
        win.update()

    timer = QTimer()
    timer.timeout.connect(tick)
    timer.start(1000 // fps)
    app.exec()


# ── Public API ────────────────────────────────────────────────────────────────

class AlertOverlay:
    def __init__(self, config: ConfigStore):
        self._enabled = config.get("alert_overlay_enabled")
        self._cfg     = DrawConfig(
            colors={
                p: _bgr_to_rgb(config.get(f"alert_color_{p.value}"))
                for p in AlertPriority
            },
            border_width = config.get("alert_border_width"),
            cycle_sec    = config.get("alert_cycle_sec"),
            max_alpha    = config.get("alert_max_alpha"),
        )
        self._parent_conn, self._child_conn = multiprocessing.Pipe()
        self._process: multiprocessing.Process | None = None

    def start(self) -> None:
        if not self._enabled or (self._process and self._process.is_alive()):
            return
        self._process = multiprocessing.Process(
            target=_run_overlay,
            args=(self._child_conn, self._cfg),
            daemon=True,
        )
        self._process.start()

    def stop(self) -> None:
        if self._process and self._process.is_alive():
            self._process.terminate()
            self._process.join(timeout=2)

    def set_active_priorities(self, priorities: set[AlertPriority]) -> None:
        if not self._enabled or not (self._process and self._process.is_alive()):
            return
        try:
            self._parent_conn.send(priorities)
        except Exception:
            pass
