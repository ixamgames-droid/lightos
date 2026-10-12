"""OUT-73 — der Reiter „Enttec Pro USB" waehlte einen toten Anschluss vor.

Nachgestellt im grossen Bedientest QA-96 (Linux): frischer Datenordner, Enttec
eingesteckt, Ausgabe → Konfigurieren… → „Verbinden". Die App richtete
``/dev/ttyS31`` ein — einen Anschluss ohne Geraet — und speicherte das. Das rote
Banner erschien, der Enttec blieb ohne Universum.

Ursache: die Liste zeigte alles, was das Betriebssystem als seriellen Anschluss
kennt, in dessen Reihenfolge; ohne gespeicherte Zeile stand der ERSTE Eintrag
da. Unter Windows ist das sinngemaess ``COM1`` oder ein Bluetooth-Anschluss.

Jeder Fall hier faehrt den echten Weg: eine Anschlussliste hinlegen, wie das
Betriebssystem sie meldet → Dialog bauen → lesen, was gewaehlt ist, und bei den
Kernfaellen „Verbinden" druecken und nachsehen, was eingerichtet und was
gespeichert wurde.

Die Anschluesse sind mit den Angaben nachgebildet, die pyserial wirklich
liefert: ein USB-Geraet hat ``vid``/``pid``, alles andere hat ``None``.
"""
import io
import json
import os
import shutil
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication      # noqa: E402

import src.ui.widgets.output_config as oc       # noqa: E402

_app = QApplication.instance() or QApplication([])

# XPLAT-15: Top-Level-Widgets nach jedem Test wirklich abbauen (s. Begruendung
# in tests/_qt_lifecycle.py — `deleteLater()` allein stellt nie zu).
import pytest as _pytest_xplat15                            # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets     # noqa: E402


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    from PySide6.QtWidgets import QApplication as _QApp
    destroy_all_top_level_widgets(_QApp.instance())


# ── Anschluesse, wie pyserial sie meldet ─────────────────────────────────────

class _Port:
    def __init__(self, device, description="n/a", vid=None, pid=None, hwid="n/a"):
        self.device = device
        self.description = description
        self.vid = vid
        self.pid = pid
        self.hwid = hwid


def _enttec(device, description="FT232R USB UART"):
    return _Port(device, description, 0x0403, 0x6001,
                 "USB VID:PID=0403:6001")


def _fremd(device, description="USB-SERIAL CH340"):
    return _Port(device, description, 0x1A86, 0x7523, "USB VID:PID=1A86:7523")


def _leer(device, description="n/a", hwid="n/a"):
    return _Port(device, description, None, None, hwid)


# ── Attrappen fuer Ausgabe und Zustand ───────────────────────────────────────

class _FakeOutputManager:
    def __init__(self):
        self._enttec_outputs: dict[int, object] = {}
        self._artnet_outputs: dict[int, object] = {}
        self._sacn_outputs: dict[int, object] = {}

    def add_universe(self, universe):
        return object()

    def add_enttec(self, universe, port):
        self._enttec_outputs[int(universe)] = port

    def remove_output(self, universe, ausser=None, **_):
        for reg in (self._enttec_outputs, self._artnet_outputs, self._sacn_outputs):
            reg.pop(int(universe), None)


class _FakeState:
    def __init__(self):
        self.output_manager = _FakeOutputManager()
        self.universes: dict[int, object] = {}

    def apply_output_config(self):
        pass


class _MitAnschluessen(unittest.TestCase):
    """Basis: Wegwerf-``universes.json`` und eine nachgestellte Anschlussliste."""

    zeilen: list | None = None     # None = es gibt die Datei nicht (frischer Ordner)
    ports: list = []

    def setUp(self):
        self._dir = tempfile.mkdtemp(prefix="lightos_out73_")
        self._pfad = os.path.join(self._dir, "universes.json")
        if self.zeilen is not None:
            with io.open(self._pfad, "w", encoding="utf-8") as f:
                f.write(json.dumps(self.zeilen, indent=2, ensure_ascii=False))
        self._alt_pfad = oc._UNIV_CONFIG_PATH
        oc._UNIV_CONFIG_PATH = self._pfad

        self._alt_comports = oc.serial.tools.list_ports.comports
        oc.serial.tools.list_ports.comports = lambda: list(self.ports)

        self.state = _FakeState()
        self._alt_get_state = oc.get_state
        oc.get_state = lambda: self.state
        self.dlg = None

    def tearDown(self):
        if self.dlg is not None:
            self.dlg.deleteLater()
        oc.get_state = self._alt_get_state
        oc.serial.tools.list_ports.comports = self._alt_comports
        oc._UNIV_CONFIG_PATH = self._alt_pfad
        shutil.rmtree(self._dir, ignore_errors=True)

    def _dialog(self):
        self.dlg = oc.OutputConfigDialog()
        return self.dlg

    def _liste(self, dlg=None):
        dlg = dlg or self.dlg
        return [dlg._combo_port.itemData(i) for i in range(dlg._combo_port.count())]

    def _gespeichert(self):
        if not os.path.exists(self._pfad):
            return []
        with io.open(self._pfad, encoding="utf-8") as f:
            return json.loads(f.read())

    def _eingerichtet(self):
        return dict(self.state.output_manager._enttec_outputs)

    def _hinweis(self, dlg=None):
        dlg = dlg or self.dlg
        zeile = getattr(dlg, "_lbl_port_hinweis", None)
        return zeile.text() if zeile is not None else ""


# ══════════════════════════════════════════════════════════════════════════════
# A) Der Fall aus QA-96: frischer Datenordner, Enttec steckt
# ══════════════════════════════════════════════════════════════════════════════

class FrischerOrdnerLinuxTest(_MitAnschluessen):
    # Reihenfolge wie vom System: erst die ttyS…, dann die USB-Geraete.
    ports = [_leer("/dev/ttyS31"), _enttec("/dev/ttyUSB0")]

    def test_der_erkannte_adapter_ist_vorgewaehlt(self):
        dlg = self._dialog()
        self.assertEqual(dlg._combo_port.currentData(), "/dev/ttyUSB0")

    def test_verbinden_richtet_den_adapter_ein_und_speichert_ihn(self):
        dlg = self._dialog()
        dlg._connect_enttec()
        self.assertEqual(self._eingerichtet(), {1: "/dev/ttyUSB0"},
                         "sonst bleibt der eingesteckte Enttec ohne Universum")
        enttec = [z for z in self._gespeichert() if z.get("output") == "Enttec"]
        self.assertEqual([(z["num"], z["patch"]) for z in enttec],
                         [(1, "/dev/ttyUSB0")],
                         "der tote Anschluss darf nicht in universes.json landen")

    def test_der_anschluss_ohne_geraet_steht_nicht_in_der_liste(self):
        self._dialog()
        self.assertNotIn("/dev/ttyS31", self._liste())

    def test_der_adapter_steht_oben(self):
        self._dialog()
        self.assertEqual(self._liste()[0], "/dev/ttyUSB0")

    def test_alle_anschluesse_zeigen_bringt_ihn_zurueck_die_wahl_bleibt(self):
        dlg = self._dialog()
        dlg._check_alle_ports.setChecked(True)
        self.assertEqual(self._liste(), ["/dev/ttyUSB0", "/dev/ttyS31"])
        self.assertEqual(dlg._combo_port.currentData(), "/dev/ttyUSB0")
        self.assertIn("kein USB-Gerät", dlg._combo_port.itemText(1))
        dlg._check_alle_ports.setChecked(False)
        self.assertEqual(self._liste(), ["/dev/ttyUSB0"])

    def test_der_hinweis_sagt_dass_etwas_ausgeblendet_ist(self):
        self._dialog()
        self.assertIn("1 Anschluss ohne USB-Gerät ist ausgeblendet", self._hinweis())


class FrischerOrdnerWindowsTest(_MitAnschluessen):
    """Sinngemaess unter Windows: COM1 ist die eingebaute Schnittstelle, COM4
    ein Bluetooth-Anschluss — beide stehen vor dem Adapter und haben kein
    USB-Geraet."""

    ports = [
        _leer("COM1", "Kommunikationsanschluss (COM1)", "ACPI\\PNP0501\\1"),
        _leer("COM4", "Standardmäßige Seriell-über-Bluetooth-Verbindung (COM4)",
              "BTHENUM\\{00001101-0000-1000-8000-00805F9B34FB}_LOCALMFG&0000"),
        _enttec("COM7", "USB Serial Port (COM7)"),
    ]

    def test_der_adapter_ist_vorgewaehlt_nicht_com1(self):
        dlg = self._dialog()
        self.assertEqual(dlg._combo_port.currentData(), "COM7")

    def test_com1_und_bluetooth_sind_ausgeblendet(self):
        self._dialog()
        self.assertEqual(self._liste(), ["COM7"])
        self.assertIn("2 Anschlüsse ohne USB-Gerät sind ausgeblendet",
                      self._hinweis())

    def test_verbinden_nimmt_den_adapter(self):
        dlg = self._dialog()
        dlg._connect_enttec()
        self.assertEqual(self._eingerichtet(), {1: "COM7"})


# ══════════════════════════════════════════════════════════════════════════════
# B) Kein Adapter da: nichts von selbst waehlen
# ══════════════════════════════════════════════════════════════════════════════

class KeinAdapterGestecktTest(_MitAnschluessen):
    ports = [_leer("/dev/ttyS0"), _leer("/dev/ttyS31")]

    def test_nichts_ist_vorgewaehlt(self):
        dlg = self._dialog()
        self.assertFalse(dlg._combo_port.currentData())

    def test_verbinden_richtet_nichts_ein_und_speichert_nichts(self):
        dlg = self._dialog()
        dlg._connect_enttec()
        self.assertEqual(self._eingerichtet(), {})
        self.assertEqual(self._gespeichert(), [])
        self.assertIn("Kein Port", dlg._lbl_enttec_status.text())

    def test_der_hinweis_sagt_was_zu_tun_ist(self):
        self._dialog()
        self.assertIn("Kein USB-DMX-Adapter erkannt", self._hinweis())
        self.assertIn("Ports aktualisieren", self._hinweis())

    def test_einstecken_und_aktualisieren_waehlt_den_adapter(self):
        dlg = self._dialog()
        self.ports = self.ports + [_enttec("/dev/ttyUSB0")]
        dlg._ports_neu_einlesen()
        self.assertEqual(dlg._combo_port.currentData(), "/dev/ttyUSB0")
        self.assertNotIn("Kein USB-DMX-Adapter", self._hinweis())

    def test_mit_haken_stehen_sie_da_aber_keiner_ist_gewaehlt(self):
        dlg = self._dialog()
        dlg._check_alle_ports.setChecked(True)
        self.assertIn("/dev/ttyS0", self._liste())
        self.assertIn("/dev/ttyS31", self._liste())
        self.assertFalse(dlg._combo_port.currentData())


class GarKeinAnschlussTest(_MitAnschluessen):
    ports = []

    def test_die_liste_sagt_es(self):
        dlg = self._dialog()
        self.assertEqual(dlg._combo_port.count(), 1)
        self.assertIn("Kein Port gefunden", dlg._combo_port.currentText())
        self.assertFalse(dlg._combo_port.currentData())


class NurFremdesUsbGeraetTest(_MitAnschluessen):
    """Ein USB-Seriell-Geraet ohne die Kennung des Enttec Pro: es kann ein
    anderer DMX-Adapter sein — oder ein Arduino. Es steht in der Liste, wird
    aber nicht von selbst gewaehlt."""

    ports = [_leer("/dev/ttyS0"), _fremd("/dev/ttyACM0")]

    def test_es_steht_in_der_liste_ist_aber_nicht_vorgewaehlt(self):
        dlg = self._dialog()
        self.assertIn("/dev/ttyACM0", self._liste())
        self.assertFalse(dlg._combo_port.currentData())

    def test_verbinden_ohne_wahl_richtet_nichts_ein(self):
        dlg = self._dialog()
        dlg._connect_enttec()
        self.assertEqual(self._eingerichtet(), {})

    def test_bewusst_gewaehlt_wird_es_eingerichtet(self):
        dlg = self._dialog()
        dlg._combo_port.setCurrentIndex(dlg._combo_port.findData("/dev/ttyACM0"))
        dlg._connect_enttec()
        self.assertEqual(self._eingerichtet(), {1: "/dev/ttyACM0"})

    def test_der_hinweis_bittet_um_die_wahl(self):
        self._dialog()
        self.assertIn("Kein Enttec Pro erkannt", self._hinweis())


# ══════════════════════════════════════════════════════════════════════════════
# C) Reihenfolge
# ══════════════════════════════════════════════════════════════════════════════

class ReihenfolgeTest(_MitAnschluessen):
    ports = [_leer("/dev/ttyS4"), _fremd("/dev/ttyACM0"),
             _enttec("/dev/ttyUSB10"), _enttec("/dev/ttyUSB2")]

    def test_adapter_dann_andere_usb_geraete_dann_der_rest(self):
        dlg = self._dialog()
        dlg._check_alle_ports.setChecked(True)
        self.assertEqual(self._liste(), ["/dev/ttyUSB2", "/dev/ttyUSB10",
                                         "/dev/ttyACM0", "/dev/ttyS4"])

    def test_bei_zwei_adaptern_der_mit_der_kleineren_nummer(self):
        dlg = self._dialog()
        self.assertEqual(dlg._combo_port.currentData(), "/dev/ttyUSB2")


# ══════════════════════════════════════════════════════════════════════════════
# D) Was gespeichert ist, bleibt gewaehlt (OUT-50) — aber nicht mehr unkommentiert
# ══════════════════════════════════════════════════════════════════════════════

class GespeicherterAdapterGewinntTest(_MitAnschluessen):
    zeilen = [{"num": 3, "name": "U3", "output": "Enttec", "patch": "/dev/ttyUSB1"}]
    ports = [_enttec("/dev/ttyUSB0"), _enttec("/dev/ttyUSB1")]

    def test_nicht_der_erste_adapter_sondern_der_gespeicherte(self):
        dlg = self._dialog()
        self.assertEqual(dlg._combo_port.currentData(), "/dev/ttyUSB1")
        self.assertEqual(dlg._spin_enttec_univ.value(), 3)


class GespeicherterToterAnschlussTest(_MitAnschluessen):
    """Die Konfiguration, die der Fehler hinterlassen hat: in ``universes.json``
    steht der tote Anschluss. Der Dialog aendert das nicht still — er zeigt es
    und sagt, wo der Adapter ist."""

    zeilen = [{"num": 1, "name": "Universe 1", "output": "Enttec",
               "patch": "/dev/ttyS31"}]
    ports = [_leer("/dev/ttyS31"), _enttec("/dev/ttyUSB0")]

    def test_er_bleibt_gewaehlt_und_sichtbar_auch_ohne_haken(self):
        dlg = self._dialog()
        self.assertEqual(dlg._combo_port.currentData(), "/dev/ttyS31")
        self.assertFalse(dlg._check_alle_ports.isChecked())

    def test_sein_eintrag_sagt_dass_nichts_dran_haengt(self):
        dlg = self._dialog()
        self.assertIn("kein USB-Gerät", dlg._combo_port.currentText())

    def test_der_adapter_steht_trotzdem_oben(self):
        self._dialog()
        self.assertEqual(self._liste(), ["/dev/ttyUSB0", "/dev/ttyS31"])

    def test_der_hinweis_nennt_den_erkannten_adapter(self):
        self._dialog()
        hinweis = self._hinweis()
        self.assertIn("/dev/ttyS31", hinweis)
        self.assertIn("/dev/ttyUSB0", hinweis)

    def test_die_hinweiszeile_ist_dann_nicht_versteckt(self):
        dlg = self._dialog()
        self.assertFalse(dlg._lbl_port_hinweis.isHidden())

    def test_nach_der_wahl_des_adapters_ist_der_hinweis_weg(self):
        dlg = self._dialog()
        dlg._combo_port.setCurrentIndex(dlg._combo_port.findData("/dev/ttyUSB0"))
        self.assertNotIn("kein USB-Gerät erkannt.", self._hinweis())
        self.assertNotIn("Erkannter Adapter", self._hinweis())

    def test_verbinden_auf_den_adapter_ersetzt_die_tote_zeile(self):
        dlg = self._dialog()
        dlg._combo_port.setCurrentIndex(dlg._combo_port.findData("/dev/ttyUSB0"))
        dlg._connect_enttec()
        self.assertEqual(self._eingerichtet(), {1: "/dev/ttyUSB0"})
        self.assertEqual([z["patch"] for z in self._gespeichert()
                          if z.get("output") == "Enttec"], ["/dev/ttyUSB0"])


class GespeicherterPortFehltTest(_MitAnschluessen):
    """Der gespeicherte Anschluss ist gar nicht da (Kabel in einer anderen
    Buchse, anderer Rechner). Wie seit OUT-50: sichtbar als „nicht gefunden",
    nicht still ersetzt — neu ist nur der Satz, wo der Adapter steht."""

    zeilen = [{"num": 3, "name": "U3", "output": "Enttec", "patch": "COM3"}]
    ports = [_leer("/dev/ttyS0"), _enttec("/dev/ttyUSB0")]

    def test_bleibt_als_nicht_gefunden_gewaehlt(self):
        dlg = self._dialog()
        self.assertEqual(dlg._combo_port.currentData(), "COM3")
        self.assertIn("nicht gefunden", dlg._combo_port.currentText())

    def test_der_hinweis_nennt_den_erkannten_adapter(self):
        self._dialog()
        self.assertIn("COM3 ist derzeit nicht da", self._hinweis())
        self.assertIn("/dev/ttyUSB0", self._hinweis())


# ══════════════════════════════════════════════════════════════════════════════
# E) Eine bewusste Wahl ueberlebt den Neuaufbau
# ══════════════════════════════════════════════════════════════════════════════

class AuswahlBleibtTest(_MitAnschluessen):
    ports = [_leer("/dev/ttyS0"), _enttec("/dev/ttyUSB0"), _enttec("/dev/ttyUSB1")]

    def test_aktualisieren_laesst_die_wahl(self):
        dlg = self._dialog()
        dlg._combo_port.setCurrentIndex(dlg._combo_port.findData("/dev/ttyUSB1"))
        dlg._ports_neu_einlesen()
        self.assertEqual(dlg._combo_port.currentData(), "/dev/ttyUSB1")

    def test_ein_bewusst_gewaehlter_anschluss_ohne_geraet_bleibt_stehen(self):
        dlg = self._dialog()
        dlg._check_alle_ports.setChecked(True)
        dlg._combo_port.setCurrentIndex(dlg._combo_port.findData("/dev/ttyS0"))
        dlg._check_alle_ports.setChecked(False)
        self.assertEqual(dlg._combo_port.currentData(), "/dev/ttyS0",
                         "der Haken darf eine getroffene Wahl nicht wegnehmen")
        self.assertIn("An /dev/ttyS0 ist kein USB-Gerät erkannt", self._hinweis())


class HinweiszeileLeerTest(_MitAnschluessen):
    ports = [_enttec("/dev/ttyUSB0")]

    def test_ohne_anlass_keine_zeile(self):
        dlg = self._dialog()
        self.assertEqual(self._hinweis(), "")
        self.assertTrue(dlg._lbl_port_hinweis.isHidden())


# ══════════════════════════════════════════════════════════════════════════════
# F) Die Regeln ohne Dialog
# ══════════════════════════════════════════════════════════════════════════════

class RegelnTest(unittest.TestCase):

    def setUp(self):
        from src.core.dmx import anschluss_auswahl
        self.aa = anschluss_auswahl

    def test_klassen(self):
        aa = self.aa
        self.assertEqual(aa.klasse_von(_enttec("COM7")), aa.ADAPTER)
        self.assertEqual(aa.klasse_von(_fremd("COM8")), aa.USB)
        self.assertEqual(aa.klasse_von(_leer("COM1")), aa.OHNE_GERAET)

    def test_ftdi_mit_anderer_produktnummer_ist_kein_erkannter_adapter(self):
        port = _Port("COM9", "FT231X", 0x0403, 0x6015)
        self.assertEqual(self.aa.klasse_von(port), self.aa.USB)

    def test_eintrag_ohne_usb_felder_gilt_als_ohne_geraet(self):
        class Nackt:
            device = "/dev/ttyX"
        self.assertEqual(self.aa.klasse_von(Nackt()), self.aa.OHNE_GERAET)
        self.assertEqual([a.device for a in self.aa.ordnen([Nackt()])], ["/dev/ttyX"])

    def test_natuerliche_reihenfolge(self):
        ports = [_enttec("COM10"), _enttec("COM9"), _enttec("COM11"), _enttec("COM2")]
        self.assertEqual([a.device for a in self.aa.ordnen(ports)],
                         ["COM2", "COM9", "COM10", "COM11"])

    def test_leere_beschreibung_wird_nicht_gezeigt(self):
        eintrag = self.aa.ordnen([_leer("/dev/ttyS31")])[0]
        self.assertNotIn("n/a", eintrag.text)
        self.assertIn("/dev/ttyS31", eintrag.text)

    def test_eintrag_ohne_namen_faellt_weg(self):
        self.assertEqual(self.aa.ordnen([_Port("")]), [])

    def test_vorschlag_ist_nur_ein_erkannter_adapter(self):
        aa = self.aa
        self.assertEqual(aa.vorschlag(aa.ordnen([_leer("COM1"), _fremd("COM5")])), "")
        self.assertEqual(
            aa.vorschlag(aa.ordnen([_leer("COM1"), _fremd("COM5"), _enttec("COM7")])),
            "COM7")

    def test_sichtbare_behaelt_den_genannten_anschluss(self):
        aa = self.aa
        alle = aa.ordnen([_leer("COM1"), _leer("COM4"), _enttec("COM7")])
        self.assertEqual([a.device for a in aa.sichtbare(alle)], ["COM7"])
        self.assertEqual([a.device for a in aa.sichtbare(alle, immer=("COM4", ""))],
                         ["COM7", "COM4"])
        self.assertEqual([a.device for a in aa.sichtbare(alle, alle=True)],
                         ["COM7", "COM1", "COM4"])

    def test_hinweis_zaehlt_den_gewaehlten_nicht_als_ausgeblendet(self):
        aa = self.aa
        alle = aa.ordnen([_leer("COM1"), _leer("COM4"), _enttec("COM7")])
        text = aa.hinweis(alle, "COM4")
        self.assertIn("An COM4 ist kein USB-Gerät erkannt", text)
        self.assertIn("Erkannter Adapter: COM7", text)
        self.assertIn("1 Anschluss ohne USB-Gerät ist ausgeblendet", text)

    def test_hinweis_mit_haken_nennt_nichts_ausgeblendetes(self):
        aa = self.aa
        alle = aa.ordnen([_leer("COM1"), _enttec("COM7")])
        self.assertEqual(aa.hinweis(alle, "COM7", alle=True), "")


if __name__ == "__main__":
    unittest.main()
