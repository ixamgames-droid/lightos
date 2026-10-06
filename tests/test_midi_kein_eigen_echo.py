"""MIDI-1: LightOS hoert seine eigenen MIDI-Ausgaenge nicht als Eingang.

Unter Linux/ALSA legt jeder geoeffnete RtMidi-Ausgang einen eigenen LESBAREN
Sequencer-Port an. ``open_all_inputs`` (4-s-Autoconnect) oeffnete ihn als
Eingang mit: jede LED-/Feedback-Meldung an den Controller kam als Eingabe
zurueck und loeste Mappings bzw. VC-Buttons aus (z. B. Blackout).

Die Tests laufen mit ECHTEN virtuellen ALSA-Ports. Ohne Sequencer (Windows,
CI ohne /dev/snd/seq) werden sie uebersprungen; dort ist kein Echo zu erwarten.
Der plattformneutrale Teil (Filter-Logik) laeuft ueberall.
"""
from __future__ import annotations

import os
import sys
import time

import pytest

from src.core.midi import midi_manager as mm

_ALSA = (sys.platform.startswith("linux") and mm.RTMIDI_OK
         and not mm._USE_WINMM and os.path.exists("/dev/snd/seq"))
alsa = pytest.mark.skipif(not _ALSA, reason="braucht ALSA-Sequencer + python-rtmidi")


def _warte(bedingung, sekunden=1.0):
    ende = time.monotonic() + sekunden
    while time.monotonic() < ende:
        if bedingung():
            return True
        time.sleep(0.01)
    return bedingung()


def test_eigener_port_erkannt_fremde_nicht():
    eigen = f"{mm.OWN_OUTPUT_CLIENT}:RtMidi output 129:0"
    assert mm.is_own_port(eigen)
    for fremd in ("RtMidiOut Client:RtMidi output 130:0",
                  "APC mini mk2:APC mini mk2 Control 24:0",
                  "MIDIOUT2 (APC mini mk2)", "LightOS", ""):
        assert not mm.is_own_port(fremd), fremd


@pytest.fixture
def geraet():
    """Virtuelles 'Pult': ein Eingang (empfaengt LEDs) + ein Ausgang (Tasten)."""
    import rtmidi
    led_in = rtmidi.MidiIn(name="EchoTest-Pult")
    led_in.open_virtual_port("EchoTest LEDs")
    empfangen: list = []
    led_in.set_callback(lambda m, _: empfangen.append(m[0]))
    tasten = rtmidi.MidiOut(name="EchoTest-Pult")
    tasten.open_virtual_port("EchoTest Tasten")
    time.sleep(0.2)
    yield empfangen, tasten
    led_in.close_port()
    tasten.close_port()
    led_in.delete()
    tasten.delete()


@pytest.fixture
def manager():
    m = mm.MidiManager()
    yield m
    m.close_all()


@alsa
def test_feedback_an_das_geraet_erzeugt_keine_eingabe(geraet, manager):
    empfangen, tasten = geraet
    ziel = next(p for p in manager.list_outputs() if "EchoTest LEDs" in p)
    assert manager.open_output(ziel)
    # Zweit-Ausgang (Mapping-Feedback mit Geraetenamen) und virtueller Ausgang
    # sind ebenfalls eigene Ports.
    assert manager.send_note_to(ziel, 1, 10, 1)
    assert manager.open_virtual_output("EchoTest Virtual OUT")

    eingaenge = manager.list_inputs()
    assert not any(mm.is_own_port(p) for p in eingaenge), eingaenge
    assert not any("RtMidi output" in p for p in eingaenge), eingaenge
    assert not any("EchoTest Virtual OUT" in p for p in eingaenge), eingaenge

    manager.open_all_inputs()   # = Autoconnect der MainWindow
    gesehen: list = []
    manager.subscribe(lambda msg: gesehen.append(msg))

    # Feedback an das Geraet senden: geteilter Ausgang, Zweit-Ausgang, virtuell.
    manager.send_note(1, 56, 3)
    manager.send_cc(1, 7, 50)
    manager.send_note_to(ziel, 1, 57, 5)
    manager.send_cc(1, 8, 90, virtual=True)
    assert _warte(lambda: len(empfangen) >= 4), empfangen
    time.sleep(0.3)
    assert gesehen == [], [(g.port_name, g.msg_type, g.data1) for g in gesehen]

    # Gegenprobe: echte Tasten des Geraets kommen weiterhin an.
    tasten.send_message([0x90, 60, 127])
    assert _warte(lambda: any(g.data1 == 60 for g in gesehen)), gesehen
    assert all("EchoTest Tasten" in g.port_name for g in gesehen)


@alsa
def test_eigener_port_laesst_sich_nicht_explizit_als_eingang_oeffnen(geraet, manager):
    import rtmidi
    ziel = next(p for p in manager.list_outputs() if "EchoTest LEDs" in p)
    assert manager.open_output(ziel)
    roh = rtmidi.MidiIn()
    try:
        eigene = [p for p in roh.get_ports() if mm.is_own_port(p)]
    finally:
        roh.delete()
    assert eigene, "eigener Ausgang sollte im ALSA-Graphen als Quelle sichtbar sein"
    assert manager.open_input(eigene[0]) is False
    assert eigene[0] not in manager._inputs


@alsa
def test_mapping_loest_durch_eigenes_feedback_nicht_aus(geraet, manager, monkeypatch):
    """Ende-zu-Ende ueber den Mapper: Note 99 -> Page 4, nur Feedback gesendet."""
    import src.core.midi.midi_mapper as mmap
    empfangen, _tasten = geraet

    class _PE:
        current_page = 0
        executors: list = []

        def set_page(self, p):
            self.current_page = p

    class _OM:
        grand_master = 1.0

        def subscribe_grand_master(self, cb):
            pass

    class _St:
        playback_engine = _PE()
        output_manager = _OM()

    monkeypatch.setattr(mmap, "get_midi_manager", lambda: manager)
    mapper = mmap.MidiMapper(_St())
    try:
        mapper.add_mapping(mmap.MidiMapping(
            msg_type="note_on", data1=99, action=mmap.ACTION_PAGE_SELECT, param="4"))
        ziel = next(p for p in manager.list_outputs() if "EchoTest LEDs" in p)
        assert manager.open_output(ziel)
        manager.open_all_inputs()
        manager.send_note(1, 99, 127)
        assert _warte(lambda: [0x90, 99, 127] in empfangen), empfangen
        time.sleep(0.3)
        assert _St.playback_engine.current_page == 0
    finally:
        mapper.close()
