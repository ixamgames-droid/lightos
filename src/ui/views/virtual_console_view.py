"""Virtual Console tab — toolbar + scrollable canvas."""
from __future__ import annotations
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QToolBar,
                                QScrollArea, QPushButton, QLabel, QSizePolicy,
                                QToolButton)
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QAction

from src.ui.virtualconsole.vc_canvas import VCCanvas


class VirtualConsoleView(QWidget):
    """Full Virtual Console tab: edit-mode toggle + canvas."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._edit_mode = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Toolbar ──────────────────────────────────────────────────────────
        toolbar = QWidget()
        toolbar.setFixedHeight(36)
        toolbar.setStyleSheet("background:#161b22; border-bottom:1px solid #30363d;")
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(8, 2, 8, 2)
        tb_layout.setSpacing(6)

        self._btn_edit = QPushButton("Bearbeiten")
        self._btn_edit.setCheckable(True)
        self._btn_edit.setChecked(False)
        self._btn_edit.setFixedSize(90, 28)
        self._btn_edit.setStyleSheet("""
            QPushButton { background:#21262d; color:#e6edf3; border:1px solid #30363d;
                          border-radius:3px; font-size:11px; }
            QPushButton:checked { background:#0d4f8b; color:#58d68d; border-color:#1f6feb; }
            QPushButton:hover { background:#30363d; }
        """)
        self._btn_edit.toggled.connect(self._toggle_edit)
        tb_layout.addWidget(self._btn_edit)

        tb_layout.addSpacing(12)

        # Widget quick-add buttons
        widget_buttons = [
            ("Button",    "VCButton"),
            ("Fader",     "VCSlider"),
            ("XY Pad",    "VCXYPad"),
            ("Cue List",  "VCCueList"),
            ("SpeedDial", "VCSpeedDial"),
            ("Label",     "VCLabel"),
            ("Frame",     "VCFrame"),
        ]
        for label, wtype in widget_buttons:
            btn = QPushButton(label)
            btn.setFixedHeight(26)
            btn.setStyleSheet("""
                QPushButton { background:#21262d; color:#8b949e; border:1px solid #30363d;
                              border-radius:3px; font-size:10px; padding:0 8px; }
                QPushButton:hover { background:#30363d; color:#e6edf3; }
                QPushButton:disabled { color:#484f58; }
            """)
            btn.clicked.connect(lambda checked=False, wt=wtype: self._add_widget(wt))
            btn.setEnabled(False)
            btn.setProperty("add_btn", True)
            tb_layout.addWidget(btn)

        tb_layout.addStretch()

        btn_clear = QPushButton("Alle löschen")
        btn_clear.setFixedHeight(26)
        btn_clear.setStyleSheet("""
            QPushButton { background:#21262d; color:#f85149; border:1px solid #30363d;
                          border-radius:3px; font-size:10px; padding:0 8px; }
            QPushButton:hover { background:#30363d; }
        """)
        btn_clear.clicked.connect(self._clear_all)
        tb_layout.addWidget(btn_clear)

        btn_save = QPushButton("Speichern")
        btn_save.setFixedHeight(26)
        btn_save.setStyleSheet("""
            QPushButton { background:#21262d; color:#3fb950; border:1px solid #30363d;
                          border-radius:3px; font-size:10px; padding:0 8px; }
            QPushButton:hover { background:#30363d; }
        """)
        btn_save.clicked.connect(self._save)
        tb_layout.addWidget(btn_save)

        btn_load = QPushButton("Laden")
        btn_load.setFixedHeight(26)
        btn_load.setStyleSheet("""
            QPushButton { background:#21262d; color:#58a6ff; border:1px solid #30363d;
                          border-radius:3px; font-size:10px; padding:0 8px; }
            QPushButton:hover { background:#30363d; }
        """)
        btn_load.clicked.connect(self._load)
        tb_layout.addWidget(btn_load)

        layout.addWidget(toolbar)

        # ── Scroll area + Canvas ──────────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(False)
        scroll.setStyleSheet("QScrollArea { border:none; background:#0d1117; }")

        self._canvas = VCCanvas()
        scroll.setWidget(self._canvas)
        layout.addWidget(scroll)

        self._toolbar_widget = toolbar

    # ── Edit mode ────────────────────────────────────────────────────────────

    def _toggle_edit(self, enabled: bool):
        self._edit_mode = enabled
        self._btn_edit.setText("Bearbeiten ✓" if enabled else "Bearbeiten")
        self._canvas.set_edit_mode(enabled)
        for btn in self._toolbar_widget.findChildren(QPushButton):
            if btn.property("add_btn"):
                btn.setEnabled(enabled)

    # ── Widget actions ────────────────────────────────────────────────────────

    def _add_widget(self, wtype: str):
        if not self._edit_mode:
            return
        from PySide6.QtCore import QPoint
        center = QPoint(self._canvas.width() // 2, self._canvas.height() // 2)
        self._canvas._add_widget(wtype, center)

    def _clear_all(self):
        if self._edit_mode:
            self._canvas._clear()

    def _save(self):
        self._canvas._save()

    def _load(self):
        self._canvas._load()

    # ── Public serialization ──────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return self._canvas.to_dict()

    def from_dict(self, d: dict):
        self._canvas.from_dict(d)
