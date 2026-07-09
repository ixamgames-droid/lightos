"""Fixture Editor — Dialog zum Erstellen / Bearbeiten eigener Fixture-Profile.

Speichert direkt in der Fixture-DB (FixtureProfile + FixtureMode + FixtureChannel)
mit source="user". Eigene Profile koennen jederzeit bearbeitet oder geloescht werden.
"""
from __future__ import annotations
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, QSpinBox,
    QComboBox, QPushButton, QLabel, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QMessageBox, QInputDialog, QGroupBox,
    QDialogButtonBox, QTabWidget, QWidget,
)
from PySide6.QtCore import Qt
from sqlalchemy.orm import Session
from sqlalchemy import select, delete
from src.core.database.fixture_db import engine
from src.core.database.models import (
    Manufacturer, FixtureProfile, FixtureMode, FixtureChannel, ChannelRange,
)


FIXTURE_TYPES = [
    "dimmer", "par", "led_bar", "moving_head", "scanner",
    "strobe", "laser", "matrix", "smoke", "hazer", "other",
]

CHANNEL_ATTRS = [
    "intensity", "color_r", "color_g", "color_b", "color_w", "color_a",
    "color_uv", "cmy_c", "cmy_m", "cmy_y", "color_wheel",
    "pan", "pan_fine", "tilt", "tilt_fine",
    "speed", "effect_speed", "duration", "shutter", "strobe",
    "gobo_wheel", "gobo_wheel2", "gobo_rotation", "gobo_fx", "fan",
    "prism", "prism_rotation", "frost", "iris", "zoom", "focus", "macro",
    "laser_boundary", "laser_bank", "laser_x", "laser_y", "laser_zoom_x",
    "laser_zoom_y", "laser_color", "laser_color_change", "laser_dots",
    "laser_draw", "laser_draw_mode", "laser_twist", "laser_grating",
    "laser_scan_rate",
    "reset", "lamp", "raw",
]

CHANNEL_COLS = ["#", "Name", "Attribut", "Default", "Highlight"]


class _ModeTab(QWidget):
    """Eine Mode-Tab: Channel-Tabelle."""

    def __init__(self, name: str = "Default", description: str = "", parent=None):
        super().__init__(parent)
        self.mode_name = name
        # Das einfache Editor-UI bearbeitet keine Beschreibung, muss sie beim
        # Save eines bestehenden Profils aber unbedingt erhalten.
        self.description = description
        self.channels: list[dict] = []   # [{name, attribute, default, highlight}]
        layout = QVBoxLayout(self)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Mode-Name:"))
        self._edit_name = QLineEdit(name)
        self._edit_name.editingFinished.connect(self._on_name_changed)
        name_row.addWidget(self._edit_name, 1)
        layout.addLayout(name_row)

        self._tbl = QTableWidget(0, len(CHANNEL_COLS))
        self._tbl.setHorizontalHeaderLabels(CHANNEL_COLS)
        self._tbl.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)
        self._tbl.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked |
                                  QAbstractItemView.EditTrigger.SelectedClicked)
        layout.addWidget(self._tbl)

        btn_row = QHBoxLayout()
        btn_add = QPushButton("+ Channel")
        btn_add.clicked.connect(self._add_channel)
        btn_del = QPushButton("- Channel")
        btn_del.clicked.connect(self._del_channel)
        btn_up = QPushButton("Hoch")
        btn_up.clicked.connect(lambda: self._move(-1))
        btn_down = QPushButton("Runter")
        btn_down.clicked.connect(lambda: self._move(1))
        for b in (btn_add, btn_del, btn_up, btn_down):
            btn_row.addWidget(b)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

    def _on_name_changed(self):
        self.mode_name = self._edit_name.text().strip() or "Default"

    def _add_channel(self):
        self._sync_from_table()   # Live-Edits sichern (Tabelle<->channels aligned)
        self.channels.append({
            "name": f"Channel {len(self.channels) + 1}",
            "attribute": "raw",
            "default": 0,
            "highlight": 255,
        })
        self._rebuild_rows()

    def _del_channel(self):
        # WICHTIG: Tabelle ZUERST zuruecksynchronisieren (Alignment Tabelle<->channels
        # gilt noch), DANN loeschen, DANN NUR neu bauen. Frueher lief _refresh() ->
        # _sync_from_table() NACH dem del: die um eins verschobene, stale Tabelle wurde
        # per Index in die bereits verkuerzte channels-Liste geschrieben -> Name/Default/
        # Highlight des Folge-Channels korrumpiert.
        self._sync_from_table()
        rows = sorted({i.row() for i in self._tbl.selectedIndexes()}, reverse=True)
        for r in rows:
            if 0 <= r < len(self.channels):
                del self.channels[r]
        self._rebuild_rows()

    def _move(self, dir: int):
        rows = sorted({i.row() for i in self._tbl.selectedIndexes()})
        if not rows:
            return
        r = rows[0]
        nr = r + dir
        if 0 <= nr < len(self.channels):
            # Edits VOR dem Tausch sichern (sonst wird nur `attribute` getauscht,
            # Name/Default/Highlight aber aus der stale Tabelle rueckgesynct).
            self._sync_from_table()
            self.channels[r], self.channels[nr] = self.channels[nr], self.channels[r]
            self._rebuild_rows()
            self._tbl.selectRow(nr)

    def _refresh(self):
        # Live-Edits zuruecklesen (Alignment vorausgesetzt), dann Tabelle neu bauen.
        self._sync_from_table()
        self._rebuild_rows()

    def _rebuild_rows(self):
        self._tbl.blockSignals(True)
        self._tbl.setRowCount(len(self.channels))
        for i, ch in enumerate(self.channels):
            # Channel #
            it_num = QTableWidgetItem(str(i + 1))
            it_num.setFlags(it_num.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._tbl.setItem(i, 0, it_num)
            # Name
            self._tbl.setItem(i, 1, QTableWidgetItem(ch["name"]))
            # Attribute (ComboBox)
            cb = QComboBox()
            for a in CHANNEL_ATTRS:
                cb.addItem(a)
            cb.setCurrentText(ch.get("attribute", "raw"))
            cb.currentTextChanged.connect(
                lambda txt, row=i: self._set_attr(row, txt))
            self._tbl.setCellWidget(i, 2, cb)
            # Default
            self._tbl.setItem(i, 3, QTableWidgetItem(str(ch.get("default", 0))))
            # Highlight
            self._tbl.setItem(i, 4, QTableWidgetItem(str(ch.get("highlight", 255))))
        self._tbl.blockSignals(False)

    def _set_attr(self, row: int, value: str):
        if 0 <= row < len(self.channels):
            self.channels[row]["attribute"] = value

    def _sync_from_table(self):
        """Liest Texteingaben (Name, Default, Highlight) aus der Tabelle zurueck."""
        for i in range(min(self._tbl.rowCount(), len(self.channels))):
            ch = self.channels[i]
            name_item = self._tbl.item(i, 1)
            if name_item:
                ch["name"] = name_item.text() or ch.get("name", f"Channel {i+1}")
            try:
                if self._tbl.item(i, 3):
                    ch["default"] = max(0, min(255, int(self._tbl.item(i, 3).text())))
            except (ValueError, AttributeError):
                pass
            try:
                if self._tbl.item(i, 4):
                    ch["highlight"] = max(0, min(255, int(self._tbl.item(i, 4).text())))
            except (ValueError, AttributeError):
                pass

    def load_mode_data(self, name: str, channels: list[dict], description: str = ""):
        self.mode_name = name
        self.description = description
        self._edit_name.setText(name)
        self.channels = [dict(c) for c in channels]
        # NUR neu bauen, NICHT syncen: channels sind frisch gesetzt, die Tabelle
        # zeigt noch den ALTEN Mode -> ein Sync wuerde alte Tabellenzeilen per Index
        # in die neuen channels schreiben (Korruption beim Mode-Wechsel).
        self._rebuild_rows()

    def get_data(self) -> tuple[str, list[dict], str]:
        self._sync_from_table()
        return self.mode_name, list(self.channels), self.description


class FixtureEditorDialog(QDialog):
    """Erstellt ein neues Fixture-Profil mit Modes/Channels in der DB."""

    def __init__(self, parent=None, fixture_id: int | None = None):
        super().__init__(parent)
        self.setWindowTitle("Fixture Editor")
        self.setMinimumSize(720, 560)
        self._fixture_id = fixture_id   # None = neu, sonst bearbeiten
        self._setup_ui()
        if self._fixture_id is not None:
            self._load_existing()
        else:
            # Mit einem Default-Mode starten
            self._add_mode(name="Default")

    def _setup_ui(self):
        root = QVBoxLayout(self)

        # Header form
        form = QFormLayout()
        self._cb_manufacturer = QComboBox()
        self._cb_manufacturer.setEditable(True)
        self._refresh_manufacturers()
        form.addRow("Hersteller:", self._cb_manufacturer)

        self._edit_name = QLineEdit("Neues Fixture")
        form.addRow("Modell:", self._edit_name)

        self._edit_short = QLineEdit("")
        self._edit_short.setMaxLength(20)
        form.addRow("Kurzname:", self._edit_short)

        self._cb_type = QComboBox()
        for t in FIXTURE_TYPES:
            self._cb_type.addItem(t)
        form.addRow("Typ:", self._cb_type)

        self._spin_power = QSpinBox()
        self._spin_power.setRange(0, 5000)
        self._spin_power.setSuffix(" W")
        form.addRow("Leistung:", self._spin_power)

        root.addLayout(form)

        # Modes tabs
        modes_box = QGroupBox("Modes")
        mb_layout = QVBoxLayout(modes_box)

        self._tabs = QTabWidget()
        mb_layout.addWidget(self._tabs)

        mode_btn_row = QHBoxLayout()
        btn_add_mode = QPushButton("+ Mode")
        btn_add_mode.clicked.connect(lambda: self._add_mode())
        btn_rename_mode = QPushButton("Umbenennen")
        btn_rename_mode.clicked.connect(self._rename_mode)
        btn_del_mode = QPushButton("- Mode")
        btn_del_mode.clicked.connect(self._del_mode)
        mode_btn_row.addWidget(btn_add_mode)
        mode_btn_row.addWidget(btn_rename_mode)
        mode_btn_row.addWidget(btn_del_mode)
        mode_btn_row.addStretch(1)
        mb_layout.addLayout(mode_btn_row)

        root.addWidget(modes_box, 1)

        # Save/Cancel
        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        btn_box.accepted.connect(self._save)
        btn_box.rejected.connect(self.reject)
        root.addWidget(btn_box)

    def _refresh_manufacturers(self):
        with Session(engine()) as s:
            mfrs = s.execute(select(Manufacturer).order_by(Manufacturer.name)).scalars().all()
            self._cb_manufacturer.clear()
            for m in mfrs:
                self._cb_manufacturer.addItem(m.name)

    def _add_mode(self, name: str | None = None, channels: list[dict] | None = None,
                  description: str = ""):
        if name is None:
            existing = [self._tabs.tabText(i) for i in range(self._tabs.count())]
            i = 1
            while f"Mode {i}" in existing:
                i += 1
            name = f"Mode {i}"
        tab = _ModeTab(name, description=description)
        if channels:
            tab.load_mode_data(name, channels, description=description)
        self._tabs.addTab(tab, name)
        self._tabs.setCurrentWidget(tab)
        return tab

    def _rename_mode(self):
        idx = self._tabs.currentIndex()
        if idx < 0:
            return
        tab = self._tabs.widget(idx)
        new_name, ok = QInputDialog.getText(
            self, "Mode umbenennen", "Neuer Name:", text=tab.mode_name)
        if ok and new_name.strip():
            tab.mode_name = new_name.strip()
            tab._edit_name.setText(tab.mode_name)
            self._tabs.setTabText(idx, tab.mode_name)

    def _del_mode(self):
        idx = self._tabs.currentIndex()
        if idx < 0 or self._tabs.count() <= 1:
            QMessageBox.information(self, "Mode löschen",
                                    "Mindestens ein Mode muss existieren.")
            return
        self._tabs.removeTab(idx)

    # ── Load / Save ──────────────────────────────────────────────────────────

    def _load_existing(self):
        with Session(engine()) as s:
            profile = s.execute(
                select(FixtureProfile).where(FixtureProfile.id == self._fixture_id)
            ).scalar_one_or_none()
            if not profile:
                return
            mfr = s.execute(
                select(Manufacturer).where(Manufacturer.id == profile.manufacturer_id)
            ).scalar_one_or_none()
            self._cb_manufacturer.setCurrentText(mfr.name if mfr else "")
            self._edit_name.setText(profile.name)
            self._edit_short.setText(profile.short_name)
            self._cb_type.setCurrentText(profile.fixture_type)
            self._spin_power.setValue(profile.power_w)
            # Modes
            modes = s.execute(
                select(FixtureMode).where(FixtureMode.fixture_id == profile.id)
            ).scalars().all()
            # Clear default tab
            while self._tabs.count():
                self._tabs.removeTab(0)
            for m in modes:
                chans = s.execute(
                    select(FixtureChannel)
                    .where(FixtureChannel.mode_id == m.id)
                    .order_by(FixtureChannel.channel_number)
                ).scalars().all()
                ch_data = [{
                    "name": c.name, "attribute": c.attribute,
                    "default": c.default_value, "highlight": c.highlight_value,
                    "invert": c.invert, "resolution": c.resolution,
                    "ranges": [{
                        "range_from": r.range_from, "range_to": r.range_to,
                        "name": r.name, "kind": r.kind,
                    } for r in c.ranges],
                } for c in chans]
                self._add_mode(name=m.name, channels=ch_data,
                               description=m.description)
            if self._tabs.count() == 0:
                self._add_mode()

    def _save(self):
        mfr_name = self._cb_manufacturer.currentText().strip()
        if not mfr_name:
            QMessageBox.warning(self, "Speichern", "Hersteller fehlt.")
            return
        name = self._edit_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Speichern", "Modell-Name fehlt.")
            return
        if self._tabs.count() == 0:
            QMessageBox.warning(self, "Speichern", "Mindestens ein Mode nötig.")
            return

        # Sync alle Modes
        modes_data = []
        for i in range(self._tabs.count()):
            tab = self._tabs.widget(i)
            mname, chans, description = tab.get_data()
            if not chans:
                QMessageBox.warning(self, "Speichern",
                                    f"Mode '{mname}' hat keine Channels.")
                return
            modes_data.append((mname, chans, description))

        with Session(engine()) as s:
            # Manufacturer get-or-create
            mfr = s.execute(select(Manufacturer).where(
                Manufacturer.name == mfr_name)).scalar_one_or_none()
            if not mfr:
                mfr = Manufacturer(name=mfr_name, short_name=mfr_name[:8].upper())
                s.add(mfr)
                s.flush()

            if self._fixture_id is not None:
                # Update existing: delete modes/channels, recreate
                profile = s.execute(select(FixtureProfile).where(
                    FixtureProfile.id == self._fixture_id)).scalar_one_or_none()
                if profile:
                    profile.manufacturer_id = mfr.id
                    profile.name = name
                    profile.short_name = self._edit_short.text().strip() or name[:8].upper()
                    profile.fixture_type = self._cb_type.currentText()
                    profile.power_w = self._spin_power.value()
                    # Alte Modes ueber die ORM-Session loeschen -> cascade=
                    # "all, delete-orphan" (FixtureMode.channels / FixtureChannel.ranges)
                    # raeumt Channels + Ranges mit ab. Ein Core-Bulk-delete(FixtureMode)
                    # umgeht die ORM-Cascade (der FK channels.mode_id hat kein
                    # ON DELETE CASCADE) und liess Channels/Ranges als Waisen zurueck.
                    old_modes = s.execute(select(FixtureMode).where(
                        FixtureMode.fixture_id == profile.id)).scalars().all()
                    for _m in old_modes:
                        s.delete(_m)
                    s.flush()
                else:
                    profile = FixtureProfile(
                        manufacturer_id=mfr.id, name=name,
                        short_name=self._edit_short.text().strip() or name[:8].upper(),
                        fixture_type=self._cb_type.currentText(),
                        power_w=self._spin_power.value(), source="user",
                    )
                    s.add(profile)
                    s.flush()
            else:
                profile = FixtureProfile(
                    manufacturer_id=mfr.id, name=name,
                    short_name=self._edit_short.text().strip() or name[:8].upper(),
                    fixture_type=self._cb_type.currentText(),
                    power_w=self._spin_power.value(), source="user",
                )
                s.add(profile)
                s.flush()

            for mname, chans, description in modes_data:
                mode = FixtureMode(
                    fixture_id=profile.id, name=mname,
                    channel_count=len(chans), description=description,
                )
                s.add(mode)
                s.flush()
                for i, ch in enumerate(chans, 1):
                    fc = FixtureChannel(
                        mode_id=mode.id, channel_number=i,
                        name=ch.get("name", f"Ch {i}"),
                    attribute=ch.get("attribute", "raw"),
                    default_value=int(ch.get("default", 0)),
                    highlight_value=int(ch.get("highlight", 255)),
                    invert=bool(ch.get("invert", False)),
                    resolution=str(ch.get("resolution", "8bit") or "8bit"),
                )
                s.add(fc)
                for r in ch.get("ranges", []) or []:
                    try:
                        fc.ranges.append(ChannelRange(
                            range_from=int(r.get("range_from", 0)),
                            range_to=int(r.get("range_to", 255)),
                            name=str(r.get("name", "") or ""),
                            kind=str(r.get("kind", "") or ""),
                        ))
                    except (AttributeError, TypeError, ValueError):
                        continue
            s.commit()
            self._saved_id = profile.id

        QMessageBox.information(self, "Gespeichert",
                                f"Fixture-Profil '{mfr_name} {name}' gespeichert.")
        # Sync UI
        try:
            from src.core.sync import get_sync, SyncEvent
            get_sync().emit(SyncEvent.REFRESH_ALL, None)
        except Exception:
            pass
        self.accept()
