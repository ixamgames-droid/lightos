"""MIDI-14: Motorfader nachfuehren — ohne das eigene Echo als Eingabe.

Seit MIDI-10 lassen sich die Fader von Mackie-Control- und X-Touch-Pulten
binden (Pitchbend, je Fader ein Kanal, 14 Bit). Das Pult fuhr sie aber nicht
nach: aenderte sich der Wert anderswo (Bildschirm, Seitenwechsel, zweites
Pult), stand der Fader falsch, und nach dem Loslassen fuhren Mackie-Pulte ihn
auf den zuletzt EMPFANGENEN Wert zurueck — also dorthin, wo LightOS nie etwas
hingeschickt hatte.

Jetzt sendet der Mapper die Stellung als Pitchbend zurueck. Drei Regeln, die
dieser Test festhaelt:

* **Die Hand hat Vorrang.** Solange vom Fader Werte kommen und kurz danach,
  geht nichts an seinen Motor; danach wird die Stellung einmal nachgetragen.
* **Das Echo ist keine Eingabe.** Was unmittelbar nach einer eigenen Sendung
  vom selben Fader zurueckkommt, ist der Bericht ueber die Motorfahrt.
* **Nichts raten.** Nachgefuehrt wird aus dem echten Stand des Ziels; bei
  Zielen ohne lesbaren Stand nur das, was der Fader selbst gemeldet hat.

Ohne Geraet: MIDI-Manager und Uhr sind Attrappen, die Rueckmelde-Schleife
wird von Hand getaktet (bis auf einen Lauf mit der echten Schleife).
"""
from __future__ import annotations

import os
import time
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import src.core.midi.midi_manager as mgr                # noqa: E402
import src.core.midi.midi_mapper as mm                  # noqa: E402
from test_midi_mapper import _FakeMidiManager, _FakeState     # noqa: E402


def _pb(kanal: int, wert14: int, port: str = "X-Touch"):
    return mgr._decode([0xE0 | (kanal - 1), wert14 & 0x7F, (wert14 >> 7) & 0x7F], port)


class _Midi(_FakeMidiManager):
    """Dazu: Pitchbend senden, gemeinsam und an einen bestimmten Ausgang."""

    def __init__(self):
        super().__init__()
        self.pitch: list[tuple] = []

    def send_pitchbend(self, channel, wert):
        self.pitch.append(("", channel, wert))
        return True

    def send_pitchbend_to(self, port, channel, wert):
        self.pitch.append((port, channel, wert))
        return True


class _Basis(unittest.TestCase):
    """Mapper mit stehender Schleife und einer Uhr, die der Test stellt."""

    def setUp(self):
        self.midi = _Midi()
        alt = mm.get_midi_manager
        mm.get_midi_manager = lambda: self.midi
        self.addCleanup(setattr, mm, "get_midi_manager", alt)
        self.zustand = _FakeState()
        self.mapper = mm.MidiMapper(self.zustand)
        self.addCleanup(self.mapper.close)
        # Die echte Schleife anhalten: jeder Schritt wird hier von Hand getan.
        self.mapper._feedback_running = False
        self.mapper._feedback_thread.join(2.0)
        self.zeit = [100.0]
        self.mapper._uhr = lambda: self.zeit[0]
        self.ex = self.zustand.playback_engine.executors[0]

    def _fader(self, kanal=1, action=mm.ACTION_EXECUTOR_FADER, param="1",
               geraet="X-Touch", **kw):
        m = mm.MidiMapping(name=f"F{kanal}", msg_type="pitchbend", channel=kanal,
                           data1=0, action=action, param=param, **kw)
        m.midi_out = mm.motor_rueckmeldung(m, geraet)
        self.mapper.add_mapping(m)
        self._takt()                    # das Pult bekommt die Anfangsstellung
        self.midi.pitch.clear()
        self._spaeter(1.0)              # ... und das Echo-Fenster dazu ist vorbei
        return m

    def _takt(self, abfragen=True):
        """Ein Durchgang der Rueckmelde-Schleife."""
        if abfragen:
            self.mapper._poll_feedback_states()
        self.mapper._motor_nachtrag(self.midi)
        while not self.mapper._feedback_queue.empty():
            mapping, value = self.mapper._feedback_queue.get_nowait()
            if mm.ist_motorfader(mapping):
                self.mapper._motor_melden(self.midi, mapping, value)
        self.mapper._motor_nachtrag(self.midi)

    def _spaeter(self, sekunden):
        self.zeit[0] += sekunden


# ══════════════════════════════════════════════════════════════════════════════
# Senden
# ══════════════════════════════════════════════════════════════════════════════

class PitchbendSendenTest(unittest.TestCase):

    def test_bytes_sind_das_gegenstueck_zum_lesen(self):
        for kanal, wert in ((1, 0), (3, 8192), (9, 16383), (16, 5000)):
            roh = mgr.pitchbend_bytes(kanal, wert)
            msg = mgr._decode(roh, "x")
            self.assertEqual((msg.msg_type, msg.channel, mgr.wert14(msg)),
                             ("pitchbend", kanal, wert))

    def test_werte_werden_begrenzt(self):
        self.assertEqual(mgr.pitchbend_bytes(1, -5), [0xE0, 0, 0])
        self.assertEqual(mgr.pitchbend_bytes(1, 99999), [0xE0, 0x7F, 0x7F])

    def test_manager_sendet_ueber_die_vorhandenen_wege(self):
        gesendet = []
        m = SimpleNamespace(send_message=lambda b: gesendet.append(("", list(b))) or True,
                            send_message_to=lambda p, b: gesendet.append((p, list(b))) or True)
        self.assertTrue(mgr.MidiManager.send_pitchbend(m, 2, 8192))
        self.assertTrue(mgr.MidiManager.send_pitchbend_to(m, "X-Touch", 2, 8192))
        self.assertEqual(gesendet, [("", [0xE1, 0, 64]), ("X-Touch", [0xE1, 0, 64])])


# ══════════════════════════════════════════════════════════════════════════════
# Nachfuehren
# ══════════════════════════════════════════════════════════════════════════════

class NachfuehrenTest(_Basis):

    def test_aenderung_am_bildschirm_faehrt_den_fader(self):
        self._fader(kanal=3)
        self.ex.fader_value = 0.5
        self._takt()
        self.assertEqual(self.midi.pitch, [("X-Touch", 3, round(0.5 * 16383))])

    def test_ohne_aenderung_wird_nichts_gesendet(self):
        self._fader()
        for _ in range(5):
            self._spaeter(0.1)
            self._takt()
        self.assertEqual(self.midi.pitch, [])

    def test_volle_aufloesung(self):
        self._fader()
        self.ex.fader_value = 5000 / 16383
        self._takt()
        self.assertEqual(self.midi.pitch[-1][2], 5000)

    def test_ohne_geraet_ueber_den_gemeinsamen_ausgang(self):
        self._fader(geraet="")
        self.ex.fader_value = 1.0
        self._takt()
        self.assertEqual(self.midi.pitch, [("", 1, 16383)])

    def test_grand_master(self):
        self._fader(kanal=9, action=mm.ACTION_GRAND_MASTER, param="")
        self.zustand.output_manager.set_grand_master(0.25)
        self._takt()
        self.assertEqual(self.midi.pitch[-1], ("X-Touch", 9, round(0.25 * 16383)))

    def test_bereich_wird_auf_die_faderstellung_zurueckgerechnet(self):
        """continuous_min/max: der Fader steht bei 0..1, das Ziel bei 0,2..0,6.
        Sonst fuehre der Motor nach jeder Bewegung an eine andere Stelle."""
        self._fader(continuous_min=0.2, continuous_max=0.6)
        self.ex.fader_value = 0.4                       # Mitte des Bereichs
        self._takt()
        self.assertEqual(self.midi.pitch[-1][2], round(0.5 * 16383))

    def test_feine_schritte_einer_ueberblendung(self):
        self._fader()
        for schritt in range(1, 6):
            self.ex.fader_value = schritt * 0.004       # 0,4 % je Takt
            self._spaeter(0.1)
            self._takt()
        self.assertEqual(len(self.midi.pitch), 5, "die 1-%-Schwelle der LEDs waere zu grob")

    def test_ziel_ohne_lesbaren_stand_wird_nicht_aus_dem_nichts_gefahren(self):
        """Programmer-Wert: der Stand laesst sich nicht zuruecklesen. Die
        Abfrage lieferte „aus“ — der Fader fuehre nach jeder Bewegung auf 0."""
        self._fader(action=mm.ACTION_PROGRAMMER_VAL, param="intensity")
        self.mapper._on_midi(_pb(1, 12000))
        for _ in range(8):
            self._spaeter(0.1)
            self._takt()
        werte = {w for _g, _k, w in self.midi.pitch}
        self.assertEqual(werte, {12000}, "nur die eigene Stellung kommt zurueck")

    def test_pitchbend_fader_ohne_motor_rueckmeldung_sendet_nichts(self):
        m = mm.MidiMapping(name="F", msg_type="pitchbend", channel=1, data1=0,
                           action=mm.ACTION_EXECUTOR_FADER, param="1")
        self.mapper.add_mapping(m)
        self.ex.fader_value = 0.7
        self._takt()
        self.assertEqual(self.midi.pitch, [])
        self.assertFalse(mm.ist_motorfader(m))

    def test_cc_fader_mit_pitchbend_rueckmeldung_ist_kein_motorfader(self):
        m = mm.MidiMapping(name="C", msg_type="cc", channel=1, data1=7,
                           action=mm.ACTION_EXECUTOR_FADER, param="1",
                           midi_out=mm.MidiOutFeedback(message_type="pitchbend"))
        self.assertFalse(mm.ist_motorfader(m))


# ══════════════════════════════════════════════════════════════════════════════
# Die Hand hat Vorrang
# ══════════════════════════════════════════════════════════════════════════════

class HandTest(_Basis):

    def test_waehrend_der_bewegung_geht_nichts_an_den_motor(self):
        self._fader()
        for wert in (2000, 4000, 6000, 8000):
            self.mapper._on_midi(_pb(1, wert))
            self._spaeter(0.05)
            self._takt()
        self.assertEqual(self.midi.pitch, [], "der Motor arbeitete gegen die Hand")
        self.assertAlmostEqual(self.ex.fader_value, 8000 / 16383)

    def test_nach_der_ruhe_bekommt_das_pult_die_stellung_einmal(self):
        """Mackie-Pulte fahren nach dem Loslassen auf den zuletzt GESENDETEN
        Wert — also muss die eigene Stellung zurueck."""
        self._fader()
        self.mapper._on_midi(_pb(1, 8000))
        self._takt()
        self._spaeter(mm.MOTOR_HAND_RUHE_S + 0.01)
        self._takt()
        self.assertEqual(self.midi.pitch, [("X-Touch", 1, 8000)])
        for _ in range(4):
            self._spaeter(0.1)
            self._takt()
        self.assertEqual(len(self.midi.pitch), 1, "nur einmal")

    def test_aenderung_von_aussen_waehrend_der_hand_wartet(self):
        self._fader()
        self.mapper._on_midi(_pb(1, 8000))
        self._takt()
        self.ex.fader_value = 0.1                       # jemand anderes dreht
        self._spaeter(0.1)
        self._takt()
        self.assertEqual(self.midi.pitch, [])
        self._spaeter(mm.MOTOR_HAND_RUHE_S)
        self._takt()
        self.assertEqual(self.midi.pitch[-1][2], round(0.1 * 16383),
                         "nachgetragen wird der Stand von JETZT")

    def test_zwei_fader_stoeren_sich_nicht(self):
        a = self._fader(kanal=1, param="1")
        self._fader(kanal=2, param="2")
        self.mapper._on_midi(_pb(1, 8000))              # Hand an Fader 1
        self.zustand.playback_engine.executors[1].fader_value = 0.9
        self._spaeter(0.05)
        self._takt()
        self.assertEqual([p[1] for p in self.midi.pitch], [2])
        self.assertIn(a.mapping_id, self.mapper._motor_offen)


# ══════════════════════════════════════════════════════════════════════════════
# Das Echo ist keine Eingabe
# ══════════════════════════════════════════════════════════════════════════════

class EchoTest(_Basis):

    def test_bericht_der_motorfahrt_wird_nicht_ausgefuehrt(self):
        """Seitenwechsel: der Executor steht auf 100 %, der Fader bei 0. Das
        Pult meldet die Fahrt Stellung fuer Stellung — das darf den Executor
        nicht durch alle Zwischenwerte ziehen."""
        self._fader()
        self.ex.fader_value = 1.0
        self._takt()
        self.assertEqual(self.midi.pitch[-1][2], 16383)
        for unterwegs in (2000, 7000, 12000, 16383):
            self._spaeter(0.04)
            self.mapper._on_midi(_pb(1, unterwegs))
            self.assertEqual(self.ex.fader_value, 1.0, f"Echo {unterwegs} wurde ausgefuehrt")

    def test_das_echo_zaehlt_nicht_als_hand(self):
        self._fader()
        self.ex.fader_value = 1.0
        self._takt()
        self.mapper._on_midi(_pb(1, 9000))              # Echo
        self.ex.fader_value = 0.3                       # naechste Aenderung von aussen
        self._spaeter(0.1)
        self._takt()
        self.assertEqual(self.midi.pitch[-1][2], round(0.3 * 16383),
                         "ein Echo darf das Nachfuehren nicht anhalten")

    def test_nach_dem_fenster_ist_es_wieder_die_hand(self):
        self._fader()
        self.ex.fader_value = 1.0
        self._takt()
        self._spaeter(mm.MOTOR_ECHO_FENSTER_S + 0.01)
        self.mapper._on_midi(_pb(1, 4000))
        self.assertAlmostEqual(self.ex.fader_value, 4000 / 16383)

    def test_fader_ohne_nachfuehren_kennt_kein_echo_fenster(self):
        m = mm.MidiMapping(name="F", msg_type="pitchbend", channel=1, data1=0,
                           action=mm.ACTION_EXECUTOR_FADER, param="1")
        self.mapper.add_mapping(m)
        self.mapper._on_midi(_pb(1, 4000))
        self.mapper._on_midi(_pb(1, 9000))
        self.assertAlmostEqual(self.ex.fader_value, 9000 / 16383)

    def test_entfernen_vergisst_den_zustand(self):
        m = self._fader()
        self.mapper._on_midi(_pb(1, 4000))
        self._takt()
        self.mapper.remove_mapping(0)
        for tabelle in (self.mapper._motor_hand_ts, self.mapper._motor_send_ts,
                        self.mapper._motor_wert, self.mapper._motor_offen):
            self.assertNotIn(m.mapping_id, tabelle)


# ══════════════════════════════════════════════════════════════════════════════
# Speichern, Bestand, die echte Schleife
# ══════════════════════════════════════════════════════════════════════════════

class BestandTest(unittest.TestCase):

    def test_speichern_und_laden(self):
        m = mm.MidiMapping(name="F", msg_type="pitchbend", channel=4, data1=0,
                           action=mm.ACTION_EXECUTOR_FADER, param="2")
        m.midi_out = mm.motor_rueckmeldung(m, "X-Touch")
        neu = mm.MidiMapping.from_config_dict(m.to_config_dict())
        self.assertTrue(mm.ist_motorfader(neu))
        self.assertEqual((neu.midi_out.channel, neu.midi_out.device), (4, "X-Touch"))
        self.assertEqual(neu.midi_out.trigger_id, -1, "keine LED-Nummer fuer einen Fader")

    def test_gespeicherte_mappings_ohne_rueckmeldung_bleiben_stumm(self):
        alt = {"id": "x", "name": "F", "target": "executor_fader:1",
               "midi_in": {"device": "", "channel": 1, "trigger_id": 0,
                           "message_type": "pitchbend"},
               "button_mode": "continuous", "midi_out": None}
        self.assertFalse(mm.ist_motorfader(mm.MidiMapping.from_config_dict(alt)))


class EchteSchleifeTest(unittest.TestCase):
    """Ein Lauf mit der wirklichen Rueckmelde-Schleife und der echten Uhr."""

    def test_hand_dann_ruhe_dann_einmal_zurueck(self):
        midi = _Midi()
        alt = mm.get_midi_manager
        mm.get_midi_manager = lambda: midi
        self.addCleanup(setattr, mm, "get_midi_manager", alt)
        mapper = mm.MidiMapper(_FakeState())
        self.addCleanup(mapper.close)
        m = mm.MidiMapping(name="F", msg_type="pitchbend", channel=2, data1=0,
                           action=mm.ACTION_EXECUTOR_FADER, param="1")
        m.midi_out = mm.motor_rueckmeldung(m, "X-Touch")
        mapper.add_mapping(m)
        time.sleep(0.3)
        midi.pitch.clear()
        t0 = time.monotonic()
        while time.monotonic() - t0 < 0.3:              # die Hand bewegt
            mapper._on_midi(_pb(2, 6000))
            time.sleep(0.02)
        self.assertEqual(midi.pitch, [], "waehrend der Bewegung gesendet")
        ende = time.monotonic() + 2.0
        while time.monotonic() < ende and not midi.pitch:
            time.sleep(0.02)
        self.assertEqual(midi.pitch, [("X-Touch", 2, 6000)])


# ══════════════════════════════════════════════════════════════════════════════
# MIDI-Ansicht
# ══════════════════════════════════════════════════════════════════════════════

class AnsichtTest(unittest.TestCase):

    def _ansicht(self, mapping, antwort, ausgang="X-Touch"):
        from src.ui.views import midi_view as mv
        zeilen = []
        fragen = []
        alt = mv.QMessageBox.question

        def frage(_p, _titel, text, *a, **k):
            fragen.append(text)
            return antwort

        mv.QMessageBox.question = staticmethod(frage)
        self.addCleanup(setattr, mv.QMessageBox, "question", alt)
        ansicht = SimpleNamespace(
            _combo_out=SimpleNamespace(currentText=lambda: ausgang),
            _append_log=zeilen.append)
        mv.MidiView._motor_rueckmeldung_fragen(ansicht, mapping)
        return fragen, zeilen

    def _fader(self):
        return mm.MidiMapping(name="F", msg_type="pitchbend", channel=5, data1=0,
                              action=mm.ACTION_EXECUTOR_FADER, param="1")

    def test_einschalten(self):
        from src.ui.views import midi_view as mv
        m = self._fader()
        fragen, zeilen = self._ansicht(m, mv.QMessageBox.StandardButton.Yes)
        self.assertTrue(mm.ist_motorfader(m))
        self.assertEqual((m.midi_out.channel, m.midi_out.device), (5, "X-Touch"))
        self.assertIn("Motorfader auf Kanal 5 nachführen?", fragen[0])
        self.assertIn("Solange du den Fader bewegst", fragen[0])
        self.assertIn("wird nachgeführt", zeilen[-1])

    def test_nein_laesst_ihn_stumm(self):
        from src.ui.views import midi_view as mv
        m = self._fader()
        self._ansicht(m, mv.QMessageBox.StandardButton.No)
        self.assertIsNone(m.midi_out)

    def test_ausschalten(self):
        from src.ui.views import midi_view as mv
        m = self._fader()
        m.midi_out = mm.motor_rueckmeldung(m, "X-Touch")
        fragen, _zeilen = self._ansicht(m, mv.QMessageBox.StandardButton.Yes)
        self.assertIn("Nachführen ausschalten?", fragen[0])
        self.assertIsNone(m.midi_out)

    def test_kein_ausgang_gewaehlt_nimmt_den_gemeinsamen(self):
        from src.ui.views import midi_view as mv
        m = self._fader()
        self._ansicht(m, mv.QMessageBox.StandardButton.Yes, ausgang="(kein Ausgang)")
        self.assertEqual(m.midi_out.device, "")

    def test_feedback_knopf_fuehrt_bei_pitchbend_zur_motor_frage(self):
        from src.ui.views import midi_view as mv
        m = self._fader()
        gefragt, led = [], []
        ansicht = SimpleNamespace(
            _map_table=SimpleNamespace(
                selectedIndexes=lambda: [SimpleNamespace(row=lambda: 0)]),
            _mapper=SimpleNamespace(get_mappings=lambda: [m]),
            _motor_rueckmeldung_fragen=gefragt.append,
            _prompt_feedback_values=led.append,
            _refresh_map_table=lambda: None)
        mv.MidiView._edit_feedback_values(ansicht)
        self.assertEqual((gefragt, led), ([m], []))


if __name__ == "__main__":
    unittest.main()
