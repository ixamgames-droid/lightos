"""OUT-74 — einen Adapter auf ein anderes Universum umziehen hinterliess die alte Zeile.

Nachgestellt im grossen Bedientest QA-96: Adapter auf Universum 2 „Verbinden",
dann auf Universum 1 „Verbinden". Der Reiter „Universen" zeigte danach BEIDE
Zeilen mit demselben Anschluss, und nach dem Neustart lag der Adapter auf dem
Universum, das zufaellig weiter hinten in der Datei stand — er sendete also
moeglicherweise das falsche Universum, ohne Meldung.

Drei Dinge werden hier gemessen, jeweils am echten Weg:

* **„Verbinden"** raeumt die anderen Zeilen desselben Adapters ab und sagt es
  („war Universe 2 — jetzt Universe 1") — gemessen an ``universes.json``.
* **Laden** einer Datei, in der ein Adapter doppelt steht: er wird fuer KEINE
  der Zeilen eingerichtet (die erste oder letzte zu nehmen waere geraten), und
  es steht in Statusleiste und Dialog.
* **Universen-Tabelle**: zwei Zeilen mit demselben Adapter bekommen ihre eigene
  Meldung statt „beide senden dorthin".
"""
import io
import json
import os
import shutil
import tempfile
import types
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication      # noqa: E402

import src.ui.widgets.output_config as oc       # noqa: E402
from src.core.app_state import AppState         # noqa: E402

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


USB0 = "/dev/ttyUSB0"
USB1 = "/dev/ttyUSB1"


class _Port:
    """Ein USB-Adapter, wie ``serial.tools.list_ports`` ihn meldet."""

    def __init__(self, device):
        self.device = device
        self.description = "FT232R USB UART"
        self.vid, self.pid = 0x0403, 0x6001
        self.hwid = "USB VID:PID=0403:6001"


class _Geraet:
    def __init__(self, port):
        self.port = port


class _FakeOutputManager:
    """Tut, was der echte Manager beim Enttec tut: derselbe Anschluss wird auf
    einem anderen Universum geschlossen, bevor er neu vergeben wird."""

    def __init__(self):
        self._enttec_outputs: dict[int, _Geraet] = {}
        self._artnet_outputs: dict[int, str] = {}
        self._sacn_outputs: dict[int, object] = {}
        self.eingerichtet: list[tuple[int, str]] = []

    def add_universe(self, universe):
        return object()

    def add_enttec(self, universe, port):
        for u in [u for u, d in self._enttec_outputs.items() if d.port == port]:
            self._enttec_outputs.pop(u)
        self._enttec_outputs[int(universe)] = _Geraet(port)
        self.eingerichtet.append((int(universe), port))

    def add_artnet(self, universe, target_ip="255.255.255.255", out_universe=None):
        self._artnet_outputs[int(universe)] = target_ip

    def add_sacn(self, universe, target_ip=None, out_universe=None):
        self._sacn_outputs[int(universe)] = target_ip

    def remove_output(self, universe, ausser=None, **_):
        for reg in (self._enttec_outputs, self._artnet_outputs, self._sacn_outputs):
            reg.pop(int(universe), None)

    def ausgabe_status(self):
        return ([{"universum": u, "weg": "Enttec"} for u in self._enttec_outputs]
                + [{"universum": u, "weg": "Art-Net"} for u in self._artnet_outputs])

    def enttec_ports(self):
        return {u: d.port for u, d in self._enttec_outputs.items()}


class _FakeState:
    def __init__(self):
        self.output_manager = _FakeOutputManager()
        self.universes: dict[int, object] = {}
        self.enttec_port_notes: dict[int, str | None] = {}

    def apply_output_config(self):
        AppState.apply_output_config(self, path=oc._UNIV_CONFIG_PATH)


class _MitKonfig(unittest.TestCase):
    zeilen: list | None = None
    ports: list = [_Port(USB0), _Port(USB1)]

    def setUp(self):
        self._dir = tempfile.mkdtemp(prefix="lightos_out74_")
        self._pfad = os.path.join(self._dir, "universes.json")
        if self.zeilen is not None:
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
        with io.open(self._pfad, "w", encoding="utf-8") as f:
            f.write(json.dumps(zeilen, indent=2, ensure_ascii=False))

    def _datei(self):
        if not os.path.exists(self._pfad):
            return []
        with io.open(self._pfad, encoding="utf-8") as f:
            return json.loads(f.read())

    def _enttec_zeilen(self):
        return sorted((z["num"], z["patch"]) for z in self._datei()
                      if z.get("output") == "Enttec")

    def _zeile(self, num):
        return next(z for z in self._datei() if z.get("num") == num)

    def _dialog(self):
        self.dlg = oc.OutputConfigDialog()
        return self.dlg

    def _verbinde(self, port, univ, dlg=None):
        dlg = dlg or self.dlg or self._dialog()
        dlg._combo_port.setCurrentIndex(dlg._combo_port.findData(port))
        dlg._spin_enttec_univ.setValue(univ)
        dlg._connect_enttec()
        return dlg

    def _neustart(self):
        """Was der naechste Programmstart aus der Datei macht."""
        frisch = _FakeState()
        AppState.apply_output_config(frisch, path=self._pfad)
        return frisch


# ══════════════════════════════════════════════════════════════════════════════
# A) Der Fall aus QA-96: erst Universum 2, dann Universum 1
# ══════════════════════════════════════════════════════════════════════════════

class UmzugTest(_MitKonfig):
    # Universum 1 gibt es schon (wie nach dem ersten Speichern der Tabelle) —
    # die neue Zeile fuer Universum 2 landet in der Datei also DAHINTER.
    zeilen = [{"num": 1, "name": "Bühne", "output": "Disabled", "patch": ""}]

    def _umziehen(self):
        self._verbinde(USB0, 2)
        self._verbinde(USB0, 1)

    def test_die_alte_zeile_verliert_den_adapter(self):
        self._umziehen()
        self.assertEqual(self._enttec_zeilen(), [(1, USB0)],
                         "sonst stehen zwei Zeilen mit demselben Anschluss da")

    def test_die_alte_zeile_bleibt_als_universum_stehen(self):
        self._umziehen()
        alt = self._zeile(2)
        self.assertEqual((alt["output"], alt["patch"]), ("Disabled", ""))
        self.assertEqual(alt["name"], "Universe 2", "der Name gehoert dem Universum")

    def test_der_status_sagt_woher_der_adapter_kam(self):
        self._umziehen()
        self.assertIn("war Universe 2 — jetzt Universe 1",
                      self.dlg._lbl_enttec_status.text())

    def test_der_satz_ueberlebt_die_spaetere_statusmeldung(self):
        self._umziehen()
        self.dlg._enttec_status_nachtragen()
        text = self.dlg._lbl_enttec_status.text()
        self.assertIn("Universe 1", text)
        self.assertIn("war Universe 2", text)

    def test_nach_dem_neustart_liegt_der_adapter_auf_universum_1(self):
        self._umziehen()
        self.assertEqual(self._neustart().output_manager.enttec_ports(), {1: USB0})

    def test_die_universen_tabelle_zeigt_es_sofort(self):
        self._umziehen()
        tabelle = self.dlg._univ_table
        stand = {tabelle.item(r, 0).text(): tabelle.cellWidget(r, 2).currentText()
                 for r in range(tabelle.rowCount())}
        self.assertEqual(stand, {"1": "Enttec", "2": "Disabled"})

    def test_in_die_andere_richtung_ebenso(self):
        self._verbinde(USB0, 1)
        self._verbinde(USB0, 2)
        self.assertEqual(self._enttec_zeilen(), [(2, USB0)])
        self.assertIn("war Universe 1 — jetzt Universe 2",
                      self.dlg._lbl_enttec_status.text())
        self.assertEqual(self._neustart().output_manager.enttec_ports(), {2: USB0})

    def test_noch_einmal_verbinden_meldet_keinen_umzug(self):
        self._verbinde(USB0, 1)
        self._verbinde(USB0, 1)
        self.assertNotIn("war Universe", self.dlg._lbl_enttec_status.text())

    def test_nach_einem_umzug_meldet_das_naechste_verbinden_ihn_nicht_wieder(self):
        self._umziehen()
        self._verbinde(USB0, 1)
        self.assertNotIn("war Universe", self.dlg._lbl_enttec_status.text())


class ZweiAdapterBleibenZweiTest(_MitKonfig):
    """Ein ANDERER Anschluss auf einem anderen Universum ist kein Umzug."""

    zeilen = [{"num": 1, "name": "Bühne", "output": "Enttec", "patch": USB0}]

    def test_der_zweite_adapter_laesst_den_ersten_stehen(self):
        self._verbinde(USB1, 2)
        self.assertEqual(self._enttec_zeilen(), [(1, USB0), (2, USB1)])
        self.assertNotIn("war Universe", self.dlg._lbl_enttec_status.text())


class NetzZeilenBleibenTest(_MitKonfig):
    """Art-Net an dieselbe Adresse auf mehreren Universen ist Absicht — die
    Regel gilt nur fuer Adapter."""

    zeilen = [{"num": 1, "name": "A", "output": "ArtNet", "patch": "2.0.0.1"},
              {"num": 2, "name": "B", "output": "ArtNet", "patch": "2.0.0.1"},
              {"num": 3, "name": "C", "output": "Enttec", "patch": USB0}]

    def test_umzug_des_adapters_ruehrt_die_netz_zeilen_nicht_an(self):
        self._verbinde(USB0, 4)
        datei = {z["num"]: (z["output"], z["patch"]) for z in self._datei()}
        self.assertEqual(datei[1], ("ArtNet", "2.0.0.1"))
        self.assertEqual(datei[2], ("ArtNet", "2.0.0.1"))
        self.assertEqual(datei[3], ("Disabled", ""))
        self.assertEqual(datei[4], ("Enttec", USB0))


class UmzugAufBelegtesUniversumTest(_MitKonfig):
    zeilen = [{"num": 1, "name": "Netz", "output": "ArtNet", "patch": "2.0.0.1"},
              {"num": 2, "name": "USB", "output": "Enttec", "patch": USB0}]

    def test_ziel_bekommt_den_adapter_quelle_wird_frei(self):
        self._verbinde(USB0, 1)
        datei = {z["num"]: (z["output"], z["patch"]) for z in self._datei()}
        self.assertEqual(datei, {1: ("Enttec", USB0), 2: ("Disabled", "")})


class WindowsSchreibweiseTest(_MitKonfig):
    """``COM3`` und ``com3`` sind unter Windows derselbe Anschluss."""

    zeilen = [{"num": 2, "name": "U2", "output": "Enttec", "patch": "com3"}]
    ports = [_Port("COM3")]

    def test_die_zeile_in_anderer_schreibweise_wird_abgeraeumt(self):
        self._verbinde("COM3", 1)
        self.assertEqual(self._enttec_zeilen(), [(1, "COM3")])


# ══════════════════════════════════════════════════════════════════════════════
# B) Eine Datei, in der der Adapter schon doppelt steht
# ══════════════════════════════════════════════════════════════════════════════

class DoppelterAdapterBeimLadenTest(_MitKonfig):
    """Das hat der Fehler hinterlassen. Welche Zeile gemeint war, steht nicht in
    der Datei — also wird der Adapter fuer keine eingerichtet, und es wird
    gesagt."""

    zeilen = [{"num": 1, "name": "Bühne", "output": "Enttec", "patch": USB0},
              {"num": 2, "name": "Traverse", "output": "Enttec", "patch": USB0},
              {"num": 3, "name": "Netz", "output": "ArtNet", "patch": "2.0.0.9"}]

    def test_der_adapter_wird_fuer_keine_der_zeilen_eingerichtet(self):
        state = self._neustart()
        self.assertEqual(state.output_manager.eingerichtet, [],
                         "sonst gewinnt die Zeile, die zufaellig hinten steht")
        self.assertEqual(state.output_manager.enttec_ports(), {})

    def test_die_reihenfolge_in_der_datei_entscheidet_nichts(self):
        vorwaerts = self._neustart().output_manager.enttec_ports()
        self._schreibe(list(reversed(self.zeilen)))
        rueckwaerts = self._neustart().output_manager.enttec_ports()
        self.assertEqual(vorwaerts, rueckwaerts)

    def test_die_uebrigen_ausgaenge_laufen_trotzdem(self):
        self.assertEqual(self._neustart().output_manager._artnet_outputs,
                         {3: "2.0.0.9"})

    def test_beide_universen_tragen_den_hinweis_fuer_die_statusleiste(self):
        notes = self._neustart().enttec_port_notes
        for num in (1, 2):
            self.assertIn("Universe 1 und 2", notes.get(num) or "")
            self.assertIn(USB0, notes.get(num) or "")
            self.assertIn("für keines", notes.get(num) or "")
        self.assertNotIn(3, {n for n, t in notes.items() if t})

    def test_ein_laufender_adapter_wird_dabei_geschlossen(self):
        # Stand im laufenden Programm noch ein Adapter auf einem der beiden
        # Universen, darf er nicht einfach weitersenden.
        state = _FakeState()
        state.output_manager.add_enttec(2, USB0)
        AppState.apply_output_config(state, path=self._pfad)
        self.assertEqual(state.output_manager.enttec_ports(), {})

    def test_der_dialog_sagt_es_statt_eine_der_zeilen_als_gespeichert_zu_zeigen(self):
        dlg = self._dialog()
        text = dlg._lbl_enttec_status.text()
        self.assertIn("Universe 1 und 2", text)
        self.assertIn("für keines", text)
        self.assertNotIn("Gespeichert:", text)

    def test_verbinden_behebt_es_und_die_hinweise_gehen(self):
        self.state.apply_output_config()
        self.assertTrue(self.state.enttec_port_notes.get(1))
        self._verbinde(USB0, 2)
        self.assertEqual(self._enttec_zeilen(), [(2, USB0)])
        self.assertFalse(any(self.state.enttec_port_notes.values()),
                         "sonst bleibt „Enttec: falsch konfiguriert“ bis zum "
                         "Neustart stehen")
        self.assertEqual(self._neustart().output_manager.enttec_ports(), {2: USB0})
        self.assertFalse(any(self._neustart().enttec_port_notes.values()))


class DreiZeilenTest(_MitKonfig):
    zeilen = [{"num": n, "name": f"U{n}", "output": "Enttec", "patch": USB0}
              for n in (4, 2, 7)]

    def test_alle_drei_werden_genannt_und_keine_eingerichtet(self):
        state = self._neustart()
        self.assertEqual(state.output_manager.eingerichtet, [])
        self.assertIn("Universe 2, 4 und 7", state.enttec_port_notes.get(4) or "")

    def test_verbinden_raeumt_beide_anderen_ab(self):
        self._verbinde(USB0, 7)
        self.assertEqual(self._enttec_zeilen(), [(7, USB0)])
        self.assertIn("war Universe 2 und 4 — jetzt Universe 7",
                      self.dlg._lbl_enttec_status.text())


class KeinFehlalarmTest(_MitKonfig):
    zeilen = [{"num": 1, "name": "A", "output": "Enttec", "patch": USB0},
              {"num": 2, "name": "B", "output": "Enttec", "patch": USB1},
              {"num": 3, "name": "C", "output": "ArtNet", "patch": "2.0.0.1"},
              {"num": 4, "name": "D", "output": "ArtNet", "patch": "2.0.0.1"},
              {"num": 5, "name": "E", "output": "Enttec", "patch": ""}]

    def test_zwei_adapter_und_gleiche_netzadresse_sind_in_ordnung(self):
        state = self._neustart()
        self.assertEqual(state.output_manager.enttec_ports(), {1: USB0, 2: USB1})
        self.assertEqual(state.output_manager._artnet_outputs,
                         {3: "2.0.0.1", 4: "2.0.0.1"})
        self.assertFalse(any(state.enttec_port_notes.values()))

    def test_der_dialog_zeigt_wie_bisher_was_gespeichert_ist(self):
        dlg = self._dialog()
        self.assertIn("Gespeichert:", dlg._lbl_enttec_status.text())


class HinweisVeraltetNichtTest(_MitKonfig):
    """Wird die Zeile ueber die Universen-Tabelle behoben, muss der Hinweis in
    der Statusleiste beim naechsten Anwenden verschwinden."""

    zeilen = [{"num": 1, "name": "A", "output": "Enttec", "patch": USB0},
              {"num": 2, "name": "B", "output": "Enttec", "patch": USB0}]

    def test_nach_der_korrektur_in_der_datei_ist_der_hinweis_weg(self):
        state = _FakeState()
        AppState.apply_output_config(state, path=self._pfad)
        self.assertTrue(state.enttec_port_notes.get(2))
        self._schreibe([{"num": 1, "name": "A", "output": "Enttec", "patch": USB0},
                        {"num": 2, "name": "B", "output": "Disabled", "patch": ""}])
        AppState.apply_output_config(state, path=self._pfad)
        self.assertFalse(any(state.enttec_port_notes.values()))
        self.assertEqual(state.output_manager.enttec_ports(), {1: USB0})

    def test_ein_geloeschtes_universum_nimmt_seinen_hinweis_mit(self):
        state = _FakeState()
        AppState.apply_output_config(state, path=self._pfad)
        self._schreibe([{"num": 1, "name": "A", "output": "Enttec", "patch": USB0}])
        AppState.apply_output_config(state, path=self._pfad)
        self.assertNotIn(2, state.enttec_port_notes)

    def test_stub_ohne_hinweisfeld_ueberlebt(self):
        # Bestandstests rufen apply_output_config auf einem Stub, der nur
        # output_manager und universes mitbringt (HW-5b).
        stub = types.SimpleNamespace(output_manager=_FakeOutputManager(), universes={})
        AppState.apply_output_config(stub, path=self._pfad)
        self.assertEqual(stub.output_manager.eingerichtet, [])
        self.assertIn("Universe 1 und 2", stub.enttec_port_notes.get(1) or "")


# ══════════════════════════════════════════════════════════════════════════════
# C) Universen-Tabelle: „Speichern" mit einem Adapter in zwei Zeilen
# ══════════════════════════════════════════════════════════════════════════════

class _Meldungen:
    """Faengt die Meldungsfenster des Dialogs ab (sonst blockiert der Test)."""

    def __init__(self):
        self.liste: list[tuple[str, str, str]] = []

    def _merke(self, art):
        def meldung(_parent, titel, text, *a, **k):
            self.liste.append((art, titel, text))
        return meldung

    def __enter__(self):
        self._alt = {n: getattr(oc.QMessageBox, n)
                     for n in ("warning", "information", "critical")}
        for name in self._alt:
            setattr(oc.QMessageBox, name, staticmethod(self._merke(name)))
        return self

    def __exit__(self, *exc):
        for name, alt in self._alt.items():
            setattr(oc.QMessageBox, name, alt)

    def titel(self):
        return [t for _art, t, _text in self.liste]


class TabelleSpeichernTest(_MitKonfig):
    zeilen = [{"num": 1, "name": "A", "output": "Enttec", "patch": USB0},
              {"num": 2, "name": "B", "output": "Enttec", "patch": USB0}]

    def test_eigene_meldung_statt_beide_senden_dorthin(self):
        dlg = self._dialog()
        with _Meldungen() as m:
            dlg._univ_save()
        self.assertIn("Ein Adapter auf mehreren Universen", m.titel())
        self.assertNotIn("Zwei Universen auf demselben Ziel", m.titel())
        text = next(t for _a, titel, t in m.liste
                    if titel == "Ein Adapter auf mehreren Universen")
        self.assertIn("Universe 1 und 2", text)
        self.assertIn("KEINES", text)

    def test_nach_dem_speichern_sendet_der_adapter_auf_keinem_der_beiden(self):
        self.state.output_manager.add_enttec(2, USB0)
        dlg = self._dialog()
        with _Meldungen():
            dlg._univ_save()
        self.assertEqual(self.state.output_manager.enttec_ports(), {})


class TabelleNetzDoppeltTest(_MitKonfig):
    zeilen = [{"num": 1, "name": "A", "output": "ArtNet", "patch": "2.0.0.1",
               "out_universe": 5},
              {"num": 2, "name": "B", "output": "ArtNet", "patch": "2.0.0.1",
               "out_universe": 5}]

    def test_fuer_netz_ziele_bleibt_die_bisherige_meldung(self):
        dlg = self._dialog()
        with _Meldungen() as m:
            dlg._univ_save()
        self.assertIn("Zwei Universen auf demselben Ziel", m.titel())
        self.assertNotIn("Ein Adapter auf mehreren Universen", m.titel())


# ══════════════════════════════════════════════════════════════════════════════
# D) Laut melden: das Ausfall-Banner (im Kiosk-Modus gibt es keine Statusleiste)
# ══════════════════════════════════════════════════════════════════════════════

class BannerTest(_MitKonfig):
    zeilen = [{"num": 1, "name": "A", "output": "Enttec", "patch": USB0},
              {"num": 2, "name": "B", "output": "Enttec", "patch": USB0},
              {"num": 3, "name": "Netz", "output": "ArtNet", "patch": "2.0.0.9"}]

    def _banner_wege(self, state):
        """Was das Hauptfenster dem Banner reicht — die echte Methode am Stub."""
        from src.ui import main_window as mw

        class _Lbl:
            def setText(self, t): pass
            def setStyleSheet(self, s): pass
            def setToolTip(self, t): pass

        gereicht = []
        state.output_manager.sende_probleme = lambda: []
        state.get_patched_fixtures = lambda: []
        stub = types.SimpleNamespace(
            _lbl_universe=_Lbl(), _state=state,
            _ausgabe_banner=types.SimpleNamespace(
                aktualisiere=lambda m, wege=None: gereicht.append(list(wege))))
        stub._universen_mit_geraeten = lambda: []
        mw.MainWindow._update_ausgabe_label(stub)
        return gereicht[0]

    def test_der_start_merkt_sich_den_konflikt(self):
        state = self._neustart()
        self.assertEqual([(d.typ, d.patch, d.universen)
                          for d in state.adapter_konflikte],
                         [("Enttec", USB0, (1, 2))])

    def test_das_banner_meldet_ihn_als_ausfall(self):
        from src.ui.ausgabe_banner import ART_STOERUNG, ausgabe_banner
        state = self._neustart()
        zustand = ausgabe_banner(self._banner_wege(state))
        self.assertEqual(zustand.art, ART_STOERUNG)
        self.assertIn(USB0, zustand.text)
        self.assertIn("Universe 1 und 2", zustand.text)
        self.assertIn("für keines eingerichtet", zustand.text)

    def test_ein_adapter_ein_eintrag(self):
        state = self._neustart()
        kaputt = [w for w in self._banner_wege(state) if w.get("verbunden") is False]
        self.assertEqual(len(kaputt), 1)

    def test_nach_verbinden_ist_das_banner_wieder_ruhig(self):
        from src.ui.ausgabe_banner import ART_STOERUNG, ausgabe_banner
        self.state.apply_output_config()
        self.assertTrue(self.state.adapter_konflikte)
        self._verbinde(USB0, 1)
        self.assertEqual(self.state.adapter_konflikte, [])
        zustand = ausgabe_banner(self._banner_wege(self.state))
        self.assertNotEqual(zustand.art, ART_STOERUNG)

    def test_ohne_konflikt_bekommt_das_banner_genau_die_wege(self):
        self._schreibe([self.zeilen[0], self.zeilen[2]])
        state = self._neustart()
        self.assertEqual(state.adapter_konflikte, [])
        self.assertEqual(self._banner_wege(state),
                         state.output_manager.ausgabe_status())


# ══════════════════════════════════════════════════════════════════════════════
# E) Die Regeln ohne Dialog
# ══════════════════════════════════════════════════════════════════════════════

class RegelnTest(unittest.TestCase):

    def setUp(self):
        from src.core.dmx import adapter_zeilen
        self.az = adapter_zeilen

    def test_schluessel(self):
        az = self.az
        self.assertEqual(az.schluessel("Enttec", " /dev/ttyUSB0 "), ("Enttec", USB0))
        self.assertEqual(az.schluessel("Enttec", "com3"), az.schluessel("Enttec", "COM3"))
        self.assertNotEqual(az.schluessel("Enttec", "/dev/ttyusb0"),
                            az.schluessel("Enttec", "/dev/ttyUSB0"))
        self.assertIsNone(az.schluessel("Enttec", ""))
        self.assertIsNone(az.schluessel("ArtNet", "2.0.0.1"))
        self.assertIsNone(az.schluessel("Disabled", USB0))
        self.assertIsNone(az.schluessel(None, None))

    def test_udmx_ohne_angabe_ist_der_einzige_adapter(self):
        az = self.az
        self.assertEqual(az.schluessel("uDMX", ""), ("uDMX", ""))
        zeilen = [{"num": 1, "output": "uDMX", "patch": ""},
                  {"num": 2, "output": "uDMX", "patch": ""}]
        self.assertEqual([d.universen for d in az.doppelte(zeilen)], [(1, 2)])

    def test_doppelte_ueberlebt_kaputte_zeilen(self):
        az = self.az
        zeilen = ["kaputt", None, {"num": "x", "output": "Enttec", "patch": USB0},
                  {"num": 3, "output": "Enttec", "patch": 7},
                  {"num": 4, "output": "Enttec", "patch": 7},
                  {"output": "Enttec", "patch": USB0}]
        self.assertEqual([(d.patch, d.universen) for d in az.doppelte(zeilen)],
                         [("7", (3, 4))])

    def test_dieselbe_nummer_zweimal_ist_kein_konflikt(self):
        zeilen = [{"num": 1, "output": "Enttec", "patch": USB0},
                  {"num": 1, "output": "Enttec", "patch": USB0}]
        self.assertEqual(self.az.doppelte(zeilen), [])

    def test_andere_abraeumen_laesst_fremdes_stehen(self):
        az = self.az
        zeilen = [{"num": 1, "name": "A", "output": "Enttec", "patch": USB0},
                  {"num": 2, "name": "B", "output": "Enttec", "patch": USB0},
                  {"num": 3, "name": "C", "output": "Enttec", "patch": USB1},
                  {"num": 4, "name": "D", "output": "sACN", "patch": USB0}]
        self.assertEqual(az.andere_abraeumen(zeilen, "Enttec", USB0, 1), [2])
        self.assertEqual([(z["output"], z["patch"]) for z in zeilen],
                         [("Enttec", USB0), ("Disabled", ""),
                          ("Enttec", USB1), ("sACN", USB0)])
        self.assertEqual(zeilen[1]["name"], "B")

    def test_andere_abraeumen_tut_nichts_fuer_netz_typen(self):
        zeilen = [{"num": 1, "output": "ArtNet", "patch": "2.0.0.1"},
                  {"num": 2, "output": "ArtNet", "patch": "2.0.0.1"}]
        self.assertEqual(self.az.andere_abraeumen(zeilen, "ArtNet", "2.0.0.1", 1), [])
        self.assertEqual(zeilen[1]["output"], "ArtNet")

    def test_umzug_text(self):
        az = self.az
        self.assertEqual(az.umzug_text([], 1), "")
        self.assertEqual(az.umzug_text([2], 1), "war Universe 2 — jetzt Universe 1")
        self.assertEqual(az.umzug_text([2, 5, 9], 1),
                         "war Universe 2, 5 und 9 — jetzt Universe 1")


class PersistOutputTest(_MitKonfig):
    """Die Schreibfunktion selbst: ohne die neue Liste aendert sich nichts."""

    zeilen = [{"num": 2, "name": "U2", "output": "Enttec", "patch": USB0}]

    def test_ohne_liste_bleibt_die_andere_zeile_wie_bisher(self):
        self.assertTrue(oc._persist_output(1, "Enttec", USB0))
        self.assertEqual(self._enttec_zeilen(), [(1, USB0), (2, USB0)])

    def test_mit_liste_wird_abgeraeumt_und_gemeldet(self):
        geraeumt: list = []
        self.assertTrue(oc._persist_output(1, "Enttec", USB0, abgeraeumt=geraeumt))
        self.assertEqual(geraeumt, [2])
        self.assertEqual(self._enttec_zeilen(), [(1, USB0)])


if __name__ == "__main__":
    unittest.main()
