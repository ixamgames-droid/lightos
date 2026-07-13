"""CDX-06: get_lan_ip-Fallback fuer isolierte Venue-LANs.

`get_lan_ip()` (src/web/app.py) ermittelte die LAN-IP nur ueber
connect(("8.8.8.8", 80)) -> das liefert die Adresse der DEFAULT-Route (bei VPN
die VPN-NIC; ohne Internet wirft es / faellt auf 127.*), was fuer die isolierten
Venue-LANs falsch ist, fuer die die Remote-URL gedacht ist.

Diese Suite nagelt fest:
- Normalfall: der connect-Pfad liefert eine brauchbare IP -> die wird genommen.
- connect wirft ODER liefert 127.* -> NIC-Enumeration; Ergebnis ist eine
  Nicht-Loopback-Adresse ODER sauber 127.0.0.1 (nie ein Crash).
- Enumeration findet eine private Adresse -> die wird bevorzugt.
"""
import os
import socket
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import src.web.app as webapp


class _FakeSock:
    """Minimaler UDP-Socket-Stub: connect kann werfen oder eine feste
    getsockname-IP liefern."""

    def __init__(self, connect_ip=None, raise_on_connect=False):
        self._connect_ip = connect_ip
        self._raise = raise_on_connect

    def connect(self, _addr):
        if self._raise:
            raise OSError("no route to host")

    def getsockname(self):
        return (self._connect_ip, 0)

    def close(self):
        pass


class GetLanIpFallbackTest(unittest.TestCase):
    def _patch_socket(self, fake_sock, addrs):
        """Patcht socket.socket (fuer die connect-Heuristik) und die
        NIC-Enumerations-Quellen mit fixen Adressen."""
        patches = [
            mock.patch.object(socket, "socket", return_value=fake_sock),
            mock.patch.object(socket, "gethostname", return_value="host"),
            mock.patch.object(
                socket, "gethostbyname",
                return_value=(addrs[0] if addrs else "127.0.0.1"),
            ),
            mock.patch.object(
                socket, "gethostbyname_ex",
                return_value=("host", [], list(addrs)),
            ),
            mock.patch.object(
                socket, "getaddrinfo",
                return_value=[
                    (socket.AF_INET, socket.SOCK_STREAM, 0, "", (a, 0))
                    for a in addrs
                ],
            ),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_normal_case_uses_connect_address(self):
        """Liefert die connect-Heuristik eine brauchbare LAN-IP, wird die
        direkt genommen (Enumeration irrelevant)."""
        self._patch_socket(_FakeSock(connect_ip="192.168.1.5"), ["10.0.0.9"])
        self.assertEqual(webapp.get_lan_ip(), "192.168.1.5")

    def test_connect_raises_falls_back_to_private_nic(self):
        """connect wirft -> die private NIC-Adresse wird genommen."""
        self._patch_socket(
            _FakeSock(raise_on_connect=True), ["127.0.0.1", "192.168.50.20"]
        )
        ip = webapp.get_lan_ip()
        self.assertEqual(ip, "192.168.50.20")
        self.assertFalse(ip.startswith("127."))

    def test_connect_loopback_falls_back_to_private_nic(self):
        """connect liefert 127.* -> die private NIC-Adresse wird genommen."""
        self._patch_socket(
            _FakeSock(connect_ip="127.0.0.1"), ["172.16.4.7"]
        )
        self.assertEqual(webapp.get_lan_ip(), "172.16.4.7")

    def test_no_private_address_returns_loopback_cleanly(self):
        """Weder connect noch Enumeration liefern etwas Brauchbares ->
        sauberer 127.0.0.1-Fallback, kein Crash."""
        self._patch_socket(
            _FakeSock(raise_on_connect=True), ["127.0.0.1"]
        )
        self.assertEqual(webapp.get_lan_ip(), "127.0.0.1")

    def test_enumeration_errors_return_loopback_cleanly(self):
        """Wirft auch die Enumeration (OSError), gibt es keinen Crash,
        sondern 127.0.0.1."""
        fake = _FakeSock(raise_on_connect=True)
        patches = [
            mock.patch.object(socket, "socket", return_value=fake),
            mock.patch.object(socket, "gethostname", return_value="host"),
            mock.patch.object(
                socket, "gethostbyname", side_effect=OSError("boom")
            ),
            mock.patch.object(
                socket, "gethostbyname_ex", side_effect=OSError("boom")
            ),
            mock.patch.object(
                socket, "getaddrinfo", side_effect=OSError("boom")
            ),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.assertEqual(webapp.get_lan_ip(), "127.0.0.1")

    def test_172_non_private_range_is_rejected(self):
        """172.32.* liegt AUSSERHALB des privaten 172.16-31-Bereichs und darf
        nicht als LAN-IP durchrutschen -> Loopback-Fallback."""
        self._patch_socket(
            _FakeSock(raise_on_connect=True), ["172.32.0.1"]
        )
        self.assertEqual(webapp.get_lan_ip(), "127.0.0.1")


if __name__ == "__main__":
    unittest.main()
