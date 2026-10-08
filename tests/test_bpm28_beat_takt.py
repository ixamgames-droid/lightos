"""BPM-28: der Beat-Timer misst mit einer hochaufloesenden Uhr.

``BPMManager._loop`` nahm ``time.monotonic()``. Unter Windows ist das
``GetTickCount64()`` mit 15,625 ms Aufloesung: der Timer bemerkte einen
faelligen Beat erst beim naechsten Uhr-Schritt, jeder Beat kam 0–15,6 ms zu
spaet. Gemessen 2026-10-08 (Sitzung D, Windows 11), Versatz gegen das ideale
Raster: 120 BPM Median 2,3 / max 13,2 ms, 600 BPM Median 6,8–8,2 ms. Mit
``bpm_manager.takt_uhr()`` (perf_counter) 0,2–0,4 ms — auch waehrend das
volle Gate parallel lief.
"""
import inspect
import os
import sys
import threading
import time
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.engine import bpm_manager                       # noqa: E402
from src.core.engine.bpm_manager import BPMManager, takt_uhr   # noqa: E402


class _Uhr:
    """Feste Uhr; ``sleep`` rueckt sie genau um die verlangte Zeit vor
    (auf 1 ns gerundet, damit sich keine Gleitkomma-Reste aufsummieren)."""

    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t = round(self.t + s, 9)


def _manager_mit_rekorder(zeitquelle):
    """BPMManager, dessen Beats nur mitgeschrieben werden — keine App-Funktionen,
    kein Zustand ausserhalb der Instanz."""
    m = BPMManager()
    zeiten = []
    m._emit_beat = lambda: zeiten.append(zeitquelle())
    m._emit_tick = lambda is_beat: None
    return m, zeiten


class TaktUhrTest(unittest.TestCase):

    def test_takt_uhr_ist_hochaufloesend(self):
        info = time.get_clock_info("perf_counter")
        self.assertTrue(info.monotonic, info)
        self.assertLessEqual(info.resolution, 0.001, info)
        # takt_uhr liest genau diese Uhr (gleicher Nullpunkt).
        self.assertLess(abs(takt_uhr() - time.perf_counter()), 1.0)

    def test_timer_nutzt_nur_die_takt_uhr(self):
        quelle = inspect.getsource(BPMManager._loop)
        self.assertIn("takt_uhr()", quelle)
        self.assertNotIn("time.monotonic()", quelle)

    def test_beats_fallen_genau_aufs_raster_der_takt_uhr(self):
        """``_loop`` im Testfaden mit fester Uhr: 240 BPM -> ein Beat alle 0,25 s,
        ohne Versatz. Das Ersatz-``time`` kennt nur ``sleep`` — eine verbliebene
        ``time.monotonic()``-Stelle fiele hier mit AttributeError auf."""
        uhr = _Uhr()
        m, zeiten = _manager_mit_rekorder(uhr)

        def _sleep(s):
            uhr.sleep(s)
            if len(zeiten) >= 9:
                m._running = False

        m._bpm = 240.0
        m._running = True
        m._timer = threading.current_thread()
        with mock.patch.object(bpm_manager, "takt_uhr", uhr), \
                mock.patch.object(bpm_manager, "time", types.SimpleNamespace(sleep=_sleep)):
            m._loop()
        m._running, m._timer = False, None

        self.assertEqual(len(zeiten), 9, zeiten)
        for k, t in enumerate(zeiten):
            self.assertAlmostEqual(t, 1000.0 + k * 0.25, places=9, msg=zeiten)

    def test_beats_kommen_puenktlich(self):
        """Echter Timer-Faden, 600 BPM, 25 Beats: Median des Versatzes gegen das
        ideale Raster. main unter Windows 6,8–8,2 ms, mit ``takt_uhr`` 0,2–0,4 ms;
        die Schwelle 3 ms laesst dem Fix Luft fuer eine voll ausgelastete Maschine."""
        m, zeiten = _manager_mit_rekorder(time.perf_counter)
        aufnehmen = m._emit_beat
        genug = threading.Event()

        def _beat():
            aufnehmen()
            if len(zeiten) >= 25:
                genug.set()

        m._emit_beat = _beat
        self.addCleanup(m.reset)
        m.set_manual_bpm(600.0)
        self.assertTrue(genug.wait(10.0), f"nur {len(zeiten)} Beats in 10 s")
        m.reset()

        beats = zeiten[:25]
        versatz = [t - beats[0] - k * 0.1 for k, t in enumerate(beats)]
        null = min(versatz)
        streuung = sorted((v - null) * 1000.0 for v in versatz)
        median = streuung[len(streuung) // 2]
        self.assertLess(median, 3.0,
                        f"Beats bis {streuung[-1]:.1f} ms neben dem Raster, "
                        f"Median {median:.1f} ms")


if __name__ == "__main__":
    unittest.main()
