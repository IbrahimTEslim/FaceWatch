from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QScrollArea, QWidget, QVBoxLayout, QLabel, QFrame,
)
from .widgets import build_input, read_widget


class CategoryPanel:
    """
    Builds and owns the scroll area for one settings category.
    Call flush() before switching away to persist edits into pending.
    """

    def __init__(self, entries: list, pending: dict[str, str], category: str):
        self._entries  = entries
        self._pending  = pending
        self._category = category
        self._widgets: dict[str, tuple] = {}   # key -> (widget, type_)
        self.scroll_area = self._build()

    def _build(self) -> QScrollArea:
        content = QWidget()
        layout  = QVBoxLayout(content)
        layout.setSpacing(14)
        layout.setContentsMargins(0, 0, 12, 0)

        for key, default, type_, description, _ in self._entries:
            current_val = self._pending.get(key, "")

            row    = QWidget()
            rl     = QVBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(2)

            lbl = QLabel(key.replace("_", " ").title())
            lbl.setFont(QFont("Arial", 11, QFont.Weight.Medium))

            widget, hint = build_input(key, type_, current_val, self._category, description)
            desc_text    = f"{description}  {hint}" if hint else description
            desc_lbl     = QLabel(desc_text)
            desc_lbl.setObjectName("desc")
            desc_lbl.setWordWrap(True)

            self._widgets[key] = (widget, type_)
            rl.addWidget(lbl)
            rl.addWidget(desc_lbl)
            rl.addWidget(widget)

            sep = QFrame()
            sep.setObjectName("sep")
            sep.setFrameShape(QFrame.Shape.HLine)
            sep.setFixedHeight(1)

            layout.addWidget(row)
            layout.addWidget(sep)

        layout.addStretch()

        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setWidget(content)
        return area

    def flush(self) -> None:
        """Write current widget values into the shared pending dict."""
        for key, (widget, type_) in self._widgets.items():
            self._pending[key] = read_widget(key, widget, type_)
