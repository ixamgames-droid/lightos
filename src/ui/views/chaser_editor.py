"""Chaser Editor — edit a Chaser function's steps."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QDoubleSpinBox, QSpinBox, QPushButton, QTableWidget, QTableWidgetItem,
    QComboBox, QDialog, QListWidget, QListWidgetItem,
    QDialogButtonBox, QHeaderView, QAbstractItemView, QSizePolicy,
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
        self.setWindowTitle("Funktion auswaehlen")
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
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # Name
        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Name:"))
        self._name_edit = QLineEdit()
        self._name_edit.textChanged.connect(self._on_name_changed)
        name_row.addWidget(self._name_edit, 1)
        root.addLayout(name_row)

        # Properties row
        prop_row = QHBoxLayout()
        prop_row.addWidget(QLabel("Run Order:"))
        self._combo_order = QComboBox()
        for ro in RunOrder:
            self._combo_order.addItem(ro.value, ro)
        self._combo_order.currentIndexChanged.connect(self._on_props_changed)
        prop_row.addWidget(self._combo_order)

        prop_row.addWidget(QLabel("Direction:"))
        self._combo_dir = QComboBox()
        for d in Direction:
            self._combo_dir.addItem(d.value, d)
        self._combo_dir.currentIndexChanged.connect(self._on_props_changed)
        prop_row.addWidget(self._combo_dir)

        prop_row.addWidget(QLabel("Speed:"))
        self._spin_speed = QDoubleSpinBox()
        self._spin_speed.setRange(0.01, 100.0)
        self._spin_speed.setSingleStep(0.1)
        self._spin_speed.setDecimals(2)
        self._spin_speed.setSuffix("x")
        self._spin_speed.setMinimumWidth(70)
        self._spin_speed.valueChanged.connect(self._on_props_changed)
        prop_row.addWidget(self._spin_speed)

        # Trigger-Modus
        prop_row.addWidget(QLabel("Trigger:"))
        self._combo_trigger = QComboBox()
        self._combo_trigger.addItem("Timer", False)
        self._combo_trigger.addItem("Beat", True)
        self._combo_trigger.currentIndexChanged.connect(self._on_props_changed)
        prop_row.addWidget(self._combo_trigger)

        self._lbl_bps = QLabel("Beats/Step:")
        prop_row.addWidget(self._lbl_bps)
        self._spin_bps = QSpinBox()
        self._spin_bps.setRange(1, 32)
        self._spin_bps.setValue(1)
        self._spin_bps.setFixedWidth(56)
        self._spin_bps.valueChanged.connect(self._on_props_changed)
        prop_row.addWidget(self._spin_bps)

        prop_row.addStretch(1)
        root.addLayout(prop_row)

        # Step table
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
        # Notiz-Spalte (6) zurueckschreiben — sonst geht die Eingabe verloren.
        self._table.itemChanged.connect(self._on_note_changed)
        root.addWidget(self._table, 1)

        # Action buttons
        btn_row = QHBoxLayout()
        btn_add = QPushButton("+ Hinzufuegen")
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
        root.addLayout(btn_row)

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
        self._update_trigger_visibility()
        self._rebuild_table()
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
