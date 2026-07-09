"""Dialog: Kanal einer gepatchten Fixture auf einen Sub-Range sperren."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QComboBox, QDialogButtonBox, QHeaderView, QAbstractItemView, QPushButton,
    QMessageBox
)
from PySide6.QtCore import Qt
from src.core.database import fixture_db as fdb
from src.core.database.models import PatchedFixture, FixtureChannel
from src.core.engine.channel_modifier import ChannelModifier, ChannelModifierManager, CurveType


_NO_LOCK = "— kein Lock (0–255) —"


class ChannelRangeLockDialog(QDialog):
    """
    Zeigt alle Kanäle einer gepatchten Fixture.
    Kanäle mit definierten ChannelRanges können auf einen Sub-Range gesperrt werden.
    Dadurch wird ein ChannelModifier erzeugt, der den Fader-Eingang (0-255)
    auf den gewählten DMX-Bereich skaliert.
    """

    def __init__(self, fixture: PatchedFixture, modifier_mgr: ChannelModifierManager,
                 parent=None):
        super().__init__(parent)
        self._fixture = fixture
        self._mgr = modifier_mgr
        self.setWindowTitle(f"Kanal-Ranges — {fixture.label}")
        self.setMinimumWidth(620)
        self._channels: list[FixtureChannel] = []
        self._combos: list[QComboBox] = []
        self._setup_ui()
        self._load()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        info = QLabel(
            f"<b>{self._fixture.fixture_name}</b> · "
            f"Univ. {self._fixture.universe} · "
            f"Adresse {self._fixture.address} · "
            f"Modus: {self._fixture.mode_name}"
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        hint = QLabel(
            "Kanäle mit Ranges: Wähle einen Sub-Range → der Fader (0–255) wird "
            "auf diesen DMX-Bereich skaliert."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #8b949e; font-size: 11px;")
        layout.addWidget(hint)

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["CH", "Kanal-Name", "Attribut", "Range-Lock"])
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self._table.setColumnWidth(0, 40)
        self._table.setColumnWidth(2, 100)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self._table)

        btn_row = QHBoxLayout()
        btn_clear = QPushButton("Alle Locks entfernen")
        btn_clear.clicked.connect(self._clear_all)
        btn_row.addWidget(btn_clear)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _load(self):
        modes = fdb.get_modes(self._fixture.fixture_profile_id)
        mode = next((m for m in modes if m.name == self._fixture.mode_name), None)
        if mode is None and modes:
            mode = modes[0]
        if mode is None:
            return

        self._channels = list(mode.channels)
        self._combos.clear()
        self._table.setRowCount(len(self._channels))

        for row, ch in enumerate(self._channels):
            dmx_abs = self._fixture.address + ch.channel_number - 1

            self._table.setItem(row, 0, QTableWidgetItem(str(ch.channel_number)))
            self._table.setItem(row, 1, QTableWidgetItem(ch.name))
            self._table.setItem(row, 2, QTableWidgetItem(ch.attribute))

            combo = QComboBox()
            if ch.ranges:
                combo.addItem(_NO_LOCK, (0, 255))
                for r in sorted(ch.ranges, key=lambda x: x.range_from):
                    label = f"{r.name}  ({r.range_from}–{r.range_to})"
                    combo.addItem(label, (r.range_from, r.range_to))
                # Vorhandenen Modifier vorauswählen
                existing = self._mgr.get(self._fixture.universe, dmx_abs)
                if existing and (existing.range_min != 0 or existing.range_max != 255):
                    for i in range(combo.count()):
                        rmin, rmax = combo.itemData(i)
                        if rmin == existing.range_min and rmax == existing.range_max:
                            combo.setCurrentIndex(i)
                            break
                combo.setEnabled(True)
            else:
                combo.addItem("(keine Ranges definiert)", (0, 255))
                combo.setEnabled(False)

            self._combos.append(combo)
            self._table.setCellWidget(row, 3, combo)

    def _clear_all(self):
        for combo in self._combos:
            combo.setCurrentIndex(0)

    def _on_accept(self):
        for row, (ch, combo) in enumerate(zip(self._channels, self._combos)):
            dmx_abs = self._fixture.address + ch.channel_number - 1
            if not combo.isEnabled():
                continue
            rmin, rmax = combo.currentData()
            existing = self._mgr.get(self._fixture.universe, dmx_abs)
            if rmin == 0 and rmax == 255:
                # Lock entfernen. Existierte der Modifier NUR wegen des Range-Locks
                # (LINEAR-Kurve, kein Custom-LUT), den Eintrag GANZ entfernen statt nur
                # die Range zu nullen — sonst bleibt ein Identitaets-Modifier (0-255,
                # LINEAR) dauerhaft im geteilten ChannelModifierManager registriert
                # (RL-01: folgenloser, aber unnoetiger Leck-Eintrag, auch persistiert).
                if existing:
                    if existing.curve == CurveType.LINEAR and not existing.custom_lut:
                        self._mgr.remove(self._fixture.universe, dmx_abs)
                    else:
                        # Modifier hat eine echte Kurve -> nur die Range aufheben,
                        # die Kurve des Nutzers NICHT loeschen.
                        existing.range_min = 0
                        existing.range_max = 255
            else:
                if existing:
                    existing.range_min = rmin
                    existing.range_max = rmax
                else:
                    label = f"{self._fixture.label} CH{ch.channel_number} ({ch.name})"
                    self._mgr.add(ChannelModifier(
                        universe=self._fixture.universe,
                        address=dmx_abs,
                        name=label,
                        curve=CurveType.LINEAR,
                        range_min=rmin,
                        range_max=rmax,
                    ))
        self.accept()
