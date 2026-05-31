"""VCButton — Virtual Console Button Widget."""
from __future__ import annotations
import os
import json
from enum import Enum
from PySide6.QtWidgets import (QDialog, QFormLayout, QLineEdit, QComboBox,
                                QDialogButtonBox, QSizePolicy, QSpinBox, QLabel)
from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QPainter, QColor, QFont, QPen
from .vc_widget import VCWidget

_SNAPSHOTS_FILE = os.path.join(
    os.environ.get("APPDATA", os.path.expanduser("~")), "LightOS", "snapshots.json"
)


class ButtonAction(str, Enum):
    TOGGLE   = "Toggle"
    FLASH    = "Flash"
    FUNCTION_TOGGLE = "FunctionToggle"
    FUNCTION_FLASH  = "FunctionFlash"
    BLACKOUT = "Blackout"
    STOP_ALL = "StopAll"
    SNAPSHOT = "Snapshot"
    CLEAR    = "Clear"        # Programmer leeren (manuelle Farben/Snaps freigeben)
    TAP      = "Tap"          # Tap-Tempo: setzt globale BPM (beat-Effekte folgen)


class VCButton(VCWidget):
    """Pushbutton — Flash / Toggle / Blackout / StopAll / Snapshot."""

    def __init__(self, caption: str = "Button", parent=None):
        super().__init__(caption, parent)
        self.action = ButtonAction.TOGGLE
        self.function_id: int | None = None
        self.snapshot_index: int | None = None
        # Verhalten beim Starten einer Funktion:
        #   exclusive        -> stoppt alle anderen Funktionen (nur 1 aktiv)
        #   clear_programmer -> leert vorher den Programmer (manuelle Farben/Snaps
        #                       blockieren sonst den Effekt, da Programmer = hoechste Prioritaet)
        self.exclusive: bool = False
        self.clear_programmer: bool = False
        # APC-Pad-Anzeige-Stil: mirror = Effekt-Farbe spiegeln, solid = feste Farbe,
        # pulse = pulsieren, alternate = zwei Farben im Wechsel, wave = Dauer-Welle.
        self.pad_style: str = "mirror"
        self.pad_color2 = (0, 0, 255)   # zweite Farbe fuer 'alternate'

        # MIDI binding (-1 = keine Bindung)
        self.midi_ch: int = 0          # 0 = alle Kanäle
        self.midi_data1: int = -1      # Note / CC-Nummer
        self.midi_type: str = "note_on"

        self._pressed = False
        self._midi_armed = False       # leuchtet auf im MIDI-Learn-Modus
        self._bg_color = QColor("#1a3a5c")
        self._fg_color = QColor("#ffffff")
        self.resize(120, 60)

    # ── MIDI-Learn ───────────────────────────────────────────────────────────

    def arm_midi_learn(self):
        """Aktiviert den MIDI-Learn-Modus für diesen Button (visuelles Feedback)."""
        self._midi_armed = True
        self.update()

    def accept_midi(self, ch: int, data1: int, msg_type: str):
        """Speichert die empfangene MIDI-Bindung."""
        self.midi_ch = ch
        self.midi_data1 = data1
        self.midi_type = msg_type
        self._midi_armed = False
        self.update()

    # ── MIDI Teach (siehe VCWidget) ────────────────────────────────────────────

    def supports_midi_teach(self) -> bool:
        return True

    def current_midi_binding(self):
        if self.midi_data1 is None or self.midi_data1 < 0:
            return None
        return (self.midi_type, self.midi_ch, self.midi_data1)

    def apply_midi_binding(self, msg_type, channel, data1):
        if data1 is None or data1 < 0:
            self.midi_data1 = -1
            return
        # APC-Tasten -> note_on, Fader -> cc (VCButton kann beides auswerten)
        self.midi_type = "cc" if msg_type == "cc" else "note_on"
        self.midi_ch = channel or 0
        self.midi_data1 = data1

    def matches_midi(self, msg) -> bool:
        """True wenn die MIDI-Message zu dieser Bindung passt."""
        if self.midi_data1 < 0:
            return False
        if self.midi_type == "note_on":
            if msg.msg_type not in ("note_on", "note_off"):
                return False
        elif self.midi_type != msg.msg_type:
            return False
        if self.midi_ch != 0 and self.midi_ch != msg.channel:
            return False
        return self.midi_data1 == msg.data1

    def handle_midi(self, msg) -> bool:
        if not self.matches_midi(msg):
            return False
        self.trigger_from_midi(msg)
        return True

    def trigger_from_midi(self, msg):
        """Löst den Button durch eine MIDI-Message aus."""
        if msg.msg_type == "note_on" and msg.data2 > 0:
            self._pressed = True
            self._trigger(True)
            self.update()
        elif msg.msg_type in ("note_off",) or (msg.msg_type == "note_on" and msg.data2 == 0):
            self._pressed = False
            self._trigger(False)
            self.update()
        elif msg.msg_type == "cc":
            press = msg.data2 > 63
            if press != self._pressed:
                self._pressed = press
                self._trigger(press)
                self.update()

    # ── Snapshot ─────────────────────────────────────────────────────────────

    def _apply_snapshot(self, index: int):
        try:
            with open(_SNAPSHOTS_FILE, encoding="utf-8") as f:
                payload = json.load(f)
            if not isinstance(payload, list) or index >= len(payload):
                return
            snap_data = payload[index]
            if not snap_data:
                return
            raw = snap_data.get("values", {})
            from src.core.app_state import get_state
            state = get_state()
            for k, attrs in raw.items():
                for attr, val in attrs.items():
                    try:
                        state.set_programmer_value(int(k), attr, int(val))
                    except Exception:
                        pass
        except Exception as e:
            print(f"[VCButton] Snapshot-Apply-Fehler: {e}")

    # ── Action ───────────────────────────────────────────────────────────────

    def _trigger(self, press: bool):
        if press:
            try:
                from .vc_frame import VCFrame
                p = self.parent()
                while p is not None:
                    if isinstance(p, VCFrame) and p.is_solo():
                        p.on_child_activated(self)
                        break
                    p = p.parent()
            except Exception:
                pass

        from src.core.app_state import get_state
        state = get_state()

        if self.action == ButtonAction.BLACKOUT:
            state.output_manager.set_blackout(bool(press))
            return

        if self.action == ButtonAction.STOP_ALL:
            if press:
                state.playback_engine.stop_all()
            return

        if self.action == ButtonAction.SNAPSHOT:
            if press and self.snapshot_index is not None:
                self._apply_snapshot(self.snapshot_index)
            return

        if self.action == ButtonAction.CLEAR:
            if press:
                try:
                    state.clear_programmer()
                except Exception:
                    pass
            return

        if self.action == ButtonAction.TAP:
            if press:
                try:
                    from src.core.engine.bpm_manager import get_bpm_manager
                    get_bpm_manager().tap()
                except Exception:
                    pass
            return

        if self.action in (ButtonAction.FUNCTION_TOGGLE, ButtonAction.FUNCTION_FLASH):
            if self.function_id is None:
                return
            fid = int(self.function_id)
            fm = state.function_manager

            def _begin():
                # Manuelle Farben/Snaps freigeben + ggf. andere Funktionen stoppen,
                # damit der Effekt sichtbar wird bzw. nur einer laeuft.
                if self.clear_programmer:
                    try:
                        state.clear_programmer()
                    except Exception:
                        pass
                if self.exclusive:
                    try:
                        fm.stop_all()
                    except Exception:
                        pass
                fm.start(fid)

            if self.action == ButtonAction.FUNCTION_TOGGLE:
                if press:
                    if fm.is_running(fid):
                        fm.stop(fid)
                    else:
                        _begin()
            else:  # FUNCTION_FLASH
                if press:
                    _begin()
                else:
                    fm.stop(fid)
            return

        if self.function_id is None:
            return
        slot = self.function_id
        executors = state.playback_engine.executors
        if slot >= len(executors):
            return
        ex = executors[slot]
        if self.action == ButtonAction.FLASH:
            ex.press_btn("flash") if press else ex.release_btn("flash")
        elif self.action == ButtonAction.TOGGLE and press:
            ex.press_btn("go")

    # ── Mouse ─────────────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if self._edit_mode:
            super().mousePressEvent(event)
            return
        if self._run_input_blocked():       # Display-only: Touch gesperrt
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._pressed = True
            self._trigger(True)
            self.update()
        event.accept()

    def mouseReleaseEvent(self, event):
        if self._edit_mode:
            super().mouseReleaseEvent(event)
            return
        if event.button() == Qt.MouseButton.LeftButton and self._pressed:
            self._pressed = False
            self._trigger(False)
            self.update()
        event.accept()

    # ── Paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        bg = self._bg_color.lighter(160) if self._pressed else self._bg_color
        p.fillRect(self.rect(), bg)

        # "Gedrueckt"-Feedback (Maus ODER MIDI): deutlicher heller Rahmen
        if self._pressed:
            p.setPen(QPen(QColor("#ffe680"), 3))
            p.drawRect(self.rect().adjusted(1, 1, -2, -2))

        # MIDI-Learn-Arm: orange Rahmen pulsieren
        if self._midi_armed:
            p.setPen(QPen(QColor("#ff8800"), 3))
            p.drawRect(self.rect().adjusted(1, 1, -2, -2))

        p.setPen(self._fg_color)
        font = QFont("Segoe UI", 9, QFont.Weight.Bold)
        p.setFont(font)

        # Snapshot-Index anzeigen wenn Snapshot-Aktion
        display = self.caption
        if self.action == ButtonAction.SNAPSHOT and self.snapshot_index is not None:
            display += f"\n[Snap {self.snapshot_index + 1}]"

        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, display)

        # Farbbalken unten je nach Aktion
        if self.action == ButtonAction.FLASH:
            p.fillRect(0, self.height() - 4, self.width(), 4, QColor("#ff8800"))
        elif self.action in (ButtonAction.FUNCTION_TOGGLE, ButtonAction.FUNCTION_FLASH):
            p.fillRect(0, self.height() - 4, self.width(), 4, QColor("#3fb950"))
        elif self.action == ButtonAction.BLACKOUT:
            p.fillRect(0, self.height() - 4, self.width(), 4, QColor("#ff2222"))
        elif self.action == ButtonAction.SNAPSHOT:
            p.fillRect(0, self.height() - 4, self.width(), 4, QColor("#ffd700"))

        # MIDI-Bindung-Indikator oben rechts
        if self.midi_data1 >= 0:
            p.fillRect(self.width() - 8, 0, 8, 8, QColor("#00aaff"))

        p.end()

    # ── Properties dialog ────────────────────────────────────────────────────

    def _open_properties(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Button Einstellungen")
        form = QFormLayout(dlg)

        cap = QLineEdit(self.caption)
        form.addRow("Beschriftung:", cap)

        act = QComboBox()
        for a in ButtonAction:
            act.addItem(a.value)
        act.setCurrentText(self.action.value)
        form.addRow("Aktion:", act)

        slot = QLineEdit(str(self.function_id) if self.function_id is not None else "")
        form.addRow("Executor-Slot / Function-ID:", slot)

        # Funktion/Chase nach Namen auswaehlen -> fuellt das Function-ID-Feld.
        func_combo = QComboBox()
        func_combo.addItem("(nach ID/Slot oben)", -1)
        self._populate_function_combo(func_combo)
        if self.function_id is not None:
            for i in range(func_combo.count()):
                if func_combo.itemData(i) == self.function_id:
                    func_combo.setCurrentIndex(i)
                    break
        func_combo.currentIndexChanged.connect(
            lambda _i: slot.setText(str(func_combo.currentData()))
            if func_combo.currentData() is not None and func_combo.currentData() >= 0
            else None
        )
        form.addRow("Funktion/Chase (Name):", func_combo)

        # Snapshot-Auswahl
        snap_combo = QComboBox()
        snap_combo.addItem("(keiner)", -1)
        self._populate_snapshot_combo(snap_combo)
        if self.snapshot_index is not None:
            for i in range(snap_combo.count()):
                if snap_combo.itemData(i) == self.snapshot_index:
                    snap_combo.setCurrentIndex(i)
                    break
        form.addRow("Snapshot:", snap_combo)

        form.addRow(QLabel("── MIDI-Bindung ──"))

        midi_type_combo = QComboBox()
        midi_type_combo.addItems(["note_on", "cc"])
        midi_type_combo.setCurrentText(self.midi_type)
        form.addRow("MIDI-Typ:", midi_type_combo)

        midi_ch_spin = QSpinBox()
        midi_ch_spin.setRange(0, 16)
        midi_ch_spin.setValue(self.midi_ch)
        midi_ch_spin.setSpecialValueText("Alle")
        form.addRow("MIDI-Kanal (0=alle):", midi_ch_spin)

        midi_note_spin = QSpinBox()
        midi_note_spin.setRange(-1, 127)
        midi_note_spin.setValue(self.midi_data1)
        midi_note_spin.setSpecialValueText("keine")
        form.addRow("Note / CC (-1=keine):", midi_note_spin)

        form.addRow(QLabel("── APC-Pad-Anzeige ──"))
        pad_style_combo = QComboBox()
        _PAD_STYLES = [("mirror", "Spiegel (Effekt-Farbe)"), ("solid", "Feste Farbe"),
                       ("pulse", "Pulsieren"), ("alternate", "Zwei Farben im Wechsel"),
                       ("wave", "Dauer-Welle")]
        for key, label in _PAD_STYLES:
            pad_style_combo.addItem(label, key)
        for i, (key, _l) in enumerate(_PAD_STYLES):
            if key == self.pad_style:
                pad_style_combo.setCurrentIndex(i)
                break
        form.addRow("Pad-Stil:", pad_style_combo)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.caption = cap.text() or self.caption
            self.action = ButtonAction(act.currentText())
            try:
                self.function_id = int(slot.text())
            except ValueError:
                self.function_id = None
            snap_idx = snap_combo.currentData()
            self.snapshot_index = snap_idx if snap_idx >= 0 else None
            self.midi_type = midi_type_combo.currentText()
            self.midi_ch = midi_ch_spin.value()
            self.midi_data1 = midi_note_spin.value()
            self.pad_style = pad_style_combo.currentData() or "mirror"
            self.update()

    def _populate_function_combo(self, combo: QComboBox):
        """Listet alle Funktionen (Chases/Sequences/Scenes...) nach Namen auf."""
        try:
            from src.core.app_state import get_state
            funcs = get_state().function_manager.all()
            for f in sorted(funcs, key=lambda x: (x.name or "").lower()):
                ftype = getattr(f.function_type, "value", str(f.function_type))
                combo.addItem(f"{f.name}  [{ftype} #{f.id}]", int(f.id))
        except Exception as e:
            print(f"[VCButton] function combo error: {e}")

    def _populate_snapshot_combo(self, combo: QComboBox):
        try:
            with open(_SNAPSHOTS_FILE, encoding="utf-8") as f:
                payload = json.load(f)
            if not isinstance(payload, list):
                return
            for i, s in enumerate(payload):
                if s and s.get("values"):
                    name = s.get("name") or f"Snap {i + 1}"
                    combo.addItem(f"{i + 1}: {name}", i)
        except Exception:
            pass

    # ── Serialization ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["action"] = self.action.value
        d["function_id"] = self.function_id
        d["snapshot_index"] = self.snapshot_index
        d["exclusive"] = self.exclusive
        d["clear_programmer"] = self.clear_programmer
        d["pad_style"] = self.pad_style
        d["pad_color2"] = list(self.pad_color2)
        d["midi_ch"] = self.midi_ch
        d["midi_data1"] = self.midi_data1
        d["midi_type"] = self.midi_type
        return d

    def apply_dict(self, d: dict):
        super().apply_dict(d)
        self.action = ButtonAction(d.get("action", "Toggle"))
        self.function_id = d.get("function_id")
        self.snapshot_index = d.get("snapshot_index")
        self.exclusive = bool(d.get("exclusive", False))
        self.clear_programmer = bool(d.get("clear_programmer", False))
        self.pad_style = d.get("pad_style", "mirror")
        c2 = d.get("pad_color2", [0, 0, 255])
        self.pad_color2 = tuple(c2) if isinstance(c2, (list, tuple)) and len(c2) == 3 else (0, 0, 255)
        self.midi_ch = d.get("midi_ch", 0)
        self.midi_data1 = d.get("midi_data1", -1)
        self.midi_type = d.get("midi_type", "note_on")
