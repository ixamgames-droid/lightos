"""Scene Editor — edit a Scene function's channel values."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QDoubleSpinBox, QPushButton, QTableWidget, QTableWidgetItem,
    QSpinBox, QHeaderView, QAbstractItemView, QSizePolicy,
    QScrollArea, QDialog, QGroupBox,
)
from PySide6.QtCore import Qt
from src.core.app_state import get_state, get_channels_for_patched, resolve_attr_channels
from src.core.engine.scene import Scene


class SceneEditor(QWidget):
    def __init__(self, scene: Scene, parent=None):
        super().__init__(parent)
        self._scene = scene
        self._state = get_state()
        self._building = False
        self._setup_ui()
        self._load_scene()

    def set_scene(self, scene: Scene):
        self._scene = scene
        self._load_scene()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        # --- top-level layout on self ---
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)

        header = QHBoxLayout(); header.setContentsMargins(0, 0, 0, 0); header.addStretch(1)
        self._btn_editor_popout = QPushButton("⤢ Großes Fenster")
        self._btn_editor_popout.setFixedHeight(24)
        self._btn_editor_popout.setToolTip("Den ganzen Editor in einem großen, scrollbaren Fenster bearbeiten")
        self._btn_editor_popout.setStyleSheet(
            "QPushButton{background:#21262d;color:#e6edf3;border:1px solid #30363d;"
            "border-radius:3px;font-size:10px;padding:1px 8px;} "
            "QPushButton:hover{background:#30363d;}")
        self._btn_editor_popout.clicked.connect(self._toggle_editor_popout)
        header.addWidget(self._btn_editor_popout)
        outer.addLayout(header)

        self._editor_body = QWidget()
        root = QVBoxLayout(self._editor_body)   # build ALL existing content into THIS
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(6)

        # Grundeinstellungen & Timing
        basics_group = QGroupBox("Grundeinstellungen && Timing")
        basics_layout = QVBoxLayout(basics_group)
        basics_layout.setSpacing(6)

        # Name
        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Name:"))
        self._name_edit = QLineEdit()
        self._name_edit.textChanged.connect(self._on_name_changed)
        name_row.addWidget(self._name_edit, 1)
        basics_layout.addLayout(name_row)

        # Timing
        timing_row = QHBoxLayout()
        timing_row.addWidget(QLabel("Fade In:"))
        self._spin_fade_in = _make_time_spin()
        self._spin_fade_in.valueChanged.connect(self._on_timing_changed)
        timing_row.addWidget(self._spin_fade_in)

        timing_row.addWidget(QLabel("Kurve:"))
        from src.ui.widgets.curve_editor import CurveThumbnail
        self._curve_thumb = CurveThumbnail(self._scene.fade_in_curve)
        self._curve_thumb.setToolTip("Fade-In-Kurve – Klicken zum Bearbeiten")
        self._curve_thumb.clicked.connect(self._edit_curve)
        timing_row.addWidget(self._curve_thumb)

        timing_row.addWidget(QLabel("Fade Out:"))
        self._spin_fade_out = _make_time_spin()
        self._spin_fade_out.valueChanged.connect(self._on_timing_changed)
        timing_row.addWidget(self._spin_fade_out)

        timing_row.addWidget(QLabel("Hold (0=unendl.):"))
        self._spin_hold = _make_time_spin()
        self._spin_hold.valueChanged.connect(self._on_timing_changed)
        timing_row.addWidget(self._spin_hold)
        timing_row.addStretch(1)
        basics_layout.addLayout(timing_row)
        root.addWidget(basics_group)

        # Buttons row
        btn_row = QHBoxLayout()
        btn_prog = QPushButton("Vom Programmer übernehmen")
        btn_prog.clicked.connect(self._take_from_programmer)
        btn_row.addWidget(btn_prog)

        btn_preview = QPushButton("Vorschau senden")
        btn_preview.clicked.connect(self._send_preview)
        btn_row.addWidget(btn_preview)

        btn_clear = QPushButton("Alle Löschen")
        btn_clear.clicked.connect(self._clear_all)
        btn_row.addWidget(btn_clear)
        btn_row.addStretch(1)
        root.addLayout(btn_row)

        # Channel table
        self._table = QTableWidget()
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setStretchLastSection(False)
        self._table.setMinimumHeight(200)
        root.addWidget(self._table, 1)

        self._editor_window = None
        self._editor_window_scroll = None
        self._editor_scroll = QScrollArea()
        self._editor_scroll.setWidgetResizable(True)
        self._editor_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._editor_scroll.setWidget(self._editor_body)
        self._editor_scroll.setStyleSheet("QScrollArea{border:none;}")
        outer.addWidget(self._editor_scroll, 1)

        self._editor_placeholder = QLabel(
            "⤢ Der Editor ist in einem eigenen großen Fenster geöffnet.\n\n"
            "Zum Andocken das Fenster schließen oder erneut auf »Großes Fenster« tippen.")
        self._editor_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._editor_placeholder.setWordWrap(True)
        self._editor_placeholder.setStyleSheet("color:#8b949e; font-size:11px; padding:24px;")
        self._editor_placeholder.setVisible(False)
        outer.addWidget(self._editor_placeholder, 1)

    def _toggle_editor_popout(self):
        if self._editor_window is not None:
            self._editor_window.close()
            return
        body = self._editor_scroll.takeWidget()
        if body is None:
            return
        win = QDialog(self)
        win.setWindowTitle("Szenen-Editor")
        win.setModal(False)
        wl = QVBoxLayout(win); wl.setContentsMargins(6, 6, 6, 6)
        sc = QScrollArea(); sc.setWidgetResizable(True)
        sc.setFrameShape(QScrollArea.Shape.NoFrame); sc.setWidget(body)
        sc.setStyleSheet("QScrollArea{border:none;}")
        wl.addWidget(sc)
        win.resize(760, 980)
        win.finished.connect(self._redock_editor)
        self._editor_window = win
        self._editor_window_scroll = sc
        self._btn_editor_popout.setText("⤡ Andocken")
        self._editor_scroll.setVisible(False)
        self._editor_placeholder.setVisible(True)
        win.show()
        # UXT-07: sonst hinter dem Hauptfenster -> nach vorn holen.
        win.raise_()
        win.activateWindow()

    def _redock_editor(self):
        if self._editor_window is None:
            return
        try:
            body = self._editor_window_scroll.takeWidget()
            if body is not None:
                self._editor_scroll.setWidget(body)
            self._editor_scroll.setVisible(True)
            self._editor_placeholder.setVisible(False)
            self._btn_editor_popout.setText("⤢ Großes Fenster")
        except RuntimeError:
            pass
        self._editor_window = None

    # ── Load / Refresh ────────────────────────────────────────────────────────

    def _load_scene(self):
        self._building = True
        self._name_edit.setText(self._scene.name)
        self._spin_fade_in.setValue(self._scene.fade_in)
        self._spin_fade_out.setValue(self._scene.fade_out)
        self._spin_hold.setValue(self._scene.hold)
        self._curve_thumb.set_curve(self._scene.fade_in_curve)
        self._rebuild_table()
        self._building = False

    def _edit_curve(self):
        from src.ui.widgets.curve_editor import CurveEditorDialog
        from PySide6.QtWidgets import QDialog
        dlg = CurveEditorDialog(self._scene.fade_in_curve,
                                title="Fade-In-Kurve", parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.result_curve:
            self._scene.fade_in_curve = dlg.result_curve
            self._curve_thumb.set_curve(dlg.result_curve)

    def _rebuild_table(self):
        """Build a row per fixture, a column per channel."""
        self._table.blockSignals(True)
        self._table.clear()
        self._table.setRowCount(0)

        fixtures = self._state.get_patched_fixtures()
        if not fixtures:
            self._table.setColumnCount(1)
            self._table.setHorizontalHeaderLabels(["Kein Fixture gepatcht"])
            self._table.blockSignals(False)
            return

        # Determine max channel count
        max_ch = 0
        fixture_channels: dict[int, list] = {}
        for f in fixtures:
            chs = get_channels_for_patched(f)
            fixture_channels[f.fid] = chs
            max_ch = max(max_ch, len(chs))

        # Columns: fixture name + one per channel
        col_labels = ["Gerät"] + [f"CH{i+1}" for i in range(max_ch)]
        self._table.setColumnCount(len(col_labels))
        self._table.setHorizontalHeaderLabels(col_labels)
        self._table.setRowCount(len(fixtures))

        for row, f in enumerate(fixtures):
            # Fixture name (read-only)
            item = QTableWidgetItem(f"{f.label} ({f.universe}/{f.address})")
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(row, 0, item)

            chs = fixture_channels[f.fid]
            for col_offset, ch in enumerate(chs):
                col = col_offset + 1
                spin = QSpinBox()
                spin.setRange(0, 255)
                spin.setMinimumWidth(52)
                # Set current scene value or 0
                val = self._scene.get_value(f.fid, ch.channel_number)
                spin.setValue(val if val is not None else 0)
                spin.setSpecialValueText("-" if val is None else "")
                # Store metadata in spin
                spin.setProperty("fid", f.fid)
                spin.setProperty("channel_number", ch.channel_number)
                spin.valueChanged.connect(self._on_spin_changed)
                self._table.setCellWidget(row, col, spin)

        self._table.resizeColumnsToContents()
        self._table.blockSignals(False)

    # ── Callbacks ─────────────────────────────────────────────────────────────

    def _on_name_changed(self, text: str):
        if not self._building:
            self._scene.name = text

    def _on_timing_changed(self):
        if not self._building:
            self._scene.fade_in = self._spin_fade_in.value()
            self._scene.fade_out = self._spin_fade_out.value()
            self._scene.hold = self._spin_hold.value()

    def _on_spin_changed(self, value: int):
        spin = self.sender()
        if spin is None:
            return
        fid = spin.property("fid")
        ch = spin.property("channel_number")
        self._scene.set_value(fid, ch, value)

    def _take_from_programmer(self):
        """Import current programmer values into the scene."""
        prog = self._state.programmer
        fixtures = self._state.get_patched_fixtures()
        for f in fixtures:
            if f.fid not in prog:
                continue
            chs = get_channels_for_patched(f)
            # Mehrkopf (X-6/Spider): vorkommens-bewusste Aufloesung statt
            # prog[fid].get(ch.attribute). Letzteres trifft nur den nackten
            # Attributnamen — beide ``color_r``-Kanaele bekaemen den Kopf-0-Wert,
            # ``color_r#1`` ginge verloren. resolve_attr_channels mappt jeden
            # ``attr``/``attr#N`` auf sein eigenes Kanal-Vorkommen (gleiche Logik
            # wie programmer_to_scene_values / _flush_programmer_to_dmx).
            for ch_no, _key, val in resolve_attr_channels(chs, prog[f.fid]):
                self._scene.set_value(f.fid, ch_no, val)
        self._load_scene()

    def _send_preview(self):
        """Write scene values directly to DMX."""
        fixtures = self._state.get_patched_fixtures()
        for sv in self._scene.values:
            fixture = next((f for f in fixtures if f.fid == sv.fixture_id), None)
            if fixture is None:
                continue
            universe = self._state.universes.get(fixture.universe)
            if universe is None:
                continue
            dmx_addr = fixture.address + sv.channel - 1
            if 1 <= dmx_addr <= 512:
                universe.set_channel(dmx_addr, sv.value)

    def _clear_all(self):
        self._scene.clear()
        self._rebuild_table()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_time_spin() -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setRange(0.0, 3600.0)
    s.setSingleStep(0.1)
    s.setDecimals(1)
    s.setSuffix(" s")
    s.setMinimumWidth(80)
    return s
