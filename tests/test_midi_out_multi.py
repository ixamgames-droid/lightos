"""MIDI-OUT-MULTI: portadressiertes Senden ohne ALSA-Clients zu verheizen.

Bisher gab es genau EINEN gemeinsamen MIDI-Ausgang: MIDI-Ansicht,
Mapping-Feedback und die APC-LED-Treiber teilten ihn. Das war kein
Schönheitsfehler, sondern eine Notbremse — jeder eigene ``MidiOut()`` legt auf
ALSA einen Sequencer-Client an, und wiederholtes Öffnen erschöpfte ihn.

Der Preis war eine stille Einschränkung: die LED-Treiber senden nur, solange
der geteilte Ausgang noch auf den APC zeigt (``_targets_apc``). Wählte man in
der MIDI-Ansicht ein anderes Gerät, hörte das LED-Feedback auf — ohne Meldung.

``send_message_to`` löst das, ohne die Notbremse aufzugeben: **ein Handle pro
PORT, gehalten** — nicht pro Nachricht. Genau das prüfen diese Tests, denn ein
Handle pro Nachricht wäre die Rückkehr des ursprünglichen Problems und im
Betrieb erst nach Stunden zu merken.
"""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.midi import midi_manager as mm                       # noqa: E402


class _FakeOut:
    """Zählt Öffnungen und merkt sich, was gesendet wurde."""
    instanzen = 0

    def __init__(self):
        type(self).instanzen += 1
        self.ports = ["APC mini mk2 Control", "Feedback-Pult", "Sonstwas"]
        self.offen: str | None = None
        self.gesendet: list = []
        self.geschlossen = 0

    def get_port_count(self):
        return len(self.ports)

    def get_port_name(self, i):
        return self.ports[i]

    def open_port(self, idx):
        self.offen = self.ports[idx]

    def close_port(self):
        self.geschlossen += 1
        self.offen = None

    def delete(self):
        pass

    def send_message(self, msg):
        self.gesendet.append(list(msg))


class _FakeRtmidi:
    MidiOut = _FakeOut


class SendMessageToTest(unittest.TestCase):
    def setUp(self):
        _FakeOut.instanzen = 0
        self._echt_rtmidi = getattr(mm, "rtmidi", None)
        self._echt_ok = mm.RTMIDI_OK
        self._echt_winmm = mm._USE_WINMM
        mm.rtmidi = _FakeRtmidi()
        mm.RTMIDI_OK = True
        mm._USE_WINMM = False
        self.m = mm.MidiManager.__new__(mm.MidiManager)
        # Nur die Felder, die send_message_to wirklich anfasst — ein voller
        # __init__ würde echte Ports scannen.
        import threading
        self.m._io_lock = threading.RLock()
        self.m._output = None
        self.m._output_name = ""
        self.m._aux_outputs = {}
        self.m._rtmidi_out_blocked = False
        self.m._log = lambda *_a, **_k: None

    def tearDown(self):
        mm.rtmidi = self._echt_rtmidi
        mm.RTMIDI_OK = self._echt_ok
        mm._USE_WINMM = self._echt_winmm

    def test_sendet_an_den_genannten_port(self):
        self.assertTrue(self.m.send_message_to("Feedback-Pult", [0x90, 1, 127]))
        aux = self.m._aux_outputs["Feedback-Pult"]
        self.assertEqual(aux.offen, "Feedback-Pult")
        self.assertEqual(aux.gesendet, [[0x90, 1, 127]])

    def test_haelt_das_handle_statt_pro_nachricht_zu_oeffnen(self):
        """★ Der Kern. Ein Handle PRO NACHRICHT waere die Rueckkehr des
        Problems, das die Ein-Ausgang-Regel ueberhaupt erst erzwungen hat —
        und im Betrieb erst nach Stunden zu merken."""
        for i in range(50):
            self.m.send_message_to("Feedback-Pult", [0x90, i, 100])
        self.assertEqual(_FakeOut.instanzen, 1,
                         "pro Port genau EIN Handle, egal wie viele Nachrichten")
        self.assertEqual(len(self.m._aux_outputs["Feedback-Pult"].gesendet), 50)

    def test_zwei_ports_zwei_handles(self):
        self.m.send_message_to("Feedback-Pult", [0x90, 1, 1])
        self.m.send_message_to("Sonstwas", [0x90, 2, 2])
        self.assertEqual(_FakeOut.instanzen, 2)
        self.assertEqual(self.m.aux_output_names(), ["Feedback-Pult", "Sonstwas"])

    def test_haupt_ausgang_wird_wiederverwendet(self):
        """Zeigt der Haupt-Ausgang schon dorthin, waere ein zweiter Client
        Verschwendung — und auf manchen Backends gar nicht erlaubt."""
        haupt = _FakeOut()
        _FakeOut.instanzen = 0          # den Haupt-Handle nicht mitzaehlen
        self.m._output = haupt
        self.m._output_name = "Feedback-Pult"
        self.assertTrue(self.m.send_message_to("Feedback-Pult", [0x90, 5, 5]))
        self.assertEqual(_FakeOut.instanzen, 0, "kein Zweit-Handle noetig")
        self.assertEqual(haupt.gesendet, [[0x90, 5, 5]])
        self.assertEqual(self.m.aux_output_names(), [])

    def test_unbekannter_port_gibt_false_und_haelt_nichts(self):
        self.assertFalse(self.m.send_message_to("Gibt-Es-Nicht", [0x90, 1, 1]))
        self.assertEqual(self.m.aux_output_names(), [],
                         "ein nicht geoeffneter Port darf keinen Handle hinterlassen")

    def test_leerer_portname_ist_kein_fehlerfall(self):
        for wert in ("", None, "   "):
            self.assertFalse(self.m.send_message_to(wert, [0x90, 1, 1]))
        self.assertEqual(_FakeOut.instanzen, 0)

    def test_sendefehler_raeumt_den_toten_handle_weg(self):
        """Sonst bliebe ein kaputter Handle fuer immer im Cache und jeder
        weitere Sendeversuch liefe ins Leere."""
        self.m.send_message_to("Feedback-Pult", [0x90, 1, 1])
        aux = self.m._aux_outputs["Feedback-Pult"]

        def kaputt(_msg):
            raise OSError("Port weg")
        aux.send_message = kaputt
        self.assertFalse(self.m.send_message_to("Feedback-Pult", [0x90, 2, 2]))
        self.assertEqual(self.m.aux_output_names(), [])

    def test_close_aux_output_gibt_frei(self):
        self.m.send_message_to("Feedback-Pult", [0x90, 1, 1])
        aux = self.m._aux_outputs["Feedback-Pult"]
        self.m.close_aux_output("Feedback-Pult")
        self.assertEqual(self.m.aux_output_names(), [])
        self.assertEqual(aux.geschlossen, 1)

    def test_ohne_rtmidi_ehrliches_false(self):
        """WinMM ist der Windows-ARM-Notweg ohne python-rtmidi. Dort gibt es
        bewusst keinen Zweit-Handle — lieber False als ein ungetesteter Pfad."""
        mm._USE_WINMM = True
        self.assertFalse(self.m.send_message_to("Feedback-Pult", [0x90, 1, 1]))


if __name__ == "__main__":
    unittest.main()
