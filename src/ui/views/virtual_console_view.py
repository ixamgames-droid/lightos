"""Virtual Console tab — toolbar + scrollable canvas."""
from __future__ import annotations
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QToolBar,
                                QScrollArea, QPushButton, QLabel, QSizePolicy,
                                QToolButton, QCheckBox, QMainWindow, QFrame)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon, QAction

from src.ui.virtualconsole.vc_canvas import VCCanvas


_BTN_BASE = """
    QPushButton { background:#21262d; color:%s; border:1px solid #30363d;
                  border-radius:3px; font-size:10px; padding:0 8px; }
    QPushButton:hover { background:#30363d; color:#e6edf3; }
    QPushButton:disabled { color:#484f58; }
"""


class VCPopoutWindow(QMainWindow):
    """Eigenstaendiges Fenster, das den VCCanvas beherbergt (Popout-Modus)."""

    closed = Signal()

    def __init__(self, canvas: VCCanvas, scroll_area: QScrollArea, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Virtual Console — Popout")
        self.setWindowFlags(Qt.WindowType.Window)
        self.resize(1280, 820)
        self._scroll = scroll_area
        self._canvas = canvas
        # Canvas aus ScrollArea herausnehmen und in dieses Fenster einbetten
        scroll_area.takeWidget()
        self.setCentralWidget(canvas)
        canvas.show()

    def closeEvent(self, event):
        # Canvas sicher zurueck in die ScrollArea legen
        self._scroll.setWidget(self._canvas)
        self.closed.emit()
        super().closeEvent(event)


class VirtualConsoleView(QWidget):
    """Full Virtual Console tab: edit-mode toggle + canvas."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._edit_mode = False
        self._popout_win: VCPopoutWindow | None = None
        self._apc_feedback = None
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

        tb_layout.addSpacing(8)

        self._chk_snap = QCheckBox("Snap on Grid")
        self._chk_snap.setChecked(True)
        self._chk_snap.setEnabled(False)
        self._chk_snap.setStyleSheet("""
            QCheckBox { color:#8b949e; font-size:11px; }
            QCheckBox:enabled { color:#e6edf3; }
            QCheckBox::indicator { width:13px; height:13px;
                border:1px solid #30363d; border-radius:2px;
                background:#21262d; }
            QCheckBox::indicator:checked { background:#0d4f8b;
                border-color:#1f6feb; }
        """)
        self._chk_snap.toggled.connect(self._canvas_snap_changed)
        tb_layout.addWidget(self._chk_snap)

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
            btn.setStyleSheet(_BTN_BASE % "#8b949e")
            btn.clicked.connect(lambda checked=False, wt=wtype: self._add_widget(wt))
            btn.setEnabled(False)
            btn.setProperty("add_btn", True)
            tb_layout.addWidget(btn)

        tb_layout.addStretch()

        # APC Mini Feedback-Button
        self._btn_apc = QPushButton("APC LEDs")
        self._btn_apc.setFixedHeight(26)
        self._btn_apc.setCheckable(True)
        self._btn_apc.setStyleSheet("""
            QPushButton { background:#21262d; color:#f0883e; border:1px solid #30363d;
                          border-radius:3px; font-size:10px; padding:0 8px; }
            QPushButton:checked { background:#3d1f00; color:#f0883e; border-color:#f0883e; }
            QPushButton:hover { background:#30363d; }
        """)
        self._btn_apc.clicked.connect(self._toggle_apc_feedback)
        tb_layout.addWidget(self._btn_apc)

        # Popout-Button
        self._btn_popout = QPushButton("Popout")
        self._btn_popout.setFixedHeight(26)
        self._btn_popout.setStyleSheet("""
            QPushButton { background:#21262d; color:#79c0ff; border:1px solid #30363d;
                          border-radius:3px; font-size:10px; padding:0 8px; }
            QPushButton:hover { background:#30363d; color:#e6edf3; }
        """)
        self._btn_popout.clicked.connect(self._toggle_popout)
        tb_layout.addWidget(self._btn_popout)

        btn_clear = QPushButton("Alle loeschen")
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
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(False)
        self._scroll.setStyleSheet("QScrollArea { border:none; background:#0d1117; }")

        self._canvas = VCCanvas()
        self._scroll.setWidget(self._canvas)
        layout.addWidget(self._scroll)

        self._toolbar_widget = toolbar

    # ── Edit mode ────────────────────────────────────────────────────────────

    def _toggle_edit(self, enabled: bool):
        self._edit_mode = enabled
        self._btn_edit.setText("Bearbeiten ✓" if enabled else "Bearbeiten")
        self._canvas.set_edit_mode(enabled)
        self._chk_snap.setEnabled(enabled)
        for btn in self._toolbar_widget.findChildren(QPushButton):
            if btn.property("add_btn"):
                btn.setEnabled(enabled)

    def _canvas_snap_changed(self, checked: bool):
        self._canvas.set_snap_to_grid(checked)

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

    # ── Popout-Fenster ────────────────────────────────────────────────────────

    def _toggle_popout(self):
        if self._popout_win is not None:
            self._popout_win.close()
            return
        self._popout_win = VCPopoutWindow(self._canvas, self._scroll, parent=None)
        self._popout_win.closed.connect(self._on_popout_closed)
        self._popout_win.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._popout_win.show()
        self._btn_popout.setText("Einbetten")
        self._btn_popout.setStyleSheet("""
            QPushButton { background:#0d4f8b; color:#79c0ff; border:1px solid #1f6feb;
                          border-radius:3px; font-size:10px; padding:0 8px; }
            QPushButton:hover { background:#1f6feb; }
        """)

    def _on_popout_closed(self):
        self._popout_win = None
        self._btn_popout.setText("Popout")
        self._btn_popout.setStyleSheet("""
            QPushButton { background:#21262d; color:#79c0ff; border:1px solid #30363d;
                          border-radius:3px; font-size:10px; padding:0 8px; }
            QPushButton:hover { background:#30363d; color:#e6edf3; }
        """)

    # ── APC Mini LED Feedback ─────────────────────────────────────────────────

    def _toggle_apc_feedback(self, checked: bool):
        if checked:
            self._start_apc_feedback()
        else:
            self._stop_apc_feedback()

    def _start_apc_feedback(self):
        try:
            from src.core.midi.apc_mini_feedback import APCMiniFeedback
            from src.core.app_state import get_state
            if self._apc_feedback is not None:
                self._apc_feedback.close()
            fb = APCMiniFeedback(port_hint="APC")
            fb.attach(get_state())
            self._apc_feedback = fb
            if not fb.is_connected:
                self._btn_apc.setChecked(False)
                print("[VirtualConsoleView] APC Mini Output nicht gefunden.")
        except Exception as e:
            self._btn_apc.setChecked(False)
            print(f"[VirtualConsoleView] APC Feedback Fehler: {e}")

    def _stop_apc_feedback(self):
        if self._apc_feedback is not None:
            self._apc_feedback.close()
            self._apc_feedback = None

    def closeEvent(self, event):
        self._stop_apc_feedback()
        if self._popout_win is not None:
            self._popout_win.close()
        super().closeEvent(event)

    # ── Public serialization ──────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return self._canvas.to_dict()

    def from_dict(self, d: dict):
        self._canvas.from_dict(d)
