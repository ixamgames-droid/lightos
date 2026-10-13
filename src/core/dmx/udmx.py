"""OUT-68: uDMX-Adapter (rohes USB, Control-Transfers) — Treiber.

Das uDMX-Protokoll (Anyma uDMX und Klone) kennt keine Endpunkte: alles laeuft
ueber Vendor-Control-Transfers an das Geraet.

======================  =====================================================
``bmRequestType``       ``0x40`` (Host -> Geraet, Vendor, Empfaenger Geraet)
``bRequest`` 2          Kanalbereich: ``wValue`` = Anzahl, ``wIndex`` =
                        Startkanal (0-basiert), Daten = Kanalwerte
``bRequest`` 1          Einzelkanal — wird hier NICHT benutzt
======================  =====================================================

★ **Es wird ausschliesslich ``bRequest`` 2 gesendet.** uDMX kennt einen
Bootloader-Befehl (``0xf8``); ein Treiber, der beliebige Request-Nummern
durchreicht, kann einen Adapter in den Firmware-Modus schicken. Die Nummer ist
deshalb eine Konstante und kein Parameter — der Test
``test_out68_udmx_treiber.py`` haelt das fest.

Am Geraet geprueft (CYL-6602 „USB-DMX512", meldet sich als Sun-light
USBDMX512, USB ``2008:1066``, Low-Speed, Vendor-Klasse, 0 Endpunkte): 512 Byte
in EINEM Transfer werden angenommen, rund 17 ms je Universum.

**Nur geaenderte Bereiche senden? Nein.** Geprueft und verworfen:

* Ein volles Bild (~17 ms) passt in den 44-Hz-Takt (22,7 ms). Ein Teilbereich
  spart nur dann Zeit, wenn sich wenig aendert — also genau dann, wenn ohnehin
  keine Eile besteht.
* Der Adapter haelt seinen eigenen Stand. Nach Neustecken, Spannungseinbruch
  oder einem verlorenen Transfer weicht er vom Stand des Rechners ab; ein
  Treiber, der nur Aenderungen schickt, bemerkt das nie.
* Sicherheit: Blackout und Laser-NOT-AUS muessen den Adapter sicher erreichen.
  Ein Bild, das immer ganz gesendet wird, braucht dafuer keinen Sonderweg.

Deshalb: **jedes Bild ganz, in jedem Takt** — das regelmaessige Voll-Senden
ist der Normalfall und kein Zusatz.

``pyusb`` (und darunter libusb) ist eine OPTIONALE Abhaengigkeit: importiert
wird erst bei Bedarf. Fehlt etwas, gibt es einen :class:`UdmxFehler` mit Code
und einem Satz, der sagt, was zu tun ist — die App laeuft weiter.

Dieses Modul importiert weder Qt noch ``app_state``: es laeuft auch im
Sende-Prozess (``udmx_process``), der per ``spawn`` gestartet wird.
"""
from __future__ import annotations

import errno
import sys
import time
from dataclasses import dataclass, field

DMX_BYTES = 512

# ── Protokoll (Konstanten, keine Parameter — s. Modul-Doku) ──────────────────
REQUEST_TYPE_OUT = 0x40          # Host -> Geraet | Vendor | Empfaenger Geraet
REQUEST_KANALBEREICH = 2         # cmd_SetChannelRange
#: Zeitlimit EINES Transfers. Ein volles Bild braucht ~17 ms; 250 ms sind
#: reichlich und halten einen haengenden Adapter trotzdem kurz.
TIMEOUT_MS = 250

# ── Gruende (als Zahl, damit sie durch ein Shared-Value passen) ──────────────
G_OK = 0
G_PYUSB_FEHLT = 1
G_LIBUSB_FEHLT = 2
G_NICHT_DA = 3
G_KEINE_BERECHTIGUNG = 4
G_TREIBER_FEHLT = 5
G_BELEGT = 6
G_ANTWORTET_NICHT = 7
G_MEHRDEUTIG = 8
G_NAME_UNKLAR = 9

UDEV_REGEL = "60-lightos-udmx.rules"

# ── OUT-76: Treiber unter Windows — erkennen, erklaeren, verlinken ───────────
#: Lage des Treibers eines Adapters (``UdmxGeraet.treiber``); leer = nicht
#: festgestellt (kein Windows, Abfrage nicht moeglich, mehrere gleiche Adapter
#: mit verschiedener Lage).
T_PASST, T_FEHLT, T_ANDERER = "passt", "fehlt", "anderer"
#: Nur offizielle Seiten. LightOS oeffnet sie nie von selbst.
LINK_ZADIG = "https://zadig.akeo.ie"
LINK_WINUSB = ("https://learn.microsoft.com/windows-hardware/drivers/usbcon/"
               "winusb-installation")


@dataclass(frozen=True)
class Kennung:
    """Eine Zeile der Geraetetabelle."""
    vid: int
    pid: int
    name: str
    #: Erwarteter Hersteller-/Produkttext (klein verglichen). ``None`` = die
    #: Kennung allein ist eindeutig.
    hersteller: str | None = None
    produkt: str | None = None
    #: OLA wertet bei uDMX einen STALL als Erfolg, weil Klone uneinheitlich
    #: antworten. Nur fuer die Original-Kennung uebernommen; am CYL-6602 ist
    #: gemessen, dass der Transfer regulaer bestaetigt wird.
    stall_ist_erfolg: bool = False


#: ★ ``16c0:05dc`` ist eine GETEILTE Kennung (V-USB, „obdev shared ID"): viele
#: Bastelgeraete und Programmer tragen sie. Ohne passenden Hersteller- UND
#: Produkttext ist so ein Geraet kein uDMX und wird nie angesprochen.
BEKANNTE_GERAETE: tuple[Kennung, ...] = (
    Kennung(0x2008, 0x1066, "CYL-6602 / Sun-light USBDMX512"),
    Kennung(0x16C0, 0x05DC, "Anyma uDMX",
            hersteller="www.anyma.ch", produkt="udmx", stall_ist_erfolg=True),
)


class UdmxFehler(Exception):
    """Fehler mit Grund-Code (``G_*``) und fertigem Satz fuer den Nutzer."""

    def __init__(self, code: int, text: str = ""):
        self.code = int(code)
        super().__init__(text or grund_text(code))


@dataclass(frozen=True)
class UdmxGeraet:
    """Ein gefundener Adapter — nur Beschreibung, nichts davon ist geoeffnet."""
    vid: int
    pid: int
    name: str
    hersteller: str = ""
    produkt: str = ""
    seriennummer: str = ""
    bus: int | None = None
    adresse: int | None = None
    #: USB-Anschluss („1-2.3") — bleibt gleich, solange der Adapter an
    #: derselben Buchse steckt. Nur ein Hinweis, kein sicherer Schluessel.
    ort: str = ""
    #: ``False``: Kennung passt, aber der Name liess sich nicht lesen (meist
    #: fehlende Berechtigung) — bei der geteilten Kennung ist dann unklar, ob
    #: es ueberhaupt ein uDMX ist. Solche Geraete werden NICHT angesprochen.
    bestaetigt: bool = True
    hinweis: str = ""
    stall_ist_erfolg: bool = False
    #: OUT-76 (nur Windows): ``T_PASST`` / ``T_FEHLT`` / ``T_ANDERER``, leer =
    #: nicht festgestellt. ``treiber_dienst`` = Name des Treibers laut Windows.
    #: Nur eine AUSKUNFT fuer Liste und Meldung — ob der Adapter sendet,
    #: entscheidet weiterhin allein der Sendeversuch.
    treiber: str = ""
    treiber_dienst: str = ""
    _dev: object = field(default=None, repr=False, compare=False)

    @property
    def kennung(self) -> str:
        return f"{self.vid:04x}:{self.pid:04x}"

    @property
    def schluessel(self) -> str:
        """Woran der Adapter wiedererkannt wird (steht in ``universes.json``):
        Seriennummer, sonst der Anschluss."""
        if self.seriennummer:
            return f"{self.kennung}#{self.seriennummer}"
        if self.ort:
            return f"{self.kennung}@{self.ort}"
        return self.kennung

    def beschriftung(self) -> str:
        teile = [self.name, self.kennung]
        if self.seriennummer:
            teile.append(f"Seriennr. {self.seriennummer}")
        elif self.ort:
            teile.append(f"Anschluss {self.ort}")
        text = " · ".join(teile)
        if not self.bestaetigt:
            return f"{text} — {self.hinweis or 'nicht bestätigt'}"
        zusatz = treiber_kurz(self.treiber, self.treiber_dienst)
        return f"{text} — {zusatz}" if zusatz else text


# ── Texte ────────────────────────────────────────────────────────────────────

def treiber_kurz(lage: str, dienst: str = "") -> str:
    """OUT-76: Zusatz in der Adapter-Liste, leer wenn nichts zu sagen ist."""
    if lage == T_FEHLT:
        return "Treiber fehlt (WinUSB zuweisen)"
    if lage == T_ANDERER:
        wer = f" „{dienst}“" if dienst else ""
        return f"falscher Treiber{wer} (WinUSB nötig)"
    return ""


def windows_treiber_schritte(usb_id: str = "") -> list[str]:
    """OUT-76: der Weg zum WinUSB-Treiber, Schritt fuer Schritt — EINE Quelle
    fuer Dialog, Diagnosepaket und INSTALL.md (der Test vergleicht sie).

    ``usb_id`` = Kennung des gefundenen Adapters (``"2008:1066"``); ohne sie
    stehen beide bekannten Kennungen im Text.
    """
    if usb_id:
        vid, _, pid = usb_id.partition(":")
        welche = f"USB ID {vid.upper()} {pid.upper()}"
    else:
        welche = "USB ID 2008 1066 (CYL-6602) oder 16C0 05DC (Anyma uDMX)"
    return [
        f"Das Programm Zadig laden: {LINK_ZADIG} — ein freies Programm eines "
        f"anderen Anbieters. LightOS liefert und installiert keine Treiber.",
        "Den Adapter einstecken und Zadig starten (Windows fragt nach "
        "Administratorrechten).",
        f"In Zadig im Menü „Options“ den Punkt „List All Devices“ einschalten "
        f"und in der Liste den Adapter wählen — zu erkennen an {welche}.",
        "Als Treiber „WinUSB“ einstellen und auf „Install Driver“ (oder "
        "„Replace Driver“) klicken; das dauert bis zu einer Minute.",
        "Zurück in LightOS: im Reiter „uDMX (USB)“ auf „Adapter suchen“ und "
        "dann auf „Verbinden“ klicken.",
    ]


def windows_treiber_achtung() -> str:
    """Die eine Warnung, die zu den Schritten gehoert."""
    return ("Achtung: in Zadig genau den Adapter wählen. Zadig ersetzt den "
            "Treiber des gewählten Geräts — eine Maus, eine Tastatur oder ein "
            "anderes Gerät funktioniert danach nicht mehr, bis man es im "
            "Geräte-Manager von Windows deinstalliert (mit „Treiber löschen“) "
            "und neu einsteckt.")


def ist_installationspaket() -> bool:
    """Laeuft LightOS aus dem Windows-Setup (gepackt), nicht aus dem Quelltext?
    Dann laesst sich nichts mit ``pip`` nachinstallieren."""
    return bool(getattr(sys, "frozen", False))


def rechte_hinweis() -> str:
    """Was auf DIESEM Betriebssystem einmalig einzurichten ist."""
    if sys.platform.startswith("win"):
        return ("Windows hat für uDMX-Adapter keinen eigenen Treiber, und "
                "LightOS liefert und installiert keine Treiber. Dem Gerät muss "
                "einmalig von Hand der WinUSB-Treiber zugewiesen werden "
                f"(z. B. mit dem Programm Zadig, {LINK_ZADIG}, Adminrechte "
                "nötig). Schritt für Schritt: Reiter „uDMX (USB)“ → „Adapter "
                "suchen“ oder INSTALL.md, Abschnitt „uDMX-Adapter“.")
    if sys.platform == "darwin":
        return "Unter macOS ist kein Treiber nötig; libusb muss installiert sein."
    return (f"Unter Linux darf ein normales Benutzerkonto USB-Geräte erst nach "
            f"einer udev-Regel ansprechen. Einmalig die Datei "
            f"packaging/linux/{UDEV_REGEL} nach /etc/udev/rules.d/ kopieren, "
            f"das Konto in die Gruppe plugdev aufnehmen und den Adapter neu "
            f"einstecken — siehe INSTALL.md, Abschnitt „uDMX-Adapter“.")


def grund_text(code: int, schluessel: str = "") -> str:
    """Ein Satz + naechster Schritt je Grund (fuer Dialog, Banner, Diagnose)."""
    was = f" ({schluessel})" if schluessel else ""
    if code == G_OK:
        return "uDMX-Adapter sendet"
    if code == G_PYUSB_FEHLT:
        if ist_installationspaket():
            # OUT-76: im gepackten LightOS gibt es kein pip — der Rat, etwas
            # nachzuinstallieren, liefe ins Leere. Seit OUT-76 gehoert pyusb
            # zum Windows-Setup (x64); aeltere Setups hatten es nicht.
            return ("Diesem LightOS aus dem Installationspaket fehlt der "
                    "Programmteil für uDMX-Adapter (pyusb); nachinstallieren "
                    "lässt er sich dort nicht. Neuere Installationspakete für "
                    "Windows (x64) bringen ihn mit — bitte LightOS "
                    "aktualisieren. Bis dahin: einen ENTTEC DMX USB Pro oder "
                    "einen Art-Net-/sACN-Node verwenden.")
        return ("Für uDMX-Adapter fehlt das Python-Paket pyusb. Nachinstallieren "
                "mit: pip install pyusb (siehe INSTALL.md, „uDMX-Adapter“).")
    if code == G_LIBUSB_FEHLT:
        return ("pyusb ist da, aber die Bibliothek libusb-1.0 wurde nicht "
                "gefunden. Linux: Paket libusb-1.0-0 installieren. Windows: "
                "pip install libusb-package.")
    if code == G_NICHT_DA:
        return f"uDMX-Adapter{was} nicht gefunden — eingesteckt?"
    if code == G_KEINE_BERECHTIGUNG:
        return f"Kein Zugriffsrecht auf den uDMX-Adapter{was}. " + rechte_hinweis()
    if code == G_TREIBER_FEHLT:
        return (f"Der uDMX-Adapter{was} ist da, lässt sich aber nicht öffnen. "
                + rechte_hinweis())
    if code == G_BELEGT:
        return (f"Der uDMX-Adapter{was} wird von einem anderen Programm "
                f"gehalten (z. B. QLC+ oder eine zweite LightOS-Instanz).")
    if code == G_ANTWORTET_NICHT:
        return (f"Der uDMX-Adapter{was} ist da, nimmt aber keine Daten an "
                f"(Zeitlimit/Übertragungsfehler) — Kabel und Adapter prüfen.")
    if code == G_MEHRDEUTIG:
        return ("Mehrere uDMX-Adapter gefunden — bitte in den "
                "Ausgabe-Einstellungen einen bestimmten auswählen.")
    if code == G_NAME_UNKLAR:
        return ("Ein Gerät mit der geteilten Kennung 16c0:05dc ist da, sein "
                "Name lässt sich aber nicht lesen — ohne ihn ist unklar, ob es "
                "ein uDMX ist. " + rechte_hinweis())
    return f"uDMX: unbekannter Zustand ({code})"


_KURZ = {
    G_PYUSB_FEHLT: "pyusb fehlt (pip install pyusb)",
    G_LIBUSB_FEHLT: "libusb-1.0 fehlt",
    G_NICHT_DA: "Adapter nicht gefunden — eingesteckt?",
    G_KEINE_BERECHTIGUNG: "kein Zugriffsrecht (Linux: udev-Regel, s. INSTALL.md)",
    G_TREIBER_FEHLT: ("Adapter lässt sich nicht öffnen (Windows: WinUSB-Treiber "
                      "fehlt — LightOS liefert keinen, s. Reiter „uDMX (USB)“)"),
    G_BELEGT: "Adapter von anderem Programm belegt",
    G_ANTWORTET_NICHT: "Adapter nimmt keine Daten an",
    G_MEHRDEUTIG: "mehrere Adapter — bitte einen auswählen",
    G_NAME_UNKLAR: "Gerätename nicht lesbar (Zugriffsrecht fehlt?)",
}


def grund_kurz(code: int) -> str:
    """Halber Satz fuer Banner/Statusleiste; leer bei ``G_OK``."""
    return _KURZ.get(int(code), "")


# ── Bibliothek (traege) ──────────────────────────────────────────────────────

def _usb_laden():
    """Liefert ``(usb.core, usb.util, backend)`` oder wirft :class:`UdmxFehler`.

    ``backend`` ist ``None`` (pyusb sucht libusb selbst) oder das von
    ``libusb-package`` mitgebrachte — damit genuegt unter Windows
    ``pip install pyusb libusb-package``, ohne eine DLL von Hand abzulegen.

    ``LIGHTOS_KEIN_USB=1`` schaltet rohes USB ganz ab (Testlaeufe, Fehlersuche):
    dann wird nichts geladen und kein Geraet aufgezaehlt.
    """
    import os
    if os.environ.get("LIGHTOS_KEIN_USB"):
        raise UdmxFehler(G_PYUSB_FEHLT, "Rohes USB ist per LIGHTOS_KEIN_USB "
                                        "abgeschaltet — uDMX-Adapter ruhen.")
    try:
        import usb.core
        import usb.util
    except Exception as e:                               # noqa: BLE001
        raise UdmxFehler(G_PYUSB_FEHLT) from e
    backend = None
    try:
        import libusb_package
        backend = libusb_package.get_libusb1_backend()
    except Exception:                                    # noqa: BLE001
        backend = None
    if backend is None:
        backend = _backend_aus_bundle()
    return usb.core, usb.util, backend


def bundle_dll_pfad(basis: str | None = None) -> str:
    """OUT-76: Pfad der mit dem Installationspaket gelieferten
    ``libusb-1.0.dll`` — leer, wenn LightOS nicht gepackt laeuft oder die
    Datei fehlt. Gesucht wird im Ordner des Pakets (dorthin legt sie
    ``LightOS.spec``) und im Programmordner (dorthin legt sie der Haken, den
    libusb-package selbst mitbringt)."""
    import os
    basis = getattr(sys, "_MEIPASS", "") if basis is None else basis
    if not basis:
        return ""
    for ordner in (os.path.join(basis, "libusb_package"), basis):
        pfad = os.path.join(ordner, "libusb-1.0.dll")
        if os.path.isfile(pfad):
            return pfad
    return ""


def _backend_aus_bundle():
    """Das pyusb-Backend mit GENAU der mitgelieferten DLL — oder ``None``.
    Rueckfall, falls ``libusb_package`` sie im gepackten LightOS nicht selbst
    findet; dann soll es nicht an der Suchreihenfolge von Windows haengen."""
    pfad = bundle_dll_pfad()
    if not pfad:
        return None
    try:
        import usb.backend.libusb1
        return usb.backend.libusb1.get_backend(find_library=lambda _name: pfad)
    except Exception:                                    # noqa: BLE001
        return None


def bibliothek_status() -> dict:
    """Ist pyusb/libusb vorhanden? — OHNE ein Geraet anzufassen.

    Fuer Selbsttest und Diagnosepaket. ``{"pyusb": bool, "pyusb_version": str,
    "libusb": bool, "libusb_quelle": str, "text": str}``.
    """
    import importlib.util
    info = {"pyusb": False, "pyusb_version": "", "libusb": False,
            "libusb_quelle": "", "text": ""}
    try:
        info["pyusb"] = importlib.util.find_spec("usb") is not None
    except (ImportError, ValueError):
        info["pyusb"] = "usb" in sys.modules
    if info["pyusb"]:
        try:
            from importlib.metadata import version
            info["pyusb_version"] = version("pyusb")
        except Exception:                                # noqa: BLE001
            pass
    try:
        if importlib.util.find_spec("libusb_package") is not None:
            info["libusb"], info["libusb_quelle"] = True, "libusb-package"
    except (ImportError, ValueError):
        pass
    if not info["libusb"]:
        try:
            from ctypes.util import find_library
            for kandidat in ("usb-1.0", "libusb-1.0", "usb"):
                pfad = find_library(kandidat)
                if pfad:
                    info["libusb"], info["libusb_quelle"] = True, str(pfad)
                    break
        except Exception:                                # noqa: BLE001
            pass
    if not info["pyusb"]:
        info["text"] = "pyusb fehlt — uDMX-Adapter nicht nutzbar (optional)"
    elif not info["libusb"]:
        info["text"] = (f"pyusb {info['pyusb_version'] or '?'} vorhanden, "
                        f"libusb-1.0 NICHT gefunden — uDMX-Adapter nicht nutzbar")
    else:
        info["text"] = (f"pyusb {info['pyusb_version'] or '?'}, libusb "
                        f"({info['libusb_quelle']}) — uDMX-Adapter nutzbar")
    return info


# ── Fehler einordnen ─────────────────────────────────────────────────────────

# libusb-Fehlercodes (``USBError.backend_error_code``)
_LIBUSB_ACCESS, _LIBUSB_NO_DEVICE, _LIBUSB_NOT_FOUND = -3, -4, -5
_LIBUSB_BUSY, _LIBUSB_TIMEOUT, _LIBUSB_PIPE, _LIBUSB_NOT_SUPPORTED = -6, -7, -9, -12


def _fehler_code(exc: BaseException) -> int:
    """USB-Fehler -> ``G_*``. Kennt errno UND den libusb-Code, weil je nach
    Plattform nur eines von beiden verlaesslich gesetzt ist."""
    if isinstance(exc, UdmxFehler):
        return exc.code
    if type(exc).__name__ == "NoBackendError":
        return G_LIBUSB_FEHLT
    if isinstance(exc, NotImplementedError):
        # OUT-76: pyusb wirft fuer LIBUSB_ERROR_NOT_SUPPORTED kein USBError,
        # sondern NotImplementedError — ohne errno und ohne libusb-Code. Genau
        # so scheitert unter Windows ein Adapter ohne WinUSB-Treiber; bisher
        # hiess das „nimmt keine Daten an — Kabel und Adapter prüfen“.
        return G_TREIBER_FEHLT
    nr = getattr(exc, "errno", None)
    roh = getattr(exc, "backend_error_code", None)
    if nr == errno.EACCES or roh == _LIBUSB_ACCESS:
        return G_KEINE_BERECHTIGUNG
    if nr == errno.ENODEV or roh in (_LIBUSB_NO_DEVICE,):
        return G_NICHT_DA
    if nr == errno.EBUSY or roh == _LIBUSB_BUSY:
        return G_BELEGT
    if roh in (_LIBUSB_NOT_SUPPORTED, _LIBUSB_NOT_FOUND) or nr in (
            errno.ENOENT, getattr(errno, "ENOTSUP", -1), errno.ENOSYS):
        return G_TREIBER_FEHLT
    return G_ANTWORTET_NICHT


def _ist_stall(exc: BaseException) -> bool:
    return (getattr(exc, "errno", None) == errno.EPIPE
            or getattr(exc, "backend_error_code", None) == _LIBUSB_PIPE)


# ── Erkennung (passiv: nur Beschreibungen, nichts wird beansprucht) ──────────

def _tabellen_zeile(vid, pid) -> Kennung | None:
    for k in BEKANNTE_GERAETE:
        if k.vid == vid and k.pid == pid:
            return k
    return None


def _text(dev, feld: str, index_feld: str) -> tuple[str, bool]:
    """Einen Beschreibungstext lesen. ``(text, lesbar)`` — ein Geraet ohne
    diesen Text (Index 0) gilt als lesbar und leer."""
    if not getattr(dev, index_feld, 0):
        return "", True
    try:
        wert = getattr(dev, feld)
    except Exception:                                    # noqa: BLE001
        return "", False
    return (str(wert).strip() if wert else ""), True


def _beschreibe(dev, zeile: Kennung) -> UdmxGeraet | None:
    hersteller, h_ok = _text(dev, "manufacturer", "iManufacturer")
    produkt, p_ok = _text(dev, "product", "iProduct")
    serie, _ = _text(dev, "serial_number", "iSerialNumber")
    bestaetigt, hinweis = True, ""
    if zeile.hersteller is not None or zeile.produkt is not None:
        if not (h_ok and p_ok):
            bestaetigt = False
            hinweis = "Name nicht lesbar (Berechtigung fehlt?)"
        elif ((zeile.hersteller is not None and hersteller.lower() != zeile.hersteller)
              or (zeile.produkt is not None and produkt.lower() != zeile.produkt)):
            return None          # geteilte Kennung, aber ein ANDERES Geraet
    bus = getattr(dev, "bus", None)
    ports = getattr(dev, "port_numbers", None)
    if bus is not None and ports:
        ort = f"{bus}-" + ".".join(str(p) for p in ports)
    elif bus is not None and getattr(dev, "address", None) is not None:
        ort = f"bus{bus}/adr{dev.address}"
    else:
        ort = ""
    return UdmxGeraet(
        vid=zeile.vid, pid=zeile.pid, name=zeile.name, hersteller=hersteller,
        produkt=produkt, seriennummer=serie, bus=bus,
        adresse=getattr(dev, "address", None), ort=ort, bestaetigt=bestaetigt,
        hinweis=hinweis, stall_ist_erfolg=zeile.stall_ist_erfolg, _dev=dev)


def windows_treiber(_zeilen=None):
    """OUT-76: Treiber-Lage der ANGESTECKTEN bekannten Adapter, wie Windows sie
    fuehrt — ``[usb_treiber_windows.UsbTreiber]``, oder ``None`` wenn nicht
    feststellbar (kein Windows, Abfrage gescheitert).

    Nur lesen, kein Geraet wird geoeffnet; braucht kein pyusb. Den Namen aus
    :data:`BEKANNTE_GERAETE` zu einem Befund liefert :func:`geraete_name`.
    """
    import os
    from src.core.dmx import usb_treiber_windows
    if _zeilen is None and os.environ.get("LIGHTOS_KEIN_USB"):
        return None          # rohes USB ist abgeschaltet (Testlaeufe, Fehlersuche)
    befunde = usb_treiber_windows.angesteckt(
        [(k.vid, k.pid) for k in BEKANNTE_GERAETE], _zeilen=_zeilen)
    if befunde is None:
        return None
    # ★ Geteilte Kennung (16c0:05dc): nennt sich das Geraet anders als ein
    # uDMX, ist es keiner — es faellt heraus, damit nie jemand den Rat bekommt,
    # einem FREMDEN Geraet den Treiber zu ersetzen.
    return [b for b in befunde if _treiber_befund_passt(b)]


def _treiber_befund_passt(befund) -> bool:
    zeile = _tabellen_zeile(befund.vid, befund.pid)
    if zeile is None:
        return False
    if zeile.produkt is None or not befund.name:
        return True
    return befund.name.strip().lower() == zeile.produkt


def treiber_befund_sicher(befund) -> bool:
    """Steht fest, dass der Befund einen uDMX-Adapter meint? Bei der geteilten
    Kennung nur, wenn Windows den Produktnamen des Geraets kennt und er passt."""
    zeile = _tabellen_zeile(befund.vid, befund.pid)
    if zeile is None:
        return False
    if zeile.produkt is None:
        return True
    return bool(befund.name) and befund.name.strip().lower() == zeile.produkt


def geraete_name(vid: int, pid: int) -> str:
    zeile = _tabellen_zeile(vid, pid)
    return zeile.name if zeile is not None else f"{vid:04x}:{pid:04x}"


def mit_treiber(geraete, befunde) -> list[UdmxGeraet]:
    """OUT-76: die Treiber-Lage in die Adapter-Liste eintragen.

    Zugeordnet wird ueber die Kennung — und nur, wenn alle angesteckten Adapter
    dieser Kennung dieselbe Lage haben (sonst bleibt sie leer: nie raten).
    """
    from dataclasses import replace
    from src.core.dmx import usb_treiber_windows
    if not befunde:
        return list(geraete)
    lage = usb_treiber_windows.lage_je_kennung(befunde)
    dienste = {(b.vid, b.pid): b.dienst for b in befunde}
    raus = []
    for g in geraete:
        l = lage.get((g.vid, g.pid), "")
        if l and not g.bestaetigt and l != T_PASST:
            # Der Name liess sich nicht lesen — unter Windows ist der fehlende
            # Treiber der Grund, nicht eine Berechtigung.
            g = replace(g, hinweis="Name nicht lesbar — " + treiber_kurz(
                l, dienste.get((g.vid, g.pid), "")))
        raus.append(replace(g, treiber=l,
                            treiber_dienst=dienste.get((g.vid, g.pid), "") if l else ""))
    return raus


def liste_geraete(usb=None, treiber=None) -> list[UdmxGeraet]:
    """Alle uDMX-Adapter am Rechner. Wirft :class:`UdmxFehler`, wenn pyusb
    oder libusb fehlt.

    Texte werden NUR von Geraeten gelesen, deren Kennung in der Tabelle steht —
    fremde USB-Geraete bleiben voellig unberuehrt. Gesendet wird hier nichts
    ausser den Standard-Abfragen, mit denen pyusb die Beschreibung holt.

    ``usb`` = ``(core, util, backend)`` fuer Tests. ``treiber`` (OUT-76) =
    Befunde aus :func:`windows_treiber`; damit traegt jeder Adapter seine
    Treiber-Lage. Ohne sie (Sender, der nur seinen Adapter sucht) wird Windows
    nicht gefragt.
    """
    core, _util, backend = usb or _usb_laden()
    try:
        kw = {"find_all": True}
        if backend is not None:
            kw["backend"] = backend
        gefunden = list(core.find(**kw) or [])
    except Exception as e:                               # noqa: BLE001
        # „kein Backend" = libusb fehlt; alles andere nach seinem Fehlercode.
        raise UdmxFehler(_fehler_code(e)) from e
    raus = []
    for dev in gefunden:
        zeile = _tabellen_zeile(getattr(dev, "idVendor", None),
                                getattr(dev, "idProduct", None))
        if zeile is None:
            continue
        g = _beschreibe(dev, zeile)
        if g is not None:
            raus.append(g)
    raus.sort(key=lambda g: (g.kennung, g.seriennummer, g.ort))
    return mit_treiber(raus, treiber) if treiber else raus


def schluessel_lesen(text) -> tuple[int | None, int | None, str, str]:
    """``"2008:1066#SN"`` / ``"2008:1066@1-2.3"`` / ``"2008:1066"`` / ``""``
    -> ``(vid, pid, seriennummer, ort)``. Unlesbares zaehlt als „beliebig"."""
    t = str(text or "").strip()
    serie = ort = ""
    if "#" in t:
        t, serie = t.split("#", 1)
    elif "@" in t:
        t, ort = t.split("@", 1)
    vid = pid = None
    if ":" in t:
        a, b = t.split(":", 1)
        try:
            vid, pid = int(a.strip(), 16), int(b.strip(), 16)
        except ValueError:
            vid = pid = None
    return vid, pid, serie.strip(), ort.strip()


def waehle(geraete, schluessel, streng: bool = False) -> UdmxGeraet:
    """Den zum Schluessel passenden Adapter — oder :class:`UdmxFehler`.

    ★ Nie raten (Lehre aus OUT-66, wo ein Wiederverbinden per Kennung den
    Adapter eines ANDEREN Universums nahm):

    * Seriennummer angegeben -> nur genau dieser Adapter.
    * Anschluss angegeben -> dieser Anschluss; steckt dort nichts mehr und
      gibt es GENAU EINEN Adapter dieser Kennung, ist es derselbe an anderer
      Buchse. Bei mehreren: keiner.
    * Nur Kennung / gar nichts -> genau einer, sonst „mehrdeutig".

    ``streng`` (mehr als EIN uDMX-Ausgang eingerichtet): nur noch der exakte
    Treffer zaehlt — Seriennummer oder genau dieser Anschluss. Der Ersatz „der
    einzige vorhandene" faellt weg, denn der einzige vorhandene Adapter kann
    der eines ANDEREN Universums sein (dessen eigener ist nur gerade abgezogen):
    zwei Universen sendeten dann abwechselnd auf denselben Ausgang.
    """
    vid, pid, serie, ort = schluessel_lesen(schluessel)
    passend = [g for g in geraete
               if (vid is None or (g.vid, g.pid) == (vid, pid))]
    nutzbar = [g for g in passend if g.bestaetigt]
    if not nutzbar:
        if passend:
            raise UdmxFehler(G_NAME_UNKLAR)
        raise UdmxFehler(G_NICHT_DA, grund_text(G_NICHT_DA, str(schluessel or "")))
    if serie:
        for g in nutzbar:
            if g.seriennummer == serie:
                return g
        raise UdmxFehler(G_NICHT_DA, grund_text(G_NICHT_DA, str(schluessel)))
    if ort:
        for g in nutzbar:
            if g.ort == ort:
                return g
    if streng:
        if ort:
            raise UdmxFehler(
                G_NICHT_DA,
                f"uDMX-Adapter ({schluessel}) steckt nicht an seinem Anschluss. "
                f"Bei mehreren uDMX-Ausgängen zählt nur der gewählte Anschluss "
                f"— zurückstecken oder in den Ausgabe-Einstellungen neu auswählen.")
        raise UdmxFehler(
            G_MEHRDEUTIG,
            "Mehrere uDMX-Ausgänge eingerichtet, aber für diesen ist kein "
            "bestimmter Adapter gewählt — bitte in den Ausgabe-Einstellungen "
            "einen auswählen.")
    if len(nutzbar) == 1:
        return nutzbar[0]
    if ort:
        raise UdmxFehler(
            G_NICHT_DA,
            f"uDMX-Adapter ({schluessel}) steckt nicht mehr an seinem Anschluss, "
            f"und es gibt mehrere gleiche — bitte in den Ausgabe-Einstellungen "
            f"neu auswählen.")
    raise UdmxFehler(G_MEHRDEUTIG)


# ── Senden ───────────────────────────────────────────────────────────────────

class Udmx:
    """Ein geoeffneter uDMX-Adapter. Schnittstelle wie ``EnttecPro``
    (``send_dmx`` / ``is_disabled`` / ``is_open`` / ``close`` / ``port``).

    ``send_dmx`` blockiert hoechstens ``TIMEOUT_MS`` und wirft nie; es gehoert
    trotzdem NICHT in den 44-Hz-Ausgabe-Thread, sondern hinter
    ``udmx_process.UdmxProcessProxy`` (eigener Prozess, „das neueste Bild
    gewinnt").
    """
    #: So viele Fehlversuche in Folge gelten als Ausfall. Klein, weil jeder
    #: Zeitlimit-Fehler schon 250 ms dauert (5 x 250 ms = gut eine Sekunde).
    FAIL_LIMIT = 5
    RECONNECT_EVERY_S = 2.0

    def __init__(self, schluessel: str = "", usb=None, melde_grund=None,
                 clock=time.monotonic, streng=None):
        self.port = str(schluessel or "").strip()
        self._usb = usb
        self._melde_grund = melde_grund
        #: Aufrufbar -> ``True``, solange mehr als ein uDMX-Ausgang
        #: eingerichtet ist (s. :func:`waehle`). ``None`` = nie.
        self._streng = streng
        #: Der gehaltene Adapter wurde unter ``streng`` gewaehlt bzw. bestaetigt.
        self._exakt = False
        self._clock = clock
        self._fail_count = 0
        self._disabled = False
        self._last_reconnect = 0.0
        self._closed = False
        self._wieder_da = False
        self._gemeldet = None      # zuletzt auf stderr gemeldeter Ausfallgrund
        self.grund = G_OK
        self.stalls = 0
        self.geraet: UdmxGeraet | None = None
        self._dev = None
        try:
            self._suchen()
        except Exception as e:                           # noqa: BLE001
            self._setze_grund(_fehler_code(e))
            if isinstance(e, UdmxFehler):
                raise
            raise UdmxFehler(self.grund) from e
        self._setze_grund(G_OK)

    # -- intern -------------------------------------------------------------

    def _bibliothek(self):
        if self._usb is None:
            self._usb = _usb_laden()
        return self._usb

    def _ist_streng(self) -> bool:
        if self._streng is None:
            return False
        try:
            return bool(self._streng())
        except Exception:                                # noqa: BLE001
            return True          # im Zweifel die sichere Seite: nicht raten

    def _suchen(self):
        streng = self._ist_streng()
        g = waehle(liste_geraete(self._bibliothek()), self.port, streng=streng)
        self.geraet, self._dev, self._exakt = g, g._dev, streng

    def _noch_der_richtige(self) -> bool:
        """Ist inzwischen ein weiterer uDMX-Ausgang dazugekommen, darf ein
        ersatzweise gewaehlter Adapter („der einzige vorhandene") nicht
        gehalten werden — er kann jetzt dem anderen Ausgang gehoeren."""
        if self._exakt or not self._ist_streng():
            return True
        try:
            waehle([self.geraet] if self.geraet is not None else [],
                   self.port, streng=True)
        except UdmxFehler as e:
            self._disable(e.code)
            return False
        self._exakt = True
        return True

    def _setze_grund(self, code: int):
        if code == self.grund:
            return
        self.grund = code
        if self._melde_grund is not None:
            try:
                self._melde_grund(code)
            except Exception:                            # noqa: BLE001
                pass

    def _freigeben(self):
        dev, self._dev = self._dev, None
        if dev is None:
            return
        try:
            self._bibliothek()[1].dispose_resources(dev)
        except Exception:                                # noqa: BLE001
            pass

    def _disable(self, code: int):
        """Adapter als ausgefallen werten: nicht weiter senden, gedrosselt neu
        suchen. Gemeldet wird EINMAL je Ausfallgrund — nicht je Bild und
        nicht bei jedem gescheiterten Wiederverbinden."""
        if code != self._gemeldet:
            self._gemeldet = code
            print(f"[Udmx] {self.port or 'Adapter'}: Ausgabe gestoppt — "
                  f"{grund_text(code, self.port)} Neuer Versuch alle "
                  f"{self.RECONNECT_EVERY_S:g}s.", file=sys.stderr)
        self._disabled = True
        self._last_reconnect = self._clock()
        self._setze_grund(code)
        self._freigeben()

    def _try_reconnect(self):
        jetzt = self._clock()
        if (jetzt - self._last_reconnect) < self.RECONNECT_EVERY_S:
            return
        self._last_reconnect = jetzt
        try:
            self._suchen()
        except Exception as e:                           # noqa: BLE001
            self._setze_grund(_fehler_code(e))
            return
        # Gefunden heisst noch nicht „sendet": der naechste Transfer zeigt es
        # (fehlende Rechte fallen erst beim Oeffnen auf). Der Grund bleibt
        # deshalb stehen, bis ein Bild wirklich angenommen wurde.
        self._disabled = False
        self._fail_count = 0
        self._wieder_da = True

    # -- oeffentlich --------------------------------------------------------

    def send_dmx(self, dmx_data: bytes):
        """512 Byte als EIN Control-Transfer (``bRequest`` 2, ab Kanal 0)."""
        assert len(dmx_data) == DMX_BYTES
        if self._closed:
            return
        if self._disabled:
            self._try_reconnect()
            if self._disabled:
                return
        dev = self._dev
        if dev is None:
            return
        if not self._noch_der_richtige():
            return
        try:
            n = dev.ctrl_transfer(REQUEST_TYPE_OUT, REQUEST_KANALBEREICH,
                                  DMX_BYTES, 0, bytes(dmx_data), TIMEOUT_MS)
        except Exception as e:                           # noqa: BLE001
            if (_ist_stall(e) and self.geraet is not None
                    and self.geraet.stall_ist_erfolg):
                self.stalls += 1
                n = DMX_BYTES
            else:
                code = _fehler_code(e)
                self._fail_count += 1
                # Abgezogen, keine Rechte, kein Treiber: das wird durch
                # Wiederholen nicht besser -> sofort als Ausfall werten.
                if (code != G_ANTWORTET_NICHT
                        or self._fail_count >= self.FAIL_LIMIT):
                    self._disable(code)
                return
        if n is not None and n != DMX_BYTES:
            self._fail_count += 1
            if self._fail_count >= self.FAIL_LIMIT:
                self._disable(G_ANTWORTET_NICHT)
            return
        self._fail_count = 0
        if self._gemeldet is not None or self._wieder_da:
            self._wieder_da = False
            self._gemeldet = None
            print(f"[Udmx] {self.port or 'Adapter'}: sendet wieder.",
                  file=sys.stderr)
        self._setze_grund(G_OK)

    def is_disabled(self) -> bool:
        return self._disabled

    def is_open(self) -> bool:
        return self._dev is not None and not self._closed

    def close(self):
        """Adapter freigeben. Idempotent, wirft nie.

        ★ Bewusst OHNE ein letztes „alles auf 0": was beim Abschalten gesendet
        wird, entscheidet der OutputManager (Laser-Aus-Werte sind nicht immer
        0). Der Adapter selbst haelt sein letztes Bild — s. Anleitung."""
        self._closed = True
        self._freigeben()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
