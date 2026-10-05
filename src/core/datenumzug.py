"""XPLAT-44: einmalige Uebernahme alter ``data/``-Nutzerdaten in den App-Datenordner.

Bis XPLAT-44 lagen fuenf Nutzerdateien (``paths.USER_DATA_FILES``) relativ zum
ARBEITSVERZEICHNIS unter ``data/``. Seitdem liegen sie in ``app_data_dir()``.
Damit ein Update nichts "verliert", uebernimmt ``main.py`` beim Start einmalig,
was am alten Ort liegt.

Regeln (bewusst konservativ — es geht um die Daten eines laufenden Betriebs):

* **Nur KOPIEREN.** Der alte Stand wird nie verschoben, geloescht oder
  veraendert; er bleibt als Rueckfall liegen.
* **Nie ueberschreiben.** Liegt die Datei im App-Ordner schon, gewinnt sie; der
  alte Stand bleibt unangetastet, ins Log kommt ein Hinweis (Konflikt).
* **Quellen:** ``<Repo/Programmordner>/data`` zuerst (dorthin schrieben die
  Startskripte, die vorher in den Programmordner wechselten), danach
  ``<CWD>/data``. Gleiche Ordner werden nur einmal betrachtet.
* **Einmal je Quellordner.** Die Marker-Datei ``datenumzug_xplat44.json`` im
  App-Ordner haelt fest, welche Quellordner erledigt sind. Ohne Marker kaeme
  eine bewusst im App-Ordner GELOESCHTE Datei (etwa "MIDI-Zuordnungen
  zuruecksetzen") beim naechsten Start aus dem alten ``data/`` zurueck.
  Pro Quellordner statt global, weil sonst ein erster Start aus einem anderen
  Ordner (leeres ``data/``) die echte Uebernahme fuer immer abschaltete.
* **Show-DB (SQLite):** nur, wenn keine andere Verbindung sie offen haelt;
  ``-wal``/``-journal`` werden mitgenommen (sonst fehlten die letzten
  Transaktionen bzw. ein Rollback). ``-shm`` bewusst NICHT: das ist ein reiner
  Index, den SQLite beim ersten Oeffnen neu aufbaut. Ist sie offen, bleibt der
  Quellordner "offen" und wird beim naechsten Start erneut versucht.
* **Robust:** jeder Fehler (fehlende Rechte, Sonderzeichen, Windows-Pfade)
  betrifft nur die eine Datei, wird geloggt und beim naechsten Start erneut
  versucht — der Programmstart bricht daran nie ab.

Importiert nur die Standardbibliothek + ``paths`` (kein Qt, kein App-State).
"""
from __future__ import annotations

import datetime
import json
import os
import re
import shutil
import sys
from dataclasses import dataclass, field
from typing import Callable, Iterable

from .paths import USER_DATA_FILES, app_data_dir

MARKER_NAME = "datenumzug_xplat44.json"
#: Abschalter fuer Werkzeuge/Sandkaesten, die NIE echte Daten lesen sollen.
ENV_AUS = "LIGHTOS_NO_DATENUMZUG"
#: SQLite-Nebendateien, die mit der DB wandern (``-shm`` s. Modul-Doku).
SQLITE_BEGLEITER = ("-wal", "-journal")
_SQLITE_ENDUNGEN = (".db", ".sqlite", ".sqlite3")

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@dataclass
class Ergebnis:
    kopiert: list = field(default_factory=list)      # [(name, quelle_pfad)]
    konflikte: list = field(default_factory=list)    # [(name, quelle_pfad)]
    offen: list = field(default_factory=list)        # [(name, quelle_pfad, grund)]
    quellen: list = field(default_factory=list)      # betrachtete Quellordner
    uebersprungen: str = ""                          # Grund, wenn gar nichts lief


def _schluessel(pfad: str) -> str:
    """Vergleichsschluessel fuer Ordner: absolut, aufgeloest, auf Windows ohne
    Gross/Klein-Unterschied (``C:\\LightOS\\data`` == ``c:\\lightos\\DATA``)."""
    try:
        p = os.path.realpath(pfad)
    except (OSError, ValueError):
        p = os.path.abspath(pfad)
    return os.path.normcase(p)


def alte_quellen(cwd: str | None = None, repo_root: str | None = None) -> list[str]:
    """Die alten ``data/``-Ordner in Prioritaetsreihenfolge, ohne Dubletten."""
    if cwd is None:
        try:
            cwd = os.getcwd()
        except OSError:          # CWD geloescht/unlesbar -> nur der Programmordner
            cwd = None
    kandidaten = [os.path.join(repo_root or _REPO_ROOT, "data")]
    if cwd:
        kandidaten.append(os.path.join(cwd, "data"))
    aus: list[str] = []
    gesehen: set[str] = set()
    for k in kandidaten:
        s = _schluessel(k)
        if s not in gesehen:
            gesehen.add(s)
            aus.append(k)
    return aus


# ── Ist die SQLite-Datei gerade offen? ─────────────────────────────────────────

def _windows_offen(pfad: str) -> bool:
    """Windows: eine Datei, die ein anderer Prozess offen haelt, laesst sich
    nicht EXKLUSIV (Share-Mode 0) oeffnen -> ERROR_SHARING_VIOLATION (32).
    Nur Lesezugriff, aendert nichts an der Datei."""
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateFileW.restype = wintypes.HANDLE
    k32.CreateFileW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
                                wintypes.HANDLE)
    GENERIC_READ, OPEN_EXISTING = 0x80000000, 3
    h = k32.CreateFileW(pfad, GENERIC_READ, 0, None, OPEN_EXISTING, 0, None)
    if h is None or h == wintypes.HANDLE(-1).value:
        return ctypes.get_last_error() == 32
    k32.CloseHandle(h)
    return False


_LOCK_FELD = re.compile(r"^[0-9a-fA-F]+:[0-9a-fA-F]+:(\d+)$")


def _linux_gesperrte_inodes(quelle: str = "/proc/locks") -> set[int]:
    """Inodes mit aktiver Dateisperre laut ``/proc/locks`` (SQLite sperrt per
    POSIX-Lock). Verglichen wird nur der Inode — das Geraet steht dort je nach
    Dateisystem (btrfs-Subvolumes) anders als in ``stat``; ein seltener
    Fehlalarm verschiebt die Uebernahme nur auf den naechsten Start."""
    inodes: set[int] = set()
    with open(quelle, encoding="ascii", errors="replace") as f:
        for zeile in f:
            for teil in zeile.split():
                m = _LOCK_FELD.match(teil)
                if m:
                    inodes.add(int(m.group(1)))
                    break
    return inodes


def sqlite_in_benutzung(db: str) -> bool:
    """True, wenn ein anderer Prozess die DB (oder ihre Nebendateien) offen haelt.

    Plattformen ohne Pruefmoeglichkeit liefern False — die Einzelinstanz-Sperre
    in ``main.py`` laeuft VOR der Uebernahme und schliesst ein zweites LightOS
    ohnehin aus; die Pruefung hier faengt Werkzeuge und Altversionen ab.
    """
    dateien = [p for p in (db, db + "-wal", db + "-shm", db + "-journal")
               if os.path.exists(p)]
    if not dateien:
        return False
    plat = sys.platform
    if plat == "win32":
        return any(_windows_offen(p) for p in dateien)
    if os.path.exists("/proc/locks"):
        gesperrt = _linux_gesperrte_inodes()
        for p in dateien:
            try:
                if os.stat(p).st_ino in gesperrt:
                    return True
            except OSError:
                continue
    return False


# ── Kopieren ──────────────────────────────────────────────────────────────────

def _ist_sqlite(name: str) -> bool:
    return name.lower().endswith(_SQLITE_ENDUNGEN)


def _kopiere_ohne_ueberschreiben(paare: list[tuple[str, str]]) -> None:
    """Kopiert ``[(quelle, ziel), …]`` erst in Temp-Namen und benennt dann um —
    die LETZTE Datei des Paars (die Hauptdatei) zuletzt. Ein Abbruch mittendrin
    hinterlaesst also nie eine halbe Hauptdatei am Zielnamen.

    Liegt ein Ziel inzwischen schon da, wird abgebrochen (``FileExistsError``),
    nicht ueberschrieben.
    """
    temps: list[tuple[str, str]] = []
    try:
        for quelle, ziel in paare:
            tmp = ziel + ".xplat44-tmp"
            shutil.copy2(quelle, tmp)
            temps.append((tmp, ziel))
        for tmp, ziel in temps:
            if os.path.exists(ziel):
                raise FileExistsError(ziel)
            os.replace(tmp, ziel)
    finally:
        for tmp, _ in temps:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass


def _marker_lesen(pfad: str) -> dict:
    try:
        with open(pfad, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def uebernehme_alte_daten(
    ziel_dir: str | None = None,
    quellen: Iterable[str] | None = None,
    *,
    dateien: Iterable[str] | None = None,
    log: Callable[[str], None] = print,
    in_benutzung: Callable[[str], bool] = sqlite_in_benutzung,
) -> Ergebnis:
    """Fuehrt die Uebernahme aus (s. Modul-Doku) und liefert, was geschah."""
    erg = Ergebnis()
    if os.environ.get(ENV_AUS):
        erg.uebersprungen = f"{ENV_AUS} gesetzt"
        return erg
    ziel_dir = ziel_dir or app_data_dir()
    namen = list(dateien) if dateien is not None else list(USER_DATA_FILES)
    quellen = list(quellen) if quellen is not None else alte_quellen()
    marker_pfad = os.path.join(ziel_dir, MARKER_NAME)
    marker = _marker_lesen(marker_pfad)
    erledigt = set(marker.get("quellen_erledigt") or [])

    offene_quellen = [q for q in quellen if _schluessel(q) not in erledigt]
    if not offene_quellen:
        erg.uebersprungen = "bereits erledigt"
        return erg

    # Quellordner ohne eine einzige bekannte Datei sind sofort erledigt — und
    # brauchen keinen App-Ordner (ein frischer Start legt ihn nicht deswegen an).
    mit_daten = []
    for q in offene_quellen:
        if any(os.path.isfile(os.path.join(q, n)) for n in namen):
            mit_daten.append(q)
    erg.quellen = list(offene_quellen)

    try:
        os.makedirs(ziel_dir, exist_ok=True)
    except OSError as e:
        log(f"[datenumzug] App-Datenordner {ziel_dir!r} nicht anlegbar ({e}) — "
            "Uebernahme beim naechsten Start erneut")
        erg.uebersprungen = "App-Datenordner nicht anlegbar"
        return erg

    fertig: list[str] = [q for q in offene_quellen if q not in mit_daten]
    for q in mit_daten:
        quelle_offen = False
        for name in namen:
            alt = os.path.join(q, name)
            if not os.path.isfile(alt):
                continue
            neu = os.path.join(ziel_dir, name)
            begleiter = SQLITE_BEGLEITER if _ist_sqlite(name) else ()
            # Bei SQLite zaehlen auch verwaiste Nebendateien am Ziel als "schon
            # da": eine fremde -wal neben einer frisch kopierten DB spielte
            # SQLite beim Oeffnen in diese ein.
            pruefen = [neu] + [neu + b for b in begleiter + ("-shm",)
                               if begleiter]
            schon_da = any(os.path.exists(p) for p in pruefen)
            if schon_da:
                erg.konflikte.append((name, alt))
                log(f"[datenumzug] {name}: im App-Ordner schon vorhanden — der "
                    f"bleibt gueltig; alter Stand {alt!r} unangetastet")
                continue
            try:
                if begleiter and in_benutzung(alt):
                    quelle_offen = True
                    erg.offen.append((name, alt, "in Benutzung"))
                    log(f"[datenumzug] {name}: {alt!r} ist von einem anderen "
                        "Prozess geoeffnet — Uebernahme beim naechsten Start")
                    continue
                paare = [(alt + b, neu + b) for b in begleiter
                         if os.path.isfile(alt + b)]
                paare.append((alt, neu))
                _kopiere_ohne_ueberschreiben(paare)
                erg.kopiert.append((name, alt))
                log(f"[datenumzug] {name}: aus {alt!r} uebernommen (kopiert; "
                    "der alte Stand bleibt liegen)")
            except Exception as e:   # Rechte, gesperrt, Platte voll, …
                quelle_offen = True
                erg.offen.append((name, alt, str(e)))
                log(f"[datenumzug] {name}: Kopie aus {alt!r} fehlgeschlagen "
                    f"({e}) — beim naechsten Start erneut")
        if not quelle_offen:
            fertig.append(q)

    if fertig:
        neu_marker = {
            "version": 1,
            "quellen_erledigt": sorted(erledigt | {_schluessel(q) for q in fertig}),
            "zuletzt": datetime.datetime.now().isoformat(timespec="seconds"),
            "kopiert": sorted({*marker.get("kopiert", []),
                               *(n for n, _ in erg.kopiert)}),
        }
        try:
            tmp = marker_pfad + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(neu_marker, f, indent=2, ensure_ascii=False)
            os.replace(tmp, marker_pfad)
        except OSError as e:
            log(f"[datenumzug] Marker {marker_pfad!r} nicht schreibbar ({e}) — "
                "die Pruefung laeuft beim naechsten Start erneut (kopiert wird "
                "trotzdem nichts doppelt: vorhandene Dateien gewinnen)")
    return erg
