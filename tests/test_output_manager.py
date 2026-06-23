"""Regressionstests fuer OutputManager Thread-Disziplin.

Hintergrund (Bug 2026-06-02): Render UND Senden laufen im selben 44-Hz-Thread.
Beim 'Ausgabe neu starten' schloss der UI-Thread ein Geraet, waehrend der
Output-Thread mitten im send_dmx() steckte -> Deadlock (pyserial/Windows) ->
komplettes Einfrieren der App. Diese Tests sichern die Fixes ab:
- Reconnect schliesst das alte Geraet (kein Port-Leak / 'Access denied').
- Eine Exception im Geraet beendet den Output-Thread NICHT.
- Connect/Disconnect waehrend laufender Ausgabe fuehrt nicht zum Deadlock.
- start() ist idempotent (kein zweiter Thread).
- stop() blockiert nicht ewig, selbst bei langsamem/haengendem Geraet.
"""
import os
import threading
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.dmx.output_manager import OutputManager


class _FakeDev:
    """Minimal-Stub fuer ein Ausgabe-Geraet (Enttec-Signatur: send_dmx(data))."""
    def __init__(self, port="COM_FAKE"):
        self.port = port
        self.closed = False
        self.sends = 0

    def send_dmx(self, data):
        self.sends += 1

    def close(self):
        self.closed = True


class _RaisingDev(_FakeDev):
    def send_dmx(self, data):
        raise RuntimeError("device boom")


class _SlowDev(_FakeDev):
    """Simuliert ein haengendes write() (z. B. Enttec ohne write_timeout)."""
    def __init__(self, delay=0.2, **kw):
        super().__init__(**kw)
        self.delay = delay

    def send_dmx(self, data):
        time.sleep(self.delay)
        self.sends += 1


class TestOutputManagerThreading(unittest.TestCase):
    def setUp(self):
        self.om = OutputManager()
        self.om.add_universe(1)

    def tearDown(self):
        self.om.stop()

    def test_reconnect_closes_previous_device(self):
        d1 = _FakeDev()
        d2 = _FakeDev()
        self.om._swap_device(self.om._enttec_outputs, 1, d1)
        self.om._swap_device(self.om._enttec_outputs, 1, d2)
        self.assertTrue(d1.closed, "altes Geraet muss beim Reconnect geschlossen werden")
        self.assertFalse(d2.closed)
        self.assertIs(self.om._enttec_outputs[1], d2)

    def test_close_enttec_on_port(self):
        d = _FakeDev(port="COM7")
        self.om._enttec_outputs[2] = d
        self.om.close_enttec_on_port("COM7")
        self.assertTrue(d.closed)
        self.assertNotIn(2, self.om._enttec_outputs)

    def test_raising_device_does_not_kill_loop(self):
        self.om._enttec_outputs[1] = _RaisingDev()
        self.om.start()
        time.sleep(0.15)
        self.assertTrue(self.om._thread.is_alive(),
                        "Output-Thread darf durch Geraete-Exception nicht sterben")

    def test_start_is_idempotent(self):
        self.om.start()
        t1 = self.om._thread
        self.om.start()
        self.assertIs(self.om._thread, t1, "start() darf keinen zweiten Thread starten")

    def test_connect_while_running_no_deadlock(self):
        """Verbinden/Trennen aus einem anderen Thread waehrend die Ausgabe laeuft
        muss schnell zurueckkehren (Lock-geschuetzt, kein Deadlock)."""
        self.om._enttec_outputs[1] = _SlowDev(delay=0.05)
        self.om.start()

        done = threading.Event()

        def reconnect():
            for _ in range(10):
                self.om._swap_device(self.om._enttec_outputs, 1, _SlowDev(delay=0.05))
            done.set()

        t = threading.Thread(target=reconnect)
        t.start()
        t.join(timeout=5.0)
        self.assertTrue(done.is_set(), "Reconnect-Schleife haengt -> Deadlock-Verdacht")

    def test_stop_returns_promptly_with_slow_device(self):
        self.om._enttec_outputs[1] = _SlowDev(delay=0.2)
        self.om.start()
        time.sleep(0.1)
        t0 = time.perf_counter()
        self.om.stop()
        elapsed = time.perf_counter() - t0
        self.assertLess(elapsed, 3.0, "stop() darf nicht ewig blockieren")
        self.assertFalse(self.om._thread, "Thread-Referenz nach stop() geloescht")


class TestOutputManagerStopSafety(unittest.TestCase):
    """STAB-02: stop() schliesst Geraete NUR, wenn der Output-Thread sicher
    beendet ist. Schliesst er trotz noch laufendem Thread, kollidiert CloseHandle()
    unter Windows mit einem ausstehenden WriteFile -> Access Violation beim Beenden
    (crash.log 21.+22.06.)."""

    def test_stop_closes_devices_when_thread_exits(self):
        om = OutputManager()
        om.add_universe(1)
        dev = _FakeDev()
        om._enttec_outputs[1] = dev
        om.start()
        time.sleep(0.05)
        om.stop()
        self.assertTrue(dev.closed, "sauber beendeter Thread -> Geraet wird geschlossen")
        self.assertEqual(om._enttec_outputs, {}, "Registry nach stop() geleert")

    def test_stop_skips_close_when_thread_hangs(self):
        om = OutputManager()
        om._stop_join_s = 0.1
        dev = _FakeDev()
        om._enttec_outputs[1] = dev
        release = threading.Event()
        stuck = threading.Thread(target=lambda: release.wait(3.0), daemon=True)
        stuck.start()
        om._thread = stuck
        t0 = time.perf_counter()
        om.stop()
        elapsed = time.perf_counter() - t0
        self.assertLess(elapsed, 1.0, "stop() darf bei haengendem Thread nicht blockieren")
        self.assertFalse(dev.closed,
                         "haengender Thread -> Geraet NICHT schliessen (AV-Schutz)")
        release.set()
        stuck.join(timeout=3.0)

    def test_second_stop_does_not_double_close(self):
        om = OutputManager()
        dev = _FakeDev()
        om._enttec_outputs[1] = dev
        om.stop()                       # kein Thread -> schliesst direkt
        self.assertTrue(dev.closed)
        dev.closed = False
        om.stop()                       # zweites Mal -> Registry leer
        self.assertFalse(dev.closed, "zweites stop() darf nicht erneut schliessen")


if __name__ == "__main__":
    unittest.main()
