"""MIDI-Konsole — Monitoring, Konfiguration, Mapping, Virtueller Port."""
from __future__ import annotations
import time
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
    MidiMapping, MidiOutFeedback, get_midi_mapper,
    BUTTON_TOGGLE, BUTTON_FLASH, BUTTON_CONTINUOUS,
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

MAP_COLS = ["Name", "Target", "Typ", "Ch", "D1", "Mode", "ON", "OFF", "Port"]


class MidiLogSignal(QObject):
    log_received = Signal(str)
    msg_received = Signal(object)
    mtc_received = Signal(int, int, int, int)   # MTC aus dem Reader-Thread -> UI
    learn_received = Signal(object)             # MIDI-Learn-Ergebnis -> GUI-Thread


class MidiView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._midi = get_midi_manager()
        self._state = get_state()
        self._mapper = self._state.midi_mapper or get_midi_mapper(self._state)
        self._log_signal = MidiLogSignal()
        self._log_signal.log_received.connect(self._append_log)
        self._log_signal.msg_received.connect(self._on_midi_msg_ui)
        self._log_signal.mtc_received.connect(self._update_mtc_label)
        self._log_signal.learn_received.connect(self._on_learn_received)
        self._learn_target_row = -1
        self._monitor_active = True       # Plain-Bool: thread-sicher aus MIDI-Thread lesbar
        self._last_monitor_emit = 0.0     # Drosselung des CC-Stroms im Monitor
        self._log_callback = lambda t: self._log_signal.log_received.emit(t)
        self._midi_callback = self._on_midi_msg
        self._mtc_reader = None
        self._mtc_callback = None
        self._setup_ui()
        self._midi.subscribe_log(self._log_callback)
        self._midi.subscribe(self._midi_callback)

        # Auto-Refresh Ports alle 2 Sek - erkennt USB-Hotplug
        from PySide6.QtCore import QTimer
        self._port_refresh_timer = QTimer(self)
        self._port_refresh_timer.timeout.connect(self._refresh_ports)
        self._port_refresh_timer.start(2000)

    def closeEvent(self, event):
        """Keine MIDI-/MTC-Callbacks in eine bereits geschlossene Qt-View lassen."""
        timer = getattr(self, "_port_refresh_timer", None)
        if timer is not None:
            timer.stop()
        try:
            self._midi.unsubscribe(self._midi_callback)
            self._midi.unsubscribe_log(self._log_callback)
        except Exception:
            pass
        reader = getattr(self, "_mtc_reader", None)
        callback = getattr(self, "_mtc_callback", None)
        if reader is not None and callback is not None:
            try:
                reader.unsubscribe(callback)
            except Exception:
                pass
        super().closeEvent(event)

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

        btn_ctrl_lib = QPushButton("Controller-Profile…")
        btn_ctrl_lib.setToolTip(
            "Controller-Bibliothek: bekannte MIDI-/DMX-Controller mit "
            "Belegung, LED-Feedback und Mapping-Vorlagen (Feature 6); "
            "QLC+-Inputprofile (.qxi) importierbar")
        btn_ctrl_lib.clicked.connect(self._open_controller_browser)
        dev_l.addRow(btn_ctrl_lib)

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
        self._chk_monitor.toggled.connect(self._set_monitor_active)
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
        btn_feedback = QPushButton("Feedback...")
        btn_feedback.setToolTip("LED-Farben für ON/OFF (Velocity) setzen")
        btn_feedback.clicked.connect(self._edit_feedback_values)
        btn_save = QPushButton("Speichern")
        btn_save.clicked.connect(self._save_mappings)
        btn_load = QPushButton("Laden")
        btn_load.clicked.connect(self._load_mappings)
        for btn in [btn_add_map, btn_del_map, btn_learn, btn_feedback, btn_save, btn_load]:
            map_toolbar.addWidget(btn)
        map_toolbar.addStretch()
        map_l.addLayout(map_toolbar)

        self._map_table = QTableWidget(0, len(MAP_COLS))
        self._map_table.setHorizontalHeaderLabels(MAP_COLS)
        self._map_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._map_table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked)
        self._map_table.itemChanged.connect(self._on_map_item_changed)
        hdr = self._map_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
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
        self._refresh_map_table()

        if not self._midi.available:
            self._append_log("⚠ Kein MIDI-Backend verfügbar (weder rtmidi noch WinMM). MIDI deaktiviert.")
        elif not RTMIDI_OK:
            self._append_log("ℹ MIDI: Windows WinMM Backend aktiv (ARM-Modus, rtmidi nicht installiert)")

    # ── Geräteverwaltung ──────────────────────────────────────────────────────

    def _open_controller_browser(self):
        """Controller-Profile öffnen (MIDI-Geräte; Feature 6: Controller-DB)."""
        try:
            from src.ui.widgets.controller_browser import ControllerBrowserDialog
            ControllerBrowserDialog(self, midi_only=True).exec()
        except Exception as e:
            QMessageBox.warning(self, "Controller-Profile", str(e))

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
                self._combo_in.addItem("(Keine MIDI-Eingänge gefunden - APC angeschlossen?)")
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
                self._combo_out.addItem("(Keine MIDI-Ausgänge gefunden)")
            else:
                if prev_out in outputs:
                    self._combo_out.setCurrentText(prev_out)

        # Status-Hinweis im Status-Label falls keine Inputs
        if not inputs and hasattr(self, "_lbl_midi_status"):
            cur_status = self._lbl_midi_status.text()
            if not cur_status.startswith("IN:") and "TIPP" not in cur_status:
                self._lbl_midi_status.setText(
                    "Keine Eingänge. TIPP: USB neu einstecken, "
                    "anderen USB-Port probieren, MIDI 2.0 Modus prüfen"
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
        # WICHTIG: läuft im MIDI-Dispatch-Thread — niemals direkt auf Qt-Widgets zugreifen!
        # Stattdessen via Signal in den GUI-Thread marshallen (_on_midi_msg_ui).
        if not self._monitor_active:
            return
        # CC-Strom (Fader) auf ~60 Hz drosseln, damit die Qt-Event-Loop nicht überflutet
        # wird. Betrifft nur die Monitor-Anzeige; die Fader-Steuerung im MidiMapper
        # bleibt ungedrosselt.
        if msg.msg_type == "cc":
            now = time.monotonic()
            if now - self._last_monitor_emit < 0.015:
                return
            self._last_monitor_emit = now
        self._log_signal.msg_received.emit(msg)

    def _on_midi_msg_ui(self, msg: MidiMessage):
        # Läuft thread-sicher im GUI-Thread (queued Signal aus _on_midi_msg).
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

    def _set_monitor_active(self, active: bool):
        self._monitor_active = bool(active)

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
            button_mode=BUTTON_TOGGLE,
            midi_out=MidiOutFeedback(state_off=5, state_on=3, trigger_id=0),
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
        self._map_table.blockSignals(True)
        self._map_table.setRowCount(len(mappings))
        for row, m in enumerate(mappings):
            on_val = ""
            off_val = ""
            if m.midi_out:
                on_val = str(m.midi_out.state_on)
                off_val = str(m.midi_out.state_off)
            vals = [
                m.name,
                m.target_id,
                m.msg_type,
                str(m.channel),
                str(m.data1),
                m.button_mode,
                on_val,
                off_val,
                m.port_filter,
            ]
            for col, val in enumerate(vals):
                self._map_table.setItem(row, col, QTableWidgetItem(val))
        self._map_table.blockSignals(False)

    def _on_map_item_changed(self, item: QTableWidgetItem):
        row = item.row()
        mappings = self._mapper.get_mappings()
        if row < 0 or row >= len(mappings):
            return
        m = mappings[row]
        col = item.column()
        txt = item.text()
        try:
            if col == 0:
                m.name = txt
            elif col == 1:
                m.target_id = txt.strip()
                if ":" in m.target_id:
                    m.action, m.param = m.target_id.split(":", 1)
                elif m.target_id:
                    m.action = m.target_id
                    m.param = ""
            elif col == 2:
                m.msg_type = txt.strip() or "note_on"
            elif col == 3:
                m.channel = int(txt or "1")
            elif col == 4:
                m.data1 = int(txt or "0")
            elif col == 5:
                m.button_mode = txt.strip().lower()
            elif col == 6:
                if m.midi_out is None:
                    m.midi_out = MidiOutFeedback()
                m.midi_out.state_on = max(0, min(127, int(txt or "127")))
            elif col == 7:
                if m.midi_out is None:
                    m.midi_out = MidiOutFeedback()
                m.midi_out.state_off = max(0, min(127, int(txt or "0")))
            elif col == 8:
                m.port_filter = txt
            m.midi_in.device = m.port_filter
            m.midi_in.channel = m.channel
            m.midi_in.trigger_id = m.data1
            m.midi_in.message_type = "cc" if m.msg_type == "cc" else "note"
            if m.midi_out:
                if m.midi_out.trigger_id < 0:
                    m.midi_out.trigger_id = m.data1
                m.midi_out.channel = m.channel
                m.midi_out.message_type = "cc" if m.msg_type == "cc" else "note"
        except ValueError:
            pass

    def _start_learn(self):
        rows = {i.row() for i in self._map_table.selectedIndexes()}
        if not rows:
            QMessageBox.information(self, "MIDI Learn", "Erst eine Mapping-Zeile auswählen.")
            return
        self._learn_target_row = list(rows)[0]
        self._append_log("⏳ MIDI Learn — sende eine MIDI-Nachricht...")
        # Der Learn-Callback kommt aus dem MIDI-Dispatch-Thread. NUR das Signal
        # emittieren (thread-sicher) — _on_learn_received laeuft dann via
        # QueuedConnection auf dem GUI-Thread. Frueher lief der Handler direkt im
        # MIDI-Thread und oeffnete dort einen MODALEN QInputDialog + mutierte die
        # Mapping-Tabelle (Cross-Thread-Qt, Absturzgefahr).
        self._mapper.start_learn(
            lambda msg: self._log_signal.learn_received.emit(msg))

    def _on_learn_received(self, msg: MidiMessage):
        row = self._learn_target_row
        mappings = self._mapper.get_mappings()
        if row < 0 or row >= len(mappings):
            return
        m = mappings[row]
        m.set_from_learn_message(msg)
        self._prompt_feedback_values(m)
        self._refresh_map_table()
        self._append_log(f"✓ Learn: {msg.msg_type} CH{msg.channel} D1={msg.data1}")

    def _edit_feedback_values(self):
        rows = {i.row() for i in self._map_table.selectedIndexes()}
        if not rows:
            QMessageBox.information(self, "Feedback", "Erst eine Mapping-Zeile auswählen.")
            return
        row = list(rows)[0]
        mappings = self._mapper.get_mappings()
        if row < 0 or row >= len(mappings):
            return
        self._prompt_feedback_values(mappings[row])
        self._refresh_map_table()

    def _prompt_feedback_values(self, mapping: MidiMapping):
        if mapping.midi_out is None:
            mapping.midi_out = MidiOutFeedback(trigger_id=mapping.data1)
        default_off = mapping.midi_out.state_off
        default_on = mapping.midi_out.state_on
        off_val, ok = QInputDialog.getInt(
            self, "Feedback OFF", "Velocity OFF (0-127):", default_off, 0, 127, 1
        )
        if not ok:
            return
        on_val, ok = QInputDialog.getInt(
            self, "Feedback ON", "Velocity ON (0-127):", default_on, 0, 127, 1
        )
        if not ok:
            return
        mapping.midi_out.state_off = off_val
        mapping.midi_out.state_on = on_val
        mapping.midi_out.trigger_id = mapping.data1
        mapping.midi_out.channel = mapping.channel
        mapping.midi_out.message_type = "cc" if mapping.msg_type == "cc" else "note"
        out_port = self._combo_out.currentText()
        if out_port and not out_port.startswith("("):
            mapping.midi_out.device = out_port

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
                button_mode=BUTTON_CONTINUOUS,
                midi_out=MidiOutFeedback(trigger_id=i - 1),
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
                button_mode=BUTTON_TOGGLE,
                midi_out=MidiOutFeedback(trigger_id=i - 1, state_off=5, state_on=3),
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
                self._mtc_reader = rd
                self._mtc_callback = self._on_mtc
                rd.subscribe(self._mtc_callback)
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
        # Laeuft im MTC-Reader-Thread (kein Qt-Event-Loop) -> QTimer.singleShot
        # wuerde hier NIE feuern. Per Signal thread-sicher in den UI-Thread.
        try:
            self._log_signal.mtc_received.emit(int(h), int(m), int(s), int(f))
        except Exception:
            pass

    def _update_mtc_label(self, h: int, m: int, s: int, f: int):
        self._lbl_mtc_time.setText(f"{h:02d}:{m:02d}:{s:02d}:{f:02d}")
        if get_mtc_reader:
            try:
                self._lbl_mtc_fps.setText(f"{get_mtc_reader().fps():.2f} fps")
            except Exception:
                pass
