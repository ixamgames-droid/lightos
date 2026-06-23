"""STAB-02: EnttecPro-Haertung gegen Access Violations beim Beenden/Reconnect.

Ohne echte serielle Hardware: ``serial.Serial`` wird durch einen Stub ersetzt.
Abgesichert:
- send_dmx() schreibt NICHT auf einen geschlossenen Port (sonst native AV statt
  fangbarer Python-Exception).
- send_dmx() faengt einen mitten im Senden geschlossenen Port ab (SerialException).
- close() leert vorher den Output-Puffer (Schutz vor CloseHandle-neben-WriteFile)
  und ist idempotent.
"""
import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import serial
from src.core.dmx import enttec_pro
from src.core.dmx.enttec_pro import EnttecPro


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


class EnttecProSafetyTest(unittest.TestCase):
    def test_send_writes_when_open(self):
        dev, ser = _make()
        dev.send_dmx(bytes(512))
        self.assertEqual(len(ser.writes), 1)
        self.assertEqual(ser.writes[0][0], 0x7E)   # START_OF_MSG

    def test_send_noop_when_closed(self):
        dev, ser = _make()
        ser.is_open = False
        dev.send_dmx(bytes(512))
        self.assertEqual(ser.writes, [], "kein write() auf geschlossenem Port")

    def test_send_swallows_serial_exception(self):
        dev, ser = _make()
        ser.raise_on_write = serial.SerialException("port gone")
        # darf NICHT propagieren (sonst stirbt der Output-Thread / crasht).
        dev.send_dmx(bytes(512))

    def test_send_timeout_purges(self):
        dev, ser = _make()
        ser.raise_on_write = serial.SerialTimeoutException("slow")
        dev.send_dmx(bytes(512))
        self.assertEqual(ser.purges, 1, "Timeout -> Output-Puffer leeren")

    def test_close_purges_then_closes_and_is_idempotent(self):
        dev, ser = _make()
        dev.close()
        self.assertEqual(ser.purges, 1, "vor close() den Output-Puffer abbrechen")
        self.assertEqual(ser.closes, 1)
        self.assertFalse(ser.is_open)
        dev.close()                       # zweites Mal -> No-Op
        self.assertEqual(ser.closes, 1, "close() ist idempotent (kein Doppel-Close)")


if __name__ == "__main__":
    unittest.main()
