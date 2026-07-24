"""MIDI-Manager Robustheit: Reconnect toter Handles (F3) + RX-Queue-Overflow (F2).

Belegt in ``docs/MIDI_AUDIT_2026-07-13.md``:

* **F3 (MIDI-RECONN):** ``open_input`` kehrte sofort zurueck, solange der Portname
  im Dict stand — ein toter Handle (USB-Unplug/Replug) wurde NIE ersetzt, der APC
  blieb stumm bis App-Neustart. Fix: Handle-Lebendigkeit pruefen, toten Handle
  schliessen+evakuieren und neu oeffnen; verschwundene Ports in ``open_all_inputs``
  evakuieren.
* **F2 (MIDI-QDROP):** die bounded RX-Queue (maxsize 4096) verwarf bei Overflow
  still einzelne Nachrichten — ein gedropptes Note-Off liess einen Flash/Moment-
  Button dauerhaft an. Fix: Drops zaehlen+loggen, und Note-Off/CC-0 bevorzugt
  zustellen (aeltestes Nicht-Release weicht).

Headless, ohne echtes MIDI-Geraet: das WinMM-Backend wird per monkeypatch durch
ein Fake ersetzt.
"""
import os
import queue

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from src.core.midi import midi_manager as mm


class FakeInput:
    """rtmidi/WinMM-kompatibler Fake-Input-Handle mit is_alive()-Protokoll."""

    def __init__(self, device_idx, port_name, on_raw):
        self.device_idx = device_idx
        self.port_name = port_name
        self.on_raw = on_raw
        self.closed = False
        self._alive = True

    def is_alive(self):
        return self._alive

    def close_port(self):
        self.closed = True


@pytest.fixture
def winmm_stub(monkeypatch):
    """Erzwingt den WinMM-Pfad mit Fake-Handles und steuerbarer Portliste."""
    ports = {"names": ["APC"]}
    monkeypatch.setattr(mm, "_USE_WINMM", True)
    monkeypatch.setattr(mm, "_winmm_list_inputs", lambda: list(ports["names"]), raising=False)
    monkeypatch.setattr(mm, "WinMMInput", FakeInput, raising=False)
    return ports


def _stop_rx(mgr):
    """RX-Dispatch-Thread anhalten -> Queue-Zustand deterministisch testbar."""
    mgr._rx_running = False
    mgr._rx_thread.join(timeout=1.0)


# ── F3: Reconnect ──────────────────────────────────────────────────────────────

def test_open_input_replaces_dead_handle(winmm_stub):
    """Ein toter Handle wird beim erneuten open_input evakuiert + neu geoeffnet."""
    mgr = mm.MidiManager()
    try:
        mgr.open_input("APC")
        h1 = mgr._inputs["APC"]
        assert isinstance(h1, FakeInput)

        # Lebender Handle -> zweiter Aufruf laesst ihn unangetastet.
        mgr.open_input("APC")
        assert mgr._inputs["APC"] is h1
        assert h1.closed is False

        # USB-Unplug/Replug: Handle tot markieren.
        h1._alive = False
        mgr.open_input("APC")
        h2 = mgr._inputs["APC"]
        assert h2 is not h1, "toter Handle wurde nicht ersetzt"
        assert h1.closed is True, "alter (toter) Handle wurde nicht geschlossen"
        assert h2.is_alive() is True
    finally:
        mgr.close_all()


def test_open_all_inputs_evicts_vanished_port(winmm_stub):
    """Ein waehrend des Betriebs verschwundener Port wird evakuiert und beim
    Replug mit frischem Handle neu geoeffnet (realer WinMM-Reconnect-Pfad)."""
    mgr = mm.MidiManager()
    try:
        mgr.open_all_inputs()
        h1 = mgr._inputs["APC"]

        # Unplug: Port verschwindet aus der Geraeteliste.
        winmm_stub["names"] = []
        mgr.open_all_inputs()
        assert "APC" not in mgr._inputs, "verschwundener Port wurde nicht evakuiert"
        assert h1.closed is True

        # Replug: Port wieder da -> frischer Handle statt totem.
        winmm_stub["names"] = ["APC"]
        mgr.open_all_inputs()
        assert "APC" in mgr._inputs
        assert mgr._inputs["APC"] is not h1
    finally:
        mgr.close_all()


def test_rtmidi_scan_error_is_soft_and_rate_limited(monkeypatch):
    """Ein kaputter ALSA-Sequencer darf weder Start noch Refresh-Schleife
    beenden und soll nicht alle zwei Sekunden neue native Clients erzeugen."""
    calls = {"n": 0}

    class BrokenMidiIn:
        def __init__(self):
            calls["n"] += 1
            raise SystemError("ALSA sequencer unavailable")

    monkeypatch.setattr(mm, "_USE_WINMM", False)
    monkeypatch.setattr(mm, "RTMIDI_OK", True)
    monkeypatch.setattr(mm.rtmidi, "MidiIn", BrokenMidiIn)
    mgr = mm.MidiManager()
    try:
        assert mgr.list_inputs() == []
        assert mgr.list_inputs() == []
        assert calls["n"] == 1, "Circuit-Breaker muss wiederholte native Scans drosseln"
        assert mgr._rtmidi_retry_after > 0
    finally:
        mgr.close_all()


def test_successful_rtmidi_scans_reuse_discovery_client(monkeypatch):
    """Hotplug-Polling darf nicht pro Aufruf einen neuen ALSA-Sequencer-Client
    erzeugen; sonst ist dessen Client-Limit nach kurzer Laufzeit erschoepft."""
    made = []

    class ScanMidiIn:
        def __init__(self):
            self.closed = False
            made.append(self)

        def get_port_count(self):
            return 1

        def get_port_name(self, index):
            assert index == 0
            return "APC mini mk2 Notes"

        def close_port(self):
            self.closed = True

    monkeypatch.setattr(mm, "_USE_WINMM", False)
    monkeypatch.setattr(mm, "RTMIDI_OK", True)
    monkeypatch.setattr(mm.rtmidi, "MidiIn", ScanMidiIn)
    mgr = mm.MidiManager()
    try:
        assert mgr.list_inputs() == ["APC mini mk2 Notes"]
        assert mgr.list_inputs() == ["APC mini mk2 Notes"]
        assert mgr.list_inputs() == ["APC mini mk2 Notes"]
        assert len(made) == 1
        assert mgr._scan_input is made[0]
    finally:
        mgr.close_all()
    assert made[0].closed is True
    assert mgr._scan_input is None


def test_open_output_promotes_discovery_handle_without_new_client(monkeypatch):
    """Portscan + Oeffnen teilen einen MidiOut-Client statt pro Klick neue
    ALSA-Clients zu erzeugen."""
    made = []

    class FakeMidiOut:
        def __init__(self):
            made.append(self)
            self.opened = None
            self.closed = False

        def get_port_count(self):
            return 1

        def get_port_name(self, index):
            return "APC mini mk2 Control"

        def open_port(self, index):
            assert self.closed is False, (
                "frischer Discovery-Handle darf vor dem ersten open_port nicht "
                "geschlossen werden")
            self.opened = index

        def close_port(self):
            self.closed = True

    monkeypatch.setattr(mm, "_USE_WINMM", False)
    monkeypatch.setattr(mm, "RTMIDI_OK", True)
    monkeypatch.setattr(mm.rtmidi, "MidiOut", FakeMidiOut)
    mgr = mm.MidiManager()
    try:
        assert mgr.list_outputs() == ["APC mini mk2 Control"]
        assert mgr.open_output("APC mini mk2 Control") is True
        assert mgr.open_output("APC mini mk2 Control") is True
        assert len(made) == 1
        assert mgr._output is made[0]
        assert mgr._scan_output is None
    finally:
        mgr.close_all()


def test_open_output_resolves_portable_apc_hint_to_control_port(monkeypatch):
    made = []

    class FakeMidiOut:
        def __init__(self):
            made.append(self)
            self.opened = None

        def get_port_count(self):
            return 2

        def get_port_name(self, index):
            return [
                "APC mini mk2:APC mini mk2 Notes 20:1",
                "APC mini mk2:APC mini mk2 Control 20:0",
            ][index]

        def open_port(self, index):
            self.opened = index

        def close_port(self):
            pass

    monkeypatch.setattr(mm, "_USE_WINMM", False)
    monkeypatch.setattr(mm, "RTMIDI_OK", True)
    monkeypatch.setattr(mm.rtmidi, "MidiOut", FakeMidiOut)
    mgr = mm.MidiManager()
    try:
        assert mgr.open_output("APC") is True
        assert mgr._output.opened == 1
        assert "Control" in mgr.current_output_name()
        assert len(made) == 1
    finally:
        mgr.close_all()


# ── F2: RX-Queue-Overflow ────────────────────────────────────────────────────

def test_is_release_classification():
    is_rel = mm.MidiManager._is_release
    assert is_rel([0x80, 60, 0]) is True      # Note-Off
    assert is_rel([0x90, 60, 0]) is True      # Note-On Velocity 0 == Note-Off
    assert is_rel([0xB0, 20, 0]) is True       # CC-Wert 0 -> Release
    assert is_rel([0x90, 60, 100]) is False    # Note-On (Nicht-Release)
    assert is_rel([0xB0, 20, 127]) is False    # CC-Wert 127
    assert is_rel([]) is False


def test_queue_overflow_never_drops_note_off(winmm_stub):
    """Bei voller Queue geht ein ankommendes Note-Off NICHT verloren: ein aelteres
    Nicht-Release weicht, das Note-Off wird zugestellt und der Drop gezaehlt."""
    mgr = mm.MidiManager()
    _stop_rx(mgr)  # Consumer anhalten, damit die Queue nicht leerlaeuft
    try:
        # Queue randvoll mit Note-On (Nicht-Release) fuellen.
        for _ in range(mm._RX_QUEUE_MAX):
            mgr._rx_queue.put_nowait(([0x90, 60, 100], "APC"))
        assert mgr._rx_queue.full()

        before = mgr._rx_dropped
        # Note-Off trifft auf volle Queue.
        mgr._on_message([0x80, 60, 0], "APC")

        assert mgr._rx_queue.full(), "Queue sollte voll bleiben (Platztausch, kein Wachstum)"
        assert mgr._rx_dropped == before + 1, "Drop wurde nicht gezaehlt"

        # Das Note-Off muss jetzt tatsaechlich in der Queue stecken.
        found_release = False
        while True:
            try:
                raw, _ = mgr._rx_queue.get_nowait()
            except queue.Empty:
                break
            if mm.MidiManager._is_release(raw):
                found_release = True
        assert found_release, "Note-Off wurde still verworfen statt zugestellt"
    finally:
        mgr._rx_running = False
        mgr.close_all()


def test_queue_overflow_drops_and_counts_nonrelease(winmm_stub):
    """Ein ankommendes Nicht-Release wird bei voller Queue verworfen + gezaehlt
    (nicht mehr still), und die Queue waechst nicht ueber maxsize."""
    mgr = mm.MidiManager()
    _stop_rx(mgr)
    try:
        for _ in range(mm._RX_QUEUE_MAX):
            mgr._rx_queue.put_nowait(([0x90, 60, 100], "APC"))
        assert mgr._rx_queue.full()

        before = mgr._rx_dropped
        mgr._on_message([0x90, 61, 100], "APC")  # weiteres Note-On -> verworfen

        assert mgr._rx_dropped == before + 1
        assert mgr._rx_queue.qsize() == mm._RX_QUEUE_MAX
    finally:
        mgr._rx_running = False
        mgr.close_all()
