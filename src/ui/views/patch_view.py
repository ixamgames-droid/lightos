"""Patch-Ansicht — Geräte patchen und verwalten."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QLabel, QMessageBox, QAbstractItemView,
    QDialog, QFormLayout, QLineEdit, QComboBox, QSpinBox, QDialogButtonBox,
    QCheckBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from src.ui.widgets import mini_icons as _mini
from src.core.app_state import (get_state, AppState, is_spider_fixture,
                                 get_channels_for_patched)
from src.core.database import fixture_db as fdb
from src.core.database.models import PatchedFixture
from src.ui.widgets.fixture_browser import FixtureBrowserDialog

TYPE_COLORS = {
    "moving_head": "#1a4a6e",
    "par":         "#1a5c1a",
    "led_bar":     "#4a3a00",
    "strobe":      "#5c2020",
    "dimmer":      "#2a2a2a",
    "scanner":     "#1a3a5c",
    "laser":       "#2a0a3a",
    "smoke":       "#2e2e2e",
    "hazer":       "#263030",
    "other":       "#222233",
}

COLS = ["FID", "Label", "Hersteller", "Gerät", "Modus", "Univ.", "Adresse", "Kanäle", "Typ"]


# ── UI-03: Fixture-Kopieren mit Offset ──────────────────────────────────────
def plan_offset_copies(source, count: int, offset: int, base_fid: int,
                       univ_size: int = 512) -> tuple[list[dict], int]:
    """Plant ``count`` Kopien von ``source`` mit Adress-Abstand ``offset`` im
    selben Universum. Reine Logik (testbar, kein Qt/DB).

    Liefert ``(specs, skipped)``: ``specs`` = Liste ``{fid, universe, address}``;
    Kopien, deren Adressbereich ueber ``univ_size`` liefe (oder < 1), werden
    uebersprungen und in ``skipped`` gezaehlt. fids werden ab ``base_fid``
    LUECKENLOS nur fuer tatsaechlich geplante Kopien vergeben (kein Loch durch
    uebersprungene)."""
    ch = max(1, int(getattr(source, "channel_count", 1)))
    base_addr = int(source.address)
    universe = int(source.universe)
    specs: list[dict] = []
    skipped = 0
    for i in range(1, int(count) + 1):
        addr = base_addr + i * int(offset)
        if addr < 1 or addr + ch - 1 > univ_size:
            skipped += 1
            continue
        specs.append({"fid": base_fid + len(specs),
                      "universe": universe, "address": addr})
    return specs, skipped


def _copy_fixture(src: PatchedFixture, fid: int, universe: int,
                  address: int) -> PatchedFixture:
    """Vollstaendige Kopie von ``src`` mit neuer fid/Universe/Adresse (Profil,
    Modus, Typ und alle Pan/Tilt/Spider-Einstellungen werden uebernommen)."""
    return PatchedFixture(
        fid=fid,
        label=src.label,
        fixture_profile_id=src.fixture_profile_id,
        mode_name=src.mode_name,
        universe=universe,
        address=address,
        channel_count=src.channel_count,
        manufacturer_name=src.manufacturer_name,
        fixture_name=src.fixture_name,
        fixture_type=src.fixture_type,
        invert_pan=src.invert_pan,
        invert_tilt=src.invert_tilt,
        swap_pan_tilt=src.swap_pan_tilt,
        spider_mirrored=src.spider_mirrored,
        spider_dual_tilt=src.spider_dual_tilt,
        pan_range_deg=src.pan_range_deg,
        tilt_range_deg=src.tilt_range_deg,
        pan_zero_dmx=src.pan_zero_dmx,
        tilt_zero_dmx=src.tilt_zero_dmx,
    )


class CopyWithOffsetDialog(QDialog):
    """Fragt Anzahl der Kopien + Adress-Abstand (Offset) ab (UI-03)."""

    def __init__(self, default_offset: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Mit Offset kopieren")
        form = QFormLayout(self)
        self._spin_count = QSpinBox()
        self._spin_count.setRange(1, 512)
        self._spin_count.setValue(1)
        self._spin_offset = QSpinBox()
        self._spin_offset.setRange(1, 512)
        self._spin_offset.setValue(max(1, int(default_offset)))
        form.addRow("Anzahl Kopien:", self._spin_count)
        form.addRow("Adress-Abstand:", self._spin_offset)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def count(self) -> int:
        return self._spin_count.value()

    def offset(self) -> int:
        return self._spin_offset.value()


class PatchFixtureEditDialog(QDialog):
    """Dialog zum Bearbeiten eines gepatchten Geraets."""

    def __init__(self, state: AppState, fixture: PatchedFixture, parent=None):
        super().__init__(parent)
        self._state = state
        self._fixture = fixture
        self.result_updates: dict | None = None
        self._modes = fdb.get_modes(fixture.fixture_profile_id) if fixture.fixture_profile_id else []
        self.setWindowTitle("Gerät bearbeiten")
        self.setMinimumWidth(440)
        self._setup_ui()
        self._validate()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()

        form.addRow("FID:", QLabel(str(self._fixture.fid)))
        form.addRow("Hersteller:", QLabel(self._fixture.manufacturer_name or "-"))
        form.addRow("Gerät:", QLabel(self._fixture.fixture_name or "-"))

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
        form.addRow("Kanäle:", self._lbl_channels)

        # Moving-Head-Ausrichtung (M3.4): Pan/Tilt invertieren/tauschen.
        self._chk_inv_pan = self._chk_inv_tilt = self._chk_swap = None
        if (self._fixture.fixture_type or "") in ("moving_head", "scanner"):
            self._chk_inv_pan = QCheckBox("Pan invertieren")
            self._chk_inv_pan.setChecked(bool(self._fixture.invert_pan))
            self._chk_inv_tilt = QCheckBox("Tilt invertieren")
            self._chk_inv_tilt.setChecked(bool(self._fixture.invert_tilt))
            self._chk_swap = QCheckBox("Pan/Tilt tauschen")
            self._chk_swap.setChecked(bool(self._fixture.swap_pan_tilt))
            form.addRow("Ausrichtung:", self._chk_inv_pan)
            form.addRow("", self._chk_inv_tilt)
            form.addRow("", self._chk_swap)
            # Physischer Pan/Tilt-Bereich (Grad) + DMX-Mitte — fuers Auto-Aim
            # ("Auf Punkt zielen") UND den 3D-Beam. Typisch 540/270, Mitte 128.
            self._spin_pan_range = QSpinBox(); self._spin_pan_range.setRange(1, 1080)
            self._spin_pan_range.setSuffix(" °")
            self._spin_pan_range.setValue(int(getattr(self._fixture, "pan_range_deg", 540) or 540))
            self._spin_pan_range.setToolTip("Physischer Pan-Schwenkbereich des Geräts (z.B. 540°).")
            self._spin_tilt_range = QSpinBox(); self._spin_tilt_range.setRange(1, 540)
            self._spin_tilt_range.setSuffix(" °")
            self._spin_tilt_range.setValue(int(getattr(self._fixture, "tilt_range_deg", 270) or 270))
            self._spin_tilt_range.setToolTip("Physischer Tilt-Bereich des Geräts (z.B. 270°).")
            self._spin_pan_zero = QSpinBox(); self._spin_pan_zero.setRange(0, 255)
            self._spin_pan_zero.setValue(int(getattr(self._fixture, "pan_zero_dmx", 128) or 128))
            self._spin_pan_zero.setToolTip("DMX-Wert, bei dem der Pan in der Mitte steht (meist 128).")
            self._spin_tilt_zero = QSpinBox(); self._spin_tilt_zero.setRange(0, 255)
            self._spin_tilt_zero.setValue(int(getattr(self._fixture, "tilt_zero_dmx", 128) or 128))
            self._spin_tilt_zero.setToolTip("DMX-Wert, bei dem der Tilt in der Mitte steht (meist 128).")
            form.addRow("Pan-Bereich:", self._spin_pan_range)
            form.addRow("Tilt-Bereich:", self._spin_tilt_range)
            form.addRow("Pan-Mitte (DMX):", self._spin_pan_zero)
            form.addRow("Tilt-Mitte (DMX):", self._spin_tilt_zero)

        # Spider-Doppelbar (nur fuer Spider): ist die 2. Farbreihe gespiegelt
        # (W,B,G,R) oder parallel zur ersten (R,G,B,W)? Rein visuell (3D).
        self._combo_spider = None
        if is_spider_fixture(self._fixture):
            self._combo_spider = QComboBox()
            self._combo_spider.addItem("Gespiegelt (W, B, G, R)", True)
            self._combo_spider.addItem("Parallel (R, G, B, W)", False)
            self._combo_spider.setCurrentIndex(
                0 if bool(getattr(self._fixture, "spider_mirrored", True)) else 1)
            self._combo_spider.setToolTip(
                "Anordnung der 2. LED-Bar im 3D-Visualizer (gleicher Controller,\n"
                "leicht andere Bauweise).\n"
                "Gespiegelt: 2. Bar = W, B, G, R (Standard).\n"
                "Parallel:   2. Bar = R, G, B, W (wie die erste)."
            )
            form.addRow("Spider-Anordnung:", self._combo_spider)

        # Spider/Dual-Tilt-Marker: fuer Butterfly-/Derby-Spider, deren zwei
        # Motoren in Wahrheit zwei Tilt-Bars sind (kein echtes Pan) — beim QXF-
        # Import oft faelschlich als pan/tilt gemappt. Auto-Erkennung unmoeglich
        # (echte Pan+Tilt-Mover sehen strukturell gleich aus), daher hier bewusst
        # setzbar, wenn das Geraet Pan UND Tilt hat. Aktiviert die Spider-Bedienung
        # (Position-Tab: Motoren statt XY-Pad, EFX-Tab: Bewegungsmuster statt Kreise).
        self._chk_spider_dual = None
        try:
            _attrs = {(ch.attribute or "") for ch in get_channels_for_patched(self._fixture)}
        except Exception:
            _attrs = set()
        _already = bool(getattr(self._fixture, "spider_dual_tilt", False))
        if ("pan" in _attrs and "tilt" in _attrs) or _already:
            self._chk_spider_dual = QCheckBox("Spider: zwei Tilt-Bars (kein Pan)")
            self._chk_spider_dual.setChecked(_already)
            self._chk_spider_dual.setToolTip(
                "Für Butterfly-/Derby-Spider, deren zwei Motoren in Wahrheit zwei\n"
                "Tilt-Bars sind (kein echtes Pan). Aktiviert die Spider-Bedienung:\n"
                "Position-Tab zeigt die Motoren-Regler statt XY-Pad, EFX-Tab zeigt\n"
                "Spider-Bewegungsmuster statt Kreis/Acht/Lissajous. Der als Pan\n"
                "importierte Motor wird dabei als zweiter Tilt-Bar angesteuert.")
            form.addRow("Spider-Steuerung:", self._chk_spider_dual)

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
        if self._chk_inv_pan is not None:
            self.result_updates.update({
                "invert_pan": self._chk_inv_pan.isChecked(),
                "invert_tilt": self._chk_inv_tilt.isChecked(),
                "swap_pan_tilt": self._chk_swap.isChecked(),
                "pan_range_deg": self._spin_pan_range.value(),
                "tilt_range_deg": self._spin_tilt_range.value(),
                "pan_zero_dmx": self._spin_pan_zero.value(),
                "tilt_zero_dmx": self._spin_tilt_zero.value(),
            })
        if self._combo_spider is not None:
            self.result_updates["spider_mirrored"] = bool(self._combo_spider.currentData())
        if self._chk_spider_dual is not None:
            self.result_updates["spider_dual_tilt"] = self._chk_spider_dual.isChecked()
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
        btn_copy = QPushButton("Mit Offset kopieren…")
        btn_copy.setToolTip(
            "Ausgewählte(s) Gerät(e) mehrfach mit festem Adress-Abstand patchen "
            "(Anzahl + Offset).")
        btn_copy.clicked.connect(self._copy_with_offset)
        btn_autopatch = QPushButton("Auto-Patch")
        btn_autopatch.clicked.connect(self._auto_patch)
        btn_generator = QPushButton("Gerät erstellen…")
        btn_generator.setToolTip(
            "Fixture Generator: eigenes Geräte-Profil grafisch anlegen "
            "(Modi, Kanäle, Bereiche, Live-Test) und in die Bibliothek speichern.")
        btn_generator.clicked.connect(self._open_generator)

        self._lbl_conflict = QLabel("")
        self._lbl_conflict.setStyleSheet("color: #ff4444; font-weight: bold;")

        toolbar.addWidget(btn_add)
        toolbar.addWidget(btn_delete)
        toolbar.addWidget(btn_copy)
        toolbar.addWidget(btn_autopatch)
        toolbar.addWidget(btn_generator)
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

        # Universe-Leiste mit Universe-Umschalter (zeigt nicht mehr nur Univ 1)
        bar_head = QHBoxLayout()
        bar_head.addWidget(QLabel("Belegte DMX-Kanäle — Universe:"))
        self._univ_select = QComboBox()
        self._univ_select.setMinimumWidth(120)
        self._univ_select.currentIndexChanged.connect(self._on_univ_select)
        bar_head.addWidget(self._univ_select)
        bar_head.addStretch()
        layout.addLayout(bar_head)
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
                # FID-Spalte bei Konflikt mit ⚠ markieren — eindeutig auch dort,
                # wo die Typ-Farbe (z. B. Strobe-Rot) der Konflikt-Farbe aehnelt.
                if col == 0 and is_conflict:
                    val = f"⚠ {val}"
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
                if is_conflict:
                    # Deutlich helleres Rot als jede Typ-Farbe (Strobe = #5c2020),
                    # damit eine Konflikt-Zeile nicht mit einem Strobe verwechselt wird.
                    item.setBackground(QColor("#b11d1d"))
                    item.setForeground(QColor("#fff0f0"))
                else:
                    item.setBackground(bg)
                # FID an jeder Zelle hinterlegen → Zeilen-Zuordnung unabhaengig
                # von der Sortier-/Anzeigereihenfolge (robust gegen kuenftige
                # Spalten-Sortierung).
                item.setData(Qt.ItemDataRole.UserRole, f.fid)
                # Geraetetyp-Icon links neben das Label (Spalte 1) setzen.
                if col == 1:
                    item.setIcon(_mini.fixture_icon_for(f))
                self._table.setItem(row, col, item)

        self._refresh_univ_bar(fixtures)
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
            skipped = getattr(dlg, "skipped_count", 0)
            if skipped:
                QMessageBox.warning(
                    self, "Nicht alle Geräte gepatcht",
                    f"{skipped} Gerät(e) konnten nicht gepatcht werden — "
                    "ab Universe 32 war kein Platz mehr.")

    def _open_generator(self):
        """Oeffnet den Fixture Generator. Nach erfolgreichem Speichern
        refresht REFRESH_ALL Patch/Bibliothek (vom Dialog emittiert)."""
        try:
            from src.ui.widgets.fixture_generator import FixtureGeneratorDialog
        except Exception as e:
            QMessageBox.warning(self, "Fixture Generator",
                                f"Generator konnte nicht geladen werden:\n{e}")
            return
        dlg = FixtureGeneratorDialog(self)
        if dlg.exec() and dlg.saved_id is not None:
            self._refresh_table()

    def _fid_at_row(self, row: int) -> int | None:
        """FID der angezeigten Zeile (aus den Item-Daten, nicht positionsbasiert)."""
        item = self._table.item(row, 0)
        if item is None:
            return None
        fid = item.data(Qt.ItemDataRole.UserRole)
        return int(fid) if fid is not None else None

    def _delete_selected(self):
        rows = {idx.row() for idx in self._table.selectedIndexes()}
        if not rows:
            return
        by_fid = {f.fid: f for f in self._state.get_patched_fixtures()}
        to_delete = [by_fid[fid] for r in sorted(rows)
                     if (fid := self._fid_at_row(r)) in by_fid]
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

    def _copy_with_offset(self):
        """UI-03: ausgewaehlte Geraete mehrfach mit festem Adress-Abstand patchen.
        Jede Kopie ist (wie add_fixture) einzeln per Ctrl+Z ruecknehmbar."""
        rows = {idx.row() for idx in self._table.selectedIndexes()}
        by_fid = {f.fid: f for f in self._state.get_patched_fixtures()}
        sources = [by_fid[fid] for r in sorted(rows)
                   if (fid := self._fid_at_row(r)) in by_fid]
        if not sources:
            QMessageBox.information(self, "Mit Offset kopieren",
                                    "Bitte zuerst mind. ein Gerät auswählen.")
            return
        default_offset = max((s.channel_count for s in sources), default=1)
        dlg = CopyWithOffsetDialog(default_offset, self)
        if not dlg.exec():
            return
        count, offset = dlg.count(), dlg.offset()
        made = skipped = 0
        for src in sources:
            # next_fid() je Quelle frisch lesen: nach den Kopien der vorigen Quelle
            # ist die naechste freie fid bereits weitergewandert.
            specs, sk = plan_offset_copies(src, count, offset, self._state.next_fid())
            skipped += sk
            for spec in specs:
                self._state.add_fixture(
                    _copy_fixture(src, spec["fid"], spec["universe"], spec["address"]))
                made += 1
        if skipped:
            QMessageBox.warning(
                self, "Mit Offset kopieren",
                f"{made} Kopie(n) angelegt, {skipped} übersprungen "
                "(Adresse läge außerhalb 1–512).")

    def _auto_patch(self):
        fixtures = self._state.get_patched_fixtures()
        if not fixtures:
            return
        # Auto-Patch schreibt ALLE Adressen/Universen neu — vorher bestaetigen,
        # damit ein versehentlicher Klick kein abgestimmtes Patch zerstoert.
        reply = QMessageBox.question(
            self, "Auto-Patch bestätigen",
            f"Auto-Patch weist allen {len(fixtures)} Geräten neue, "
            "fortlaufende Adressen zu (überschreibt Universe und Adresse).\n"
            "Fortfahren? (rückgängig mit Strg+Z möglich)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._state.auto_patch_fixtures()

    def _on_double_click(self, index):
        fid = self._fid_at_row(index.row())
        if fid is None:
            return
        fixture = next((f for f in self._state.get_patched_fixtures()
                        if f.fid == fid), None)
        if fixture is None:
            return
        dlg = PatchFixtureEditDialog(self._state, fixture, self)
        if dlg.exec() and dlg.result_updates:
            self._state.update_fixture(fixture.fid, **dlg.result_updates)

    def _on_univ_select(self, _idx):
        sel = self._univ_select.currentData()
        self._univ_bar.update_fixtures(
            self._state.get_patched_fixtures(), int(sel) if sel is not None else 1)

    def _refresh_univ_bar(self, fixtures: list[PatchedFixture]):
        """Universe-Auswahl mit den im Patch vorhandenen Universen fuellen und
        die Belegungsleiste fuer das ausgewaehlte Universe zeichnen."""
        univs = sorted({f.universe for f in fixtures}) or [1]
        prev = self._univ_select.currentData()
        self._univ_select.blockSignals(True)
        self._univ_select.clear()
        for u in univs:
            self._univ_select.addItem(f"Universe {u}", u)
        target = prev if prev in univs else univs[0]
        idx = self._univ_select.findData(target)
        self._univ_select.setCurrentIndex(max(0, idx))
        self._univ_select.blockSignals(False)
        self._univ_bar.update_fixtures(fixtures, int(target))

    def _on_state_change(self, event: str, _data):
        if event == "patch_changed":
            self._refresh_table()


class UniverseBar(QWidget):
    """Zeigt belegte DMX-Kanäle eines Universe als farbige Blöcke."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(28)
        self._fixtures: list[PatchedFixture] = []
        self._universe = 1

    def update_fixtures(self, fixtures: list[PatchedFixture], universe: int = 1):
        self._universe = universe
        self._fixtures = [f for f in fixtures if f.universe == universe]
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
