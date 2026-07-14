"""OUT-03: pro Universum konfigurierbare externe Art-Net/sACN-Universe-Nummer.

Sichert ab, dass _send_all die konfigurierte externe Nummer (out_universe) statt
der fixen Default-Rechnung nutzt — und dass ohne Konfiguration das bisherige
Verhalten unveraendert bleibt (Art-Net = num-1, sACN = num)."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.dmx import output_manager as om_mod
from src.core.dmx.output_manager import OutputManager


class _FakeNetSender:
    """Stub mit Art-Net/sACN-Signatur: send_dmx(universe, data)."""
    def __init__(self, *_a, **_kw):
        self.last_universe = None
        self.sends = 0
        self.closed = False

    def send_dmx(self, universe, data):
        self.last_universe = universe
        self.sends += 1

    def close(self):
        self.closed = True


class TestExternalUniverseNumber(unittest.TestCase):
    def setUp(self):
        # Art-Net/sACN-Sender durch Fakes ersetzen (kein echter Socket).
        self._orig_artnet = om_mod.ArtNetSender
        self._orig_sacn = om_mod.SACNSender
        om_mod.ArtNetSender = _FakeNetSender
        om_mod.SACNSender = _FakeNetSender
        self.om = OutputManager()

    def tearDown(self):
        om_mod.ArtNetSender = self._orig_artnet
        om_mod.SACNSender = self._orig_sacn

    def _send_once(self):
        # Direkt _send_all aufrufen (kein Output-Thread noetig).
        self.om._send_all()

    def test_artnet_out_universe_overrides_default(self):
        self.om.add_universe(3)
        self.om.add_artnet(3, "255.255.255.255", out_universe=5)
        self._send_once()
        sender = self.om._artnet_outputs[3]
        self.assertEqual(sender.last_universe, 5)

    def test_artnet_default_is_num_minus_one(self):
        self.om.add_universe(3)
        self.om.add_artnet(3, "255.255.255.255")
        self._send_once()
        sender = self.om._artnet_outputs[3]
        self.assertEqual(sender.last_universe, 2)   # 3 - 1

    def test_sacn_out_universe_overrides_default(self):
        self.om.add_universe(4)
        self.om.add_sacn(4, None, out_universe=5)
        self._send_once()
        sender = self.om._sacn_outputs[4]
        self.assertEqual(sender.last_universe, 5)

    def test_sacn_default_is_num(self):
        self.om.add_universe(4)
        self.om.add_sacn(4, None)
        self._send_once()
        sender = self.om._sacn_outputs[4]
        self.assertEqual(sender.last_universe, 4)

    def test_remove_output_clears_out_universe(self):
        # Nach remove_output darf ein neuer Adapter die alte externe Nummer nicht
        # erben (faellt wieder auf Default zurueck).
        self.om.add_universe(3)
        self.om.add_artnet(3, "255.255.255.255", out_universe=5)
        self.om.remove_output(3)
        self.om.add_artnet(3, "255.255.255.255")   # ohne out_universe
        self._send_once()
        sender = self.om._artnet_outputs[3]
        self.assertEqual(sender.last_universe, 2)   # Default 3 - 1


if __name__ == "__main__":
    unittest.main()
