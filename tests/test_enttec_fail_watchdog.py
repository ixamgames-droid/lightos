"""OUT-02: Enttec-Serial-Fehler-Watchdog (Auto-Disable + gedrosselter Reconnect).

Ziel: bei wackligem/abgezogenem USB NICHT dauerhaft bei 44 Hz auf einen toten Port
schreiben (jeder WriteFile auf ein entferntes USB-Geraet riskiert eine native Access
Violation). Nach FAIL_LIMIT aufeinanderfolgenden Fehlern wird der Port geschlossen
und als tot markiert; ein gedrosselter Reconnect reaktiviert die Ausgabe, sobald das
Geraet zurueck ist.

Ohne echte Hardware: ``serial.Serial`` wird durch einen Stub ersetzt.
"""
import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import serial
from src.core.dmx import enttec_pro
from src.core.dmx.enttec_pro import EnttecPro

N = EnttecPro.FAIL_LIMIT


class _FakeSerial:
    def __init__(self, *args, **kwargs):
        self.is_open = True
        self.writes = []
        self.purges = 0
        self.closes = 0
        self.raise_on_write: Exception | None = None

    def write(self, data):
        if self.raise_on_write is not None:
            raise self.raise_on_write
        self.writes.append(bytes(data))

    def reset_output_buffer(self):
        self.purges += 1

    def close(self):
        self.closes += 1
        self.is_open = False


def _make() -> tuple[EnttecPro, _FakeSerial]:
    with mock.patch.object(enttec_pro.serial, "Serial", _FakeSerial):
        dev = EnttecPro("COM_TEST")
    return dev, dev._ser  # type: ignore[attr-defined]


class EnttecFailWatchdogTest(unittest.TestCase):
    def test_consecutive_failures_disable_and_close(self):
        dev, ser = _make()
        ser.raise_on_write = serial.SerialException("port gone")
        for _ in range(N):
            dev.send_dmx(bytes(512))
        self.assertTrue(dev.is_disabled(), "Port nach FAIL_LIMIT Fehlern als tot werten")
        self.assertGreaterEqual(ser.closes, 1, "toten Port schliessen (kein 44-Hz-Hammern)")

    def test_below_limit_stays_active(self):
        dev, ser = _make()
        ser.raise_on_write = serial.SerialException("flaky")
        for _ in range(N - 1):
            dev.send_dmx(bytes(512))
        self.assertFalse(dev.is_disabled(), "ein paar Aussetzer duerfen NICHT sofort disablen")

    def test_success_resets_consecutive_counter(self):
        dev, ser = _make()
        ser.raise_on_write = serial.SerialException("flaky")
        for _ in range(N - 1):
            dev.send_dmx(bytes(512))
        # Ein erfolgreicher Frame setzt den Zaehler zurueck ...
        ser.raise_on_write = None
        dev.send_dmx(bytes(512))
        self.assertFalse(dev.is_disabled())
        # ... also disablen N-1 WEITERE Fehler immer noch nicht (kein Aufsummieren
        # ueber Erfolge hinweg -> nur ANHALTENDE Abrisse zaehlen).
        ser.raise_on_write = serial.SerialException("flaky again")
        for _ in range(N - 1):
            dev.send_dmx(bytes(512))
        self.assertFalse(dev.is_disabled())

    def test_timeout_counts_as_failure(self):
        dev, ser = _make()
        ser.raise_on_write = serial.SerialTimeoutException("slow")
        for _ in range(N):
            dev.send_dmx(bytes(512))
        self.assertTrue(dev.is_disabled(), "auch Timeouts zaehlen Richtung Auto-Disable")
        self.assertGreaterEqual(ser.purges, 1, "Timeout leert weiterhin den Output-Puffer")

    def test_disabled_stops_writing(self):
        dev, ser = _make()
        ser.raise_on_write = serial.SerialException("gone")
        for _ in range(N):
            dev.send_dmx(bytes(512))
        # Default-Drossel (3 s) -> direkt nach dem Disable KEIN Reconnect.
        before = len(ser.writes)
        ser.raise_on_write = None
        dev.send_dmx(bytes(512))
        self.assertEqual(len(ser.writes), before,
                         "im disabled-Zustand wird NICHT auf den (toten) Port geschrieben")

    def test_reconnect_reenables_when_port_returns(self):
        # Patch fuer den GANZEN Test aktiv -> auch der Reconnect oeffnet einen Fake.
        with mock.patch.object(enttec_pro.serial, "Serial", _FakeSerial):
            dev = EnttecPro("COM_TEST")
            dev._reconnect_every_s = 0.0   # Drossel aus -> sofortiger Reconnect-Versuch
            old = dev._ser
            old.raise_on_write = serial.SerialException("gone")
            for _ in range(N):
                dev.send_dmx(bytes(512))
            self.assertTrue(dev.is_disabled())

            # Naechster Frame im disabled-Zustand -> Reconnect (frischer Fake-Port).
            dev.send_dmx(bytes(512))
            self.assertFalse(dev.is_disabled(), "nach erfolgreichem Reopen wieder aktiv")
            self.assertIsNot(dev._ser, old, "neuer Serial-Port nach Reconnect")

            # Und es wird wieder geschrieben.
            dev.send_dmx(bytes(512))
            self.assertEqual(len(dev._ser.writes), 1)


if __name__ == "__main__":
    unittest.main()
