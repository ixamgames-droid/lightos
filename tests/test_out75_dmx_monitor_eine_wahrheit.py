"""OUT-75: DMX-Monitor und Ausgabe sagen dasselbe wie Statusleiste und Banner.

Vier Befunde aus dem grossen Bedientest QA-96:

(a) Der Monitor meldete gruen „geht raus“, waehrend Banner und Statusleiste
    „sendet NICHT“ zeigten — er fragte nur, ob ein Adapter REGISTRIERT ist.
(b) Bei einem nicht angelegten Universum blieb das Raster auf den Werten des
    vorher gewaehlten stehen.
(c) Greift die NOT-AUS-Sperre eines Ausgabewegs, sendet dieser Weg etwas
    anderes als das Bild des Universums — der Monitor zeigte das Bild.
(d) „Verbinden“/„Uebernehmen“ ersetzte eine laufende Ausgabe desselben
    Universums ohne Rueckfrage.

Es wird an kein Geraet gesendet — alle Ausgaenge sind Attrappen.
"""
from __future__ import annotations

import os
import types
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication                       # noqa: E402

from src.core.dmx.output_manager import OutputManager            # noqa: E402
from src.ui import monitor_ausgang as ma                         # noqa: E402
from src.ui.ausgabe_banner import ART_STOERUNG, ausgabe_banner   # noqa: E402

_app = QApplication.instance() or QApplication([])

# XPLAT-15: Top-Level-Widgets nach jedem Test wirklich abbauen.
import pytest as _pytest_xplat15                                 # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets          # noqa: E402


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    destroy_all_top_level_widgets(QApplication.instance())


# ── Attrappen ───────────────────────────────────────────────────────────────

class _Enttec:
    """Ein Enttec-artiger Ausgang mit Selbstauskunft wie der echte Proxy."""

    def __init__(self, port="COM3", verbunden=True, verbindet=False):
        self.port = port
        self._verbunden = verbunden
        self._verbindet = verbindet
        self.bilder: list[bytes] = []

    def status(self):
        from src.core.dmx.serial_process import ST_CONNECTING
        return ST_CONNECTING if self._verbindet else object()

    def is_connected(self):
        return self._verbunden

    def is_open(self):
        return True                 # der Worker-PROZESS lebt — das sagt nichts

    def send_dmx(self, daten):
        self.bilder.append(bytes(daten))

    def close(self):
        pass


class _Netz:
    def __init__(self, target_ip="2.0.0.1"):
        self.target_ip = target_ip
        self.bilder: list[tuple[int, bytes]] = []

    def send_dmx(self, universum, daten):
        self.bilder.append((universum, bytes(daten)))

    def close(self):
        pass


class _Label:
    def __init__(self):
        self.text, self.style, self.tip = "", "", ""

    def setText(self, t):
        self.text = t

    def setStyleSheet(self, s):
        self.style = s

    def setToolTip(self, t):
        self.tip = t


def _monitor_label(om, univ=1, gesendet=True, **kw):
    from src.ui.views import dmx_monitor_view as mv
    stub = types.SimpleNamespace(_lbl_ausgang=_Label())
    mv.DmxMonitorView._update_ausgang_label(stub, om, univ, gesendet, **kw)
    return stub._lbl_ausgang


def _manager(*universen):
    om = OutputManager()
    for u in universen or (1,):
        om.add_universe(u)
    om.grand_master = 1.0
    return om


# ══════════════════════════════════════════════════════════════════════════════
# (a) Eine Wahrheit
# ══════════════════════════════════════════════════════════════════════════════

class ToterAnschlussTest(unittest.TestCase):
    """Der Fall aus dem Befund: der Adapter ist eingerichtet, der Anschluss
    laesst sich nicht oeffnen. Beim Senden wirft nichts."""

    def setUp(self):
        self.om = _manager()
        self.om._enttec_outputs[1] = _Enttec("/dev/ttyS31", verbunden=False)
        self.addCleanup(self.om.stop)

    def test_der_monitor_sagt_sendet_nicht(self):
        lbl = _monitor_label(self.om)
        self.assertIn("sendet NICHT", lbl.text)
        self.assertNotIn("geht raus", lbl.text)
        self.assertIn("ff4444", lbl.style)

    def test_er_sagt_dasselbe_wie_das_banner(self):
        banner = ausgabe_banner(self.om.ausgabe_status())
        self.assertEqual(banner.art, ART_STOERUNG)
        lbl = _monitor_label(self.om)
        self.assertIn("Enttec", lbl.text)
        self.assertIn("Enttec", banner.text)
        # derselbe Grund, dieselbe Formulierung
        self.assertIn("Adapter nicht verbunden", banner.text)
        self.assertIn("Adapter nicht verbunden", lbl.tip)
        self.assertIn("/dev/ttyS31", lbl.tip)

    def test_auch_nach_gesendeten_frames_bleibt_es_dabei(self):
        for _ in range(5):
            self.om._send_all()
        self.assertIn("sendet NICHT", _monitor_label(self.om).text)


class EineWahrheitTest(unittest.TestCase):
    """Fuer jede Lage: meldet das Banner einen Ausfall fuer ein Universum,
    darf der Monitor dieses Universum nicht gruen zeigen — und umgekehrt."""

    LAGEN = {
        "tot": [{"universum": 1, "weg": "Enttec", "ziel": "COM3",
                 "verbunden": False, "problem": "", "zustand": "tot"}],
        "fehlerserie": [{"universum": 1, "weg": "Art-Net", "ziel": "2.0.0.1",
                         "verbunden": False, "problem": "20 Sendefehler in Folge",
                         "zustand": "unbekannt"}],
        "sendet": [{"universum": 1, "weg": "Enttec", "ziel": "COM3",
                    "verbunden": True, "problem": "", "zustand": "sendet"}],
        "ungewiss": [{"universum": 1, "weg": "sACN", "ziel": "",
                      "verbunden": None, "problem": "", "zustand": "unbekannt"}],
        "verbindet": [{"universum": 1, "weg": "Enttec", "ziel": "COM3",
                       "verbunden": None, "problem": "", "zustand": "verbindet"}],
        "anderes_universum_tot": [
            {"universum": 2, "weg": "Enttec", "ziel": "COM4",
             "verbunden": False, "problem": "", "zustand": "tot"},
            {"universum": 1, "weg": "Art-Net", "ziel": "2.0.0.1",
             "verbunden": None, "problem": "", "zustand": "unbekannt"}],
    }

    def test_ausfall_und_gruen_schliessen_sich_aus(self):
        for name, wege in self.LAGEN.items():
            for universum in (1, 2):
                with self.subTest(lage=name, universum=universum):
                    a = ma.aussage(universum, wege, gesendet=True)
                    ausfall_hier = any(w["universum"] == universum
                                       and w["verbunden"] is False for w in wege)
                    self.assertEqual(a.art == ma.ART_SENDET_NICHT, ausfall_hier)
                    if ausfall_hier:
                        self.assertEqual(ausgabe_banner(wege).art, ART_STOERUNG)
                        self.assertNotEqual(a.stil, ma.STIL_OK)

    def test_verbindet_ist_weder_gruen_noch_rot(self):
        a = ma.aussage(1, self.LAGEN["verbindet"], gesendet=True)
        self.assertEqual(a.art, ma.ART_VERBINDET)
        self.assertIn("verbindet", a.text)
        self.assertEqual(a.stil, ma.STIL_FEHLT)

    def test_ungewiss_bleibt_gruen_wie_im_banner(self):
        """Ein UDP-Ausgang kann nicht wissen, ob jemand zuhoert — das Banner
        meldet dafuer keinen Ausfall, der Monitor auch nicht."""
        a = ma.aussage(1, self.LAGEN["ungewiss"], gesendet=True)
        self.assertEqual(a.art, ma.ART_GEHT_RAUS)

    def test_zwei_wege_einer_tot_beide_werden_genannt(self):
        wege = self.LAGEN["tot"] + [
            {"universum": 1, "weg": "Art-Net", "ziel": "2.0.0.1",
             "verbunden": None, "problem": "", "zustand": "unbekannt"}]
        a = ma.aussage(1, wege, gesendet=True)
        self.assertIn("Enttec sendet NICHT", a.text)
        self.assertIn("Art-Net geht raus", a.text)

    def test_ohne_ausgang_und_rohwerte_wie_bisher(self):
        self.assertIn("keinen Ausgang", ma.aussage(1, [], True).text)
        self.assertIn("Rohwerte", ma.aussage(1, self.LAGEN["sendet"], False).text)

    def test_ausgabe_status_nennt_den_zustand(self):
        om = _manager()
        self.addCleanup(om.stop)
        om._enttec_outputs[1] = _Enttec(verbindet=True)
        self.assertEqual([e["zustand"] for e in om.ausgabe_status()], ["verbindet"])
        self.assertIn("verbindet", _monitor_label(om).text)


# ══════════════════════════════════════════════════════════════════════════════
# Die echte Ansicht (ohne Fenster)
# ══════════════════════════════════════════════════════════════════════════════

class _MitAnsicht(unittest.TestCase):

    def setUp(self):
        from src.ui.views import dmx_monitor_view as mv
        self.om = _manager(1, 2)
        self.addCleanup(self.om.stop)
        self.ansicht = mv.DmxMonitorView()
        self.ansicht._timer.stop()
        self.ansicht._state = types.SimpleNamespace(
            universes=self.om.universes, output_manager=self.om,
            get_patched_fixtures=lambda: [])
        self.addCleanup(self.ansicht.deleteLater)

    def _waehle(self, universum):
        combo = self.ansicht._combo_univ
        combo.setCurrentIndex(combo.findData(universum))
        self.ansicht._zeige_stand()

    def _werte(self):
        return list(self.ansicht._grid._values)


# ══════════════════════════════════════════════════════════════════════════════
# (b) Nicht angelegtes Universum
# ══════════════════════════════════════════════════════════════════════════════

class NichtAngelegtesUniversumTest(_MitAnsicht):

    def setUp(self):
        super().setUp()
        self.om.universes[1].set_channel(5, 200)
        self.om._artnet_outputs[1] = _Netz()
        self.om._send_all()

    def test_das_raster_zeigt_nicht_die_werte_des_vorherigen(self):
        self._waehle(1)
        self.assertEqual(self._werte()[4], 200)
        self._waehle(7)
        self.assertEqual(self._werte(), [0] * 512,
                         "sonst stehen unter „Universe 7“ die Werte von Universe 1")

    def test_das_raster_und_die_zeile_sagen_warum(self):
        self._waehle(7)
        self.assertIn("Universe 7", self.ansicht._grid.leer_text())
        self.assertIn("nicht angelegt", self.ansicht._grid.leer_text())
        self.assertIn("nicht angelegt", self.ansicht._lbl_ausgang.text())
        self.assertNotIn("geht raus", self.ansicht._lbl_ausgang.text())

    def test_zurueck_auf_ein_angelegtes_universum_zeigt_es_wieder(self):
        self._waehle(7)
        self._waehle(1)
        self.assertEqual(self.ansicht._grid.leer_text(), "")
        self.assertEqual(self._werte()[4], 200)
        self.assertIn("geht raus", self.ansicht._lbl_ausgang.text())

    def test_angelegt_aber_ohne_ausgang_ist_etwas_anderes(self):
        self._waehle(2)
        self.assertEqual(self.ansicht._grid.leer_text(), "")
        self.assertIn("keinen Ausgang", self.ansicht._lbl_ausgang.text())

    def test_das_raster_laesst_sich_leer_zeichnen(self):
        self._waehle(7)
        bild = self.ansicht._grid.grab()        # darf nicht werfen
        self.assertFalse(bild.isNull())


# ══════════════════════════════════════════════════════════════════════════════
# (c) Sperre je Ausgabeweg
# ══════════════════════════════════════════════════════════════════════════════

class SperreJeAusgabewegTest(_MitAnsicht):
    """Universum 1 geht ueber Enttec UND Art-Net hinaus; auf dem Enttec-Weg
    sperrt der NOT-AUS die Adresse 10 (dort haengt der Laser eines anderen
    Universums) und setzt dessen Aus-Wert 50."""

    def setUp(self):
        super().setUp()
        self.om.universes[1].set_channel(10, 120)
        self.enttec = _Enttec("COM3")
        self.om._enttec_outputs[1] = self.enttec
        self.om._artnet_outputs[1] = _Netz("2.0.0.1")
        self.om._laser_estop_wege = {self.om._weg_enttec(self.enttec): {10: 50}}
        self.om._send_all()

    def test_der_manager_weiss_was_an_jeden_weg_ging(self):
        wege = {w["weg"]: w for w in self.om.gesendete_wege(1)}
        self.assertEqual(sorted(wege), ["Art-Net", "Enttec"])
        self.assertEqual(wege["Enttec"]["daten"][9], 50)
        self.assertEqual(wege["Art-Net"]["daten"][9], 120)
        self.assertEqual(wege["Enttec"]["ziel"], "COM3")
        self.assertEqual(self.enttec.bilder[-1][9], 50, "und genau das ging hinaus")

    def test_das_bild_des_universums_zeigt_die_sperre_nicht(self):
        """Deshalb reicht ``get_display_frame`` hier nicht."""
        self.assertEqual(self.om.get_display_frame(1)[9], 120)

    def test_der_monitor_zeigt_den_gesperrten_weg_wie_gesendet(self):
        self._waehle(1)
        self.assertEqual(self.ansicht._combo_weg.currentText(), "Enttec → COM3")
        self.assertEqual(self._werte()[9], 50)
        self.assertIn("NOT-AUS-Sperre auf diesem Ausgang: 1 Adresse",
                      self.ansicht._lbl_ausgang.text())

    def test_der_andere_weg_zeigt_was_er_sendet(self):
        self._waehle(1)
        combo = self.ansicht._combo_weg
        combo.setCurrentIndex(combo.findText("Art-Net → 2.0.0.1"))
        self.ansicht._zeige_stand()
        self.assertEqual(self._werte()[9], 120)
        self.assertNotIn("NOT-AUS-Sperre", self.ansicht._lbl_ausgang.text())

    def test_die_auswahl_erscheint_nur_bei_mehreren_wegen(self):
        self._waehle(1)
        self.assertFalse(self.ansicht._combo_weg.isHidden())
        self.om._artnet_outputs.pop(1)
        self.om._send_all()
        self.ansicht._zeige_stand()
        self.assertTrue(self.ansicht._combo_weg.isHidden())
        self.assertEqual(self._werte()[9], 50, "der eine Weg wird gezeigt, wie er sendet")

    def test_die_auswahl_ueberlebt_den_naechsten_takt(self):
        self._waehle(1)
        combo = self.ansicht._combo_weg
        combo.setCurrentIndex(1)
        gewaehlt = combo.currentText()
        self.om._send_all()
        self.ansicht._zeige_stand()
        self.assertEqual(combo.currentText(), gewaehlt)

    def test_ohne_sperre_sind_alle_wege_gleich_dem_bild(self):
        self.om._laser_estop_wege = {}
        self.om._send_all()
        for weg in self.om.gesendete_wege(1):
            self.assertEqual(weg["daten"], self.om.get_display_frame(1))

    def test_universum_ohne_ausgang_hat_keine_wege(self):
        self.assertEqual(self.om.gesendete_wege(2), [])

    def test_udmx_ist_ein_eigener_weg_mit_eigener_sperre(self):
        """OUT-68: alle uDMX-Ausgaenge teilen sich einen Ausgabeweg — auch
        dessen Sperre muss der Monitor zeigen koennen."""
        udmx = _Enttec("16c0:05dc@1-4")
        self.om._udmx_outputs[1] = udmx
        self.om._laser_estop_wege = {self.om._weg_udmx(): {10: 77}}
        self.om._send_all()
        wege = {w["weg"]: w for w in self.om.gesendete_wege(1)}
        self.assertEqual(sorted(wege), ["Art-Net", "Enttec", "uDMX"])
        self.assertEqual(wege["uDMX"]["ziel"], "16c0:05dc@1-4")
        self.assertEqual(wege["uDMX"]["daten"][9], 77)
        self.assertEqual(wege["Enttec"]["daten"][9], 120)
        self.assertEqual(udmx.bilder[-1][9], 77, "und genau das ging hinaus")

    def test_der_monitor_bietet_den_udmx_weg_an(self):
        self.om._udmx_outputs[1] = _Enttec("16c0:05dc@1-4")
        self.om._laser_estop_wege = {self.om._weg_udmx(): {10: 77}}
        self.om._send_all()
        self._waehle(1)
        combo = self.ansicht._combo_weg
        stelle = combo.findText("uDMX → 16c0:05dc@1-4")
        self.assertGreaterEqual(stelle, 0, [combo.itemText(i) for i in range(combo.count())])
        combo.setCurrentIndex(stelle)
        self.ansicht._zeige_stand()
        self.assertEqual(self._werte()[9], 77)
        self.assertIn("NOT-AUS-Sperre auf diesem Ausgang: 1 Adresse",
                      self.ansicht._lbl_ausgang.text())

    def test_manager_ohne_init_ueberlebt(self):
        om = OutputManager.__new__(OutputManager)
        self.assertEqual(om.gesendete_wege(1), [])


# ══════════════════════════════════════════════════════════════════════════════
# (d) Rueckfrage vor dem Ersetzen
# ══════════════════════════════════════════════════════════════════════════════

import io                                                        # noqa: E402
import json                                                      # noqa: E402
import shutil                                                    # noqa: E402
import tempfile                                                  # noqa: E402

import src.ui.widgets.output_config as oc                        # noqa: E402


class _Port:
    def __init__(self, device):
        self.device = device
        self.description = "FT232R USB UART"
        self.vid, self.pid = 0x0403, 0x6001


class _FakeOM:
    """Manager-Attrappe mit ``ausgabe_status`` — daran haengt die Rueckfrage."""

    def __init__(self):
        self.laufend: list[dict] = []
        self.rufe: list[tuple] = []
        self._enttec_outputs: dict = {}

    def ausgabe_status(self):
        return [dict(e) for e in self.laufend]

    def add_universe(self, u):
        return object()

    def remove_output(self, u, ausser=None, **_):
        self.rufe.append(("weg", int(u)))

    def add_enttec(self, u, port):
        self.rufe.append(("enttec", int(u), port))

    def add_artnet(self, u, ip="255.255.255.255", out_universe=None):
        self.rufe.append(("artnet", int(u), ip))

    def add_sacn(self, u, ip=None, out_universe=None):
        self.rufe.append(("sacn", int(u), ip))

    def add_udmx(self, u, schluessel=""):
        self.rufe.append(("udmx", int(u), schluessel))


class RueckfrageTest(unittest.TestCase):

    def setUp(self):
        self._dir = tempfile.mkdtemp(prefix="lightos_out75_")
        self.addCleanup(shutil.rmtree, self._dir, True)
        alt_pfad, alt_ports, alt_state = (oc._UNIV_CONFIG_PATH,
                                          oc.serial.tools.list_ports.comports,
                                          oc.get_state)
        oc._UNIV_CONFIG_PATH = os.path.join(self._dir, "universes.json")
        oc.serial.tools.list_ports.comports = lambda: [_Port("COM3")]
        self.om = _FakeOM()
        self.state = types.SimpleNamespace(output_manager=self.om, universes={},
                                           apply_output_config=lambda: None)
        oc.get_state = lambda: self.state
        self.fragen: list[str] = []
        self.antwort = oc.QMessageBox.StandardButton.No
        alt_frage = oc.QMessageBox.question

        def frage(_parent, titel, text, *a, **k):
            self.fragen.append(f"{titel}\n{text}")
            return self.antwort

        oc.QMessageBox.question = staticmethod(frage)

        def zurueck():
            oc.QMessageBox.question = alt_frage
            oc._UNIV_CONFIG_PATH, oc.serial.tools.list_ports.comports = alt_pfad, alt_ports
            oc.get_state = alt_state
        self.addCleanup(zurueck)
        self.dlg = oc.OutputConfigDialog()
        self.addCleanup(self.dlg.deleteLater)

    def _laeuft(self, weg, ziel, universum=1):
        self.om.laufend.append({"universum": universum, "weg": weg, "ziel": ziel,
                                "verbunden": True, "problem": ""})

    def _enttec(self, universum=1):
        self.dlg._combo_port.setCurrentIndex(self.dlg._combo_port.findData("COM3"))
        self.dlg._spin_enttec_univ.setValue(universum)
        self.dlg._connect_enttec()

    def _gespeichert(self):
        if not os.path.exists(oc._UNIV_CONFIG_PATH):
            return []
        with io.open(oc._UNIV_CONFIG_PATH, encoding="utf-8") as f:
            return json.loads(f.read())

    # ── Enttec ──

    def test_laufendes_artnet_wird_nicht_ohne_frage_ersetzt(self):
        self._laeuft("Art-Net", "2.0.0.1")
        self._enttec()
        self.assertEqual(len(self.fragen), 1)
        self.assertIn("Art-Net → 2.0.0.1", self.fragen[0])
        self.assertIn("Enttec → COM3", self.fragen[0])
        self.assertIn("Universe 1", self.fragen[0])

    def test_nein_laesst_alles_wie_es_war(self):
        self._laeuft("Art-Net", "2.0.0.1")
        self._enttec()
        self.assertEqual(self.om.rufe, [], "nichts entfernt, nichts eingerichtet")
        self.assertEqual(self._gespeichert(), [], "nichts gespeichert")
        self.assertIn("Abgebrochen", self.dlg._lbl_enttec_status.text())

    def test_ja_ersetzt(self):
        self._laeuft("Art-Net", "2.0.0.1")
        self.antwort = oc.QMessageBox.StandardButton.Yes
        self._enttec()
        self.assertEqual(self.om.rufe, [("weg", 1), ("enttec", 1, "COM3")])

    def test_dieselbe_ausgabe_noch_einmal_ist_kein_ersetzen(self):
        self._laeuft("Enttec", "COM3")
        self._enttec()
        self.assertEqual(self.fragen, [])
        self.assertEqual(self.om.rufe, [("weg", 1), ("enttec", 1, "COM3")])

    def test_anderer_anschluss_auf_demselben_universum_wird_gefragt(self):
        self._laeuft("Enttec", "COM9")
        self._enttec()
        self.assertEqual(len(self.fragen), 1)

    def test_ausgabe_eines_anderen_universums_zaehlt_nicht(self):
        self._laeuft("Art-Net", "2.0.0.1", universum=2)
        self._enttec(1)
        self.assertEqual(self.fragen, [])

    def test_freies_universum_keine_frage(self):
        self._enttec()
        self.assertEqual(self.fragen, [])
        self.assertEqual(self.om.rufe, [("weg", 1), ("enttec", 1, "COM3")])

    # ── Art-Net und sACN ──

    def test_artnet_uebernehmen_fragt_bei_laufendem_enttec(self):
        self._laeuft("Enttec", "COM3")
        self.dlg._check_artnet.setChecked(True)
        self.dlg._spin_artnet_univ.setValue(1)
        self.dlg._edit_artnet_ip.setText("2.0.0.1")
        self.dlg._apply_artnet()
        self.assertEqual(len(self.fragen), 1)
        self.assertEqual(self.om.rufe, [])
        self.assertIn("Abgebrochen", self.dlg._lbl_artnet_status.text())

    def test_artnet_unveraendert_keine_frage(self):
        self._laeuft("Art-Net", "2.0.0.1")
        self.dlg._check_artnet.setChecked(True)
        self.dlg._spin_artnet_univ.setValue(1)
        self.dlg._edit_artnet_ip.setText("2.0.0.1")
        self.dlg._apply_artnet()
        self.assertEqual(self.fragen, [])
        self.assertIn(("artnet", 1, "2.0.0.1"), self.om.rufe)

    def test_sacn_uebernehmen_fragt_bei_laufendem_artnet(self):
        self._laeuft("Art-Net", "2.0.0.1")
        self.dlg._check_sacn.setChecked(True)
        self.dlg._spin_sacn_univ.setValue(1)
        self.dlg._apply_sacn()
        self.assertEqual(len(self.fragen), 1)
        self.assertEqual(self.om.rufe, [])
        self.assertIn("Abgebrochen", self.dlg._lbl_sacn_status.text())

    def test_sacn_multicast_unveraendert_keine_frage(self):
        self._laeuft("sACN", "")
        self.dlg._check_sacn.setChecked(True)
        self.dlg._check_sacn_multicast.setChecked(True)
        self.dlg._spin_sacn_univ.setValue(1)
        self.dlg._apply_sacn()
        self.assertEqual(self.fragen, [])

    # ── uDMX (OUT-68) ──

    def _udmx(self, schluessel="16c0:05dc@1-4", universum=1):
        self.dlg._combo_udmx.clear()
        self.dlg._combo_udmx.addItem(schluessel, schluessel)
        self.dlg._spin_udmx_univ.setValue(universum)
        self.dlg._connect_udmx()

    def test_udmx_verbinden_fragt_bei_laufendem_enttec(self):
        self._laeuft("Enttec", "COM3")
        self._udmx()
        self.assertEqual(len(self.fragen), 1)
        self.assertIn("Enttec → COM3", self.fragen[0])
        self.assertIn("uDMX → 16c0:05dc@1-4", self.fragen[0])
        self.assertEqual(self.om.rufe, [], "nichts entfernt, nichts eingerichtet")
        self.assertEqual(self._gespeichert(), [])
        self.assertIn("Abgebrochen", self.dlg._lbl_udmx_status.text())

    def test_udmx_ja_ersetzt(self):
        self._laeuft("Enttec", "COM3")
        self.antwort = oc.QMessageBox.StandardButton.Yes
        self._udmx()
        self.assertEqual(self.om.rufe, [("weg", 1), ("udmx", 1, "16c0:05dc@1-4")])

    def test_udmx_unveraendert_keine_frage(self):
        self._laeuft("uDMX", "16c0:05dc@1-4")
        self._udmx()
        self.assertEqual(self.fragen, [])
        self.assertEqual(self.om.rufe, [("weg", 1), ("udmx", 1, "16c0:05dc@1-4")])

    def test_anderer_udmx_adapter_wird_gefragt(self):
        self._laeuft("uDMX", "16c0:05dc@1-5")
        self._udmx()
        self.assertEqual(len(self.fragen), 1)

    def test_enttec_verbinden_fragt_bei_laufendem_udmx(self):
        self._laeuft("uDMX", "16c0:05dc@1-4")
        self._enttec()
        self.assertEqual(len(self.fragen), 1)
        self.assertIn("uDMX → 16c0:05dc@1-4", self.fragen[0])

    # ── Grundlage der Frage ──

    def test_manager_ohne_auskunft_keine_frage(self):
        self.assertEqual(oc._andere_ausgaben(types.SimpleNamespace(), 1, "Enttec", "COM3"), [])

    def test_auskunft_die_wirft_keine_frage(self):
        def kaputt():
            raise RuntimeError("weg")
        om = types.SimpleNamespace(ausgabe_status=kaputt)
        self.assertEqual(oc._andere_ausgaben(om, 1, "Enttec", "COM3"), [])

    def test_vorgabe_der_frage_ist_nein(self):
        import inspect
        quelle = inspect.getsource(oc.OutputConfigDialog._ersetzen_bestaetigt)
        self.assertTrue(quelle.rstrip().endswith(
            "return antwort == QMessageBox.StandardButton.Yes"))
        self.assertIn("QMessageBox.StandardButton.No)", quelle)


if __name__ == "__main__":
    unittest.main()
