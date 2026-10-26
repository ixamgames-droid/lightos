"""OUT-70 — Befunde aus QA-96 zum Assistenten und zum Testsignal.

Je Befund ein Test, der ohne die Aenderung rot ist:

* S-03 Testsignal-Sperre mit derselben Laser-Erkennung wie NOT-AUS/Blackout
  (``laser.erkennung.ist_laser``, LAS-37);
* S-07 Sperre je AUSGANG, nicht je Universum;
* V-03 Geraet auf Adresse 1 nennen, Nebel/Funken & Co. sperren, Sichtbarkeit,
  alter Wert danach;
* V-06 eine Ersetzen-Frage auf beiden Wegen (Reiter und Assistent);
* V-07 „Jetzt testen“ nach dem Einrichten, „Stopp“ waehrend des Laufs;
* B-02 Kopfzeile sagt, dass der Reiter Testsignal sendet;
* D-09 Ausgabe-Anleitung ohne Reste aus der Zeit vor uDMX und Assistent.

Offscreen, nur Attrappen: kein USB, kein serieller Port, kein Netz.
"""
from __future__ import annotations

import io
import os
import shutil
import tempfile
import types
from unittest import mock

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication                      # noqa: E402

from src.core.dmx import anschluss_auswahl                      # noqa: E402
from src.core.dmx import interfaces as ifc                      # noqa: E402
from src.core.dmx import output_manager as om_mod               # noqa: E402
from src.core.dmx import testsignal                             # noqa: E402
from src.ui.widgets import interface_assistent as ia            # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class _Empfaenger:
    def __init__(self, port="/dev/attrappe0"):
        self.port, self.bilder = port, []

    def send_dmx(self, data):
        self.bilder.append(bytes(data))

    def is_connected(self):
        return True

    def close(self):
        pass


def _om(*universen, enttec=True):
    om = om_mod.OutputManager()
    geraete = {}
    for u in universen:
        om.add_universe(u)
        if enttec:
            geraete[u] = om._enttec_outputs[u] = _Empfaenger(f"/dev/attrappe{u}")
    return om, geraete


def _fx(universe=1, address=1, **kw):
    werte = dict(universe=universe, address=address, fixture_type="dimmer",
                 fixture_name="Dimmer", label="", manufacturer_name="", fid=1,
                 fixture_profile_id=None)
    werte.update(kw)
    return types.SimpleNamespace(**werte)


def _kanal(name, attribute="raw", nr=1):
    return types.SimpleNamespace(name=name, attribute=attribute,
                                 channel_number=nr)


# ── S-03: dieselbe Laser-Erkennung wie NOT-AUS und Blackout ─────────────────

def test_s03_laser_nur_am_kanalnamen_sperrt_das_testsignal():
    """Wie das Eurolite „LED KLS Laser Bar FX Light Set“: Typ ``other``,
    Kanaele „Laser: Red“/„Laser: Green“ als ``raw`` — der Blackout erkannte es,
    das Testsignal nicht."""
    om, _ = _om(1)
    bar = _fx(address=30, fixture_type="other", fixture_name="FX Lichtset")
    kanaele = {id(bar): [_kanal("Dimmer", "intensity", 1),
                         _kanal("Laser: Red", "raw", 2),
                         _kanal("Laser: Green", "raw", 3)]}
    grund = testsignal.sperre_grund(om, 1, [bar],
                                    kanaele_von=lambda f: kanaele[id(f)])
    assert "Laser" in grund
    # Gegenprobe: dieselbe Regel wie Blackout/NOT-AUS (LAS-37).
    from src.core.laser.erkennung import ist_laser
    assert ist_laser(bar, kanaele[id(bar)])


def test_s03_laser_nur_am_geraetenamen_sperrt_auch_im_assistenten(app):
    om, _ = _om(1)
    bar = _fx(address=30, fixture_type="other",
              fixture_name="LED KLS Laser Bar FX Light Set")
    state = types.SimpleNamespace(output_manager=om,
                                  get_patched_fixtures=lambda: [bar])
    dlg = ia.InterfaceAssistent(befunde=[], state=state)
    try:
        zeile = dlg.test_zeilen[0]
        assert not zeile["knopf"].isEnabled() and "Laser" in zeile["stand"].text()
        with mock.patch.object(dlg, "_frage", side_effect=AssertionError):
            assert "Laser" in dlg.testsignal_senden(1)
        assert om._tick_callbacks == []
    finally:
        dlg.deleteLater()


# ── S-07: Laser an DIESEM AUSGANG, nicht nur im Universum ───────────────────

def _artnet(om, u, ext):
    om.add_universe(u)
    om._artnet_outputs[u] = _Empfaenger(f"artnet{u}")
    om._out_universe[u] = ext


def test_s07_anderes_universum_mit_laser_auf_demselben_ausgang_sperrt():
    om = om_mod.OutputManager()
    _artnet(om, 1, 0)                    # Laser-Universum
    _artnet(om, 2, 0)                    # anderes Universum, SELBES Netz-Ziel
    _artnet(om, 3, 5)                    # anderes Ziel
    om.set_laser_adressen({1: frozenset({10})})
    grund = testsignal.sperre_grund(om, 2)
    assert "Universum 1" in grund and "denselben Ausgang" in grund
    assert testsignal.sperre_grund(om, 3) == ""
    assert "Laser" in testsignal.Testsignal(om, 2).start()


def test_s07_laser_auf_geteiltem_ausgang_bricht_einen_laufenden_test_ab():
    om = om_mod.OutputManager()
    _artnet(om, 1, 0)
    _artnet(om, 2, 0)
    zeit = [0.0]
    ts = testsignal.Testsignal(om, 2, uhr=lambda: zeit[0])
    assert ts.start() == ""
    zeit[0] = 1.0
    om._send_all()
    assert om.universes[2].get_channel(1) > 0
    om.set_laser_adressen({1: frozenset({3})})       # Laser im Nachbar-Universum
    zeit[0] = 1.1
    om._send_all()
    assert not ts.laeuft and "Laser" in ts.abbruch_grund


# ── V-03: was auf Adresse 1 liegt, Effektgeraete, Sichtbarkeit, alter Wert ──

def test_v03_nebelgeraet_auf_adresse_1_sperrt_auf_adresse_40_nicht():
    om, _ = _om(1)
    nebel = _fx(address=1, fixture_type="other", fixture_name="Hazer 900")
    kan = lambda f: [_kanal("Ausstoss", "raw", 1), _kanal("Lüfter", "raw", 2)]  # noqa: E731
    grund = testsignal.sperre_grund(om, 1, [nebel], kanaele_von=kan)
    assert "Hazer 900" in grund and "Adresse 1" in grund
    weit = _fx(address=40, fixture_type="other", fixture_name="Hazer 900")
    lampe = _fx(address=1, fixture_type="dimmer", fixture_name="PAR 64")
    assert testsignal.sperre_grund(om, 1, [weit, lampe], kanaele_von=kan) == ""


def test_v03_rueckfrage_nennt_das_geraet_auf_adresse_1_und_den_blackout():
    om, _ = _om(1)
    lampe = _fx(address=1, label="PAR vorne links")
    frage = testsignal.frage_text(om, 1, [lampe], kanaele_von=lambda f: [_kanal("D")])
    assert "„PAR vorne links“" in frage and "Adresse 1" in frage
    assert testsignal.FRAGE in frage
    assert "nicht zu sehen" not in frage
    leer = testsignal.frage_text(om, 1, [])
    assert "kein Gerät" in leer
    om.set_blackout(True)
    assert "BLACKOUT" in testsignal.frage_text(om, 1, [])
    om.set_blackout(False)
    om.set_grand_master(0.0)
    assert "Grand Master" in testsignal.frage_text(om, 1, [])


def test_v03_nach_dem_test_steht_kanal_1_auf_dem_alten_wert():
    om, _ = _om(1)
    om.universes[1].set_channel(1, 77)
    zeit = [0.0]
    ts = testsignal.Testsignal(om, 1, uhr=lambda: zeit[0])
    assert ts.start() == ""
    zeit[0] = 1.0
    om._send_all()
    assert om.universes[1].get_channel(1) != 77
    ts.stopp()
    assert om.universes[1].get_channel(1) == 77
    # auch beim regulaeren Ende
    ts2 = testsignal.Testsignal(om, 1, uhr=lambda: zeit[0])
    ts2.start()
    zeit[0] = 2.0
    om._send_all()
    zeit[0] = 1.0 + testsignal.DAUER_S + 1.5
    om._send_all()
    assert not ts2.laeuft and om.universes[1].get_channel(1) == 77


# ── Sicherheitsinvarianten (unverhandelbar) ─────────────────────────────────

def test_invariante_nie_bei_aktivem_notaus_auch_nicht_ueber_die_wege():
    om, _ = _om(1)
    om._laser_estop_wege = {("enttec", "/dev/x"): {5: 0}}
    assert "NOT-AUS" in testsignal.sperre_grund(om, 1)
    om._laser_estop_wege = {}
    om._laser_estop_aktiv = True
    assert "NOT-AUS" in testsignal.Testsignal(om, 1).start()
    assert om._tick_callbacks == []


def test_invariante_notaus_waehrend_des_laufs_beendet_sofort(app):
    om, geraete = _om(1)
    zeit = [0.0]
    ts = testsignal.Testsignal(om, 1, uhr=lambda: zeit[0])
    ts.start()
    zeit[0] = 1.0
    om._send_all()
    om.set_laser_estop_mask({}, aktiv=True)
    zeit[0] = 1.1
    om._send_all()
    assert not ts.laeuft and "NOT-AUS" in ts.abbruch_grund
    assert om._tick_callbacks == []


# ── V-06: eine Ersetzen-Frage auf beiden Wegen ──────────────────────────────

class _Port:
    def __init__(self, device):
        self.device = device
        self.description = "FT232R USB UART"
        self.manufacturer, self.product = "FTDI", "FT232R USB UART"
        self.vid, self.pid = 0x0403, 0x6001
        self.serial_number = None


class _FakeOM:
    def __init__(self):
        self.laufend: list[dict] = []
        self.rufe: list[tuple] = []
        self._enttec_outputs: dict = {}
        self.universes: dict = {}

    def ausgabe_status(self):
        return [dict(e) for e in self.laufend]

    def add_universe(self, u):
        return object()

    def remove_output(self, u, ausser=None, **_):
        self.rufe.append(("weg", int(u)))

    def add_enttec(self, u, port, **_):
        self.rufe.append(("enttec", int(u), port))


def test_v06_assistent_und_reiter_fragen_dieselbe_eine_frage(app):
    from src.ui.widgets import output_config as oc
    tmp = tempfile.mkdtemp(prefix="lightos_out70_v06_")
    om = _FakeOM()
    om.laufend.append({"universum": 1, "weg": "Art-Net", "ziel": "192.0.2.10",
                       "verbunden": True, "problem": ""})
    state = types.SimpleNamespace(output_manager=om, universes={},
                                  apply_output_config=lambda: None,
                                  get_patched_fixtures=lambda: [])
    fragen = []

    def frage(_parent, titel, text, *a, **k):
        fragen.append(titel)
        return oc.QMessageBox.StandardButton.No

    with mock.patch.object(oc, "_UNIV_CONFIG_PATH",
                           os.path.join(tmp, "universes.json")), \
         mock.patch.object(oc.serial.tools.list_ports, "comports",
                           lambda: [_Port("/dev/ttyUSB0")]), \
         mock.patch.object(oc, "get_state", lambda: state), \
         mock.patch.object(oc.QMessageBox, "question", staticmethod(frage)):
        dlg = oc.OutputConfigDialog()
        befund = ifc.bewerte(ifc.RohGeraet(vid=0x0403, pid=0x6001,
                                           produkt="FT232R USB UART",
                                           hersteller="FTDI", port="/dev/ttyUSB0"),
                             system="linux", zugriff=lambda p: True,
                             belegt=lambda p: [])
        assi = ia.InterfaceAssistent(befunde=[befund], state=state,
                                     einrichten=dlg._assistent_einrichten)
        try:
            karte = assi.karten[0]
            karte.spin_universum.setValue(1)
            with mock.patch.object(assi, "_frage", side_effect=AssertionError(
                    "der Assistent darf keine eigene Ersetzen-Frage stellen")):
                karte.btn_einrichten.click()
            assert fragen == ["Laufende Ausgabe ersetzen?"]
            assert om.rufe == []                   # „Nein“: nichts ersetzt
            assert "Abgebrochen" in karte.lbl_ergebnis.text()
            assert karte.btn_testen.isHidden()     # nichts eingerichtet
        finally:
            assi.deleteLater()
            dlg.deleteLater()
            shutil.rmtree(tmp, True)


# ── V-07: „Jetzt testen“ und „Stopp“ ────────────────────────────────────────

def test_v07_nach_dem_einrichten_jetzt_testen_mit_stopp(app):
    om, _ = _om(enttec=False)
    om.add_universe(1)
    om.universes[1].set_channel(1, 33)
    state = types.SimpleNamespace(output_manager=om,
                                  get_patched_fixtures=lambda: [])

    def einrichten(art, ziel, universum):
        om._enttec_outputs[universum] = _Empfaenger(ziel)
        return f"Eingerichtet: {ziel} → Universum {universum}"

    befund = ifc.bewerte(ifc.RohGeraet(vid=0x0403, pid=0x6001,
                                       produkt="DMX USB PRO", hersteller="ENTTEC",
                                       port="/dev/attrappe9"),
                         system="linux", zugriff=lambda p: True,
                         belegt=lambda p: [])
    dlg = ia.InterfaceAssistent(befunde=[befund], state=state,
                                einrichten=einrichten)
    try:
        karte = dlg.karten[0]
        assert karte.btn_testen.isHidden()
        karte.spin_universum.setValue(1)
        karte.btn_einrichten.click()
        assert not karte.btn_testen.isHidden()
        assert karte.btn_testen.text() == "Jetzt testen"
        fragen = []
        with mock.patch.object(dlg, "_frage",
                               lambda text, ja: fragen.append(text) or True):
            karte.btn_testen.click()
        assert len(fragen) == 1 and testsignal.FRAGE in fragen[0]
        assert dlg.tabs.currentIndex() == dlg._test_index
        zeile = dlg.test_zeilen[0]
        assert zeile["knopf"].text() == "Stopp" and zeile["knopf"].isEnabled()
        lauf = dlg._laeufe[1]
        lauf._t0 -= 1.0
        om._send_all()
        assert om.universes[1].get_channel(1) != 33
        zeile["knopf"].click()                       # Stopp
        assert not lauf.laeuft and om._tick_callbacks == []
        assert om.universes[1].get_channel(1) == 33
        assert zeile["knopf"].text() == "Testsignal senden"
        assert "Gestoppt" in zeile["stand"].text()
        # Schliessen stoppt ebenfalls und stellt den alten Wert her.
        with mock.patch.object(dlg, "_frage", lambda text, ja: True):
            assert dlg.testsignal_senden(1) == ""
        lauf2 = dlg._laeufe[1]
        lauf2._t0 -= 1.0
        om._send_all()
        dlg.reject()
        assert not lauf2.laeuft and om._tick_callbacks == []
        assert om.universes[1].get_channel(1) == 33
    finally:
        dlg.deleteLater()


def test_v07_abgebrochene_rueckfrage_startet_nichts(app):
    om, _ = _om(1)
    state = types.SimpleNamespace(output_manager=om,
                                  get_patched_fixtures=lambda: [])
    dlg = ia.InterfaceAssistent(befunde=[], state=state)
    try:
        with mock.patch.object(dlg, "_frage", lambda text, ja: False):
            assert dlg.jetzt_testen(1) == "abgebrochen"
        assert om._tick_callbacks == [] and not dlg._laeufe
    finally:
        dlg.deleteLater()


# ── B-02: Kopfzeile ─────────────────────────────────────────────────────────

def test_b02_kopfzeile_sagt_dass_der_reiter_testsignal_sendet():
    assert "Nur der Reiter Testsignal sendet — nach Rückfrage" in ia.KOPF_TEXT
    assert "Es wird nichts gesendet" not in ia.KOPF_TEXT


# ── Portliste (Merge mit OUT-73): dieselbe Regel wie find_enttec_port ──────

def test_portliste_nach_merge_kennzeichnet_wie_die_erkennung():
    P = types.SimpleNamespace
    pro = P(device="/dev/ttyUSB1", description="DMX USB PRO", vid=0x0403,
            pid=0x6001, manufacturer="ENTTEC", product="DMX USB PRO")
    unklar = P(device="/dev/ttyUSB2", description="FT232R USB UART", vid=0x0403,
               pid=0x6001, manufacturer="FTDI", product="FT232R USB UART")
    fremd = P(device="/dev/ttyUSB0", description="USB-DMX512 Converter",
              vid=0x0403, pid=0x6001, manufacturer="FTDI",
              product="USB-DMX512 Converter")
    liste = anschluss_auswahl.ordnen([fremd, unklar, pro])
    texte = {a.device: a.text for a in liste}
    assert texte["/dev/ttyUSB1"].endswith("[Enttec DMX USB Pro]")
    assert texte["/dev/ttyUSB2"].endswith("[FTDI-Adapter, Typ unklar]")
    assert "[" not in texte["/dev/ttyUSB0"]
    assert anschluss_auswahl.vorschlag([a for a in liste
                                        if a.device == "/dev/ttyUSB0"]) == ""


# ── D-09: Ausgabe-Anleitung ─────────────────────────────────────────────────

def _lies(*teile):
    with io.open(os.path.join(ROOT, *teile), encoding="utf-8") as f:
        return f.read()


def test_d09_ausgabe_anleitung_ohne_reste_vor_udmx_und_assistent():
    de = _lies("docs", "anleitung_ausgabe_einrichten", "ANLEITUNG.md")
    en = _lies("docs", "anleitung_ausgabe_einrichten", "ANLEITUNG.en.md")
    index = _lies("docs", "ANLEITUNGEN.md")
    assert "die drei Wege frei" not in de and "the three ways freely" not in en
    assert "vier Wege" in de and "four ways" in en
    assert "`[Enttec Pro]`" not in de and "`[Enttec Pro]`" not in en
    for text in (de, en):
        assert "[Enttec DMX USB Pro]" in text
        assert "[FTDI-Adapter, Typ unklar]" in text
        assert "(Typ unklar), kein Universe" in text   # Statusleisten-Zustand
    # uDMX nicht mehr ohne Nummer zwischen „2.“ und „3.“
    assert "## 2b. uDMX-Adapter (USB)" in de and "## 2b. uDMX adapters (USB)" in en
    assert "(#2b-udmx-adapter-usb)" in de and "(#2b-udmx-adapters-usb)" in en
    # Assistent mit eigenem Abschnitt, Testsignal und Bild
    assert "## Assistent „Interface einrichten…“" in de
    for wort in ("Jetzt testen", "Stopp", "Nur der Reiter Testsignal sendet",
                 "Laufende Ausgabe ersetzen?"):
        assert wort in de, wort
    for bild in ("10_assistent.png", "11_testsignal.png"):
        assert f"img/{bild}" in de and f"img/{bild}" in en
        assert os.path.exists(os.path.join(ROOT, "docs", "anleitung_ausgabe_einrichten",
                                           "img", bild))
    assert "Dialog noch ohne diesen Knopf" not in de
    assert "ENTTEC, Art-Net, sACN" not in index and "ENTTEC, uDMX, Art-Net, sACN" in index


def test_sichtkontrolle_eine_testzeile_je_universum_auch_bei_zwei_ausgaengen(app):
    """Sichtkontrolle: Universum 1 ueber Art-Net UND Enttec — eine Zeile, die
    beide Ausgaenge nennt und waehrend des Laufs „Stopp“ zeigt."""
    om, _ = _om(1)
    om._artnet_outputs[1] = _Empfaenger()
    om._artnet_outputs[1].target_ip = "192.0.2.50"
    state = types.SimpleNamespace(output_manager=om,
                                  get_patched_fixtures=lambda: [])
    dlg = ia.InterfaceAssistent(befunde=[], state=state)
    try:
        assert len(dlg.test_zeilen) == 1
        with mock.patch.object(dlg, "_frage", lambda text, ja: True):
            assert dlg.testsignal_senden(1) == ""
        assert dlg.test_zeilen[0]["knopf"].text() == "Stopp"
    finally:
        dlg.reject()
        dlg.deleteLater()
