"""OUT-83: Belegter COM-Port — Banner nennt die Belegung, nicht das USB-Kabel.

Befund aus der HW-6-Probe (Windows, echter Enttec, 22.11.2026): bei belegtem
Port (Fehlercode 5) stand im Banner „Adapter nicht verbunden (USB-Kabel/Port
pruefen)“, die Warnzeile behauptete, es erscheine kein Fehler im Bild, und die
Verdachtsliste nannte den venv-Starter ``python.exe`` — den Elternprozess der
eigenen Instanz.

Hier unter Linux nachgestellt: der Oeffnungsversuch liefert per Attrappe die
Windows-Fehlercodes 5/32 (kein echter Port), der Prozess-Schnappschuss ist eine
Liste ``(pid, eltern_pid, name)``.
"""
from __future__ import annotations

import io
import os
import sys
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.dmx import port_check as pc  # noqa: E402
from src.core.dmx.output_manager import OutputManager  # noqa: E402
from src.ui.ausgabe_banner import ausgabe_banner  # noqa: E402

PORT = "COM3"


class _Enttec:
    """Attrappe eines Enttec-Proxys: hat einen Port, sendet (nicht)."""

    def __init__(self, verbunden: bool):
        self.port = PORT
        self.verbunden = verbunden

    def is_connected(self):
        return self.verbunden

    def send_dmx(self, *args):
        pass


def _warne(code: int, verdaechtig=None) -> str:
    puffer = io.StringIO()
    with mock.patch.object(pc, "_win_oeffnungsversuch", lambda p: code), \
         mock.patch.object(pc, "windows_verdaechtige_prozesse",
                           lambda *a, **k: list(verdaechtig or [])):
        pc._warne_windows(PORT, puffer)
    return puffer.getvalue()


def _om(dev) -> OutputManager:
    om = OutputManager()
    om.add_universe(1)
    om._enttec_outputs[1] = dev
    return om


class _Basis(unittest.TestCase):
    def setUp(self):
        pc._BELEGT_GEMELDET.clear()
        self.addCleanup(pc._BELEGT_GEMELDET.clear)


class WarnzeileTest(_Basis):
    def test_warnzeile_behauptet_kein_unsichtbares_versagen(self):
        for code in (5, 32):
            with self.subTest(code=code):
                text = _warne(code)
                self.assertIn("NICHT anlaufen", text)
                self.assertNotIn("ohne dass ein Fehler im Bild", text)
                self.assertIn("von einem anderen Programm belegt", text)

    def test_unbekannter_port_merkt_nichts(self):
        _warne(2)
        self.assertEqual("", pc.belegt_grund(PORT))


class BannerTest(_Basis):
    def test_belegt_zeigt_belegung_statt_usb_kabel(self):
        for code in (5, 32):
            with self.subTest(code=code):
                pc._BELEGT_GEMELDET.clear()
                _warne(code, [(4711, "python.exe")])
                om = _om(_Enttec(verbunden=False))
                zustand = ausgabe_banner(om.ausgabe_status())
                self.assertIn("von einem anderen Programm belegt", zustand.text)
                self.assertNotIn("Adapter nicht verbunden", zustand.text)
                self.assertIn("Verdachtsliste", zustand.tooltip)
                self.assertIn("4711", zustand.tooltip)

    def test_ohne_verdaechtige_trotzdem_hinweis_auf_liste(self):
        _warne(5, [])
        text = ausgabe_banner(_om(_Enttec(False)).ausgabe_status()).text
        self.assertIn("belegt", text)
        self.assertIn("Verdachtsliste", text)

    def test_positivkontrolle_ohne_belegung_bleibt_usb_hinweis(self):
        text = ausgabe_banner(_om(_Enttec(False)).ausgabe_status()).text
        self.assertIn("Adapter nicht verbunden", text)

    def test_nach_erfolgreichem_senden_ist_der_befund_alt(self):
        _warne(5, [(4711, "python.exe")])
        dev = _Enttec(verbunden=True)
        om = _om(dev)
        om.ausgabe_status()                       # sendet -> vergessen
        dev.verbunden = False                     # spaeter abgezogen
        text = ausgabe_banner(om.ausgabe_status()).text
        self.assertIn("Adapter nicht verbunden", text)
        self.assertNotIn("belegt", text)


class GewandertTest(_Basis):
    def test_befund_haengt_am_konfigurierten_port(self):
        # In-Prozess-EnttecPro: ``port`` kann einem Dongle an eine andere
        # Nummer gefolgt sein, ``konfig_port`` bleibt der gepruefte Port.
        _warne(5, [(4711, "python.exe")])
        dev = _Enttec(verbunden=False)
        dev.konfig_port = PORT
        dev.port = "COM9"
        text = ausgabe_banner(_om(dev).ausgabe_status()).text
        self.assertIn("von einem anderen Programm belegt", text)


class ElternketteTest(unittest.TestCase):
    def test_eigener_starter_und_vorfahren_fallen_heraus(self):
        prozesse = [
            (100, 4, "explorer.exe"),
            (150, 100, "python.exe"),     # Startskript ueber dem Starter
            (200, 150, "python.exe"),     # venv-Starter (Elternprozess)
            (300, 200, "python.exe"),     # die eigene App
            (310, 300, "python.exe"),     # eigener Ausgabe-Worker (Kind)
            (400, 100, "python.exe"),     # Waise eines frueheren Laufs
            (500, 100, "pythonw.exe"),
        ]
        pids = [p for p, _ in pc.verdaechtige_aus_liste(prozesse, 300)]
        self.assertNotIn(300, pids)
        self.assertNotIn(200, pids, "venv-Starter darf kein Verdacht sein")
        self.assertNotIn(150, pids)
        self.assertEqual([310, 400, 500], pids)

    def test_kreis_durch_pid_wiederverwendung_haengt_nicht(self):
        prozesse = [(1, 2, "python.exe"), (2, 1, "python.exe"),
                    (3, 9, "python.exe")]
        self.assertEqual([(3, "python.exe")],
                         pc.verdaechtige_aus_liste(prozesse, 1))


if __name__ == "__main__":
    unittest.main()
