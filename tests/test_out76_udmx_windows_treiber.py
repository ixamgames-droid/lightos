"""OUT-76: uDMX unter Windows — fehlenden Treiber erkennen, erklaeren, verlinken.

**Der Befund (Sitzung A, 12.10.2026).** uDMX-Adapter gelten als unterstuetzt,
unter Windows fehlt ihnen aber ein Treiber, den weder Windows noch LightOS
mitbringt. Die Adapter-Liste zeigte einen angesteckten Adapter trotzdem, als
waere alles in Ordnung; erst nach „Verbinden“ stand da ein einzelner Satz. Und:

* pyusb meldet den fehlenden Treiber als ``NotImplementedError`` — LightOS
  ordnete das als „nimmt keine Daten an — Kabel und Adapter prüfen“ ein.
* Im LightOS aus dem Installationspaket hiess der Rat „pip install pyusb“.

**Regel des Projektinhabers:** Treiber NIE mitliefern oder installieren — nur
erkennen, erklaeren und verlinken. Der erste Block unten haelt fest, dass die
Abfrage nur liest.

Es wird an kein Geraet gesendet; USB und Windows-Abfrage sind Attrappen (bis
auf EINEN Lese-Test der echten Abfrage, nur unter Windows).
"""
from __future__ import annotations

import io
import json
import os
import sys
import types

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.dmx import udmx                                    # noqa: E402
from src.core.dmx import udmx_treiber_text as tt                 # noqa: E402
from src.core.dmx import usb_treiber_windows as tw               # noqa: E402
from src.ui import udmx_treiber_hinweis as th                    # noqa: E402

sys.path.insert(0, os.path.dirname(__file__))
import _out68_usb_attrappe as attrappe                           # noqa: E402

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CYL = "USB\\VID_2008&PID_1066&REV_0100"
ANYMA = "USB\\VID_16C0&PID_05DC&REV_0100"


def _zeilen(*zeilen):
    return lambda: list(zeilen)


def _befunde(*zeilen):
    return udmx.windows_treiber(_zeilen=_zeilen(*zeilen))


def _daten(*zeilen):
    return [tt.befund_daten(b) for b in _befunde(*zeilen)]


# ══════════════════════════════════════════════════════════════════════════════
# A) Die Abfrage: nur lesen, nie raten
# ══════════════════════════════════════════════════════════════════════════════

def test_die_abfrage_liest_nur():
    """Regel des Projekts: LightOS installiert und aendert keine Treiber. Im
    Modul steht deshalb kein Aufruf, der etwas schreibt, installiert oder ein
    anderes Programm startet."""
    with io.open(os.path.join(_REPO, "src", "core", "dmx", "usb_treiber_windows.py"),
                 encoding="utf-8") as f:
        quelle = f.read()
    for verboten in ("SetupDiInstall", "DiInstallDriver", "UpdateDriverForPlugAndPlay",
                     "SetupCopyOEMInf", "SetupDiSetDeviceRegistryProperty",
                     "SetupDiCallClassInstaller", "SetupDiRemoveDevice",
                     "CM_Reenumerate", "CM_Disable", "CM_Enable", "CM_Uninstall",
                     "winreg", "subprocess", "os.system", "ShellExecute",
                     "CreateFile", "pnputil"):
        assert verboten not in quelle, verboten
    for erlaubt in ("SetupDiGetClassDevsW", "SetupDiEnumDeviceInfo",
                    "SetupDiGetDeviceRegistryPropertyW", "CM_Get_DevNode_Status"):
        assert erlaubt in quelle


def test_kennung_und_lage_aus_den_zeilen():
    b = tw.aus_zeilen([(CYL, "WinUSB", 0, "USBDMX512", "USB-Gerät"),
                       ("USB\\VID_046D&PID_C52B", "usbccgp", 0, "Empfänger", "")])
    assert [(x.kennung, x.lage) for x in b] == [("046d:c52b", tw.ANDERER),
                                                ("2008:1066", tw.PASST)]
    assert b[1].name == "USBDMX512" and b[1].beschreibung == "USB-Gerät"


@pytest.mark.parametrize("dienst,lage", [
    ("WinUSB", tw.PASST), ("winusb", tw.PASST), ("libusbK", tw.PASST),
    ("libusb0", tw.PASST), ("", tw.FEHLT), ("  ", tw.FEHLT),
    ("HidUsb", tw.ANDERER), ("usbccgp", tw.ANDERER)])
def test_lage_je_treiber_dienst(dienst, lage):
    assert tw.aus_zeilen([(CYL, dienst, 0, "", "")])[0].lage == lage


def test_schnittstellen_eines_verbundgeraets_zaehlen_nicht():
    """Der ADAPTER braucht den Treiber — die Zeile ``…&MI_00`` ist nur eine
    seiner Schnittstellen und sagte sonst „passt“, wo nichts passt."""
    b = tw.aus_zeilen([(CYL, "usbccgp", 0, "", ""),
                       ("USB\\VID_2008&PID_1066&MI_00", "WinUSB", 0, "", "")])
    assert [x.lage for x in b] == [tw.ANDERER]


def test_nur_die_gesuchten_kennungen():
    zeilen = [(CYL, "", 28, "", ""), ("USB\\VID_046D&PID_C52B", "HidUsb", 0, "", "")]
    assert [x.kennung for x in tw.aus_zeilen(zeilen, [(0x2008, 0x1066)])] == ["2008:1066"]
    assert tw.aus_zeilen(zeilen, []) == []
    assert tw.aus_zeilen([("ROOT\\KDNIC", "kdnic", 0, "", "")]) == []


def test_nicht_feststellbar_ist_none_und_nicht_leer(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    assert tw.angesteckt([(0x2008, 0x1066)]) is None            # kein Windows

    def kaputt():
        raise OSError(5, "verweigert")
    assert tw.angesteckt(None, _zeilen=kaputt) is None          # Abfrage gescheitert
    assert tw.angesteckt(None, _zeilen=lambda: []) == []        # nichts steckt


def test_mehrere_gleiche_adapter_mit_verschiedener_lage_bleiben_offen():
    b = tw.aus_zeilen([(CYL, "WinUSB", 0, "", ""), (CYL, "", 28, "", ""),
                       (ANYMA, "", 28, "uDMX", "")])
    assert tw.lage_je_kennung(b) == {(0x16C0, 0x05DC): tw.FEHLT}
    assert tw.lage_je_kennung([]) == {}


@pytest.mark.skipif(not sys.platform.startswith("win"), reason="nur unter Windows")
def test_die_echte_abfrage_laeuft_und_liest_nur_beschreibungen():
    zeilen = tw._setupapi_zeilen()
    assert isinstance(zeilen, list)
    for zeile in zeilen:
        assert len(zeile) == 5 and isinstance(zeile[0], str) and isinstance(zeile[2], int)
    assert tw.angesteckt([(0xFFFF, 0xFFFE)]) == []


# ══════════════════════════════════════════════════════════════════════════════
# B) Der Treiber: richtiger Grund, ehrliche Liste
# ══════════════════════════════════════════════════════════════════════════════

def test_pyusb_meldet_den_fehlenden_treiber_als_notimplementederror():
    """pyusb wirft fuer LIBUSB_ERROR_NOT_SUPPORTED kein USBError — ohne errno
    und ohne libusb-Code. Bisher: „nimmt keine Daten an — Kabel prüfen“."""
    assert udmx._fehler_code(NotImplementedError(
        "Operation not supported or unimplemented on this platform")) == udmx.G_TREIBER_FEHLT


def test_sender_ohne_treiber_nennt_sofort_den_richtigen_grund():
    dev = attrappe.Geraet()

    def nicht_unterstuetzt(_daten):
        raise NotImplementedError("Operation not supported or unimplemented on this platform")
    dev.verhalten = nicht_unterstuetzt
    gruende = []
    u = udmx.Udmx("2008:1066", usb=attrappe.usb(dev), melde_grund=gruende.append)
    u.send_dmx(bytes(512))
    assert u.is_disabled(), "kein Treiber wird durch Wiederholen nicht besser"
    assert u.grund == udmx.G_TREIBER_FEHLT
    assert gruende[-1] == udmx.G_TREIBER_FEHLT
    assert len(dev.transfers) == 1


def test_liste_traegt_die_treiber_lage():
    dev = attrappe.Geraet(produkt="USBDMX512")
    ohne = udmx.liste_geraete(attrappe.usb(dev), treiber=_befunde((CYL, "", 28, "USBDMX512", "")))
    assert ohne[0].treiber == udmx.T_FEHLT
    assert ohne[0].beschriftung().endswith("— Treiber fehlt (WinUSB zuweisen)")
    assert ohne[0].bestaetigt, "bleibt waehlbar: der Sender findet ihn, sobald der Treiber da ist"
    mit = udmx.liste_geraete(attrappe.usb(dev), treiber=_befunde((CYL, "WinUSB", 0, "", "")))
    assert mit[0].treiber == udmx.T_PASST and "Treiber" not in mit[0].beschriftung()
    fremd = udmx.liste_geraete(attrappe.usb(dev), treiber=_befunde((CYL, "HidUsb", 0, "", "")))
    assert "falscher Treiber „HidUsb“" in fremd[0].beschriftung()


def test_ohne_auftrag_wird_windows_nicht_gefragt(monkeypatch):
    """Der Sender sucht nur seinen Adapter (alle 2 s beim Wiederverbinden) —
    die Treiber-Frage gehoert in die Suche des Dialogs."""
    monkeypatch.setattr(tw, "angesteckt",
                        lambda *a, **k: pytest.fail("Windows wurde gefragt"))
    g = udmx.liste_geraete(attrappe.usb(attrappe.Geraet()))
    assert g[0].treiber == "" and "Treiber" not in g[0].beschriftung()


def test_ohne_treiber_ist_der_name_nicht_lesbar_das_steht_dann_da():
    dev = attrappe.anyma(lesbar=False)
    g = udmx.liste_geraete(attrappe.usb(dev), treiber=_befunde((ANYMA, "", 28, "uDMX", "")))
    assert not g[0].bestaetigt
    assert g[0].hinweis == "Name nicht lesbar — Treiber fehlt (WinUSB zuweisen)"
    # ohne Auskunft von Windows bleibt der bisherige Hinweis
    alt = udmx.liste_geraete(attrappe.usb(dev))
    assert "Berechtigung" in alt[0].hinweis


def test_zwei_gleiche_adapter_verschiedene_lage_keine_behauptung():
    a, b = attrappe.Geraet(ports=(2,)), attrappe.Geraet(ports=(5,), adresse=6)
    g = udmx.liste_geraete(attrappe.usb(a, b), treiber=_befunde(
        (CYL, "WinUSB", 0, "", ""), (CYL, "", 28, "", "")))
    assert [x.treiber for x in g] == ["", ""]
    assert all("Treiber" not in x.beschriftung() for x in g)


def test_geteilte_kennung_ein_fremdes_geraet_wird_nie_gemeldet():
    """16c0:05dc tragen viele Bastelgeraete. Nennt sich das Geraet nicht „uDMX“,
    darf niemand den Rat bekommen, ihm den Treiber zu ersetzen."""
    assert _befunde((ANYMA, "HidUsb", 0, "USBasp", "")) == []
    b = _befunde((ANYMA, "", 28, "uDMX", ""))
    assert len(b) == 1 and udmx.treiber_befund_sicher(b[0])
    unbekannt = _befunde((ANYMA, "", 28, "", ""))
    assert len(unbekannt) == 1 and not udmx.treiber_befund_sicher(unbekannt[0])
    assert udmx.treiber_befund_sicher(_befunde((CYL, "", 28, "", ""))[0])


def test_abgeschaltetes_usb_fragt_auch_windows_nicht(monkeypatch):
    monkeypatch.setenv("LIGHTOS_KEIN_USB", "1")
    monkeypatch.setattr(tw, "angesteckt",
                        lambda *a, **k: pytest.fail("Windows wurde gefragt"))
    assert udmx.windows_treiber() is None


# ══════════════════════════════════════════════════════════════════════════════
# C) Die Erklaerung: Schritte, Links, ehrliche Worte
# ══════════════════════════════════════════════════════════════════════════════

def test_schritte_nennen_programm_link_und_die_kennung():
    schritte = udmx.windows_treiber_schritte("2008:1066")
    assert len(schritte) == 5
    assert udmx.LINK_ZADIG in schritte[0] and "installiert keine Treiber" in schritte[0]
    assert "List All Devices" in schritte[2] and "USB ID 2008 1066" in schritte[2]
    assert "WinUSB" in schritte[3] and "Install Driver" in schritte[3]
    assert "Adapter suchen" in schritte[4]
    beide = udmx.windows_treiber_schritte()[2]
    assert "2008 1066" in beide and "16C0 05DC" in beide
    assert "Maus" in udmx.windows_treiber_achtung()


def test_links_sind_offizielle_seiten():
    assert udmx.LINK_ZADIG == "https://zadig.akeo.ie"
    assert udmx.LINK_WINUSB.startswith("https://learn.microsoft.com/")


def test_im_installationspaket_kein_rat_zu_pip(monkeypatch):
    assert "pip install pyusb" in udmx.grund_text(udmx.G_PYUSB_FEHLT)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    text = udmx.grund_text(udmx.G_PYUSB_FEHLT)
    assert "pip" not in text
    assert "Installationspaket" in text and "nicht nachinstallieren" in text
    assert "Art-Net" in text


def test_kurztext_sagt_dass_lightos_keinen_treiber_liefert():
    kurz = udmx.grund_kurz(udmx.G_TREIBER_FEHLT)
    assert "WinUSB" in kurz and "LightOS liefert keinen" in kurz


def test_nach_der_suche_gewinnt_der_fehlende_treiber():
    assert th.nach_suche({"treiber": [], "code": udmx.G_OK}) is None
    assert th.nach_suche({"code": udmx.G_PYUSB_FEHLT}) is None
    assert th.nach_suche({"treiber": _daten((CYL, "WinUSB", 0, "", ""))}) is None
    status, html = th.nach_suche({"treiber": _daten((CYL, "", 28, "USBDMX512", "")),
                                  "code": udmx.G_OK})
    assert status == "1 Adapter am USB gefunden — Treiber fehlt (Windows), Schritte unten"
    assert html.startswith("<html>") and html.count("<li>") == 5
    assert f'<a href="{udmx.LINK_ZADIG}">' in html
    assert f'<a href="{udmx.LINK_WINUSB}">' in html
    assert "CYL-6602" in html and "2008:1066" in html
    assert "Treiber nicht installiert" in html              # Code 28 des Geräte-Managers
    assert "liefert und installiert keinen" in html
    assert "Maus" in html and "Außerdem" not in html


def test_fehlt_dazu_pyusb_steht_beides_da(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    _status, html = th.nach_suche({
        "treiber": _daten((CYL, "", 28, "", "")), "code": udmx.G_PYUSB_FEHLT,
        "text": udmx.grund_text(udmx.G_PYUSB_FEHLT)})
    assert "Außerdem: Dieses LightOS aus dem Installationspaket" in html


def test_falscher_treiber_und_unsichere_kennung():
    status, html = th.nach_suche({"treiber": _daten((CYL, "HidUsb", 0, "", ""))})
    assert "falscher Treiber" in status and "den Treiber „HidUsb“ zugeordnet" in html
    _status, html = th.nach_suche({"treiber": _daten((ANYMA, "", 28, "", ""))})
    assert "geteilten Kennung 16c0:05dc" in html
    assert "Nur zuweisen, wenn das Gerät sicher dein uDMX-Adapter ist" in html


def test_texte_werden_maskiert():
    html = th.schritte_html("2008:1066", "Name <b> & Co")
    assert "Name &lt;b&gt; &amp; Co" in html


# ══════════════════════════════════════════════════════════════════════════════
# D) Der Reiter „uDMX (USB)“
# ══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def konfig(tmp_path, monkeypatch):
    from src.ui.widgets import output_config as oc
    p = tmp_path / "universes.json"
    monkeypatch.setattr(oc, "_UNIV_CONFIG_PATH", str(p))
    io.open(p, "w", encoding="utf-8").write(json.dumps(
        [{"num": 1, "name": "Main", "output": "Disabled", "patch": ""}]))
    return oc


@pytest.fixture
def dialog(konfig):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    d = konfig.OutputConfigDialog()
    yield d
    d.deleteLater()


def test_die_suche_fragt_windows_auch_ohne_pyusb(konfig, monkeypatch):
    """conftest schaltet rohes USB ab -> „pyusb fehlt“. Die Auskunft von
    Windows kommt trotzdem mit: sie braucht kein pyusb."""
    assert konfig._udmx_suchen()["treiber"] == []
    befunde = _befunde((CYL, "", 28, "USBDMX512", ""))
    monkeypatch.setattr(udmx, "windows_treiber", lambda: befunde)
    ergebnis = konfig._udmx_suchen()
    assert ergebnis["code"] == udmx.G_PYUSB_FEHLT and ergebnis["geraete"] == []
    assert [(t["kennung"], t["lage"]) for t in ergebnis["treiber"]] == [
        ("2008:1066", udmx.T_FEHLT)]


def test_die_suche_ueberlebt_eine_gescheiterte_windows_abfrage(konfig, monkeypatch):
    def kaputt():
        raise RuntimeError("weg")
    monkeypatch.setattr(udmx, "windows_treiber", kaputt)
    assert konfig._udmx_suchen()["treiber"] == []


def test_reiter_zeigt_schritte_statt_eingesteckt(dialog):
    dialog._udmx_liste_zeigen({
        "geraete": [], "unklar": 0, "code": udmx.G_PYUSB_FEHLT,
        "text": udmx.grund_text(udmx.G_PYUSB_FEHLT),
        "treiber": _daten((CYL, "", 28, "USBDMX512", ""))})
    assert "Treiber fehlt" in dialog._lbl_udmx_status.text()
    hinweis = dialog._lbl_udmx_hinweis.text()
    assert udmx.LINK_ZADIG in hinweis and "List All Devices" in hinweis
    assert "eingesteckt?" not in hinweis
    assert dialog._combo_udmx.itemText(0) == "Adapter ohne Treiber — siehe unten"
    assert dialog._combo_udmx.itemData(0) == "", "nichts Waehlbares vorgetaeuscht"
    assert dialog._lbl_udmx_hinweis.openExternalLinks()
    # Die Schritte sind laenger als der Reiter hoch ist: sie rollen, statt
    # unten abgeschnitten zu werden (im Bild geprueft, hier festgehalten).
    assert dialog._udmx_hinweis_rollen.widget() is dialog._lbl_udmx_hinweis
    assert dialog._udmx_hinweis_rollen.widgetResizable()


def test_gefundener_adapter_ohne_treiber_steht_ehrlich_in_der_liste(dialog):
    dev = attrappe.Geraet()
    befunde = _befunde((CYL, "", 28, "USBDMX512", ""))
    g = udmx.liste_geraete(attrappe.usb(dev), treiber=befunde)
    dialog._udmx_liste_zeigen({
        "geraete": [(x.beschriftung(), x.schluessel) for x in g], "unklar": 0,
        "code": udmx.G_OK, "text": "",
        "treiber": [tt.befund_daten(b) for b in befunde]})
    assert "Treiber fehlt (WinUSB zuweisen)" in dialog._combo_udmx.itemText(0)
    assert dialog._combo_udmx.itemData(0) == "2008:1066@1-2"
    assert "Treiber fehlt" in dialog._lbl_udmx_status.text()
    assert "Adapter gefunden — „Verbinden“ richtet ihn ein" not in dialog._lbl_udmx_status.text()


def test_ohne_treiber_befund_bleibt_der_reiter_wie_bisher(dialog):
    dialog._udmx_liste_zeigen({
        "geraete": [("CYL-6602 · 2008:1066 · Anschluss 1-2", "2008:1066@1-2")],
        "unklar": 0, "code": udmx.G_OK, "text": "",
        "treiber": _daten((CYL, "WinUSB", 0, "", ""))})
    assert "1 Adapter gefunden" in dialog._lbl_udmx_status.text()
    assert dialog._lbl_udmx_hinweis.text() == ""
    dialog._udmx_liste_zeigen({"geraete": [], "unklar": 0, "code": udmx.G_OK, "text": ""})
    assert "Kein uDMX-Adapter gefunden" in dialog._lbl_udmx_status.text()


def test_nach_verbinden_stehen_die_schritte_da(dialog, konfig, monkeypatch):
    dev = types.SimpleNamespace(
        port="2008:1066@1-2", grund=lambda: udmx.G_TREIBER_FEHLT,
        grund_text=lambda: udmx.grund_text(udmx.G_TREIBER_FEHLT, "2008:1066@1-2"),
        is_connected=lambda: False, is_disabled=lambda: True, status=lambda: 2)
    om = types.SimpleNamespace(_udmx_outputs={3: dev})
    monkeypatch.setattr(konfig, "get_state",
                        lambda: types.SimpleNamespace(output_manager=om))
    dialog._udmx_pruef_univ, dialog._udmx_pruef_versuche = 3, 0
    monkeypatch.setattr(tw, "ist_windows", lambda: True)
    dialog._udmx_status_nachtragen()
    assert "sendet nicht" in dialog._lbl_udmx_status.text()
    hinweis = dialog._lbl_udmx_hinweis.text()
    assert hinweis.count("<li>") == 5 and "USB ID 2008 1066" in hinweis
    # Auf einem anderen System bleibt der Satz aus grund_text.
    monkeypatch.setattr(tw, "ist_windows", lambda: False)
    dialog._udmx_status_nachtragen()
    assert "<li>" not in dialog._lbl_udmx_hinweis.text()


# ══════════════════════════════════════════════════════════════════════════════
# E) Diagnosepaket und Anleitung
# ══════════════════════════════════════════════════════════════════════════════

def test_diagnosepaket_nennt_die_treiber_lage_und_den_weg(monkeypatch):
    from src.core import diagnose_log
    monkeypatch.setitem(sys.modules, "src.core.app_state",
                        types.SimpleNamespace(_state=None))
    assert len(diagnose_log.udmx_infos()) == 1                  # ohne Befund wie bisher
    ohne = _befunde((CYL, "", 28, "USBDMX512", ""))
    mit = _befunde((CYL, "WinUSB", 0, "", ""))
    monkeypatch.setattr(udmx, "windows_treiber", lambda: ohne)
    zeilen = diagnose_log.udmx_infos()
    assert zeilen[1].startswith("Windows-Treiber: CYL-6602")
    assert "keinen Treiber zugeordnet" in zeilen[1]
    assert any(z.strip().startswith("1. Das Programm Zadig laden") for z in zeilen)
    assert any("Achtung" in z for z in zeilen)
    monkeypatch.setattr(udmx, "windows_treiber", lambda: mit)
    zeilen = diagnose_log.udmx_infos()
    assert zeilen[1:] == ["Windows-Treiber CYL-6602 / Sun-light USBDMX512 "
                          "(2008:1066): WinUSB — passt"]


def _lies(*teile):
    with io.open(os.path.join(_REPO, *teile), encoding="utf-8") as f:
        return f.read()


def test_install_md_beschreibt_denselben_weg():
    text = " ".join(_lies("INSTALL.md").split())
    for marke in (udmx.LINK_ZADIG, "List All Devices", "WinUSB", "Install Driver",
                  "Maus", "liefert und installiert keine Treiber",
                  "Installationspaket"):
        assert marke in text, marke


def test_anleitung_sagt_ehrlich_was_windows_braucht():
    # Zeilenumbrueche der Doku zaehlen nicht.
    de = " ".join(_lies("docs", "anleitung_ausgabe_einrichten", "ANLEITUNG.md").split())
    en = " ".join(_lies("docs", "anleitung_ausgabe_einrichten", "ANLEITUNG.en.md").split())
    assert "Unter Windows braucht er einen Treiber, den weder Windows noch LightOS mitbringt" in de
    assert "Treiber fehlt" in de and udmx.LINK_ZADIG in de
    assert "neither Windows nor LightOS ships" in en and udmx.LINK_ZADIG in en
