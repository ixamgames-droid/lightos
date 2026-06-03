"""Virtual Console tab — toolbar + canvas + Snapshot-Sidebar."""
from __future__ import annotations
import os
import json
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QPushButton,
    QLabel, QSizePolicy, QSplitter, QListWidget, QListWidgetItem,
    QFrame, QMenu
)
from PySide6.QtCore import Qt, QPoint, QSize, QTimer
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

        # ── Funktionen (Effekte / Matrix / Scenes / Chaser) ────────────────────
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet("color:#30363d;")
        layout.addWidget(sep2)

        hdr2 = QLabel("Funktionen")
        hdr2.setStyleSheet(
            "color:#9DFF52; font-weight:bold; font-size:12px; padding:2px 0;")
        hdr2.setToolTip("Gespeicherte Effekte, Matrix, Scenes und Chaser dieser Show")
        layout.addWidget(hdr2)

        self._fn_list = QListWidget()
        self._fn_list.setStyleSheet(
            "QListWidget { background:#0d1117; border:1px solid #21262d;"
            " color:#c9d1d9; font-size:11px; }"
            "QListWidget::item { padding:5px 4px; border-bottom:1px solid #21262d; }"
            "QListWidget::item:selected { background:#2ea043; color:#ffffff; }"
            "QListWidget::item:hover { background:#21262d; }"
        )
        self._fn_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._fn_list.customContextMenuRequested.connect(self._fn_context_menu)
        self._fn_list.itemDoubleClicked.connect(self._on_fn_double_click)
        layout.addWidget(self._fn_list, 1)

        btn_fn_toggle = QPushButton("Start / Stop")
        btn_fn_toggle.setFixedHeight(26)
        btn_fn_toggle.setToolTip("Ausgewählte Funktion starten bzw. stoppen (zum Testen)")
        btn_fn_toggle.setStyleSheet(
            "QPushButton { background:#238636; color:#fff; border:none;"
            " border-radius:3px; font-size:10px; }"
            "QPushButton:hover { background:#2ea043; }")
        btn_fn_toggle.clicked.connect(self._toggle_selected_function)
        layout.addWidget(btn_fn_toggle)

        btn_fn_assign = QPushButton("→ VC-Button zuweisen")
        btn_fn_assign.setFixedHeight(26)
        btn_fn_assign.setToolTip(
            "Weist die ausgewählte Funktion dem nächsten angeklickten VC-Button zu")
        btn_fn_assign.setStyleSheet(
            "QPushButton { background:#2a3344; color:#9DFF52; border:1px solid #3a6b3a;"
            " border-radius:3px; font-size:10px; }"
            "QPushButton:hover { background:#364463; }"
            "QPushButton:checked { background:#9DFF52; color:#000; }")
        btn_fn_assign.setCheckable(True)
        btn_fn_assign.clicked.connect(self._on_fn_assign_clicked)
        self._btn_fn_assign = btn_fn_assign
        layout.addWidget(btn_fn_assign)

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
        self.refresh_functions()

    # ── Funktionen ─────────────────────────────────────────────────────────────

    # Kurze, sprechende Typ-Labels für die Liste.
    _FN_TYPE_LABEL = {
        "Scene": "Scene", "Chaser": "Chaser", "RGBMatrix": "Matrix",
        "EFX": "Effekt", "Sequence": "Seq", "Collection": "Coll",
        "Audio": "Audio", "Script": "Script", "Show": "Show",
    }

    def refresh_functions(self):
        if not hasattr(self, "_fn_list"):
            return
        # Auswahl merken, damit Start/Stop die Selektion nicht verliert.
        prev_fid = self._selected_function_id()
        self._fn_list.clear()
        try:
            from src.core.engine.function_manager import get_function_manager
            fm = get_function_manager()
            funcs = fm.all()
        except Exception:
            return
        # Nach Typ, dann Name sortieren — übersichtliche Gruppen.
        def _key(f):
            return (f.function_type.value, (f.name or "").lower())
        restore_row = -1
        for row, f in enumerate(sorted(funcs, key=_key)):
            try:
                tlabel = self._FN_TYPE_LABEL.get(
                    f.function_type.value, f.function_type.value)
                running = " ●" if fm.is_running(f.id) else ""
                item = QListWidgetItem(f"[{tlabel}] {f.name}{running}")
                item.setData(Qt.ItemDataRole.UserRole, f.id)
                self._fn_list.addItem(item)
                if f.id == prev_fid:
                    restore_row = row
            except Exception:
                continue
        if restore_row >= 0:
            self._fn_list.setCurrentRow(restore_row)

    def _selected_function_id(self):
        item = self._fn_list.currentItem()
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def _toggle_selected_function(self):
        fid = self._selected_function_id()
        if fid is None:
            return
        try:
            from src.core.engine.function_manager import get_function_manager
            fm = get_function_manager()
            if fm.is_running(fid):
                fm.stop(fid)
            else:
                fm.start(fid)
        except Exception as e:
            print(f"[Sidebar] Funktion toggeln fehlgeschlagen: {e}")
        self.refresh_functions()

    def _on_fn_double_click(self, item: QListWidgetItem):
        self._toggle_selected_function()

    def _fn_context_menu(self, pos: QPoint):
        item = self._fn_list.itemAt(pos)
        if item is None:
            return
        fid = item.data(Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        menu.addAction("Start / Stop").triggered.connect(self._toggle_selected_function)
        menu.addAction("Diesem VC-Button zuweisen →").triggered.connect(
            lambda: self._start_fn_assign(fid))
        menu.exec(QCursor.pos())

    def _on_fn_assign_clicked(self, checked: bool):
        if not checked:
            self._canvas.cancel_function_assign()
            return
        fid = self._selected_function_id()
        if fid is None:
            self._btn_fn_assign.setChecked(False)
            return
        self._start_fn_assign(fid)

    def _start_fn_assign(self, fid):
        self._canvas.start_function_assign(fid)
        self._canvas.function_assign_done.connect(self._on_fn_assign_done)
        self._btn_fn_assign.setChecked(True)

    def _on_fn_assign_done(self):
        self._btn_fn_assign.setChecked(False)
        try:
            self._canvas.function_assign_done.disconnect(self._on_fn_assign_done)
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
        self._pop_scroll = None
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

        self._btn_snap = QPushButton("⊞ Snap")
        self._btn_snap.setCheckable(True)
        self._btn_snap.setChecked(False)
        self._btn_snap.setFixedHeight(26)
        self._btn_snap.setToolTip(
            "Snap auf Grid — Widgets rasten beim Verschieben und Skalieren\n"
            "am Raster ein (Grid-Größe: 8 px)"
        )
        self._btn_snap.setStyleSheet("""
            QPushButton { background:#21262d; color:#8b949e; border:1px solid #30363d;
                          border-radius:3px; font-size:10px; padding:0 8px; }
            QPushButton:checked { background:#0d4f8b; color:#58d68d; border-color:#1f6feb; }
            QPushButton:hover:!disabled { background:#30363d; color:#e6edf3; }
            QPushButton:disabled { color:#484f58; border-color:#21262d; }
        """)
        self._btn_snap.setProperty("edit_only", True)
        self._btn_snap.setVisible(False)
        self._btn_snap.toggled.connect(self._toggle_snap)
        tb_layout.addWidget(self._btn_snap)

        tb_layout.addSpacing(8)

        # Widget quick-add buttons
        widget_buttons = [
            ("Button",    "VCButton"),
            ("Fader",     "VCSlider"),
            ("XY Pad",    "VCXYPad"),
            ("Cue List",  "VCCueList"),
            ("SpeedDial", "VCSpeedDial"),
            ("Farbe",     "VCColor"),
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
            btn.setProperty("add_btn", True)
            btn.setProperty("edit_only", True)
            btn.setVisible(False)
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

        # Touch-Lock (Display-only): nur Anzeige, keine Steuerung per Touchscreen
        self._btn_touch_lock = QPushButton("🔒 Touch-Lock")
        self._btn_touch_lock.setCheckable(True)
        self._btn_touch_lock.setFixedHeight(26)
        self._btn_touch_lock.setToolTip(
            "Display-only: Touchscreen/Maus steuert nicht mehr (nur Anzeige).\n"
            "APC mini / MIDI steuern weiterhin. Schützt vor versehentlichem Antippen."
        )
        self._btn_touch_lock.setStyleSheet("""
            QPushButton { background:#21262d; color:#ffb000; border:1px solid #ffb000;
                          border-radius:3px; font-size:10px; padding:0 8px; }
            QPushButton:checked { background:#ffb000; color:#000; font-weight:bold; }
            QPushButton:hover { background:#30363d; }
        """)
        self._btn_touch_lock.toggled.connect(self._toggle_touch_lock)
        tb_layout.addWidget(self._btn_touch_lock)

        # Bank-Umschaltung (= Executor-Page): bestimmt, welche Widgets/Pads aktiv
        # sind. APC-Page-Buttons schalten dieselbe Bank. Immer sichtbar.
        tb_layout.addSpacing(12)
        _bank_btn_css = """
            QPushButton { background:#21262d; color:#58a6ff; border:1px solid #30363d;
                          border-radius:3px; font-size:12px; font-weight:bold; }
            QPushButton:hover { background:#30363d; color:#e6edf3; }
        """
        self._btn_bank_prev = QPushButton("◀")
        self._btn_bank_prev.setFixedSize(26, 26)
        self._btn_bank_prev.setToolTip("Vorherige Bank (Pad-/Widget-Seite)")
        self._btn_bank_prev.setStyleSheet(_bank_btn_css)
        self._btn_bank_prev.clicked.connect(lambda: self._step_bank(-1))
        tb_layout.addWidget(self._btn_bank_prev)

        self._lbl_bank = QLabel("Bank 1")
        self._lbl_bank.setFixedWidth(54)
        self._lbl_bank.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_bank.setStyleSheet(
            "color:#58a6ff; font-size:11px; font-weight:bold;"
        )
        tb_layout.addWidget(self._lbl_bank)

        self._btn_bank_next = QPushButton("▶")
        self._btn_bank_next.setFixedSize(26, 26)
        self._btn_bank_next.setToolTip("Nächste Bank (Pad-/Widget-Seite)")
        self._btn_bank_next.setStyleSheet(_bank_btn_css)
        self._btn_bank_next.clicked.connect(lambda: self._step_bank(1))
        tb_layout.addWidget(self._btn_bank_next)

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
        btn_clear.setProperty("edit_only", True)
        btn_clear.setVisible(False)
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
        self._btn_sidebar = QPushButton("◀ Bibliothek")
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

        # ── Status-Zeile: aktiver Effekt ──────────────────────────────────────
        self._lbl_active_fx = QLabel("Aktiver Effekt: —")
        # Feste, schmale Hoehe: sonst dehnt sich das Label vertikal auf und
        # verdeckt die halbe Canvas-Flaeche.
        self._lbl_active_fx.setFixedHeight(22)
        self._lbl_active_fx.setStyleSheet(
            "background:#0d1117; color:#9DFF52; border-bottom:1px solid #21262d;"
            " padding:2px 10px; font-size:11px;")
        layout.addWidget(self._lbl_active_fx)
        self._active_fx_timer = QTimer(self)
        self._active_fx_timer.setInterval(400)
        self._active_fx_timer.timeout.connect(self._update_active_fx)
        self._active_fx_timer.start()

        # ── Splitter: Canvas links, Sidebar rechts ────────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setStyleSheet("QSplitter::handle { background:#30363d; width:2px; }")

        self._main_scroll = QScrollArea()
        self._main_scroll.setWidgetResizable(False)
        self._main_scroll.setStyleSheet("QScrollArea { border:none; background:#0d1117; }")

        self._canvas = VCCanvas()
        self._canvas.midi_learn_done.connect(self._on_midi_learn_done)
        self._canvas.bank_changed.connect(self._on_bank_changed)
        self._on_bank_changed(self._canvas.active_bank)
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

        # Stretch=1: der Canvas-/Sidebar-Splitter bekommt den gesamten
        # verbleibenden vertikalen Platz (Toolbar + Statuszeile sind fix).
        layout.addWidget(splitter, 1)

    # ── Status: aktiver Effekt ───────────────────────────────────────────────

    def _update_active_fx(self):
        """Zeigt den zuletzt gestarteten, noch laufenden Effekt + Anzahl laufender."""
        try:
            from src.core.engine.function_manager import get_function_manager
            fm = get_function_manager()
            # Funktionsliste der Sidebar nachziehen, wenn sich die Anzahl geaendert
            # hat (z. B. Show geladen) — ohne bei jedem Tick die Auswahl zu stoeren.
            try:
                cnt = len(fm.all())
                if cnt != getattr(self, "_last_fn_count", -1):
                    self._last_fn_count = cnt
                    if getattr(self, "_sidebar", None) is not None:
                        self._sidebar.refresh_functions()
            except Exception:
                pass
            active = fm.active_function()
            running = len(getattr(fm, "_running_ids", ()) or ())
            if active is not None:
                extra = f"  (+{running - 1} weitere)" if running > 1 else ""
                self._lbl_active_fx.setText(
                    f"Aktiver Effekt: {active.function_type.value} · {active.name}{extra}")
                self._lbl_active_fx.setStyleSheet(
                    "background:#0d1117; color:#9DFF52; border-bottom:1px solid #21262d;"
                    " padding:2px 10px; font-size:11px;")
            else:
                self._lbl_active_fx.setText("Aktiver Effekt: —")
                self._lbl_active_fx.setStyleSheet(
                    "background:#0d1117; color:#666; border-bottom:1px solid #21262d;"
                    " padding:2px 10px; font-size:11px;")
        except Exception:
            pass

    # ── Edit mode ────────────────────────────────────────────────────────────

    def _canvas_alive(self) -> bool:
        """True, wenn das C++-Objekt des Canvas noch existiert (gegen
        'already deleted'-Abstürze, falls der Canvas anderweitig zerstört wurde)."""
        try:
            import shiboken6
            return shiboken6.isValid(self._canvas)
        except Exception:
            return self._canvas is not None

    def _toggle_edit(self, enabled: bool):
        self._edit_mode = enabled
        self._btn_edit.setText("Bearbeiten ✓" if enabled else "Bearbeiten")
        if not self._canvas_alive():
            return
        self._canvas.set_edit_mode(enabled)
        # Bearbeiten-only-Buttons (Widgets hinzufügen, Snap, Alle löschen) nur
        # im Bearbeiten-Modus zeigen -> aufgeraeumtes Fenster im Live-Betrieb.
        for btn in self._toolbar_widget.findChildren(QPushButton):
            if btn.property("edit_only"):
                btn.setVisible(enabled)

    def _toggle_snap(self, checked: bool):
        self._canvas.set_snap_to_grid(checked)

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

    def _toggle_touch_lock(self, checked: bool):
        """Display-only: Touch/Maus im Run-Modus sperren (APC/MIDI bleibt aktiv)."""
        try:
            from src.ui.virtualconsole.vc_widget import VCWidget
            VCWidget.input_locked = bool(checked)
            self._btn_touch_lock.setText("🔒 Gesperrt" if checked else "🔒 Touch-Lock")
        except Exception as e:
            print(f"[VC] touch lock error: {e}")

    def _toggle_apc_leds(self, checked: bool):
        if checked:
            try:
                from src.core.app_state import get_state
                from src.core.midi.midi_manager import get_midi_manager
                outs = get_midi_manager().list_outputs()
                is_mk2 = any("mk2" in p.lower() for p in outs)
                if is_mk2:
                    # mk2 nutzt RGB + spiegelt die VC-Button-Zustaende
                    from src.core.midi.apc_mk2_feedback import ApcMk2Feedback
                    self._apc_feedback = ApcMk2Feedback(self._canvas)
                else:
                    from src.core.midi.apc_mini_feedback import APCMiniFeedback
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

    # ── Bank/Page ──────────────────────────────────────────────────────────────

    def _step_bank(self, delta: int):
        target = max(0, min(9, self._canvas.active_bank + int(delta)))
        pe = None
        try:
            from src.core.app_state import get_state
            pe = get_state().playback_engine
        except Exception:
            pe = None
        if pe is not None:
            pe.set_page(target)        # -> Canvas via Page-Callback -> bank_changed
        else:
            self._canvas.set_active_bank(target)

    def _on_bank_changed(self, b: int):
        self._lbl_bank.setText(f"Bank {int(b) + 1}")

    # ── Popout ────────────────────────────────────────────────────────────────

    def _popout_canvas(self):
        if self._popout_window is not None:
            self._popout_window.show()
            self._popout_window.raise_()
            return

        view = self

        class _PopoutWindow(QWidget):
            def closeEvent(self, event):
                # Beim Schließen des Popout-Fensters den Canvas zurück in die
                # Haupt-Ansicht holen — sonst bleibt er im (versteckten) Fenster
                # hängen und die Virtual Console verschwindet aus LightOS.
                # WICHTIG: takeWidget() löst die Eigentümerschaft, ohne den Canvas
                # zu löschen. Würde man ihn im Popout-Scroll lassen, zerstört das
                # schließende Fenster das C++-Objekt (-> "VCCanvas already deleted"
                # beim nächsten Bearbeiten-/Hinzufügen-Klick).
                if view._pop_scroll is not None:
                    view._pop_scroll.takeWidget()
                    view._pop_scroll = None
                view._main_scroll.setWidget(view._canvas)
                view._popout_window = None
                event.accept()

        win = _PopoutWindow(None, Qt.WindowType.Window)
        win.setWindowTitle("Virtual Console — Popout")
        win.resize(1280, 800)
        pop_l = QVBoxLayout(win)
        pop_l.setContentsMargins(0, 0, 0, 0)

        pop_scroll = QScrollArea()
        pop_scroll.setWidgetResizable(False)
        pop_scroll.setStyleSheet("QScrollArea { border:none; background:#0d1117; }")
        # Canvas zuerst aus dem Haupt-Scroll lösen (ohne Löschen), dann übergeben.
        self._main_scroll.takeWidget()
        pop_scroll.setWidget(self._canvas)
        pop_l.addWidget(pop_scroll)

        self._pop_scroll = pop_scroll
        self._popout_window = win
        win.show()

    # ── Sidebar ───────────────────────────────────────────────────────────────

    def _toggle_sidebar(self, checked: bool):
        self._sidebar.setVisible(checked)
        self._btn_sidebar.setText("◀ Bibliothek" if checked else "▶ Bibliothek")
        if checked:
            self._sidebar.refresh()

    # ── Widget actions ────────────────────────────────────────────────────────

    def _add_widget(self, wtype: str):
        if not self._edit_mode or not self._canvas_alive():
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
