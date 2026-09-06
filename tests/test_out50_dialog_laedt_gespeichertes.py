"""OUT-50 — der Ausgabe-Dialog las seinen gespeicherten Stand dreimal nicht.

★ Derselbe Fehler wie OUT-ENTTECUNIV, nur an drei weiteren Stellen desselben
Moduls. Bei OUT-ENTTECUNIV blieb Davids LED-Balken dunkel, weil die
Universumsspinbox ihren gespeicherten Wert nie las. Der Audit danach suchte
gezielt nach der Fehlerklasse — und fand sie noch dreimal:

    (a) COM-Port    -> `_refresh_ports` fuellte die Liste, waehlte aber nie den
                       gespeicherten Port. „Verbinden“ nahm den ERSTEN Port und
                       schrieb ihn zurueck. (Zweite Haelfte von HW-5c.)
    (b) Art-Net-Tab -> Universum, Ziel-IP und Aktiv-Haken wurden nie geladen.
                       „Uebernehmen“ legte eine PHANTOM-ZEILE auf Universum 1 an.
    (c) sACN-Tab    -> dito, und der Multicast-Haken stand HART auf True:
                       „Uebernehmen“ ersetzte eine gespeicherte Unicast-IP
                       durch einen Leerstring.

★★ Warum kein Bestandstest das fing: KEINER baute den Dialog gegen eine
bestehende universes.json. Alle setzen die Widgets vorher selbst
(`test_output_config.py`, `test_output_config_lifecycle.py`) und ueberspringen
damit genau den fehlenden Ladeschritt. Deshalb faehrt jeder Test hier den
echten Weg: Datei hinlegen -> Dialog bauen -> Widget lesen.

Der Kern der Datei ist die `RoundTripTest`-Klasse: sie misst nicht die
Vorbelegung, sondern den SCHADEN — oeffnen, „Uebernehmen“ druecken, ohne etwas
zu aendern, und nachsehen, ob die Datei noch dieselbe ist.
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


class _FakePort:
    """Nachbildung eines `serial.tools.list_ports`-Eintrags."""

    def __init__(self, device, description="FTDI", vid=None, pid=None):
        self.device = device
        self.description = description
        self.vid = vid
        self.pid = pid


class _FakeOutputManager:
    def __init__(self):
        self._enttec_outputs: dict[int, object] = {}
        self._artnet_outputs: dict[int, object] = {}
        self._sacn_outputs: dict[int, object] = {}

    def add_universe(self, universe):
        return object()

    def add_enttec(self, universe, port):
        self._enttec_outputs[int(universe)] = port

    def add_artnet(self, universe, target_ip="255.255.255.255", out_universe=None):
        self._artnet_outputs[int(universe)] = target_ip

    def add_sacn(self, universe, target_ip=None, out_universe=None):
        self._sacn_outputs[int(universe)] = target_ip

    def remove_output(self, universe, ausser=None):
        # NET-12: der echte Manager kennt `ausser` (welcher Adaptertyp
        # STEHEN bleibt). Ohne den Parameter wirft das Double einen
        # TypeError, den `_apply_sacn` in seinem try schluckt — dann
        # laeuft `add_sacn` nie und der Test misst etwas anderes, als
        # er glaubt.
        for reg in (self._enttec_outputs, self._artnet_outputs, self._sacn_outputs):
            reg.pop(int(universe), None)


class _FakeState:
    def __init__(self):
        self.output_manager = _FakeOutputManager()
        self.universes: dict[int, object] = {}

    def apply_output_config(self):
        pass


class _MitKonfig(unittest.TestCase):
    """Basis: legt eine universes.json an den Ort, den das Modul liest.

    Die Umlenkung ist Pflicht und kein Test-Komfort — ohne sie schriebe die
    Suite in die echte `data/universes.json`, also in genau die Datei, ohne die
    kein DMX rausgeht (s. Modulkopf von output_config.py).
    """

    zeilen: list = []
    ports: list = []

    def setUp(self):
        self._dir = tempfile.mkdtemp(prefix="lightos_out50_")
        self._pfad = os.path.join(self._dir, "universes.json")
        self._schreibe(self.zeilen)
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

    def _schreibe(self, zeilen):
        io.open(self._pfad, "w", encoding="utf-8").write(
            json.dumps(zeilen, indent=2, ensure_ascii=False))

    def _gelesen(self):
        return json.loads(io.open(self._pfad, encoding="utf-8").read())

    def _dialog(self):
        self.dlg = oc.OutputConfigDialog()
        return self.dlg


# ══════════════════════════════════════════════════════════════════════════════
# A) Der gemeinsame Helfer
# ══════════════════════════════════════════════════════════════════════════════

class GespeicherteAusgabeZeileTest(_MitKonfig):

    def _lauf(self, zeilen, typ):
        self._schreibe(zeilen)
        return oc._gespeicherte_ausgabe_zeile(typ)

    def test_findet_die_zeile_ihres_typs(self):
        z = self._lauf([{"num": 4, "output": "ArtNet", "patch": "2.0.0.99"}], "ArtNet")
        self.assertIsNotNone(z)
        self.assertEqual(z["patch"], "2.0.0.99")

    def test_typen_werden_nicht_verwechselt(self):
        zeilen = [{"num": 2, "output": "sACN", "patch": "10.0.0.5"},
                  {"num": 4, "output": "ArtNet", "patch": "2.0.0.99"}]
        self.assertEqual(self._lauf(zeilen, "sACN")["patch"], "10.0.0.5")
        self.assertEqual(self._lauf(zeilen, "ArtNet")["patch"], "2.0.0.99")
        self.assertIsNone(self._lauf(zeilen, "Enttec"))

    def test_mehrere_zeilen_kleinste_nummer_gewinnt(self):
        # Bei Art-Net ist das ein normales Mehr-Universen-Setup, kein Fehler —
        # der Tab kann nur eines zeigen, also muss die Wahl vorhersehbar sein.
        z = self._lauf([{"num": 7, "output": "ArtNet", "patch": "2.0.0.7"},
                        {"num": 3, "output": "ArtNet", "patch": "2.0.0.3"}], "ArtNet")
        self.assertEqual(z["num"], 3)

    def test_kaputte_zeilen_halten_den_dialog_nicht_auf(self):
        z = self._lauf([{"num": "abc", "output": "ArtNet"},
                        {"output": "ArtNet"},                       # ohne num
                        {"num": 99, "output": "ArtNet"},            # ausserhalb 1..32
                        {"num": 0, "output": "ArtNet"},             # ausserhalb 1..32
                        "kaputt",                                   # gar kein dict
                        {"num": 5, "output": "ArtNet", "patch": "2.0.0.5"}], "ArtNet")
        self.assertEqual(z["num"], 5)

    def test_ohne_treffer_none(self):
        self.assertIsNone(self._lauf([], "ArtNet"))
        self.assertIsNone(self._lauf([{"num": 1, "output": "Disabled"}], "ArtNet"))

    def test_enttec_universum_baut_auf_demselben_helfer_auf(self):
        # OUT-ENTTECUNIV-Verhalten bleibt unveraendert (Bestandsschutz).
        self._schreibe([{"num": 3, "output": "Enttec", "patch": "/dev/ttyUSB0"}])
        self.assertEqual(oc._gespeichertes_enttec_universum(), 3)
        self.assertEqual(oc._gespeicherter_enttec_port(), "/dev/ttyUSB0")
        self._schreibe([])
        self.assertEqual(oc._gespeichertes_enttec_universum(), 1)
        self.assertEqual(oc._gespeicherter_enttec_port(), "")


# ══════════════════════════════════════════════════════════════════════════════
# B) Die Widgets benutzen den Helfer auch — der Test, der den Fehler gefunden haette
# ══════════════════════════════════════════════════════════════════════════════

class ArtNetTabWirdVorbelegtTest(_MitKonfig):
    zeilen = [{"num": 4, "name": "Bar", "output": "ArtNet", "patch": "192.168.1.99"}]

    def test_universum_ip_und_haken(self):
        dlg = self._dialog()
        self.assertEqual(dlg._spin_artnet_univ.value(), 4,
                         "sonst legt „Uebernehmen“ eine Phantom-Zeile auf U1 an")
        self.assertEqual(dlg._edit_artnet_ip.text(), "192.168.1.99")
        self.assertTrue(dlg._check_artnet.isChecked())

    def test_das_belegte_universum_ist_abwaehlbar(self):
        # MU-02: ohne gemerktes Universum waere der frisch gesetzte Haken zwar
        # sichtbar, aber sein Abwaehlen wirkungslos.
        dlg = self._dialog()
        self.assertEqual(dlg._artnet_active_univ, 4)
        dlg._check_artnet.setChecked(False)
        dlg._apply_artnet()
        self.assertNotIn(4, self.state.output_manager._artnet_outputs)


class ArtNetExterneUniverseTest(_MitKonfig):
    zeilen = [{"num": 4, "output": "ArtNet", "patch": "2.0.0.1", "out_universe": 12}]

    def test_startuniversum_folgt_dem_geladenen_universum(self):
        # A3D-15 laedt die externe Universe fuer das GEWAEHLTE interne Universum.
        # Solange das immer 1 war, kam die gespeicherte 12 nie zum Vorschein.
        dlg = self._dialog()
        self.assertEqual(dlg._spin_artnet_univ.value(), 4)
        self.assertEqual(dlg._spin_artnet_start_univ.value(), 12)


class SacnUnicastTabWirdVorbelegtTest(_MitKonfig):
    zeilen = [{"num": 6, "output": "sACN", "patch": "10.0.0.5"}]

    def test_universum_ip_und_multicast_haken(self):
        dlg = self._dialog()
        self.assertEqual(dlg._spin_sacn_univ.value(), 6)
        self.assertEqual(dlg._edit_sacn_ip.text(), "10.0.0.5")
        self.assertFalse(dlg._check_sacn_multicast.isChecked(),
                         "hart auf True -> „Uebernehmen“ loescht die Unicast-IP")
        self.assertTrue(dlg._check_sacn.isChecked())


class SacnMulticastTabWirdVorbelegtTest(_MitKonfig):
    zeilen = [{"num": 2, "output": "sACN", "patch": ""}]

    def test_leerer_patch_bedeutet_multicast(self):
        dlg = self._dialog()
        self.assertEqual(dlg._spin_sacn_univ.value(), 2)
        self.assertEqual(dlg._edit_sacn_ip.text(), "")
        self.assertTrue(dlg._check_sacn_multicast.isChecked())


class EnttecPortWirdVorgewaehltTest(_MitKonfig):
    zeilen = [{"num": 3, "output": "Enttec", "patch": "/dev/ttyUSB1"}]
    ports = [_FakePort("/dev/ttyUSB0"), _FakePort("/dev/ttyUSB1")]

    def test_nicht_der_erste_port_sondern_der_gespeicherte(self):
        dlg = self._dialog()
        self.assertEqual(dlg._combo_port.currentData(), "/dev/ttyUSB1",
                         "sonst oeffnet „Verbinden“ ein fremdes FTDI-Geraet")
        self.assertEqual(dlg._spin_enttec_univ.value(), 3)

    def test_aktualisieren_verliert_die_auswahl_nicht(self):
        dlg = self._dialog()
        dlg._combo_port.setCurrentIndex(dlg._combo_port.findData("/dev/ttyUSB0"))
        dlg._refresh_ports()
        self.assertEqual(dlg._combo_port.currentData(), "/dev/ttyUSB0",
                         "eine bewusste Auswahl darf ein Listen-Neuaufbau nicht "
                         "wegwerfen")


class EnttecPortFehltTest(_MitKonfig):
    """★ Der gespeicherte Port ist weg (Kabel um, anderer Rechner, HW-5b)."""

    zeilen = [{"num": 3, "output": "Enttec", "patch": "COM3"}]
    ports = [_FakePort("/dev/ttyUSB0"), _FakePort("/dev/ttyUSB9")]

    def test_faellt_nicht_still_auf_ein_fremdes_geraet(self):
        dlg = self._dialog()
        self.assertEqual(dlg._combo_port.currentData(), "COM3")
        self.assertIn("nicht gefunden", dlg._combo_port.currentText(),
                      "der fehlende Port muss sichtbar sein, nicht ersetzt")


class FrischeInstallationTest(_MitKonfig):
    zeilen = []
    ports = [_FakePort("/dev/ttyUSB0")]

    def test_ohne_gespeicherte_zeilen_bleiben_die_defaults(self):
        dlg = self._dialog()
        self.assertEqual(dlg._spin_enttec_univ.value(), 1)
        self.assertEqual(dlg._spin_artnet_univ.value(), 1)
        self.assertEqual(dlg._edit_artnet_ip.text(), "255.255.255.255")
        self.assertFalse(dlg._check_artnet.isChecked())
        self.assertEqual(dlg._spin_sacn_univ.value(), 1)
        self.assertTrue(dlg._check_sacn_multicast.isChecked())
        self.assertFalse(dlg._check_sacn.isChecked())


# ══════════════════════════════════════════════════════════════════════════════
# C) Das Akzeptanzkriterium: oeffnen + „Uebernehmen“ darf nichts veraendern
# ══════════════════════════════════════════════════════════════════════════════

class RoundTripTest(_MitKonfig):
    """★ Der eigentliche Schaden — gemessen an der DATEI, nicht am Widget.

    Genau hier lag der Unterschied zwischen „sieht falsch aus“ und „zerstoert
    die Konfiguration“: weil „Verbinden“/„Uebernehmen“ den angezeigten Wert
    zurueckschreiben, machte jeder Besuch des Tabs aus einem Anzeigefehler eine
    dauerhafte Fehlkonfiguration.
    """

    zeilen = [
        {"num": 3, "name": "Balken", "output": "Enttec", "patch": "/dev/ttyUSB1"},
        {"num": 4, "name": "Bar", "output": "ArtNet", "patch": "192.168.1.99"},
        {"num": 6, "name": "Dach", "output": "sACN", "patch": "10.0.0.5"},
    ]
    ports = [_FakePort("/dev/ttyUSB0"), _FakePort("/dev/ttyUSB1")]

    def _zeile(self, num):
        for r in self._gelesen():
            if int(r["num"]) == num:
                return r
        return None

    def test_artnet_uebernehmen_ohne_aenderung_legt_keine_phantom_zeile_an(self):
        dlg = self._dialog()
        dlg._apply_artnet()
        self.assertEqual(self._zeile(4)["patch"], "192.168.1.99")
        self.assertEqual(self._zeile(4)["output"], "ArtNet")
        # Vor dem Fix entstand hier eine zweite Art-Net-Zeile auf Universum 1.
        self.assertIsNone(self._zeile(1),
                          "Phantom-Zeile auf Universum 1 angelegt")
        self.assertEqual(len(self._gelesen()), 3)

    def test_sacn_uebernehmen_ohne_aenderung_behaelt_die_unicast_ip(self):
        dlg = self._dialog()
        dlg._apply_sacn()
        self.assertEqual(self._zeile(6)["patch"], "10.0.0.5",
                         "der hart gesetzte Multicast-Haken loeschte sie")
        self.assertIsNone(self._zeile(1))

    def test_enttec_verbinden_ohne_aenderung_behaelt_port_und_universum(self):
        dlg = self._dialog()
        dlg._connect_enttec()
        self.assertEqual(self._zeile(3)["patch"], "/dev/ttyUSB1")
        self.assertEqual(self._zeile(3)["output"], "Enttec")
        self.assertIsNone(self._zeile(1))

    def test_alle_drei_nacheinander_lassen_die_datei_unveraendert(self):
        """Der Durchgang, den David real macht: Tab fuer Tab durchklicken."""
        vorher = self._gelesen()
        dlg = self._dialog()
        dlg._connect_enttec()
        dlg._apply_artnet()
        dlg._apply_sacn()
        nachher = self._gelesen()
        self.assertEqual(
            {int(r["num"]): (r["output"], r["patch"]) for r in vorher},
            {int(r["num"]): (r["output"], r["patch"]) for r in nachher})

    def test_ein_zweiter_dialog_sieht_denselben_stand(self):
        """„Tab zu, Tab auf“ — Davids urspruengliche Beobachtung."""
        dlg = self._dialog()
        dlg._connect_enttec()
        dlg._apply_artnet()
        dlg._apply_sacn()
        dlg.deleteLater()
        self.dlg = zweiter = oc.OutputConfigDialog()
        self.assertEqual(zweiter._spin_enttec_univ.value(), 3)
        self.assertEqual(zweiter._combo_port.currentData(), "/dev/ttyUSB1")
        self.assertEqual(zweiter._spin_artnet_univ.value(), 4)
        self.assertEqual(zweiter._edit_artnet_ip.text(), "192.168.1.99")
        self.assertEqual(zweiter._spin_sacn_univ.value(), 6)
        self.assertEqual(zweiter._edit_sacn_ip.text(), "10.0.0.5")


if __name__ == "__main__":
    unittest.main()


# ══════════════════════════════════════════════════════════════════════════════
# D) Haertung — Review-Funde am eigenen Diff
# ══════════════════════════════════════════════════════════════════════════════

class KaputteDateiOeffnetTrotzdemTest(_MitKonfig):
    """★ Der Dialog muss sich oeffnen lassen, gerade wenn die Datei kaputt ist.

    `universes.json` ist von Hand editierbar. Stand dort etwas anderes als ein
    String im `patch`-Feld, flog `.strip()` als AttributeError aus dem
    Konstruktor — und ausgerechnet das Werkzeug, mit dem man den Fehler beheben
    wuerde, liesse sich nicht mehr oeffnen.
    """

    zeilen = [{"num": 3, "output": "Enttec", "patch": 3},
              {"num": 4, "output": "ArtNet", "patch": None},
              {"num": 6, "output": "sACN", "patch": ["kaputt"]}]
    ports = [_FakePort("/dev/ttyUSB0")]

    def test_dialog_baut_und_zeigt_die_universen(self):
        dlg = self._dialog()
        self.assertEqual(dlg._spin_enttec_univ.value(), 3)
        self.assertEqual(dlg._spin_artnet_univ.value(), 4)
        self.assertEqual(dlg._spin_sacn_univ.value(), 6)


class SlotHaeltDenDialogNichtFestTest(_MitKonfig):
    """★ Fallenklasse STAB-09/10: ein `self` fangendes Lambda als Signal-Slot
    pinnt den Dialog GC-unsichtbar (Dialog -> Button -> Lambda -> Dialog).
    Der „Ports aktualisieren"-Knopf haengt deshalb an einer Bound-Method.
    """

    ports = [_FakePort("/dev/ttyUSB0")]

    def test_kein_selbst_fangendes_lambda_in_der_datei(self):
        import inspect
        quelle = inspect.getsource(oc.OutputConfigDialog)
        self.assertNotIn("lambda: self.", quelle)
        self.assertNotIn("lambda _", quelle)

    def test_der_knopf_ruft_wirklich_neu_ein(self):
        # Die Bound-Method darf keine Attrappe sein: sie muss die Liste
        # tatsaechlich neu aufbauen (sonst waere der Umbau eine stille Regression).
        dlg = self._dialog()
        self.ports = [_FakePort("/dev/ttyUSB0"), _FakePort("/dev/ttyUSB7")]
        dlg._ports_neu_einlesen()
        geraete = [dlg._combo_port.itemData(i)
                   for i in range(dlg._combo_port.count())]
        self.assertIn("/dev/ttyUSB7", geraete)
