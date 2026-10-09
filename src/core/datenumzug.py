"""XPLAT-44: einmalige Uebernahme alter ``data/``-Nutzerdaten in den App-Datenordner.

Bis XPLAT-44 lagen fuenf Nutzerdateien (``paths.USER_DATA_FILES``) relativ zum
ARBEITSVERZEICHNIS unter ``data/``. Seitdem liegen sie in ``app_data_dir()``.
Damit ein Update nichts "verliert", uebernimmt ``main.py`` beim Start einmalig,
was am alten Ort liegt.

Regeln (bewusst konservativ — es geht um die Daten eines laufenden Betriebs):

* **Nur KOPIEREN.** Der alte Stand wird nie verschoben, geloescht oder
  veraendert; er bleibt als Rueckfall liegen.
* **Nie ueberschreiben.** Liegt die Datei im App-Ordner schon MIT INHALT,
  gewinnt sie; der alte Stand bleibt unangetastet (Konflikt). Ein Konflikt
  gilt erst als erledigt, wenn ``main.py`` ihn dem Nutzer SICHTBAR gemeldet hat
  (``quittiere_konflikte``) — ein Werkzeug ohne Fenster erledigt ihn nie.
* **Frisch angelegte, leere Ziele zaehlen nicht.** Startete LightOS (oder ein
  Werkzeug ueber ``get_state()``) einmal ohne Uebernahme, liegt im App-Ordner
  eine LEERE Show-DB (kein Patch, keine Gruppen) bzw. ein JSON ``[]``/``{}``.
  Das ist kein Nutzerstand: es wird nach ``<name>.vor-xplat44`` gesichert und
  der alte Stand kopiert. Ebenso verwaiste SQLite-Nebendateien ohne Hauptdatei.
  Das gilt nur, solange die Datei NOCH NIE uebernommen wurde (``kopiert`` im
  Marker): eine einmal uebernommene und dann bewusst geleerte Show ist ein
  Nutzerstand, ein weiterer alter Ordner meldet dann einen Konflikt.
* **Konflikt aufloesen** (``alten_stand_uebernehmen``): auf Wunsch aus dem
  Dialog wird das Ziel samt ``-wal``/``-shm``/``-journal`` gesichert und der
  alte Stand samt Begleitdateien kopiert — nie nur die Hauptdatei (die echte
  Show steckt oft noch in der ``-wal``).
* **Sperre:** ``uebernehme_alte_daten``, ``quittiere_konflikte`` und
  ``alten_stand_uebernehmen`` laufen unter einer Dateisperre im App-Ordner
  (``datenumzug_xplat44.lock``); zwei gleichzeitig startende Prozesse
  (App + Werkzeug) kopieren also nicht ineinander, und der Marker wird unter
  der Sperre neu gelesen (kein verlorenes Update). Temp-Dateien bekommen
  eindeutige Namen.
* **Override-Variablen** (``LIGHTOS_SHOW_DB``, ``LIGHTOS_UNIVERSES_JSON``):
  ist eine gesetzt, wird die Datei NICHT in den (dann ungelesenen) App-Ordner
  kopiert; die Quelle bleibt fuer einen Start ohne Override offen.
* **Zentral:** ``get_state()`` ruft ``einmal_je_prozess()`` VOR dem ersten
  Oeffnen der Show-DB — auch Werkzeuge/Beispiele uebernehmen also zuerst.
* **Quellen:** ``<Repo/Programmordner>/data`` zuerst (dorthin schrieben die
  Startskripte, die vorher in den Programmordner wechselten), danach
  ``<CWD>/data``. Gleiche Ordner werden nur einmal betrachtet. Ein Ordner, der
  eine Git-Worktree-KOPIE ist (``.git`` ist dort eine Datei), ist nie Quelle:
  sein ``data/`` ist ein Entwicklungs-/Testabzug, kein Betriebsstand.
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
import filecmp
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Callable, Iterable

from .paths import USER_DATA_FILES, app_data_dir, programm_dir

MARKER_NAME = "datenumzug_xplat44.json"
#: Sperrdatei im App-Ordner (zwischen Prozessen, s. ``_sperre``).
SPERRE_NAME = "datenumzug_xplat44.lock"
#: Wie lange auf die Sperre eines anderen Prozesses gewartet wird.
SPERRE_TIMEOUT = 300.0
#: Abschalter fuer Werkzeuge/Sandkaesten, die NIE echte Daten lesen sollen.
ENV_AUS = "LIGHTOS_NO_DATENUMZUG"
#: SQLite-Nebendateien, die mit der DB wandern (``-shm`` s. Modul-Doku).
SQLITE_BEGLEITER = ("-wal", "-journal")
_SQLITE_ENDUNGEN = (".db", ".sqlite", ".sqlite3")
#: Endung der Sicherung eines ersetzten frischen/leeren Ziels.
SICHERUNG = ".vor-xplat44"
#: Tabellen, die eine Show-DB zu einem NUTZERSTAND machen. Eine frisch von
#: ``AppState.open_show`` angelegte DB hat hier (und ueberall) 0 Zeilen.
_SHOW_INHALT_TABELLEN = ("patched_fixtures", "fixture_groups",
                         "quarantined_fixtures")

# XPLAT-47: im gefrorenen Build der Programmordner (sys._MEIPASS) — dort liegt
# nur mitgelieferte Ware, kein altes ``data/`` mit Nutzerdateien; gelesen wird
# ohnehin nur (kopiert in den App-Datenordner, nie zurueck).
_REPO_ROOT = programm_dir()


@dataclass
class Ergebnis:
    kopiert: list = field(default_factory=list)      # [(name, quelle_pfad)]
    konflikte: list = field(default_factory=list)    # [(name, quelle_pfad)]
    offen: list = field(default_factory=list)        # [(name, quelle_pfad, grund)]
    quellen: list = field(default_factory=list)      # betrachtete Quellordner
    uebersprungen: str = ""                          # Grund, wenn gar nichts lief
    ersetzt: list = field(default_factory=list)      # [(name, sicherung)] leere Ziele
    ziel_dir: str = ""
    namen: list = field(default_factory=list)

    def show_db_in_benutzung(self) -> bool:
        """Die Show-DB konnte wegen einer offenen Verbindung nicht uebernommen
        werden — legte die App jetzt eine neue an, fehlte die Show."""
        return any(n == "current_show.db" and g == "in Benutzung"
                   for n, _q, g in self.offen)

    def show_db_offen(self) -> list[tuple[str, str]]:
        """``[(quelle, grund)]`` fuer jede NICHT uebernommene Show-DB — egal
        warum (in Benutzung, Platte voll, Rechte, Ziel geoeffnet). Ein
        gesetzter Override (``LIGHTOS_SHOW_DB``) ist Absicht und fehlt hier."""
        var = USER_DATA_FILES.get("current_show.db") or ""
        return [(q, g) for n, q, g in self.offen
                if n == "current_show.db" and not (var and g == f"{var} gesetzt")]


def _schluessel(pfad: str) -> str:
    """Vergleichsschluessel fuer Ordner: absolut, aufgeloest, auf Windows ohne
    Gross/Klein-Unterschied (``C:\\LightOS\\data`` == ``c:\\lightos\\DATA``)."""
    try:
        p = os.path.realpath(pfad)
    except (OSError, ValueError):
        p = os.path.abspath(pfad)
    return os.path.normcase(p)


def _ist_worktree_kopie(ordner: str) -> bool:
    """``ordner`` ist ein zusaetzlicher Git-Worktree: dort ist ``.git`` eine
    DATEI (Verweis auf das Haupt-Repo), kein Ordner. Dessen ``data/`` ist ein
    Entwicklungs-/Testabzug und darf den Betriebsstand nie fuellen."""
    try:
        return os.path.isfile(os.path.join(ordner, ".git"))
    except (OSError, ValueError):
        return False


def alte_quellen(cwd: str | None = None, repo_root: str | None = None) -> list[str]:
    """Die alten ``data/``-Ordner in Prioritaetsreihenfolge, ohne Dubletten
    und ohne Git-Worktree-Kopien (``_ist_worktree_kopie``)."""
    if cwd is None:
        try:
            cwd = os.getcwd()
        except OSError:          # CWD geloescht/unlesbar -> nur der Programmordner
            cwd = None
    kandidaten = []
    for basis in (repo_root or _REPO_ROOT, cwd):
        if basis and not _ist_worktree_kopie(basis):
            kandidaten.append(os.path.join(basis, "data"))
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


_LOCK_FELD = re.compile(r"^([0-9a-fA-F]+):([0-9a-fA-F]+):(\d+)$")


def _linux_gesperrte_dateien(quelle: str = "/proc/locks") -> set[tuple[int, int, int]]:
    """``(major, minor, inode)`` jeder Datei mit aktiver Sperre laut
    ``/proc/locks`` (SQLite sperrt per POSIX-Lock). Der Kernel schreibt das
    Geraet hexadezimal, den Inode dezimal."""
    aus: set[tuple[int, int, int]] = set()
    with open(quelle, encoding="ascii", errors="replace") as f:
        for zeile in f:
            for teil in zeile.split():
                m = _LOCK_FELD.match(teil)
                if m:
                    aus.add((int(m.group(1), 16), int(m.group(2), 16),
                             int(m.group(3))))
                    break
    return aus


def _lock_trifft(st_dev: int, st_ino: int,
                 gesperrt: set[tuple[int, int, int]]) -> bool:
    """Gleicht Geraet UND Inode ab. Nur wenn das Geraet der Datei in
    ``/proc/locks`` gar nicht vorkommt (btrfs-Subvolumes, overlayfs: dort
    zaehlt der Kernel das Geraet anders als ``stat``), reicht der Inode —
    ein seltener Fehlalarm verschiebt die Uebernahme nur auf den naechsten
    Start, ein uebersehener Lock kopierte eine halbe DB."""
    geraet = (os.major(st_dev), os.minor(st_dev))
    if (*geraet, st_ino) in gesperrt:
        return True
    if any((ma, mi) == geraet for ma, mi, _ in gesperrt):
        return False            # Geraetezaehlung passt -> kein Inode-Rueckfall
    return any(ino == st_ino for _ma, _mi, ino in gesperrt)


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
        gesperrt = _linux_gesperrte_dateien()
        for p in dateien:
            try:
                st = os.stat(p)
                if _lock_trifft(st.st_dev, st.st_ino, gesperrt):
                    return True
            except OSError:
                continue
    return False


# ── Sperre zwischen Prozessen ─────────────────────────────────────────────────

def _sperre_nehmen(fd: int) -> bool:
    """Ein Versuch, ``fd`` exklusiv zu sperren (nicht blockierend)."""
    try:
        if os.name == "nt":
            import msvcrt
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _sperre_freigeben(fd: int) -> None:
    try:
        if os.name == "nt":
            import msvcrt
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass


@contextmanager
def _sperre(ziel_dir: str, timeout: float | None = None):
    """Exklusive Dateisperre ``SPERRE_NAME`` im App-Ordner, plattformneutral
    (``fcntl.flock`` bzw. ``msvcrt.locking``). Wartet hoechstens ``timeout``
    Sekunden auf einen anderen Prozess, dann ``TimeoutError`` (der Start
    bricht daran nicht ab, s. ``einmal_je_prozess``)."""
    timeout = SPERRE_TIMEOUT if timeout is None else timeout
    try:
        fd = os.open(os.path.join(ziel_dir, SPERRE_NAME),
                     os.O_RDWR | os.O_CREAT, 0o644)
    except OSError:
        # Sperrdatei nicht anlegbar (Schreibschutz): dann kann auch niemand
        # sonst dort kopieren — ohne Sperre weiter; jede Datei scheitert
        # einzeln, wird gemeldet und beim naechsten Start wiederholt.
        yield
        return
    try:
        ende = time.monotonic() + timeout
        while not _sperre_nehmen(fd):
            if time.monotonic() >= ende:
                raise TimeoutError(f"Sperre {SPERRE_NAME} in {ziel_dir!r} belegt")
            time.sleep(0.05)
        try:
            yield
        finally:
            _sperre_freigeben(fd)
    finally:
        os.close(fd)


def _eindeutige_tmp(ziel: str) -> str:
    """Freier, eindeutiger Temp-Name neben ``ziel`` (gleiches Dateisystem ->
    ``os.replace`` bleibt atomar)."""
    fd, tmp = tempfile.mkstemp(prefix=os.path.basename(ziel) + ".",
                               suffix=".xplat44-tmp",
                               dir=os.path.dirname(ziel) or ".")
    os.close(fd)
    return tmp


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
    umbenannt: list[str] = []
    try:
        for quelle, ziel in paare:
            tmp = _eindeutige_tmp(ziel)
            temps.append((tmp, ziel))
            shutil.copy2(quelle, tmp)
        for tmp, ziel in temps:
            if os.path.exists(ziel):
                raise FileExistsError(ziel)
            os.replace(tmp, ziel)
            umbenannt.append(ziel)
    except BaseException:
        # Rollback: schon umbenannte Begleiter (-wal) DIESES Laufs wieder weg —
        # sonst laege eine verwaiste -wal ohne Hauptdatei am Ziel.
        for ziel in umbenannt:
            try:
                os.remove(ziel)
            except OSError:
                pass
        raise
    finally:
        for tmp, _ in temps:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass


def _ziel_ist_leer(neu: str, sqlite: bool) -> bool:
    """True, wenn am Ziel KEIN Nutzerstand liegt: fehlende Hauptdatei (nur
    verwaiste Nebendateien), eine Show-DB ohne Patch/Gruppen/Quarantaene oder
    ein JSON ``[]``/``{}``/``null``/leer. Im Zweifel (unlesbar, kaputt) False —
    dann bleibt es beim Konflikt, ersetzt wird nichts."""
    if not os.path.exists(neu):
        return True
    try:
        if sqlite:
            # Auf einer KOPIE pruefen: so faellt keine Recovery/Checkpoint am
            # Ziel an, und eine -wal ohne -shm stoert nicht (read-only-Oeffnen
            # scheitert daran je nach SQLite-Version).
            with tempfile.TemporaryDirectory(prefix="xplat44_pruef_") as td:
                kopie = os.path.join(td, "pruef.db")
                shutil.copy2(neu, kopie)
                for b in SQLITE_BEGLEITER:
                    if os.path.isfile(neu + b):
                        shutil.copy2(neu + b, kopie + b)
                return _db_ohne_show_inhalt(kopie)
        with open(neu, encoding="utf-8") as f:
            text = f.read()
        if not text.strip():
            return True
        return json.loads(text) in ([], {}, None)
    except Exception as e:
        # STAB-30: zaehlt dann als Konflikt — den Grund sichtbar machen.
        from src.core.diagnose_log import melde_still
        melde_still("datenumzug.ziel_pruefen", e, text=os.path.basename(neu))
        return False


def _db_ohne_show_inhalt(db: str) -> bool:
    con = sqlite3.connect(db, timeout=1.0)
    try:
        tabellen = {t for (t,) in con.execute(
            "select name from sqlite_master where type='table'")}
        for t in _SHOW_INHALT_TABELLEN:
            if t in tabellen and con.execute(
                    f'select 1 from "{t}" limit 1').fetchone():
                return False
        return True
    finally:
        con.close()


def _gleicher_stand(alt: str, neu: str, begleiter: tuple) -> bool:
    """Ziel ist byte-gleich mit der Quelle (samt -wal/-journal) — etwa nach
    einem Lauf mit verlorenem Marker. Dann nichts tun, auch nichts sichern.
    JSON (ohne Begleiter) gilt auch bei anderem Leerraum als gleich
    (``"[]\\n"`` == ``"[]"``)."""
    if not begleiter and _gleiches_json(alt, neu):
        return True
    try:
        for b in ("",) + tuple(begleiter):
            a, z = os.path.isfile(alt + b), os.path.isfile(neu + b)
            if a != z or (a and not filecmp.cmp(alt + b, neu + b, shallow=False)):
                return False
        return True
    except OSError:
        return False


def _gleiches_json(alt: str, neu: str) -> bool:
    """Beide Dateien sind JSON mit gleichem Inhalt — Leerraum zaehlt nicht."""
    try:
        with open(alt, encoding="utf-8") as f:
            a = f.read()
        with open(neu, encoding="utf-8") as f:
            z = f.read()
    except (OSError, ValueError):
        return False
    if "".join(a.split()) == "".join(z.split()):
        return True
    try:
        return json.loads(a) == json.loads(z)
    except ValueError:
        return False


def _sichere_paare(pfade: list[str]) -> list[tuple[str, str]]:
    """Benennt die vorhandenen ``pfade`` nach ``<pfad>.vor-xplat44`` (bei
    Belegung ``.vor-xplat44.2`` …) um; liefert ``[(pfad, sicherung), …]``."""
    zusatz = SICHERUNG
    n = 1
    while any(os.path.exists(p + zusatz) for p in pfade):
        n += 1
        zusatz = f"{SICHERUNG}.{n}"
    aus = []
    for p in pfade:
        if os.path.exists(p):
            os.replace(p, p + zusatz)
            aus.append((p, p + zusatz))
    return aus


def _sichere(pfade: list[str]) -> str:
    """Wie ``_sichere_paare``; liefert die Sicherung der ersten Datei."""
    paare = _sichere_paare(pfade)
    return paare[0][1] if paare else ""


def _marker_lesen(pfad: str) -> dict:
    try:
        with open(pfad, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError) as e:
        if os.path.exists(pfad):   # STAB-30: kaputte Marke, nicht "gibt's nicht"
            from src.core.diagnose_log import melde_still
            melde_still("datenumzug.marke", e)
        return {}


def _marker_schreiben(marker_pfad: str, marker: dict, log: Callable[[str], None]) -> None:
    marker = dict(marker)
    marker["version"] = 1
    marker["zuletzt"] = datetime.datetime.now().isoformat(timespec="seconds")
    tmp = ""
    try:
        tmp = _eindeutige_tmp(marker_pfad)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(marker, f, indent=2, ensure_ascii=False)
        os.replace(tmp, marker_pfad)
    except OSError as e:
        if tmp and os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
        log(f"[datenumzug] Marker {marker_pfad!r} nicht schreibbar ({e}) — "
            "die Pruefung laeuft beim naechsten Start erneut (kopiert wird "
            "trotzdem nichts doppelt: vorhandene Dateien gewinnen)")


def _abschliessen(marker: dict, quellen_namen: dict[str, list[str]]) -> list[str]:
    """Traegt jeden Quellordner, dessen vorhandene Dateien ALLE erledigt sind,
    in ``quellen_erledigt`` ein (und raeumt seine Teil-Liste weg)."""
    erledigt = set(marker.get("quellen_erledigt") or [])
    teil = dict(marker.get("teil_erledigt") or {})
    fertig = []
    for q, vorhanden in quellen_namen.items():
        s = _schluessel(q)
        if set(vorhanden) <= set(teil.get(s) or []):
            erledigt.add(s)
            teil.pop(s, None)
            fertig.append(q)
    marker["quellen_erledigt"] = sorted(erledigt)
    marker["teil_erledigt"] = teil
    return fertig


def _teil_lesen(marker: dict) -> dict[str, list[str]]:
    return {k: list(v) for k, v in (marker.get("teil_erledigt") or {}).items()
            if isinstance(v, list)}


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
    erg.ziel_dir, erg.namen = ziel_dir, list(namen)
    quellen = list(quellen) if quellen is not None else alte_quellen()
    marker_pfad = os.path.join(ziel_dir, MARKER_NAME)

    # Schneller Weg ohne Sperre (und ohne den App-Ordner anzulegen): alles
    # erledigt. Unter der Sperre wird der Marker unten NEU gelesen.
    erledigt = set(_marker_lesen(marker_pfad).get("quellen_erledigt") or [])
    if not [q for q in quellen if _schluessel(q) not in erledigt]:
        erg.uebersprungen = "bereits erledigt"
        return erg

    try:
        os.makedirs(ziel_dir, exist_ok=True)
    except OSError as e:
        log(f"[datenumzug] App-Datenordner {ziel_dir!r} nicht anlegbar ({e}) — "
            "Uebernahme beim naechsten Start erneut")
        erg.uebersprungen = "App-Datenordner nicht anlegbar"
        return erg

    with _sperre(ziel_dir):
        _uebernehme_unter_sperre(erg, ziel_dir, quellen, namen, marker_pfad,
                                 log, in_benutzung)
    return erg


def _uebernehme_unter_sperre(erg: Ergebnis, ziel_dir: str, quellen: list[str],
                             namen: list[str], marker_pfad: str,
                             log: Callable[[str], None],
                             in_benutzung: Callable[[str], bool]) -> None:
    # Marker unter der Sperre lesen: ein zweiter Prozess, der eben fertig
    # wurde, ist damit sichtbar (kein doppeltes Kopieren, kein verlorenes Update).
    marker = _marker_lesen(marker_pfad)
    erledigt = set(marker.get("quellen_erledigt") or [])
    teil = _teil_lesen(marker)
    schon_kopiert = set(marker.get("kopiert") or [])

    offene_quellen = [q for q in quellen if _schluessel(q) not in erledigt]
    if not offene_quellen:
        erg.uebersprungen = "bereits erledigt"
        return

    vorhanden: dict[str, list[str]] = {}
    for q in offene_quellen:
        vorhanden[q] = [n for n in namen if os.path.isfile(os.path.join(q, n))]
    erg.quellen = list(offene_quellen)

    for q, dort in vorhanden.items():
        schon = teil.setdefault(_schluessel(q), [])
        for name in dort:
            if name in schon:
                continue
            alt = os.path.join(q, name)
            neu = os.path.join(ziel_dir, name)
            sqlite = _ist_sqlite(name)
            begleiter = SQLITE_BEGLEITER if sqlite else ()
            var = USER_DATA_FILES.get(name)
            if var and os.environ.get(var):
                # Die App liest gerade eine andere Datei — dorthin zu kopieren
                # waere fuer diesen Lauf wirkungslos und fuer einen spaeteren
                # ueberraschend. Offen lassen: ein Start ohne Override holt nach.
                erg.offen.append((name, alt, f"{var} gesetzt"))
                log(f"[datenumzug] {name}: {var} gesetzt — Uebernahme aus "
                    f"{alt!r} beim naechsten Start ohne Override")
                continue
            # Bei SQLite zaehlen auch verwaiste Nebendateien am Ziel als "schon
            # da": eine fremde -wal neben einer frisch kopierten DB spielte
            # SQLite beim Oeffnen in diese ein.
            am_ziel = [p for p in [neu] + [neu + b for b in begleiter + ("-shm",)
                                           if begleiter]
                       if os.path.exists(p)]
            try:
                if am_ziel:
                    if _gleicher_stand(alt, neu, begleiter):
                        schon.append(name)          # schon derselbe Stand
                        continue
                    # Leer ersetzen NUR, solange der Name nie uebernommen
                    # wurde: eine uebernommene und dann bewusst geleerte Show
                    # ist ein Nutzerstand, kein frisch angelegtes Ziel.
                    if name in schon_kopiert or not _ziel_ist_leer(neu, sqlite):
                        erg.konflikte.append((name, alt))
                        log(f"[datenumzug] {name}: im App-Ordner schon vorhanden — "
                            f"der bleibt gueltig; alter Stand {alt!r} unangetastet")
                        continue
                    if sqlite and in_benutzung(neu):
                        erg.offen.append((name, alt, "Ziel in Benutzung"))
                        log(f"[datenumzug] {name}: leere Ziel-DB ist geoeffnet — "
                            "Uebernahme beim naechsten Start")
                        continue
                if begleiter and in_benutzung(alt):
                    erg.offen.append((name, alt, "in Benutzung"))
                    log(f"[datenumzug] {name}: {alt!r} ist von einem anderen "
                        "Prozess geoeffnet — Uebernahme beim naechsten Start")
                    continue
                if am_ziel:
                    gesichert = _sichere(am_ziel)
                    erg.ersetzt.append((name, gesichert))
                    log(f"[datenumzug] {name}: frisches/leeres Ziel nach "
                        f"{gesichert!r} gesichert")
                paare = [(alt + b, neu + b) for b in begleiter
                         if os.path.isfile(alt + b)]
                paare.append((alt, neu))
                _kopiere_ohne_ueberschreiben(paare)
                erg.kopiert.append((name, alt))
                schon.append(name)
                log(f"[datenumzug] {name}: aus {alt!r} uebernommen (kopiert; "
                    "der alte Stand bleibt liegen)")
            except Exception as e:   # Rechte, gesperrt, Platte voll, …
                erg.offen.append((name, alt, str(e)))
                log(f"[datenumzug] {name}: Kopie aus {alt!r} fehlgeschlagen "
                    f"({e}) — beim naechsten Start erneut")

    marker["teil_erledigt"] = {k: v for k, v in teil.items() if v}
    marker["kopiert"] = sorted(schon_kopiert | {n for n, _ in erg.kopiert})
    _abschliessen(marker, vorhanden)
    _marker_schreiben(marker_pfad, marker, log)


def _quittiere_unter_sperre(ziel_dir: str, namen: list[str],
                            konflikte: list[tuple[str, str]],
                            log: Callable[[str], None],
                            kopiert: Iterable[str] = ()) -> None:
    marker_pfad = os.path.join(ziel_dir, MARKER_NAME)
    marker = _marker_lesen(marker_pfad)      # unter der Sperre NEU gelesen
    teil = _teil_lesen(marker)
    quellen_namen: dict[str, list[str]] = {}
    for name, alt in konflikte:
        q = os.path.dirname(alt)
        s = _schluessel(q)
        if name not in teil.setdefault(s, []):
            teil[s].append(name)
        quellen_namen[q] = [n for n in namen
                            if os.path.isfile(os.path.join(q, n))]
    marker["teil_erledigt"] = teil
    if kopiert:
        marker["kopiert"] = sorted({*(marker.get("kopiert") or []), *kopiert})
    _abschliessen(marker, quellen_namen)
    _marker_schreiben(marker_pfad, marker, log)


def quittiere_konflikte(erg: Ergebnis, log: Callable[[str], None] = print) -> None:
    """Nach der SICHTBAREN Meldung (Dialog in ``main.py``): die Konflikte aus
    ``erg`` gelten als entschieden (App-Ordner gewinnt), ihr Quellordner wird
    nicht mehr erneut gemeldet."""
    if not erg.konflikte or not erg.ziel_dir:
        return
    with _sperre(erg.ziel_dir):
        _quittiere_unter_sperre(erg.ziel_dir, erg.namen, erg.konflikte, log)


def alten_stand_uebernehmen(
    ziel_dir: str,
    name: str,
    alt: str,
    *,
    namen: Iterable[str] | None = None,
    log: Callable[[str], None] = print,
    in_benutzung: Callable[[str], bool] = sqlite_in_benutzung,
) -> list[tuple[str, str]]:
    """Konflikt zugunsten des ALTEN Stands aufloesen (Knopf im Dialog).

    Sichert das Ziel samt ``-wal``/``-shm``/``-journal`` nach
    ``<datei>.vor-xplat44`` und kopiert die Quelle samt ``-wal``/``-journal``
    (nie nur die Hauptdatei: die echte Show steckt oft noch in der ``-wal``).
    Scheitert das Kopieren, werden die Sicherungen zurueckbenannt.
    Liefert ``[(datei, sicherung), …]``; wirft bei jedem Fehler (Aufrufer
    zeigt dann die Anleitung zum Handkopieren)."""
    neu = os.path.join(ziel_dir, name)
    sqlite = _ist_sqlite(name)
    begleiter = SQLITE_BEGLEITER if sqlite else ()
    namen = list(namen) if namen is not None else list(USER_DATA_FILES)
    with _sperre(ziel_dir):
        if not os.path.isfile(alt):
            raise FileNotFoundError(alt)
        if sqlite and in_benutzung(alt):
            raise RuntimeError(f"{alt} ist von einem anderen Programm geoeffnet")
        if sqlite and in_benutzung(neu):
            raise RuntimeError(f"{neu} ist von einem anderen Programm geoeffnet")
        am_ziel = [neu + b for b in ("",) + (("-wal", "-shm", "-journal")
                                             if sqlite else ())]
        gesichert = _sichere_paare(am_ziel)
        paare = [(alt + b, neu + b) for b in begleiter if os.path.isfile(alt + b)]
        paare.append((alt, neu))
        try:
            _kopiere_ohne_ueberschreiben(paare)
        except BaseException:
            for orig, sich in gesichert:
                try:
                    if not os.path.exists(orig):
                        os.replace(sich, orig)
                except OSError as e:
                    # STAB-30: sonst liegt der Stand still unter der Sicherung —
                    # sieht aus wie Datenverlust.
                    from src.core.diagnose_log import melde_still
                    melde_still("datenumzug.rueckbau", e,
                                text=f"Sicherung {sich!r} nicht zurueckgelegt")
            raise
        log(f"[datenumzug] {name}: alter Stand {alt!r} auf Wunsch uebernommen; "
            f"bisheriger Stand gesichert: {[s for _o, s in gesichert]!r}")
        _quittiere_unter_sperre(ziel_dir, namen, [(name, alt)], log,
                                kopiert=[name])
    return gesichert


_PROZESS_ERGEBNIS: Ergebnis | None = None


def einmal_je_prozess(log: Callable[[str], None] = print) -> Ergebnis:
    """Die Uebernahme hoechstens EINMAL je Prozess — von ``main.py`` (frueh,
    mit Dialog) und von ``get_state()`` (vor dem ersten Oeffnen der Show-DB,
    damit auch Werkzeuge erst uebernehmen, bevor eine leere DB entsteht)."""
    global _PROZESS_ERGEBNIS
    if _PROZESS_ERGEBNIS is None:
        try:
            _PROZESS_ERGEBNIS = uebernehme_alte_daten(log=log)
        except Exception as e:     # der Start bricht daran nie ab
            log(f"[datenumzug] uebersprungen: {e}")
            _PROZESS_ERGEBNIS = Ergebnis(uebersprungen=f"Fehler: {e}")
    return _PROZESS_ERGEBNIS
