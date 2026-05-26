"""Patch-Ansicht — Geräte patchen und verwalten."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QLabel, QMessageBox, QAbstractItemView,
    QInputDialog
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from src.core.app_state import get_state, AppState
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
        fx = fixtures[row]

        label, ok = QInputDialog.getText(
            self, "Fixture bearbeiten", "Label:", text=fx.label
        )
        if not ok:
            return
        universe, ok = QInputDialog.getInt(
            self, "Fixture bearbeiten", "Universe:", fx.universe, 1, 32
        )
        if not ok:
            return
        address, ok = QInputDialog.getInt(
            self, "Fixture bearbeiten", "DMX-Adresse:", fx.address, 1, 512
        )
        if not ok:
            return

        end_addr = address + fx.channel_count - 1
        if end_addr > 512:
            QMessageBox.warning(
                self, "Ungültige Adresse",
                f"Adresse {address} + {fx.channel_count}ch = {end_addr} > 512."
            )
            return

        conflicts = self._state.check_address_conflict(
            universe, address, fx.channel_count, exclude_fid=fx.fid
        )
        if conflicts:
            QMessageBox.warning(
                self, "Adresskonflikt",
                "Die gewählte Adresse kollidiert mit bestehenden Fixtures."
            )
            return

        self._state.update_fixture(
            fx.fid,
            label=label.strip() or fx.label,
            universe=universe,
            address=address,
        )

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
