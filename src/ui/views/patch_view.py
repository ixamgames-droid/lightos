"""Patch-Ansicht — Geräte patchen und verwalten."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QLabel, QMessageBox, QAbstractItemView,
    QDialog, QFormLayout, QLineEdit, QComboBox, QSpinBox, QDialogButtonBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from src.ui.widgets import mini_icons as _mini
from src.core.app_state import get_state, AppState
from src.core.database import fixture_db as fdb
from src.core.database.models import PatchedFixture
from src.ui.widgets.fixture_browser import FixtureBrowserDialog

TYPE_COLORS = {
    "moving_head": "#1a4a6e",
    "par":         "#1a5c1a",
    "led_bar":     "#4a3a00",
    "strobe":      "#5c2020",
    "dimmer":      "#2a2a2a",
    "other":       "#222233",
}

COLS = ["FID", "Label", "Hersteller", "Gerät", "Modus", "Univ.", "Adresse", "Kanäle", "Typ"]


class PatchFixtureEditDialog(QDialog):
    """Dialog zum Bearbeiten eines gepatchten Geraets."""

    def __init__(self, state: AppState, fixture: PatchedFixture, parent=None):
        super().__init__(parent)
        self._state = state
        self._fixture = fixture
        self.result_updates: dict | None = None
        self._modes = fdb.get_modes(fixture.fixture_profile_id) if fixture.fixture_profile_id else []
        self.setWindowTitle("Geraet bearbeiten")
        self.setMinimumWidth(440)
        self._setup_ui()
        self._validate()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()

        form.addRow("FID:", QLabel(str(self._fixture.fid)))
        form.addRow("Hersteller:", QLabel(self._fixture.manufacturer_name or "-"))
        form.addRow("Geraet:", QLabel(self._fixture.fixture_name or "-"))

        self._edit_label = QLineEdit(self._fixture.label)
        form.addRow("Label:", self._edit_label)

        self._combo_mode = QComboBox()
        current_mode_idx = -1
        for i, m in enumerate(self._modes):
            self._combo_mode.addItem(f"{m.name} ({m.channel_count}ch)", (m.name, m.channel_count))
            if m.name == self._fixture.mode_name:
                current_mode_idx = i
        if current_mode_idx >= 0:
            self._combo_mode.setCurrentIndex(current_mode_idx)
        elif self._modes:
            self._combo_mode.setCurrentIndex(0)
        self._combo_mode.currentIndexChanged.connect(self._on_mode_changed)
        form.addRow("Modus:", self._combo_mode)

        self._spin_universe = QSpinBox()
        self._spin_universe.setRange(1, 32)
        self._spin_universe.setValue(max(1, min(32, int(self._fixture.universe))))
        self._spin_universe.valueChanged.connect(self._validate)
        form.addRow("Universe:", self._spin_universe)

        self._spin_address = QSpinBox()
        self._spin_address.setRange(1, 512)
        self._spin_address.setValue(max(1, min(512, int(self._fixture.address))))
        self._spin_address.valueChanged.connect(self._validate)
        form.addRow("DMX-Adresse:", self._spin_address)

        self._lbl_channels = QLabel("")
        form.addRow("Kanaele:", self._lbl_channels)

        layout.addLayout(form)

        self._lbl_warn = QLabel("")
        self._lbl_warn.setStyleSheet("color: #ff6666;")
        layout.addWidget(self._lbl_warn)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _selected_mode_and_channels(self) -> tuple[str, int]:
        data = self._combo_mode.currentData()
        if isinstance(data, tuple) and len(data) == 2:
            return str(data[0]), int(data[1])
        return self._fixture.mode_name, int(self._fixture.channel_count)

    def _on_mode_changed(self, _idx):
        self._validate()

    def _validate(self):
        _mode_name, ch_count = self._selected_mode_and_channels()
        ch_count = max(1, ch_count)
        self._lbl_channels.setText(str(ch_count))

        max_start = max(1, 512 - ch_count + 1)
        self._spin_address.setMaximum(max_start)
        if self._spin_address.value() > max_start:
            self._spin_address.setValue(max_start)

        conflicts = self._state.check_address_conflict(
            self._spin_universe.value(),
            self._spin_address.value(),
            ch_count,
            exclude_fid=self._fixture.fid,
        )
        if conflicts:
            self._lbl_warn.setText(
                "Adresskonflikt mit FID: " + ", ".join(str(fid) for fid in sorted(conflicts))
            )
        else:
            self._lbl_warn.setText("")

    def _on_accept(self):
        mode_name, ch_count = self._selected_mode_and_channels()
        label = (self._edit_label.text() or "").strip() or self._fixture.label
        universe = self._spin_universe.value()
        address = self._spin_address.value()

        conflicts = self._state.check_address_conflict(
            universe, address, ch_count, exclude_fid=self._fixture.fid
        )
        if conflicts:
            reply = QMessageBox.question(
                self,
                "Adresskonflikt",
                "Es gibt Adresskonflikte mit FID "
                + ", ".join(str(fid) for fid in sorted(conflicts))
                + ".\nTrotzdem speichern?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        self.result_updates = {
            "label": label,
            "mode_name": mode_name,
            "universe": universe,
            "address": address,
            "channel_count": ch_count,
        }
        self.accept()


class PatchView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._state: AppState = get_state()
        self._state.subscribe(self._on_state_change)
        self._setup_ui()
        self._refresh_table()
        # Zentraler StateSync
        try:
            from src.core.sync import get_sync, SyncEvent
            sync = get_sync()
            sync.subscribe(SyncEvent.REFRESH_ALL, lambda *_: self._refresh_table())
            sync.subscribe(SyncEvent.PATCH_CHANGED, lambda *_: self._refresh_table())
        except Exception as e:
            print(f"[patch_view] sync subscribe error: {e}")

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # Toolbar
        toolbar = QHBoxLayout()
        btn_add = QPushButton("+ Gerät hinzufügen")
        btn_add.clicked.connect(self._add_fixture)
        btn_delete = QPushButton("Löschen")
        btn_delete.setObjectName("btn_danger")
        btn_delete.clicked.connect(self._delete_selected)
        btn_autopatch = QPushButton("Auto-Patch")
        btn_autopatch.clicked.connect(self._auto_patch)

        self._lbl_conflict = QLabel("")
        self._lbl_conflict.setStyleSheet("color: #ff4444; font-weight: bold;")

        toolbar.addWidget(btn_add)
        toolbar.addWidget(btn_delete)
        toolbar.addWidget(btn_autopatch)
        toolbar.addStretch()
        toolbar.addWidget(self._lbl_conflict)
        layout.addLayout(toolbar)

        # Tabelle
        self._table = QTableWidget(0, len(COLS))
        self._table.setHorizontalHeaderLabels(COLS)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().hide()
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        for col in [0, 5, 6, 7, 8]:
            hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        self._table.doubleClicked.connect(self._on_double_click)
        layout.addWidget(self._table)

        # Universe-Leiste
        layout.addWidget(QLabel("Universe 1 — Belegte DMX-Kanäle:"))
        self._univ_bar = UniverseBar(self)
        layout.addWidget(self._univ_bar)

    def _refresh_table(self):
        fixtures = self._state.get_patched_fixtures()
        self._table.setRowCount(len(fixtures))
        conflicts = self._find_conflicts(fixtures)

        for row, f in enumerate(fixtures):
            vals = [
                str(f.fid),
                f.label,
                f.manufacturer_name,
                f.fixture_name,
                f.mode_name,
                str(f.universe),
                str(f.address),
                str(f.channel_count),
                f.fixture_type,
            ]
            bg = QColor(TYPE_COLORS.get(f.fixture_type, "#222233"))
            is_conflict = f.fid in conflicts

            for col, val in enumerate(vals):
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
                if is_conflict:
                    item.setBackground(QColor("#5c1a1a"))
                    item.setForeground(QColor("#ff6666"))
                else:
                    item.setBackground(bg)
                # Geraetetyp-Icon links neben das Label (Spalte 1) setzen.
                if col == 1:
                    item.setIcon(_mini.fixture_icon(f.fixture_type))
                self._table.setItem(row, col, item)

        self._univ_bar.update_fixtures(fixtures)
        conflict_count = len(conflicts)
        if conflict_count:
            self._lbl_conflict.setText(f"⚠ {conflict_count} Adresskonflikt(e)!")
        else:
            self._lbl_conflict.setText("")

    def _find_conflicts(self, fixtures: list[PatchedFixture]) -> set[int]:
        conflicts = set()
        for i, a in enumerate(fixtures):
            for b in fixtures[i + 1:]:
                if a.universe != b.universe:
                    continue
                a_end = a.address + a.channel_count - 1
                b_end = b.address + b.channel_count - 1
                if a.address <= b_end and a_end >= b.address:
                    conflicts.add(a.fid)
                    conflicts.add(b.fid)
        return conflicts

    def _add_fixture(self):
        dlg = FixtureBrowserDialog(self._state.next_fid(), self)
        if dlg.exec() and dlg.result_fixture:
            self._state.add_fixture(dlg.result_fixture)
            for extra in getattr(dlg, "extra_fixtures", []):
                self._state.add_fixture(extra)

    def _delete_selected(self):
        rows = {idx.row() for idx in self._table.selectedIndexes()}
        if not rows:
            return
        fixtures = self._state.get_patched_fixtures()
        to_delete = [fixtures[r] for r in rows if r < len(fixtures)]
        if not to_delete:
            return
        names = ", ".join(f.label for f in to_delete)
        reply = QMessageBox.question(
            self, "Löschen bestätigen",
            f"Folgende Geräte löschen?\n{names}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            for f in to_delete:
                self._state.remove_fixture(f.fid)

    def _auto_patch(self):
        fixtures = self._state.get_patched_fixtures()
        if not fixtures:
            return
        self._state.auto_patch_fixtures()

    def _on_double_click(self, index):
        row = index.row()
        fixtures = self._state.get_patched_fixtures()
        if row < 0 or row >= len(fixtures):
            return
        fixture = fixtures[row]
        dlg = PatchFixtureEditDialog(self._state, fixture, self)
        if dlg.exec() and dlg.result_updates:
            self._state.update_fixture(fixture.fid, **dlg.result_updates)

    def _on_state_change(self, event: str, _data):
        if event == "patch_changed":
            self._refresh_table()


class UniverseBar(QWidget):
    """Zeigt belegte DMX-Kanäle in Universe 1 als farbige Blöcke."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(28)
        self._fixtures: list[PatchedFixture] = []

    def update_fixtures(self, fixtures: list[PatchedFixture]):
        self._fixtures = [f for f in fixtures if f.universe == 1]
        self.update()

    def paintEvent(self, _event):
        from PySide6.QtGui import QPainter, QBrush
        p = QPainter(self)
        w = self.width()
        h = self.height()
        block_w = w / 512

        # Hintergrund
        p.fillRect(0, 0, w, h, QColor("#111"))

        for f in self._fixtures:
            x = int((f.address - 1) * block_w)
            bw = max(1, int(f.channel_count * block_w))
            color = QColor(TYPE_COLORS.get(f.fixture_type, "#333"))
            color = color.lighter(160)
            p.fillRect(x, 2, bw, h - 4, color)

            # FID-Label wenn breit genug
            if bw > 20:
                p.setPen(QColor("#fff"))
                p.drawText(x + 2, 2, bw - 4, h - 4,
                           Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                           str(f.fid))
        p.end()
