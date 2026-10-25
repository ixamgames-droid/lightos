"""OSC-06: freie OSC-Adressen, OSC-Learn und Rueckmeldung.

Zu den festen ``/lightos/...``-Adressen des :class:`~src.core.osc.osc_server.OscServer`
kommt eine **Zuordnungstabelle**: beliebige eingehende Adressen (mit Mustern)
-> Ziel in LightOS. Die festen Adressen bleiben unveraendert gueltig; eine
Nachricht, die beide trifft, wirkt auf beiden Wegen.

Muster (Spalte „Adresse“):

* OSC-Platzhalter nach OSC 1.0: ``*`` (beliebig viele Zeichen ausser ``/``),
  ``?`` (ein Zeichen ausser ``/``), ``[abc]`` / ``[a-z]`` / ``[!abc]`` und
  ``{go,start}`` (Alternativen).
* Grenzen: hoechstens zwei ``*`` je Adressteil, ``{n}`` 1–6 Ziffern, Adressen
  ueber :data:`ADRESSE_MAX` Zeichen werden nicht verglichen (ReDoS-Schutz).
* ``{n}`` liefert die **Zielnummer** aus der Adresse (eine Ziffernfolge), z. B.
  ``/Page1/Fader{n}`` oder ``/exec/{n}/go``. Zielnummer = n + ``versatz``
  (grandMA3 ``/Page1/Fader201`` -> Executor 1 mit Versatz -200).
* Ohne ``{n}``: feste ``nummer`` — oder, mit ``nummer_aus_argument``, das ERSTE
  Argument ist die Zielnummer und das zweite der Wert (``/hog/playback/go/0 3``).

Argumente werden robust gelesen (:func:`wert_aus_argument`): int, float, bool,
Zahl-als-Text, ``on``/``off``. Der Bereich (``0-1``, ``0-100``, ``0-255``) legt
fest, was „voll“ ist. Fehlende oder kaputte Argumente aendern bei Fadern,
Grand Master und Blackout **nichts**. Tasten ohne Argument loesen aus (Bang,
wie bei den festen Adressen), Tasten mit Wert nur beim Druck (>= halbe Skala).

Threads: python-osc ruft :meth:`OscZuordnung.empfange` in seinen
Empfangs-Threads (``ThreadingOSCUDPServer`` = ein Thread je Paket). Dort wird
nur verglichen und eine :class:`Aktion` eingereiht. Angewandt wird in
:meth:`OscZuordnung.abarbeiten` im GUI-Thread, angestossen per
Queued-Signal (:func:`installiere_qt_bruecke`) — wie bei der
DMX-Fernsteuerung (``src/core/dmx/fernsteuerung.py``).

Rueckmeldung (:class:`OscRueckmeldung`): sendet Executor-Fader, Executor
aktiv, Cue-Nummer (GO-Index), Grand Master und Blackout an ein Ziel
(IP:Port) ueber den :class:`~src.core.osc.osc_server.OscSender` — nur bei
Aenderung, hoechstens ``rate_hz`` Durchgaenge je Sekunde, laeuft im GUI-Thread
(QTimer), liest dort den Zustand. Echo-Schutz: ein eingehender Wert, der einem
binnen :data:`ECHO_FENSTER` selbst gemeldeten Wert desselben Ziels entspricht,
wird verworfen (:meth:`OscRueckmeldung.ist_echo`); Werte, die selbst vom Pult
kamen, sind keine Echo-Kandidaten.

Speicherort: eigene Datei ``osc_zuordnungen.json`` im App-Datenordner
(:func:`src.core.paths.osc_zuordnungen_path`, Override
``LIGHTOS_OSC_ZUORDNUNGEN``). Fehlt sie oder ist sie kaputt: nichts zugeordnet,
Rueckmeldung aus.
"""
from __future__ import annotations

import ipaddress
import json
import math
import os
import queue
import re
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Callable

FORMAT_VERSION = 1
EXECUTOR_MAX = 20           # PlaybackEngine.MAX_EXECUTORS

# ── Ziele ─────────────────────────────────────────────────────────────────
ZIEL_FADER = "executor_fader"
ZIEL_GO = "executor_go"
ZIEL_BACK = "executor_back"
ZIEL_STOP = "executor_stop"
ZIEL_GM = "grand_master"
ZIEL_BLACKOUT = "blackout"
ZIEL_FKT_START = "funktion_start"
ZIEL_FKT_STOP = "funktion_stop"
ZIEL_FKT_UMSCHALTEN = "funktion_umschalten"
ZIEL_TAP = "tap_tempo"
ZIELE = (ZIEL_FADER, ZIEL_GO, ZIEL_BACK, ZIEL_STOP, ZIEL_GM, ZIEL_BLACKOUT,
         ZIEL_FKT_START, ZIEL_FKT_STOP, ZIEL_FKT_UMSCHALTEN, ZIEL_TAP)
#: Ziele, die einen Wert brauchen (ohne gueltigen Wert: nichts tun)
WERT_ZIELE = (ZIEL_FADER, ZIEL_GM, ZIEL_BLACKOUT)
#: Ziele mit Executor-Nummer
EXECUTOR_ZIELE = (ZIEL_FADER, ZIEL_GO, ZIEL_BACK, ZIEL_STOP)
FUNKTIONS_ZIELE = (ZIEL_FKT_START, ZIEL_FKT_STOP, ZIEL_FKT_UMSCHALTEN)
_TASTE = {ZIEL_GO: "go", ZIEL_BACK: "back", ZIEL_STOP: "stop"}

# ── Wertebereiche ─────────────────────────────────────────────────────────
BEREICH_1 = "0-1"
BEREICH_100 = "0-100"
BEREICH_255 = "0-255"
BEREICHE = {BEREICH_1: 1.0, BEREICH_100: 100.0, BEREICH_255: 255.0}

_AUS_TOKEN = ("0", "off", "false", "no", "aus", "nein")
_AN_TOKEN = ("on", "true", "yes", "an", "ja")


def _int(wert, vorgabe: int, lo: int, hi: int) -> int:
    try:
        n = int(wert)
    except (TypeError, ValueError, OverflowError):
        return vorgabe
    return max(lo, min(hi, n))


def wert_aus_argument(arg, bereich: str = BEREICH_1) -> float | None:
    """Ein OSC-Argument als 0..1 lesen. ``None`` = unbrauchbar (nichts tun).

    bool -> 0/1 (unabhaengig vom Bereich); int/float werden durch die Skala des
    Bereichs geteilt und auf 0..1 geklemmt; Text: Zahl oder on/off-Wort.
    NaN, Unendlich, Blob, Nil und Unbekanntes -> ``None``."""
    skala = BEREICHE.get(bereich, 1.0)
    if isinstance(arg, bool):
        return 1.0 if arg else 0.0
    if arg is None or isinstance(arg, (bytes, bytearray, list, tuple, dict)):
        return None
    if isinstance(arg, str):
        t = arg.strip().lower()
        if t in _AN_TOKEN:
            return 1.0
        if t in _AUS_TOKEN[1:]:
            return 0.0
        try:
            arg = float(t)
        except ValueError:
            return None
    try:
        v = float(arg)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(v):
        return None
    return max(0.0, min(1.0, v / skala))


# ── Muster ────────────────────────────────────────────────────────────────

PLATZHALTER = "{n}"


#: Laengere Adressen werden nicht verglichen (Schutz vor teuren Mustern).
ADRESSE_MAX = 256
#: Hoechstens so viele ``*`` je Adressteil (eine Folge ``**`` zaehlt als einer).
STERNE_JE_TEIL = 2
#: ``{n}`` liest hoechstens so viele Ziffern.
N_ZIFFERN = 6


def _teil_zu_regex(teil: str, zustand: dict) -> str | None:
    """Einen Adressteil (zwischen zwei ``/``) uebersetzen; ``None`` = ungueltig."""
    aus = []
    i = 0
    sterne = 0
    while i < len(teil):
        c = teil[i]
        if teil.startswith(PLATZHALTER, i):
            if zustand["hat_n"]:
                return None
            zustand["hat_n"] = True
            aus.append(r"(?P<n>[0-9]{1,%d})" % N_ZIFFERN)
            i += len(PLATZHALTER)
            continue
        if c == "*":
            while i + 1 < len(teil) and teil[i + 1] == "*":
                i += 1
            sterne += 1
            if sterne > STERNE_JE_TEIL:
                return None
            aus.append(r"[^/]*")
        elif c == "?":
            aus.append(r"[^/]")
        elif c == "[":
            ende = teil.find("]", i + 1)
            if ende < 0:
                return None
            inhalt = teil[i + 1:ende]
            neg = inhalt.startswith("!")
            if neg:
                inhalt = inhalt[1:]
            if not inhalt:
                return None
            teile = []
            for ch in inhalt:
                teile.append("-" if ch == "-" else re.escape(ch))
            aus.append("[" + ("^" if neg else "") + "".join(teile) + "]")
            i = ende
        elif c == "{":
            ende = teil.find("}", i + 1)
            if ende < 0:
                return None
            alternativen = teil[i + 1:ende].split(",")
            aus.append("(?:" + "|".join(re.escape(a) for a in alternativen) + ")")
            i = ende
        elif c in "]}":
            return None
        else:
            aus.append(re.escape(c))
        i += 1
    return "".join(aus)


def muster_zu_regex(muster: str) -> re.Pattern | None:
    """OSC-Adressmuster (mit ``{n}``) in einen regulaeren Ausdruck uebersetzen.
    ``{n}`` wird die Gruppe ``n`` (1–6 Ziffern), hoechstens einmal. Ungueltig
    (leer, ohne fuehrenden ``/``, offene Klammer, ``/`` in Klammern, zweimal
    ``{n}``, mehr als zwei ``*`` in einem Adressteil) -> ``None``.

    Jeder Adressteil ist eine atomare Gruppe, die nur am naechsten ``/`` bzw.
    am Ende enden darf: da kein Platzhalter ``/`` ueberspringt, ist dieses Ende
    eindeutig — die Bedeutung bleibt gleich, aber ein Fehlschlag spaeter in der
    Adresse verfolgt fruehere Teile nicht mehr zurueck (sonst wuchs die
    Rechenzeit mit Sternen in mehreren Teilen exponentiell)."""
    if not isinstance(muster, str):
        return None
    muster = muster.strip()
    if not muster.startswith("/") or any(c.isspace() for c in muster):
        return None
    zustand = {"hat_n": False}
    stuecke = []
    for teil in muster[1:].split("/"):
        rx = _teil_zu_regex(teil, zustand)
        if rx is None:
            return None
        stuecke.append("(?>" + rx + "(?=/|$))")
    try:
        return re.compile("^/" + "/".join(stuecke) + "$")
    except re.error:
        return None


_ZIFFERN = re.compile(r"[0-9]+")


def vorschlag_muster(adresse: str) -> tuple[str, int | None]:
    """OSC-Learn: aus einer konkreten Adresse ein Muster vorschlagen — die
    LETZTE Ziffernfolge wird ``{n}``. ``/Page1/Fader201`` -> (``/Page1/Fader{n}``,
    201), ``/exec/3/go`` -> (``/exec/{n}/go``, 3). Ohne Ziffern: unveraendert."""
    adresse = (adresse or "").strip()
    treffer = list(_ZIFFERN.finditer(adresse))
    if not treffer:
        return adresse, None
    m = treffer[-1]
    if len(m.group()) > N_ZIFFERN:      # passt nie auf {n}
        return adresse, None
    return adresse[:m.start()] + PLATZHALTER + adresse[m.end():], int(m.group())


def vorschlag_ziel(adresse: str, args=()) -> str:
    """OSC-Learn: plausibles Ziel aus Adresse und Argument raten."""
    a = (adresse or "").lower()
    if "blackout" in a or a.endswith("/bo"):
        return ZIEL_BLACKOUT
    if "grand" in a or "/gm" in a:
        return ZIEL_GM
    if "tap" in a:
        return ZIEL_TAP
    for wort, ziel in (("back", ZIEL_BACK), ("stop", ZIEL_STOP),
                       ("release", ZIEL_STOP), ("go", ZIEL_GO),
                       ("push", ZIEL_GO), ("button", ZIEL_GO), ("key", ZIEL_GO)):
        if re.search(r"(^|/|_)" + wort + r"(\d*)($|/|_)", a):
            return ziel
    if "fader" in a or "/pb/" in a or "/sub/" in a or "level" in a:
        return ZIEL_FADER
    if args:
        erstes = args[0]
        if isinstance(erstes, float) and 0.0 < erstes < 1.0:
            return ZIEL_FADER
    return ZIEL_GO if not args else ZIEL_FADER


# ── Datenmodell ───────────────────────────────────────────────────────────

@dataclass
class Zuordnung:
    adresse: str = "/lightos/eigen/{n}"
    ziel: str = ZIEL_FADER
    nummer: int = 1             # feste Zielnummer (ohne {n} und ohne Argument)
    versatz: int = 0            # Zielnummer = n + versatz
    nummer_aus_argument: bool = False
    funktion: str = ""          # Name oder Id (Funktions-Ziele)
    bereich: str = BEREICH_1

    @classmethod
    def aus_dict(cls, d) -> "Zuordnung | None":
        """Eine Zeile aus der Datei; unbrauchbar -> ``None`` (kostet nur sich)."""
        if not isinstance(d, dict):
            return None
        adresse = str(d.get("adresse", "")).strip()
        ziel = str(d.get("ziel", "")).strip()
        if ziel not in ZIELE or muster_zu_regex(adresse) is None:
            return None
        bereich = str(d.get("bereich", BEREICH_1))
        return cls(
            adresse=adresse,
            ziel=ziel,
            nummer=_int(d.get("nummer"), 1, 1, 9999),
            versatz=_int(d.get("versatz"), 0, -9999, 9999),
            nummer_aus_argument=bool(d.get("nummer_aus_argument", False)),
            funktion=str(d.get("funktion", "") or "").strip(),
            bereich=bereich if bereich in BEREICHE else BEREICH_1,
        )

    def als_dict(self) -> dict:
        return asdict(self)


# Rueckmelde-Zustaende
RM_FADER = "fader"
RM_AKTIV = "aktiv"
RM_CUE = "cue"
RM_GM = "grand_master"
RM_BLACKOUT = "blackout"
RM_ARTEN = (RM_FADER, RM_AKTIV, RM_CUE, RM_GM, RM_BLACKOUT)
#: Je Executor gesendet (Adresse mit {n})
RM_JE_EXECUTOR = (RM_FADER, RM_AKTIV, RM_CUE)

RATE_STANDARD = 30
RATE_MAX = 60

#: Echo-Schutz: ein eingehender Wert, der einem in diesem Zeitfenster (s)
#: selbst gemeldeten Wert desselben Ziels entspricht, gilt als Echo.
ECHO_FENSTER = 0.5
ECHO_TOLERANZ = 0.0025      # 0..1; deckt das Runden auf 0-255 ab


@dataclass(frozen=True)
class Vorlage:
    name: str
    titel: str
    adressen: dict
    bereich: str = BEREICH_1
    versatz: int = 0
    geprueft: bool = False
    hinweis: str = ""


#: Ausgangs-Vorlagen. Nur Vorschlaege fuer die Adressen — der Wortlaut fremder
#: Pulte stammt aus deren oeffentlicher Doku und ist OHNE Geraet nicht
#: geprueft (``geprueft=False`` -> im Dialog „ungeprüft“).
VORLAGEN: dict[str, Vorlage] = {v.name: v for v in (
    Vorlage("lightos", "LightOS (eigenes Schema)", {
        RM_FADER: "/lightos/exec/{n}/fader",
        RM_AKTIV: "/lightos/exec/{n}/aktiv",
        RM_CUE: "/lightos/exec/{n}/cue",
        RM_GM: "/lightos/grandmaster",
        RM_BLACKOUT: "/lightos/blackout",
    }, geprueft=True,
        hinweis="Gleiche Adressen wie der Eingang (Fader 0.0–1.0)."),
    Vorlage("touchosc", "TouchOSC (Layout „Simple“)", {
        RM_FADER: "/1/fader{n}",
        RM_AKTIV: "/1/toggle{n}",
        RM_CUE: "",
        RM_GM: "",
        RM_BLACKOUT: "",
    }, hinweis="Adressen eines eigenen Layouts eintragen; nicht mit Gerät geprüft."),
    Vorlage("magicq", "ChamSys MagicQ", {
        RM_FADER: "/pb/{n}",
        RM_AKTIV: "",
        RM_CUE: "",
        RM_GM: "",
        RM_BLACKOUT: "",
    }, bereich=BEREICH_100,
        hinweis="Playback-Pegel 0–100; nicht mit Pult geprüft."),
    Vorlage("grandma3", "grandMA3", {
        RM_FADER: "/Page1/Fader{n}",
        RM_AKTIV: "",
        RM_CUE: "",
        RM_GM: "",
        RM_BLACKOUT: "",
    }, bereich=BEREICH_100, versatz=200,
        hinweis="Executor 1 → Fader201; je nach OSC-Einstellung des Pults mit "
                "Präfix davor. Nicht mit Pult geprüft."),
    Vorlage("eos", "ETC Eos", {
        RM_FADER: "/eos/sub/{n}",
        RM_AKTIV: "",
        RM_CUE: "",
        RM_GM: "",
        RM_BLACKOUT: "",
    }, hinweis="Submaster-Pegel 0.0–1.0; nicht mit Pult geprüft."),
)}


def _ip_gueltig(ip: str) -> bool:
    try:
        ipaddress.ip_address(str(ip).strip())
        return True
    except ValueError:
        return False


def executoren_aus_text(text: str) -> list[int]:
    """``"1-4, 8"`` -> [1, 2, 3, 4, 8]; ausserhalb 1..20 und Unlesbares fallen weg."""
    aus: list[int] = []
    for teil in str(text or "").replace(";", ",").split(","):
        teil = teil.strip()
        if not teil:
            continue
        try:
            if "-" in teil:
                a, b = (int(x) for x in teil.split("-", 1))
                bereich = range(min(a, b), max(a, b) + 1)
            else:
                bereich = range(int(teil), int(teil) + 1)
        except ValueError:
            continue
        for n in bereich:
            if 1 <= n <= EXECUTOR_MAX and n not in aus:
                aus.append(n)
    return aus


@dataclass
class RueckmeldeKonfig:
    aktiv: bool = False
    ziel_ip: str = "127.0.0.1"
    ziel_port: int = 9000
    vorlage: str = "lightos"
    executoren: str = "1-10"
    versatz: int = 0            # gesendete Nummer = Executor + versatz
    bereich: str = BEREICH_1    # Fader / Grand Master
    rate_hz: int = RATE_STANDARD
    adressen: dict = field(default_factory=lambda: dict(VORLAGEN["lightos"].adressen))

    @classmethod
    def aus_dict(cls, d) -> "RueckmeldeKonfig":
        if not isinstance(d, dict):
            return cls()
        ip = str(d.get("ziel_ip", "127.0.0.1")).strip()
        bereich = str(d.get("bereich", BEREICH_1))
        adressen_roh = d.get("adressen") if isinstance(d.get("adressen"), dict) else {}
        adressen = {}
        for art in RM_ARTEN:
            a = str(adressen_roh.get(art, "") or "").strip()
            # Ungueltig (kein /, Leerzeichen) -> leer = nicht senden.
            adressen[art] = a if (a.startswith("/") and not any(
                c.isspace() for c in a)) else ""
        vorlage = str(d.get("vorlage", "lightos"))
        return cls(
            aktiv=bool(d.get("aktiv", False)),
            ziel_ip=ip if _ip_gueltig(ip) else "127.0.0.1",
            ziel_port=_int(d.get("ziel_port"), 9000, 1, 65535),
            vorlage=vorlage if vorlage in VORLAGEN else "lightos",
            executoren=str(d.get("executoren", "1-10")),
            versatz=_int(d.get("versatz"), 0, -9999, 9999),
            bereich=bereich if bereich in BEREICHE else BEREICH_1,
            rate_hz=_int(d.get("rate_hz"), RATE_STANDARD, 1, RATE_MAX),
            adressen=adressen,
        )

    def als_dict(self) -> dict:
        return asdict(self)

    def vorlage_anwenden(self, name: str) -> None:
        v = VORLAGEN.get(name)
        if v is None:
            return
        self.vorlage = name
        self.adressen = dict(v.adressen)
        self.bereich = v.bereich
        self.versatz = v.versatz


@dataclass
class Konfig:
    aktiv: bool = True          # Zuordnungen wirken (Rueckmeldung hat eigenes aktiv)
    zuordnungen: list[Zuordnung] = field(default_factory=list)
    rueckmeldung: RueckmeldeKonfig = field(default_factory=RueckmeldeKonfig)

    @classmethod
    def aus_dict(cls, d) -> "Konfig":
        if not isinstance(d, dict):
            return cls()
        zs = []
        roh = d.get("zuordnungen")
        for z in roh if isinstance(roh, list) else []:
            zz = Zuordnung.aus_dict(z)
            if zz is not None:
                zs.append(zz)
        return cls(aktiv=bool(d.get("aktiv", True)), zuordnungen=zs,
                   rueckmeldung=RueckmeldeKonfig.aus_dict(d.get("rueckmeldung")))

    def als_dict(self) -> dict:
        return {"version": FORMAT_VERSION, "aktiv": bool(self.aktiv),
                "zuordnungen": [z.als_dict() for z in self.zuordnungen],
                "rueckmeldung": self.rueckmeldung.als_dict()}


def konfig_pfad() -> str:
    from src.core.paths import osc_zuordnungen_path
    return osc_zuordnungen_path()


def lade_konfig(pfad: str | None = None) -> Konfig:
    """Fehlende oder kaputte Datei -> leere Konfiguration (Rueckmeldung aus)."""
    pfad = pfad or konfig_pfad()
    try:
        with open(pfad, "r", encoding="utf-8") as f:
            return Konfig.aus_dict(json.load(f))
    except (OSError, ValueError, RecursionError):
        return Konfig()


def speichere_konfig(konfig: Konfig, pfad: str | None = None) -> bool:
    """Atomar schreiben (Hilfsdatei + ``os.replace``). ``True`` = geschrieben."""
    pfad = pfad or konfig_pfad()
    try:
        ordner = os.path.dirname(pfad)
        if ordner:
            os.makedirs(ordner, exist_ok=True)
        tmp = pfad + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(konfig.als_dict(), f, indent=2, ensure_ascii=False)
        os.replace(tmp, pfad)
        return True
    except OSError as e:
        from src.core.diagnose_log import melde_still
        melde_still("osc.zuordnung", e, text="speichern")
        return False


# ── Eingang ───────────────────────────────────────────────────────────────

@dataclass
class Aktion:
    """Eine im OSC-Thread erkannte, noch nicht angewandte Aktion."""
    ziel: str
    nummer: int = 0             # Executor- bzw. Funktions-Id (0 = keine)
    wert: float | None = None   # 0..1 (Fader/GM/Blackout)
    funktion: str = ""          # Name/Id-Text (Funktions-Ziele)


_LOSGELASSEN = object()

#: Die festen Adressen des OscServers — Lernen uebergeht sie (sie wirken
#: schon ohne Zuordnung; zugeordnet loesten sie doppelt aus).
_FESTE = re.compile(r"^/lightos/(go|back|blackout|programmer/clear|exec/.*|ch/.*)$")


def ist_feste_adresse(adresse: str) -> bool:
    return bool(_FESTE.match(str(adresse or "")))


def _zahl(arg) -> int | None:
    """Zielnummer aus einem Argument: ganze Zahl (int, float ohne Rest,
    Ziffern-Text). bool und alles andere -> ``None``."""
    if isinstance(arg, bool):
        return None
    if isinstance(arg, int):
        return arg
    if isinstance(arg, float):
        return int(arg) if math.isfinite(arg) and arg == int(arg) else None
    if isinstance(arg, str):
        t = arg.strip()
        if re.fullmatch(r"-?[0-9]{1,%d}" % N_ZIFFERN, t):
            return int(t)
    return None


def _gedrueckt(werte, bereich: str) -> bool | None:
    """Taste: ohne Argument = Druck (Bang). Mit Argument: >= halbe Skala.
    Kaputtes Argument -> ``None`` (nichts tun)."""
    if not werte:
        return True
    if werte[0] is None:        # OSC-Nil als Bang
        return True
    w = wert_aus_argument(werte[0], bereich)
    if w is None:
        return None
    return w >= 0.5


class OscZuordnung:
    """Zuordnungen anwenden (Eingang) und OSC-Learn."""

    def __init__(self):
        self._lock = threading.Lock()
        self._konfig = Konfig()
        self._kompiliert: list[tuple[re.Pattern, Zuordnung]] = []
        self._queue: "queue.SimpleQueue[Aktion]" = queue.SimpleQueue()
        self._wecker: Callable[[], None] | None = None
        self._lerner: Callable[[str, tuple, object], None] | None = None
        self._rueckmeldung: "OscRueckmeldung | None" = None
        self.angewandt = 0
        self.verworfen = 0      # Treffer mit kaputtem Argument / Nummer
        self.echos = 0          # verworfene Echos der eigenen Rueckmeldung

    def set_rueckmeldung(self, rm: "OscRueckmeldung | None") -> None:
        """Fuer den Echo-Schutz: Werte, die die Rueckmeldung gerade selbst
        gesendet hat, kommen als Echo zurueck und werden verworfen."""
        self._rueckmeldung = rm

    @property
    def konfig(self) -> Konfig:
        return self._konfig

    def konfigurieren(self, konfig: Konfig) -> None:
        komp = []
        if konfig.aktiv:
            for z in konfig.zuordnungen:
                rx = muster_zu_regex(z.adresse)
                if rx is not None:
                    komp.append((rx, z))
        with self._lock:
            self._konfig = konfig
            self._kompiliert = komp
        self._leeren()

    # ── Learn ─────────────────────────────────────────────────────────────

    def lerne(self, rueckruf: Callable[[str, tuple, object], None] | None) -> None:
        """Die NAECHSTE eingehende Nachricht an ``rueckruf(adresse, args,
        absender)`` melden (aus dem OSC-Thread!) und danach aufhoeren.
        ``None`` bricht ab. Die gelernte Nachricht loest keine Zuordnung aus."""
        with self._lock:
            self._lerner = rueckruf

    @property
    def lernt(self) -> bool:
        return self._lerner is not None

    # ── OSC-Thread ────────────────────────────────────────────────────────

    def empfange(self, adresse: str, args=(), absender=None) -> int:
        """Im OSC-Thread: Treffer suchen, Aktionen einreihen. Liefert die Zahl
        neu eingereihter Aktionen; wendet NICHTS selbst an."""
        args = tuple(args)
        if not isinstance(adresse, str) or len(adresse) > ADRESSE_MAX:
            return 0
        rm = self._rueckmeldung
        # Lernen uebergeht feste /lightos-Adressen und Echos der eigenen
        # Rueckmeldung; sie laufen normal weiter, das Lernen wartet weiter.
        uebergehen = self._lerner is not None and (
            ist_feste_adresse(adresse)
            or (rm is not None and rm.ist_echo_adresse(adresse, args)))
        with self._lock:
            lerner = None if uebergehen else self._lerner
            if lerner is not None:
                self._lerner = None
            kompiliert = self._kompiliert
        # Vergleichen ausserhalb der Sperre: konfigurieren()/lerne() aus dem
        # GUI-Thread warten nie auf ein Paket.
        treffer = [] if lerner is not None else [
            (rx.match(adresse), z) for rx, z in kompiliert]
        if lerner is not None:
            try:
                lerner(adresse, args, absender)
            except Exception as e:
                from src.core.diagnose_log import melde_still
                melde_still("osc.lernen", e, text=str(adresse))
            return 0
        neu = 0
        for m, z in treffer:
            if m is None:
                continue
            try:
                a = self._aktion(m, z, args)
            except Exception as e:          # kostet nur diesen Treffer
                from src.core.diagnose_log import melde_still
                melde_still("osc.zuordnung", e, text=str(adresse)[:80])
                a = None
            if a is _LOSGELASSEN:
                continue
            if a is None:
                with self._lock:
                    self.verworfen += 1
                continue
            self._queue.put(a)
            neu += 1
        if neu:
            w = self._wecker
            if w is not None:
                try:
                    w()
                except Exception as e:
                    from src.core.diagnose_log import melde_still
                    melde_still("osc.zuordnung", e, text="wecker")
            else:
                # Ohne Qt-Bruecke (Skript, headless): direkt anwenden, wie die
                # festen Adressen des OscServers es tun.
                self.abarbeiten()
        return neu

    @staticmethod
    def _aktion(m: re.Match, z: Zuordnung, args: tuple):
        """Aktion fuer einen Treffer. ``None`` = kaputt (Argument/Nummer),
        ``_LOSGELASSEN`` = Taste losgelassen (bewusst nichts)."""
        werte = args
        if "n" in m.re.groupindex:
            nummer = int(m.group("n")) + z.versatz
        elif z.nummer_aus_argument:
            nummer = _zahl(args[0]) if args else None
            if nummer is None:
                return None
            nummer += z.versatz
            werte = args[1:]
        else:
            nummer = z.nummer
        if z.ziel in EXECUTOR_ZIELE and not (1 <= nummer <= EXECUTOR_MAX):
            return None
        if z.ziel in WERT_ZIELE:
            w = wert_aus_argument(werte[0], z.bereich) if werte else None
            if w is None:
                return None
            return Aktion(z.ziel, nummer, w)
        druck = _gedrueckt(werte, z.bereich)
        if druck is None:
            return None
        if not druck:
            return _LOSGELASSEN
        if z.ziel in FUNKTIONS_ZIELE:
            # Name/Id im Feld „Funktion“ hat Vorrang, sonst ist die
            # Zielnummer die Funktions-Id.
            if z.funktion:
                return Aktion(z.ziel, 0, None, z.funktion)
            if nummer < 1:
                return None
            return Aktion(z.ziel, nummer)
        return Aktion(z.ziel, nummer)

    # ── GUI-Thread ────────────────────────────────────────────────────────

    def set_wecker(self, wecker: Callable[[], None] | None) -> None:
        self._wecker = wecker

    def _leeren(self) -> list[Aktion]:
        aus = []
        while True:
            try:
                aus.append(self._queue.get_nowait())
            except queue.Empty:
                return aus

    def abarbeiten(self, state=None) -> int:
        """Wartende Aktionen anwenden (GUI-Thread). Mehrere Werte fuer
        dasselbe Wert-Ziel fallen auf den letzten zusammen; Tasten zaehlen
        einzeln. Liefert die Zahl angewandter Aktionen."""
        aktionen = self._leeren()
        if not aktionen:
            return 0
        if state is None:
            from src.core.app_state import get_state
            state = get_state()
        letzte: dict[tuple[str, int], Aktion] = {}
        reihe: list = []
        for a in aktionen:
            if a.ziel in WERT_ZIELE:
                k = (a.ziel, a.nummer if a.ziel == ZIEL_FADER else 0)
                if k not in letzte:
                    reihe.append(k)
                letzte[k] = a
            else:
                reihe.append(a)
        n = 0
        rm = self._rueckmeldung
        for eintrag in reihe:
            a = letzte[eintrag] if isinstance(eintrag, tuple) else eintrag
            try:
                if rm is not None and a.ziel in WERT_ZIELE:
                    if rm.ist_echo(a.ziel, a.nummer, a.wert):
                        self.echos += 1
                        continue
                    rm.extern_gesetzt(a.ziel, a.nummer, a.wert)
                if self._anwenden(state, a):
                    n += 1
            except Exception as e:
                from src.core.diagnose_log import melde_still
                melde_still("osc.zuordnung", e, text=a.ziel)
        self.angewandt += n
        return n

    @staticmethod
    def _funktion_finden(fm, a: Aktion):
        if a.funktion:
            t = a.funktion.strip()
            if t.isdigit():
                return fm.get(int(t))
            for f in fm.all():
                if str(getattr(f, "name", "")).strip().lower() == t.lower():
                    return f
            return None
        return fm.get(int(a.nummer)) if a.nummer else None

    @classmethod
    def _anwenden(cls, state, a: Aktion) -> bool:
        pe = getattr(state, "playback_engine", None)
        if a.ziel == ZIEL_GM:
            val = max(0.0, min(1.0, float(a.wert)))
            state.output_manager.set_grand_master(val)
            if pe is not None:      # wie midi_mapper/fernsteuerung
                for ex in pe.executors:
                    if getattr(ex, "fader_function", "") == "master":
                        ex.fader_value = val
            return True
        if a.ziel == ZIEL_BLACKOUT:
            state.output_manager.set_blackout(float(a.wert) >= 0.5)
            return True
        if a.ziel == ZIEL_TAP:
            from src.core.engine.bpm_manager import get_bpm_manager
            get_bpm_manager().tap()
            return True
        if a.ziel in FUNKTIONS_ZIELE:
            fm = getattr(state, "function_manager", None)
            if fm is None:
                return False
            f = cls._funktion_finden(fm, a)
            if f is None:
                return False
            fid = f.id
            if a.ziel == ZIEL_FKT_START:
                fm.start(fid)
            elif a.ziel == ZIEL_FKT_STOP:
                fm.stop(fid)
            elif fm.is_running(fid):
                fm.stop(fid)
            else:
                fm.start(fid)
            return True
        if pe is None:
            return False
        ex = pe.get_executor(int(a.nummer))
        if a.ziel == ZIEL_FADER:
            ex.fader_value = max(0.0, min(1.0, float(a.wert)))
            return True
        taste = _TASTE.get(a.ziel)
        if taste:
            ex.press_btn(taste)
            return True
        return False


# ── Rueckmeldung ──────────────────────────────────────────────────────────

class OscRueckmeldung:
    """Zustaende per OSC an ein Ziel melden — nur bei Aenderung, gedrosselt.

    :meth:`tick` laeuft im GUI-Thread (QTimer der Qt-Bruecke) und liest dort
    den App-Zustand. Ein Wert gilt erst als gemeldet, wenn ``send`` ``True``
    lieferte (erst senden, dann merken) — ein Aussetzer wird beim naechsten
    Durchgang nachgeholt statt dauerhaft verschluckt."""

    #: hoechstens so viele Nachrichten je Durchgang; der Rest folgt im naechsten
    MAX_JE_TICK = 64

    def __init__(self, sender_fabrik: Callable[[str, int], object] | None = None,
                 uhr: Callable[[], float] = time.monotonic):
        self._fabrik = sender_fabrik or self._standard_sender
        self._uhr = uhr
        self._konfig = RueckmeldeKonfig()
        self._sender = None
        self._cache: dict[str, object] = {}
        self._letzter_tick = -1e9
        self.gesendet = 0
        # Echo-Schutz (GUI-Thread schreibt; der OSC-Thread liest nur per get)
        self._echo: dict[tuple, list[tuple[float, float]]] = {}
        self._extern: dict[tuple, float] = {}
        self._zuletzt: dict[str, tuple[object, float]] = {}

    @staticmethod
    def _standard_sender(ip: str, port: int):
        from src.core.osc.osc_server import OscSender
        return OscSender(ip, port)

    @property
    def konfig(self) -> RueckmeldeKonfig:
        return self._konfig

    def konfigurieren(self, konfig: RueckmeldeKonfig) -> None:
        alt = self._sender
        self._konfig = konfig
        self._cache.clear()
        self._echo.clear()
        self._extern.clear()
        self._zuletzt.clear()
        self._sender = None
        if alt is not None:
            try:
                alt.close()
            except Exception:
                pass
        if konfig.aktiv:
            try:
                self._sender = self._fabrik(konfig.ziel_ip, int(konfig.ziel_port))
            except Exception as e:
                from src.core.diagnose_log import melde_still
                melde_still("osc.rueckmeldung", e, text=str(konfig.ziel_ip))
                self._sender = None

    def alles_neu(self) -> None:
        """Beim naechsten Durchgang alle Werte senden (z. B. Oberflaeche neu verbunden)."""
        self._cache.clear()

    @property
    def aktiv(self) -> bool:
        return bool(self._konfig.aktiv and self._sender is not None)

    @staticmethod
    def _wert(roh: float, bereich: str):
        skala = BEREICHE.get(bereich, 1.0)
        if bereich == BEREICH_255:
            return int(round(roh * 255))
        if bereich == BEREICH_100:
            return round(roh * skala, 1)
        return round(roh, 3)

    def zustaende(self, state) -> dict[str, object]:
        """Soll-Werte {Adresse: Wert} aus dem App-Zustand."""
        return {a: w for a, (w, _s, _r) in self._soll(state).items()}

    def _soll(self, state) -> dict[str, tuple]:
        """{Adresse: (Wert, Echo-Schluessel oder None, Wert 0..1)}."""
        k = self._konfig
        ad = k.adressen
        aus: dict[str, tuple] = {}
        om = getattr(state, "output_manager", None)
        if om is not None:
            if ad.get(RM_GM):
                try:
                    roh = float(om.grand_master)
                    aus[ad[RM_GM]] = (self._wert(roh, k.bereich), (ZIEL_GM, 0), roh)
                except Exception:
                    pass
            if ad.get(RM_BLACKOUT):
                try:
                    an = 1 if om.blackout else 0
                    aus[ad[RM_BLACKOUT]] = (an, (ZIEL_BLACKOUT, 0), float(an))
                except Exception:
                    pass
        pe = getattr(state, "playback_engine", None)
        if pe is None:
            return aus
        for n in executoren_aus_text(k.executoren):
            try:
                ex = pe.get_executor(n)
            except Exception:
                continue
            nr = str(n + k.versatz)
            stack = getattr(ex, "stack", None)
            idx = getattr(stack, "current_index", -1) if stack is not None else -1
            for art in RM_JE_EXECUTOR:
                muster = ad.get(art)
                if not muster:
                    continue
                adresse = muster.replace(PLATZHALTER, nr)
                if art == RM_FADER:
                    roh = float(ex.fader_value)
                    aus[adresse] = (self._wert(roh, k.bereich), (ZIEL_FADER, n), roh)
                elif art == RM_AKTIV:
                    aus[adresse] = (1 if idx >= 0 else 0, None, 0.0)
                else:
                    aus[adresse] = (idx + 1 if idx >= 0 else 0, None, 0.0)
        return aus

    # ── Echo-Schutz ───────────────────────────────────────────────────────

    @staticmethod
    def _gleich(ziel: str, a: float, b: float) -> bool:
        if ziel == ZIEL_BLACKOUT:
            return (a >= 0.5) == (b >= 0.5)
        return abs(a - b) <= ECHO_TOLERANZ

    def _merken(self, schluessel: tuple, roh: float, jetzt: float) -> None:
        ext = self._extern.pop(schluessel, None)
        if ext is not None and self._gleich(schluessel[0], ext, roh):
            # Der Wert kam selbst vom Pult: sein Echo ist harmlos, und eine
            # spaetere echte Pultbewegung auf denselben Wert soll wirken.
            return
        liste = [e for e in self._echo.get(schluessel, ())
                 if jetzt - e[1] <= ECHO_FENSTER]
        liste.append((roh, jetzt))
        self._echo[schluessel] = liste

    def ist_echo(self, ziel: str, nummer: int, wert, jetzt: float | None = None) -> bool:
        """GUI-Thread: ist dieser eingehende Wert (0..1) das Echo eines eben
        selbst gemeldeten Werts desselben Ziels? Dann nicht anwenden — sonst
        ueberschriebe ein verspaetetes Echo eine lokale Bewegung."""
        if wert is None or ziel not in WERT_ZIELE:
            return False
        jetzt = self._uhr() if jetzt is None else jetzt
        schluessel = (ziel, int(nummer) if ziel == ZIEL_FADER else 0)
        return any(jetzt - t <= ECHO_FENSTER and self._gleich(ziel, w, float(wert))
                   for w, t in self._echo.get(schluessel, ()))

    def extern_gesetzt(self, ziel: str, nummer: int, wert) -> None:
        """GUI-Thread: dieser Wert kam vom Pult (kein Echo-Kandidat)."""
        if wert is None or ziel not in WERT_ZIELE:
            return
        self._extern[(ziel, int(nummer) if ziel == ZIEL_FADER else 0)] = float(wert)

    def ist_echo_adresse(self, adresse: str, args, jetzt: float | None = None) -> bool:
        """OSC-Thread (fuer Lernen): kam auf genau dieser Adresse eben der
        eigene Wert zurueck?"""
        e = self._zuletzt.get(adresse)
        if e is None or not args:
            return False
        wert, t = e
        jetzt = self._uhr() if jetzt is None else jetzt
        if jetzt - t > ECHO_FENSTER:
            return False
        try:
            return abs(float(args[0]) - float(wert)) <= 1e-3 * max(1.0, abs(float(wert)))
        except (TypeError, ValueError, OverflowError):
            return False

    def tick(self, state=None, jetzt: float | None = None) -> int:
        """Einen Durchgang senden, wenn die Drossel es erlaubt. Liefert die
        Zahl gesendeter Nachrichten."""
        if not self.aktiv:
            return 0
        jetzt = self._uhr() if jetzt is None else jetzt
        if jetzt - self._letzter_tick < 1.0 / max(1, min(RATE_MAX, self._konfig.rate_hz)):
            return 0
        self._letzter_tick = jetzt
        if state is None:
            from src.core.app_state import get_state
            state = get_state()
        n = 0
        for adresse, (wert, schluessel, roh) in self._soll(state).items():
            if self._cache.get(adresse, object()) == wert:
                continue
            if n >= self.MAX_JE_TICK:
                break
            ok = self._sender.send(adresse, wert)
            if ok is False:
                continue        # nicht merken -> naechster Durchgang
            self._cache[adresse] = wert
            self._zuletzt[adresse] = (wert, jetzt)
            if schluessel is not None:
                self._merken(schluessel, roh, jetzt)
            n += 1
        self.gesendet += n
        return n


# ── Singletons + Qt-Bruecke ───────────────────────────────────────────────

_zuordnung: OscZuordnung | None = None
_rueckmeldung: OscRueckmeldung | None = None
_instanz_lock = threading.Lock()


def get_osc_zuordnung() -> OscZuordnung:
    global _zuordnung
    with _instanz_lock:
        if _zuordnung is None:
            _zuordnung = OscZuordnung()
        return _zuordnung


def get_osc_rueckmeldung() -> OscRueckmeldung:
    global _rueckmeldung
    with _instanz_lock:
        if _rueckmeldung is None:
            _rueckmeldung = OscRueckmeldung()
        return _rueckmeldung


_qt_bruecke = None


def installiere_qt_bruecke():
    """Im GUI-Thread aufrufen (einmal je Prozess): elternloses QObject, dessen
    Signal aus dem OSC-Thread gefeuert und per Queued-Connection im GUI-Thread
    ausgeliefert wird (dort laeuft :meth:`OscZuordnung.abarbeiten`), plus der
    QTimer der Rueckmeldung."""
    global _qt_bruecke
    zu = get_osc_zuordnung()
    if _qt_bruecke is not None:
        zu.set_wecker(_qt_bruecke.wecken)
        _qt_bruecke.rueckmeldung_pruefen()
        return _qt_bruecke
    from PySide6.QtCore import QObject, Qt, QTimer, Signal

    class _Bruecke(QObject):
        anstossen = Signal()

        def __init__(self, zu: OscZuordnung, rm: OscRueckmeldung):
            super().__init__(None)
            self._zu = zu
            self._rm = rm
            self._unterwegs = threading.Event()
            self.anstossen.connect(self._los, Qt.ConnectionType.QueuedConnection)
            self._timer = QTimer(self)
            self._timer.timeout.connect(self._rm_tick)

        def wecken(self):
            if not self._unterwegs.is_set():
                self._unterwegs.set()
                self.anstossen.emit()

        def _los(self):
            self._unterwegs.clear()
            self._zu.abarbeiten()

        def _rm_tick(self):
            try:
                self._rm.tick()
            except Exception as e:
                from src.core.diagnose_log import melde_still
                melde_still("osc.rueckmeldung", e, text="tick")

        def rueckmeldung_pruefen(self):
            if self._rm.aktiv:
                ms = max(5, int(1000 / max(1, self._rm.konfig.rate_hz)))
                self._timer.start(ms)
            else:
                self._timer.stop()

    _qt_bruecke = _Bruecke(zu, get_osc_rueckmeldung())
    zu.set_wecker(_qt_bruecke.wecken)
    _qt_bruecke.rueckmeldung_pruefen()
    return _qt_bruecke


def anwenden(konfig: Konfig) -> None:
    """Konfiguration in Eingang und Rueckmeldung uebernehmen (GUI-Thread)."""
    get_osc_zuordnung().set_rueckmeldung(get_osc_rueckmeldung())
    get_osc_zuordnung().konfigurieren(konfig)
    get_osc_rueckmeldung().konfigurieren(konfig.rueckmeldung)
    if _qt_bruecke is not None:
        _qt_bruecke.rueckmeldung_pruefen()


def beim_start() -> Konfig:
    """App-Start (GUI-Thread): gespeicherte Zuordnung laden, Qt-Bruecke
    einrichten. Startet KEINEN Server — der OSC-Eingang bleibt opt-in."""
    konfig = lade_konfig()
    installiere_qt_bruecke()
    anwenden(konfig)
    return konfig
