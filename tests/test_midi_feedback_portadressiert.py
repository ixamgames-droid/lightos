"""MIDI-FB-PORT — Mapping-Feedback reisst den MIDI-Ausgang nicht mehr weg.

`midi_mapper._feedback_loop` schaltete den GETEILTEN Ausgang auf das im Mapping
genannte Geraet um (``open_output``), sobald er nicht schon dorthin zeigte —
pro Nachricht. Zwei Folgen:

* Die Auswahl in der MIDI-Ansicht wurde dem Benutzer **unter den Fingern
  weggenommen**, ohne dass die Anzeige es mitbekam.
* Bei Mappings auf ZWEI Geraete sprang der Ausgang bei jeder Nachricht hin und
  her — und ``open_output`` ist auf ALSA nicht billig.

Das war ausserdem der Antagonist, der die APC-LEDs verstummen liess
(MIDI-LED-AUX): die sind seit dem portadressierten Senden immun, der Mapper war
es noch nicht.

**Gemessen vor dem Umbau**, weil der Umbau eine neue Gefahr schafft: nennt ein
Mapping einen Port, den es NICHT gibt, muesste bei jeder Nachricht ein neuer
Zweit-Handle geoeffnet werden. Ergebnis: **20 ``MidiOut()`` fuer 20
Nachrichten** — genau die ALSA-Client-Erschoepfung, gegen die die portadressierte
API ueberhaupt gebaut wurde. Deshalb gehoert der Negativ-Merker
(``_aux_failed`` + ``_AUX_RETRY_S``) mit in diese Runde und nicht in die naechste.
"""
from __future__ import annotations

import threading
import unittest

from src.core.midi import midi_manager as mm
from src.core.midi.midi_mapper import MidiMapper


class _FakeOut:
    """Zaehlt, wie oft ueberhaupt ein MidiOut gebaut wird."""
    instanzen = 0

    def __init__(self):
        type(self).instanzen += 1
        self.ports = ["APC mini mk2 Control", "Feedback-Pult"]
        self.offen: str | None = None
        self.gesendet: list = []

    def get_port_count(self):
        return len(self.ports)

    def get_port_name(self, i):
        return self.ports[i]

    def open_port(self, i):
        self.offen = self.ports[i]

    def close_port(self):
        self.offen = None

    def send_message(self, msg):
        self.gesendet.append(tuple(msg))

    def delete(self):
        pass


class _FakeRtmidi:
    MidiOut = _FakeOut


class NegativMerkerTest(unittest.TestCase):
    """Der Preis des portadressierten Sendens darf nicht der alte Fehler sein."""

    def setUp(self):
        _FakeOut.instanzen = 0
        self._alt = (getattr(mm, "rtmidi", None), mm.RTMIDI_OK, mm._USE_WINMM)
        mm.rtmidi = _FakeRtmidi()
        mm.RTMIDI_OK = True
        mm._USE_WINMM = False
        self.m = mm.MidiManager.__new__(mm.MidiManager)
        self.m._io_lock = threading.RLock()
        self.m._output = None
        self.m._output_name = ""
        self.m._aux_outputs = {}
        self.m._aux_failed = {}
        self.m._rtmidi_out_blocked = False
        self.m._log = lambda *_a, **_k: None

    def tearDown(self):
        mm.rtmidi, mm.RTMIDI_OK, mm._USE_WINMM = self._alt

    def test_toter_port_baut_nicht_pro_nachricht_einen_client(self):
        for _ in range(20):
            self.assertFalse(self.m.send_message_to("Gibt Es Nicht", [0x90, 1, 1]))
        self.assertEqual(_FakeOut.instanzen, 1,
                         "pro Nachricht ein neuer ALSA-Client")

    def test_der_merker_verfaellt(self):
        """Ein wieder eingestecktes Geraet muss von selbst zurueckkommen —
        sonst haette man den Aussetzer nur gegen einen dauerhaften getauscht."""
        self.assertFalse(self.m.send_message_to("Gibt Es Nicht", [0x90, 1, 1]))
        self.assertIn("Gibt Es Nicht", self.m._aux_failed)
        # Zeit vorspulen statt schlafen: der Test soll die REGEL pruefen.
        self.m._aux_failed["Gibt Es Nicht"] -= (mm._AUX_RETRY_S + 1.0)
        _FakeOut.instanzen = 0
        self.assertFalse(self.m.send_message_to("Gibt Es Nicht", [0x90, 1, 1]))
        self.assertEqual(_FakeOut.instanzen, 1,
                         "nach Ablauf der Sperre wurde gar nicht neu versucht")

    def test_gueltiger_port_bleibt_ungebremst(self):
        """Gegenprobe: der Merker darf einen funktionierenden Port nicht treffen."""
        for _ in range(20):
            self.assertTrue(self.m.send_message_to("Feedback-Pult", [0x90, 1, 1]))
        self.assertEqual(_FakeOut.instanzen, 1)
        self.assertEqual(self.m._aux_failed, {})

    def test_erfolg_loescht_einen_alten_merker(self):
        self.m._aux_failed["Feedback-Pult"] = 0.0    # laengst abgelaufen
        self.assertTrue(self.m.send_message_to("Feedback-Pult", [0x90, 1, 1]))
        self.assertNotIn("Feedback-Pult", self.m._aux_failed)

    def test_cc_und_note_nennen_denselben_port(self):
        self.assertTrue(self.m.send_cc_to("Feedback-Pult", 1, 7, 64))
        self.assertTrue(self.m.send_note_to("Feedback-Pult", 2, 36, 100))
        aux = self.m._aux_outputs["Feedback-Pult"]
        self.assertEqual(aux.gesendet, [(0xB0, 7, 64), (0x91, 36, 100)])
        self.assertEqual(_FakeOut.instanzen, 1, "je Port EIN Handle")


class _Midi:
    """Manager-Attrappe, die beide Wege getrennt mitschreibt."""

    def __init__(self):
        self.callbacks = []
        self.geteilt: list = []
        self.an_port: list = []
        self.open_output_calls = 0

    def subscribe(self, cb):
        self.callbacks.append(cb)

    def send_cc(self, channel, cc, value, virtual=False):
        self.geteilt.append(("cc", channel, cc, value))

    def send_note(self, channel, note, velocity=127):
        self.geteilt.append(("note", channel, note, velocity))

    def send_cc_to(self, port, channel, cc, value):
        self.an_port.append((port, "cc", channel, cc, value))
        return True

    def send_note_to(self, port, channel, note, velocity=127):
        self.an_port.append((port, "note", channel, note, velocity))
        return True

    def open_output(self, port_name, **_kw):
        self.open_output_calls += 1
        return True

    def current_output_name(self):
        return ""


class FeedbackWegTest(unittest.TestCase):
    """Prueft die Weiche direkt: mit Geraet adressiert, ohne Geraet geteilt."""

    def setUp(self):
        self.midi = _Midi()

    def test_mit_geraet_wird_adressiert(self):
        MidiMapper._sende(self.midi, "Feedback-Pult", "cc", 1, 7, 64)
        MidiMapper._sende(self.midi, "Feedback-Pult", "note", 1, 36, 127)
        self.assertEqual(self.midi.an_port, [
            ("Feedback-Pult", "cc", 1, 7, 64),
            ("Feedback-Pult", "note", 1, 36, 127),
        ])
        self.assertEqual(self.midi.geteilt, [])
        self.assertEqual(self.midi.open_output_calls, 0,
                         "gemeinsamer Ausgang wurde umgeschaltet")

    def test_ohne_geraet_bleibt_der_gemeinsame_ausgang(self):
        """Kein Ziel zu adressieren — dann ist der geteilte Ausgang richtig.

        Das ist die haeufigste Konfiguration: ein Pult, kein `device` im
        Mapping. Wuerde sie mit auf den Zweit-Handle-Pfad rutschen, haette der
        Umbau fuer die meisten Nutzer nur Nachteile.
        """
        MidiMapper._sende(self.midi, "", "cc", 1, 7, 64)
        MidiMapper._sende(self.midi, "", "note", 1, 36, 127)
        self.assertEqual(self.midi.geteilt, [
            ("cc", 1, 7, 64), ("note", 1, 36, 127),
        ])
        self.assertEqual(self.midi.an_port, [])


if __name__ == "__main__":
    unittest.main()
