"""QA-89: der Cue-Fade misst seinen Fortschritt mit einer hochaufloesenden Uhr.

``FadeState`` nahm ``time.monotonic()``. Unter Windows ist das
``GetTickCount64()`` mit 15,625 ms Aufloesung (gemessen 2026-10-08, Sitzung D,
Windows 11): ein Fade rueckte nur in diesen Schritten vor, und eine Cue mit
Fade 0 (intern 1 ms) blieb nach GO bis zum naechsten Tick bei 0.
``test_ui68_go_ohne_executor`` wartet 10 ms und wackelte deshalb unter Windows
(auf main 8 von 10 Laeufen rot, je 1–3 Tests).

Seit QA-89 kommt die Zeit aus ``cue_stack.fade_uhr()`` (perf_counter).
"""
import inspect
import os
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.engine import cue_stack                      # noqa: E402
from src.core.engine.cue_stack import FadeState, fade_uhr   # noqa: E402


class _Uhr:
    def __init__(self, t=100.0):
        self.t = t

    def __call__(self):
        return self.t


class FadeUhrTest(unittest.TestCase):

    def test_fade_uhr_ist_hochaufloesend(self):
        info = time.get_clock_info("perf_counter")
        self.assertTrue(info.monotonic, info)
        self.assertLessEqual(info.resolution, 0.001, info)
        # fade_uhr liest genau diese Uhr (gleicher Nullpunkt).
        self.assertLess(abs(fade_uhr() - time.perf_counter()), 1.0)

    def test_fadestate_nutzt_nur_die_fade_uhr(self):
        for fn in (FadeState.__init__, FadeState._progress, FadeState._blend_per_attr):
            quelle = inspect.getsource(fn)
            with self.subTest(fn.__qualname__):
                self.assertIn("fade_uhr()", quelle)
                self.assertNotIn("time.monotonic()", quelle)

    def test_fortschritt_folgt_der_fade_uhr(self):
        uhr = _Uhr(100.0)
        with mock.patch.object(cue_stack, "fade_uhr", uhr):
            fs = FadeState({1: {"intensity": 0}}, {1: {"intensity": 200}},
                           duration=1.0, delay=0.0)
            self.assertEqual(fs.current_values()[1]["intensity"], 0)
            uhr.t = 100.5                 # halber Fade; scurve(0,5) = 0,5
            self.assertEqual(fs.current_values()[1]["intensity"], 100)
            uhr.t = 101.0
            self.assertEqual(fs.current_values()[1]["intensity"], 200)
            self.assertTrue(fs.done)

    def test_null_fade_ist_nach_wenigen_millisekunden_fertig(self):
        """Der Windows-Fall aus test_ui68: Fade 0 heisst intern 1 ms. Mit dem
        15,6-ms-Raster war die Cue nach 3 ms meist noch bei 0."""
        fs = FadeState({1: {"intensity": 0}}, {1: {"intensity": 128}},
                       duration=0.0, delay=0.0)
        time.sleep(0.003)
        self.assertEqual(fs.current_values()[1]["intensity"], 128)
        self.assertTrue(fs.done)


if __name__ == "__main__":
    unittest.main()
