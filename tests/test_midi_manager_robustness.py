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

import types

import pytest

from src.core.midi import midi_manager as mm


@pytest.fixture
def rtmidi_stub(monkeypatch):
    """Sorgt dafuer, dass ``mm.rtmidi`` monkeypatchbar ist.

    ``midi_manager`` bindet den Namen ``rtmidi`` NUR, wenn der optionale
    C-Extension-Import geklappt hat. Auf jedem Rechner ohne ``python-rtmidi``
    — also auch in der GitHub-CI und in einem frischen venv — existiert das
    Attribut gar nicht, und ``monkeypatch.setattr(mm.rtmidi, ...)`` scheiterte
    mit ``AttributeError``. Die Tests pruefen aber reine Python-Logik
    (Circuit-Breaker, Handle-Wiederverwendung, Port-Aufloesung) und brauchen
    kein echtes rtmidi. Deshalb hier notfalls ein leeres Modul einhaengen.
    """
    if getattr(mm, "rtmidi", None) is None:
        stub = types.SimpleNamespace(MidiIn=object, MidiOut=object)
        monkeypatch.setattr(mm, "rtmidi", stub, raising=False)
    return mm.rtmidi


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


def test_rtmidi_scan_error_is_soft_and_rate_limited(monkeypatch, rtmidi_stub):
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


def test_successful_rtmidi_scans_reuse_discovery_client(monkeypatch, rtmidi_stub):
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


def test_open_output_promotes_discovery_handle_without_new_client(monkeypatch, rtmidi_stub):
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


def test_open_output_resolves_portable_apc_hint_to_control_port(monkeypatch, rtmidi_stub):
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


class _PortsFakeMidiOut:
    """Fake-MidiOut mit fester Portliste und beobachtbarem Offen-Zustand."""

    ports: list[str] = []
    made: list = []

    def __init__(self):
        type(self).made.append(self)
        self.opened = None
        self.is_open = False

    def get_port_count(self):
        return len(type(self).ports)

    def get_port_name(self, index):
        return type(self).ports[index]

    def open_port(self, index):
        self.opened = index
        self.is_open = True

    def close_port(self):
        self.is_open = False

    def send_message(self, msg):
        if not self.is_open:
            raise RuntimeError("Port ist zu")


def _rtmidi_out_manager(monkeypatch, ports):
    cls = type("FakeOut", (_PortsFakeMidiOut,), {"ports": list(ports), "made": []})
    monkeypatch.setattr(mm, "_USE_WINMM", False)
    monkeypatch.setattr(mm, "RTMIDI_OK", True)
    monkeypatch.setattr(mm.rtmidi, "MidiOut", cls)
    return mm.MidiManager(), cls


def test_unresolvable_port_does_not_kill_the_open_output(monkeypatch, rtmidi_stub):
    """Regression: ein nicht auffindbarer Portname darf den LAUFENDEN Ausgang
    nicht schliessen.

    Vorher rief open_output() in diesem Fall close_port() auf genau dem Handle,
    der als ``self._output`` in Benutzung ist — ``_output``/``_output_name``
    blieben aber gesetzt. Der Manager meldete weiter „offen", es ging nie wieder
    ein Byte raus, und der Early-Return verhinderte jedes Wiederoeffnen. Real
    ausgeloest von ``midi_mapper._feedback_loop``, das den in der Show
    gespeicherten (plattformfremden) Portnamen dauernd erneut anfordert.
    """
    mgr, cls = _rtmidi_out_manager(monkeypatch, ["APC mini mk2"])
    try:
        assert mgr.open_output("APC mini mk2") is True
        handle = mgr._output
        assert handle.is_open is True

        # Portname aus einer auf Linux gespeicherten Show — hier unbekannt.
        assert mgr.open_output("APC mini mk2:APC mini mk2 Control 20:0") is False

        assert handle.is_open is True, "laufender Ausgang wurde geschlossen"
        assert mgr.current_output_name() == "APC mini mk2"
        assert mgr.send_message([0x90, 5, 21]) is True
    finally:
        mgr.close_all()


def test_unresolvable_port_keeps_discovery_handle_reusable(monkeypatch, rtmidi_stub):
    """Ohne offenen Ausgang darf ein Fehlversuch den Discovery-Handle nicht
    verbrennen — sonst legt der naechste Scan einen neuen ALSA-Client an."""
    mgr, cls = _rtmidi_out_manager(monkeypatch, ["Irgendein Synth"])
    try:
        assert mgr.list_outputs() == ["Irgendein Synth"]
        assert mgr.open_output("APC") is False
        assert mgr._scan_output is not None, "Discovery-Handle ging verloren"
        assert mgr.list_outputs() == ["Irgendein Synth"]
        assert len(cls.made) == 1, "es wurde ein zusaetzlicher Client erzeugt"
    finally:
        mgr.close_all()


def test_explicit_selection_is_exact_not_substring(monkeypatch, rtmidi_stub):
    """Die explizite Auswahl aus der Portliste muss exakt oeffnen.

    'APC mini mk2' ist Teilstring von 'MIDIOUT2 (APC mini mk2)'. Mit dem
    unscharfen Vergleich meldete open_output() Erfolg, ohne umzuschalten — die
    MIDI-Ansicht faerbte gruen und der Benutzer kam nie mehr auf den anderen
    Port.
    """
    mgr, _cls = _rtmidi_out_manager(
        monkeypatch, ["APC mini mk2", "MIDIOUT2 (APC mini mk2)"])
    try:
        assert mgr.open_output("MIDIOUT2 (APC mini mk2)") is True
        assert mgr.current_output_name() == "MIDIOUT2 (APC mini mk2)"

        # Unscharf (Profil-Hinweis) -> darf kurzschliessen.
        assert mgr.open_output("APC mini mk2", allow_hint=True) is True
        assert mgr.current_output_name() == "MIDIOUT2 (APC mini mk2)"

        # Explizit (Benutzerauswahl) -> muss wirklich umschalten.
        assert mgr.open_output("APC mini mk2", allow_hint=False) is True
        assert mgr.current_output_name() == "APC mini mk2"
    finally:
        mgr.close_all()


def test_failed_output_constructor_does_not_disable_input_scan(monkeypatch, rtmidi_stub):
    """Ein gescheiterter MidiOut()-Konstruktor darf die EINGANGS-Erkennung nicht
    mitreissen — sonst ist der APC als Eingabegeraet tot, obwohl nur der Ausgang
    scheiterte (Autoconnect findet dann nichts mehr)."""
    class BrokenMidiOut:
        def __init__(self):
            raise SystemError("ALSA: Cannot allocate memory")

    class WorkingMidiIn:
        def get_port_count(self):
            return 1

        def get_port_name(self, index):
            return "APC mini mk2 Notes"

        def close_port(self):
            pass

    monkeypatch.setattr(mm, "_USE_WINMM", False)
    monkeypatch.setattr(mm, "RTMIDI_OK", True)
    monkeypatch.setattr(mm.rtmidi, "MidiOut", BrokenMidiOut)
    monkeypatch.setattr(mm.rtmidi, "MidiIn", WorkingMidiIn)
    mgr = mm.MidiManager()
    try:
        assert mgr.open_output("APC") is False
        assert mgr._rtmidi_out_blocked is True
        # Entscheidend: Eingaenge bleiben scanbar.
        assert mgr.list_inputs() == ["APC mini mk2 Notes"]
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
