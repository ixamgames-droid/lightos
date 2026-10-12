"""MIDI-15: Touch-Sperre fuer Motorfader.

MIDI-14 fuehrt Motorfader nach und laesst der Hand den Vortritt — erkennt sie
aber nur daran, dass sich der Fader BEWEGT. Zwei Luecken blieben:

* Wer einen Fader nur festhaelt (ohne ihn zu bewegen), gegen den arbeitete der
  Motor, sobald sich der Wert anderswo aenderte.
* Bewegte die Software den Wert laufend (Ueberblendung), galt alles, was vom
  Fader kam, als Bericht der Motorfahrt — die Hand kam nicht durch.

Mackie-Pulte melden die Beruehrung selbst: Note 104..112 auf Kanal 1 fuer die
Fader 1..9, Anschlag > 0 = beruehrt, 0 oder Note-Off = losgelassen. Solange
beruehrt ist, geht nichts an den Motor, und was vom Fader kommt, ist die Hand.

Ohne Geraet: MIDI-Manager und Uhr sind Attrappen (wie in MIDI-14).
"""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import src.core.midi.midi_manager as mgr                # noqa: E402
import src.core.midi.midi_mapper as mm                  # noqa: E402
from test_midi14_motorfader_rueckmeldung import _Basis, _pb    # noqa: E402


def _note(kanal: int, nummer: int, anschlag: int, port: str = "X-Touch"):
    return mgr._decode([0x90 | (kanal - 1), nummer, anschlag], port)


def _note_aus(kanal: int, nummer: int, port: str = "X-Touch"):
    return mgr._decode([0x80 | (kanal - 1), nummer, 0], port)


class BelegungTest(unittest.TestCase):

    def test_mackie_noten(self):
        self.assertEqual([mm.mackie_touch_note(k) for k in (1, 2, 8, 9)],
                         [104, 105, 111, 112])
        self.assertIsNone(mm.mackie_touch_note(10))
        self.assertIsNone(mm.mackie_touch_note(0))

    def test_rueckmeldung_traegt_die_note(self):
        m = mm.MidiMapping(name="F", msg_type="pitchbend", channel=3, data1=0,
                           action=mm.ACTION_EXECUTOR_FADER, param="1")
        self.assertEqual(mm.motor_rueckmeldung(m).touch_note, 106)
        self.assertIsNone(mm.motor_rueckmeldung(m, touch=False).touch_note)
        m.channel = 12
        self.assertIsNone(mm.motor_rueckmeldung(m).touch_note)

    def test_speichern_und_laden(self):
        m = mm.MidiMapping(name="F", msg_type="pitchbend", channel=3, data1=0,
                           action=mm.ACTION_EXECUTOR_FADER, param="1")
        m.midi_out = mm.motor_rueckmeldung(m, "X-Touch")
        neu = mm.MidiMapping.from_config_dict(m.to_config_dict())
        self.assertEqual(neu.midi_out.touch_note, 106)

    def test_rueckmeldung_ohne_note_bleibt_zeichen_fuer_zeichen(self):
        """Gespeicherte LED-Rueckmeldungen bekommen kein neues Feld."""
        fb = mm.MidiOutFeedback(trigger_id=5)
        self.assertNotIn("touch_note", fb.to_dict())
        self.assertEqual(sorted(fb.to_dict()), [
            "aux_channel", "brightness", "channel", "device", "message_type",
            "state_off", "state_on", "trigger_id"])
        self.assertIsNone(mm.MidiOutFeedback.from_dict(fb.to_dict()).touch_note)


class BeruehrtTest(_Basis):

    def _beruehren(self, kanal=1, port="X-Touch"):
        self.mapper._on_midi(_note(1, 103 + kanal, 127, port))

    def _loslassen(self, kanal=1, port="X-Touch"):
        self.mapper._on_midi(_note(1, 103 + kanal, 0, port))

    def test_festgehaltener_fader_wird_nicht_gefahren(self):
        """Die Luecke aus MIDI-14: beruehrt, aber nicht bewegt."""
        self._fader()
        self._beruehren()
        self.ex.fader_value = 0.8                       # jemand anderes dreht
        for _ in range(10):
            self._spaeter(0.1)
            self._takt()
        self.assertEqual(self.midi.pitch, [], "der Motor arbeitete gegen die Hand")

    def test_loslassen_traegt_sofort_nach(self):
        self._fader()
        self._beruehren()
        self.ex.fader_value = 0.8
        self._spaeter(0.1)
        self._takt()
        self._loslassen()
        self._takt(abfragen=False)                      # ohne Wartezeit
        self.assertEqual(self.midi.pitch, [("X-Touch", 1, round(0.8 * 16383))])

    def test_loslassen_bestaetigt_auch_die_eigene_stellung(self):
        """Mackie: nach dem Loslassen faehrt der Fader auf den zuletzt
        gesendeten Wert — also muss die Stellung zurueck, die die Hand
        eingestellt hat, auch wenn LightOS denselben Wert schon einmal sandte."""
        self._fader()
        self.ex.fader_value = 6000 / 16383
        self._takt()
        self.assertEqual(self.midi.pitch[-1][2], 6000)
        self.midi.pitch.clear()
        self._spaeter(1.0)
        self._beruehren()
        self.mapper._on_midi(_pb(1, 9000))
        self.mapper._on_midi(_pb(1, 6000))              # zurueck auf den alten Wert
        self._loslassen()
        self._takt()
        self.assertEqual(self.midi.pitch, [("X-Touch", 1, 6000)])

    def test_hand_kommt_durch_eine_laufende_fahrt(self):
        """Die zweite Luecke aus MIDI-14: die Software bewegt den Wert
        laufend, jede Sendung erneuert das Echo-Fenster."""
        self._fader()
        for schritt in range(1, 4):
            self.ex.fader_value = schritt * 0.1
            self._spaeter(0.1)
            self._takt()
        self.assertEqual(len(self.midi.pitch), 3)
        self._beruehren()
        self.mapper._on_midi(_pb(1, 12000))             # mitten im Echo-Fenster
        self.assertAlmostEqual(self.ex.fader_value, 12000 / 16383,
                               msg="die beruehrte Hand wurde als Echo verworfen")

    def test_ohne_beruehrung_bleibt_das_echo_fenster(self):
        self._fader()
        self.ex.fader_value = 1.0
        self._takt()
        self.mapper._on_midi(_pb(1, 5000))              # Bericht der Motorfahrt
        self.assertEqual(self.ex.fader_value, 1.0)

    def test_note_off_laesst_auch_los(self):
        self._fader()
        self._beruehren()
        self.ex.fader_value = 0.5
        self._takt()
        self.mapper._on_midi(_note_aus(1, 104))
        self._takt(abfragen=False)
        self.assertEqual(len(self.midi.pitch), 1)

    def test_nur_der_beruehrte_fader_steht_still(self):
        self._fader(kanal=1, param="1")
        self._fader(kanal=2, param="2")
        self._beruehren(kanal=1)
        self.ex.fader_value = 0.4
        self.zustand.playback_engine.executors[1].fader_value = 0.9
        self._spaeter(0.1)
        self._takt()
        self.assertEqual([p[1] for p in self.midi.pitch], [2])

    def test_note_eines_anderen_pults_zaehlt_nicht(self):
        m = self._fader()
        m.midi_in.device = "X-Touch"
        self.mapper._on_midi(_note(1, 104, 127, port="Anderes Pult"))
        self.assertNotIn(m.mapping_id, self.mapper._motor_beruehrt)
        self.mapper._on_midi(_note(1, 104, 127, port="X-Touch"))
        self.assertIn(m.mapping_id, self.mapper._motor_beruehrt)

    def test_note_auf_anderem_kanal_oder_mit_anderer_nummer_zaehlt_nicht(self):
        m = self._fader()
        self.mapper._on_midi(_note(2, 104, 127))        # Kanal 2
        self.mapper._on_midi(_note(1, 105, 127))        # Fader 2
        self.assertNotIn(m.mapping_id, self.mapper._motor_beruehrt)

    def test_fader_ohne_beruehrungs_note_wie_in_midi14(self):
        m = self._fader()
        m.midi_out.touch_note = None
        self.mapper._on_midi(_note(1, 104, 127))
        self.assertNotIn(m.mapping_id, self.mapper._motor_beruehrt)
        self.ex.fader_value = 0.5
        self._takt()
        self.assertEqual(len(self.midi.pitch), 1)

    def test_die_note_laeuft_weiter_durch_die_mappings(self):
        """Wer die Note 104 selbst gebunden hat, bekommt sie weiterhin."""
        self._fader()
        self.mapper.add_mapping(mm.MidiMapping(
            name="Taste", msg_type="note_on", channel=1, data1=104,
            action=mm.ACTION_EXECUTOR_FLASH, param="2", button_mode=mm.BUTTON_FLASH))
        self._beruehren()
        self.assertTrue(self.zustand.playback_engine.executors[1]._flash_active)

    def test_beruehrung_wird_auch_waehrend_des_lernens_gemerkt(self):
        m = self._fader()
        self.mapper.start_learn(lambda _msg: None, pitchbend=True)
        self._beruehren()
        self.assertIn(m.mapping_id, self.mapper._motor_beruehrt)
        self.mapper.stop_learn()

    def test_entfernen_vergisst_die_beruehrung(self):
        m = self._fader()
        self._beruehren()
        self.mapper.remove_mapping(0)
        self.assertNotIn(m.mapping_id, self.mapper._motor_beruehrt)

    def test_ziel_ohne_lesbaren_stand_nur_anfassen_sendet_nichts(self):
        """Programmer-Wert: LightOS kennt den Stand nicht. Anfassen und
        Loslassen ohne Bewegung darf den Fader nicht auf 0 fahren."""
        self._fader(action=mm.ACTION_PROGRAMMER_VAL, param="intensity")
        self._beruehren()
        self._spaeter(0.2)
        self._loslassen()
        for _ in range(5):
            self._spaeter(0.1)
            self._takt()
        self.assertEqual(self.midi.pitch, [])

    def test_ziel_ohne_lesbaren_stand_bekommt_die_eigene_stellung(self):
        self._fader(action=mm.ACTION_PROGRAMMER_VAL, param="intensity")
        self._beruehren()
        self.mapper._on_midi(_pb(1, 11000))
        self._loslassen()
        for _ in range(5):
            self._spaeter(0.1)
            self._takt()
        self.assertEqual({w for _g, _k, w in self.midi.pitch}, {11000},
                         "nie eine geratene Stellung (0)")

    def test_loslassen_ohne_vorherige_beruehrung_sendet_nichts(self):
        self._fader()
        self._loslassen()
        self._takt(abfragen=False)
        self.assertEqual(self.midi.pitch, [])


class AnsichtTest(unittest.TestCase):

    def test_die_frage_nennt_die_beruehrungs_note(self):
        from src.ui.views.midi_view import MidiView
        m = mm.MidiMapping(name="F", msg_type="pitchbend", channel=5, data1=0,
                           action=mm.ACTION_EXECUTOR_FADER, param="1")
        self.assertIn("Note 108 auf Kanal 1", MidiView._touch_satz(m))
        m.channel = 12
        self.assertIn("keinen Berührungssensor", MidiView._touch_satz(m))


if __name__ == "__main__":
    unittest.main()
