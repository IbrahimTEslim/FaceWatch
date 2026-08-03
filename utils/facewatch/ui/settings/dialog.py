import sys
import sqlite3
from config_defaults import DEFAULTS
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QApplication, QDialog, QHBoxLayout, QVBoxLayout,
    QListWidget, QListWidgetItem, QPushButton, QFrame, QWidget,
)
from .category_panel import CategoryPanel

_CATEGORY_ORDER = [
    "camera", "recognition", "gaze", "proximity",
    "expressions", "focus", "fatigue", "wellness",
    "demographics", "report", "ui", "keys", "storage", "models",
]

_STYLE = """
    QDialog        { background: #141414; color: #f0f0f0; }
    QListWidget    { background: #1a1a1a; border: none; font-size: 13px; }
    QListWidget::item { padding: 10px 16px; color: #aaa; }
    QListWidget::item:selected { background: #1e3a35; color: #00dcb4; border-left: 3px solid #00dcb4; }
    QListWidget::item:hover    { background: #222; color: #fff; }
    QLabel         { color: #f0f0f0; font-size: 12px; }
    QLabel#desc    { color: #888; font-size: 11px; }
    QLineEdit      { background: #222; border: 1px solid #333; border-radius: 4px;
                     color: #f0f0f0; padding: 4px 8px; font-size: 12px; }
    QLineEdit:focus { border-color: #00dcb4; }
    QCheckBox      { color: #f0f0f0; font-size: 12px; }
    QCheckBox::indicator { width: 16px; height: 16px; }
    QPushButton    { background: #1e3a35; color: #00dcb4; border: 1px solid #00dcb4;
                     border-radius: 4px; padding: 6px 18px; font-size: 12px; }
    QPushButton:hover  { background: #00dcb4; color: #000; }
    QPushButton#cancel { background: #222; color: #888; border-color: #444; }
    QPushButton#cancel:hover { background: #333; color: #fff; }
    QPushButton#reset  { background: #2a1a1a; color: #e05050; border-color: #e05050; }
    QPushButton#reset:hover  { background: #e05050; color: #fff; }
    QScrollArea    { border: none; }
    QFrame#sep     { background: #2a2a2a; }
"""


def open_settings(db_path: str, quit_key: str = "q") -> None:
    """Open the settings dialog. Blocks until closed.
    quit_key: pressing this key closes the dialog so the engine can quit.
    """
    app = QApplication.instance() or QApplication(sys.argv)

    # Group DEFAULTS by category
    categories: dict[str, list] = {}
    for entry in DEFAULTS:
        categories.setdefault(entry[4], []).append(entry)

    ordered_cats = [c for c in _CATEGORY_ORDER if c in categories]
    for c in categories:
        if c not in ordered_cats:
            ordered_cats.append(c)

    conn = sqlite3.connect(db_path, check_same_thread=False, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")

    # Pre-load all current DB values into pending
    pending: dict[str, str] = {}
    for entry in DEFAULTS:
        key, default = entry[0], entry[1]
        row = conn.execute("SELECT value FROM config WHERE key=?", (key,)).fetchone()
        pending[key] = row["value"] if row else str(default)

    # ── Dialog ────────────────────────────────────────────────────────────────
    dlg = QDialog()
    dlg.setWindowTitle("FaceWatch — Settings")
    dlg.setMinimumSize(820, 560)
    dlg.setStyleSheet(_STYLE)

    def keyPressEvent(event):
        if event.text() == quit_key:
            dlg.reject()
        else:
            QDialog.keyPressEvent(dlg, event)
    dlg.keyPressEvent = keyPressEvent

    root = QHBoxLayout(dlg)
    root.setContentsMargins(0, 0, 0, 0)
    root.setSpacing(0)

    # Sidebar
    sidebar = QListWidget()
    sidebar.setFixedWidth(170)
    for cat in ordered_cats:
        item = QListWidgetItem(cat.capitalize())
        item.setData(Qt.ItemDataRole.UserRole, cat)
        sidebar.addItem(item)

    # Right area: stacked panels + buttons
    right = QVBoxLayout()
    right.setContentsMargins(24, 20, 24, 16)
    right.setSpacing(0)

    panel_container = QWidget()
    panel_layout    = QVBoxLayout(panel_container)
    panel_layout.setContentsMargins(0, 0, 0, 0)

    # Buttons
    btn_save   = QPushButton("Save")
    btn_reset  = QPushButton("Reset category")
    btn_cancel = QPushButton("Cancel")
    btn_reset.setObjectName("reset")
    btn_cancel.setObjectName("cancel")
    btn_row = QHBoxLayout()
    btn_row.addWidget(btn_reset)
    btn_row.addStretch()
    btn_row.addWidget(btn_cancel)
    btn_row.addWidget(btn_save)

    right.addWidget(panel_container, stretch=1)
    right.addSpacing(12)
    right.addLayout(btn_row)

    right_widget = QWidget()
    right_widget.setLayout(right)

    div = QFrame()
    div.setObjectName("sep")
    div.setFrameShape(QFrame.Shape.VLine)
    div.setFixedWidth(1)

    root.addWidget(sidebar)
    root.addWidget(div)
    root.addWidget(right_widget)

    # Track active panel
    active_panel: list[CategoryPanel | None] = [None]

    def show_category(cat: str) -> None:
        if active_panel[0]:
            active_panel[0].flush()
        # Remove and destroy all widgets in the container
        while panel_layout.count():
            item = panel_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        panel = CategoryPanel(categories[cat], pending, cat)
        active_panel[0] = panel
        panel_layout.addWidget(panel.scroll_area)

    def on_category_changed(item: QListWidgetItem) -> None:
        show_category(item.data(Qt.ItemDataRole.UserRole))

    def on_save() -> None:
        if active_panel[0]:
            active_panel[0].flush()
        for key, value in pending.items():
            conn.execute("UPDATE config SET value=? WHERE key=?", (value, key))
        btn_save.setText("Saved ✓")
        QTimer.singleShot(1500, lambda: btn_save.setText("Save"))

    def on_reset() -> None:
        if not active_panel[0]:
            return
        cat = sidebar.currentItem().data(Qt.ItemDataRole.UserRole)
        for key, default, *_ in categories.get(cat, []):
            pending[key] = str(default)
            conn.execute("UPDATE config SET value=? WHERE key=?", (str(default), key))
        active_panel[0] = None
        show_category(cat)

    sidebar.currentItemChanged.connect(on_category_changed)
    btn_save.clicked.connect(on_save)
    btn_reset.clicked.connect(on_reset)
    btn_cancel.clicked.connect(dlg.reject)

    if ordered_cats:
        sidebar.setCurrentRow(0)
        show_category(ordered_cats[0])

    dlg.exec()
    conn.close()
