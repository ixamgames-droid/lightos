"""ENG-33 — gemeinsame, ersetzbare Show-Zeit fuer Cue-Fades, Follow-Cues und Effekte.

Vorher liefen Cue-Fades auf ``perf_counter`` (QA-89) und Follow-Cues auf einem
``threading.Timer`` — wer Bild fuer Bild rendert (Aufnahme, Headless-Pruefung),
sah dadurch keine Fades und keine Follows, waehrend die Effekte im Render-Takt
(``dt``) schon liefen. Seit ENG-33 lesen alle drei ``show_zeit.jetzt()``; Tests
und Aufnahmen setzen eine manuelle Uhr ein und ruecken sie vor — ohne zu schlafen.
"""
from __future__ import annotations

import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.engine import show_zeit                       # noqa: E402
from src.core.engine.cue import Cue                         # noqa: E402
from src.core.engine.cue_stack import CueStack, FadeState   # noqa: E402


def _stack(fade=2.0, follow=None):
    s = CueStack("ENG-33")
    c1 = Cue(1.0, "Eins", values={1: {"intensity": 200}}, fade_in=fade)
    c1.fade_curve = "linear"
    c1.follow = follow
    c2 = Cue(2.0, "Zwei", values={1: {"intensity": 0}}, fade_in=0.0)
    s.cues = [c1, c2]
    return s


class TestManuelleUhr(unittest.TestCase):
    def test_fade_ueber_zwei_sekunden_ohne_schlafen(self):
        with show_zeit.manuelle_uhr() as uhr:
            fs = FadeState({1: {"intensity": 0}}, {1: {"intensity": 200}},
                           2.0, 0.0, "linear")
            self.assertEqual(fs.current_values()[1]["intensity"], 0)
            uhr.vorruecken(1.0)
            self.assertEqual(fs.current_values()[1]["intensity"], 100)
            self.assertFalse(fs.done)
            uhr.vorruecken(1.0)
            self.assertEqual(fs.current_values()[1]["intensity"], 200)
            self.assertTrue(fs.done)

    def test_cueliste_fadet_im_takt_der_uhr(self):
        with show_zeit.manuelle_uhr() as uhr:
            s = _stack(fade=2.0)
            s.go()
            uhr.vorruecken(1.0)
            self.assertEqual(s.tick()[1]["intensity"], 100)
            uhr.vorruecken(1.0)
            self.assertEqual(s.tick()[1]["intensity"], 200)
            s.stop()

    def test_follow_loest_erst_nach_follow_zeit_aus(self):
        # Follow-Zeit zaehlt ab dem GO, plus Fade-Zeit der Cue (bisheriger Kontrakt).
        with show_zeit.manuelle_uhr() as uhr:
            s = _stack(fade=1.0, follow=0.5)
            s.go()
            self.assertEqual(s.current_index, 0)
            uhr.vorruecken(1.49)
            s.tick()
            self.assertEqual(s.current_index, 0, "Follow zu frueh")
            uhr.vorruecken(0.02)
            s.tick()
            self.assertEqual(s.current_index, 1, "Follow nicht ausgeloest")
            s.stop()

    def test_follow_ohne_tick_wartet(self):
        # Eingefroren bzw. kein Render-Takt: kein Follow im Hintergrund.
        with show_zeit.manuelle_uhr() as uhr:
            s = _stack(fade=0.0, follow=0.1)
            s.go()
            uhr.vorruecken(5.0)
            self.assertEqual(s.current_index, 0)
            s.tick()
            self.assertEqual(s.current_index, 1)
            s.stop()

    def test_follow_fade_beginnt_am_faelligkeitszeitpunkt(self):
        # Spaeter Tick (Frame-Raster): der Folge-Fade ist so weit, als waere er
        # exakt zur Faelligkeit gestartet — Follow-Ketten driften nicht.
        with show_zeit.manuelle_uhr() as uhr:
            s = _stack(fade=0.0, follow=1.0)
            s.cues[1].fade_in = 2.0
            s.cues[1].fade_curve = "linear"
            s.go()
            s.tick()
            uhr.vorruecken(2.0)      # faellig bei 1.0, Tick erst bei 2.0
            out = s.tick()
            self.assertEqual(s.current_index, 1)
            self.assertEqual(out[1]["intensity"], 100)   # 200 -> 0, halb
            s.stop()

    def test_shift_clock_schiebt_auch_den_follow(self):
        with show_zeit.manuelle_uhr() as uhr:
            s = _stack(fade=0.0, follow=1.0)
            s.go()
            uhr.vorruecken(10.0)     # Freeze: 10 s ohne Tick
            s.shift_clock(10.0)
            s.tick()
            self.assertEqual(s.current_index, 0)
            uhr.vorruecken(1.01)
            s.tick()
            self.assertEqual(s.current_index, 1)
            s.stop()

    def test_stop_verwirft_den_follow(self):
        with show_zeit.manuelle_uhr() as uhr:
            s = _stack(fade=0.0, follow=0.5)
            s.go()
            s.stop()
            uhr.vorruecken(1.0)
            s.tick()
            self.assertEqual(s.current_index, -1)

    def test_go_to_auf_cue_ohne_follow_verwirft_den_alten(self):
        # Vorher (Timer wie Faelligkeit) blieb der Follow der alten Cue stehen
        # und schaltete nach einem Sprung unerwartet weiter.
        with show_zeit.manuelle_uhr() as uhr:
            s = _stack(fade=0.0, follow=0.5)
            s.cues.append(Cue(3.0, "Drei", values={1: {"intensity": 50}},
                              fade_in=0.0))
            s.go()
            s.go_to(2.0)                     # Cue 2 hat keinen Follow
            uhr.vorruecken(1.0)
            s.tick()
            self.assertEqual(s.current_index, 1)
            self.assertIsNone(s._follow_faellig)

    def test_follow_kette_driftet_nicht(self):
        # Zwei Follows hintereinander, beide Ticks spaet: die zweite Faelligkeit
        # zaehlt ab der ersten (0.3 + 0.3 = 0.6), nicht ab dem spaeten Tick (0.65).
        with show_zeit.manuelle_uhr() as uhr:
            s = CueStack("Kette")
            for i, f in enumerate((0.3, 0.3, None)):
                c = Cue(float(i + 1), f"C{i}", values={1: {"intensity": 50 * (i + 1)}},
                        fade_in=0.0)
                c.follow = f
                s.cues.append(c)
            s.go()
            s.tick()
            uhr.vorruecken(0.35)
            s.tick()
            self.assertEqual(s.current_index, 1)
            uhr.vorruecken(0.27)             # t = 0.62
            s.tick()
            self.assertEqual(s.current_index, 2, "Kette driftet um das Tick-Raster")
            s.stop()

    def test_nachholen_nach_langer_pause_ohne_durchflackern(self):
        # Ausgabe-Thread hing 5 s (Serial-Write, GC, Freeze einer anderen Page):
        # EIN Tick stellt die Liste direkt auf die Cue, auf der sie mit
        # durchlaufender Zeit stuende — nicht je Bild eine Cue auf vollem Wert.
        with show_zeit.manuelle_uhr() as uhr:
            s = CueStack("Chase")
            s.mode = "loop"
            for i in range(4):
                c = Cue(float(i + 1), f"C{i}", values={1: {"intensity": 40 * (i + 1)}},
                        fade_in=0.5)
                c.fade_curve = "linear"
                c.follow = 0.5
                s.cues.append(c)
            s.go()
            s.tick()
            uhr.vorruecken(5.2)      # Starts 0,1,2,3,4,5 -> bei 5.2 Cue 2 (Index 1)
            out = s.tick()
            self.assertEqual(s.current_index, 1)
            self.assertEqual(out[1]["intensity"], 56)    # 40 -> 80, 0.2/0.5
            uhr.vorruecken(1 / 44)
            s.tick()
            self.assertEqual(s.current_index, 1, "Kette flackert nach dem Aufholen weiter")
            s.stop()

    def test_follow_null_schaltet_hoechstens_einmal_je_tick_ohne_haengen(self):
        # Follow 0 + Fade 0 (Endlos-Chase) darf den Tick nicht festhalten.
        with show_zeit.manuelle_uhr() as uhr:
            s = _stack(fade=0.0, follow=0.0)
            s.cues[1].follow = 0.0
            s.mode = "loop"
            s.go()
            for _ in range(5):
                uhr.vorruecken(1 / 44)
                s.tick()
            self.assertIn(s.current_index, (0, 1))
            self.assertIsNotNone(s._follow_faellig)
            s.stop()

    def test_shift_clock_schiebt_jede_liste_nur_einmal(self):
        with show_zeit.manuelle_uhr():
            s = _stack(fade=0.0, follow=1.0)
            s.go()
            vorher = s._follow_faellig
            gesehen: set = set()
            s.shift_clock(10.0, gesehen)
            s.shift_clock(10.0, gesehen)     # dieselbe Liste auf zweitem Executor
            self.assertAlmostEqual(s._follow_faellig, vorher + 10.0)
            s.stop()

    def test_efx_vorschau_folgt_derselben_uhr(self):
        # Die Vorschau (EFX.tick) rueckt genau um den Uhr-Vorschub vor — wie der
        # Render-Pfad, der denselben Schritt als dt bekommt.
        from src.core.engine.efx import EfxInstance
        with show_zeit.manuelle_uhr() as uhr:
            a, b = EfxInstance("A"), EfxInstance("B")
            a.start()
            b.start()
            uhr.vorruecken(0.25)
            a.tick()
            b._advance(0.25)
            self.assertGreater(a._phase, 0.0)
            self.assertAlmostEqual(a._phase, b._phase, places=9)
            a.stop()
            b.stop()

    def test_matrix_vorschau_folgt_derselben_uhr(self):
        from src.core.engine.rgb_matrix import RgbMatrixInstance
        with show_zeit.manuelle_uhr() as uhr:
            m, n = RgbMatrixInstance("M"), RgbMatrixInstance("N")
            for x in (m, n):
                x.fixture_grid = [1, 2, 3, 4]
                x.start()
            uhr.vorruecken(0.5)
            m.tick()
            n._advance_step(0.5)
            self.assertGreater(m._step, 0.0)
            self.assertAlmostEqual(m._step, n._step, places=9)
            m.stop()
            n.stop()

    def test_uhr_wird_zurueckgesetzt(self):
        with show_zeit.manuelle_uhr():
            pass
        self.assertIs(show_zeit.aktuelle_uhr(), show_zeit.STANDARD_UHR)


class TestStandardUhr(unittest.TestCase):
    def test_standard_ist_perf_counter(self):
        # Verhalten der App unveraendert: dieselbe Uhr wie Fades seit QA-89.
        self.assertIs(show_zeit.STANDARD_UHR, time.perf_counter)
        self.assertIs(show_zeit.aktuelle_uhr(), time.perf_counter)
        self.assertLess(abs(show_zeit.jetzt() - time.perf_counter()), 1.0)

    def test_follow_startet_keinen_thread(self):
        # Verhalten statt Quelltext: GO mit Follow armiert nur eine Faelligkeit.
        import threading
        with show_zeit.manuelle_uhr():
            vorher = set(threading.enumerate())
            s = _stack(fade=1.0, follow=0.5)
            s.go()
            s.tick()
            neu = [t for t in threading.enumerate() if t not in vorher]
            self.assertEqual(neu, [])
            self.assertIsNotNone(s._follow_faellig)
            s.stop()


class TestShowcaseSimulation(unittest.TestCase):
    """Das Anleitungsbilder-Werkzeug (Herkunft von ENG-33, DEMO-07) setzt seine
    simulierte Zeit als Show-Uhr ein — Fades UND Follows laufen darauf."""

    def test_sim_einbauen_setzt_die_show_uhr(self):
        from unittest import mock
        tools = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")
        if tools not in sys.path:
            sys.path.insert(0, tools)
        from anleitungsbilder import szenen_showcase as sc

        class _BM:
            def _emit_beat(self):
                pass
        bm = _BM()
        alt = show_zeit.aktuelle_uhr()
        try:
            with mock.patch("src.core.engine.bpm_manager.get_bpm_manager",
                            return_value=bm):
                sc.sim_einbauen()
                sc.sim_einbauen()            # zweiter Aufruf: no-op
            self.assertIs(show_zeit.aktuelle_uhr(), sc._UHR)
            s = _stack(fade=0.0, follow=0.5)
            s.go()
            sc._UHR.t += 0.49
            s.tick()
            self.assertEqual(s.current_index, 0)
            sc._UHR.t += 0.02
            s.tick()
            self.assertEqual(s.current_index, 1, "Follow laeuft nicht auf der Sim-Zeit")
            s.stop()
        finally:
            show_zeit.setze_uhr(alt)


if __name__ == "__main__":
    unittest.main()
