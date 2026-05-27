"""Virtual Console tab — toolbar + canvas + Snapshot-Sidebar."""
from __future__ import annotations
import os
import json
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QPushButton,
    QLabel, QSizePolicy, QSplitter, QListWidget, QListWidgetItem,
    QFrame, QMenu
)
from PySide6.QtCore import Qt, QPoint, QSize
from PySide6.QtGui import QColor, QCursor

from src.ui.virtualconsole.vc_canvas import VCCanvas

_SNAPSHOTS_FILE = os.path.join(
    os.environ.get("APPDATA", os.path.expanduser("~")), "LightOS", "snapshots.json"
)


# ─────────────────────────────────────────────────────────────────────────────
#  Snapshot-Sidebar
# ─────────────────────────────────────────────────────────────────────────────

class SnapshotSidebar(QWidget):
    """Rechte Seitenleiste mit der Snapshot-Übersicht."""

    def __init__(self, canvas: VCCanvas, parent=None):
        super().__init__(parent)
        self._canvas = canvas
        self._assign_snap_idx: int | None = None
        self._setup_ui()
        self.setMinimumWidth(180)
        self.setMaximumWidth(280)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # Header
        hdr = QLabel("Snapshots")
        hdr.setStyleSheet(
            "color:#ffd700; font-weight:bold; font-size:12px; padding:2px 0;"
        )
        layout.addWidget(hdr)

        btn_refresh = QPushButton("Aktualisieren")
        btn_refresh.setFixedHeight(22)
        btn_refresh.setStyleSheet(
            "QPushButton { background:#21262d; color:#8b949e; border:1px solid #30363d;"
            " border-radius:3px; font-size:10px; }"
            "QPushButton:hover { background:#30363d; color:#e6edf3; }"
        )
        btn_refresh.clicked.connect(self.refresh)
        layout.addWidget(btn_refresh)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color:#30363d;")
        layout.addWidget(sep)

        # Liste
        self._list = QListWidget()
        self._list.setStyleSheet(
            "QListWidget { background:#0d1117; border:1px solid #21262d;"
            " color:#c9d1d9; font-size:11px; }"
            "QListWidget::item { padding:6px 4px; border-bottom:1px solid #21262d; }"
            "QListWidget::item:selected { background:#1f6feb; color:#ffffff; }"
            "QListWidget::item:hover { background:#21262d; }"
        )
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._context_menu)
        self._list.itemDoubleClicked.connect(self._on_double_click)
        layout.addWidget(self._list, 1)

        # Buttons unten
        btn_apply = QPushButton("Apply")
        btn_apply.setFixedHeight(26)
        btn_apply.setToolTip("Ausgewählten Snapshot in den Programmer laden")
        btn_apply.setStyleSheet(
            "QPushButton { background:#1f6feb; color:#fff; border:none;"
            " border-radius:3px; font-size:10px; }"
            "QPushButton:hover { background:#388bfd; }"
        )
        btn_apply.clicked.connect(self._apply_selected)
        layout.addWidget(btn_apply)

        btn_assign = QPushButton("→ VC-Button zuweisen")
        btn_assign.setFixedHeight(26)
        btn_assign.setToolTip(
            "Assigns den ausgewählten Snapshot dem nächsten angeklickten VC-Button"
        )
        btn_assign.setStyleSheet(
            "QPushButton { background:#2a3344; color:#ffd700; border:1px solid #4f6391;"
            " border-radius:3px; font-size:10px; }"
            "QPushButton:hover { background:#364463; }"
            "QPushButton:checked { background:#ffd700; color:#000; }"
        )
        btn_assign.setCheckable(True)
        btn_assign.clicked.connect(self._on_assign_clicked)
        self._btn_assign = btn_assign
        layout.addWidget(btn_assign)

        self.refresh()

    # ── Daten ────────────────────────────────────────────────────────────────

    def refresh(self):
        self._list.clear()
        try:
            with open(_SNAPSHOTS_FILE, encoding="utf-8") as f:
                payload = json.load(f)
            if not isinstance(payload, list):
                return
            for i, s in enumerate(payload):
                if not s or not s.get("values"):
                    continue
                name = s.get("name") or f"Snap {i + 1}"
                count = len(s.get("values", {}))
                item = QListWidgetItem(f"{i + 1}:  {name}\n        ({count} Fixtures)")
                item.setData(Qt.ItemDataRole.UserRole, i)
                self._list.addItem(item)
        except Exception:
            pass

    def _selected_index(self) -> int | None:
        item = self._list.currentItem()
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    # ── Apply ────────────────────────────────────────────────────────────────

    def _apply_selected(self):
        idx = self._selected_index()
        if idx is None:
            return
        self._apply_snapshot(idx)

    def _on_double_click(self, item: QListWidgetItem):
        idx = item.data(Qt.ItemDataRole.UserRole)
        self._apply_snapshot(idx)

    def _apply_snapshot(self, index: int):
        try:
            with open(_SNAPSHOTS_FILE, encoding="utf-8") as f:
                payload = json.load(f)
            if not isinstance(payload, list) or index >= len(payload):
                return
            snap_data = payload[index]
            if not snap_data:
                return
            raw = snap_data.get("values", {})
            from src.core.app_state import get_state
            state = get_state()
            for k, attrs in raw.items():
                for attr, val in attrs.items():
                    try:
                        state.set_programmer_value(int(k), attr, int(val))
                    except Exception:
                        pass
        except Exception as e:
            print(f"[SnapshotSidebar] Apply-Fehler: {e}")

    # ── Assign to Button ─────────────────────────────────────────────────────

    def _on_assign_clicked(self, checked: bool):
        if not checked:
            self._canvas.cancel_snapshot_assign()
            return
        idx = self._selected_index()
        if idx is None:
            self._btn_assign.setChecked(False)
            return
        self._canvas.start_snapshot_assign(idx)
        # Button automatisch zurücksetzen wenn fertig
        self._canvas.snapshot_assign_done.connect(self._on_assign_done)

    def _on_assign_done(self):
        self._btn_assign.setChecked(False)
        try:
            self._canvas.snapshot_assign_done.disconnect(self._on_assign_done)
        except Exception:
            pass

    # ── Kontext-Menü ─────────────────────────────────────────────────────────

    def _context_menu(self, pos: QPoint):
        item = self._list.itemAt(pos)
        if item is None:
            return
        idx = item.data(Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        menu.addAction("Apply (in Programmer laden)").triggered.connect(
            lambda: self._apply_snapshot(idx))
        menu.addAction("Diesem VC-Button zuweisen →").triggered.connect(
            lambda: self._start_assign(idx))
        menu.exec(QCursor.pos())

    def _start_assign(self, idx: int):
        self._canvas.start_snapshot_assign(idx)
        self._canvas.snapshot_assign_done.connect(self._on_assign_done)
        self._btn_assign.setChecked(True)


# ─────────────────────────────────────────────────────────────────────────────
#  VirtualConsoleView
# ─────────────────────────────────────────────────────────────────────────────

class VirtualConsoleView(QWidget):
    """Full Virtual Console tab: Toolbar + Canvas + Snapshot-Sidebar."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._edit_mode = False
        self._midi_learn_active = False
        self._popout_window = None
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

        tb_layout.addSpacing(16)

        # MIDI-Learn-Button
        self._btn_midi_learn = QPushButton("MIDI Lernen")
        self._btn_midi_learn.setCheckable(True)
        self._btn_midi_learn.setFixedHeight(26)
        self._btn_midi_learn.setToolTip(
            "MIDI-Patch-Modus: Zuerst einen VC-Button anklicken,\n"
            "dann die gewünschte MIDI-Taste drücken."
        )
        self._btn_midi_learn.setStyleSheet("""
            QPushButton { background:#21262d; color:#ff8800; border:1px solid #ff8800;
                          border-radius:3px; font-size:10px; padding:0 8px; }
            QPushButton:checked { background:#ff8800; color:#000; font-weight:bold; }
            QPushButton:hover { background:#30363d; }
        """)
        self._btn_midi_learn.toggled.connect(self._toggle_midi_learn)
        tb_layout.addWidget(self._btn_midi_learn)

        # APC LEDs Toggle
        self._btn_apc_leds = QPushButton("APC LEDs")
        self._btn_apc_leds.setCheckable(True)
        self._btn_apc_leds.setFixedHeight(26)
        self._btn_apc_leds.setToolTip(
            "APC Mini LED-Feedback aktivieren/deaktivieren\n"
            "Grün = aktiv, Grün blinkend = gestoppt, Rot = Flash, Gelb = aktuelle Page"
        )
        self._btn_apc_leds.setStyleSheet("""
            QPushButton { background:#21262d; color:#00cc66; border:1px solid #00cc66;
                          border-radius:3px; font-size:10px; padding:0 8px; }
            QPushButton:checked { background:#00cc66; color:#000; font-weight:bold; }
            QPushButton:hover { background:#30363d; }
        """)
        self._btn_apc_leds.toggled.connect(self._toggle_apc_leds)
        tb_layout.addWidget(self._btn_apc_leds)

        # Popout Button
        self._btn_popout = QPushButton("⧉ Popout")
        self._btn_popout.setFixedHeight(26)
        self._btn_popout.setToolTip("Virtual Console in eigenem Fenster öffnen")
        self._btn_popout.setStyleSheet("""
            QPushButton { background:#21262d; color:#8b949e; border:1px solid #30363d;
                          border-radius:3px; font-size:10px; padding:0 8px; }
            QPushButton:hover { background:#30363d; color:#e6edf3; }
        """)
        self._btn_popout.clicked.connect(self._popout_canvas)
        tb_layout.addWidget(self._btn_popout)

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

        # Sidebar-Toggle
        self._btn_sidebar = QPushButton("◀ Snaps")
        self._btn_sidebar.setCheckable(True)
        self._btn_sidebar.setChecked(True)
        self._btn_sidebar.setFixedHeight(26)
        self._btn_sidebar.setStyleSheet("""
            QPushButton { background:#21262d; color:#ffd700; border:1px solid #30363d;
                          border-radius:3px; font-size:10px; padding:0 8px; }
            QPushButton:checked { background:#2a3344; color:#ffd700; }
            QPushButton:hover { background:#30363d; }
        """)
        self._btn_sidebar.toggled.connect(self._toggle_sidebar)
        tb_layout.addWidget(self._btn_sidebar)

        layout.addWidget(toolbar)
        self._toolbar_widget = toolbar

        # ── Splitter: Canvas links, Sidebar rechts ────────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setStyleSheet("QSplitter::handle { background:#30363d; width:2px; }")

        self._main_scroll = QScrollArea()
        self._main_scroll.setWidgetResizable(False)
        self._main_scroll.setStyleSheet("QScrollArea { border:none; background:#0d1117; }")

        self._canvas = VCCanvas()
        self._canvas.midi_learn_done.connect(self._on_midi_learn_done)
        self._main_scroll.setWidget(self._canvas)
        splitter.addWidget(self._main_scroll)

        # Sidebar
        self._sidebar = SnapshotSidebar(self._canvas)
        self._sidebar.setStyleSheet(
            "QWidget { background:#0d1117; border-left:1px solid #21262d; }"
        )
        splitter.addWidget(self._sidebar)

        # Größenverhältnis: Canvas viel breiter als Sidebar
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 1)
        self._splitter = splitter

        layout.addWidget(splitter)

    # ── Edit mode ────────────────────────────────────────────────────────────

    def _toggle_edit(self, enabled: bool):
        self._edit_mode = enabled
        self._btn_edit.setText("Bearbeiten ✓" if enabled else "Bearbeiten")
        self._canvas.set_edit_mode(enabled)
        for btn in self._toolbar_widget.findChildren(QPushButton):
            if btn.property("add_btn"):
                btn.setEnabled(enabled)

    # ── MIDI-Learn ───────────────────────────────────────────────────────────

    def _toggle_midi_learn(self, checked: bool):
        self._midi_learn_active = checked
        if checked:
            self._canvas.start_midi_learn()
        else:
            self._canvas.cancel_midi_learn()

    def _on_midi_learn_done(self):
        self._midi_learn_active = False
        self._btn_midi_learn.setChecked(False)

    # ── APC LEDs ─────────────────────────────────────────────────────────────

    def _toggle_apc_leds(self, checked: bool):
        if checked:
            try:
                from src.core.midi.apc_mini_feedback import APCMiniFeedback
                from src.core.app_state import get_state
                self._apc_feedback = APCMiniFeedback()
                if self._apc_feedback.is_connected:
                    self._apc_feedback.attach(get_state())
                else:
                    self._btn_apc_leds.setChecked(False)
                    self._apc_feedback = None
            except Exception as e:
                print(f"[VC] APC LEDs Fehler: {e}")
                self._btn_apc_leds.setChecked(False)
        else:
            if self._apc_feedback:
                self._apc_feedback.close()
                self._apc_feedback = None

    # ── Popout ────────────────────────────────────────────────────────────────

    def _popout_canvas(self):
        if self._popout_window is not None:
            self._popout_window.show()
            self._popout_window.raise_()
            return

        win = QWidget(None, Qt.WindowType.Window)
        win.setWindowTitle("Virtual Console — Popout")
        win.resize(1280, 800)
        pop_l = QVBoxLayout(win)
        pop_l.setContentsMargins(0, 0, 0, 0)

        pop_scroll = QScrollArea()
        pop_scroll.setWidgetResizable(False)
        pop_scroll.setStyleSheet("QScrollArea { border:none; background:#0d1117; }")
        pop_scroll.setWidget(self._canvas)
        pop_l.addWidget(pop_scroll)

        def _on_close(event):
            self._main_scroll.setWidget(self._canvas)
            self._popout_window = None
            self._btn_popout.setStyleSheet(self._btn_popout.styleSheet())
            event.accept()

        win.closeEvent = _on_close
        self._popout_window = win
        win.show()

    # ── Sidebar ───────────────────────────────────────────────────────────────

    def _toggle_sidebar(self, checked: bool):
        self._sidebar.setVisible(checked)
        self._btn_sidebar.setText("◀ Snaps" if checked else "▶ Snaps")
        if checked:
            self._sidebar.refresh()

    # ── Widget actions ────────────────────────────────────────────────────────

    def _add_widget(self, wtype: str):
        if not self._edit_mode:
            return
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
