"""WEB-11: Wohin zeigt der QR-Code der Handy-Konsole — und wann gibt es keinen?

Der Link lautet ``http://<IP>:<Port>/konsole?k=<Schluessel>``. Heikel ist die
IP: ein Rechner hat oft mehrere Netzwerkkarten (WLAN, Kabel, VPN, virtuelle
Karten), und nur eine davon haengt im selben Netz wie das Handy. Deshalb:

  * Es werden ALLE IPv4-Adressen der aktiven Karten gelesen (nur gelesen),
    ``127.x`` und Link-Local (``169.254.x``) fallen heraus.
  * Gibt es mehrere, bietet die Oberflaeche eine Auswahl an (Name der Karte +
    Adresse) und merkt sich die zuletzt gewaehlte.
  * Es wird nie eine Adresse angezeigt, die es auf diesem Rechner nicht gibt.
    Ist die gemerkte Adresse verschwunden (anderes WLAN), gilt sie nicht mehr.
  * Laeuft der Server nicht, ist er nur an ``127.0.0.1`` gebunden oder ist die
    Handy-Konsole aus, gibt es KEINEN Link — sondern den noetigen Schritt.

Der Kern (``brauchbare_adressen``, ``waehle``, ``lage``) ist reines Python und
bekommt alles hereingereicht; nur ``lese_schnittstellen`` und ``lage_jetzt``
fragen den Rechner. Nichts hier schreibt den Link oder den Schluessel in ein
Protokoll.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote

SERVER_AUS = "server_aus"
NUR_LOKAL = "nur_lokal"
KONSOLE_AUS = "konsole_aus"
KEIN_NETZ = "kein_netz"
NETZ_NEU = "netz_neu"
BEREIT = "bereit"

WARNUNG = ("Nur im eigenen WLAN zeigen — wer den Code scannt, "
           "kann die Handy-Konsole bedienen.")

SCHRITTE = {
    SERVER_AUS: "Das Web-Interface läuft nicht. Einschalten: "
                "Ausgabe → Web-Interface.",
    NUR_LOKAL: "Das Web-Interface ist nur auf diesem PC erreichbar. "
               "Für das Handy „LAN-/Handy-Remote“ einschalten "
               "(Ausgabe → Web-Remote: Verbindung & Token).",
    KONSOLE_AUS: "Die Handy-Konsole ist ausgeschaltet. Den Schalter "
                 "„Handy-Konsole“ einschalten.",
    KEIN_NETZ: "Keine Netzwerkverbindung gefunden. Den PC mit dem WLAN "
               "(oder per Kabel mit dem Router) verbinden, in dem auch das "
               "Handy ist.",
    NETZ_NEU: "Das Netzwerk hat sich geändert, seit das Web-Interface läuft. "
              "Web-Interface einmal aus- und wieder einschalten "
              "(Ausgabe → Web-Interface).",
    BEREIT: "",
}

# Karten, die fast nie das Netz des Handys sind — sie bleiben waehlbar, stehen
# aber hinten und werden nie von allein vorgeschlagen, solange es andere gibt.
_VIRTUELL = ("docker", "veth", "virbr", "vbox", "virtualbox", "vmnet", "vmware",
             "br-", "tailscale", "wsl", "vethernet", "hyper-v", "zerotier",
             "tun", "tap", "wg", "utun", "loopback")


@dataclass(frozen=True)
class Schnittstelle:
    """Eine Netzwerkkarte, wie das System sie meldet."""
    name: str
    adressen: tuple = ()
    aktiv: bool = True
    loopback: bool = False


@dataclass(frozen=True)
class Adresse:
    karte: str
    ip: str

    @property
    def beschriftung(self) -> str:
        return f"{self.karte} — {self.ip}" if self.karte else self.ip


@dataclass(frozen=True)
class Lage:
    """Was die Oberflaeche zeigen soll. ``url`` ist nur bei ``BEREIT`` gesetzt."""
    zustand: str
    adressen: tuple = ()
    gewaehlt: Adresse | None = None
    url: str = ""

    @property
    def bereit(self) -> bool:
        return self.zustand == BEREIT and bool(self.url)

    @property
    def schritt(self) -> str:
        return SCHRITTE.get(self.zustand, "")

    def __repr__(self) -> str:      # der Link traegt den Schluessel — nie zeigen
        return f"<Lage {self.zustand}, {len(self.adressen)} Adresse(n)>"


def _ipv4(text) -> tuple | None:
    teile = str(text).strip().split(".")
    if len(teile) != 4:
        return None
    try:
        zahlen = tuple(int(t) for t in teile)
    except ValueError:
        return None
    if any(z < 0 or z > 255 for z in zahlen):
        return None
    return zahlen


def ist_brauchbar(ip) -> bool:
    """Eine IPv4-Adresse, unter der ein Handy im selben Netz den PC erreicht:
    nicht Loopback (127/8), nicht Link-Local (169.254/16), nicht 0/8, keine
    Multicast-/Rundruf-Adresse."""
    z = _ipv4(ip)
    if z is None:
        return False
    if z[0] in (0, 127) or z[0] >= 224:
        return False
    if z[0] == 169 and z[1] == 254:
        return False
    return True


def _privat(ip: str) -> bool:
    z = _ipv4(ip)
    if z is None:
        return False
    return (z[0] == 10 or (z[0] == 192 and z[1] == 168)
            or (z[0] == 172 and 16 <= z[1] <= 31))


def _virtuell(name: str) -> bool:
    n = (name or "").lower()
    return any(n.startswith(v) or f" {v}" in n or f"({v}" in n for v in _VIRTUELL)


def brauchbare_adressen(schnittstellen) -> list:
    """Alle Adressen, die fuer den Link in Frage kommen — die wahrscheinlichen
    zuerst (private Adressen echter Karten), ohne Doppelte."""
    gefunden, gesehen = [], set()
    for s in schnittstellen or ():
        if not s.aktiv or s.loopback:
            continue
        for ip in s.adressen or ():
            ip = str(ip).strip()
            if ist_brauchbar(ip) and ip not in gesehen:
                gesehen.add(ip)
                gefunden.append(Adresse(str(s.name or ""), ip))
    gefunden.sort(key=lambda a: (_virtuell(a.karte), not _privat(a.ip)))
    return gefunden


def waehle(adressen, gemerkt: str = "", bevorzugt: str = "") -> Adresse | None:
    """Die Adresse fuer den Link: die gemerkte, sonst die der Standard-Route
    (``bevorzugt``), sonst die erste der Liste. Nur was in ``adressen`` steht,
    kommt in Frage — eine gemerkte Adresse, die es nicht mehr gibt, verfaellt."""
    adressen = list(adressen or ())
    if not adressen:
        return None
    for wunsch in (gemerkt, bevorzugt):
        for a in adressen:
            if wunsch and a.ip == wunsch:
                return a
    return adressen[0]


def konsole_url(ip: str, port: int, schluessel: str) -> str:
    basis = f"http://{ip}:{int(port)}/konsole"
    return f"{basis}?k={quote(str(schluessel), safe='')}" if schluessel else basis


def lage(*, laeuft: bool, bind_host: str, konsole_an: bool, schnittstellen,
         schluessel: str, port: int = 5000, gemerkt: str = "",
         bevorzugt: str = "", erlaubt=None) -> Lage:
    """Der Zustand der Verbindung aus den hereingereichten Fakten.

    ``erlaubt``: die Adressen, von denen der laufende Server eine Seite samt
    Socket annimmt (seine Origin-Liste, beim Start festgelegt). Eine Adresse,
    die erst danach dazukam (WLAN spaeter verbunden), wuerde am Handy zwar die
    Seite laden, aber nie verbinden — sie wird deshalb nicht angeboten;
    bleibt dann keine uebrig, ist der Schritt „Web-Interface neu starten"."""
    if not laeuft:
        return Lage(SERVER_AUS)
    if str(bind_host or "").startswith("127.") or bind_host == "localhost":
        return Lage(NUR_LOKAL)
    if not konsole_an:
        return Lage(KONSOLE_AUS)
    adressen = brauchbare_adressen(schnittstellen)
    # An eine bestimmte Adresse gebunden: nur die ist erreichbar.
    if bind_host and bind_host not in ("0.0.0.0", "::"):
        adressen = [a for a in adressen if a.ip == bind_host]
    if erlaubt is not None and adressen:
        bekannt = [a for a in adressen if a.ip in erlaubt]
        if not bekannt:
            return Lage(NETZ_NEU)
        adressen = bekannt
    wahl = waehle(adressen, gemerkt, bevorzugt)
    if wahl is None or not schluessel:
        return Lage(KEIN_NETZ, tuple(adressen))
    return Lage(BEREIT, tuple(adressen), wahl, konsole_url(wahl.ip, port, schluessel))


# ── Den Rechner fragen ───────────────────────────────────────────────────────

def lese_schnittstellen() -> list:
    """Die Netzwerkkarten des Rechners, nur lesend, ohne Fremdbibliothek
    (``QNetworkInterface`` aus dem ohnehin vorhandenen Qt). Nie eine Ausnahme:
    im Zweifel eine leere Liste — dann zeigt der Dialog „kein Netz"."""
    try:
        from PySide6.QtNetwork import QAbstractSocket, QNetworkInterface
    except Exception:
        return []
    raus = []
    try:
        for karte in QNetworkInterface.allInterfaces():
            flags = karte.flags()
            aktiv = bool(flags & QNetworkInterface.InterfaceFlag.IsUp) and bool(
                flags & QNetworkInterface.InterfaceFlag.IsRunning)
            schleife = bool(flags & QNetworkInterface.InterfaceFlag.IsLoopBack)
            adressen = []
            for eintrag in karte.addressEntries():
                ip = eintrag.ip()
                if ip.protocol() == QAbstractSocket.NetworkLayerProtocol.IPv4Protocol:
                    adressen.append(ip.toString())
            name = karte.humanReadableName() or karte.name()
            raus.append(Schnittstelle(str(name), tuple(adressen), aktiv, schleife))
    except Exception as e:
        print(f"[handy_verbindung] ERROR: Netzwerkkarten nicht lesbar: "
              f"{type(e).__name__}")
        return []
    return raus


def lage_jetzt(schnittstellen=None, bevorzugt=None) -> Lage:
    """``lage`` mit den echten Werten des laufenden Programms. Die Liste der
    Karten und die Adresse der Standard-Route kann der Aufrufer hereinreichen
    (die Oberflaeche fragt sie nicht bei jedem Takt neu ab)."""
    from src.web import app as web_app
    from src.web import remote_settings
    laeuft = bool(web_app.is_running())
    if not laeuft:
        return Lage(SERVER_AUS)
    bind_host = web_app.bind_host()
    if bind_host.startswith("127."):
        return Lage(NUR_LOKAL)
    if not remote_settings.is_vc_remote_enabled():
        return Lage(KONSOLE_AUS)
    if schnittstellen is None:
        schnittstellen = lese_schnittstellen()
    if bevorzugt is None:
        bevorzugt = standard_adresse()
    return lage(laeuft=True, bind_host=bind_host, konsole_an=True,
                schnittstellen=schnittstellen,
                schluessel=remote_settings.get_token(),
                port=web_app.server_port(),
                gemerkt=remote_settings.get_handy_ip(), bevorzugt=bevorzugt,
                erlaubt=web_app.erlaubte_hosts())


def standard_adresse() -> str:
    """Die Adresse der Standard-Route — nur ein Vorschlag fuer die Vorauswahl,
    nie eine eigene Quelle: ``waehle`` nimmt sie nur, wenn sie in der Liste der
    wirklich vorhandenen Adressen steht."""
    try:
        from src.web import app as web_app
        return str(web_app.get_lan_ip() or "")
    except Exception:
        return ""
