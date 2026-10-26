"""LIZ-1: Urheberangabe und Testlizenz (Kern ohne Qt).

LightOS ist in der Testphase: der Quelltext ist oeffentlich einsehbar, benutzen
darf man das Programm nur mit Erlaubnis des Urhebers (siehe ``LICENSE``). Diese
Erlaubnis kommt als kleine **Lizenzdatei** — JSON, UTF-8::

    {"format": 1, "kennung": "…", "name": "…", "gueltig_bis": "2027-01-31",
     "ausgestellt_am": "2026-10-12", "hinweis": "…", "signatur": "<Base64>"}

``gueltig_bis`` ist ein ISO-Datum (der Tag zaehlt noch mit) oder ``null`` fuer
unbefristet. ``signatur`` ist eine Ed25519-Signatur ueber alle uebrigen Felder
in kanonischer Schreibweise (:func:`kanonisch`). Geprueft wird gegen den
oeffentlichen Schluessel unten; der zugehoerige private Schluessel liegt nur
beim Urheber.

Wichtig fuer den Betrieb:

* **Geprueft wird nur beim Programmstart** (``main.py``). Laeuft die App, hat
  ein Ablauf keinerlei Wirkung — eine laufende Show wird nie unterbrochen.
* **Kein Netz.** Die Pruefung liest eine Datei und rechnet; die App geht nie
  ins Internet. Die Systemuhr wird nicht gegengeprueft.
* **Nie eine Ausnahme nach aussen.** Jede Pruef-Funktion liefert einen
  :class:`Lizenzstatus`.
* Im oeffentlichen Quelltext laesst sich die Abfrage entfernen. Das ist
  bekannt und hingenommen: sie ist Huerde und klares Zeichen, kein Kopierschutz.

Suchorte der Lizenzdatei (:func:`suchorte`): die Umgebungsvariable
``LIGHTOS_LIZENZ`` (Pfad), danach ``<App-Datenordner>/lightos-lizenz.lic``.
"""
from __future__ import annotations

import base64
import binascii
import datetime as _dt
import json
import os
import secrets
import sys
from dataclasses import dataclass

from src.core import ed25519
from src.core.paths import app_data_dir

# ── Urheberangabe (eine Quelle fuer Fenster, Log, Show-Datei, Diagnosepaket) ──
PROGRAMM = "LightOS"
URHEBER = "ixamgames-droid"
QUELLE = "https://github.com/ixamgames-droid/lightos"
COPYRIGHT = f"Copyright (c) 2026 {URHEBER} — alle Rechte vorbehalten"

# Kennzeichen des Herkunftsvermerks in erzeugten Dateien (Show, Diagnosepaket);
# aendert sich nur, wenn sich der Aufbau des Vermerks aendert.
_VERMERK_SHOW = "2fc2b88a94d5"
_VERMERK_PAKET = "3b97438b"

# ── Lizenzdatei ──────────────────────────────────────────────────────────────
DATEINAME = "lightos-lizenz.lic"
ENV_PFAD = "LIGHTOS_LIZENZ"
FORMAT = 1
#: Ab so vielen Tagen vor dem Ablauf weist der Start dezent darauf hin.
VORWARN_TAGE = 14

#: Oeffentlicher Ed25519-Schluessel (32 Bytes), gegen den Lizenzdateien geprueft
#: werden. Ein neuer Schluessel macht alle bisherigen Lizenzdateien ungueltig.
OEFFENTLICHER_SCHLUESSEL = bytes.fromhex(
    "b5e3c12e1a76dc7a2a3e594438dcdf8d5bf783a7c6cb9535ebb47b56480e6052")

# Vorspann der signierten Nachricht: trennt Lizenz-Signaturen von allem, was
# sonst je mit demselben Schluessel signiert werden koennte.
_KONTEXT = bytes.fromhex("7bffd5d5b27ab7c2")
# Eine Lizenzdatei hat wenige hundert Bytes. Groessere Dateien werden gar nicht
# erst eingelesen (jemand waehlt im Dialog versehentlich ein Video aus).
_MAX_BYTES = 19536
# Felder der Formatversion 1 (``signatur`` kommt beim Signieren hinzu).
_FELDER = ("kennung", "format", "ausgestellt_am", "hinweis", "gueltig_bis", "name")
# Zeichenvorrat der Kennung: ohne 0/O und 1/I, damit sie sich vorlesen laesst.
_KENNUNG_ZEICHEN = "5N4AG3U6J2CDHBLVYP8MFSQKWX7ER9ZT"
_KENNUNG_LAENGE = 12

# ── Zustaende ────────────────────────────────────────────────────────────────
GUELTIG = "gueltig"
FEHLT = "fehlt"
ABGELAUFEN = "abgelaufen"
UNGUELTIG = "ungueltig"

#: Umgehung fuer die Testsuite — wirkt NUR unter pytest (:func:`testlauf`).
ENV_TESTLAUF = "LIGHTOS_LIZENZ_TESTLAUF"


def _datum_text(tag: _dt.date | None) -> str:
    return tag.strftime("%d.%m.%Y") if tag else ""


@dataclass(frozen=True)
class Lizenzstatus:
    """Ergebnis einer Pruefung. ``name``/``kennung``/``gueltig_bis`` sind nur
    gefuellt, wenn die Signatur gepasst hat (also bei gueltig und abgelaufen)."""
    zustand: str
    name: str = ""
    kennung: str = ""
    gueltig_bis: _dt.date | None = None
    grund: str = ""
    pfad: str = ""

    @property
    def ist_gueltig(self) -> bool:
        return self.zustand == GUELTIG

    @property
    def unbefristet(self) -> bool:
        return self.ist_gueltig and self.gueltig_bis is None

    @property
    def kurzkennung(self) -> str:
        """Gekuerzte Kennung fuer Log und Diagnosepaket — dort steht bewusst
        NICHT der Name des Lizenznehmers."""
        return (self.kennung[:6] + "…") if self.kennung else ""

    def tage_bis_ablauf(self, heute: _dt.date | None = None) -> int | None:
        """Volle Tage bis zum letzten gueltigen Tag; ``None`` bei unbefristet."""
        if self.gueltig_bis is None:
            return None
        return (self.gueltig_bis - (heute or _dt.date.today())).days

    def laeuft_bald_ab(self, heute: _dt.date | None = None) -> bool:
        tage = self.tage_bis_ablauf(heute)
        return self.ist_gueltig and tage is not None and tage <= VORWARN_TAGE

    def text(self) -> str:
        """Fuer Menschen, MIT Namen (Fenster „Über LightOS“, Dialog)."""
        if self.zustand == GUELTIG:
            if self.gueltig_bis is None:
                return f"lizenziert für {self.name}, unbefristet gültig"
            return (f"lizenziert für {self.name}, gültig bis "
                    f"{_datum_text(self.gueltig_bis)}")
        if self.zustand == ABGELAUFEN:
            return (f"nicht lizenziert — die Testlizenz für {self.name} ist am "
                    f"{_datum_text(self.gueltig_bis)} abgelaufen")
        if self.zustand == FEHLT:
            return "nicht lizenziert — keine Lizenzdatei gefunden"
        return "nicht lizenziert — die Lizenzdatei ist ungültig" + (
            f" ({self.grund})" if self.grund else "")

    def log_text(self) -> str:
        """Fuer Log und Diagnosepaket, OHNE Namen (nur gekuerzte Kennung)."""
        if self.zustand == GUELTIG:
            bis = ("unbefristet" if self.gueltig_bis is None
                   else f"bis {self.gueltig_bis.isoformat()}")
            return f"gueltig ({bis}, Kennung {self.kurzkennung})"
        if self.zustand == ABGELAUFEN:
            return (f"abgelaufen seit {self.gueltig_bis.isoformat() if self.gueltig_bis else '?'}"
                    f" (Kennung {self.kurzkennung})")
        if self.zustand == FEHLT:
            return "fehlt"
        return "ungueltig" + (f" ({self.grund})" if self.grund else "")


# ── Herkunftsvermerk in erzeugten Dateien ────────────────────────────────────

_version_cache: list[str] = []


def programmversion() -> str:
    """``APP_VERSION`` aus ``main.py`` (einmal gelesen); ``"?"``, wenn nicht
    ermittelbar."""
    if not _version_cache:
        version = None
        try:
            from src.core.audio.audio_recorder import _lightos_version
            version = _lightos_version()
        except Exception:                           # noqa: BLE001
            version = None
        _version_cache.append(version if isinstance(version, str) and version else "?")
    return _version_cache[0]


def erstellt_mit() -> dict:
    """Der Vermerk im Kopf einer gespeicherten Show (``show.json``).

    Fest und deterministisch: haengt nur an der Programmversion, nicht an Uhr,
    Rechner oder Lizenznehmer — zweimal Speichern ergibt dieselben Bytes."""
    return {
        "programm": PROGRAMM,
        "urheber": URHEBER,
        "quelle": QUELLE,
        "version": programmversion(),
        "kennzeichen": _VERMERK_SHOW,
    }


def vermerk_zeile(version: str | None = None) -> str:
    """„erstellt mit LightOS … von ixamgames-droid“ fuer Textdateien."""
    return (f"erstellt mit {PROGRAMM} {version or programmversion()} von "
            f"{URHEBER} — {QUELLE}")


def paket_kennzeichen() -> str:
    return f"1-{_VERMERK_PAKET}"


# ── Lesen und Pruefen ────────────────────────────────────────────────────────

def kanonisch(daten: dict) -> bytes:
    """Die signierte Nachricht zu einer Lizenz: alle Felder ausser ``signatur``,
    als JSON mit sortierten Schluesseln, ohne Leerraum, UTF-8."""
    felder = {k: v for k, v in daten.items() if k != "signatur"}
    text = json.dumps(felder, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"))
    return _KONTEXT + text.encode("utf-8")


def _datum(wert) -> _dt.date:
    if not isinstance(wert, str):
        raise ValueError("kein Datum")
    return _dt.date.fromisoformat(wert.strip())


def pruefe_daten(daten, heute: _dt.date | None = None, pfad: str = "",
                 schluessel: bytes | None = None) -> Lizenzstatus:
    """Prueft den geparsten Inhalt einer Lizenzdatei."""
    try:
        if not isinstance(daten, dict):
            return Lizenzstatus(UNGUELTIG, grund="kein Lizenzformat", pfad=pfad)
        fmt = daten.get("format")
        if isinstance(fmt, bool) or fmt != FORMAT:
            # Der Wert stammt aus einer ungeprueften Datei: gekuerzt anzeigen,
            # sonst sprengt ein langer Text Dialog, Log und Diagnosepaket.
            fmt = repr(fmt)
            fmt = fmt if len(fmt) <= 24 else fmt[:23] + "…"
            return Lizenzstatus(
                UNGUELTIG, pfad=pfad,
                grund=f"unbekanntes Lizenzformat {fmt} — diese Programmversion "
                      f"kennt Format {FORMAT}")
        name, kennung = daten.get("name"), daten.get("kennung")
        if not (isinstance(name, str) and name.strip()
                and isinstance(kennung, str) and kennung.strip()):
            return Lizenzstatus(UNGUELTIG, grund="Name oder Kennung fehlt", pfad=pfad)
        signatur = daten.get("signatur")
        if not isinstance(signatur, str):
            return Lizenzstatus(UNGUELTIG, grund="Signatur fehlt", pfad=pfad)
        try:
            sig = base64.b64decode(signatur.encode("ascii"), validate=True)
        except (ValueError, binascii.Error, UnicodeError):
            return Lizenzstatus(UNGUELTIG, grund="Signatur nicht lesbar", pfad=pfad)
        bis_roh = daten.get("gueltig_bis")
        try:
            bis = None if bis_roh is None else _datum(bis_roh)
        except ValueError:
            return Lizenzstatus(UNGUELTIG, grund="Ablaufdatum nicht lesbar", pfad=pfad)
        if not ed25519.pruefe(schluessel or OEFFENTLICHER_SCHLUESSEL,
                              kanonisch(daten), sig):
            return Lizenzstatus(UNGUELTIG, grund="Signatur passt nicht", pfad=pfad)
        name, kennung = name.strip(), kennung.strip()
        if bis is not None and (heute or _dt.date.today()) > bis:
            return Lizenzstatus(ABGELAUFEN, name=name, kennung=kennung,
                                gueltig_bis=bis, pfad=pfad,
                                grund=f"abgelaufen am {_datum_text(bis)}")
        return Lizenzstatus(GUELTIG, name=name, kennung=kennung,
                            gueltig_bis=bis, pfad=pfad)
    except Exception as e:                          # noqa: BLE001
        return Lizenzstatus(UNGUELTIG, pfad=pfad,
                            grund=f"nicht pruefbar ({type(e).__name__})")


def pruefe_datei(pfad, heute: _dt.date | None = None) -> Lizenzstatus:
    """Liest und prueft EINE Datei. Gibt es sie nicht: ``fehlt``."""
    try:
        pfad = os.fspath(pfad)
        if not os.path.isfile(pfad):
            return Lizenzstatus(FEHLT, pfad=pfad)
        if os.path.getsize(pfad) > _MAX_BYTES:
            return Lizenzstatus(UNGUELTIG, grund="keine Lizenzdatei (zu gross)",
                                pfad=pfad)
        with open(pfad, "rb") as fh:
            roh = fh.read(_MAX_BYTES + 1)
        try:
            daten = json.loads(roh.decode("utf-8-sig"))
        except (ValueError, UnicodeError):
            return Lizenzstatus(UNGUELTIG, grund="Datei beschädigt oder keine "
                                "Lizenzdatei", pfad=pfad)
        return pruefe_daten(daten, heute, pfad)
    except Exception as e:                          # noqa: BLE001
        return Lizenzstatus(UNGUELTIG, pfad=str(pfad),
                            grund=f"nicht lesbar ({type(e).__name__})")


def standard_pfad() -> str:
    """Wo die Lizenzdatei im App-Datenordner liegt."""
    return os.path.join(app_data_dir(), DATEINAME)


def suchorte(env=None) -> list[str]:
    """Kandidaten in der Reihenfolge, in der sie geprueft werden."""
    env = os.environ if env is None else env
    orte: list[str] = []
    ausdruecklich = (env.get(ENV_PFAD) or "").strip()
    if ausdruecklich:
        orte.append(os.path.expanduser(ausdruecklich))
    orte.append(standard_pfad())
    return orte


_RANG = {ABGELAUFEN: 2, UNGUELTIG: 1, FEHLT: 0}


def pruefe(heute: _dt.date | None = None, env=None) -> Lizenzstatus:
    """Der Lizenzstatus dieser Installation: die erste gueltige Datei der
    :func:`suchorte` — sonst der aussagekraeftigste Befund (abgelaufen vor
    ungueltig vor fehlt)."""
    bester = Lizenzstatus(FEHLT)
    try:
        for pfad in suchorte(env):
            status = pruefe_datei(pfad, heute)
            if status.ist_gueltig:
                return status
            if _RANG.get(status.zustand, 0) > _RANG.get(bester.zustand, 0):
                bester = status
    except Exception as e:                          # noqa: BLE001
        return Lizenzstatus(UNGUELTIG, grund=f"nicht pruefbar ({type(e).__name__})")
    return bester


def installiere(quelle, heute: _dt.date | None = None
                ) -> tuple[Lizenzstatus, str]:
    """Prueft ``quelle`` und legt sie — nur wenn gueltig — als
    ``lightos-lizenz.lic`` in den App-Datenordner.

    Rueckgabe ``(status, fehler)``: ``fehler`` ist leer, wenn die Datei gueltig
    ist UND abgelegt wurde. Eine ungueltige/abgelaufene Datei wird nie kopiert;
    eine vorhandene Lizenz bleibt dann, wie sie ist."""
    status = pruefe_datei(quelle, heute)
    if not status.ist_gueltig:
        return status, status.text()
    ziel = standard_pfad()
    try:
        quelle = os.fspath(quelle)
        if os.path.exists(ziel) and os.path.samefile(quelle, ziel):
            return status, ""
        with open(quelle, "rb") as fh:
            inhalt = fh.read(_MAX_BYTES + 1)
        os.makedirs(os.path.dirname(ziel), exist_ok=True)
        tmp = ziel + ".tmp"
        with open(tmp, "wb") as fh:
            fh.write(inhalt)
        os.replace(tmp, ziel)
    except Exception as e:                          # noqa: BLE001
        return status, (f"Die Lizenzdatei ist gültig, ließ sich aber nicht in den "
                        f"Datenordner kopieren ({type(e).__name__}: {e}).")
    return pruefe_datei(ziel, heute), ""


# ── Wann fragt der Start? (reine Funktionen, ohne Qt) ────────────────────────

def testlauf(env=None, module=None, gepackt: bool | None = None) -> bool:
    """True, wenn die Testsuite die Abfrage ausdruecklich abgeschaltet hat.

    Der Schalter ``LIGHTOS_LIZENZ_TESTLAUF=1`` wirkt NUR unter pytest: entweder
    laeuft pytest in diesem Prozess, oder der Prozess wurde von einem Test
    gestartet (pytest setzt ``PYTEST_CURRENT_TEST`` und vererbt es). Ausserhalb
    davon ist er wirkungslos.

    Codex-Review #1076: beide Angaben stammen nur aus der Umgebung — zwei
    gesetzte Variablen umgingen so die Lizenzabfrage auch beim gepackten
    Programm. Im gepackten Programm (``sys.frozen``, PyInstaller) gibt es keine
    Testsuite; dort wirkt der Schalter deshalb nie. Wer aus dem Quelltext
    startet, kann den Code ohnehin aendern — dort bleibt es beim Schalter."""
    env = os.environ if env is None else env
    module = sys.modules if module is None else module
    if gepackt is None:
        gepackt = bool(getattr(sys, "frozen", False))
    if gepackt:
        return False
    if env.get(ENV_TESTLAUF) != "1":
        return False
    return "PYTEST_CURRENT_TEST" in env or "pytest" in module


def abfrage_noetig(status: Lizenzstatus, *, selbsttest: bool = False,
                   diagnose: bool = False, env=None, module=None,
                   gepackt: bool | None = None) -> bool:
    """Muss der GUI-Start nach einer Lizenzdatei fragen?

    Nie bei ``--selbsttest`` und ``--diagnose`` (beide oeffnen kein Fenster),
    nie im Testlauf (:func:`testlauf`), nie mit gueltiger Lizenz. ``--kiosk``
    und ``--touch`` aendern daran nichts."""
    if selbsttest or diagnose:
        return False
    if testlauf(env, module, gepackt):
        return False
    return not status.ist_gueltig


def start_zeile(status: Lizenzstatus) -> str:
    """Die eine Zeile fuers Programm-Log beim Start (ohne Namen)."""
    return (f"[lizenz] {PROGRAMM} — {COPYRIGHT} | {QUELLE} | "
            f"Lizenz: {status.log_text()}")


def ablauf_hinweis(status: Lizenzstatus, heute: _dt.date | None = None) -> str:
    """Dezenter Hinweis ab :data:`VORWARN_TAGE` Tagen vor dem Ablauf, sonst ''."""
    if not status.laeuft_bald_ab(heute):
        return ""
    return (f"Testlizenz läuft am {_datum_text(status.gueltig_bis)} ab. Eine "
            f"Verlängerung gibt es beim Urheber ({QUELLE}).")


def lizenztext_pfad() -> str:
    """Die mitgelieferte ``LICENSE`` (Quellbetrieb: Repo-Wurzel; Setup-Build:
    neben den Programmdateien)."""
    from src.core.paths import programm_datei
    return programm_datei("LICENSE")


def lizenztext() -> str:
    try:
        with open(lizenztext_pfad(), encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return (f"{COPYRIGHT}.\n\nDer vollständige Lizenztext steht in der Datei "
                f"LICENSE unter {QUELLE}.")


# ── Ausstellen (nur mit dem privaten Schluessel des Urhebers moeglich) ───────

def neue_kennung() -> str:
    return "".join(secrets.choice(_KENNUNG_ZEICHEN) for _ in range(_KENNUNG_LAENGE))


def stelle_aus(geheim: bytes, name: str, gueltig_bis: _dt.date | None,
               hinweis: str = "", kennung: str | None = None,
               ausgestellt_am: _dt.date | None = None) -> dict:
    """Baut und signiert eine Lizenz (Format 1). Ohne den zum
    :data:`OEFFENTLICHER_SCHLUESSEL` passenden privaten Schluessel entsteht eine
    Datei, die das Programm als ungueltig abweist."""
    werte = {
        "format": FORMAT,
        "kennung": kennung or neue_kennung(),
        "name": str(name).strip(),
        "gueltig_bis": gueltig_bis.isoformat() if gueltig_bis else None,
        "ausgestellt_am": (ausgestellt_am or _dt.date.today()).isoformat(),
        "hinweis": str(hinweis or ""),
    }
    daten = {feld: werte[feld] for feld in _FELDER}
    if not daten["name"]:
        raise ValueError("Lizenz ohne Namen")
    sig = ed25519.signiere(geheim, kanonisch(daten))
    daten["signatur"] = base64.b64encode(sig).decode("ascii")
    return daten


def als_text(daten: dict) -> str:
    """Inhalt der Lizenzdatei (JSON, UTF-8, lesbar eingerueckt)."""
    return json.dumps(daten, indent=2, ensure_ascii=False) + "\n"
