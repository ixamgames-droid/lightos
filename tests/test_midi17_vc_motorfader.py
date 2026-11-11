"""MIDI-17: VC-Fader fuehrt den Motor eines Mackie-/X-Touch-Faders nach.

Bisher fuhr LightOS nur Motorfader nach, die in der MIDI-Ansicht an einen
Executor-Fader oder den Grand Master gebunden waren (MIDI-14/15). Ein VC-Fader
mit Pitchbend-Bindung steuerte zwar, der Motor blieb aber stehen: nach einem
Seitenwechsel oder einer Mausbewegung stand der Pult-Fader woanders als der
VC-Wert. Abgesichert (ohne Pult, mit gestellter Uhr):

* ``MotorFader``: Hand vor Motor mit Nachtrag, Echo-Fenster und Nachlauf,
  Touch-Sperre mit sofortigem Nachtrag beim Loslassen und Ablauf nach 10 s;
* VC-Fader: Maus -> Motor faehrt, Pult-Eingabe -> kein Echo zurueck, aber
  Nachtrag der eigenen Stellung; Bericht der Motorfahrt wird nicht
  ausgefuehrt; Beruehrungs-Note sperrt; nur mit Haken, Pitchbend und festem
  Kanal; Speichern/Laden nur wenn an.
"""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication             # noqa: E402

import src.core.midi.midi_manager as mgr                # noqa: E402
from src.core.midi.midi_mapper import (                 # noqa: E402
    MOTOR_BERUEHRT_MAX_S, MOTOR_ECHO_FENSTER_S, MOTOR_HAND_RUHE_S,
    MOTOR_NACHLAUF_S,
)
from src.core.midi.motor_fader import MotorFader        # noqa: E402
from src.ui.virtualconsole.vc_slider import SliderMode, VCSlider    # noqa: E402

_app = QApplication.instance() or QApplication([])


class _Uhr:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def _pb(kanal: int, wert14: int, port: str = "X-Touch"):
    return mgr._decode([0xE0 | (kanal - 1), wert14 & 0x7F, (wert14 >> 7) & 0x7F], port)


def _note(kanal: int, nummer: int, velocity: int, port: str = "X-Touch"):
    return mgr._decode([0x90 | (kanal - 1), nummer, velocity], port)


class MotorFaderTest(unittest.TestCase):

    def setUp(self):
        self.uhr = _Uhr()
        self.gesendet: list[int] = []
        self.m = MotorFader(lambda w: self.gesendet.append(w) or True, uhr=self.uhr)

    def test_melden_sendet_und_gleiches_nicht_doppelt(self):
        self.assertTrue(self.m.melden(8000))
        self.assertFalse(self.m.melden(8000))
        self.assertEqual(self.gesendet, [8000])
        self.assertTrue(self.m.melden(8000, erzwingen=True))
        self.assertEqual(self.gesendet, [8000, 8000])

    def test_hand_vor_motor_und_nachtrag(self):
        self.assertFalse(self.m.eingang(3000))       # Hand
        self.assertFalse(self.m.melden(3000))        # gemerkt, nicht gesendet
        self.assertTrue(self.m.wartet)
        self.uhr.t += MOTOR_HAND_RUHE_S / 2
        self.assertFalse(self.m.nachtrag())
        self.uhr.t += MOTOR_HAND_RUHE_S
        self.assertTrue(self.m.nachtrag())
        self.assertEqual(self.gesendet, [3000])
        self.assertFalse(self.m.wartet)

    def test_echo_fenster(self):
        self.m.melden(12000)
        self.uhr.t += MOTOR_ECHO_FENSTER_S / 2
        self.assertTrue(self.m.eingang(5000), "Zwischenstellung der Motorfahrt")

    def test_nachlauf_nah_am_ziel_ist_echo_weit_weg_ist_hand(self):
        self.m.melden(12000)
        self.uhr.t += (MOTOR_ECHO_FENSTER_S + MOTOR_NACHLAUF_S) / 2
        self.assertTrue(self.m.eingang(12100), "Motor schwingt ein")
        self.assertFalse(self.m.eingang(2000), "so weit weg ist es die Hand")
        self.uhr.t += MOTOR_NACHLAUF_S
        self.assertFalse(self.m.eingang(12000), "nach dem Nachlauf ist alles Hand")

    def test_touch_sperre_und_loslassen_traegt_sofort_nach(self):
        self.m.beruehrung(True)
        self.assertFalse(self.m.melden(9000))
        self.uhr.t += 5.0
        self.assertFalse(self.m.nachtrag(), "beruehrt: nichts an den Motor")
        self.assertTrue(self.m.beruehrung(False))
        self.assertEqual(self.gesendet, [9000])

    def test_mit_sensor_ist_im_nachlauf_alles_echo(self):
        self.m.beruehrung(True)
        self.m.beruehrung(False)
        self.m.melden(4000)
        self.uhr.t += (MOTOR_ECHO_FENSTER_S + MOTOR_NACHLAUF_S) / 2
        self.assertTrue(self.m.eingang(15000), "ohne Beruehrung keine Hand")

    def test_verlorenes_loslassen_loest_nach_10_s(self):
        self.m.beruehrung(True)
        self.m.melden(7000)
        self.uhr.t += MOTOR_BERUEHRT_MAX_S + 0.1
        self.assertTrue(self.m.nachtrag())
        self.assertEqual(self.gesendet, [7000])

    def test_senden_fehler_bricht_nicht(self):
        m = MotorFader(lambda w: 1 / 0, uhr=self.uhr)
        self.assertFalse(m.melden(100))


class _FakeMM:
    def __init__(self):
        self.pb: list[tuple[int, int]] = []

    def send_pitchbend(self, kanal, wert):
        self.pb.append((kanal, wert))
        return True


class VcMotorfaderTest(unittest.TestCase):

    def setUp(self):
        VCSlider.soft_takeover = False
        self.addCleanup(setattr, VCSlider, "soft_takeover", False)
        self.mm = _FakeMM()
        alt = mgr.get_midi_manager
        mgr.get_midi_manager = lambda: self.mm
        self.addCleanup(setattr, mgr, "get_midi_manager", alt)
        self.uhr = _Uhr()
        self.s = VCSlider("F")
        self.s.mode = SliderMode.SPEED          # harmloser Modus
        self.s._motor._uhr = self.uhr
        self.s.apply_midi_binding("pitchbend", 2, 0)
        self.s.midi_motor = True

    def test_maus_faehrt_motor(self):
        self.s.value = 255
        self.assertEqual(self.mm.pb, [(2, 16383)])
        self.uhr.t += 2
        self.s.value = 0
        self.assertEqual(self.mm.pb[-1], (2, 0))

    def test_ohne_haken_oder_ohne_festen_kanal_kein_motor(self):
        self.s.midi_motor = False
        self.s.value = 200
        self.s.midi_motor = True
        self.s.apply_midi_binding("pitchbend", 0, 0)      # „Alle“
        self.s.value = 100
        self.s.apply_midi_binding("cc", 2, 7)
        self.s.value = 50
        self.assertEqual(self.mm.pb, [])

    def test_pult_eingabe_kein_echo_aber_nachtrag(self):
        self.assertTrue(self.s.handle_midi(_pb(2, 8192)))
        self.assertEqual(self.s.value, 128)
        self.assertEqual(self.mm.pb, [], "nicht gegen die Hand fahren")
        self.uhr.t += MOTOR_HAND_RUHE_S + 0.05
        self.s._motor_nachtrag()
        self.assertEqual(self.mm.pb, [(2, round(128 / 255 * 16383))])

    def test_bericht_der_motorfahrt_wird_nicht_ausgefuehrt(self):
        self.s.value = 255
        self.uhr.t += MOTOR_ECHO_FENSTER_S / 2
        self.assertTrue(self.s.handle_midi(_pb(2, 4000)))
        self.assertEqual(self.s.value, 255)

    def test_beruehrung_sperrt_bis_loslassen(self):
        self.s.handle_midi(_note(1, 105, 127))           # Fader 2 = Note 105
        self.s.value = 10
        self.assertEqual(self.mm.pb, [])
        self.s.handle_midi(_note(1, 105, 0))
        self.assertEqual(self.mm.pb, [(2, round(10 / 255 * 16383))])

    def test_andere_beruehrungs_note_sperrt_nicht(self):
        self.s.handle_midi(_note(1, 104, 127))           # Fader 1
        self.s.value = 10
        self.assertEqual(len(self.mm.pb), 1)

    def test_seitenwechsel_faehrt_auch_gleichen_wert(self):
        self.s.value = 100
        self.uhr.t += 2
        self.s.arm_pickup()
        self.assertEqual(len(self.mm.pb), 2)

    def test_speichern_laden(self):
        d = self.s.to_dict()
        self.assertTrue(d.get("midi_motor"))
        neu = VCSlider("G")
        neu.apply_dict(d)
        self.assertTrue(neu.midi_motor)
        self.s.midi_motor = False
        self.assertNotIn("midi_motor", self.s.to_dict())


if __name__ == "__main__":
    unittest.main()
