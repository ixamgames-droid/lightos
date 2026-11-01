"""OUT-81: by-id-Namen (``/dev/serial/by-id``) im Port-Feld „Enttec Pro USB“.

Befund (zweite Gegenpruefung zu OUT-80): ein by-id-Name und das ``ttyUSB…``
desselben Anschlusses galten als zwei Ausgabewege — Laser-Universum am
by-id-Namen, ein anderes Universum an ``ttyUSB1`` -> Laser-Adresse 255 statt 0.
Deshalb bot OUT-80 die Namen nicht an. Seit OUT-80 normalisiert der
NOT-AUS-Weg (``_wege_enttec``); OUT-81 zieht die restlichen Portvergleiche nach
(Doppel-Pruefung OUT-74, Verdraengen beim Anlegen, Portwechsel/Seriennummer im
Dialog) und bietet die Namen dann an.

Nur Attrappen: Wegwerf-Ordner mit Symlinks auf Wegwerf-Dateien, gefaelschte
``comports()``, ``_make_enttec_device`` als Sender-Attrappe, ``universes.json``
als Wegwerf-Datei. Keine Hardware, keine App-Daten.
"""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.dmx import adapter_zeilen                          # noqa: E402
from src.core.dmx import anschluss_auswahl as aa                 # noqa: E402
from src.core.dmx import output_manager as om_mod                # noqa: E402
from src.core.dmx.enttec_pro import ENTTEC_PID, ENTTEC_VID       # noqa: E402

POSIX = os.name == "posix"
LINKNAME = "usb-ENTTEC_DMX_USB_PRO_EN123456-if00-port0"


class _Ordner:
    """Wegwerf-``/dev``: ``ttyFAKE_OUT81_0/1`` als Dateien, ``by-id`` mit Link
    auf ``ttyFAKE_OUT81_1``."""

    def __init__(self, testfall):
        tmp = tempfile.TemporaryDirectory()
        testfall.addCleanup(tmp.cleanup)
        self.tty0 = os.path.join(tmp.name, "ttyFAKE_OUT81_0")
        self.tty1 = os.path.join(tmp.name, "ttyFAKE_OUT81_1")
        for p in (self.tty0, self.tty1):
            open(p, "w").close()
        self.by_id = os.path.join(tmp.name, "by-id")
        os.mkdir(self.by_id)
        self.link = os.path.join(self.by_id, LINKNAME)
        os.symlink(self.tty1, self.link)


def _port(device, vid=ENTTEC_VID, pid=ENTTEC_PID):
    return SimpleNamespace(device=device, vid=vid, pid=pid,
                           description="DMX USB PRO", manufacturer="ENTTEC",
                           product="DMX USB PRO", serial_number=None)


# ── Port-Feld ────────────────────────────────────────────────────────────────

@unittest.skipUnless(POSIX, "by-id-Namen: Linux")
class StabileNamenImPortFeld(unittest.TestCase):

    def setUp(self):
        self.o = _Ordner(self)
        self.liste = aa.ordnen([_port(self.o.tty0), _port(self.o.tty1)])

    def test_link_steht_unter_seinem_anschluss_und_erbt_klasse(self):
        raus = aa.mit_stabilen_namen(self.liste, ordner=self.o.by_id)
        self.assertEqual([self.o.tty0, self.o.tty1, self.o.link],
                         [a.device for a in raus])
        self.assertEqual(raus[1].klasse, raus[2].klasse)
        self.assertEqual(raus[1].zusatz, raus[2].zusatz)
        self.assertIn(self.o.tty1, raus[2].text)

    def test_vorgewaehlt_bleibt_der_anschluss_selbst(self):
        raus = aa.mit_stabilen_namen(self.liste, ordner=self.o.by_id)
        self.assertEqual(self.o.tty0, aa.vorschlag(raus))
        nur1 = aa.mit_stabilen_namen(aa.ordnen([_port(self.o.tty1)]),
                                     ordner=self.o.by_id)
        self.assertEqual(self.o.tty1, aa.vorschlag(nur1))

    def test_link_ohne_anschluss_in_der_liste_fehlt(self):
        raus = aa.mit_stabilen_namen(aa.ordnen([_port(self.o.tty0)]),
                                     ordner=self.o.by_id)
        self.assertEqual([self.o.tty0], [a.device for a in raus])

    def test_ohne_ordner_unveraendert(self):
        raus = aa.mit_stabilen_namen(
            self.liste, ordner=os.path.join(self.o.by_id, "fehlt"))
        self.assertEqual(self.liste, raus)

    def test_windows_unberuehrt(self):
        with mock.patch.object(aa.os, "name", "nt"):
            raus = aa.mit_stabilen_namen(self.liste, ordner=self.o.by_id)
        self.assertEqual(self.liste, raus)

    def test_dialog_bietet_by_id_an(self):
        from PySide6.QtWidgets import QApplication
        import src.ui.widgets.output_config as oc
        QApplication.instance() or QApplication([])
        fd, pfad = tempfile.mkstemp(suffix="_out81.json")
        os.close(fd)
        self.addCleanup(os.remove, pfad)
        with open(pfad, "w", encoding="utf-8") as f:
            json.dump([], f)
        ports = [_port(self.o.tty0), _port(self.o.tty1)]
        with mock.patch.object(oc, "_UNIV_CONFIG_PATH", pfad), \
                mock.patch.object(oc.serial.tools.list_ports, "comports",
                                  lambda *a, **k: list(ports)), \
                mock.patch.object(aa, "BY_ID_ORDNER", self.o.by_id):
            dlg = oc.OutputConfigDialog()
            try:
                dlg._refresh_ports()
                daten = [dlg._combo_port.itemData(i)
                         for i in range(dlg._combo_port.count())]
                self.assertIn(self.o.link, daten)
                self.assertEqual(self.o.tty0, dlg._combo_port.currentData())
            finally:
                dlg.close()
                dlg.deleteLater()

    def test_suite_lenkt_den_echten_ordner_um(self):
        # conftest: ein echter Adapter am Testrechner aendert keinen Dialog-Test.
        self.assertNotEqual("/dev/serial/by-id", aa.BY_ID_ORDNER)


# ── Jeder Portvergleich erkennt beide Namen als EINEN Anschluss ──────────────

@unittest.skipUnless(POSIX, "Symlinks als Portnamen: POSIX")
class EinAnschlussZweiNamen(unittest.TestCase):

    def setUp(self):
        self.o = _Ordner(self)

    def test_gleicher_port_beide_richtungen(self):
        import src.ui.widgets.output_config as oc
        self.assertTrue(oc._gleicher_port(self.o.link, self.o.tty1))
        self.assertTrue(oc._gleicher_port(self.o.tty1, self.o.link))
        self.assertFalse(oc._gleicher_port(self.o.link, self.o.tty0))
        self.assertTrue(oc._gleicher_port("COM3", "com3"))
        self.assertFalse(oc._gleicher_port("", self.o.tty1))

    def test_adapter_zeilen_doppelt(self):
        rows = [{"num": 1, "output": "Enttec", "patch": self.o.link},
                {"num": 2, "output": "Enttec", "patch": self.o.tty1}]
        d = adapter_zeilen.doppelte(rows)
        self.assertEqual(1, len(d))
        self.assertEqual((1, 2), d[0].universen)

    def test_adapter_zeilen_umzug_raeumt_anderen_namen_ab(self):
        rows = [{"num": 1, "output": "Enttec", "patch": self.o.tty1},
                {"num": 2, "output": "Enttec", "patch": self.o.tty0}]
        self.assertEqual([1], adapter_zeilen.andere_abraeumen(
            rows, "Enttec", self.o.link, bleibt=3))
        self.assertEqual("Disabled", rows[0]["output"])
        self.assertEqual("Enttec", rows[1]["output"])

    def test_adapter_zeilen_windows_schreibweise_bleibt(self):
        self.assertEqual(("Enttec", "COM3"),
                         adapter_zeilen.schluessel("Enttec", "com3"))

    def test_seriennummer_beim_verbinden_ueber_by_id(self):
        import src.ui.widgets.output_config as oc
        fd, pfad = tempfile.mkstemp(suffix="_out81_sn.json")
        os.close(fd)
        self.addCleanup(os.remove, pfad)
        with open(pfad, "w", encoding="utf-8") as f:
            json.dump([{"num": 1, "output": "Enttec", "patch": self.o.tty1,
                        "enttec_seriennr": "EN0314159"}], f)
        with mock.patch.object(oc, "_UNIV_CONFIG_PATH", pfad):
            # Gleicher Anschluss unter dem by-id-Namen: Nummer bleibt.
            self.assertEqual("EN0314159",
                             oc._enttec_seriennr_fuer(1, self.o.link))
            # Wirklich anderer Anschluss: Nummer gilt nicht mehr.
            self.assertIsNone(oc._enttec_seriennr_fuer(1, self.o.tty0))

    def test_diagnose_by_id_name_ist_kein_falscher_port(self):
        # Review: ``diagnose_port`` verglich woertlich mit ``comports()`` —
        # ein im Port-Feld gewaehlter by-id-Name meldete „existiert auf diesem
        # System nicht“ und die Statusleiste „falsch konfiguriert“.
        from src.core.dmx import enttec_pro as ep
        with mock.patch.object(ep, "list_serial_ports",
                               return_value=[self.o.tty0, self.o.tty1]), \
                mock.patch.object(ep, "find_enttec_port",
                                  return_value=self.o.tty1):
            self.assertIsNone(ep.diagnose_port(self.o.link))
            self.assertIsNone(ep.diagnose_port(self.o.tty1))
            weg = os.path.join(self.o.by_id, "usb-ENTTEC_weg-if00-port0")
            self.assertIn("existiert auf diesem System nicht",
                          ep.diagnose_port(weg) or "")

    def test_nachweislich_eigen_ueber_beide_namen(self):
        # Review: konfiguriert als by-id-Name, zurueckgemeldet als ttyUSB…
        # (Prozess-Proxy) ist der Dongle nachweislich an SEINEM Anschluss.
        dev = SimpleNamespace(konfig_port=self.o.link, port=self.o.link,
                              port_aktuell=self.o.tty1,
                              is_connected=lambda: True)
        om = om_mod.OutputManager.__new__(om_mod.OutputManager)
        self.assertTrue(om._enttec_nachweislich_eigen(dev))
        dev.port_aktuell = self.o.tty0
        self.assertFalse(om._enttec_nachweislich_eigen(dev))


class _Sender:
    gesendet: dict = {}
    offen: list = []

    def __init__(self, port):
        self.port = port
        _Sender.offen.append(self)

    def send_dmx(self, data):
        _Sender.gesendet[self.port] = bytes(data)

    def close(self):
        if self in _Sender.offen:
            _Sender.offen.remove(self)

    def is_open(self):
        return True


@unittest.skipUnless(POSIX, "Symlinks als Portnamen: POSIX")
class ManagerEinAnschluss(unittest.TestCase):
    """Verdraengen beim Anlegen + NOT-AUS je Ausgabeweg (OUT-64)."""

    def setUp(self):
        self.o = _Ordner(self)
        p = mock.patch.object(om_mod, "_make_enttec_device", _Sender)
        p.start()
        self.addCleanup(p.stop)
        _Sender.gesendet, _Sender.offen = {}, []
        self.om = om_mod.OutputManager()
        for u in (1, 2):
            self.om.add_universe(u)
            self.om.universes[u].set_channel(40, 255)

    def _still(self):
        return redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO())

    def _senden(self):
        a, b = self._still()
        with a, b:
            self.om._send_all()

    def test_anlegen_am_tty_verdraengt_by_id_ausgang(self):
        a, b = self._still()
        with a, b:
            self.om.add_enttec(1, self.o.link)
            self.om.add_enttec(2, self.o.tty1)
        self.assertNotIn(1, self.om._enttec_outputs,
                         "zwei Ausgaenge auf einem Anschluss")
        self.assertEqual([self.o.tty1], [s.port for s in _Sender.offen])

    def test_anlegen_am_by_id_verdraengt_tty_ausgang(self):
        a, b = self._still()
        with a, b:
            self.om.add_enttec(1, self.o.tty1)
            self.om.add_enttec(2, self.o.link)
        self.assertNotIn(1, self.om._enttec_outputs)
        self.assertEqual([self.o.link], [s.port for s in _Sender.offen])

    def test_anderer_anschluss_bleibt(self):
        a, b = self._still()
        with a, b:
            self.om.add_enttec(1, self.o.tty0)
            self.om.add_enttec(2, self.o.link)
        self.assertEqual({1, 2}, set(self.om._enttec_outputs))

    def _notaus(self, laser_port, anderer_port):
        a, b = self._still()
        with a, b:
            self.om.add_enttec(1, laser_port)
            self.om.set_laser_estop_mask({1: frozenset({40})}, True)
            self.om.add_enttec(2, anderer_port)
        self._senden()
        self.assertEqual(0, _Sender.gesendet[anderer_port][39],
                         f"NOT-AUS umgangen: Laser an {laser_port}, "
                         f"U2 an {anderer_port}")

    def test_sicherheit_laser_an_by_id_anderes_universum_an_tty(self):
        # ★ Der Test aus der OUT-80-Gegenpruefung: Laser-Kanal bleibt 0.
        self._notaus(self.o.link, self.o.tty1)

    def test_sicherheit_laser_an_tty_anderes_universum_an_by_id(self):
        self._notaus(self.o.tty1, self.o.link)

    def test_sicherheit_mit_namen_aus_dem_port_feld(self):
        # Der by-id-Name genau so, wie das Port-Feld ihn anbietet.
        raus = aa.mit_stabilen_namen(aa.ordnen([_port(self.o.tty1)]),
                                     ordner=self.o.by_id)
        angeboten = [a.device for a in raus if a.device != self.o.tty1]
        self.assertEqual([self.o.link], angeboten)
        self._notaus(angeboten[0], self.o.tty1)

    def test_ungesperrt_bleibt_255(self):
        a, b = self._still()
        with a, b:
            self.om.add_enttec(2, self.o.link)
        self._senden()
        self.assertEqual(255, _Sender.gesendet[self.o.link][39])


if __name__ == "__main__":
    unittest.main()
