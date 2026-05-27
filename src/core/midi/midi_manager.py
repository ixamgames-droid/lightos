"""MIDI Manager — Geräte auflisten, empfangen, senden, virtueller Port."""
from __future__ import annotations
import threading
from dataclasses import dataclass
from typing import Callable

try:
    import rtmidi
    RTMIDI_OK = True
except ImportError:
    RTMIDI_OK = False

try:
    from .midi_backend_winmm import (
        WINMM_OK,
        list_inputs  as _wm_list_inputs,
        list_outputs as _wm_list_outputs,
        WinMMInput,
        WinMMOutput,
    )
except Exception:
    WINMM_OK = False
    _wm_list_inputs  = lambda: []
    _wm_list_outputs = lambda: []
    WinMMInput  = None
    WinMMOutput = None


@dataclass
class MidiMessage:
    port_name: str
    channel: int       # 1-16
    msg_type: str      # "note_on", "note_off", "cc", "pc", "pitchbend"
    data1: int         # Note / CC-Nummer / PC-Nummer
    data2: int         # Velocity / CC-Wert / 0


def _decode(raw: list[int], port_name: str) -> MidiMessage | None:
    if not raw:
        return None
    status = raw[0]
    msg_type_code = status & 0xF0
    channel = (status & 0x0F) + 1
    d1 = raw[1] if len(raw) > 1 else 0
    d2 = raw[2] if len(raw) > 2 else 0

    types = {
        0x90: "note_on" if d2 > 0 else "note_off",
        0x80: "note_off",
        0xB0: "cc",
        0xC0: "pc",
        0xE0: "pitchbend",
    }
    msg_type = types.get(msg_type_code)
    if msg_type is None:
        return None
    return MidiMessage(port_name, channel, msg_type, d1, d2)


class MidiManager:
    def __init__(self):
        self._inputs: dict[str, object] = {}     # name → rtmidi.MidiIn
        self._output: object | None = None       # rtmidi.MidiOut
        self._virtual_out: object | None = None
        self._callbacks: list[Callable[[MidiMessage], None]] = []
        self._log_callbacks: list[Callable[[str], None]] = []
        self._learn_cb: Callable[[MidiMessage], None] | None = None
        self.available = RTMIDI_OK or WINMM_OK

    # ── Port-Listing ─────────────────────────────────────────────────────────

    def list_inputs(self) -> list[str]:
        if RTMIDI_OK:
            m = rtmidi.MidiIn()
            ports = [m.get_port_name(i) for i in range(m.get_port_count())]
            del m
            return ports
        if WINMM_OK:
            return _wm_list_inputs()
        return []

    def list_outputs(self) -> list[str]:
        if RTMIDI_OK:
            m = rtmidi.MidiOut()
            ports = [m.get_port_name(i) for i in range(m.get_port_count())]
            del m
            return ports
        if WINMM_OK:
            return _wm_list_outputs()
        return []

    # ── Verbinden ────────────────────────────────────────────────────────────

    def open_input(self, port_name: str):
        if port_name in self._inputs:
            return
        if RTMIDI_OK:
            m = rtmidi.MidiIn()
            ports = [m.get_port_name(i) for i in range(m.get_port_count())]
            if port_name not in ports:
                del m
                return
            idx = ports.index(port_name)
            m.open_port(idx)
            m.set_callback(lambda msg, _: self._on_message(msg[0], port_name))
            self._inputs[port_name] = m
            self._log(f"MIDI Input geöffnet: {port_name}")
        elif WINMM_OK:
            ports = _wm_list_inputs()
            if port_name not in ports:
                return
            idx = ports.index(port_name)
            m = WinMMInput(idx, port_name, self._on_message)
            self._inputs[port_name] = m
            self._log(f"MIDI Input geöffnet (WinMM): {port_name}")

    def open_output(self, port_name: str):
        if RTMIDI_OK:
            m = rtmidi.MidiOut()
            ports = [m.get_port_name(i) for i in range(m.get_port_count())]
            if port_name not in ports:
                del m
                return
            idx = ports.index(port_name)
            m.open_port(idx)
            self._output = m
            self._log(f"MIDI Output geöffnet: {port_name}")
        elif WINMM_OK:
            ports = _wm_list_outputs()
            if port_name not in ports:
                return
            idx = ports.index(port_name)
            self._output = WinMMOutput(idx)
            self._log(f"MIDI Output geöffnet (WinMM): {port_name}")

    def open_virtual_input(self, name: str = "LightOS Virtual IN"):
        """Erstellt einen virtuellen MIDI-Eingang (andere Apps können darauf senden)."""
        if not RTMIDI_OK:
            return False
        try:
            m = rtmidi.MidiIn()
            m.open_virtual_port(name)
            m.set_callback(lambda msg, _: self._on_message(msg[0], f"Virtual:{name}"))
            self._inputs[f"Virtual:{name}"] = m
            self._log(f"Virtueller MIDI-Eingang erstellt: {name}")
            return True
        except Exception as e:
            self._log(f"Virtueller Port fehlgeschlagen: {e}")
            return False

    def open_virtual_output(self, name: str = "LightOS Virtual OUT"):
        """Erstellt einen virtuellen MIDI-Ausgang."""
        if not RTMIDI_OK:
            return False
        try:
            m = rtmidi.MidiOut()
            m.open_virtual_port(name)
            self._virtual_out = m
            self._log(f"Virtueller MIDI-Ausgang erstellt: {name}")
            return True
        except Exception as e:
            self._log(f"Virtueller Port fehlgeschlagen: {e}")
            return False

    def close_all(self):
        for m in self._inputs.values():
            try:
                m.close_port()
            except Exception:
                pass
        self._inputs.clear()
        if self._output:
            try:
                self._output.close_port()
            except Exception:
                pass
        self._output = None

    # ── Senden ───────────────────────────────────────────────────────────────

    def send_cc(self, channel: int, cc: int, value: int, virtual: bool = False):
        status = 0xB0 | ((channel - 1) & 0x0F)
        msg = [status, cc & 0x7F, value & 0x7F]
        out = self._virtual_out if virtual else self._output
        if out:
            out.send_message(msg)

    def send_note(self, channel: int, note: int, velocity: int = 127):
        status = 0x90 | ((channel - 1) & 0x0F)
        self._output and self._output.send_message([status, note & 0x7F, velocity & 0x7F])

    def send_note_off(self, channel: int, note: int):
        status = 0x80 | ((channel - 1) & 0x0F)
        self._output and self._output.send_message([status, note & 0x7F, 0])

    # ── Callbacks ────────────────────────────────────────────────────────────

    def subscribe(self, cb: Callable[[MidiMessage], None]):
        self._callbacks.append(cb)

    def subscribe_log(self, cb: Callable[[str], None]):
        self._log_callbacks.append(cb)

    def start_learn(self, callback: Callable[[MidiMessage], None]):
        """Einmaliger MIDI-Learn: ruft callback(msg) mit der naechsten empfangenen
        MIDI-Message auf. Normale Callbacks werden danach trotzdem ausgefuehrt."""
        self._learn_cb = callback

    def cancel_learn(self):
        """Bricht laufenden MIDI-Learn ab."""
        self._learn_cb = None

    def _on_message(self, raw: list[int], port_name: str):
        msg = _decode(raw, port_name)
        if msg:
            if self._learn_cb is not None:
                cb = self._learn_cb
                self._learn_cb = None
                try:
                    cb(msg)
                except Exception:
                    pass
            for cb in self._callbacks:
                try:
                    cb(msg)
                except Exception:
                    pass
            self._log(f"[{port_name}] {msg.msg_type} CH{msg.channel} D1={msg.data1} D2={msg.data2}")

    def _log(self, text: str):
        for cb in self._log_callbacks:
            try:
                cb(text)
            except Exception:
                pass


# Singleton
_manager: MidiManager | None = None


def get_midi_manager() -> MidiManager:
    global _manager
    if _manager is None:
        _manager = MidiManager()
    return _manager
