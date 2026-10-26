"""MIDI-14/15 im Zusammenspiel mit den anderen Fernsteuer-Wegen.

Seit OSC-06 (freie OSC-Zuordnungen), NET-15 (DMX-Fernsteuerung ueber
Art-Net/sACN) und WEB-12 (feste Handy-Fernbedienung) hat ein Executor-Fader
mehrere Quellen. Alle schreiben in denselben Zustand (``fader_value`` bzw.
``grand_master``) — und genau den liest die Motorfader-Rueckmeldung zurueck.
Dieser Test haelt fest, dass das ohne eigene Verdrahtung so bleibt:

* Bewegt ein anderer Weg den Fader, faehrt der Motor nach.
* Das Echo dieser Fahrt wird nicht als Eingabe ausgefuehrt — der Executor
  bleibt dort, wo der andere Weg ihn hingestellt hat.
* Liegt die Hand auf dem Fader (MIDI-15), wartet der Motor; nach dem
  Loslassen wird der Stand von JETZT gesendet.

Ohne Geraet, ohne Netz: die Wege werden ueber ihre Anwende-Funktionen
angesprochen, MIDI-Manager und Uhr sind Attrappen.
"""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import src.core.midi.midi_mapper as mm                  # noqa: E402
from src.core.dmx import fernsteuerung as net15         # noqa: E402
from src.core.osc import osc_zuordnung as osc06         # noqa: E402
from test_midi14_motorfader_rueckmeldung import _Basis, _pb     # noqa: E402
from test_midi15_touch_sperre import _note              # noqa: E402


def _osc_fader(state, slot: int, wert: float) -> None:
    assert osc06.OscZuordnung._anwenden(
        state, osc06.Aktion(ziel=osc06.ZIEL_FADER, nummer=slot, wert=wert))


def _osc_gm(state, wert: float) -> None:
    assert osc06.OscZuordnung._anwenden(
        state, osc06.Aktion(ziel=osc06.ZIEL_GM, wert=wert))


def _net15_fader(state, slot: int, wert: float) -> None:
    assert net15.DmxFernsteuerung._anwenden(
        state, net15.Aktion(ziel=net15.ZIEL_FADER, executor=slot, wert=wert))


def _net15_gm(state, wert: float) -> None:
    assert net15.DmxFernsteuerung._anwenden(
        state, net15.Aktion(ziel=net15.ZIEL_GM, executor=0, wert=wert))


class _Wege(_Basis):

    def _web12_fader(self, slot: int, wert: float) -> None:
        try:
            import src.web.app as web
        except Exception as e:                  # pragma: no cover
            self.skipTest(f"Web-Teil nicht ladbar: {e}")
        alt_state, alt_laser = web._get_state, web._laser_gesperrt
        web._get_state = lambda: self.zustand
        web._laser_gesperrt = lambda: False
        try:
            antwort, code = web.fest_fader(slot, {"level": wert})
        finally:
            web._get_state, web._laser_gesperrt = alt_state, alt_laser
        self.assertEqual((antwort, code), ({"ok": True}, 200))

    def _web12_gm(self, wert: float) -> None:
        from src.web import fern_pult
        self.addCleanup(fern_pult.vergessen)
        self.assertTrue(fern_pult.gm_setzen(self.zustand, wert, "", True)["ok"])


class MotorFaehrtNachTest(_Wege):
    """Jeder Weg bewegt den Fader — der Motor folgt."""

    def _pruefe(self, setzen, wert):
        self._fader()
        self._takt()                                    # Anfangsstand
        self.midi.pitch.clear()
        setzen(wert)
        self._spaeter(0.1)
        self._takt()
        self.assertEqual(self.midi.pitch, [("X-Touch", 1, round(wert * 16383))])

    def test_osc06(self):
        self._pruefe(lambda w: _osc_fader(self.zustand, 1, w), 0.6)

    def test_net15(self):
        self._pruefe(lambda w: _net15_fader(self.zustand, 1, w), 0.4)

    def test_web12(self):
        self._pruefe(lambda w: self._web12_fader(1, w), 0.75)

    def _pruefe_gm(self, setzen, wert):
        self._fader(action=mm.ACTION_GRAND_MASTER, param="")
        self._takt()
        self.midi.pitch.clear()
        setzen(wert)
        self._spaeter(0.1)
        self._takt()
        self.assertEqual(self.midi.pitch, [("X-Touch", 1, round(wert * 16383))])

    def test_grand_master_osc06(self):
        self._pruefe_gm(lambda w: _osc_gm(self.zustand, w), 0.3)

    def test_grand_master_net15(self):
        self._pruefe_gm(lambda w: _net15_gm(self.zustand, w), 0.2)

    def test_grand_master_web12(self):
        self._pruefe_gm(self._web12_gm, 0.5)


class EchoNachFremdemWegTest(_Wege):

    def test_bericht_der_fahrt_ueberschreibt_den_anderen_weg_nicht(self):
        """OSC stellt 100 %, der Motor faehrt von 0 hoch und meldet unterwegs
        Zwischenstellungen — der Executor bleibt bei 100 %."""
        self._fader()
        self._takt()
        _osc_fader(self.zustand, 1, 1.0)
        self._spaeter(0.1)
        self._takt()
        self.assertEqual(self.midi.pitch[-1][2], 16383)
        for unterwegs in (3000, 9000, 15000):
            self._spaeter(0.04)
            self.mapper._on_midi(_pb(1, unterwegs))
            self.assertEqual(self.ex.fader_value, 1.0)

    def test_hand_nach_dem_fenster_gewinnt_wieder(self):
        """Letzter Schreiber gewinnt: nach dem Echo-Fenster ist der Fader
        wieder die Hand und setzt den Executor, auch gegen NET-15."""
        self._fader()
        _net15_fader(self.zustand, 1, 0.8)
        self._takt()
        self._spaeter(mm.MOTOR_ECHO_FENSTER_S + 0.01)
        self.mapper._on_midi(_pb(1, 4000))
        self.assertAlmostEqual(self.ex.fader_value, 4000 / 16383)


class NachlaufTest(_Wege):
    """Gegenpruefung: ein Motor, der seine Endstellung erst NACH dem Echo-
    Fenster meldet, darf den fremd gesetzten Wert nicht ueberschreiben — und
    zwei Motoren auf demselben Ziel duerfen sich nicht aufschaukeln."""

    def test_spaeter_bericht_ueberschreibt_osc_nicht(self):
        self._fader()
        self._takt()
        self.midi.pitch.clear()
        _osc_fader(self.zustand, 1, 1.0)
        self._takt()
        self.assertEqual(self.midi.pitch, [("X-Touch", 1, 16383)])
        for unterwegs in (6000, 12000, 16000):          # 0,1 / 0,2 / 0,3 s
            self._spaeter(0.1)
            self.mapper._on_midi(_pb(1, unterwegs))
            self._takt()
        self.assertEqual(self.ex.fader_value, 1.0)
        self._spaeter(1.0)
        self._takt()
        self.assertEqual(self.midi.pitch, [("X-Touch", 1, 16383)],
                         "der Motor wurde auf den Nachlauf zurueckgefahren")

    def test_mit_sensor_zaehlt_ohne_beruehrung_auch_ein_weiter_weg(self):
        """Hat sich der Beruehrungssensor einmal gemeldet, ist ein Bericht
        ohne Beruehrung im Nachlauf nie die Hand — auch weit vom Ziel."""
        self._fader()
        self.mapper._on_midi(_note(1, 104, 127))
        self.mapper._on_midi(_note(1, 104, 0))
        self._spaeter(1.0)
        self._takt()
        self.midi.pitch.clear()
        _net15_fader(self.zustand, 1, 1.0)
        self._takt()
        self._spaeter(0.6)
        self.mapper._on_midi(_pb(1, 9000))              # langsamer Motor
        self.assertEqual(self.ex.fader_value, 1.0)

    def test_nach_dem_nachlauf_zaehlt_auch_ein_feiner_schritt(self):
        self._fader()
        _osc_fader(self.zustand, 1, 0.5)
        self._takt()
        self._spaeter(mm.MOTOR_NACHLAUF_S + 0.01)
        self.mapper._on_midi(_pb(1, round(0.51 * 16383)))
        self.assertAlmostEqual(self.ex.fader_value, round(0.51 * 16383) / 16383)

    def test_zwei_motoren_auf_einem_executor_schaukeln_nicht(self):
        self._fader(kanal=1, geraet="Pult A")
        self._fader(kanal=2, geraet="Pult B")
        self._takt()
        self.midi.pitch.clear()
        _osc_fader(self.zustand, 1, 8000 / 16383)
        self._takt()
        self.assertEqual(sorted(self.midi.pitch),
                         [("Pult A", 1, 8000), ("Pult B", 2, 8000)])
        verlauf = []
        for _ in range(20):
            # jeder Motor meldet 0,3 s nach seiner Sendung knapp daneben
            gesendet = list(self.midi.pitch)
            self.midi.pitch.clear()
            verlauf += gesendet
            self._spaeter(0.3)
            for port, kanal, wert in gesendet:
                self.mapper._on_midi(_pb(kanal, wert - 20, port=port))
            self._spaeter(0.5)
            self._takt()
        self.assertEqual(sorted(verlauf), [("Pult A", 1, 8000), ("Pult B", 2, 8000)],
                         "die Motoren schaukeln sich auf")
        self.assertAlmostEqual(self.ex.fader_value, 8000 / 16383)

    def test_grand_master_mit_bereich_wird_zurueckgelesen(self):
        """Nur das Zuruecklesen rechnet durch continuous_min/max — ein
        Durchreichen des rohen GM-Werts ergaebe 4096 statt 8192."""
        self._fader(action=mm.ACTION_GRAND_MASTER, param="",
                    continuous_min=0.0, continuous_max=0.5)
        self._takt()
        self.midi.pitch.clear()
        _osc_gm(self.zustand, 0.25)
        self._spaeter(0.1)
        self._takt()
        self.assertEqual(self.midi.pitch, [("X-Touch", 1, 8192)])


class BeruehrtWaehrendFremdemWegTest(_Wege):

    def test_osc_waehrend_der_hand_wartet_bis_zum_loslassen(self):
        self._fader()
        self._takt()
        self.midi.pitch.clear()
        self.mapper._on_midi(_note(1, 104, 127))        # Hand auf Fader 1
        _osc_fader(self.zustand, 1, 0.9)
        self._spaeter(1.0)
        self._takt()
        self.assertEqual(self.midi.pitch, [], "der Motor arbeitete gegen die Hand")
        _net15_fader(self.zustand, 1, 0.25)             # noch ein Weg dazwischen
        self._spaeter(0.1)
        self._takt()
        self.assertEqual(self.midi.pitch, [])
        self.mapper._on_midi(_note(1, 104, 0))          # losgelassen
        self._takt(abfragen=False)
        self.assertEqual(self.midi.pitch, [("X-Touch", 1, round(0.25 * 16383))],
                         "nachgetragen wird der Stand von JETZT")


if __name__ == "__main__":
    unittest.main()
