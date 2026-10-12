"""OUT-70 — Assistent „Interface einrichten…“, Einsteck-Hinweis, Anzeige.

Offscreen, nur mit gestellten Befunden: kein USB, kein serieller Port, kein
Netz, kein Browser.
"""
from __future__ import annotations

import os
import types
from unittest import mock

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QStatusBar           # noqa: E402

from src.core.dmx import interfaces as ifc                        # noqa: E402
from src.core.dmx import output_manager as om_mod                 # noqa: E402
from src.ui.widgets import interface_assistent as ia              # noqa: E402
from src.ui import interface_hinweis as ih                        # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _roh(vid, pid, produkt="", hersteller="", port="", **kw):
    return ifc.RohGeraet(vid=vid, pid=pid, produkt=produkt,
                         hersteller=hersteller, port=port, **kw)


def _befunde(system="linux", **kw):
    roh = [
        _roh(0x0403, 0x6001, "FT232R USB UART", "FTDI",
             "/dev/ttyUSB0" if system == "linux" else "COM3", ort="1-2"),
        _roh(0x2008, 0x1066, "USBDMX512", "Sun-light", ort="1-3",
             dev_pfad="/dev/bus/usb/001/007"),
        _roh(0x1A86, 0x7523, "USB Serial", "QinHeng",
             "/dev/ttyUSB1" if system == "linux" else "COM4", ort="1-4"),
        _roh(0x0962, 0x2001, "USBDMX2", "Sunlite", ort="1-5"),
    ]
    werte = dict(system=system, zugriff=lambda p: True, belegt=lambda p: [],
                 usb_bibliothek=True)
    werte.update(kw)
    return ifc.erkenne(quellen=(roh, []), **werte)


class _Empfaenger:
    def __init__(self, port):
        self.port, self.bilder = port, []

    def send_dmx(self, data):
        self.bilder.append(bytes(data))

    def is_connected(self):
        return True

    def close(self):
        pass


def _state(laser_universen=(), ausgaben=((1, "/dev/ttyUSB0"),)):
    om = om_mod.OutputManager()
    geraete = {}
    for u, port in ausgaben:
        om.add_universe(u)
        geraete[u] = om._enttec_outputs[u] = _Empfaenger(port)
    fixtures = [types.SimpleNamespace(universe=u, fixture_type="laser")
                for u in laser_universen]
    state = types.SimpleNamespace(output_manager=om,
                                  get_patched_fixtures=lambda: fixtures)
    return state, om, geraete


def _nach_titel(teil, **kw):
    return next(b for b in _befunde(**kw) if teil in b.titel)


def _karte(dlg, teil):
    return next(k for k in dlg.karten if teil in k.befund.titel)


# ── Liste und Aktionen ───────────────────────────────────────────────────────

def test_liste_zeigt_befund_ampel_und_passende_aktionen(app):
    dlg = ia.InterfaceAssistent(befunde=_befunde())
    try:
        assert len(dlg.karten) == 4
        assert dlg.lbl_usb_stand.text() == "4 Geräte gefunden"
        woerter = {k.befund.titel.split(" ")[0]: k.lbl_ampel.text()
                   for k in dlg.karten}
        assert woerter == {"FTDI-Adapter": "●  Typ unklar",
                           "CYL-6602": "●  bereit", "WCH": "●  geplant",
                           "Sunlite": "●  nicht unterstützt"}

        ft = _karte(dlg, "FTDI-Adapter")
        assert "0403:6001 · /dev/ttyUSB0" in ft.lbl_kennung.text()
        assert "Open DMX" in ft.lbl_text.text()
        assert ft.btn_einrichten.text() == (
            "Als Ausgabe für Universe 1 einrichten (Enttec-Pro-kompatibel)")
        ft.spin_universum.setValue(4)
        assert "Universe 4" in ft.btn_einrichten.text()
        assert ft.btn_zugriff is None and ft.btn_treiber is None
        assert ft.hilfe.isHidden()

        cyl = _karte(dlg, "CYL-6602")
        assert cyl.btn_einrichten.text().endswith("einrichten (uDMX)")
        assert "ff5c5c" not in cyl.lbl_ampel.styleSheet()

        for teil in ("WCH", "Sunlite"):
            k = _karte(dlg, teil)
            assert k.btn_einrichten is None and k.spin_universum is None
            assert k.btn_anleitung is not None
        assert _karte(dlg, "Sunlite").btn_zugriff is None
        assert "Art-Net" in _karte(dlg, "Sunlite").lbl_text.text()
    finally:
        dlg.deleteLater()


def test_treiber_fehlt_bietet_unter_linux_die_anleitung_zum_aufklappen(app):
    ohne_port = _roh(0x0403, 0x6001, "FT232R USB UART", "FTDI", ort="1-2")
    b = ifc.bewerte(ohne_port, system="linux", zugriff=lambda p: True,
                    belegt=lambda p: [])
    dlg = ia.InterfaceAssistent(befunde=[b])
    try:
        k = dlg.karten[0]
        assert k.lbl_ampel.text() == "●  Treiber fehlt"
        assert k.btn_einrichten is None and k.hilfe.isHidden()
        k.btn_zugriff.click()
        assert not k.hilfe.isHidden()
        assert k.txt_befehl.toPlainText() == ifc.BEFEHL_DIALOUT
    finally:
        dlg.deleteLater()


def test_leere_liste_erklaert_sich(app):
    dlg = ia.InterfaceAssistent(befunde=[])
    try:
        assert dlg.karten == [] and dlg.lbl_usb_stand.text() == "Nichts gefunden"
        assert "Netzwerk" in dlg._lbl_leer.text()
    finally:
        dlg.deleteLater()


def test_keine_berechtigung_zeigt_befehl_sofort_und_fuehrt_nichts_aus(app):
    befunde = _befunde(zugriff=lambda p: False)
    with mock.patch("subprocess.Popen", side_effect=AssertionError), \
         mock.patch("subprocess.run", side_effect=AssertionError), \
         mock.patch("os.system", side_effect=AssertionError):
        dlg = ia.InterfaceAssistent(befunde=befunde)
        try:
            cyl = _karte(dlg, "CYL-6602")
            assert cyl.lbl_ampel.text() == "●  keine Berechtigung"
            assert not cyl.hilfe.isHidden() and cyl.btn_zugriff is None
            assert "udev" in cyl.txt_befehl.toPlainText()
            assert cyl.txt_befehl.isReadOnly()
            cyl.btn_kopieren.click()
            assert cyl.btn_kopieren.text() == "Kopiert"
            assert cyl.btn_einrichten is None      # erst Recht, dann einrichten
        finally:
            dlg.deleteLater()


def test_windows_oeffnet_nur_die_herstellerseite(app):
    geoeffnet, doku = [], []
    dlg = ia.InterfaceAssistent(befunde=_befunde(system="windows"),
                                oeffne_url=geoeffnet.append,
                                oeffne_doku=doku.append)
    try:
        ft = _karte(dlg, "FTDI-Adapter")
        assert ft.btn_treiber.text() == "Treiber-Seite des Herstellers öffnen"
        assert ft.btn_zugriff is None
        ft.btn_treiber.click()
        _karte(dlg, "WCH").btn_treiber.click()
        assert geoeffnet == [ifc.LINK_FTDI, ifc.LINK_WCH]
        assert _karte(dlg, "Sunlite").btn_treiber is None
        dlg.oeffne_url("file:///etc/passwd")            # nur https
        assert len(geoeffnet) == 2
        ft.btn_anleitung.click()
        assert doku == ["anleitung_ausgabe_einrichten/INTERFACES.md"]
        assert os.path.exists(os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "docs", *doku[0].split("/")))
    finally:
        dlg.deleteLater()


def test_einrichten_laeuft_ueber_den_rueckruf_und_fragt_vor_dem_ersetzen(app):
    state, _om, _g = _state()
    rufe = []

    def einrichten(art, ziel, universum):
        rufe.append((art, ziel, universum))
        return f"Eingerichtet: {ziel} → Universe {universum}"

    dlg = ia.InterfaceAssistent(befunde=_befunde(), state=state,
                                einrichten=einrichten)
    try:
        cyl = _karte(dlg, "CYL-6602")
        assert cyl.spin_universum.value() == 2          # Universe 1 ist belegt
        cyl.btn_einrichten.click()
        assert rufe == [("uDMX", "2008:1066@1-3", 2)]
        assert "Universe 2" in cyl.lbl_ergebnis.text()

        ft = _karte(dlg, "FTDI-Adapter")
        ft.spin_universum.setValue(1)
        fragen = []
        with mock.patch.object(dlg, "_frage",
                               lambda text, ja: fragen.append(text) or False):
            ft.btn_einrichten.click()
        assert len(rufe) == 1 and "Universe 1 gibt schon" in fragen[0]
        with mock.patch.object(dlg, "_frage", lambda text, ja: True):
            ft.btn_einrichten.click()
        assert rufe[-1] == ("Enttec", "/dev/ttyUSB0", 1)
    finally:
        dlg.deleteLater()


# ── Netzwerk ─────────────────────────────────────────────────────────────────

def test_netzwerk_reiter_erklaert_und_zeigt_adressen_nur_an(app):
    karten = [{"name": "enp3s0", "ip": "192.168.1.10",
               "netmask": "255.255.255.0", "broadcast": "192.168.1.255"},
              {"name": "lo", "ip": "127.0.0.1", "netmask": "255.0.0.0",
               "broadcast": None}]
    with mock.patch("socket.socket", side_effect=AssertionError("Netz")):
        dlg = ia.InterfaceAssistent(befunde=[], netzkarten=karten)
    try:
        text = dlg.lbl_netz.text()
        assert text.count(". ") + 1 == 3                # drei Saetze
        for wort in ("Art-Net", "sACN", "LAN-Kabel direkt", "selben Netz",
                     "im Betriebssystem", "ändert nichts"):
            assert wort in text
        assert dlg.netz_zeilen == [("enp3s0", "192.168.1.10", "255.255.255.0")]
        assert "noch nicht" in dlg.lbl_netz_suche.text()
        assert dlg.tabs.tabText(1) == "Netzwerk (Art-Net / sACN)"
        assert not dlg.artnet_gewuenscht
        dlg.btn_artnet.click()
        assert dlg.artnet_gewuenscht
    finally:
        dlg.deleteLater()

    leer = ia.InterfaceAssistent(befunde=[], netzkarten=[])
    try:
        assert leer.netz_zeilen == []
    finally:
        leer.deleteLater()


# ── Testsignal ───────────────────────────────────────────────────────────────

def test_testsignal_ist_bei_laser_gesperrt_mit_erklaerung(app):
    state, om, geraete = _state(laser_universen=(2,),
                                ausgaben=((1, "/dev/a"), (2, "/dev/b")))
    dlg = ia.InterfaceAssistent(befunde=[], state=state)
    try:
        frei, gesperrt = dlg.test_zeilen
        assert frei["knopf"].isEnabled() and not frei["gesperrt"]
        assert not gesperrt["knopf"].isEnabled()
        assert gesperrt["knopf"].text() == "Testsignal gesperrt"
        assert "Laser" in gesperrt["stand"].text()
        with mock.patch.object(dlg, "_frage", side_effect=AssertionError):
            assert "Laser" in dlg.testsignal_senden(2)   # auch am Knopf vorbei
        om._send_all()
        assert geraete[2].bilder[-1] == bytes(512)
        assert om._tick_callbacks == []
    finally:
        dlg.deleteLater()


def test_testsignal_nur_nach_ausdruecklicher_rueckfrage(app):
    state, om, geraete = _state()
    dlg = ia.InterfaceAssistent(befunde=[], state=state)
    try:
        fragen = []
        with mock.patch.object(dlg, "_frage",
                               lambda text, ja: fragen.append(text) or False):
            dlg.test_zeilen[0]["knopf"].click()
        assert "keine Laser" in fragen[0] and "Geräte reagieren" in fragen[0]
        assert om._tick_callbacks == [] and not dlg._laeufe

        with mock.patch.object(dlg, "_frage", lambda text, ja: True):
            assert dlg.testsignal_senden(1) == ""
        assert len(om._tick_callbacks) == 1
        assert not dlg.test_zeilen[0]["knopf"].isEnabled()
        lauf = dlg._laeufe[1]
        lauf._t0 -= 1.0                                 # eine Sekunde spaeter
        om._send_all()
        assert geraete[1].bilder[-1][0] > 100
        assert geraete[1].bilder[-1][1:] == bytes(511)
        # Blackout gilt weiter.
        om.set_blackout(True)
        om._send_all()
        assert geraete[1].bilder[-1] == bytes(512)
        om.set_blackout(False)
        # Schliessen beendet das Signal: Kanal 1 auf 0, kein Callback mehr.
        dlg.reject()
        assert not lauf.laeuft and om._tick_callbacks == []
        om._send_all()
        assert geraete[1].bilder[-1] == bytes(512)
    finally:
        dlg.deleteLater()


def test_ohne_ausgabe_gibt_es_kein_testsignal(app):
    state, _om, _g = _state(ausgaben=())
    dlg = ia.InterfaceAssistent(befunde=[], state=state)
    try:
        assert dlg.test_zeilen == []
    finally:
        dlg.deleteLater()


# ── Ausgabe-Dialog ───────────────────────────────────────────────────────────

def test_ausgabe_dialog_hat_den_knopf_und_richtet_ueber_die_reiter_ein(app):
    from src.ui.widgets import output_config as oc
    dlg = oc.OutputConfigDialog()
    try:
        assert dlg._btn_assistent.text() == "Interface einrichten…"
        assert dlg._tabs.tabText(dlg._artnet_tab_index) == "Art-Net"
        rufe = []
        with mock.patch.object(dlg, "_connect_enttec",
                               lambda: rufe.append(("Enttec",
                                                    dlg._combo_port.currentData(),
                                                    dlg._spin_enttec_univ.value()))), \
             mock.patch.object(dlg, "_connect_udmx",
                               lambda: rufe.append(("uDMX",
                                                    dlg._combo_udmx.currentData(),
                                                    dlg._spin_udmx_univ.value()))), \
             mock.patch.object(oc.serial.tools.list_ports, "comports", lambda: []):
            dlg._assistent_einrichten("Enttec", "/dev/attrappe7", 5)
            dlg._assistent_einrichten("uDMX", "2008:1066@1-3", 6)
            assert "nicht einrichten" in dlg._assistent_einrichten("sACN", "", 1)
        assert rufe == [("Enttec", "/dev/attrappe7", 5),
                        ("uDMX", "2008:1066@1-3", 6)]
    finally:
        dlg.deleteLater()


def test_portliste_nennt_nicht_mehr_jeden_ftdi_enttec_pro():
    from src.ui.widgets import output_config as oc
    P = types.SimpleNamespace
    assert oc._port_kennzeichnung(P(vid=0x0403, pid=0x6001, manufacturer="FTDI",
                                    product="FT232R USB UART")) == (
        "  [FTDI-Adapter, Typ unklar]")
    assert oc._port_kennzeichnung(P(vid=0x0403, pid=0x6001, manufacturer="ENTTEC",
                                    product="DMX USB PRO")) == (
        "  [Enttec DMX USB Pro]")
    assert oc._port_kennzeichnung(P(vid=0x0403, pid=0x6001)) == (
        "  [FTDI-Adapter, Typ unklar]")


# ── Statusleiste ─────────────────────────────────────────────────────────────

class _Label:
    text = style = tip = ""

    def setText(self, t):
        self.text = t

    def setStyleSheet(self, s):
        self.style = s

    def setToolTip(self, t):
        self.tip = t


def _statusbalken(art):
    from src.ui import main_window as mw
    lbl = _Label()
    stub = types.SimpleNamespace(_lbl_enttec=lbl, _state=types.SimpleNamespace())
    stub._update_ausgabe_label = lambda: None
    stub._PORTSUCHE_ALLE_S = mw.MainWindow._PORTSUCHE_ALLE_S
    stub._enttec_port_gesucht = types.MethodType(
        mw.MainWindow._enttec_port_gesucht, stub)
    with mock.patch.object(mw, "find_enttec_port", lambda: "/dev/ttyUSB0"), \
         mock.patch.object(mw, "port_art", lambda port: art):
        mw.MainWindow._check_hardware(stub)
    return lbl


def test_statusleiste_unterscheidet_unklaren_ftdi_nur_ohne_universe():
    lbl = _statusbalken("unklar")
    assert lbl.text == "FTDI-Adapter /dev/ttyUSB0 erkannt (Typ unklar), kein Universe"
    assert "Interface einrichten" in lbl.tip
    assert _statusbalken("pro").text == "Enttec: /dev/ttyUSB0 erkannt, kein Universe"
    assert _statusbalken("").text == "Enttec: /dev/ttyUSB0 erkannt, kein Universe"


# ── Einsteck-Hinweis ─────────────────────────────────────────────────────────

def test_einsteck_hinweis_dezent_wegklickbar_abschaltbar(app):
    leiste = QStatusBar()
    klicks = []
    an = [True]
    ft, cyl = _nach_titel("FTDI-Adapter"), _nach_titel("CYL-6602")
    h = ih.InterfaceHinweis(leiste, lambda: klicks.append(1), aktiv=lambda: an[0])
    try:
        assert h.pruefe([ft]) == "" and not h.sichtbar()     # Ausgangsstand
        text = h.pruefe([ft, cyl])
        assert text.startswith("Neues DMX-Interface erkannt: CYL-6602")
        assert text.endswith("— Einrichten…")
        assert h.sichtbar() and h.knopf.text() == text and h.knopf.isFlat()
        h.zu.click()                                         # wegklicken
        assert not h.sichtbar() and klicks == []
        assert h.pruefe([ft, cyl]) == ""                     # nicht nochmal
        h.pruefe([ft])
        h.pruefe([ft, cyl])                                  # neu eingesteckt
        assert h.sichtbar()
        h.knopf.click()
        assert klicks == [1] and not h.sichtbar()
        # Abgeschaltet: keine Meldung, keine Suche.
        an[0] = False
        h.pruefe([ft])
        assert h.pruefe([ft, cyl]) == "" and not h.sichtbar()
        h.takt()
        assert h._thread is None
    finally:
        leiste.deleteLater()


def test_einsteck_abfrage_sucht_im_hilfsthread_und_nie_bei_kein_usb(app,
                                                                   monkeypatch):
    leiste = QStatusBar()
    alle = [_nach_titel("FTDI-Adapter"), _nach_titel("CYL-6602")]
    try:
        monkeypatch.setenv("LIGHTOS_KEIN_USB", "1")
        h = ih.InterfaceHinweis(leiste, lambda: None)
        with mock.patch.object(ifc, "erkenne", side_effect=AssertionError):
            h.takt()
        assert h._thread is None

        folge = [[alle[0]], [alle[0], alle[1]], [alle[0], alle[1]]]
        h2 = ih.InterfaceHinweis(leiste, lambda: None,
                                 suche=lambda: folge.pop(0))
        for _ in range(3):
            h2.takt()
            h2._thread.join(2)
        assert h2.sichtbar() and "CYL-6602" in h2.text
        assert ih.ABFRAGE_MS >= 3000
    finally:
        leiste.deleteLater()


def test_einsteck_abfrage_fragt_nie_wer_den_port_haelt(monkeypatch):
    """Review: die Abfrage alle 5 s darf nicht jedes Mal ganz ``/proc``
    durchsuchen (``port_belegt_von``) — sie braucht nur „was steckt?“."""
    ft = _roh(0x0403, 0x6001, "FT232R USB UART", "FTDI", "/dev/ttyUSB0",
              ort="1-2")
    gefragt = []
    monkeypatch.delenv("LIGHTOS_KEIN_USB", raising=False)
    monkeypatch.setattr(ifc, "_system", lambda: "linux")
    monkeypatch.setattr(ifc, "lies_sysfs", lambda *a, **k: [ft])
    monkeypatch.setattr(ifc, "lies_seriell", lambda *a, **k: [])
    monkeypatch.setattr(ifc, "_zugriff", lambda p: True)
    monkeypatch.setattr(ifc, "_belegt", lambda p: gefragt.append(p) or [])
    befunde = ih._standard_suche()
    assert [b.geraet.port for b in befunde] == ["/dev/ttyUSB0"]
    assert gefragt == []
