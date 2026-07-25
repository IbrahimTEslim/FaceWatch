import sys
from config_defaults import DEFAULTS

# category display order
_CATEGORY_ORDER = [
    "camera", "recognition", "gaze", "proximity",
    "expressions", "focus", "demographics", "report", "ui", "keys", "storage", "models",
]


def open_settings(db_path: str) -> None:
    """Open the settings dialog. Blocks until closed. Writes changes directly to DB."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QFont, QIntValidator, QDoubleValidator
    from PyQt6.QtWidgets import (
        QApplication, QDialog, QHBoxLayout, QVBoxLayout, QListWidget,
        QListWidgetItem, QScrollArea, QWidget, QLabel, QLineEdit,
        QCheckBox, QPushButton, QFrame, QSizePolicy,
    )
    import sqlite3

    app = QApplication.instance() or QApplication(sys.argv)

    # Group defaults by category preserving order
    categories: dict[str, list] = {}
    for entry in DEFAULTS:
        key, default, type_, description, category = entry
        categories.setdefault(category, []).append(entry)

    ordered_cats = [c for c in _CATEGORY_ORDER if c in categories]
    for c in categories:
        if c not in ordered_cats:
            ordered_cats.append(c)

    # Read current values from DB
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    def db_get(key: str, default) -> str:
        row = conn.execute("SELECT value FROM config WHERE key=?", (key,)).fetchone()
        return row["value"] if row else str(default)

    def db_set(key: str, value: str) -> None:
        conn.execute("UPDATE config SET value=? WHERE key=?", (value, key))
        conn.commit()

    def db_reset(keys: list[str], defaults: dict[str, str]) -> None:
        for k in keys:
            conn.execute("UPDATE config SET value=? WHERE key=?", (defaults[k], k))
        conn.commit()

    # ── Dialog ────────────────────────────────────────────────────────────────
    dlg = QDialog()
    dlg.setWindowTitle("FaceWatch — Settings")
    dlg.setMinimumSize(780, 520)
    dlg.setStyleSheet("""
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
    """)

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

    # Right panel
    right = QVBoxLayout()
    right.setContentsMargins(24, 20, 24, 16)
    right.setSpacing(0)

    scroll_area = QScrollArea()
    scroll_area.setWidgetResizable(True)
    scroll_content = QWidget()
    scroll_layout = QVBoxLayout(scroll_content)
    scroll_layout.setSpacing(14)
    scroll_layout.setContentsMargins(0, 0, 12, 0)
    scroll_area.setWidget(scroll_content)

    # Track widgets: key -> (widget, type_)
    widgets: dict[str, tuple] = {}
    current_cat: list[str] = [ordered_cats[0] if ordered_cats else ""]

    def build_category(cat: str) -> None:
        # Clear scroll layout
        while scroll_layout.count():
            item = scroll_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        widgets.clear()
        current_cat[0] = cat

        for key, default, type_, description, _ in categories.get(cat, []):
            row = QWidget()
            row_layout = QVBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(2)

            lbl = QLabel(key.replace("_", " ").title())
            lbl.setFont(QFont("Arial", 11, QFont.Weight.Medium))

            desc_lbl = QLabel(description)
            desc_lbl.setObjectName("desc")
            desc_lbl.setWordWrap(True)

            current_val = db_get(key, default)

            if type_ == "bool":
                widget = QCheckBox()
                widget.setChecked(current_val.lower() in ("true", "1", "yes"))
            else:
                widget = QLineEdit(current_val)
                if type_ == "int":
                    widget.setValidator(QIntValidator())
                elif type_ == "float":
                    widget.setValidator(QDoubleValidator())
                widget.setFixedWidth(260)

            widgets[key] = (widget, type_)
            row_layout.addWidget(lbl)
            row_layout.addWidget(desc_lbl)
            row_layout.addWidget(widget)

            sep = QFrame()
            sep.setObjectName("sep")
            sep.setFrameShape(QFrame.Shape.HLine)
            sep.setFixedHeight(1)

            scroll_layout.addWidget(row)
            scroll_layout.addWidget(sep)

        scroll_layout.addStretch()

    # Bottom buttons
    btn_row = QHBoxLayout()
    btn_save   = QPushButton("Save")
    btn_reset  = QPushButton("Reset category")
    btn_cancel = QPushButton("Cancel")
    btn_reset.setObjectName("reset")
    btn_cancel.setObjectName("cancel")
    btn_row.addWidget(btn_reset)
    btn_row.addStretch()
    btn_row.addWidget(btn_cancel)
    btn_row.addWidget(btn_save)

    right.addWidget(scroll_area)
    right.addSpacing(12)
    right.addLayout(btn_row)

    right_widget = QWidget()
    right_widget.setLayout(right)

    root.addWidget(sidebar)

    divider = QFrame()
    divider.setObjectName("sep")
    divider.setFrameShape(QFrame.Shape.VLine)
    divider.setFixedWidth(1)
    root.addWidget(divider)
    root.addWidget(right_widget)

    # ── Signals ───────────────────────────────────────────────────────────────
    def on_category_changed(item: QListWidgetItem) -> None:
        build_category(item.data(Qt.ItemDataRole.UserRole))

    def on_save() -> None:
        for key, (widget, type_) in widgets.items():
            if isinstance(widget, QCheckBox):
                db_set(key, str(widget.isChecked()))
            else:
                db_set(key, widget.text())
        dlg.accept()

    def on_reset() -> None:
        cat = current_cat[0]
        defaults_map = {e[0]: str(e[1]) for e in categories.get(cat, [])}
        db_reset(list(defaults_map.keys()), defaults_map)
        build_category(cat)

    sidebar.currentItemChanged.connect(on_category_changed)
    btn_save.clicked.connect(on_save)
    btn_reset.clicked.connect(on_reset)
    btn_cancel.clicked.connect(dlg.reject)

    # Select first category
    if sidebar.count():
        sidebar.setCurrentRow(0)
        build_category(ordered_cats[0])

    dlg.exec()
    conn.close()
