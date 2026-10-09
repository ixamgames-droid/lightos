"""MIDI-3: Mappings ueberleben das Neustecken eines Pults.

ALSA vergibt beim Neustecken eine neue Client:Port-Nummer (``20:0`` ->
``24:0``), rtmidi auf Windows haengt einen Index an. Ein gespeichertes Mapping
muss trotzdem ueber den Geraetenamen greifen — und bei zwei gleichen Geraeten
das richtige (Name + Ordinal) treffen.
"""
from __future__ import annotations

import unittest

from src.core.midi.midi_manager import MidiMessage
import src.core.midi.midi_manager as mgr
import src.core.midi.midi_mapper as mm

ALT = "APC MINI:APC MINI MIDI 1 20:0"
NEU = "APC MINI:APC MINI MIDI 1 24:0"
ZWEI_A = "APC MINI:APC MINI MIDI 1 28:0"
ZWEI_B = "APC MINI:APC MINI MIDI 1 32:0"


class _FakeMidi:
    def __init__(self, eingaenge=()):
        self.callbacks = []
        self._eingaenge = list(eingaenge)

    def subscribe(self, cb):
        self.callbacks.append(cb)

    def offene_eingaenge(self):
        return list(self._eingaenge)

    def send_note(self, *a, **k):
        pass

    def send_cc(self, *a, **k):
        pass

    def send_note_to(self, *a, **k):
        return True

    def send_cc_to(self, *a, **k):
        return True


def _msg(port):
    return MidiMessage(port_name=port, channel=1, msg_type="note_on",
                       data1=5, data2=127)


class PortnamenTests(unittest.TestCase):
    def setUp(self):
        self._alt = mm.get_midi_manager

    def tearDown(self):
        mm.get_midi_manager = self._alt

    def _mit(self, eingaenge):
        fake = _FakeMidi(eingaenge)
        mm.get_midi_manager = lambda: fake

    def test_basisname_ohne_alsa_nummer(self):
        self.assertEqual(mgr.port_basisname(ALT), "APC MINI:APC MINI MIDI 1")
        self.assertEqual(mgr.port_basisname("APC MINI 1"), "APC MINI")
        self.assertEqual(mgr.port_basisname("MIDIOUT2 (APC mini mk2)"),
                         "MIDIOUT2 (APC mini mk2)")

    def test_altes_mapping_mit_nummer_greift_nach_neustecken(self):
        self._mit([NEU])
        b = mm.MidiInBinding(device=ALT, channel=1, trigger_id=5)
        self.assertTrue(b.matches(_msg(NEU)))

    def test_windows_index_wechsel(self):
        self._mit(["APC MINI 2"])
        b = mm.MidiInBinding(device="APC MINI 1", channel=1, trigger_id=5)
        self.assertTrue(b.matches(_msg("APC MINI 2")))

    def test_teilstring_filter_bleibt(self):
        self._mit([NEU])
        b = mm.MidiInBinding(device="APC", channel=1, trigger_id=5)
        self.assertTrue(b.matches(_msg(NEU)))
        b2 = mm.MidiInBinding(device="X-Touch", channel=1, trigger_id=5)
        self.assertFalse(b2.matches(_msg(NEU)))

    def test_learn_speichert_stabilen_namen(self):
        self._mit([ZWEI_A, ZWEI_B])
        b = mm.MidiInBinding.from_message(_msg(ZWEI_B))
        self.assertEqual(b.device, "APC MINI:APC MINI MIDI 1 #2")
        a = mm.MidiInBinding.from_message(_msg(ZWEI_A))
        self.assertEqual(a.device, "APC MINI:APC MINI MIDI 1")

    def test_zwei_gleiche_geraete_bleiben_getrennt(self):
        self._mit([ZWEI_A, ZWEI_B])
        erstes = mm.MidiInBinding(device="APC MINI:APC MINI MIDI 1",
                                  channel=1, trigger_id=5)
        zweites = mm.MidiInBinding(device="APC MINI:APC MINI MIDI 1 #2",
                                   channel=1, trigger_id=5)
        self.assertTrue(erstes.matches(_msg(ZWEI_A)))
        self.assertFalse(erstes.matches(_msg(ZWEI_B)))
        self.assertTrue(zweites.matches(_msg(ZWEI_B)))
        self.assertFalse(zweites.matches(_msg(ZWEI_A)))

    def test_alte_nummer_noch_vorhanden_bleibt_exakt(self):
        # Beide Pulte stecken, die gespeicherte Nummer existiert noch: nur
        # genau dieses Geraet, nicht auch das andere gleichnamige.
        self._mit([ZWEI_A, ZWEI_B])
        b = mm.MidiInBinding(device=ZWEI_B, channel=1, trigger_id=5)
        self.assertTrue(b.matches(_msg(ZWEI_B)))
        self.assertFalse(b.matches(_msg(ZWEI_A)))

    def test_ausgang_wird_nach_neustecken_aufgeloest(self):
        ports = ["Midi Through:Midi Through Port-0 14:0", NEU]
        self.assertEqual(mgr.loese_portnamen_auf(ALT, ports), NEU)
        self.assertEqual(mgr.loese_portnamen_auf(NEU, ports), NEU)
        self.assertIsNone(mgr.loese_portnamen_auf("X-Touch 9:0", ports))


if __name__ == "__main__":
    unittest.main()
