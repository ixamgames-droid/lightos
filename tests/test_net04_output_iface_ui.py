"""NET-04: Ausgangs-Netzwerkkarte in der UI waehlbar + gerichteter Broadcast.

XPLAT-06 hatte die Socket-Haelfte gebaut, aber nur ueber die Env-Variable
``LIGHTOS_OUTPUT_IFACE`` — im Betrieb also unerreichbar. Auf einem Venue-PC mit
WLAN **und** Lichtnetz sendet Linux den Limited Broadcast (255.255.255.255) nur
ueber die Default-Route: die Fixtures bleiben schwarz, waehrend die Oberflaeche
„Aktiv" meldet.

★ Die Produktentscheidung dahinter ist bewusst SICHER geschnitten und wird hier
in beide Richtungen festgehalten: der gerichtete Broadcast gilt **nur bei
ausdruecklich gewaehlter NIC**. Ohne Auswahl bleibt alles beim Bestandsverhalten
— den Default global umzustellen waere die groessere Verbesserung und genau
deshalb falsch: es aenderte bestehende, funktionierende Rigs still, und zwar an
der Stelle, an der ein Fehler „Fixtures bleiben schwarz" heisst.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.dmx import output_iface


class DirectedBroadcastTest(unittest.TestCase):
    """Reine Rechnung — pruefbar ohne Netz."""

    def test_uebliche_masken(self):
        self.assertEqual(output_iface.directed_broadcast("192.168.1.50",
                                                         "255.255.255.0"),
                         "192.168.1.255")
        self.assertEqual(output_iface.directed_broadcast("10.0.5.7",
                                                         "255.255.0.0"),
                         "10.0.255.255")
        self.assertEqual(output_iface.directed_broadcast("172.16.3.9",
                                                         "255.255.255.128"),
                         "172.16.3.127")

    def test_randfaelle_liefern_None_statt_unsinn(self):
        # /32 hat keinen Broadcast-Bereich ...
        self.assertIsNone(output_iface.directed_broadcast("1.2.3.4",
                                                          "255.255.255.255"))
        # ... und /0 ergaebe wieder den Limited Broadcast: „gerichtet" waere
        # dann eine leere Behauptung, der Aufrufer soll das merken.
        self.assertIsNone(output_iface.directed_broadcast("1.2.3.4", "0.0.0.0"))
        self.assertIsNone(output_iface.directed_broadcast("keine-ip",
                                                          "255.255.255.0"))
        self.assertIsNone(output_iface.directed_broadcast("1.2.3.4", "quatsch"))


class InterfaceListeTest(unittest.TestCase):
    def test_liste_ist_wohlgeformt_und_ohne_doppelte(self):
        eintraege = output_iface.list_output_interfaces()
        self.assertIsInstance(eintraege, list)
        ips = [e["ip"] for e in eintraege]
        self.assertEqual(len(ips), len(set(ips)),
                         f"dieselbe IP mehrfach in der Auswahlliste: {ips}")
        for e in eintraege:
            self.assertEqual(set(e), {"name", "ip", "netmask", "broadcast"})
            if e["broadcast"] is not None:
                self.assertIsNotNone(
                    e["netmask"],
                    "ein Broadcast ohne Netzmaske waere geraten, nicht abgeleitet")

    def test_loopback_steht_hinten(self):
        """Nicht ausgeblendet (fuer Tests brauchbar), aber auch nicht der erste
        Vorschlag — ein DMX-Ausgang auf 127.0.0.1 erreicht kein Geraet."""
        eintraege = output_iface.list_output_interfaces()
        lo = [i for i, e in enumerate(eintraege) if e["ip"].startswith("127.")]
        andere = [i for i, e in enumerate(eintraege)
                  if not e["ip"].startswith("127.")]
        if lo and andere:
            self.assertGreater(min(lo), max(andere))

    def test_aufzaehlung_wirft_nie(self):
        """★ Sie haengt ueber `artnet_broadcast_target` am ArtNetSender-
        Konstruktor, laeuft also im AUSGABEPFAD. Eine Ausnahme dort kostet den
        DMX-Ausgang — fuer eine blosse Komfort-Ableitung.

        Genau das ist beim Bauen passiert: ein Bestandstest ersetzt
        `socket.socket` durch eine Attrappe ohne `fileno()`, und der
        AttributeError kam durch ein reines `except OSError` nicht ab.
        """
        import socket as _socket

        class KaputterSocket:
            def __init__(self, *a, **k):
                pass

        echt = _socket.socket
        _socket.socket = KaputterSocket
        try:
            self.assertEqual(output_iface._interfaces_linux(), [],
                             "die ioctl-Aufzaehlung muss still leer liefern")
            self.assertIsInstance(output_iface.list_output_interfaces(), list)
        finally:
            _socket.socket = echt


class BroadcastZielTest(unittest.TestCase):
    """★ Der Kern der Produktentscheidung, in beide Richtungen."""

    def setUp(self):
        self._alt = os.environ.get("LIGHTOS_OUTPUT_IFACE")

    def tearDown(self):
        if self._alt is None:
            os.environ.pop("LIGHTOS_OUTPUT_IFACE", None)
        else:
            os.environ["LIGHTOS_OUTPUT_IFACE"] = self._alt

    def test_ohne_auswahl_bleibt_alles_wie_bisher(self):
        os.environ.pop("LIGHTOS_OUTPUT_IFACE", None)
        with _leere_prefs():
            self.assertIsNone(output_iface.output_interface_ip())
            self.assertEqual(output_iface.artnet_broadcast_target(),
                             "255.255.255.255",
                             "ohne gewaehlte NIC darf sich NICHTS aendern")

    def test_mit_auswahl_gerichteter_broadcast(self):
        echte = [e for e in output_iface.list_output_interfaces()
                 if e["broadcast"]]
        if not echte:
            self.skipTest("keine NIC mit ableitbarem Subnetz auf diesem Rechner")
        nic = echte[0]
        os.environ["LIGHTOS_OUTPUT_IFACE"] = nic["ip"]
        self.assertEqual(output_iface.artnet_broadcast_target(),
                         nic["broadcast"])

    def test_unbekannte_ip_faellt_auf_den_default_zurueck(self):
        """Steht dort eine IP, die es hier nicht gibt (Show vom anderen
        Rechner, Adapter abgezogen), darf nichts geraten werden."""
        os.environ["LIGHTOS_OUTPUT_IFACE"] = "203.0.113.77"
        self.assertEqual(output_iface.artnet_broadcast_target(),
                         "255.255.255.255")

    def test_artnet_sender_uebernimmt_das_ziel_nur_beim_limited_broadcast(self):
        from src.core.dmx.artnet import ArtNetSender
        echte = [e for e in output_iface.list_output_interfaces()
                 if e["broadcast"]]
        if not echte:
            self.skipTest("keine NIC mit ableitbarem Subnetz")
        nic = echte[0]
        os.environ["LIGHTOS_OUTPUT_IFACE"] = nic["ip"]
        s1 = ArtNetSender()                       # Default = Limited Broadcast
        self.assertEqual(s1.target_ip, nic["broadcast"])
        # Ein ausdrueckliches Ziel bleibt unangetastet — sonst wuerde eine
        # bewusst eingetragene Node-IP ueberschrieben.
        s2 = ArtNetSender("10.10.10.5")
        self.assertEqual(s2.target_ip, "10.10.10.5")
        for s in (s1, s2):
            try:
                s._sock.close()
            except Exception:
                pass


class PrefsQuelleTest(unittest.TestCase):
    """Die UI-Auswahl liegt geraetegebunden in ui_prefs.json — die Env-Variable
    gewinnt trotzdem, sie ist der Notausgang fuer Support und Tests."""

    def setUp(self):
        self._alt = os.environ.get("LIGHTOS_OUTPUT_IFACE")
        os.environ.pop("LIGHTOS_OUTPUT_IFACE", None)

    def tearDown(self):
        if self._alt is None:
            os.environ.pop("LIGHTOS_OUTPUT_IFACE", None)
        else:
            os.environ["LIGHTOS_OUTPUT_IFACE"] = self._alt

    def test_gespeicherte_auswahl_wird_gelesen(self):
        with _prefs({"output_iface_ip": "192.0.2.9"}):
            self.assertEqual(output_iface.output_interface_ip(), "192.0.2.9")

    def test_env_gewinnt_gegen_die_gespeicherte_auswahl(self):
        os.environ["LIGHTOS_OUTPUT_IFACE"] = "198.51.100.4"
        with _prefs({"output_iface_ip": "192.0.2.9"}):
            self.assertEqual(output_iface.output_interface_ip(), "198.51.100.4")

    def test_kaputte_prefs_kosten_hoechstens_die_einstellung(self):
        """Eine unlesbare Prefs-Datei darf NIE den DMX-Ausgang kosten."""
        with _prefs_roh("{kein json"):
            self.assertIsNone(output_iface.output_interface_ip())
            self.assertEqual(output_iface.artnet_broadcast_target(),
                             "255.255.255.255")


# ── Prefs-Umlenkung ──────────────────────────────────────────────────────────
# programmer_view._PREFS_PATH ist ein Modul-Konstante; fuer den Test wird sie
# auf eine Wegwerf-Datei gebogen (dieselbe Technik wie LIGHTOS_SHOW_DB, nur ohne
# eigene Env-Variable — die gibt es fuer ui_prefs.json nicht).

class _Umlenkung:
    def __init__(self, inhalt: str | None):
        self._inhalt = inhalt

    def __enter__(self):
        from src.ui.views import programmer_view as pv
        self._pv = pv
        self._alt_path = pv._PREFS_PATH
        self._tmp = tempfile.mkdtemp(prefix="lightos-net04-")
        pfad = os.path.join(self._tmp, "ui_prefs.json")
        if self._inhalt is not None:
            with open(pfad, "w", encoding="utf-8") as f:
                f.write(self._inhalt)
        pv._PREFS_PATH = pfad
        return pfad

    def __exit__(self, *a):
        self._pv._PREFS_PATH = self._alt_path
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)
        return False


def _prefs(daten: dict):
    return _Umlenkung(json.dumps(daten))


def _prefs_roh(text: str):
    return _Umlenkung(text)


def _leere_prefs():
    return _Umlenkung("{}")


if __name__ == "__main__":
    unittest.main()
