"""VIZ-86: die Zeitgeber, die den Push-Takt des 3D-Visualizers bestimmen,
laufen als ``Qt.PreciseTimer``.

Unter Windows rastet der Standard-``QTimer`` (CoarseTimer) auf das
15,6-ms-Systemraster ein. Gemessen (Windows 11): 66/33/22 ms ergaben 12,6/21,2/
31,8 Pushes je Sekunde statt 15/30/44; mit PreciseTimer 33 ms -> 30,2/s.
Unter Linux faellt das nicht auf — deshalb prueft der Test den Timer-Typ und
nicht die gemessene Rate.

Nicht betroffen: der DMX-Ausgabe-Thread hat einen eigenen Takt
(``time.perf_counter`` + ``time.sleep``), keinen QTimer.
"""
import os
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QApplication

from src.ui.visualizer import dmx_push as DP

_app = QApplication.instance() or QApplication([])


class ServiceTimerTest(unittest.TestCase):
    def test_service_tick_ist_praezise(self):
        from src.core.app_state import AppState
        from src.ui.visualizer.visualizer_service import VisualizerService
        svc = VisualizerService(AppState())
        svc._ensure_timer()
        try:
            self.assertEqual(svc._timer.timerType(), Qt.TimerType.PreciseTimer)
        finally:
            svc._timer.stop()


class EinmalTimerTest(unittest.TestCase):
    def test_precise_single_shot_feuert_einmal_und_raeumt_auf(self):
        gesehen = []
        DP.precise_single_shot(5, lambda: gesehen.append(1))
        lebend = list(DP._PRAEZISE_TIMER)
        self.assertEqual(len(lebend), 1)
        self.assertEqual(lebend[0].timerType(), Qt.TimerType.PreciseTimer)
        self.assertTrue(lebend[0].isSingleShot())
        ende = time.monotonic() + 2
        while not gesehen and time.monotonic() < ende:
            _app.processEvents()
            time.sleep(0.002)
        for _ in range(5):
            _app.processEvents()
        self.assertEqual(gesehen, [1])
        self.assertEqual(DP._PRAEZISE_TIMER, set(), "Timer nach dem Ausloesen freigegeben")

    def test_kanal_nutzt_ohne_eigenen_zeitgeber_den_praezisen(self):
        """Takt-Drossel (_nachher) und Waechter (_waechter) des Push-Kanals."""
        aufrufe = []

        class _Kanal(DP.DmxPushChannel):
            pass

        orig = DP.precise_single_shot
        DP.precise_single_shot = lambda ms, fn: aufrufe.append(ms)
        try:
            k = _Kanal.__new__(_Kanal)
            k._schedule = None
            k._timer_armed = False
            k._waechter_aktiv = False
            DP.DmxPushChannel._nachher(k, 0.010)
            DP.DmxPushChannel._waechter(k, 0.5)
        finally:
            DP.precise_single_shot = orig
        self.assertEqual(aufrufe, [10, 520])

    def test_kein_qtimer_singleshot_mehr_im_kanal(self):
        quelle = open(DP.__file__, encoding="utf-8").read()
        self.assertNotIn("QTimer.singleShot", quelle.split("class DmxPushChannel", 1)[1])


if __name__ == "__main__":
    unittest.main()
