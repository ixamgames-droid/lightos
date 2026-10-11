"""OUT-68 — uDMX-Treiber: Protokoll, Erkennung, Ausfall und Wiederkehr.

Ausschliesslich mit der USB-Attrappe (``_out68_usb_attrappe``): kein echtes
Geraet, kein pyusb. Was am echten Adapter gemessen wurde, steht hier als
Erwartung fest:

* ``bmRequestType`` 0x40, ``bRequest`` 2, ``wValue`` = Anzahl (512),
  ``wIndex`` = Startkanal (0), Daten = die 512 Kanalwerte — EIN Transfer.
* Nie eine andere Request-Nummer (uDMX kennt den Bootloader-Befehl 0xf8).
"""
from __future__ import annotations

import errno
import os
import sys

import pytest

from src.core.dmx import udmx
import _out68_usb_attrappe as fake

BILD = bytes(range(256)) * 2


class Uhr:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def _adapter(geraet=None, schluessel="", **kw):
    g = geraet or fake.Geraet()
    usb = fake.usb(g)
    return udmx.Udmx(schluessel, usb=usb, **kw), g, usb


# ── Protokoll ────────────────────────────────────────────────────────────────

def test_ein_bild_ist_genau_ein_transfer_mit_den_gemessenen_parametern():
    dev, g, _ = _adapter()
    dev.send_dmx(BILD)
    assert g.transfers == [(0x40, 2, 512, 0, BILD, udmx.TIMEOUT_MS)]


def test_jedes_bild_wird_ganz_gesendet_auch_wenn_sich_nichts_aendert():
    """Kein „nur Aenderungen": der Adapter haelt seinen eigenen Stand, und
    Blackout/NOT-AUS muessen ihn in jedem Takt sicher erreichen."""
    dev, g, _ = _adapter()
    for _ in range(3):
        dev.send_dmx(BILD)
    einzeln = bytearray(BILD)
    einzeln[7] ^= 0xFF
    dev.send_dmx(bytes(einzeln))
    assert len(g.transfers) == 4
    assert all(t[2] == 512 and t[3] == 0 and len(t[4]) == 512 for t in g.transfers)
    assert g.transfers[-1][4] == bytes(einzeln)


def test_falsche_laenge_wird_nicht_gesendet():
    dev, g, _ = _adapter()
    with pytest.raises(AssertionError):
        dev.send_dmx(bytes(100))
    assert g.transfers == []


def test_niemals_eine_andere_request_nummer():
    """Ueber Ausfall, Wiederkehr und Schliessen hinweg: nur 0x40 / Request 2."""
    uhr = Uhr()
    dev, g, usb = _adapter(clock=uhr)
    dev.send_dmx(BILD)
    g.verhalten = lambda _d: (_ for _ in ()).throw(fake.abgezogen())
    dev.send_dmx(BILD)
    g2 = fake.Geraet()
    usb[0].geraete = [g2]
    uhr.t += 10
    dev.send_dmx(BILD)
    dev.close()
    alle = g.transfers + g2.transfers
    assert alle and {(t[0], t[1]) for t in alle} == {(0x40, 2)}


def test_quelltext_hat_genau_eine_sende_stelle_mit_fester_request_nummer():
    quelle = open(udmx.__file__, encoding="utf-8").read()
    assert quelle.count("ctrl_transfer(") == 1
    assert "ctrl_transfer(REQUEST_TYPE_OUT, REQUEST_KANALBEREICH," in quelle
    assert udmx.REQUEST_TYPE_OUT == 0x40 and udmx.REQUEST_KANALBEREICH == 2


def test_schliessen_sendet_nichts_und_ist_idempotent():
    """Kein eigenmaechtiges „alles auf 0" — das entscheidet der OutputManager
    (Laser-Aus-Werte sind nicht immer 0)."""
    dev, g, _ = _adapter()
    dev.send_dmx(BILD)
    dev.close()
    dev.close()
    dev.send_dmx(BILD)
    assert len(g.transfers) == 1
    assert g.freigegeben == 1 and not dev.is_open()


# ── Erkennung ────────────────────────────────────────────────────────────────

def test_cyl_6602_wird_an_der_kennung_erkannt_ohne_namen():
    g = fake.Geraet(bus=3, ports=(1, 4))
    [gefunden] = udmx.liste_geraete(fake.usb(g))
    assert gefunden.kennung == "2008:1066" and gefunden.bestaetigt
    assert gefunden.ort == "3-1.4"
    assert gefunden.schluessel == "2008:1066@3-1.4"
    assert "CYL-6602" in gefunden.beschriftung()


def test_anyma_braucht_hersteller_und_produktnamen():
    echt = fake.anyma()
    [gefunden] = udmx.liste_geraete(fake.usb(echt))
    assert gefunden.bestaetigt and gefunden.seriennummer == "SN001"
    assert gefunden.schluessel == "16c0:05dc#SN001"


@pytest.mark.parametrize("hersteller,produkt", [
    ("www.fischl.de", "USBasp"),          # Programmer mit derselben Kennung
    ("www.anyma.ch", "anderes Ding"),
    ("Irgendwer", "uDMX"),
    ("", ""),
])
def test_geteilte_kennung_mit_fremdem_namen_ist_kein_udmx(hersteller, produkt):
    fremd = fake.anyma(hersteller=hersteller, produkt=produkt)
    assert udmx.liste_geraete(fake.usb(fremd)) == []
    with pytest.raises(udmx.UdmxFehler) as e:
        udmx.Udmx("", usb=fake.usb(fremd))
    assert e.value.code == udmx.G_NICHT_DA
    assert fremd.transfers == []


def test_geteilte_kennung_ohne_lesbaren_namen_wird_nicht_angesprochen():
    unklar = fake.anyma(lesbar=False)
    [g] = udmx.liste_geraete(fake.usb(unklar))
    assert not g.bestaetigt and "nicht lesbar" in g.beschriftung()
    with pytest.raises(udmx.UdmxFehler) as e:
        udmx.Udmx("", usb=fake.usb(unklar))
    assert e.value.code == udmx.G_NAME_UNKLAR
    assert unklar.transfers == []


def test_fremde_usb_geraete_bleiben_unberuehrt():
    """Texte werden nur von Geraeten gelesen, deren Kennung in der Tabelle steht."""
    maus = fake.Geraet(vid=0x046D, pid=0xC077, hersteller="Logitech", produkt="Maus")
    ftdi = fake.Geraet(vid=0x0403, pid=0x6001, hersteller="FTDI", produkt="FT232R")
    assert udmx.liste_geraete(fake.usb(maus, ftdi, fake.Geraet())).__len__() == 1
    assert maus.text_zugriffe == 0 and ftdi.text_zugriffe == 0
    assert maus.transfers == [] and ftdi.transfers == []


def test_schluessel_lesen():
    assert udmx.schluessel_lesen("2008:1066") == (0x2008, 0x1066, "", "")
    assert udmx.schluessel_lesen("16c0:05dc#SN#1") == (0x16C0, 0x05DC, "SN#1", "")
    assert udmx.schluessel_lesen(" 2008:1066@1-2.3 ") == (0x2008, 0x1066, "", "1-2.3")
    assert udmx.schluessel_lesen("") == (None, None, "", "")
    assert udmx.schluessel_lesen("Quatsch") == (None, None, "", "")
    assert udmx.schluessel_lesen(None) == (None, None, "", "")


def test_zwei_gleiche_adapter_werden_am_anschluss_unterschieden():
    a, b = fake.Geraet(ports=(1,)), fake.Geraet(ports=(2,), adresse=6)
    geraete = udmx.liste_geraete(fake.usb(a, b))
    assert udmx.waehle(geraete, "2008:1066@1-2")._dev is b
    assert udmx.waehle(geraete, "2008:1066@1-1")._dev is a
    with pytest.raises(udmx.UdmxFehler) as e:
        udmx.waehle(geraete, "2008:1066")
    assert e.value.code == udmx.G_MEHRDEUTIG
    with pytest.raises(udmx.UdmxFehler) as e:
        udmx.waehle(geraete, "")
    assert e.value.code == udmx.G_MEHRDEUTIG


def test_fehlender_anschluss_bei_mehreren_adaptern_nimmt_keinen_fremden():
    """Lehre aus OUT-66: nie den Adapter eines anderen Universums greifen."""
    a, b = fake.Geraet(ports=(1,)), fake.Geraet(ports=(2,), adresse=6)
    geraete = udmx.liste_geraete(fake.usb(a, b))
    with pytest.raises(udmx.UdmxFehler) as e:
        udmx.waehle(geraete, "2008:1066@1-7")
    assert e.value.code == udmx.G_NICHT_DA


def test_einziger_adapter_an_anderer_buchse_wird_wiedererkannt():
    g = fake.Geraet(ports=(4,))
    assert udmx.waehle(udmx.liste_geraete(fake.usb(g)), "2008:1066@1-2")._dev is g


def test_streng_nimmt_nie_den_einzigen_vorhandenen_als_ersatz():
    """Review OUT-68: bei mehreren uDMX-Ausgaengen kann „der einzige
    vorhandene" der Adapter eines ANDEREN Universums sein."""
    g = fake.Geraet(ports=(4,))
    geraete = udmx.liste_geraete(fake.usb(g))
    assert udmx.waehle(geraete, "2008:1066@1-4", streng=True)._dev is g
    with pytest.raises(udmx.UdmxFehler) as e:
        udmx.waehle(geraete, "2008:1066@1-2", streng=True)
    assert e.value.code == udmx.G_NICHT_DA and "Anschluss" in str(e.value)
    for offen in ("2008:1066", ""):
        with pytest.raises(udmx.UdmxFehler) as e:
            udmx.waehle(geraete, offen, streng=True)
        assert e.value.code == udmx.G_MEHRDEUTIG
    # Die Seriennummer ist exakt — sie gilt auch streng, an jeder Buchse.
    s = fake.anyma(serie="A1", ports=(7,))
    assert udmx.waehle(udmx.liste_geraete(fake.usb(s)), "16c0:05dc#A1",
                       streng=True)._dev is s


def test_abgezogener_adapter_greift_nicht_den_des_anderen_universums():
    """Zwei gleiche Adapter ohne Seriennummer, zwei Universen. Wird der zweite
    abgezogen, darf sein Sender nicht auf den ersten ausweichen."""
    uhr = Uhr()
    a, b = fake.Geraet(ports=(2,)), fake.Geraet(ports=(3,), adresse=6)
    usb = fake.usb(a, b)
    eins = udmx.Udmx("2008:1066@1-2", usb=usb, clock=uhr, streng=lambda: True)
    zwei = udmx.Udmx("2008:1066@1-3", usb=usb, clock=uhr, streng=lambda: True)
    eins.send_dmx(bytes([1]) * 512)
    zwei.send_dmx(bytes([2]) * 512)
    b.verhalten = lambda _d: (_ for _ in ()).throw(fake.abgezogen())
    usb[0].geraete = [a]
    for _ in range(4):
        zwei.send_dmx(bytes([2]) * 512)
        eins.send_dmx(bytes([1]) * 512)
        uhr.t += udmx.Udmx.RECONNECT_EVERY_S + 0.1
    assert zwei.is_disabled() and zwei.grund == udmx.G_NICHT_DA
    assert {t[4][0] for t in a.transfers} == {1}
    # Zurueck an seine Buchse: er sendet wieder — auf SEINEN Adapter.
    neu = fake.Geraet(ports=(3,), adresse=9)
    usb[0].geraete = [a, neu]
    zwei.send_dmx(bytes([2]) * 512)
    assert not zwei.is_disabled() and neu.transfers[-1][4][0] == 2


def test_ersatzweise_gehaltener_adapter_wird_losgelassen_sobald_streng_gilt():
    """Ein Ausgang allein darf seinen umgesteckten Adapter nehmen. Kommt ein
    zweiter uDMX-Ausgang dazu, gilt das nicht mehr — auch nicht fuer den schon
    gehaltenen Adapter (er kann der des neuen Ausgangs sein)."""
    streng = [False]
    g = fake.Geraet(ports=(4,))
    dev = udmx.Udmx("2008:1066@1-2", usb=fake.usb(g), streng=lambda: streng[0])
    dev.send_dmx(BILD)
    assert len(g.transfers) == 1 and not dev.is_disabled()
    streng[0] = True
    dev.send_dmx(BILD)
    assert len(g.transfers) == 1 and dev.is_disabled()
    assert dev.grund == udmx.G_NICHT_DA
    # Ein exakt passender Adapter bleibt dagegen, wenn „streng" spaeter kommt.
    g2 = fake.Geraet(ports=(2,))
    dev2 = udmx.Udmx("2008:1066@1-2", usb=fake.usb(g2), streng=lambda: streng[0])
    dev2.send_dmx(BILD)
    assert len(g2.transfers) == 1 and not dev2.is_disabled()
    # … und ein Schluessel ohne Anschluss/Seriennummer wird „mehrdeutig".
    streng[0] = False
    g3 = fake.Geraet()
    dev3 = udmx.Udmx("", usb=fake.usb(g3), streng=lambda: streng[0])
    dev3.send_dmx(BILD)
    streng[0] = True
    dev3.send_dmx(BILD)
    assert len(g3.transfers) == 1 and dev3.grund == udmx.G_MEHRDEUTIG


def test_seriennummer_passt_nur_auf_genau_diesen_adapter():
    a, b = fake.anyma(serie="A1"), fake.anyma(serie="B2", ports=(3,))
    geraete = udmx.liste_geraete(fake.usb(a, b))
    assert udmx.waehle(geraete, "16c0:05dc#B2")._dev is b
    with pytest.raises(udmx.UdmxFehler) as e:
        udmx.waehle(udmx.liste_geraete(fake.usb(a)), "16c0:05dc#B2")
    assert e.value.code == udmx.G_NICHT_DA


def test_andere_kennung_im_schluessel_passt_nicht():
    with pytest.raises(udmx.UdmxFehler) as e:
        udmx.waehle(udmx.liste_geraete(fake.usb(fake.Geraet())), "16c0:05dc")
    assert e.value.code == udmx.G_NICHT_DA


# ── fehlende Bibliothek ──────────────────────────────────────────────────────

def test_fehlendes_pyusb_gibt_klare_meldung_statt_absturz(monkeypatch):
    monkeypatch.delenv("LIGHTOS_KEIN_USB", raising=False)
    monkeypatch.setitem(sys.modules, "usb", None)       # import usb -> ImportError
    monkeypatch.setitem(sys.modules, "usb.core", None)
    with pytest.raises(udmx.UdmxFehler) as e:
        udmx.liste_geraete()
    assert e.value.code == udmx.G_PYUSB_FEHLT
    assert "pip install pyusb" in str(e.value)
    with pytest.raises(udmx.UdmxFehler) as e:
        udmx.Udmx("2008:1066")
    assert e.value.code == udmx.G_PYUSB_FEHLT


def test_schalter_kein_usb_laedt_nichts(monkeypatch):
    monkeypatch.setenv("LIGHTOS_KEIN_USB", "1")
    with pytest.raises(udmx.UdmxFehler) as e:
        udmx._usb_laden()
    assert e.value.code == udmx.G_PYUSB_FEHLT and "LIGHTOS_KEIN_USB" in str(e.value)


def test_fehlendes_libusb_wird_von_fehlendem_pyusb_unterschieden():
    with pytest.raises(udmx.UdmxFehler) as e:
        udmx.liste_geraete(fake.usb(fake.Geraet(), backend=False))
    assert e.value.code == udmx.G_LIBUSB_FEHLT
    assert "libusb" in str(e.value)


def test_modul_import_braucht_kein_pyusb():
    """Der Import oben lief, obwohl pyusb optional ist; das Modul zieht weder
    Qt noch app_state (es laeuft auch im Sende-Prozess)."""
    quelle = open(udmx.__file__, encoding="utf-8").read()
    kopf = quelle.split("class Kennung")[0]
    assert "import usb" not in kopf
    assert "PySide6" not in quelle and "app_state" not in quelle.replace(
        "``app_state``", "")


def test_bibliothek_status_fasst_kein_geraet_an():
    info = udmx.bibliothek_status()
    assert set(info) >= {"pyusb", "libusb", "text"}
    assert isinstance(info["text"], str) and info["text"]


# ── Ausfall und Wiederkehr ───────────────────────────────────────────────────

def test_abziehen_stoppt_sofort_und_wiederverbinden_heilt(capsys):
    uhr = Uhr()
    gruende = []
    dev, g, usb = _adapter(clock=uhr, melde_grund=gruende.append)
    dev.send_dmx(BILD)
    g.verhalten = lambda _d: (_ for _ in ()).throw(fake.abgezogen())
    dev.send_dmx(BILD)
    assert dev.is_disabled() and dev.grund == udmx.G_NICHT_DA
    assert g.freigegeben == 1
    usb[0].geraete = []

    # Solange er weg ist: nicht weiter senden, nur gedrosselt suchen.
    vorher = usb[0].suchen
    for _ in range(50):
        dev.send_dmx(BILD)
    assert usb[0].suchen == vorher            # Drossel: keine Suche je Bild
    uhr.t += udmx.Udmx.RECONNECT_EVERY_S + 0.1
    dev.send_dmx(BILD)
    assert usb[0].suchen == vorher + 1 and dev.is_disabled()
    assert len(g.transfers) == 2

    # Wieder eingesteckt (neues Geraete-Objekt, andere Adresse).
    neu = fake.Geraet(adresse=9)
    usb[0].geraete = [neu]
    uhr.t += udmx.Udmx.RECONNECT_EVERY_S + 0.1
    dev.send_dmx(BILD)
    assert not dev.is_disabled() and dev.grund == udmx.G_OK
    assert neu.transfers == [(0x40, 2, 512, 0, BILD, udmx.TIMEOUT_MS)]
    assert gruende == [udmx.G_NICHT_DA, udmx.G_OK]
    err = capsys.readouterr().err
    assert err.count("Ausgabe gestoppt") == 1 and err.count("sendet wieder") == 1


def test_fehlende_berechtigung_wird_einmal_gemeldet_nicht_bei_jedem_versuch(capsys):
    uhr = Uhr()
    g = fake.Geraet()
    g.verhalten = lambda _d: (_ for _ in ()).throw(fake.keine_rechte())
    dev, _, _ = _adapter(g, clock=uhr)
    for _ in range(6):
        dev.send_dmx(BILD)
        uhr.t += udmx.Udmx.RECONNECT_EVERY_S + 0.1
    assert dev.is_disabled() and dev.grund == udmx.G_KEINE_BERECHTIGUNG
    assert capsys.readouterr().err.count("Ausgabe gestoppt") == 1


def test_einzelnes_zeitlimit_ist_kein_ausfall_eine_serie_schon():
    g = fake.Geraet()
    dev, _, _ = _adapter(g)
    g.verhalten = lambda _d: (_ for _ in ()).throw(fake.zeitlimit())
    for _ in range(udmx.Udmx.FAIL_LIMIT - 1):
        dev.send_dmx(BILD)
    assert not dev.is_disabled()
    g.verhalten = None
    dev.send_dmx(BILD)
    assert not dev.is_disabled() and dev._fail_count == 0
    g.verhalten = lambda _d: (_ for _ in ()).throw(fake.zeitlimit())
    for _ in range(udmx.Udmx.FAIL_LIMIT):
        dev.send_dmx(BILD)
    assert dev.is_disabled() and dev.grund == udmx.G_ANTWORTET_NICHT


def test_zu_kurz_angenommene_daten_zaehlen_als_fehler():
    g = fake.Geraet()
    g.verhalten = lambda _d: 8
    dev, _, _ = _adapter(g)
    for _ in range(udmx.Udmx.FAIL_LIMIT):
        dev.send_dmx(BILD)
    assert dev.is_disabled() and dev.grund == udmx.G_ANTWORTET_NICHT


def test_stall_gilt_nur_bei_der_original_kennung_als_erfolg():
    """Wie OLA: Anyma-Klone antworten uneinheitlich. Am CYL-6602 ist ein
    regulaer bestaetigter Transfer gemessen — dort bleibt ein STALL ein Fehler."""
    a = fake.anyma()
    a.verhalten = lambda _d: (_ for _ in ()).throw(fake.stall())
    dev, _, _ = _adapter(a)
    for _ in range(10):
        dev.send_dmx(BILD)
    assert not dev.is_disabled() and dev.stalls == 10

    c = fake.Geraet()
    c.verhalten = lambda _d: (_ for _ in ()).throw(fake.stall())
    dev2, _, _ = _adapter(c)
    for _ in range(udmx.Udmx.FAIL_LIMIT):
        dev2.send_dmx(BILD)
    assert dev2.is_disabled()


@pytest.mark.parametrize("fehler,code", [
    (fake.USBError("", errno.EACCES), udmx.G_KEINE_BERECHTIGUNG),
    (fake.USBError("", None, -3), udmx.G_KEINE_BERECHTIGUNG),
    (fake.USBError("", errno.ENODEV), udmx.G_NICHT_DA),
    (fake.USBError("", errno.EBUSY), udmx.G_BELEGT),
    (fake.USBError("", None, -12), udmx.G_TREIBER_FEHLT),
    (fake.USBError("", None, -5), udmx.G_TREIBER_FEHLT),
    (fake.USBError("", errno.ETIMEDOUT), udmx.G_ANTWORTET_NICHT),
    (fake.NoBackendError("x"), udmx.G_LIBUSB_FEHLT),
])
def test_fehler_werden_eingeordnet(fehler, code):
    assert udmx._fehler_code(fehler) == code


def test_hinweistexte_nennen_den_naechsten_schritt(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    t = udmx.grund_text(udmx.G_KEINE_BERECHTIGUNG, "2008:1066")
    assert "udev" in t and udmx.UDEV_REGEL in t and "plugdev" in t
    monkeypatch.setattr(sys, "platform", "win32")
    t = udmx.grund_text(udmx.G_TREIBER_FEHLT)
    assert "WinUSB" in t and "Zadig" in t and "installiert keine Treiber" in t
    for code in range(1, 10):
        assert udmx.grund_text(code) and udmx.grund_kurz(code)
    assert udmx.grund_kurz(udmx.G_OK) == ""


def test_regeldatei_im_repo_nennt_beide_kennungen():
    wurzel = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    text = open(os.path.join(wurzel, "packaging", "linux", udmx.UDEV_REGEL),
                encoding="utf-8").read()
    for k in udmx.BEKANNTE_GERAETE:
        assert f'ATTRS{{idVendor}}=="{k.vid:04x}"' in text
        assert f'ATTRS{{idProduct}}=="{k.pid:04x}"' in text
    assert 'GROUP="plugdev"' in text
    # Die geteilte Kennung darf nur mit Namenspruefung freigegeben werden.
    anyma = [z for z in text.splitlines()
             if z.strip() and not z.startswith("#") and "05dc" in z]
    assert anyma and all('ATTRS{product}=="uDMX"' in z for z in anyma)
