"""Chaser Editor — edit a Chaser function's steps."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QDoubleSpinBox, QSpinBox, QPushButton, QTableWidget, QTableWidgetItem,
    QComboBox, QDialog, QListWidget, QListWidgetItem,
    QDialogButtonBox, QHeaderView, QAbstractItemView, QSizePolicy,
    QScrollArea, QGroupBox, QFormLayout, QCheckBox,
)
from PySide6.QtCore import Qt
from src.core.engine.chaser import Chaser, ChaserStep
from src.core.engine.function import RunOrder, Direction
from src.core.engine.function_manager import get_function_manager
from src.ui.widgets.curve_editor import CurveThumbnail, CurveEditorDialog


class FunctionSelectorDialog(QDialog):
    """Modal dialog to pick a function from the registry."""

    def __init__(self, parent=None, exclude_id: int | None = None):
        super().__init__(parent)
        self.setWindowTitle("Funktion auswählen")
        self.setMinimumSize(340, 400)
        self._selected_id: int | None = None

        layout = QVBoxLayout(self)
        self._list = QListWidget()
        layout.addWidget(self._list)

        fm = get_function_manager()
        for f in fm.all():
            # Den bearbeiteten Chaser NICHT als eigenen Schritt anbieten —
            # Selbstreferenz würde beim Abspielen zu Endlos-Rekursion führen.
            if exclude_id is not None and f.id == exclude_id:
                continue
            item = QListWidgetItem(f"{f.function_type.value}: {f.name}")
            item.setData(Qt.ItemDataRole.UserRole, f.id)
            self._list.addItem(item)

        self._list.itemDoubleClicked.connect(self._accept)

        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.accepted.connect(self._accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def _accept(self):
        item = self._list.currentItem()
        if item:
            self._selected_id = item.data(Qt.ItemDataRole.UserRole)
            self.accept()

    @property
    def selected_id(self) -> int | None:
        return self._selected_id


class ChaserEditor(QWidget):
    def __init__(self, chaser: Chaser, parent=None):
        super().__init__(parent)
        self._chaser = chaser
        self._building = False
        self._setup_ui()
        self._load_chaser()

    def set_chaser(self, chaser: Chaser):
        self._chaser = chaser
        self._load_chaser()

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
        root = QVBoxLayout(self._editor_body)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(6)

        # Grundeinstellungen — Name
        grp_basic = QGroupBox("Grundeinstellungen")
        basic_form = QFormLayout(grp_basic)
        self._name_edit = QLineEdit()
        self._name_edit.textChanged.connect(self._on_name_changed)
        basic_form.addRow("Name:", self._name_edit)
        root.addWidget(grp_basic)

        # Wiedergabe & Tempo — vorher eine schmale prop_row (clippte horizontal)
        grp_play = QGroupBox("Wiedergabe && Tempo")
        play_form = QFormLayout(grp_play)

        self._combo_order = QComboBox()
        for ro in RunOrder:
            self._combo_order.addItem(ro.value, ro)
        self._combo_order.currentIndexChanged.connect(self._on_props_changed)
        play_form.addRow("Run Order:", self._combo_order)

        self._combo_dir = QComboBox()
        for d in Direction:
            self._combo_dir.addItem(d.value, d)
        self._combo_dir.currentIndexChanged.connect(self._on_props_changed)
        play_form.addRow("Direction:", self._combo_dir)

        self._spin_speed = QDoubleSpinBox()
        self._spin_speed.setRange(0.01, 100.0)
        self._spin_speed.setSingleStep(0.1)
        self._spin_speed.setDecimals(2)
        self._spin_speed.setSuffix("x")
        self._spin_speed.setMinimumWidth(70)
        self._spin_speed.valueChanged.connect(self._on_props_changed)
        play_form.addRow("Speed:", self._spin_speed)

        # Trigger-Modus
        self._combo_trigger = QComboBox()
        self._combo_trigger.addItem("Timer", False)
        self._combo_trigger.addItem("Beat", True)
        self._combo_trigger.currentIndexChanged.connect(self._on_props_changed)
        play_form.addRow("Trigger:", self._combo_trigger)

        self._lbl_bps = QLabel("Beats/Step:")
        self._spin_bps = QSpinBox()
        self._spin_bps.setRange(1, 32)
        self._spin_bps.setValue(1)
        self._spin_bps.setMinimumWidth(70)
        self._spin_bps.valueChanged.connect(self._on_props_changed)
        play_form.addRow(self._lbl_bps, self._spin_bps)

        # Tempo-Bus: beatgenau an einen Tempo-Bus koppeln (folgt der globalen BPM)
        # ODER bewusst frei laufen lassen (dann zeitbasierter Crossfade zwischen den
        # Schritten). Spiegelt das Tempo-Panel der Matrix-/EFX-Editoren.
        self._tempo_bus_combo = QComboBox()
        self._tempo_bus_combo.addItem("Global (taktgleich, Standard)", "Global")
        self._tempo_bus_combo.addItem("Frei (nicht taktgebunden)", "")
        for _bus_id in ("A", "B", "C", "D"):
            self._tempo_bus_combo.addItem(f"Bus {_bus_id}", _bus_id)
        self._tempo_bus_combo.setToolTip(
            "Beatgenau an einen Tempo-Bus koppeln (folgt der globalen BPM) oder "
            "'Frei' für zeitbasiertes Überblenden zwischen den Schritten.")
        self._tempo_bus_combo.currentIndexChanged.connect(self._on_props_changed)
        play_form.addRow("Tempo-Bus:", self._tempo_bus_combo)

        self._tempo_mult_spin = QDoubleSpinBox()
        self._tempo_mult_spin.setRange(0.0625, 16.0)
        self._tempo_mult_spin.setSingleStep(0.25)
        self._tempo_mult_spin.setDecimals(4)
        self._tempo_mult_spin.setValue(1.0)
        self._tempo_mult_spin.setMinimumWidth(70)
        self._tempo_mult_spin.setToolTip(
            "Geschwindigkeit relativ zum Tempo-Bus, z. B. 0,5 = halb, 2 = doppelt.")
        self._tempo_mult_spin.valueChanged.connect(self._on_props_changed)
        play_form.addRow("Tempo ×:", self._tempo_mult_spin)

        self._tempo_phase_spin = QDoubleSpinBox()
        self._tempo_phase_spin.setRange(0.0, 1.0)
        self._tempo_phase_spin.setSingleStep(0.05)
        self._tempo_phase_spin.setDecimals(2)
        self._tempo_phase_spin.setValue(0.0)
        self._tempo_phase_spin.setMinimumWidth(70)
        self._tempo_phase_spin.setToolTip(
            "Phasenversatz in Beats. 0 = gemeinsamer Start auf der Eins.")
        self._tempo_phase_spin.valueChanged.connect(self._on_props_changed)
        play_form.addRow("Tempo-Versatz:", self._tempo_phase_spin)

        self._tempo_align_check = QCheckBox("Taktgleich starten")
        self._tempo_align_check.setToolTip(
            "An (Standard): startet auf dem gemeinsamen Beat-Raster des Bus, zusammen "
            "mit allen anderen taktgleichen Effekten. Aus: startet bewusst frei bei "
            "seinem eigenen Null. (Wirkt nur mit gewähltem Tempo-Bus.)")
        self._tempo_align_check.toggled.connect(self._on_props_changed)
        play_form.addRow("", self._tempo_align_check)
        root.addWidget(grp_play)

        # Schritte — Tabelle + Aktions-Buttons
        grp_steps = QGroupBox("Schritte")
        steps_layout = QVBoxLayout(grp_steps)

        self._table = QTableWidget()
        self._table.setColumnCount(7)
        self._table.setHorizontalHeaderLabels(
            ["Schritt", "Funktion", "Fade In", "Kurve", "Hold", "Fade Out", "Notiz"]
        )
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for c in range(2, 7):
            self._table.horizontalHeader().setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setMinimumHeight(200)
        # Notiz-Spalte (6) zurueckschreiben — sonst geht die Eingabe verloren.
        self._table.itemChanged.connect(self._on_note_changed)
        steps_layout.addWidget(self._table, 1)

        # Action buttons
        btn_row = QHBoxLayout()
        btn_add = QPushButton("+ Hinzufügen")
        btn_add.clicked.connect(self._add_step)
        btn_row.addWidget(btn_add)

        btn_del = QPushButton("Entfernen")
        btn_del.clicked.connect(self._remove_step)
        btn_row.addWidget(btn_del)

        btn_up = QPushButton("Nach oben")
        btn_up.clicked.connect(self._move_up)
        btn_row.addWidget(btn_up)

        btn_down = QPushButton("Nach unten")
        btn_down.clicked.connect(self._move_down)
        btn_row.addWidget(btn_down)
        btn_row.addStretch(1)
        steps_layout.addLayout(btn_row)
        root.addWidget(grp_steps)

        # Inline-Funktions-Picker: die ganze Liste verfuegbarer Funktionen, Mehrfach-
        # auswahl -> direkt als Schritte ans Ende anhaengen (ohne jedes Mal einen
        # Modal-Dialog). So baut man einen frisch angelegten, leeren Chase unten zusammen.
        grp_pick = QGroupBox("Funktionen zum Chase hinzufügen")
        pick_layout = QVBoxLayout(grp_pick)
        self._add_list = QListWidget()
        self._add_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._add_list.setMinimumHeight(120)
        self._add_list.itemDoubleClicked.connect(self._add_from_picker_item)
        pick_layout.addWidget(self._add_list, 1)
        pick_btn_row = QHBoxLayout()
        btn_take = QPushButton("↳ In Chase übernehmen")
        btn_take.setToolTip("Alle markierten Funktionen als Schritte ans Ende anhängen")
        btn_take.clicked.connect(self._add_selected_from_picker)
        pick_btn_row.addWidget(btn_take)
        btn_refresh = QPushButton("↻")
        btn_refresh.setFixedWidth(34)
        btn_refresh.setToolTip("Liste aktualisieren")
        btn_refresh.clicked.connect(self._refresh_picker)
        pick_btn_row.addWidget(btn_refresh)
        pick_btn_row.addStretch(1)
        pick_layout.addLayout(pick_btn_row)
        root.addWidget(grp_pick)

        # --- outer scroll + popout plumbing ---
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
        win.setWindowTitle("Chaser-Editor")
        win.setModal(False)
        wl = QVBoxLayout(win); wl.setContentsMargins(6, 6, 6, 6)
        sc = QScrollArea(); sc.setWidgetResizable(True)
        sc.setFrameShape(QScrollArea.Shape.NoFrame); sc.setWidget(body)
        sc.setStyleSheet("QScrollArea{border:none;}")
        wl.addWidget(sc)
        win.resize(760, 980)
        win.finished.connect(lambda *_: self._redock_editor())
        self._editor_window = win
        self._editor_window_scroll = sc
        self._btn_editor_popout.setText("⤡ Andocken")
        self._editor_scroll.setVisible(False)
        self._editor_placeholder.setVisible(True)
        win.show()

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

    # ── Load ─────────────────────────────────────────────────────────────────

    def _load_chaser(self):
        self._building = True
        self._name_edit.setText(self._chaser.name)

        idx = self._combo_order.findData(self._chaser.run_order)
        if idx >= 0:
            self._combo_order.setCurrentIndex(idx)

        idx = self._combo_dir.findData(self._chaser.direction)
        if idx >= 0:
            self._combo_dir.setCurrentIndex(idx)

        self._spin_speed.setValue(self._chaser.speed)
        # Trigger
        trig_idx = 1 if getattr(self._chaser, "audio_triggered", False) else 0
        self._combo_trigger.setCurrentIndex(trig_idx)
        self._spin_bps.setValue(max(1, int(getattr(self._chaser, "beats_per_step", 1))))
        _bi = self._tempo_bus_combo.findData(getattr(self._chaser, "tempo_bus_id", "Global"))
        self._tempo_bus_combo.setCurrentIndex(_bi if _bi >= 0 else 0)
        self._tempo_mult_spin.setValue(float(getattr(self._chaser, "tempo_multiplier", 1.0)))
        self._tempo_phase_spin.setValue(float(getattr(self._chaser, "phase_offset", 0.0)))
        self._tempo_align_check.setChecked(bool(getattr(self._chaser, "align_on_start", True)))
        self._update_trigger_visibility()
        self._rebuild_table()
        self._refresh_picker()
        self._building = False

    def _rebuild_table(self):
        self._table.blockSignals(True)
        self._table.setRowCount(len(self._chaser.steps))
        fm = get_function_manager()

        for row, step in enumerate(self._chaser.steps):
            # Step number
            num_item = QTableWidgetItem(str(row + 1))
            num_item.setFlags(num_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            num_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, 0, num_item)

            # Function name
            fn = fm.get(step.function_id)
            fn_name = f"{fn.function_type.value}: {fn.name}" if fn else f"[ID {step.function_id}]"
            fn_item = QTableWidgetItem(fn_name)
            fn_item.setFlags(fn_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(row, 1, fn_item)

            # Timing spinboxes: Fade In(2), Hold(4), Fade Out(5)
            for col, attr in ((2, "fade_in"), (4, "hold"), (5, "fade_out")):
                spin = QDoubleSpinBox()
                spin.setRange(0.0, 3600.0)
                spin.setSingleStep(0.1)
                spin.setDecimals(1)
                spin.setSuffix(" s")
                spin.setValue(getattr(step, attr))
                spin.setProperty("row", row)
                spin.setProperty("attr", attr)
                spin.valueChanged.connect(self._on_step_timing_changed)
                self._table.setCellWidget(row, col, spin)

            # Fade-In-Kurve (Spalte 3): klickbare Mini-Vorschau
            thumb = CurveThumbnail(step.fade_in_curve)
            thumb.setToolTip(f"Fade-Kurve: {step.fade_in_curve.name}\n"
                             "Klicken zum Bearbeiten")
            thumb.clicked.connect(lambda r=row: self._edit_curve(r))
            self._table.setCellWidget(row, 3, thumb)

            # Note
            note_item = QTableWidgetItem(step.note)
            self._table.setItem(row, 6, note_item)

        self._table.blockSignals(False)

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_name_changed(self, text: str):
        if not self._building:
            self._chaser.name = text

    def _on_props_changed(self):
        if self._building:
            return
        self._chaser.run_order = self._combo_order.currentData()
        self._chaser.direction = self._combo_dir.currentData()
        self._chaser.speed = self._spin_speed.value()
        self._chaser.audio_triggered = bool(self._combo_trigger.currentData())
        self._chaser.beats_per_step = int(self._spin_bps.value())
        self._chaser.tempo_bus_id = str(self._tempo_bus_combo.currentData() or "")
        self._chaser.tempo_multiplier = self._tempo_mult_spin.value()
        self._chaser.phase_offset = self._tempo_phase_spin.value()
        self._chaser.align_on_start = self._tempo_align_check.isChecked()
        self._update_trigger_visibility()

    def _update_trigger_visibility(self):
        is_beat = bool(self._combo_trigger.currentData())
        self._lbl_bps.setVisible(is_beat)
        self._spin_bps.setVisible(is_beat)

    def _edit_curve(self, row: int):
        if not (0 <= row < len(self._chaser.steps)):
            return
        step = self._chaser.steps[row]
        dlg = CurveEditorDialog(step.fade_in_curve,
                                title=f"Fade-Kurve – Schritt {row + 1}", parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.result_curve:
            step.fade_in_curve = dlg.result_curve
            self._rebuild_table()
            self._table.selectRow(row)

    def _on_note_changed(self, item):
        """Schreibt die editierte Notiz-Zelle (Spalte 6) in den Step zurueck."""
        if self._building or item is None or item.column() != 6:
            return
        row = item.row()
        if 0 <= row < len(self._chaser.steps):
            self._chaser.steps[row].note = item.text()

    def _on_step_timing_changed(self, value: float):
        spin = self.sender()
        if spin is None:
            return
        row = spin.property("row")
        attr = spin.property("attr")
        if 0 <= row < len(self._chaser.steps):
            setattr(self._chaser.steps[row], attr, value)

    def _add_step(self):
        dlg = FunctionSelectorDialog(self, exclude_id=getattr(self._chaser, "id", None))
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        fid = dlg.selected_id
        if fid is None:
            return
        step = ChaserStep(function_id=fid, fade_in=0.0, hold=1.0, fade_out=0.0)
        self._chaser.steps.append(step)
        self._rebuild_table()

    def _remove_step(self):
        row = self._table.currentRow()
        if 0 <= row < len(self._chaser.steps):
            self._chaser.steps.pop(row)
            self._rebuild_table()

    def _move_up(self):
        row = self._table.currentRow()
        if row > 0:
            steps = self._chaser.steps
            steps[row - 1], steps[row] = steps[row], steps[row - 1]
            self._rebuild_table()
            self._table.selectRow(row - 1)

    def _move_down(self):
        row = self._table.currentRow()
        steps = self._chaser.steps
        if row < len(steps) - 1:
            steps[row], steps[row + 1] = steps[row + 1], steps[row]
            self._rebuild_table()
            self._table.selectRow(row + 1)

    # ── Inline-Funktions-Picker ────────────────────────────────────────────────

    def _refresh_picker(self):
        """Liste aller verfuegbaren Funktionen aufbauen (ohne den Chaser selbst)."""
        self._add_list.clear()
        fm = get_function_manager()
        self_id = getattr(self._chaser, "id", None)
        for f in fm.all():
            if self_id is not None and f.id == self_id:
                continue   # Selbstreferenz vermeiden (Endlos-Rekursion beim Abspielen)
            it = QListWidgetItem(f"{f.function_type.value}: {f.name}")
            it.setData(Qt.ItemDataRole.UserRole, f.id)
            self._add_list.addItem(it)

    def _append_step(self, fid: int):
        self._chaser.steps.append(
            ChaserStep(function_id=int(fid), fade_in=0.0, hold=1.0, fade_out=0.0))

    def _add_from_picker_item(self, item):
        fid = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if fid is not None:
            self._append_step(int(fid))
            self._rebuild_table()

    def _add_selected_from_picker(self):
        added = 0
        for item in self._add_list.selectedItems():
            fid = item.data(Qt.ItemDataRole.UserRole)
            if fid is not None:
                self._append_step(int(fid))
                added += 1
        if added:
            self._rebuild_table()
