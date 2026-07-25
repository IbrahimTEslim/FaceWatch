from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QLineEdit, QPushButton, QCheckBox, QColorDialog,
    QSpinBox, QDoubleSpinBox,
)

# (min, max) bounds for int/float keys
LIMITS: dict[str, tuple] = {
    "camera_index":              (0,    10),
    "max_faces":                 (1,    20),
    "max_embeddings_per_face":   (1,    50),
    "stats_interval_sec":        (1,    300),
    "recognition_threshold":     (0.0,  1.0),
    "unknown_match_threshold":   (0.0,  1.0),
    "max_retry_attempts":        (1,    30),
    "retry_interval_sec":        (1,    60),
    "enrichment_interval_sec":   (1,    60),
    "gaze_alert_sec":            (1,    120),
    "gaze_return_sec":           (1,    60),
    "proximity_alert_cm":        (10.0, 200.0),
    "proximity_alert_sec":       (1,    60),
    "proximity_clear_sec":       (1,    120),
    "expr_threshold_blink":      (0.0,  1.0),
    "expr_threshold_smile":      (0.0,  1.0),
    "expr_threshold_angry":      (0.0,  1.0),
    "expr_threshold_surprised":  (0.0,  1.0),
    "expr_threshold_neutral":    (0.0,  1.0),
    "expr_threshold_drowsy":     (0.0,  1.0),
    "drowsy_window_sec":         (10,   300),
    "demographics_refresh_days": (1,    365),
    "report_port":               (1024, 65535),
    "focus_weight_gaze":         (0.0,  1.0),
    "focus_weight_drowsy":       (0.0,  1.0),
    "focus_weight_distraction":  (0.0,  1.0),
    "focus_weight_posture":      (0.0,  1.0),
    "focus_posture_min_cm":      (10.0, 200.0),
    "focus_posture_max_cm":      (10.0, 300.0),
    "alert_border_width":        (1,    40),
    "alert_cycle_sec":           (0.5,  10.0),
    "alert_max_alpha":           (0,    255),
}


def bgr_to_hex(bgr_str: str) -> str:
    try:
        b, g, r = [int(x) for x in bgr_str.split(",")]
        return f"#{r:02x}{g:02x}{b:02x}"
    except Exception:
        return "#ffffff"


def hex_to_bgr(hex_str: str) -> str:
    h = hex_str.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"{b},{g},{r}"


class KeyCaptureEdit(QLineEdit):
    """Captures the next key press on click."""
    def __init__(self, value: str):
        super().__init__(value)
        self.setPlaceholderText("Click then press a key…")
        self.setFixedWidth(120)
        self._captured = value

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Escape, Qt.Key.Key_Return,
                           Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
            super().keyPressEvent(event)
            return
        if event.text():
            self._captured = event.text()
            self.setText(event.text())
            self.clearFocus()

    def mousePressEvent(self, event):
        self.setFocus()
        self.selectAll()

    def text(self) -> str:
        return self._captured


class TimeListEdit(QLineEdit):
    """Only allows digits, colons and commas. Format: HH:MM,HH:MM"""
    def __init__(self, value: str):
        super().__init__(value)
        self.setPlaceholderText("HH:MM,HH:MM  e.g. 18:00,21:00")
        self.setFixedWidth(260)

    def keyPressEvent(self, event):
        allowed = set("0123456789:,")
        if event.key() in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete,
                           Qt.Key.Key_Left, Qt.Key.Key_Right,
                           Qt.Key.Key_Home, Qt.Key.Key_End):
            super().keyPressEvent(event)
            return
        if event.text() and event.text() not in allowed:
            return
        super().keyPressEvent(event)


def _make_spinbox(current_val: str, lo, hi) -> QSpinBox:
    w = QSpinBox()
    w.setStyleSheet(
        "QSpinBox { background:#222; border:1px solid #333; border-radius:4px;"
        " color:#f0f0f0; padding:4px 8px; font-size:12px; }"
        "QSpinBox:focus { border-color:#00dcb4; }"
    )
    w.setFixedWidth(160)
    w.setRange(int(lo) if lo is not None else 0,
               int(hi) if hi is not None else 999999)
    try:
        w.setValue(int(current_val))
    except ValueError:
        pass
    return w


def _make_doublespinbox(current_val: str, lo, hi) -> QDoubleSpinBox:
    w = QDoubleSpinBox()
    w.setStyleSheet(
        "QDoubleSpinBox { background:#222; border:1px solid #333; border-radius:4px;"
        " color:#f0f0f0; padding:4px 8px; font-size:12px; }"
        "QDoubleSpinBox:focus { border-color:#00dcb4; }"
    )
    w.setFixedWidth(160)
    w.setDecimals(4)
    w.setRange(float(lo) if lo is not None else 0.0,
               float(hi) if hi is not None else 999999.0)
    w.setSingleStep(0.01)
    try:
        w.setValue(float(current_val))
    except ValueError:
        pass
    return w


class ColorPickerButton(QPushButton):
    """Button that shows a color swatch and opens a color picker on click."""
    def __init__(self, bgr_str: str, parent=None):
        super().__init__(parent)
        self.setFixedSize(80, 28)
        self._set_color(bgr_to_hex(bgr_str))
        self.clicked.connect(self._pick)

    def _set_color(self, hex_color: str) -> None:
        self._hex = hex_color
        self.setStyleSheet(f"background:{hex_color}; border:1px solid #555; border-radius:4px;")

    def _pick(self) -> None:
        color = QColorDialog.getColor(QColor(self._hex), self.window(), "Pick color")
        if color.isValid():
            self._set_color(color.name())

    def value(self) -> str:
        return hex_to_bgr(self._hex)


def build_input(key: str, type_: str, current_val: str, category: str, desc: str) -> tuple:
    """Returns (widget, range_hint: str | None)."""
    if type_ == "bool":
        w = QCheckBox()
        w.setChecked(current_val.lower() in ("true", "1", "yes"))
        return w, None

    if "color" in key:
        return ColorPickerButton(current_val), None

    if category == "keys":
        return KeyCaptureEdit(current_val), None

    if key == "report_times":
        return TimeListEdit(current_val), None

    lo, hi = LIMITS.get(key, (None, None))
    hint = f"[{lo} – {hi}]" if lo is not None and hi is not None else None

    if type_ == "int":
        return _make_spinbox(current_val, lo, hi), hint

    if type_ == "float":
        return _make_doublespinbox(current_val, lo, hi), hint

    w = QLineEdit(current_val)
    w.setFixedWidth(260)
    return w, None


def read_widget(key: str, widget, type_: str) -> str:
    if isinstance(widget, QCheckBox):
        return str(widget.isChecked())
    if isinstance(widget, ColorPickerButton):
        return widget.value()
    if isinstance(widget, (QSpinBox, QDoubleSpinBox)):
        return str(widget.value())
    return widget.text()
