"""OUT-70: DMX-Interfaces erkennen — Kenntnis-Tabelle und passive Erkennung.

Dieses Modul beantwortet zwei Fragen, ohne ein Geraet anzusprechen:

* **Was ist das?** — :data:`EINTRAEGE` ordnet USB-Kennungen (und, wo eine
  Kennung mehrdeutig ist, Hersteller-/Produkttexte) einer Interface-Familie zu.
* **Was braucht es?** — :data:`FAMILIEN` sagt je Familie, ob LightOS sie
  ausgibt, was unter Linux bzw. Windows einmalig einzurichten ist und was der
  naechste Schritt ist. LightOS installiert nie selbst Treiber: es nennt den
  Treiber und verlinkt die Seite des Herstellers.

★ **Erkennen ist nicht Ansprechen.** Gelesen wird nur, was das Betriebssystem
ohnehin weiss: die Liste der seriellen Ports (pyserial), unter Linux ``sysfs``
(dort liegen Kennung und Texte schon im Kernel vor), sonst die
USB-Geraeteliste von pyusb — **ohne ein Geraet zu oeffnen**. Texte werden ueber
pyusb nur von Geraeten gelesen, deren Kennung in der Tabelle steht. Kein
serieller Port wird geoeffnet, kein Befehl gesendet. Der Test
``tests/test_out70_interface_erkennung.py`` zaehlt die Zugriffe.

Herkunft der Kennungen: oeffentlich einsehbare Geraetelisten der freien
Programme OLA und QLC+ sowie eigene Messung (``2008:1066``). Was nicht aus
einer solchen Quelle stammt, traegt ``vermutet=True`` und wird in Assistent
und Doku so gekennzeichnet.

Kein Qt, kein ``app_state`` — reine Daten und Rechnung.
"""
from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field, replace

# ── Status ───────────────────────────────────────────────────────────────────
STATUS_UNTERSTUETZT = "unterstuetzt"
STATUS_GEPLANT = "geplant"
STATUS_NICHT = "nicht_unterstuetzt"

#: Wie gut ist die Angabe geprueft? (Spalte „Geprüft“ der Kompatibilitaetsliste)
PRUEF_GERAET = "am Gerät getestet"
PRUEF_SPEZ = "nach Spezifikation"
PRUEF_GEPLANT = "geplant"
PRUEF_NICHT = "nicht unterstützt"

TEXT_NICHT = "nicht unterstützt — Art-Net-Adapter nehmen"

BUS_SERIELL = "seriell"      # meldet sich als serieller Port (COM / ttyUSB / ttyACM)
BUS_USB = "usb"              # rohes USB, kein Port
BUS_HID = "hid"
BUS_NETZ = "netz"

# ── Befund-Codes ─────────────────────────────────────────────────────────────
B_BEREIT = "bereit"
B_EINGERICHTET = "eingerichtet"
B_TYP_UNKLAR = "typ_unklar"
B_GEPLANT = "geplant"
B_NICHT_UNTERSTUETZT = "nicht_unterstuetzt"
B_TREIBER_FEHLT = "treiber_fehlt"
B_KEINE_BERECHTIGUNG = "keine_berechtigung"
B_BELEGT = "belegt"
B_BIBLIOTHEK_FEHLT = "bibliothek_fehlt"
B_UNBEKANNT = "unbekannt"

AMPEL_GRUEN, AMPEL_GELB, AMPEL_ROT, AMPEL_BLAU, AMPEL_GRAU = (
    "gruen", "gelb", "rot", "blau", "grau")

_AMPEL = {
    B_BEREIT: AMPEL_GRUEN, B_EINGERICHTET: AMPEL_GRUEN,
    B_TYP_UNKLAR: AMPEL_GELB, B_TREIBER_FEHLT: AMPEL_GELB,
    B_KEINE_BERECHTIGUNG: AMPEL_GELB, B_BELEGT: AMPEL_GELB,
    B_BIBLIOTHEK_FEHLT: AMPEL_GELB,
    B_GEPLANT: AMPEL_BLAU, B_NICHT_UNTERSTUETZT: AMPEL_ROT,
    B_UNBEKANNT: AMPEL_GRAU,
}

#: Kurzwort je Befund (Ampel-Beschriftung im Assistenten, Diagnosepaket).
BEFUND_WORT = {
    B_BEREIT: "bereit", B_EINGERICHTET: "eingerichtet",
    B_TYP_UNKLAR: "Typ unklar", B_GEPLANT: "geplant",
    B_NICHT_UNTERSTUETZT: "nicht unterstützt",
    B_TREIBER_FEHLT: "Treiber fehlt",
    B_KEINE_BERECHTIGUNG: "keine Berechtigung",
    B_BELEGT: "belegt von anderem Programm",
    B_BIBLIOTHEK_FEHLT: "Programmteil fehlt", B_UNBEKANNT: "unbekannt",
}

# ── Links (nur offizielle Seiten; https) ─────────────────────────────────────
LINK_FTDI = "https://ftdichip.com/drivers/vcp-drivers/"
LINK_WCH = "https://www.wch-ic.com/downloads/CH341SER_EXE.html"
LINK_SILABS = ("https://www.silabs.com/developer-tools/"
               "usb-to-uart-bridge-vcp-drivers")
LINK_WINUSB = ("https://learn.microsoft.com/windows-hardware/drivers/usbcon/"
               "winusb-installation")
LINK_ARDUINO = "https://www.arduino.cc/en/software"
LINK_EUROLITE = "https://www.steinigke.de/"

#: Kopierbare Befehle — LightOS zeigt sie an und fuehrt sie NIE selbst aus.
BEFEHL_DIALOUT = 'sudo usermod -aG dialout "$USER"'
BEFEHL_UDMX = (
    "sudo cp packaging/linux/60-lightos-udmx.rules /etc/udev/rules.d/\n"
    "sudo udevadm control --reload-rules && sudo udevadm trigger\n"
    'sudo usermod -aG plugdev "$USER"')

_LINUX_SERIELL = ("Kein Treiber nötig (im Kernel). Das Benutzerkonto muss in "
                  "der Gruppe dialout sein; danach einmal ab- und wieder "
                  "anmelden.")
_LINUX_UDMX = ("Kein Treiber nötig. Einmalig die udev-Regel "
               "packaging/linux/60-lightos-udmx.rules einspielen und den "
               "Adapter neu einstecken.")
_LINUX_KEINER = "Wird von LightOS nicht angesprochen."

#: Anker in ``docs/anleitung_ausgabe_einrichten/INTERFACES.md``.
DOKU_DATEI = "docs/anleitung_ausgabe_einrichten/INTERFACES.md"


@dataclass(frozen=True)
class Familie:
    """Eine Interface-Familie = ein Protokoll, nicht ein Produkt."""
    schluessel: str
    name: str
    status: str
    #: Text aus ``output_config.AUSGABE_TYPEN`` — nur bei ``unterstuetzt``.
    ausgabe_art: str = ""
    bus: str = BUS_SERIELL
    #: Kennung sagt nicht, welches Protokoll das Geraet spricht.
    typ_unklar: bool = False
    linux: str = _LINUX_SERIELL
    linux_befehl: str = ""
    windows_treiber: str = ""
    windows_link: str = ""
    naechster_schritt: str = ""

    def status_text(self) -> str:
        """Wortlaut der Spalte „Status in LightOS“."""
        if self.status == STATUS_UNTERSTUETZT:
            return f"unterstützt: {self.ausgabe_art}"
        if self.status == STATUS_GEPLANT:
            return "geplant"
        return TEXT_NICHT


_FTDI_WIN = "FTDI VCP (kommt meist über Windows Update)"

FAMILIEN: dict[str, Familie] = {f.schluessel: f for f in (
    Familie("pro", "Pro-Nachrichtenformat (Enttec-Pro-kompatibel)",
            STATUS_UNTERSTUETZT, ausgabe_art="Enttec",
            linux_befehl=BEFEHL_DIALOUT,
            windows_treiber=_FTDI_WIN, windows_link=LINK_FTDI,
            naechster_schritt="Als Ausgabe einrichten (Art „Enttec“)."),
    Familie("ftdi_unklar", "FTDI-Adapter — Typ unklar",
            STATUS_UNTERSTUETZT, ausgabe_art="Enttec", typ_unklar=True,
            linux_befehl=BEFEHL_DIALOUT,
            windows_treiber=_FTDI_WIN, windows_link=LINK_FTDI,
            naechster_schritt=(
                "Prüfen, was auf dem Adapter steht. Enttec-Pro-kompatible "
                "Adapter laufen über die Art „Enttec“ — mit dem Testsignal "
                "ausprobieren. Reine „Open DMX“-Kabel werden noch nicht "
                "unterstützt (geplant).")),
    Familie("ftdi_sonstig", "FTDI-Chip (anderer Baustein) — Typ unklar",
            STATUS_GEPLANT, typ_unklar=True,
            linux_befehl=BEFEHL_DIALOUT,
            windows_treiber=_FTDI_WIN, windows_link=LINK_FTDI,
            naechster_schritt=(
                "Noch nicht als DMX-Interface erkannt. Spricht der Adapter das "
                "Pro-Format, lässt er sich im Reiter „Enttec Pro USB“ von Hand "
                "wählen.")),
    Familie("eurolite_pro", "Eurolite USB-DMX512 PRO",
            STATUS_GEPLANT,
            linux_befehl=BEFEHL_DIALOUT,
            windows_treiber="in Windows enthalten (usbser)",
            windows_link=LINK_EUROLITE,
            naechster_schritt="Geplant. Bis dahin: Art-Net-Adapter nehmen."),
    Familie("selbstbau", "Selbstbau seriell (Arduino, ESP, CH340, CP210x)",
            STATUS_GEPLANT,
            linux=(_LINUX_SERIELL + " Erscheint ein CH340 nicht als "
                   "/dev/ttyUSB*, hält ihn oft der Braille-Dienst brltty fest."),
            linux_befehl=BEFEHL_DIALOUT,
            windows_treiber="Treiber des Chip-Herstellers (siehe Zeile)",
            naechster_schritt=(
                "Wird erkannt, aber noch nicht angesteuert (geplant; Anleitung "
                "und Beispiel-Sketch folgen). Spricht der eigene Aufbau das "
                "Pro-Format mit 57600 Baud, lässt er sich schon jetzt im "
                "Reiter „Enttec Pro USB“ von Hand wählen.")),
    Familie("udmx", "uDMX (USB, ohne COM-Port)",
            STATUS_UNTERSTUETZT, ausgabe_art="uDMX", bus=BUS_USB,
            linux=_LINUX_UDMX, linux_befehl=BEFEHL_UDMX,
            windows_treiber=("WinUSB — muss dem Gerät einmalig von Hand "
                             "zugewiesen werden (noch nicht am Gerät erprobt)"),
            windows_link=LINK_WINUSB,
            naechster_schritt="Als Ausgabe einrichten (Art „uDMX“)."),
    Familie("udmx_geplant", "uDMX-Verwandte (USB, ohne COM-Port)",
            STATUS_GEPLANT, bus=BUS_USB,
            linux="Kein Treiber nötig; Zugriffsrecht per udev-Regel (folgt).",
            windows_treiber="WinUSB — von Hand zuzuweisen",
            windows_link=LINK_WINUSB,
            naechster_schritt="Geplant. Bis dahin: Art-Net-Adapter nehmen."),
    Familie("nische", "Sonderbauformen (eigenes Protokoll)",
            STATUS_NICHT, bus=BUS_USB, linux=_LINUX_KEINER,
            windows_treiber="—",
            naechster_schritt=(
                "Wird nicht unterstützt. Ausweg: ein Art-Net- oder sACN-Adapter "
                "(Ethernet→DMX) — der läuft mit jeder Software.")),
    Familie("hid", "HID-Adapter (FX5, Nodle, Digital Enlightenment)",
            STATUS_NICHT, bus=BUS_HID, linux=_LINUX_KEINER,
            windows_treiber="in Windows enthalten (HID)",
            naechster_schritt=(
                "Wird nicht unterstützt. Ausweg: ein Art-Net- oder "
                "sACN-Adapter (Ethernet→DMX).")),
    Familie("proprietaer", "An Herstellersoftware gebundene Interfaces",
            STATUS_NICHT, bus=BUS_USB, linux=_LINUX_KEINER,
            windows_treiber="nur mit der Software des Herstellers",
            naechster_schritt=(
                "Dieses Interface arbeitet nur mit der Software seines "
                "Herstellers (eigenes, geschütztes Protokoll). Ausweg: ein "
                "Art-Net- oder sACN-Adapter (Ethernet→DMX).")),
    Familie("artnet", "Art-Net (Ethernet→DMX)",
            STATUS_UNTERSTUETZT, ausgabe_art="ArtNet", bus=BUS_NETZ,
            linux="Kein Treiber. PC und Adapter brauchen Adressen im selben Netz.",
            windows_treiber="keiner; Firewall-Freigabe für LightOS",
            naechster_schritt="Im Reiter „Art-Net“ einrichten."),
    Familie("sacn", "sACN / E1.31 (Ethernet→DMX)",
            STATUS_UNTERSTUETZT, ausgabe_art="sACN", bus=BUS_NETZ,
            linux="Kein Treiber. PC und Adapter brauchen Adressen im selben Netz.",
            windows_treiber="keiner; Firewall-Freigabe für LightOS",
            naechster_schritt="Im Reiter „sACN (E1.31)“ einrichten."),
)}


@dataclass(frozen=True)
class Eintrag:
    """Eine Zeile der Kenntnis-Tabelle.

    ``vid``/``pid`` ``None`` = beliebig (``pid``) bzw. reine Texterkennung
    (``vid``). Die Text-Merkmale werden klein und als Teilstring verglichen;
    mehrere Merkmale eines Feldes sind Alternativen.
    """
    vid: int | None
    pid: int | None
    familie: str
    name: str
    hersteller: tuple[str, ...] = ()
    produkt: tuple[str, ...] = ()
    geprueft: str = PRUEF_SPEZ
    pruef_notiz: str = ""
    #: Kennung nicht aus einer nachlesbaren Quelle — ehrlich kennzeichnen.
    vermutet: bool = False
    #: Abweichender Windows-Treiber/Link (sonst der der Familie).
    windows_treiber: str = ""
    windows_link: str = ""

    @property
    def hat_merkmal(self) -> bool:
        return bool(self.hersteller or self.produkt)

    @property
    def kennung(self) -> str:
        if self.vid is None:
            return "(Name)"
        return f"{self.vid:04x}:" + ("*" if self.pid is None else f"{self.pid:04x}")


def _e(vid, pid, familie, name, **kw) -> Eintrag:
    kw.setdefault("geprueft", {
        STATUS_GEPLANT: PRUEF_GEPLANT, STATUS_NICHT: PRUEF_NICHT,
    }.get(FAMILIEN[familie].status, PRUEF_SPEZ))
    return Eintrag(vid, pid, familie, name, **kw)


_CH340 = dict(windows_treiber="CH341SER (WCH)", windows_link=LINK_WCH)
_CP210 = dict(windows_treiber="CP210x Universal Windows Driver (Silicon Labs)",
              windows_link=LINK_SILABS)
_CDC = dict(windows_treiber="in Windows enthalten (usbser, ab Windows 10)")

#: ★ Reihenfolge zaehlt: bei gleicher Kennung gewinnt die ERSTE Zeile, deren
#: Text-Merkmal passt; die Zeile ohne Merkmal ist der Rueckfall und steht
#: deshalb zuletzt. („DMX USB PRO Mk2“ vor „DMX USB PRO“.)
EINTRAEGE: tuple[Eintrag, ...] = (
    # ── FTDI 0403:6001 — eine Kennung, viele Geraete ─────────────────────────
    _e(0x0403, 0x6001, "pro", "Enttec DMX USB Pro Mk2 (1. Universum)",
       produkt=("dmx usb pro mk2",), vermutet=True),
    _e(0x0403, 0x6001, "pro", "Enttec DMX USB Pro", produkt=("dmx usb pro",)),
    _e(0x0403, 0x6001, "pro", "DMXking ultraDMX", produkt=("ultradmx",)),
    _e(0x0403, 0x6001, "pro", "DMXIS", produkt=("dmxis",)),
    _e(0x0403, 0x6001, "nische", "Vince USB-DMX512",
       produkt=("usb-dmx512 converter",)),
    _e(0x0403, 0x6001, "ftdi_unklar",
       "FTDI-Adapter (FT232) — Enttec Pro, Open DMX oder Eurolite Pro Mk2?",
       geprueft=PRUEF_GERAET,
       pruef_notiz=("Linux, ein Pro-kompatibler FT232-Adapter über die Art "
                    "„Enttec“; „Open DMX“-Kabel sind geplant")),
    _e(0x0403, 0x6010, "ftdi_sonstig", "FTDI FT2232 (zwei Kanäle)", vermutet=True),
    _e(0x0403, 0x6014, "ftdi_sonstig", "FTDI FT232H", vermutet=True),
    _e(0x0403, 0x6015, "ftdi_sonstig", "FTDI FT230X / FT231X", vermutet=True),
    _e(0x0403, 0xC850, "nische", "DMX4ALL USB-Interface"),
    # ── Eurolite ─────────────────────────────────────────────────────────────
    _e(0x04D8, 0xFA63, "eurolite_pro", "Eurolite USB-DMX512 PRO (altes Modell)",
       hersteller=("eurolite",), produkt=("eurolite",)),
    # ── Selbstbau: serielle Wandler und Boards ───────────────────────────────
    _e(0x1A86, 0x7523, "selbstbau", "WCH CH340 (z. B. Arduino Nano-Nachbau)",
       **_CH340),
    _e(0x1A86, 0x5523, "selbstbau", "WCH CH341", vermutet=True, **_CH340),
    _e(0x1A86, 0x55D4, "selbstbau", "WCH CH9102", vermutet=True, **_CH340),
    _e(0x10C4, 0xEA60, "selbstbau", "Silicon Labs CP210x (z. B. ESP32-Board)",
       **_CP210),
    _e(0x2341, None, "selbstbau", "Arduino (Originalboard)", vermutet=True,
       windows_treiber="in Windows enthalten; sonst mit der Arduino-IDE",
       windows_link=LINK_ARDUINO),
    _e(0x2A03, None, "selbstbau", "Arduino (arduino.org-Board)", vermutet=True,
       windows_treiber="in Windows enthalten; sonst mit der Arduino-IDE",
       windows_link=LINK_ARDUINO),
    _e(0x303A, None, "selbstbau", "Espressif ESP32 (eigener USB-Anschluss)",
       vermutet=True, **_CDC),
    # ── uDMX ─────────────────────────────────────────────────────────────────
    _e(0x2008, 0x1066, "udmx", "CYL-6602 „USB-DMX512“ (Sun-light USBDMX512)",
       geprueft=PRUEF_GERAET,
       pruef_notiz="Linux, Kommunikation; Ausgang mit Gerät noch offen"),
    # 16c0:05dc ist eine GETEILTE Kennung (V-USB): nur mit beiden Texten.
    _e(0x16C0, 0x05DC, "udmx", "Anyma uDMX und Nachbauten",
       hersteller=("www.anyma.ch",), produkt=("udmx",)),
    _e(0x03EB, 0x8888, "udmx_geplant", "AVLdiy D512",
       hersteller=("avldiy",), produkt=("d512",)),
    # ── Sonderbauformen ──────────────────────────────────────────────────────
    _e(0x10CF, 0x8062, "nische", "Velleman K8062 / VM116"),
    _e(0x03EB, 0x2018, "nische", "DMX4ALL NanoDMX"),
    _e(0x0CE1, None, "nische", "Peperoni / Lighting Solutions"),
    _e(0x0A30, 0x0002, "nische", "DMXCreator 512 Basic"),
    _e(0x0483, 0x57FE, "nische", "ShowJockey SJ-DMX-U1"),
    _e(0x16C0, 0x088B, "hid", "FX5 USB DMX"),
    _e(0x04B4, 0x0F1F, "hid", "Digital Enlightenment USB DMX"),
    _e(0x16D0, 0x0830, "hid", "DMXControl Nodle U1"),
    _e(0x16D0, 0x0833, "hid", "DMXControl Nodle R4S"),
    # ── An Herstellersoftware gebunden ───────────────────────────────────────
    _e(0x0962, 0x2000, "proprietaer", "Sunlite USBDMX2 (ohne Firmware)"),
    _e(0x0962, 0x2001, "proprietaer", "Sunlite USBDMX2"),
    # Ohne belegte Kennung: nur am Namen erkannt (nur aus passiven Quellen).
    _e(None, None, "proprietaer", "Nicolaudie / Sunlite (SIUDI, SUT)",
       hersteller=("nicolaudie", "sunlite"), produkt=("siudi", "sunlite suite"),
       vermutet=True),
    _e(None, None, "proprietaer", "ADJ myDMX", produkt=("mydmx",), vermutet=True),
    _e(None, None, "proprietaer", "Chauvet Xpress", produkt=("xpress",),
       vermutet=True),
)

#: Netzwerk-Zeilen der Kompatibilitaetsliste (haben keine USB-Kennung).
NETZ_ZEILEN: tuple[tuple[str, str], ...] = (
    ("artnet", "Art-Net-Adapter aller Hersteller, ESP32-Selbstbau, Pi mit OLA"),
    ("sacn", "sACN-Adapter (E1.31)"),
)


# ── Zuordnung ────────────────────────────────────────────────────────────────

def _passt_text(merkmale: tuple[str, ...], text: str) -> bool:
    t = (text or "").lower()
    return any(m in t for m in merkmale)


def _passt_wort(merkmale: tuple[str, ...], text: str) -> bool:
    """Wie :func:`_passt_text`, aber das Merkmal muss an einem WORTANFANG
    stehen. Fuer Zeilen ohne Kennung: dort entscheidet allein der Text, und
    „xpress“ steckt sonst in jedem „Express“ (USB-Stick „Cruzer Express“ wuerde
    als Chauvet-Interface gemeldet)."""
    t = (text or "").lower()
    return any(re.search(r"(?<![a-z0-9])" + re.escape(m), t) for m in merkmale)


def _merkmal_passt(e: Eintrag, hersteller: str, produkt: str) -> bool:
    """Bei reinen Namens-Zeilen genuegt EIN Feld, sonst muessen alle
    angegebenen Felder passen (geteilte Kennung: Hersteller UND Produkt)."""
    passt = _passt_wort if e.vid is None else _passt_text
    treffer = []
    if e.hersteller:
        treffer.append(passt(e.hersteller, hersteller))
    if e.produkt:
        treffer.append(passt(e.produkt, produkt))
    if e.vid is None:
        return any(treffer)
    return all(treffer)


def ordne_ein(vid, pid, hersteller: str = "", produkt: str = "") -> Eintrag | None:
    """Kennung (+ Texte) -> Tabellenzeile, oder ``None`` = unbekannt."""
    rueckfall = None
    for e in EINTRAEGE:
        if e.vid is None:
            continue
        if e.vid != vid or (e.pid is not None and e.pid != pid):
            continue
        if not e.hat_merkmal:
            rueckfall = rueckfall or e
        elif _merkmal_passt(e, hersteller, produkt):
            return e
    if rueckfall is not None:
        return rueckfall
    if hersteller or produkt:
        for e in EINTRAEGE:
            if e.vid is None and _merkmal_passt(e, hersteller, produkt):
                return e
    return None


def kennung_bekannt(vid, pid) -> bool:
    """Steht diese Kennung ueberhaupt in der Tabelle? (Nur dann duerfen ueber
    pyusb Texte gelesen werden.)"""
    return any(e.vid == vid and (e.pid is None or e.pid == pid)
               for e in EINTRAEGE if e.vid is not None)


def ist_pro_kandidat(vid, pid, hersteller: str = "", produkt: str = "") -> int:
    """Fuer ``enttec_pro.find_enttec_port``: 2 = eindeutig Pro-Format,
    1 = FTDI mit unklarem Typ (koennte ein Pro sein), 0 = nein."""
    e = ordne_ein(vid, pid, hersteller, produkt)
    if e is None or vid != 0x0403 or pid != 0x6001:
        return 0
    if e.familie == "pro":
        return 2
    return 1 if e.familie == "ftdi_unklar" else 0


# ── Rohdaten ─────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class RohGeraet:
    """Was das Betriebssystem ueber ein Geraet weiss — nichts davon erfragt."""
    vid: int | None = None
    pid: int | None = None
    hersteller: str = ""
    produkt: str = ""
    seriennummer: str = ""
    port: str = ""            # /dev/ttyUSB0, COM3 — leer bei rohem USB
    ort: str = ""             # USB-Anschluss „1-2.3“
    dev_pfad: str = ""        # /dev/bus/usb/001/005 (Linux)
    treiber: tuple[str, ...] = ()
    quelle: str = ""

    @property
    def kennung(self) -> str:
        if self.vid is None or self.pid is None:
            return "—"
        return f"{self.vid:04x}:{self.pid:04x}"


def _hex(wert) -> int | None:
    try:
        return int(str(wert).strip(), 16)
    except (TypeError, ValueError):
        return None


def _lies(pfad: str) -> str:
    try:
        with open(pfad, encoding="utf-8", errors="replace") as f:
            return f.read().strip()
    except OSError:
        return ""


def lies_sysfs(wurzel: str = "/sys/bus/usb/devices") -> list[RohGeraet]:
    """Linux: USB-Geraete aus ``sysfs`` — reine Dateilektuere, der Kernel hat
    Kennung und Texte beim Einstecken schon gelesen. Hubs bleiben aussen vor."""
    try:
        namen = sorted(os.listdir(wurzel))
    except OSError:
        return []
    raus = []
    for name in namen:
        if ":" in name or name.startswith("usb"):
            continue
        basis = os.path.join(wurzel, name)
        vid, pid = _hex(_lies(f"{basis}/idVendor")), _hex(_lies(f"{basis}/idProduct"))
        if vid is None or pid is None or _lies(f"{basis}/bDeviceClass") == "09":
            continue
        treiber, port = [], ""
        for schnitt in namen:
            if not schnitt.startswith(name + ":"):
                continue
            sbasis = os.path.join(wurzel, schnitt)
            try:
                treiber.append(os.path.basename(os.readlink(f"{sbasis}/driver")))
            except OSError:
                pass
            for ordner in (sbasis, os.path.join(sbasis, "tty")):
                try:
                    for kind in sorted(os.listdir(ordner)):
                        if kind.startswith("tty") and kind != "tty" and not port:
                            port = "/dev/" + kind
                except OSError:
                    pass
        try:
            dev = "/dev/bus/usb/%03d/%03d" % (int(_lies(f"{basis}/busnum")),
                                              int(_lies(f"{basis}/devnum")))
        except ValueError:
            dev = ""
        raus.append(RohGeraet(
            vid=vid, pid=pid, hersteller=_lies(f"{basis}/manufacturer"),
            produkt=_lies(f"{basis}/product"), seriennummer=_lies(f"{basis}/serial"),
            port=port, ort=name, dev_pfad=dev, treiber=tuple(treiber),
            quelle="sysfs"))
    return raus


def lies_seriell(comports=None) -> list[RohGeraet]:
    """Serielle Ports aus pyserial — nur die Liste, kein Port wird geoeffnet.
    Ports ohne USB-Kennung (eingebaute, Bluetooth) bleiben aussen vor."""
    if comports is None:
        try:
            from serial.tools import list_ports
            comports = list_ports.comports
        except Exception:                                # noqa: BLE001
            return []
    raus = []
    try:
        ports = list(comports())
    except Exception:                                    # noqa: BLE001
        return []
    for p in ports:
        vid, pid = getattr(p, "vid", None), getattr(p, "pid", None)
        if vid is None or pid is None:
            continue
        ort = str(getattr(p, "location", "") or "").split(":")[0]
        raus.append(RohGeraet(
            vid=vid, pid=pid,
            hersteller=str(getattr(p, "manufacturer", "") or ""),
            produkt=str(getattr(p, "product", "") or ""),
            seriennummer=str(getattr(p, "serial_number", "") or ""),
            port=str(getattr(p, "device", "") or ""), ort=ort, quelle="seriell"))
    return raus


def lies_pyusb(usb=None) -> list[RohGeraet]:
    """USB-Geraeteliste ueber pyusb — **ohne ein Geraet zu oeffnen**.

    Kennung und Anschluss stehen in der Liste, die libusb ohnehin fuehrt.
    Texte (Hersteller/Produkt/Seriennummer) kosten eine Standard-Abfrage an das
    Geraet; die gibt es NUR fuer Kennungen aus der Tabelle. Alles andere wird
    weder gelesen noch gemeldet. Fehlt pyusb/libusb: leere Liste.
    """
    try:
        from src.core.dmx import udmx
        core, _util, backend = usb or udmx._usb_laden()
        kw = {"find_all": True}
        if backend is not None:
            kw["backend"] = backend
        gefunden = list(core.find(**kw) or [])
    except Exception:                                    # noqa: BLE001
        return []
    raus = []
    for dev in gefunden:
        vid, pid = getattr(dev, "idVendor", None), getattr(dev, "idProduct", None)
        if not kennung_bekannt(vid, pid):
            continue                       # fremdes Geraet: voellig unberuehrt
        hersteller, _ = udmx._text(dev, "manufacturer", "iManufacturer")
        produkt, _ = udmx._text(dev, "product", "iProduct")
        serie, _ = udmx._text(dev, "serial_number", "iSerialNumber")
        bus, ports = getattr(dev, "bus", None), getattr(dev, "port_numbers", None)
        ort = (f"{bus}-" + ".".join(str(p) for p in ports)
               if bus is not None and ports else "")
        raus.append(RohGeraet(vid=vid, pid=pid, hersteller=hersteller,
                              produkt=produkt, seriennummer=serie, ort=ort,
                              quelle="pyusb"))
    return raus


def fuehre_zusammen(usb: list[RohGeraet], seriell: list[RohGeraet]) -> list[RohGeraet]:
    """Dasselbe Geraet steht in der USB- UND in der Portliste: zusammenlegen
    (Anschluss, sonst Kennung + Seriennummer). Der Port kommt aus der Portliste."""
    raus = list(usb)
    for s in seriell:
        ziel = None
        for i, u in enumerate(raus):
            if (u.vid, u.pid) != (s.vid, s.pid) or (u.port and u.port != s.port):
                continue
            if (s.ort and u.ort == s.ort) or (
                    s.seriennummer and u.seriennummer == s.seriennummer) or (
                    not s.ort and not s.seriennummer):
                ziel = i
                break
        if ziel is None:
            raus.append(s)
        else:
            u = raus[ziel]
            raus[ziel] = replace(
                u, port=s.port or u.port, hersteller=u.hersteller or s.hersteller,
                produkt=u.produkt or s.produkt,
                seriennummer=u.seriennummer or s.seriennummer)
    return raus


# ── Befund ───────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Befund:
    """Ein gefundenes Geraet mit Klartext — die UI formuliert nichts selbst."""
    geraet: RohGeraet
    eintrag: Eintrag | None
    code: str
    titel: str
    text: str
    #: Was auf DIESEM Betriebssystem einmalig zu tun ist (leer = nichts).
    hilfe: str = ""
    befehl: str = ""          # kopierbar, wird nie ausgefuehrt (Linux)
    link: str = ""            # Herstellerseite (Windows)
    #: Ausgabe-Art und Ziel, wenn sich das Geraet einrichten laesst.
    einrichten_als: str = ""
    einrichten_ziel: str = ""
    universum: int | None = None       # schon eingerichtet auf …
    vermutet: bool = False
    extra: dict = field(default_factory=dict, compare=False)

    @property
    def ampel(self) -> str:
        return _AMPEL.get(self.code, AMPEL_GRAU)

    @property
    def wort(self) -> str:
        return BEFUND_WORT.get(self.code, self.code)

    @property
    def familie(self) -> Familie | None:
        return FAMILIEN.get(self.eintrag.familie) if self.eintrag else None

    @property
    def bekannt(self) -> bool:
        return self.eintrag is not None

    @property
    def identitaet(self) -> str:
        """Woran der Einsteck-Waechter dasselbe Geraet wiedererkennt."""
        g = self.geraet
        return f"{g.kennung}|{g.seriennummer or g.ort or g.port}"

    def unterzeile(self) -> str:
        """„0403:6001 · /dev/ttyUSB0 · FT232R USB UART“ (ohne Seriennummer)."""
        g = self.geraet
        teile = [g.kennung]
        if g.port:
            teile.append(g.port)
        elif g.ort:
            teile.append(f"USB-Anschluss {g.ort}")
        name = " ".join(t for t in (g.hersteller, g.produkt) if t)
        if name:
            teile.append(f"meldet sich als „{name}“")
        return " · ".join(teile)


def maskiere(seriennummer: str) -> str:
    """Seriennummer fuers Diagnosepaket: zwei Zeichen + Laenge, nie ganz."""
    s = (seriennummer or "").strip()
    if not s:
        return ""
    return f"{s[:2]}…({len(s)} Zeichen)"


def _system() -> str:
    return "windows" if sys.platform.startswith("win") else "linux"


def _zugriff(pfad: str) -> bool:
    try:
        return os.access(pfad, os.R_OK | os.W_OK)
    except OSError:
        return False


def _belegt(port: str) -> list:
    """Linux: wer haelt den Port? (liest nur ``/proc``; Windows: keine Auskunft,
    dort muesste man den Port oeffnen — und das tut die Erkennung nie.)"""
    if _system() != "linux":
        return []
    try:
        from src.core.dmx.port_check import port_belegt_von
        return port_belegt_von(port)
    except Exception:                                    # noqa: BLE001
        return []


def _udmx_schluessel(g: RohGeraet) -> str:
    if g.seriennummer:
        return f"{g.kennung}#{g.seriennummer}"
    return f"{g.kennung}@{g.ort}" if g.ort else g.kennung


def bewerte(g: RohGeraet, *, system: str | None = None, zugriff=None,
            belegt=None, usb_bibliothek: bool | None = None,
            eingerichtet: dict | None = None) -> Befund:
    """Rohdaten -> Befund. Alle Systemfragen sind einsetzbar (Tests).

    ``eingerichtet`` = ``{Port oder uDMX-Schluessel: Universum}`` der schon
    angelegten Ausgaben — dann meldet der Befund „eingerichtet“ statt „bereit“
    (und fragt nicht mehr, wer den Port haelt: das ist LightOS selbst).
    """
    system = system or _system()
    zugriff = zugriff or _zugriff
    belegt = belegt or _belegt
    eingerichtet = eingerichtet or {}
    e = ordne_ein(g.vid, g.pid, g.hersteller, g.produkt)
    if e is None:
        return Befund(g, None, B_UNBEKANNT, "Unbekannter serieller USB-Adapter",
                      "LightOS kennt dieses Gerät nicht und spricht es nicht an. "
                      "Ist es ein DMX-Interface im Pro-Format, lässt es sich im "
                      "Reiter „Enttec Pro USB“ von Hand wählen.")
    fam = FAMILIEN[e.familie]
    hilfe = fam.linux if system == "linux" else (
        f"Treiber: {e.windows_treiber or fam.windows_treiber}")
    basis = dict(hilfe=hilfe, vermutet=e.vermutet,
                 befehl=fam.linux_befehl if system == "linux" else "",
                 link=(e.windows_link or fam.windows_link)
                 if system == "windows" else "")

    def raus(code, text, **kw):
        return Befund(g, e, code, e.name, text, **{**basis, **kw})

    if fam.status == STATUS_NICHT:
        return raus(B_NICHT_UNTERSTUETZT, fam.naechster_schritt, befehl="", link="")
    seriell = fam.bus == BUS_SERIELL
    if seriell and not g.port:
        if system == "windows":
            text = ("Das Gerät ist am USB sichtbar, hat aber keinen COM-Port — "
                    "Windows hat keinen Treiber dafür. Treiber von der Seite des "
                    "Herstellers installieren, dann neu einstecken.")
        else:
            text = ("Das Gerät ist am USB sichtbar, hat aber keinen seriellen "
                    "Port. Bei CH340-Adaptern hält oft der Braille-Dienst brltty "
                    "das Gerät fest; sonst einmal neu einstecken.")
        return raus(B_TREIBER_FEHLT, text)
    if fam.status == STATUS_GEPLANT:
        return raus(B_GEPLANT, fam.naechster_schritt)

    ziel = g.port if seriell else _udmx_schluessel(g)
    fertig = dict(einrichten_als=fam.ausgabe_art, einrichten_ziel=ziel)
    if ziel in eingerichtet:
        return raus(B_EINGERICHTET,
                    f"Als Ausgabe „{fam.ausgabe_art}“ für Universe "
                    f"{eingerichtet[ziel]} eingerichtet."
                    + (" Der Typ lässt sich an der USB-Kennung nicht ablesen — "
                       "solange das Licht reagiert, ist alles richtig."
                       if fam.typ_unklar else ""),
                    universum=eingerichtet[ziel], **fertig)
    if not seriell and usb_bibliothek is False:
        return raus(B_BIBLIOTHEK_FEHLT,
                    "Erkannt — für uDMX-Adapter fehlt aber das Zusatzpaket "
                    "pyusb (siehe INSTALL.md, „uDMX-Adapter“).", befehl="", link="")
    pfad = g.port if seriell else g.dev_pfad
    if system == "linux" and pfad and not zugriff(pfad):
        return raus(B_KEINE_BERECHTIGUNG,
                    "Erkannt, aber dieses Benutzerkonto darf das Gerät nicht "
                    "benutzen. Einmalig einrichten (Befehl unten), dann neu "
                    "anmelden bzw. neu einstecken.", **fertig)
    if seriell:
        halter = belegt(g.port)
        if halter:
            wer = halter[0][1] or f"PID {halter[0][0]}"
            return raus(B_BELEGT,
                        f"Ein anderes Programm hält den Port offen ({wer}). "
                        f"Erst dort schließen (z. B. QLC+ oder eine zweite "
                        f"LightOS-Instanz).", extra={"halter": halter}, **fertig)
    if fam.typ_unklar:
        return raus(B_TYP_UNKLAR,
                    "An der USB-Kennung ist nicht zu erkennen, ob das ein "
                    "Enttec-Pro-kompatibler Adapter oder ein „Open DMX“-Kabel "
                    "ist. Bitte prüfen: Pro-kompatible laufen über die Art "
                    "„Enttec“ (einrichten und Testsignal senden); reine "
                    "„Open DMX“-Kabel werden noch nicht unterstützt.", **fertig)
    text = f"Bereit. {fam.naechster_schritt}"
    if not seriell and system == "windows":
        text += (" Unter Windows muss dem Gerät vorher einmalig der "
                 "WinUSB-Treiber zugewiesen sein.")
    return raus(B_BEREIT, text, **fertig)


def erkenne(*, quellen=None, system: str | None = None, schnell: bool = False,
            **bewertung) -> list[Befund]:
    """Alle angeschlossenen Interfaces als Befunde — passiv.

    ``quellen`` = ``(usb_liste, serielle_liste)`` fuer Tests. Ohne Angabe:
    Linux ``sysfs`` + Portliste, sonst pyusb-Liste + Portliste (``schnell``:
    ohne pyusb — fuer die Abfrage im Hintergrund).

    ``LIGHTOS_KEIN_USB=1`` schaltet die Erkennung ab (Testlaeufe, Fehlersuche).
    Unbekannte Geraete erscheinen nur, wenn sie ein serieller USB-Adapter sind.
    """
    system = system or _system()
    if quellen is None:
        if os.environ.get("LIGHTOS_KEIN_USB"):
            return []
        if system == "linux":
            usb = lies_sysfs()
        else:
            usb = [] if schnell else lies_pyusb()
        quellen = (usb, lies_seriell())
    usb, seriell = quellen
    befunde = []
    for g in fuehre_zusammen(list(usb), list(seriell)):
        b = bewerte(g, system=system, **bewertung)
        if b.eintrag is None and not g.port:
            continue                  # irgendein USB-Geraet: geht uns nichts an
        befunde.append(b)
    befunde.sort(key=lambda b: (not b.bekannt, b.geraet.kennung,
                                b.geraet.port, b.geraet.ort))
    return befunde


def eingerichtete_ziele(output_manager) -> dict:
    """``{Port bzw. uDMX-Schluessel: Universum}`` der angelegten USB-Ausgaben."""
    raus = {}
    try:
        for e in output_manager.ausgabe_status():
            if e.get("weg") in ("Enttec", "uDMX") and e.get("ziel"):
                raus.setdefault(str(e["ziel"]), int(e["universum"]))
    except Exception:                                    # noqa: BLE001
        pass
    return raus


# ── Einsteck-Waechter ────────────────────────────────────────────────────────

class EinsteckWaechter:
    """Merkt, wenn im Betrieb ein BEKANNTES Interface dazukommt.

    Der erste Aufruf legt nur den Ausgangsstand fest — was beim Start schon
    steckt, ist keine Neuigkeit. Abziehen und Wiedereinstecken meldet erneut.
    """

    def __init__(self):
        self._gesehen: set[str] | None = None

    def neue(self, befunde) -> list[Befund]:
        bekannte = [b for b in befunde if b.bekannt]
        jetzt = {b.identitaet for b in bekannte}
        vorher, self._gesehen = self._gesehen, jetzt
        if vorher is None:
            return []
        return [b for b in bekannte if b.identitaet not in vorher]


def hinweis_text(befunde) -> str:
    """Statusleisten-Text fuer neu eingesteckte Interfaces."""
    namen = [b.titel for b in befunde]
    if not namen:
        return ""
    was = namen[0] if len(namen) == 1 else f"{namen[0]} und {len(namen) - 1} weitere"
    return f"Neues DMX-Interface erkannt: {was} — Einrichten…"


# ── Diagnose und Doku ────────────────────────────────────────────────────────

def diagnose_zeilen(befunde) -> list[str]:
    """Zeilen fuers Diagnosepaket — Kennung, Befund, Port; Seriennummer nur
    maskiert, kein Benutzer- oder Rechnername."""
    raus = []
    for b in befunde:
        g = b.geraet
        teile = [g.kennung, b.titel, f"Befund: {b.wort}"]
        if g.port:
            teile.append(f"Port {g.port}")
        elif g.ort:
            teile.append(f"USB-Anschluss {g.ort}")
        if g.produkt:
            teile.append(f"Produkttext „{g.produkt}“")
        if g.seriennummer:
            teile.append(f"Seriennr. {maskiere(g.seriennummer)}")
        if g.treiber:
            teile.append("Kernel-Treiber " + ",".join(sorted(set(g.treiber))))
        if b.universum is not None:
            teile.append(f"Universe {b.universum}")
        raus.append(" · ".join(teile))
    return raus


DOKU_ANFANG = "<!-- INTERFACE-TABELLE:ANFANG (erzeugt aus src/core/dmx/interfaces.py) -->"
DOKU_ENDE = "<!-- INTERFACE-TABELLE:ENDE -->"


def _zelle(text: str) -> str:
    return (text or "—").replace("|", "/").replace("\n", " ")


def doku_tabelle() -> str:
    """Die Kompatibilitaetsliste als Markdown-Tabelle — steht wortgleich in
    :data:`DOKU_DATEI` (Test gleicht ab). Neu erzeugen:
    ``python -m src.core.dmx.interfaces``."""
    zeilen = [
        "| Gerät | USB-Kennung | Status in LightOS | Geprüft | Linux | Windows-Treiber |",
        "|---|---|---|---|---|---|",
    ]

    def zeile(name, kennung, fam, geprueft, treiber, link):
        win = _zelle(treiber)
        if link:
            win += f" — [Herstellerseite]({link})"
        zeilen.append(f"| {_zelle(name)} | {kennung} | {fam.status_text()} | "
                      f"{_zelle(geprueft)} | {_zelle(fam.linux)} | {win} |")

    for e in EINTRAEGE:
        fam = FAMILIEN[e.familie]
        kennung = f"`{e.kennung}`" if e.vid is not None else "am Namen"
        if e.hat_merkmal and e.vid is not None:
            kennung += " + Name"
        if e.vermutet:
            kennung += " (vermutet)"
        geprueft = e.geprueft + (f" ({e.pruef_notiz})" if e.pruef_notiz else "")
        zeile(e.name, kennung, fam, geprueft,
              e.windows_treiber or fam.windows_treiber,
              e.windows_link or fam.windows_link)
    for schluessel, name in NETZ_ZEILEN:
        fam = FAMILIEN[schluessel]
        zeile(name, "Netzwerk", fam, PRUEF_SPEZ, fam.windows_treiber, "")
    return "\n".join(zeilen)


if __name__ == "__main__":                               # pragma: no cover
    print(DOKU_ANFANG)
    print(doku_tabelle())
    print(DOKU_ENDE)
