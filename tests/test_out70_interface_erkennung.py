"""OUT-70 — Interfaces erkennen: Tabelle, passive Erkennung, Befunde.

Nur Attrappen und gestellte Systeminfos: kein echtes USB, kein serieller Port,
kein Netz (``LIGHTOS_KEIN_USB`` aus der conftest schaltet die echte Erkennung
zusaetzlich ab).
"""
from __future__ import annotations

import os
import re
import types
from unittest import mock

import pytest

from src.core.dmx import enttec_pro, interfaces as ifc, testsignal
from src.core.dmx import output_manager as om_mod
import _out68_usb_attrappe as fake

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _roh(vid, pid, produkt="", hersteller="", port="", **kw):
    return ifc.RohGeraet(vid=vid, pid=pid, produkt=produkt,
                         hersteller=hersteller, port=port, **kw)


def _frei(**kw):
    """Bewertung ohne Systemzugriff: Zugriff erlaubt, niemand haelt den Port."""
    werte = dict(system="linux", zugriff=lambda p: True, belegt=lambda p: [])
    werte.update(kw)
    return werte


FT232 = _roh(0x0403, 0x6001, "FT232R USB UART", "FTDI", "/dev/ttyUSB0",
             seriennummer="A50285BI", ort="1-2")
CYL = _roh(0x2008, 0x1066, "USBDMX512", "Sun-light", ort="1-3",
           dev_pfad="/dev/bus/usb/001/007")
NANO = _roh(0x1A86, 0x7523, "USB Serial", "QinHeng", "/dev/ttyUSB1", ort="1-4")
SUNLITE = _roh(0x0962, 0x2001, "USBDMX2", "Sunlite", ort="1-5")


# ── Tabelle ──────────────────────────────────────────────────────────────────

def test_jede_zeile_ist_vollstaendig():
    from src.ui.widgets.output_config import AUSGABE_TYPEN
    assert len(ifc.EINTRAEGE) >= 25
    for e in ifc.EINTRAEGE:
        fam = ifc.FAMILIEN[e.familie]                 # Familie gibt es
        assert e.name.strip() and fam.name.strip(), e
        assert fam.status in (ifc.STATUS_UNTERSTUETZT, ifc.STATUS_GEPLANT,
                              ifc.STATUS_NICHT)
        assert fam.linux.strip() and fam.naechster_schritt.strip(), fam
        assert (e.windows_treiber or fam.windows_treiber).strip(), e
        assert e.geprueft in (ifc.PRUEF_GERAET, ifc.PRUEF_SPEZ,
                              ifc.PRUEF_GEPLANT, ifc.PRUEF_NICHT)
        if fam.status == ifc.STATUS_UNTERSTUETZT:
            assert fam.ausgabe_art in AUSGABE_TYPEN, fam
            assert fam.status_text() == f"unterstützt: {fam.ausgabe_art}"
        else:
            assert not fam.ausgabe_art
            assert e.geprueft != ifc.PRUEF_GERAET
        if e.vid is None:
            assert e.hat_merkmal and e.vermutet, e      # reine Namens-Zeile


def test_links_sind_https_und_nur_dort_wo_ein_treiber_zu_holen_ist():
    links = {l for e in ifc.EINTRAEGE for l in (e.windows_link,) if l}
    links |= {f.windows_link for f in ifc.FAMILIEN.values() if f.windows_link}
    assert links
    for link in links:
        assert link.startswith("https://") and " " not in link, link
    for fam in ifc.FAMILIEN.values():
        if fam.status == ifc.STATUS_NICHT:
            assert not fam.windows_link and not fam.linux_befehl, fam


def test_keine_doppelte_kennung_ohne_unterscheidungsmerkmal():
    """Mehrere Zeilen mit derselben Kennung brauchen ein Text-Merkmal; genau
    eine darf der Rueckfall ohne Merkmal sein — und der steht zuletzt."""
    gruppen: dict = {}
    for i, e in enumerate(ifc.EINTRAEGE):
        if e.vid is not None:
            gruppen.setdefault((e.vid, e.pid), []).append((i, e))
    assert len(gruppen[(0x0403, 0x6001)]) >= 5
    for kennung, zeilen in gruppen.items():
        ohne = [i for i, e in zeilen if not e.hat_merkmal]
        assert len(ohne) <= 1, kennung
        if ohne and len(zeilen) > 1:
            assert ohne[0] == max(i for i, _ in zeilen), kennung
    # Wildcard-Zeilen (beliebige PID) duerfen keine genaue Zeile verdecken.
    for e in ifc.EINTRAEGE:
        if e.vid is not None and e.pid is None:
            assert not [k for k in gruppen if k[0] == e.vid and k[1] is not None]


def test_befehle_fuehren_nichts_aus_und_stehen_nur_als_text_da():
    quelle = open(ifc.__file__, encoding="utf-8").read()
    for wort in ("subprocess", "os.system", "Popen", "webbrowser"):
        assert wort not in quelle
    assert ifc.BEFEHL_UDMX.splitlines()[0].startswith("sudo cp packaging/linux/")
    assert os.path.exists(os.path.join(
        WURZEL, "packaging", "linux", "60-lightos-udmx.rules"))


# ── Zuordnung je Familie ─────────────────────────────────────────────────────

@pytest.mark.parametrize("vid,pid,hersteller,produkt,familie,namensteil", [
    (0x0403, 0x6001, "ENTTEC", "DMX USB PRO", "pro", "Enttec DMX USB Pro"),
    (0x0403, 0x6001, "ENTTEC", "DMX USB PRO Mk2", "pro", "Mk2"),
    (0x0403, 0x6001, "DMXking", "ultraDMX Pro", "pro", "DMXking"),
    (0x0403, 0x6001, "FTDI", "FT232R USB UART", "ftdi_unklar", "FTDI-Adapter"),
    (0x0403, 0x6001, "FTDI", "USB <-> Serial", "ftdi_unklar", "FTDI-Adapter"),
    (0x0403, 0x6001, "ENTTEC", "Open DMX", "ftdi_unklar", "FTDI-Adapter"),
    (0x0403, 0x6001, "", "", "ftdi_unklar", "FTDI-Adapter"),
    (0x0403, 0x6001, "", "USB-DMX512 CONVERTER", "nische", "Vince"),
    (0x0403, 0x6015, "FTDI", "FT230X", "ftdi_sonstig", "FT230X"),
    (0x0403, 0xC850, "", "", "nische", "DMX4ALL"),
    (0x04D8, 0xFA63, "Eurolite", "Eurolite DMX512 Pro", "eurolite_pro", "Eurolite"),
    (0x1A86, 0x7523, "", "USB Serial", "selbstbau", "CH340"),
    (0x10C4, 0xEA60, "Silicon Labs", "CP2102", "selbstbau", "CP210x"),
    (0x2341, 0x0043, "Arduino", "Uno", "selbstbau", "Arduino"),
    (0x2A03, 0x0043, "", "", "selbstbau", "Arduino"),
    (0x303A, 0x1001, "Espressif", "", "selbstbau", "ESP32"),
    (0x2008, 0x1066, "", "", "udmx", "CYL-6602"),
    (0x16C0, 0x05DC, "www.anyma.ch", "uDMX", "udmx", "Anyma"),
    (0x03EB, 0x8888, "AVLdiy.cn", "D512", "udmx_geplant", "AVLdiy"),
    (0x10CF, 0x8062, "", "", "nische", "Velleman"),
    (0x16C0, 0x088B, "", "", "hid", "FX5"),
    (0x16D0, 0x0830, "", "", "hid", "Nodle"),
    (0x0962, 0x2001, "", "", "proprietaer", "Sunlite"),
    (0x1234, 0x0001, "Nicolaudie", "SIUDI-10", "proprietaer", "Nicolaudie"),
    (0x1234, 0x0002, "ADJ", "myDMX 3.0", "proprietaer", "myDMX"),
    (0x1234, 0x0003, "Chauvet", "Xpress 512", "proprietaer", "Xpress"),
])
def test_zuordnung_je_familie(vid, pid, hersteller, produkt, familie, namensteil):
    e = ifc.ordne_ein(vid, pid, hersteller, produkt)
    assert e is not None and e.familie == familie
    assert namensteil in e.name


def test_geteilte_kennung_ohne_passenden_namen_bleibt_unbekannt():
    """16c0:05dc tragen viele Bastelgeraete — nur Hersteller UND Produkt
    machen daraus ein uDMX."""
    assert ifc.ordne_ein(0x16C0, 0x05DC, "", "") is None
    assert ifc.ordne_ein(0x16C0, 0x05DC, "www.anyma.ch", "USBasp") is None
    assert ifc.ordne_ein(0x04D8, 0xFA63, "Microchip", "CDC") is None
    assert ifc.ordne_ein(0x046D, 0xC077, "Logitech", "Mouse") is None


# ── Befunde ──────────────────────────────────────────────────────────────────

def test_befund_ft232_typ_unklar_laesst_sich_trotzdem_einrichten():
    b = ifc.bewerte(FT232, **_frei())
    assert b.code == ifc.B_TYP_UNKLAR and b.ampel == ifc.AMPEL_GELB
    assert b.wort == "Typ unklar"
    assert "Open DMX" in b.text and "Enttec" in b.text
    assert (b.einrichten_als, b.einrichten_ziel) == ("Enttec", "/dev/ttyUSB0")
    assert b.befehl == ifc.BEFEHL_DIALOUT and b.link == ""


def test_befund_ft232_schon_eingerichtet():
    b = ifc.bewerte(FT232, **_frei(eingerichtet={"/dev/ttyUSB0": 3},
                                   belegt=lambda p: [(1, "lightos")]))
    assert b.code == ifc.B_EINGERICHTET and b.universum == 3
    assert b.ampel == ifc.AMPEL_GRUEN and "Universe 3" in b.text


def test_befund_cyl_bereit_und_schluessel_passt_zum_udmx_treiber():
    b = ifc.bewerte(CYL, **_frei(usb_bibliothek=True))
    assert b.code == ifc.B_BEREIT and b.ampel == ifc.AMPEL_GRUEN
    assert (b.einrichten_als, b.einrichten_ziel) == ("uDMX", "2008:1066@1-3")
    from src.core.dmx import udmx
    assert udmx.schluessel_lesen(b.einrichten_ziel)[:2] == (0x2008, 0x1066)
    mit_nr = ifc.bewerte(ifc.replace(CYL, seriennummer="X9"), **_frei())
    assert mit_nr.einrichten_ziel == "2008:1066#X9"


def test_befund_keine_berechtigung_treiber_belegt_bibliothek():
    b = ifc.bewerte(CYL, **_frei(zugriff=lambda p: False))
    assert b.code == ifc.B_KEINE_BERECHTIGUNG and b.wort == "keine Berechtigung"
    assert "udev" in b.befehl and b.befehl == ifc.BEFEHL_UDMX

    b = ifc.bewerte(FT232, **_frei(zugriff=lambda p: False))
    assert b.code == ifc.B_KEINE_BERECHTIGUNG and "dialout" in b.befehl

    b = ifc.bewerte(FT232, **_frei(belegt=lambda p: [(4711, "qlcplus")]))
    assert b.code == ifc.B_BELEGT and "qlcplus" in b.text
    assert b.wort == "belegt von anderem Programm"

    b = ifc.bewerte(CYL, **_frei(usb_bibliothek=False))
    assert b.code == ifc.B_BIBLIOTHEK_FEHLT and "pyusb" in b.text

    ohne_port = ifc.replace(NANO, port="")
    b = ifc.bewerte(ohne_port, **_frei(system="windows"))
    assert b.code == ifc.B_TREIBER_FEHLT and b.wort == "Treiber fehlt"
    assert b.link == ifc.LINK_WCH and b.befehl == ""
    b = ifc.bewerte(ohne_port, **_frei())
    assert b.code == ifc.B_TREIBER_FEHLT and "brltty" in b.text and not b.link


def test_befund_geplant_nicht_unterstuetzt_unbekannt():
    b = ifc.bewerte(NANO, **_frei())
    assert b.code == ifc.B_GEPLANT and b.ampel == ifc.AMPEL_BLAU
    assert not b.einrichten_als
    b = ifc.bewerte(SUNLITE, **_frei())
    assert b.code == ifc.B_NICHT_UNTERSTUETZT and b.ampel == ifc.AMPEL_ROT
    assert "Art-Net" in b.text and not b.einrichten_als and not b.link
    b = ifc.bewerte(_roh(0x067B, 0x2303, "USB-Serial", port="/dev/ttyUSB5"),
                    **_frei())
    assert b.code == ifc.B_UNBEKANNT and not b.bekannt and not b.einrichten_als


def test_windows_nennt_link_statt_befehl():
    b = ifc.bewerte(ifc.replace(FT232, port="COM3"), **_frei(system="windows"))
    assert b.link == ifc.LINK_FTDI and b.befehl == ""
    assert b.einrichten_ziel == "COM3"
    b = ifc.bewerte(CYL, **_frei(system="windows"))
    assert b.link == ifc.LINK_WINUSB and "WinUSB" in b.text


# ── Quellen: nur lesen ───────────────────────────────────────────────────────

def _sysfs(tmp_path, name, vid, pid, produkt="", hersteller="", serie="",
           klasse="00", tty="", treiber=""):
    d = tmp_path / name
    d.mkdir()
    for datei, wert in (("idVendor", vid), ("idProduct", pid),
                        ("product", produkt), ("manufacturer", hersteller),
                        ("serial", serie), ("bDeviceClass", klasse),
                        ("busnum", "1"), ("devnum", "7")):
        if wert:
            (d / datei).write_text(wert + "\n", encoding="utf-8")
    s = tmp_path / f"{name}:1.0"
    s.mkdir()
    if tty:
        (s / tty).mkdir()
    if treiber:
        ziel = tmp_path / "_treiber" / treiber
        ziel.mkdir(parents=True, exist_ok=True)
        os.symlink(ziel, s / "driver")


def test_sysfs_wird_gelesen_hubs_bleiben_draussen(tmp_path):
    _sysfs(tmp_path, "1-2", "0403", "6001", "FT232R USB UART", "FTDI",
           "A50285BI", tty="ttyUSB0", treiber="ftdi_sio")
    _sysfs(tmp_path, "1-3", "2008", "1066", "USBDMX512", "Sun-light")
    _sysfs(tmp_path, "1-1", "1d6b", "0002", "Hub", klasse="09")
    (tmp_path / "usb1").mkdir()
    geraete = ifc.lies_sysfs(str(tmp_path))
    assert [g.kennung for g in geraete] == ["0403:6001", "2008:1066"]
    ft = geraete[0]
    assert (ft.port, ft.ort, ft.treiber) == ("/dev/ttyUSB0", "1-2", ("ftdi_sio",))
    assert ft.dev_pfad == "/dev/bus/usb/001/007"
    assert geraete[1].port == "" and geraete[1].produkt == "USBDMX512"
    assert ifc.lies_sysfs(str(tmp_path / "gibt-es-nicht")) == []


def test_kein_zugriff_auf_unbekannte_geraete():
    """★ Die Attrappe zaehlt: ein fremdes Geraet wird weder nach Texten gefragt
    noch geoeffnet; an KEIN Geraet geht ein Transfer."""
    maus = fake.Geraet(vid=0x046D, pid=0xC077, hersteller="Logitech",
                       produkt="Mouse", serie="M1")
    drucker = fake.Geraet(vid=0x16C0, pid=0x0483, hersteller="x", produkt="y")
    cyl = fake.Geraet(hersteller="Sun-light", produkt="USBDMX512", ports=(3,))
    geraete = ifc.lies_pyusb(fake.usb(maus, drucker, cyl))
    assert [g.kennung for g in geraete] == ["2008:1066"]
    assert geraete[0].ort == "1-3" and geraete[0].produkt == "USBDMX512"
    assert maus.text_zugriffe == 0 and drucker.text_zugriffe == 0
    for g in (maus, drucker, cyl):
        assert g.transfers == [] and g.freigegeben == 0
    # Auch die Bewertung fasst nichts an.
    befunde = ifc.erkenne(quellen=(geraete, []), **_frei())
    assert [b.code for b in befunde] == [ifc.B_BEREIT]
    assert cyl.transfers == [] and cyl.text_zugriffe == 2   # Hersteller + Produkt


def test_serielle_liste_oeffnet_keinen_port():
    class Port:
        def __init__(self, device, vid, pid, product="", location=""):
            self.device, self.vid, self.pid = device, vid, pid
            self.product, self.manufacturer = product, ""
            self.serial_number, self.location = "", location

    ports = [Port("/dev/ttyS0", None, None),
             Port("/dev/ttyUSB0", 0x0403, 0x6001, "FT232R USB UART", "1-2:1.0"),
             Port("/dev/ttyUSB7", 0x067B, 0x2303, "PL2303")]
    with mock.patch("serial.Serial", side_effect=AssertionError("Port geöffnet")), \
         mock.patch("builtins.open", side_effect=AssertionError("Datei geöffnet")):
        roh = ifc.lies_seriell(lambda: ports)
        befunde = ifc.erkenne(quellen=([], roh), **_frei())
    assert [g.port for g in roh] == ["/dev/ttyUSB0", "/dev/ttyUSB7"]
    assert roh[0].ort == "1-2"
    assert [b.code for b in befunde] == [ifc.B_TYP_UNKLAR, ifc.B_UNBEKANNT]


def test_usb_und_portliste_werden_zusammengelegt():
    usb = [ifc.replace(FT232, port=""), CYL,
           _roh(0x046D, 0xC077, "Mouse", ort="1-9")]
    seriell = [_roh(0x0403, 0x6001, port="/dev/ttyUSB0", ort="1-2")]
    befunde = ifc.erkenne(quellen=(usb, seriell), **_frei())
    assert [(b.geraet.kennung, b.geraet.port) for b in befunde] == [
        ("0403:6001", "/dev/ttyUSB0"), ("2008:1066", "")]   # Maus fehlt
    assert befunde[0].geraet.produkt == "FT232R USB UART"


def test_abgeschaltet_per_umgebung(monkeypatch):
    monkeypatch.setenv("LIGHTOS_KEIN_USB", "1")
    with mock.patch.object(ifc, "lies_sysfs", side_effect=AssertionError), \
         mock.patch.object(ifc, "lies_seriell", side_effect=AssertionError):
        assert ifc.erkenne() == []


# ── Bestand: find_enttec_port ────────────────────────────────────────────────

class _Port:
    def __init__(self, device, vid=0x0403, pid=0x6001, product="",
                 manufacturer=""):
        self.device, self.vid, self.pid = device, vid, pid
        self.product, self.manufacturer = product, manufacturer


def _ports(*ports):
    return mock.patch.object(enttec_pro.serial.tools.list_ports, "comports",
                             lambda: list(ports))


def test_ft232_bestand_wird_weiter_gefunden():
    """★ Der vorhandene Adapter: FT232 mit 0403:6001, laeuft ueber den
    Enttec-Weg. Er muss gefunden werden wie bisher — auch ganz ohne Texte
    (aeltere pyserial-Attrappen, Windows ohne Produkttext)."""
    with _ports(_Port("/dev/ttyUSB0", product="FT232R USB UART",
                      manufacturer="FTDI")):
        assert enttec_pro.find_enttec_port() == "/dev/ttyUSB0"
        assert enttec_pro.pro_kandidaten() == [("/dev/ttyUSB0", False)]
        assert enttec_pro.port_art("/dev/ttyUSB0") == "unklar"

    class Karg:                     # nur device/vid/pid, wie in Bestandstests
        device, vid, pid = "COM7", 0x0403, 0x6001
    with _ports(Karg()):
        assert enttec_pro.find_enttec_port() == "COM7"


def test_ausgewiesener_pro_gewinnt_vor_unklarem_ftdi():
    with _ports(_Port("/dev/ttyUSB0", product="FT232R USB UART"),
                _Port("/dev/ttyUSB1", product="DMX USB PRO",
                      manufacturer="ENTTEC")):
        assert enttec_pro.find_enttec_port() == "/dev/ttyUSB1"
        assert enttec_pro.port_art("/dev/ttyUSB1") == "pro"
        assert enttec_pro.port_art("/dev/ttyUSB0") == "unklar"
        assert enttec_pro.port_art("/dev/ttyUSB9") == ""


def test_nicht_jedes_0403_6001_ist_ein_enttec():
    """Ein Geraet, das sich als etwas anderes ausweist, wird nie genommen."""
    with _ports(_Port("/dev/ttyUSB0", product="USB-DMX512 CONVERTER"),
                _Port("/dev/ttyUSB3", vid=0x1A86, pid=0x7523)):
        assert enttec_pro.find_enttec_port() is None
        assert enttec_pro.pro_kandidaten() == []


# ── Einsteck-Waechter ────────────────────────────────────────────────────────

def test_einsteck_waechter_meldet_nur_neue_bekannte():
    w = ifc.EinsteckWaechter()
    b_ft = ifc.bewerte(FT232, **_frei())
    b_cyl = ifc.bewerte(CYL, **_frei())
    b_fremd = ifc.bewerte(_roh(0x067B, 0x2303, port="/dev/ttyUSB5"), **_frei())
    assert w.neue([b_ft]) == []                       # Ausgangsstand
    assert w.neue([b_ft]) == []
    assert w.neue([b_ft, b_fremd]) == []              # unbekannt: keine Meldung
    neu = w.neue([b_ft, b_cyl])
    assert neu == [b_cyl]
    assert ifc.hinweis_text(neu) == (
        "Neues DMX-Interface erkannt: CYL-6602 „USB-DMX512“ "
        "(Sun-light USBDMX512) — Einrichten…")
    assert w.neue([b_ft, b_cyl]) == []
    assert w.neue([b_ft]) == [] and w.neue([b_ft, b_cyl]) == [b_cyl]
    assert "und 1 weitere" in ifc.hinweis_text([b_ft, b_cyl])
    assert ifc.hinweis_text([]) == ""


# ── Diagnose ─────────────────────────────────────────────────────────────────

def test_diagnose_ohne_seriennummern():
    befunde = ifc.erkenne(quellen=([FT232, CYL], []), **_frei())
    zeilen = ifc.diagnose_zeilen(befunde)
    text = "\n".join(zeilen)
    assert "A50285BI" not in text and "A5…(8 Zeichen)" in text
    assert "0403:6001" in text and "Befund: Typ unklar" in text
    assert "2008:1066" in text and "Befund: bereit" in text
    assert ifc.maskiere("") == "" and ifc.maskiere("X") == "X…(1 Zeichen)"


def test_diagnosepaket_hat_abschnitt_dmx_interfaces(monkeypatch):
    from src.core import diagnose_log
    befunde = ifc.erkenne(quellen=([FT232], []), **_frei())
    monkeypatch.setattr(ifc, "erkenne", lambda **kw: befunde)
    text = diagnose_log.systeminfo_text("9.9.9")
    assert "DMX-Interfaces:" in text
    assert "0403:6001" in text and "A50285BI" not in text
    monkeypatch.setattr(ifc, "erkenne", lambda **kw: [])
    assert diagnose_log.interface_infos() == [
        "Erkennung abgeschaltet (LIGHTOS_KEIN_USB)"]
    monkeypatch.delenv("LIGHTOS_KEIN_USB", raising=False)
    assert diagnose_log.interface_infos() == ["keine erkannt"]


# ── Doku gleicht der Tabelle ─────────────────────────────────────────────────

def _doku() -> str:
    with open(os.path.join(WURZEL, ifc.DOKU_DATEI), encoding="utf-8") as f:
        return f.read()


def test_doku_tabelle_stimmt_mit_der_tabelle_ueberein():
    text = _doku()
    assert ifc.DOKU_ANFANG in text and ifc.DOKU_ENDE in text
    block = text.split(ifc.DOKU_ANFANG)[1].split(ifc.DOKU_ENDE)[0].strip()
    assert block == ifc.doku_tabelle().strip(), (
        "docs-Tabelle weicht ab — neu erzeugen: "
        "python -m src.core.dmx.interfaces")


def test_am_geraet_getestet_steht_nur_bei_zwei_geraeten():
    zeilen = [z for z in ifc.doku_tabelle().splitlines()
              if ifc.PRUEF_GERAET in z]
    assert len(zeilen) == 2
    assert any("FT232" in z and "Linux" in z for z in zeilen)
    assert any("CYL-6602" in z and "Ausgang mit Gerät noch offen" in z
               for z in zeilen)
    # Im Fliesstext der Seite darf das Wort keinem weiteren Geraet gelten.
    rest = _doku().split(ifc.DOKU_ENDE)[1] + _doku().split(ifc.DOKU_ANFANG)[0]
    for absatz in re.split(r"\n\s*\n", rest):
        if ifc.PRUEF_GERAET in absatz:
            assert "FT232" in absatz or "CYL-6602" in absatz or "bedeutet" in absatz


def test_doku_nennt_lan_kabel_direkt_am_pc_und_alle_links():
    text = _doku()
    assert "LAN-Kabel direkt am PC" in text
    assert "im Betriebssystem" in text
    for link in (ifc.LINK_FTDI, ifc.LINK_WCH, ifc.LINK_SILABS, ifc.LINK_WINUSB):
        assert link in text


# ── Testsignal ───────────────────────────────────────────────────────────────

class _Empfaenger:
    port = "/dev/attrappe"

    def __init__(self):
        self.bilder = []

    def send_dmx(self, data):
        self.bilder.append(bytes(data))

    def is_connected(self):
        return True

    def close(self):
        pass


def _manager():
    om = om_mod.OutputManager()
    om.add_universe(1)
    dev = _Empfaenger()
    om._enttec_outputs[1] = dev
    return om, dev


def test_testsignal_laeuft_ueber_den_normalen_weg_und_endet_auf_null():
    om, dev = _manager()
    zeit = [100.0]
    ts = testsignal.Testsignal(om, 1, uhr=lambda: zeit[0])
    assert ts.start() == ""
    werte = []
    for schritt in range(0, 50):
        zeit[0] = 100.0 + schritt * 0.1
        om._send_all()
        werte.append(dev.bilder[-1][0])
    assert max(werte) >= 240 and werte[0] == 0
    assert werte[1] < werte[5] < werte[12]            # langsam hoch
    assert all(b[1:] == bytes(511) for b in dev.bilder)   # nur Kanal 1
    zeit[0] = 105.01
    om._send_all()
    assert not ts.laeuft and dev.bilder[-1] == bytes(512)
    assert ts._tick not in om._tick_callbacks
    zeit[0] = 106.0
    om._send_all()
    assert dev.bilder[-1] == bytes(512)


def test_testsignal_blackout_gewinnt():
    om, dev = _manager()
    zeit = [0.0]
    ts = testsignal.Testsignal(om, 1, uhr=lambda: zeit[0])
    ts.start()
    zeit[0] = 1.0
    om._send_all()
    assert dev.bilder[-1][0] > 150
    om.set_blackout(True)
    zeit[0] = 1.1
    om._send_all()
    assert dev.bilder[-1] == bytes(512)
    ts.stopp()
    ts.stopp()                                          # mehrfach erlaubt


def test_testsignal_gesperrt_bei_laser_im_universum():
    om, dev = _manager()
    om.set_laser_adressen({1: frozenset({10, 11})})
    ts = testsignal.Testsignal(om, 1)
    grund = ts.start()
    assert "Laser" in grund and "Universe 1" in grund and not ts.laeuft
    om._send_all()
    assert dev.bilder[-1] == bytes(512) and ts._tick not in om._tick_callbacks
    # Laser in einem ANDEREN Universum sperrt dieses nicht.
    om.set_laser_adressen({2: frozenset({1})})
    assert testsignal.sperre_grund(om, 1) == ""
    # Gepatchter Laser ohne Maske (Plan noch nicht gebaut) sperrt ebenfalls.
    laser = types.SimpleNamespace(universe=1, fixture_type="laser")
    lampe = types.SimpleNamespace(universe=1, fixture_type="par")
    assert "Laser" in testsignal.sperre_grund(om, 1, [lampe, laser])
    assert testsignal.sperre_grund(om, 1, [lampe]) == ""
    assert "nicht angelegt" in testsignal.sperre_grund(om, 7)


def test_testsignal_bricht_ab_wenn_laser_oder_notaus_dazukommt():
    om, dev = _manager()
    zeit = [0.0]
    ts = testsignal.Testsignal(om, 1, uhr=lambda: zeit[0])
    ts.start()
    zeit[0] = 1.0
    om._send_all()
    assert dev.bilder[-1][0] > 0
    om.set_laser_adressen({1: frozenset({5})})
    zeit[0] = 1.1
    om._send_all()
    assert not ts.laeuft and "Laser" in ts.abbruch_grund
    assert dev.bilder[-1] == bytes(512)

    om2, _dev2 = _manager()
    om2._laser_estop_aktiv = True
    assert "NOT-AUS" in testsignal.Testsignal(om2, 1).start()
