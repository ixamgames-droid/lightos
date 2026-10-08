"""QA-87: Tap-Tempo misst mit einer hochaufloesenden Uhr — auch unter Windows.

Alle vier Tap-Wege (``TempoBus.tap``, ``TempoBusManager.tap_grandmaster``,
``BPMManager.tap``, ``VCSpeedDial._tap``) nahmen ihre Zeitstempel aus
``time.monotonic()``. Unter Windows ist das ``GetTickCount64()`` mit 15,625 ms
Aufloesung (gemessen 2026-10-08, Sitzung D, Windows 11):

* zwei Taps direkt hintereinander lagen im selben Tick — Abstand 0, BPM 0.
  ``test_vc_speed_node::test_master_tap_taps_bus`` und
  ``test_vc_tempo_widgets::test_tap_bus_sets_bpm`` waren deshalb unter Windows rot
  und unter Linux gruen; der lokale ``VCSpeedDial``-Zweig teilte sogar durch null;
* jeder Abstand war auf 15,625 ms gerastert — bei 130 BPM lag die Tap-BPM nach
  zwei ideal getappten Schlaegen bis 2,4 BPM daneben, nach fuenf noch bis 0,9 BPM.

Seit QA-87 kommen die Zeitstempel aus ``src.core.engine.tap_uhr`` (perf_counter).
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

from PySide6.QtWidgets import QApplication

from src.core.engine import tap_uhr
from src.core.engine.bpm_manager import BPMManager, get_bpm_manager
from src.core.engine.tempo_bus import (
    TempoBus, TempoBusManager, get_tempo_bus_manager, reset_tempo_bus_manager,
)
from src.ui.virtualconsole.vc_speedial import VCSpeedDial, SpeedTarget


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _bpm_manager_ohne_timer() -> BPMManager:
    """Eigener BPMManager ohne Beat-Thread (wie in test_bpm_leader)."""
    m = BPMManager()
    m._ensure_running = lambda: setattr(m, "_running", True)   # type: ignore[method-assign]
    m._stop_timer = lambda: setattr(m, "_running", False)      # type: ignore[method-assign]
    return m


class _Uhr:
    """Feste Tap-Zeit: bleibt stehen, bis der Test sie weiterstellt — egal, wie oft
    ein Tap-Weg sie liest (TempoBus mit Quelle 'bpm_global' liest sie zweimal)."""

    def __init__(self, t=10.0):
        self.t = t

    def __call__(self):
        return self.t


class TapUhrTest(unittest.TestCase):

    def setUp(self):
        _app()
        reset_tempo_bus_manager()
        get_bpm_manager().reset()

    def tearDown(self):
        reset_tempo_bus_manager()
        get_bpm_manager().reset()

    # ── Die Uhr selbst ───────────────────────────────────────────────────────
    def test_tap_uhr_ist_monoton_und_hochaufloesend(self):
        info = time.get_clock_info(tap_uhr.UHR)
        self.assertTrue(info.monotonic, info)
        # Windows: monotonic = GetTickCount64 (0,015625 s), perf_counter = QPC (1e-7 s).
        self.assertLessEqual(info.resolution, 0.001, info)

    def test_jetzt_liest_die_benannte_uhr(self):
        a = tap_uhr.jetzt()
        b = getattr(time, tap_uhr.UHR)()
        # Gleiche Uhr, gleicher Nullpunkt -> praktisch gleich. monotonic laege
        # unter Windows ganz woanders (anderer Nullpunkt).
        self.assertLess(abs(b - a), 1.0)

    def test_alle_tap_wege_nutzen_die_tap_uhr(self):
        for fn in (TempoBus.tap, TempoBusManager.tap_grandmaster, BPMManager.tap,
                   VCSpeedDial._tap):
            quelle = inspect.getsource(fn)
            with self.subTest(fn.__qualname__):
                self.assertIn("tap_uhr.jetzt()", quelle)
                self.assertNotIn("time.monotonic()", quelle)

    # ── Der Fall aus den roten Tests: echte Uhr, Taps ohne Pause ─────────────
    def test_zwei_echte_taps_ohne_pause_ergeben_eine_bpm(self):
        bus = TempoBus("QA87")                 # Quelle 'manual': eigene Tap-Rechnung
        bus.tap()
        self.assertGreater(bus.tap(), 0.0)
        mgr = _bpm_manager_ohne_timer()
        mgr.tap()
        self.assertGreater(mgr.tap(), 0.0)

    # ── Gleicher Zeitstempel: verwerfen, nicht teilen ────────────────────────
    def test_gleicher_zeitstempel_wird_verworfen(self):
        uhr = _Uhr(5.0)
        with mock.patch.object(tap_uhr, "jetzt", uhr):
            w = VCSpeedDial("Speed")
            w.target_mode = SpeedTarget.FUNCTION     # lokaler Tap-Zweig
            w.bpm = 100
            w._tap()
            w._tap()                                 # vorher: ZeroDivisionError
            self.assertAlmostEqual(w.bpm, 100.0)

            mgr = _bpm_manager_ohne_timer()
            mgr.tap()
            self.assertEqual(mgr.tap(), 0.0)

            bus = TempoBus("QA87")
            vorher = bus.bpm
            bus.tap()
            self.assertEqual(bus.tap(), vorher)

    def test_verworfener_tap_bleibt_nicht_in_der_historie(self):
        """Codex-Review #955: der doppelte Zeitstempel darf auch die FOLGENDEN Taps
        nicht verfaelschen. Taps bei 10,0 / 10,0 / 10,5 / 10,5 / 11,0 s sind zwei
        echte Abstaende von 0,5 s -> 120 BPM; mit dem Duplikat in der Historie
        waren es 240 BPM (Mittel aus 0 / 0,5 / 0 / 0,5)."""
        def tappen(tap):
            ergebnis = None
            for t in (10.0, 10.0, 10.5, 10.5, 11.0):
                uhr.t = t
                ergebnis = tap()
            return ergebnis

        uhr = _Uhr()
        with mock.patch.object(tap_uhr, "jetzt", uhr):
            bus = TempoBus("QA87")
            self.assertAlmostEqual(tappen(bus.tap), 120.0, places=6)

            mgr = _bpm_manager_ohne_timer()
            self.assertAlmostEqual(tappen(mgr.tap), 120.0, places=6)

            tbm = get_tempo_bus_manager()
            self.assertAlmostEqual(tappen(tbm.tap_grandmaster), 120.0, places=6)

            w = VCSpeedDial("Speed")
            w.target_mode = SpeedTarget.FUNCTION
            tappen(w._tap)
            self.assertAlmostEqual(w.bpm, 120.0, places=6)

    # ── Mathematik an allen vier Stellen mit fester Uhr ──────────────────────
    def test_tap_mathematik_an_allen_vier_stellen(self):
        def tappen(tap, n=5):
            ergebnis = None
            for i in range(n):
                uhr.t = 10.0 + 0.5 * i               # 0,5 s Abstand -> 120 BPM
                ergebnis = tap()
            return ergebnis

        uhr = _Uhr()
        with mock.patch.object(tap_uhr, "jetzt", uhr):
            bus = TempoBus("QA87")
            self.assertAlmostEqual(tappen(bus.tap), 120.0, places=6)

            mgr = _bpm_manager_ohne_timer()
            self.assertAlmostEqual(tappen(mgr.tap), 120.0, places=6)

            tbm = get_tempo_bus_manager()
            self.assertAlmostEqual(tappen(tbm.tap_grandmaster), 120.0, places=6)

            w = VCSpeedDial("Speed")
            w.target_mode = SpeedTarget.FUNCTION
            tappen(w._tap)
            self.assertAlmostEqual(w.bpm, 120.0, places=6)


if __name__ == "__main__":
    unittest.main()
