"""MIDI-Konsole — Monitoring, Konfiguration, Mapping, Virtueller Port."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QComboBox, QListWidget, QListWidgetItem, QPlainTextEdit,
    QGroupBox, QFormLayout, QSplitter, QTableWidget,
    QTableWidgetItem, QHeaderView, QCheckBox, QAbstractItemView,
    QInputDialog, QMessageBox
)
from PySide6.QtCore import Qt, QTimer, Signal, QObject
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QTabWidget
from src.core.midi.midi_manager import get_midi_manager, MidiMessage, RTMIDI_OK
from src.core.midi.midi_mapper import (
    MidiMapper, MidiMapping,
    ACTION_EXECUTOR_GO, ACTION_EXECUTOR_BACK, ACTION_EXECUTOR_FLASH,
    ACTION_EXECUTOR_FADER, ACTION_PROGRAMMER_VAL, ACTION_GRAND_MASTER, ACTION_NONE
)
from src.core.app_state import get_state
try:
    from src.core.timecode.mtc_reader import get_mtc_reader
except Exception:
    get_mtc_reader = None  # type: ignore

ACTION_LABELS = {
    ACTION_EXECUTOR_GO:    "Executor GO",
    ACTION_EXECUTOR_BACK:  "Executor BACK",
    ACTION_EXECUTOR_FLASH: "Executor FLASH",
    ACTION_EXECUTOR_FADER: "Executor FADER",
    ACTION_PROGRAMMER_VAL: "Programmer Attribut",
    ACTION_GRAND_MASTER:   "Grand Master",
    ACTION_NONE:           "Keine Aktion",
}

MAP_COLS = ["Name", "Typ", "Ch", "D1", "Aktion", "Parameter", "Port"]


class MidiLogSignal(QObject):
    log_received = Signal(str)


class MidiView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._midi = get_midi_manager()
        self._state = get_state()
        self._mapper = MidiMapper(self._state)
        self._log_signal = MidiLogSignal()
        self._log_signal.log_received.connect(self._append_log)
        self._learn_target_row = -1
        self._setup_ui()
        self._midi.subscribe_log(lambda t: self._log_signal.log_received.emit(t))
        self._midi.subscribe(self._on_midi_msg)

        # Auto-Refresh Ports alle 2 Sek - erkennt USB-Hotplug
        from PySide6.QtCore import QTimer
        self._port_refresh_timer = QTimer(self)
        self._port_refresh_timer.timeout.connect(self._refresh_ports)
        self._port_refresh_timer.start(2000)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        splitter = QSplitter(Qt.Orientation.Vertical)

        # ── Oberer Bereich: Geräteverwaltung + Konsole ────────────────────────
        top = QWidget()
        top_l = QHBoxLayout(top)
        top_l.setContentsMargins(0, 0, 0, 0)

        # Linke Seite: Geräte
        dev_box = QGroupBox("MIDI-Geräte")
        dev_l = QFormLayout(dev_box)

        self._combo_in = QComboBox()
        btn_refresh = QPushButton("↻")
        btn_refresh.setFixedWidth(28)
        btn_refresh.clicked.connect(self._refresh_ports)
        in_row = QHBoxLayout()
        in_row.addWidget(self._combo_in, 1)
        in_row.addWidget(btn_refresh)
        dev_l.addRow("Eingang:", in_row)

        btn_open_in = QPushButton("Eingang öffnen")
        btn_open_in.clicked.connect(self._open_input)
        dev_l.addRow(btn_open_in)

        self._combo_out = QComboBox()
        dev_l.addRow("Ausgang:", self._combo_out)
        btn_open_out = QPushButton("Ausgang öffnen")
        btn_open_out.clicked.connect(self._open_output)
        dev_l.addRow(btn_open_out)

        self._check_virt_in = QCheckBox("Virtuellen Eingang erstellen")
        self._check_virt_out = QCheckBox("Virtuellen Ausgang erstellen")
        self._check_virt_in.toggled.connect(self._toggle_virtual_in)
        self._check_virt_out.toggled.connect(self._toggle_virtual_out)
        dev_l.addRow(self._check_virt_in)
        dev_l.addRow(self._check_virt_out)

        self._lbl_midi_status = QLabel("Nicht verbunden")
        self._lbl_midi_status.setStyleSheet("color: #888;")
        dev_l.addRow("Status:", self._lbl_midi_status)

        top_l.addWidget(dev_box, stretch=1)

        # Rechte Seite: Echtzeit-Monitor
        mon_box = QGroupBox("MIDI Monitor (Eingehende Nachrichten)")
        mon_l = QVBoxLayout(mon_box)

        self._console = QPlainTextEdit()
        self._console.setReadOnly(True)
        self._console.setFont(QFont("Courier New", 10))
        self._console.setMaximumBlockCount(200)
        self._console.setStyleSheet("background: #0a0a0a; color: #00ff88; border: 1px solid #333;")
        mon_l.addWidget(self._console)

        btn_row = QHBoxLayout()
        btn_clear = QPushButton("Konsole leeren")
        btn_clear.clicked.connect(self._console.clear)
        btn_row.addWidget(btn_clear)
        self._chk_monitor = QCheckBox("Monitor aktiv")
        self._chk_monitor.setChecked(True)
        btn_row.addWidget(self._chk_monitor)
        mon_l.addLayout(btn_row)

        top_l.addWidget(mon_box, stretch=2)

        splitter.addWidget(top)

        # ── Unterer Bereich: MIDI-Mapping-Tabelle ─────────────────────────────
        map_box = QGroupBox("MIDI-Mapping — Steuerung von LightOS via MIDI")
        map_l = QVBoxLayout(map_box)

        map_toolbar = QHBoxLayout()
        btn_add_map = QPushButton("+ Mapping hinzufügen")
        btn_add_map.clicked.connect(self._add_mapping)
        btn_del_map = QPushButton("Entfernen")
        btn_del_map.setObjectName("btn_danger")
        btn_del_map.clicked.connect(self._delete_mapping)
        btn_learn = QPushButton("MIDI Learn")
        btn_learn.setToolTip("Wähle eine Zeile, dann klicke MIDI-Learn\nund sende eine MIDI-Nachricht")
        btn_learn.clicked.connect(self._start_learn)
        btn_save = QPushButton("Speichern")
        btn_save.clicked.connect(self._save_mappings)
        btn_load = QPushButton("Laden")
        btn_load.clicked.connect(self._load_mappings)
        for btn in [btn_add_map, btn_del_map, btn_learn, btn_save, btn_load]:
            map_toolbar.addWidget(btn)
        map_toolbar.addStretch()
        map_l.addLayout(map_toolbar)

        self._map_table = QTableWidget(0, len(MAP_COLS))
        self._map_table.setHorizontalHeaderLabels(MAP_COLS)
        self._map_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._map_table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked)
        hdr = self._map_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        map_l.addWidget(self._map_table)

        # Schnell-Mapping-Vorlagen
        tmpl_box = QGroupBox("Schnell-Vorlagen")
        tmpl_l = QHBoxLayout(tmpl_box)
        btn_tmpl_faders = QPushButton("CC1-10 → Executor-Fader 1-10")
        btn_tmpl_faders.clicked.connect(self._template_faders)
        btn_tmpl_notes = QPushButton("Note 0-9 → Executor GO 1-10")
        btn_tmpl_notes.clicked.connect(self._template_notes_go)
        tmpl_l.addWidget(btn_tmpl_faders)
        tmpl_l.addWidget(btn_tmpl_notes)
        map_l.addWidget(tmpl_box)

        splitter.addWidget(map_box)
        splitter.setSizes([300, 400])
        layout.addWidget(splitter)

        # ── MTC (MIDI Time Code) Reader ───────────────────────────────────────
        try:
            self._build_mtc_box(layout)
        except Exception as e:
            print(f"[MidiView] MTC box init error: {e}")

        # Ports laden
        self._refresh_ports()

        if not self._midi.available:
            self._append_log("⚠ Kein MIDI-Backend verfügbar (weder rtmidi noch WinMM). MIDI deaktiviert.")
        elif not RTMIDI_OK:
            self._append_log("ℹ MIDI: Windows WinMM Backend aktiv (ARM-Modus, rtmidi nicht installiert)")

    # ── Geräteverwaltung ──────────────────────────────────────────────────────

    def _refresh_ports(self):
        # Aktuelle Auswahl merken um sie wiederherzustellen
        prev_in = self._combo_in.currentText() if self._combo_in.count() else ""
        prev_out = self._combo_out.currentText() if self._combo_out.count() else ""

        inputs = self._midi.list_inputs()
        outputs = self._midi.list_outputs()

        # Nur neu aufbauen wenn sich was geaendert hat (verhindert Combo-Flicker)
        cur_in_items = [self._combo_in.itemText(i) for i in range(self._combo_in.count())
                        if not self._combo_in.itemText(i).startswith("(")]
        cur_out_items = [self._combo_out.itemText(i) for i in range(self._combo_out.count())
                         if not self._combo_out.itemText(i).startswith("(")]

        if cur_in_items != inputs:
            self._combo_in.clear()
            for p in inputs:
                self._combo_in.addItem(p)
            if not inputs:
                self._combo_in.addItem("(Keine MIDI-Eingaenge gefunden - APC angeschlossen?)")
            else:
                # Selektion wiederherstellen oder erste Auswahl wo "APC" drinsteht
                apc_idx = next((i for i, p in enumerate(inputs) if "APC" in p), -1)
                if prev_in in inputs:
                    self._combo_in.setCurrentText(prev_in)
                elif apc_idx >= 0:
                    self._combo_in.setCurrentIndex(apc_idx)

        if cur_out_items != outputs:
            self._combo_out.clear()
            for p in outputs:
                self._combo_out.addItem(p)
            if not outputs:
                self._combo_out.addItem("(Keine MIDI-Ausgaenge gefunden)")
            else:
                if prev_out in outputs:
                    self._combo_out.setCurrentText(prev_out)

        # Status-Hinweis im Status-Label falls keine Inputs
        if not inputs and hasattr(self, "_lbl_midi_status"):
            cur_status = self._lbl_midi_status.text()
            if not cur_status.startswith("IN:") and "TIPP" not in cur_status:
                self._lbl_midi_status.setText(
                    "Keine Eingaenge. TIPP: USB neu einstecken, "
                    "anderen USB-Port probieren, MIDI 2.0 Modus pruefen"
                )
                self._lbl_midi_status.setStyleSheet("color: #ffaa00;")

    def _open_input(self):
        port = self._combo_in.currentText()
        if not port or port.startswith("("):
            return
        self._midi.open_input(port)
        self._lbl_midi_status.setText(f"IN: {port}")
        self._lbl_midi_status.setStyleSheet("color: #00cc66;")

    def _open_output(self):
        port = self._combo_out.currentText()
        if not port or port.startswith("("):
            return
        self._midi.open_output(port)
        self._lbl_midi_status.setText(f"OUT: {port}")

    def _toggle_virtual_in(self, checked: bool):
        if checked:
            ok = self._midi.open_virtual_input("LightOS Virtual IN")
            if ok:
                self._append_log("✓ Virtueller MIDI-Eingang aktiv: 'LightOS Virtual IN'")
            else:
                self._check_virt_in.setChecked(False)
                self._append_log("✗ Virtueller Port nicht unterstützt (Windows: loopMIDI installieren)")

    def _toggle_virtual_out(self, checked: bool):
        if checked:
            ok = self._midi.open_virtual_output("LightOS Virtual OUT")
            if not ok:
                self._check_virt_out.setChecked(False)

    # ── Monitor ───────────────────────────────────────────────────────────────

    def _on_midi_msg(self, msg: MidiMessage):
        if not self._chk_monitor.isChecked():
            return
        prefixes = {
            "cc":       "CC   ",
            "note_on":  "NOTE+",
            "note_off": "NOTE-",
            "pc":       "PC   ",
        }
        prefix = prefixes.get(msg.msg_type, msg.msg_type.upper()[:5])
        line = (f"{prefix} [{msg.port_name[:20]}] "
                f"CH{msg.channel:2d} D1={msg.data1:3d} D2={msg.data2:3d}")
        self._console.appendPlainText(line)

    def _append_log(self, text: str):
        self._console.appendPlainText(text)

    # ── MIDI-Mapping ──────────────────────────────────────────────────────────

    def _add_mapping(self):
        m = MidiMapping(
            name="Neues Mapping",
            msg_type="cc",
            channel=1,
            data1=0,
            action=ACTION_EXECUTOR_GO,
            param="1",
            port_filter="",
        )
        self._mapper.add_mapping(m)
        self._refresh_map_table()

    def _delete_mapping(self):
        rows = {i.row() for i in self._map_table.selectedIndexes()}
        for row in sorted(rows, reverse=True):
            self._mapper.remove_mapping(row)
        self._refresh_map_table()

    def _refresh_map_table(self):
        mappings = self._mapper.get_mappings()
        self._map_table.setRowCount(len(mappings))
        for row, m in enumerate(mappings):
            vals = [
                m.name, m.msg_type, str(m.channel),
                str(m.data1), ACTION_LABELS.get(m.action, m.action),
                m.param, m.port_filter,
            ]
            for col, val in enumerate(vals):
                self._map_table.setItem(row, col, QTableWidgetItem(val))

    def _start_learn(self):
        rows = {i.row() for i in self._map_table.selectedIndexes()}
        if not rows:
            QMessageBox.information(self, "MIDI Learn", "Erst eine Mapping-Zeile auswählen.")
            return
        self._learn_target_row = list(rows)[0]
        self._append_log("⏳ MIDI Learn — sende eine MIDI-Nachricht...")
        self._mapper.start_learn(self._on_learn_received)

    def _on_learn_received(self, msg: MidiMessage):
        row = self._learn_target_row
        mappings = self._mapper.get_mappings()
        if row < 0 or row >= len(mappings):
            return
        m = mappings[row]
        m.msg_type = msg.msg_type
        m.channel = msg.channel
        m.data1 = msg.data1
        m.port_filter = msg.port_name
        self._refresh_map_table()
        self._append_log(f"✓ Learn: {msg.msg_type} CH{msg.channel} D1={msg.data1}")

    # ── Vorlagen ──────────────────────────────────────────────────────────────

    def _template_faders(self):
        for i in range(1, 11):
            m = MidiMapping(
                name=f"Executor {i} Fader",
                msg_type="cc", channel=1,
                data1=i - 1,
                action=ACTION_EXECUTOR_FADER,
                param=str(i),
                port_filter="",
            )
            self._mapper.add_mapping(m)
        self._refresh_map_table()
        self._append_log("✓ Vorlage: CC1-10 → Executor Fader 1-10")

    def _template_notes_go(self):
        for i in range(1, 11):
            m = MidiMapping(
                name=f"Executor {i} GO",
                msg_type="note_on", channel=1,
                data1=i - 1,
                action=ACTION_EXECUTOR_GO,
                param=str(i),
                port_filter="",
            )
            self._mapper.add_mapping(m)
        self._refresh_map_table()
        self._append_log("✓ Vorlage: Note 0-9 → Executor GO 1-10")

    def _save_mappings(self):
        self._mapper.save("data/midi_mappings.json")
        self._append_log("✓ Mappings gespeichert: data/midi_mappings.json")

    def _load_mappings(self):
        self._mapper.load("data/midi_mappings.json")
        self._refresh_map_table()
        self._append_log("✓ Mappings geladen")

    # ── MTC (MIDI Time Code) ─────────────────────────────────────────────────

    def _build_mtc_box(self, parent_layout):
        """Append a MTC Reader groupbox to parent_layout."""
        box = QGroupBox("MTC - MIDI Time Code Reader")
        bl = QHBoxLayout(box)

        # Port-Auswahl
        bl.addWidget(QLabel("Port:"))
        self._combo_mtc_port = QComboBox()
        bl.addWidget(self._combo_mtc_port, stretch=1)
        btn_refresh = QPushButton("↻")
        btn_refresh.setFixedWidth(28)
        btn_refresh.clicked.connect(self._refresh_mtc_ports)
        bl.addWidget(btn_refresh)
        btn_connect = QPushButton("Verbinden")
        btn_connect.clicked.connect(self._attach_mtc)
        bl.addWidget(btn_connect)

        bl.addWidget(QLabel("Zeit:"))
        self._lbl_mtc_time = QLabel("--:--:--:--")
        self._lbl_mtc_time.setStyleSheet(
            "font-family: monospace; font-size: 18px; color: #FFD700; "
            "padding: 2px 8px; background: #0a0a0a; border: 1px solid #333;"
        )
        bl.addWidget(self._lbl_mtc_time)

        self._lbl_mtc_fps = QLabel("-- fps")
        self._lbl_mtc_fps.setStyleSheet("color: #888;")
        bl.addWidget(self._lbl_mtc_fps)

        parent_layout.addWidget(box)
        self._refresh_mtc_ports()

        # Subscribe (via QTimer in MTC callback to be Qt-thread-safe)
        try:
            if get_mtc_reader:
                rd = get_mtc_reader()
                rd.subscribe(self._on_mtc)
        except Exception as e:
            print(f"[MidiView] MTC subscribe error: {e}")

    def _refresh_mtc_ports(self):
        if not get_mtc_reader:
            return
        try:
            rd = get_mtc_reader()
            self._combo_mtc_port.clear()
            for p in rd.list_ports():
                self._combo_mtc_port.addItem(p)
            if self._combo_mtc_port.count() == 0:
                self._combo_mtc_port.addItem("(keine MIDI-Ports)")
        except Exception as e:
            print(f"[MidiView] MTC list ports error: {e}")

    def _attach_mtc(self):
        if not get_mtc_reader:
            return
        port = self._combo_mtc_port.currentText()
        if not port or port.startswith("("):
            return
        try:
            ok = get_mtc_reader().attach_midi_input(port)
            if ok:
                self._append_log(f"MTC: Verbunden mit {port}")
            else:
                self._append_log(f"MTC: Verbindung fehlgeschlagen ({port})")
        except Exception as e:
            self._append_log(f"MTC: Fehler {e}")

    def _on_mtc(self, h: int, m: int, s: int, f: int):
        try:
            QTimer.singleShot(0, lambda: self._update_mtc_label(h, m, s, f))
        except Exception:
            pass

    def _update_mtc_label(self, h: int, m: int, s: int, f: int):
        self._lbl_mtc_time.setText(f"{h:02d}:{m:02d}:{s:02d}:{f:02d}")
        if get_mtc_reader:
            try:
                self._lbl_mtc_fps.setText(f"{get_mtc_reader().fps():.2f} fps")
            except Exception:
                pass
