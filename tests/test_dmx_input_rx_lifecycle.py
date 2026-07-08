"""NET-06 (aus AUD-06): RX-Thread-Lebenszyklus der DMX-Eingaenge.

Stirbt der `_loop` eines Receivers ueber einen `break` (transienter OSError aus
recvfrom bei einem Netz-Blip, oder ein unerwarteter Fehler), MUSS `self._running`
zurueckgesetzt und `is_running()` ehrlich `False` werden — sonst luegt `is_running()`
dauerhaft `True`, der UI-Auto-Restart-Guard `if not rx.is_running(): rx.start()`
verpufft und der Eingang bleibt permanent stumm (UI sagt weiter 'Aktiv').
"""
import os
import threading
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.dmx.artnet_input import ArtNetReceiver
from src.core.dmx.sacn_input import SACNReceiver


class _BoomSock:
    """Socket-Stub, dessen recvfrom eine feste Exception wirft (kein echtes Netz)."""
    def __init__(self, exc):
        self._exc = exc

    def recvfrom(self, _n):
        raise self._exc

    def close(self):
        pass


class RxLifecycleTest(unittest.TestCase):
    def test_is_running_false_without_live_thread(self):
        """NET-06: _running=True aber kein lebender Thread -> is_running() False."""
        for rx in (ArtNetReceiver(), SACNReceiver()):
            rx._running = True
            rx._thread = None          # ueber break gestorben (Thread weg)
            self.assertFalse(rx.is_running())

    def test_is_running_true_only_with_live_thread(self):
        rx = ArtNetReceiver()
        rx._running = True
        ev = threading.Event()
        rx._thread = threading.Thread(target=ev.wait, daemon=True)
        rx._thread.start()
        try:
            self.assertTrue(rx.is_running())
        finally:
            ev.set()
            rx._thread.join(1.0)
        self.assertFalse(rx.is_running())   # Thread beendet -> nicht mehr laufend

    def test_artnet_loop_oserror_resets_running(self):
        """Transienter OSError (Netz-Blip) im _loop -> _running=False (Auto-Restart)."""
        rx = ArtNetReceiver()
        rx._sock = _BoomSock(OSError("net down"))
        rx._running = True
        rx._loop()                          # laeuft synchron in den OSError-break
        self.assertFalse(rx._running)

    def test_artnet_loop_unexpected_error_resets_running(self):
        rx = ArtNetReceiver()
        rx._sock = _BoomSock(ValueError("weird"))
        rx._running = True
        rx._loop()                          # aeusserer except -> break
        self.assertFalse(rx._running)

    def test_sacn_loop_oserror_resets_running(self):
        rx = SACNReceiver()
        rx._sock = _BoomSock(OSError("net down"))
        rx._running = True
        rx._loop()
        self.assertFalse(rx._running)

    def test_sacn_loop_unexpected_error_resets_running(self):
        rx = SACNReceiver()
        rx._sock = _BoomSock(ValueError("weird"))
        rx._running = True
        rx._loop()
        self.assertFalse(rx._running)


if __name__ == "__main__":
    unittest.main()
