"""Editor fuer Input-Profile - Mappings verwalten, Lernen, Save."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QMessageBox, QInputDialog, QLineEdit,
    QDialogButtonBox,
)
from PySide6.QtCore import Qt
from src.core.input.profile import (
    InputProfile, list_profiles, delete_profile, create_default_apc_mini_profile
)
from src.core.midi.midi_mapper import (
    MidiMapping, ACTION_EXECUTOR_GO, ACTION_EXECUTOR_BACK, ACTION_EXECUTOR_FLASH,
    ACTION_EXECUTOR_FADER, ACTION_GRAND_MASTER, ACTION_PROGRAMMER_VAL,
    ACTION_PAGE_SELECT, ACTION_PAGE_NEXT, ACTION_PAGE_PREV, ACTION_NONE,
)

ACTIONS = [
    ("Executor GO",       ACTION_EXECUTOR_GO),
    ("Executor BACK",     ACTION_EXECUTOR_BACK),
    ("Executor FLASH",    ACTION_EXECUTOR_FLASH),
    ("Executor FADER",    ACTION_EXECUTOR_FADER),
    ("Grand Master",      ACTION_GRAND_MASTER),
    ("Programmer Value",  ACTION_PROGRAMMER_VAL),
    ("Page Select",       ACTION_PAGE_SELECT),
    ("Page Next",         ACTION_PAGE_NEXT),
    ("Page Prev",         ACTION_PAGE_PREV),
    ("Keine",             ACTION_NONE),
]


class InputProfileEditor(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Input-Profile verwalten")
        self.setMinimumSize(900, 580)
        self._profile = None  # type: InputProfile | None
        self._setup_ui()
        self._reload_profiles()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Profil-Auswahl
        prof_row = QHBoxLayout()
        prof_row.addWidget(QLabel("Profil:"))
        self._combo = QComboBox()
        self._combo.setMinimumWidth(200)
        self._combo.currentTextChanged.connect(self._on_profile_changed)
        prof_row.addWidget(self._combo)
        b = QPushButton("Neu")
        b.clicked.connect(self._new_profile)
        prof_row.addWidget(b)
        b = QPushButton("Duplizieren")
        b.clicked.connect(self._dup_profile)
        prof_row.addWidget(b)
        b = QPushButton("APC mini Default")
        b.clicked.connect(self._create_apc_default)
        prof_row.addWidget(b)
        b = QPushButton("Loeschen")
        b.setStyleSheet("background:#a02020;color:white;")
        b.clicked.connect(self._delete_profile)
        prof_row.addWidget(b)
        prof_row.addStretch()
        layout.addLayout(prof_row)

        # Description
        desc_row = QHBoxLayout()
        desc_row.addWidget(QLabel("Geraet (Filter):"))
        self._device_hint = QLineEdit()
        self._device_hint.setPlaceholderText("z.B. APC, X-Touch, ...")
        self._device_hint.textChanged.connect(self._save_meta)
        desc_row.addWidget(self._device_hint)
        desc_row.addWidget(QLabel("Beschreibung:"))
        self._description = QLineEdit()
        self._description.textChanged.connect(self._save_meta)
        desc_row.addWidget(self._description, 1)
        layout.addLayout(desc_row)

        # Mappings-Tabelle
        self._table = QTableWidget(0, 7)
        self._table.setHorizontalHeaderLabels([
            "Name", "Typ", "Channel", "Note/CC", "Action", "Param", "Port-Filter"
        ])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.itemChanged.connect(self._on_item_edited)
        layout.addWidget(self._table, 1)

        # Buttons
        btn_row = QHBoxLayout()
        b = QPushButton("+ Mapping")
        b.clicked.connect(self._add_mapping)
        btn_row.addWidget(b)
        b = QPushButton("MIDI Lernen")
        b.clicked.connect(self._learn_mapping)
        btn_row.addWidget(b)
        b = QPushButton("Loeschen")
        b.setStyleSheet("background:#a02020;color:white;")
        b.clicked.connect(self._delete_mapping)
        btn_row.addWidget(b)
        btn_row.addStretch()
        b = QPushButton("Aktivieren (an MidiMapper)")
        b.setStyleSheet("background:#206020;color:white;")
        b.clicked.connect(self._activate)
        btn_row.addWidget(b)
        layout.addLayout(btn_row)

        # Close
        bbox = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bbox.rejected.connect(self.reject)
        bbox.accepted.connect(self.accept)
        layout.addWidget(bbox)

    def _reload_profiles(self):
        self._combo.blockSignals(True)
        self._combo.clear()
        for name in list_profiles():
            self._combo.addItem(name)
        self._combo.blockSignals(False)
        if self._combo.count() > 0:
            self._combo.setCurrentIndex(0)
            self._load_current()
        else:
            self._profile = None
            self._refresh_table()

    def _load_current(self):
        name = self._combo.currentText()
        if not name:
            self._profile = None
            self._refresh_table()
            return
        self._profile = InputProfile.load(name)
        self._device_hint.blockSignals(True)
        self._description.blockSignals(True)
        if self._profile:
            self._device_hint.setText(self._profile.device_hint)
            self._description.setText(self._profile.description)
        else:
            self._device_hint.clear()
            self._description.clear()
        self._device_hint.blockSignals(False)
        self._description.blockSignals(False)
        self._refresh_table()

    def _on_profile_changed(self, _text):
        self._load_current()

    def _refresh_table(self):
        self._table.blockSignals(True)
        self._table.setRowCount(0)
        if self._profile:
            for m in self._profile.mappings:
                r = self._table.rowCount()
                self._table.insertRow(r)
                self._table.setItem(r, 0, QTableWidgetItem(m.name))
                self._table.setItem(r, 1, QTableWidgetItem(m.msg_type))
                self._table.setItem(r, 2, QTableWidgetItem(str(m.channel)))
                self._table.setItem(r, 3, QTableWidgetItem(str(m.data1)))
                # Action as combo
                cb = QComboBox()
                for label, val in ACTIONS:
                    cb.addItem(label, val)
                idx = next((i for i, (l, v) in enumerate(ACTIONS) if v == m.action), 0)
                cb.setCurrentIndex(idx)
                cb.currentIndexChanged.connect(
                    lambda _i, mm=m, c=cb: (setattr(mm, "action", c.currentData()), self._save_meta())
                )
                self._table.setCellWidget(r, 4, cb)
                self._table.setItem(r, 5, QTableWidgetItem(m.param))
                self._table.setItem(r, 6, QTableWidgetItem(m.port_filter))
        self._table.blockSignals(False)

    def _on_item_edited(self, item):
        if not self._profile:
            return
        r = item.row()
        if r >= len(self._profile.mappings):
            return
        m = self._profile.mappings[r]
        c = item.column()
        try:
            if c == 0:
                m.name = item.text()
            elif c == 1:
                m.msg_type = item.text()
            elif c == 2:
                m.channel = int(item.text() or "0")
            elif c == 3:
                m.data1 = int(item.text() or "0")
            elif c == 5:
                m.param = item.text()
            elif c == 6:
                m.port_filter = item.text()
        except ValueError:
            pass
        self._save_meta()

    def _save_meta(self):
        if not self._profile:
            return
        try:
            self._profile.device_hint = self._device_hint.text()
            self._profile.description = self._description.text()
            self._profile.save()
        except Exception as e:
            print(f"[InputProfileEditor] save_meta error: {e}")

    def _new_profile(self):
        name, ok = QInputDialog.getText(self, "Neues Profil", "Name:")
        if not ok or not name.strip():
            return
        p = InputProfile(name=name.strip())
        p.save()
        self._reload_profiles()
        self._combo.setCurrentText(name.strip())

    def _dup_profile(self):
        if not self._profile:
            return
        name, ok = QInputDialog.getText(self, "Profil duplizieren", "Neuer Name:")
        if not ok or not name.strip():
            return
        try:
            import copy
            new_p = copy.deepcopy(self._profile)
            new_p.name = name.strip()
            new_p.save()
            self._reload_profiles()
            self._combo.setCurrentText(name.strip())
        except Exception as e:
            print(f"[InputProfileEditor] dup error: {e}")

    def _create_apc_default(self):
        try:
            p = create_default_apc_mini_profile()
            p.save()
            self._reload_profiles()
            self._combo.setCurrentText(p.name)
        except Exception as e:
            QMessageBox.warning(self, "Fehler", str(e))

    def _delete_profile(self):
        name = self._combo.currentText()
        if not name:
            return
        if QMessageBox.question(self, "Profil loeschen", f"'{name}' wirklich loeschen?") \
                != QMessageBox.StandardButton.Yes:
            return
        delete_profile(name)
        self._reload_profiles()

    def _add_mapping(self):
        if not self._profile:
            return
        m = MidiMapping(name="Neu", msg_type="note_on", channel=0,
                        data1=0, action=ACTION_NONE, param="", port_filter="")
        self._profile.mappings.append(m)
        self._save_meta()
        self._refresh_table()

    def _learn_mapping(self):
        if not self._profile:
            return
        try:
            from src.core.app_state import get_state
            state = get_state()
            if not hasattr(state, "midi_mapper") or not getattr(state, "midi_mapper", None):
                from src.core.midi.midi_mapper import MidiMapper
                state.midi_mapper = MidiMapper(state)
            QMessageBox.information(self, "MIDI Lernen",
                                    "Druecke jetzt eine Taste/Note auf deinem MIDI-Geraet ...")

            def learned(msg):
                try:
                    r = self._table.currentRow()
                    if r < 0 or r >= len(self._profile.mappings):
                        m = MidiMapping(name="Gelernt", msg_type=msg.msg_type, channel=msg.channel,
                                        data1=msg.data1, action=ACTION_NONE, param="", port_filter="")
                        self._profile.mappings.append(m)
                    else:
                        m = self._profile.mappings[r]
                        m.msg_type = msg.msg_type
                        m.channel = msg.channel
                        m.data1 = msg.data1
                    self._save_meta()
                    self._refresh_table()
                except Exception as e:
                    print(f"[InputProfileEditor] learned cb error: {e}")
            state.midi_mapper.start_learn(learned)
        except Exception as e:
            QMessageBox.warning(self, "Fehler", str(e))

    def _delete_mapping(self):
        if not self._profile:
            return
        rows = sorted({i.row() for i in self._table.selectedIndexes()}, reverse=True)
        for r in rows:
            if r < len(self._profile.mappings):
                self._profile.mappings.pop(r)
        self._save_meta()
        self._refresh_table()

    def _activate(self):
        """Aktuelles Profil an den MidiMapper uebergeben."""
        if not self._profile:
            return
        try:
            from src.core.app_state import get_state
            state = get_state()
            if not hasattr(state, "midi_mapper") or not getattr(state, "midi_mapper", None):
                from src.core.midi.midi_mapper import MidiMapper
                state.midi_mapper = MidiMapper(state)
            mapper = state.midi_mapper
            mapper._mappings = list(self._profile.mappings)
            import os
            os.makedirs("data", exist_ok=True)
            mapper.save("data/midi_mappings.json")
            QMessageBox.information(
                self, "Aktiviert",
                f"{len(self._profile.mappings)} Mappings aktiv. Auto-Load beim naechsten Start."
            )
        except Exception as e:
            QMessageBox.warning(self, "Fehler", str(e))
