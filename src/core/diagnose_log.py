"""STAB-30: Sitzungs-Log und Diagnosepaket fuer Fernhilfe.

Wenn LightOS auf einem fremden Rechner nicht tut, was es soll, soll der Tester
EINE Datei schicken koennen, aus der hervorgeht, was im Hintergrund passiert ist
— auch das, was bisher still scheiterte. Dieses Modul buendelt dafuer:

* **Sitzungs-Log** ``<App-Daten>/logs/lightos.log``: ``stdout``/``stderr`` werden
  zusaetzlich (Tee) in die Datei geschrieben — mit Zeitstempel je Zeile, thread-
  sicher, begrenzt (5 MB je Datei, die letzten Sitzungen bleiben als ``.1`` …
  ``.5`` liegen). Das Terminal sieht unveraendert dasselbe wie bisher. Damit
  landen die ``print("[modul] …")``-Zeilen, Python-``logging``, die Qt-Meldungen
  (der Qt-Handler in ``main.py`` schreibt nach ``stderr``) und die JS-Konsole
  des Visualizers (wird dort per ``print`` weitergereicht) in derselben Datei.
* **Kopfblock** je Sitzung: Version/Commit (im Setup-Build aus der eingebetteten
  ``build_info.json``, sonst aus ``.git``), gefroren ja/nein, Betriebssystem samt
  Architektur (Windows-ARM-Emulation erkennbar), Python, PySide6/Qt, Datenordner
  (Benutzerpfad anonymisiert). Was erst spaeter bekannt ist (Bildschirme, GPU-
  Stufe, DMX-Ausgaenge, MIDI, Show), meldet :func:`merke` als ``[diagnose]``-Zeile
  nach und haelt es fuer das Diagnosepaket fest.
* :func:`melde_still` — knappe, gedrosselte Logzeile fuer bisher stille
  ``except …: pass``-Stellen (je Fehlerart einmal, je Stelle hoechstens
  ``_STILL_MAX_JE_TAG`` verschiedene).
* :func:`erstelle_diagnosepaket` — zip mit Logs, ``crash.log``, Systeminfo und
  einer Einstellungsliste OHNE private Inhalte (keine Show-Dateien, keine
  Datenbanken, Benutzerpfade anonymisiert). In ``crash.log`` werden bekannte
  harmlose Windows-Meldungen (COM-Hinweise, STAB-33) als "kein Absturz"
  gekennzeichnet — echte Abstuerze bleiben unveraendert.

Grundregel wie bei ``crash_logging``: **Logging darf den Start nie verhindern und
nie blockieren.** Jeder Schreibfehler wird geschluckt; ist die Datei nicht
schreibbar, laeuft die App einfach ohne Sitzungs-Log weiter.

Importiert beim Laden nur die Standardbibliothek (PySide6 lazy und nur, wenn es
schon geladen ist) — damit ist es in ``main.py`` vor dem Qt-Import nutzbar.
"""
from __future__ import annotations

import datetime
import json
import os
import platform
import struct
import sys
import threading
import zipfile

from src.core import crash_logging as _cl
from src.core.paths import app_data_dir, crash_log_path

LOG_NAME = "lightos.log"
MAX_BYTES = 5 * 1024 * 1024        # je Logdatei
BACKUPS = 5                        # so viele vorige Sitzungen/Teile bleiben liegen
_PUFFER_MAX = 512 * 1024           # Startpuffer, bevor die Datei offen ist
_LOCK_TIMEOUT = 0.25               # nie laenger auf das Log warten
_PAKET_MAX_JE_DATEI = 8 * 1024 * 1024
#: Was NIE ins Diagnosepaket darf (Shows, Datenbanken samt Begleitdateien).
_VERBOTENE_ENDUNGEN = (".lshow", ".db", ".db-wal", ".db-shm", ".db-journal",
                       ".sqlite", ".sqlite3")


# ── Pfade ────────────────────────────────────────────────────────────────────
def log_dir() -> str:
    """Ordner der Sitzungs-Logs. ``LIGHTOS_LOG_DIR`` biegt ihn um (Tests)."""
    override = os.environ.get("LIGHTOS_LOG_DIR")
    if override:
        return override
    return os.path.join(app_data_dir(), "logs")


def log_path() -> str:
    return os.path.join(log_dir(), LOG_NAME)


# ── Anonymisieren ────────────────────────────────────────────────────────────
def _benutzername() -> str:
    for var in ("USERNAME", "USER", "LOGNAME"):
        wert = os.environ.get(var)
        if wert:
            return wert
    try:
        return os.path.basename(os.path.expanduser("~"))
    except Exception:
        return ""


def anonymisiere(text: str, home: str | None = None,
                 user: str | None = None) -> str:
    """Ersetzt den Home-Pfad durch ``~`` und den Benutzernamen als Pfadteil durch
    ``%USERNAME%`` — in beiden Schreibweisen der Trenner, unter Windows ohne
    Ruecksicht auf Gross-/Kleinschreibung."""
    if not text:
        return text
    try:
        import re
        home = os.path.expanduser("~") if home is None else home
        user = _benutzername() if user is None else user
        flags = re.IGNORECASE if (sys.platform == "win32" or "\\" in (home or "")) else 0
        if home and len(home) > 3:
            for variante in {home, home.replace("\\", "/"), home.replace("/", "\\")}:
                text = re.sub(re.escape(variante.rstrip("/\\")), "~", text,
                              flags=flags)
        if user and len(user) >= 2:
            # nur als PFADTEIL ersetzen (…/name/… bzw. …\name\…) — ein kurzer
            # Name taucht sonst mitten in harmlosen Woertern auf.
            muster = r"(?<=[/\\])" + re.escape(user) + r"(?=[/\\]|$|\s|['\"])"
            text = re.sub(muster, "%USERNAME%", text, flags=flags)
    except Exception:
        pass
    return text


# ── Log-Senke ────────────────────────────────────────────────────────────────
class LogSink:
    """Thread-sichere, begrenzte Logdatei. Vor :meth:`open` wird gepuffert (die
    Importe vor der Einzelinstanz-Sperre drucken schon), danach direkt
    geschrieben. Alle Fehler werden geschluckt; nach einem Schreibfehler bleibt
    die Senke still (``kaputt``), statt jede Zeile erneut scheitern zu lassen."""

    def __init__(self, max_bytes: int = MAX_BYTES, backups: int = BACKUPS,
                 puffer_max: int = _PUFFER_MAX):
        self.max_bytes = max_bytes
        self.backups = backups
        self.puffer_max = puffer_max
        self.path: str | None = None
        self.kaputt = False
        self._fh = None
        self._size = 0
        self._puffer: list[str] = []
        self._puffer_len = 0
        self._puffer_voll = False
        self._lock = threading.RLock()

    @property
    def offen(self) -> bool:
        return self._fh is not None

    def open(self, path: str, kopf: str = "") -> bool:
        """Rotiert die vorige Sitzung weg (``.1`` …), oeffnet ``path`` neu,
        schreibt ``kopf`` und den Startpuffer. False = kein Log (App laeuft)."""
        if not self._lock.acquire(timeout=_LOCK_TIMEOUT * 8):
            return False
        try:
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            # jede Sitzung beginnt in einer frischen Datei -> die vorigen
            # bleiben als .1 … .N lesbar getrennt (max_bytes=0 = "nicht leer").
            _cl.rotate_if_large(path, max_bytes=0, backups=self.backups)
            self._fh = open(path, "a", encoding="utf-8", errors="replace",
                            buffering=1)
            self.path = path
            self._size = 0
            if kopf:
                self._schreibe(kopf)
            if self._puffer:
                self._schreibe("".join(self._puffer))
                if self._puffer_voll:
                    self._schreibe("(… Startpuffer voll, fruehe Zeilen gekuerzt)\n")
            self._puffer = []
            self._puffer_len = 0
            return True
        except Exception:
            self._fh = None
            self.kaputt = True
            return False
        finally:
            self._lock.release()

    def _schreibe(self, text: str) -> None:
        fh = self._fh
        if fh is None:
            return
        fh.write(text)
        self._size += len(text)
        if self._size > self.max_bytes and self.path:
            try:
                fh.close()
            except Exception:
                pass
            self._fh = None
            _cl.rotate_if_large(self.path, max_bytes=0, backups=self.backups)
            self._fh = open(self.path, "a", encoding="utf-8", errors="replace",
                            buffering=1)
            self._size = 0
            self._fh.write(f"=== Fortsetzung {_cl._ts()} (Log rotiert, "
                           f"vorheriger Teil: {LOG_NAME}.1) ===\n")

    def write(self, text: str) -> None:
        if not text or self.kaputt:
            return
        # Nie blockieren: wer das Lock nicht schnell bekommt, verliert die Zeile.
        if not self._lock.acquire(timeout=_LOCK_TIMEOUT):
            return
        try:
            if self._fh is None:
                if self.path is None and not self._puffer_voll:
                    if self._puffer_len + len(text) > self.puffer_max:
                        self._puffer_voll = True
                    else:
                        self._puffer.append(text)
                        self._puffer_len += len(text)
                return
            self._schreibe(text)
        except Exception:
            self.kaputt = True
            try:
                if self._fh is not None:
                    self._fh.close()
            except Exception:
                pass
            self._fh = None
        finally:
            self._lock.release()

    def flush(self) -> None:
        try:
            if self._fh is not None:
                self._fh.flush()
        except Exception:
            pass

    def close(self) -> None:
        with self._lock:
            try:
                if self._fh is not None:
                    self._fh.close()
            except Exception:
                pass
            self._fh = None


class TeeStream:
    """Ersetzt ``sys.stdout``/``sys.stderr``: schreibt unveraendert in den
    Original-Stream (falls es einen gibt — unter ``pythonw`` ist er ``None``) und
    zusaetzlich mit Zeitstempel je Zeile in die :class:`LogSink`.

    ``kennung`` steht hinter dem Zeitstempel (`` `` = stdout, ``!`` = stderr);
    Zeilen aus Nebenthreads tragen den Threadnamen."""

    def __init__(self, original, sink: LogSink, kennung: str = " "):
        self._original = original
        self._sink = sink
        self._kennung = kennung
        self._zeilenanfang = True
        self._lock = threading.Lock()

    # -- Stream-Schnittstelle --
    def write(self, s) -> int:
        if not isinstance(s, str):
            try:
                s = str(s)
            except Exception:
                return 0
        orig = self._original
        if orig is not None:
            try:
                orig.write(s)
            except Exception:
                pass            # kaputte Konsole/Codierung darf nie werfen
        try:
            self._sink.write(self._mit_zeitstempel(s))
        except Exception:
            pass
        return len(s)

    def _mit_zeitstempel(self, s: str) -> str:
        if not s:
            return s
        jetzt = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        thread = threading.current_thread()
        faden = "" if thread is threading.main_thread() else f"<{thread.name}> "
        praefix = f"{jetzt} {self._kennung} {faden}"
        with self._lock:
            teile = s.split("\n")
            raus = []
            for i, teil in enumerate(teile):
                letzte = i == len(teile) - 1
                if letzte and teil == "":
                    break           # endete mit \n -> naechster Aufruf neue Zeile
                if self._zeilenanfang:
                    raus.append(praefix)
                raus.append(teil)
                if not letzte:
                    raus.append("\n")
                    self._zeilenanfang = True
                else:
                    self._zeilenanfang = False
            if s.endswith("\n"):
                self._zeilenanfang = True
            return "".join(raus)

    def writelines(self, zeilen) -> None:
        for z in zeilen:
            self.write(z)

    def flush(self) -> None:
        if self._original is not None:
            try:
                self._original.flush()
            except Exception:
                pass
        self._sink.flush()

    def isatty(self) -> bool:
        try:
            return bool(self._original is not None and self._original.isatty())
        except Exception:
            return False

    def fileno(self) -> int:
        if self._original is None:
            import io
            raise io.UnsupportedOperation("fileno")
        return self._original.fileno()

    @property
    def encoding(self) -> str:
        return getattr(self._original, "encoding", None) or "utf-8"

    @property
    def errors(self):
        return getattr(self._original, "errors", None) or "replace"

    def readable(self) -> bool:
        return False

    def writable(self) -> bool:
        return True

    @property
    def closed(self) -> bool:
        return False

    def __getattr__(self, name):
        # alles Uebrige (buffer, mode, reconfigure …) an das Original
        if self._original is None:
            raise AttributeError(name)
        return getattr(self._original, name)


# ── Prozessweiter Zustand ────────────────────────────────────────────────────
_sink: LogSink | None = None
_laufzeit: dict[str, str] = {}
_laufzeit_lock = threading.Lock()

#: Diese Aufrufe schreiben KEIN Sitzungs-Log (keine Nebenwirkungen bzw. kein
#: App-Lauf): Hilfe, Selbsttest des gepackten Builds, Diagnosepaket.
_OHNE_LOG = ("-h", "--help", "--selbsttest", "--diagnose")


def soll_mitschreiben(argv) -> bool:
    try:
        for a in argv or ():
            if a.split("=", 1)[0] in _OHNE_LOG:
                return False
        return os.environ.get("LIGHTOS_NO_SESSION_LOG", "").strip() not in (
            "1", "true", "yes", "on")
    except Exception:
        return False


def install_tee(sink: LogSink | None = None) -> LogSink | None:
    """Haengt stdout/stderr an die (zunaechst puffernde) Senke. Idempotent.
    Gibt die Senke zurueck — oder None, falls das Umhaengen scheiterte."""
    global _sink
    try:
        if _sink is not None:
            return _sink
        sink = sink or LogSink()
        sys.stdout = TeeStream(sys.stdout, sink, " ")
        sys.stderr = TeeStream(sys.stderr, sink, "!")
        _sink = sink
        return sink
    except Exception:
        return None


def oeffne_sitzungslog(app_version: str = "?", programm_dir: str | None = None,
                       path: str | None = None) -> str | None:
    """Oeffnet die Logdatei der installierten Senke und schreibt den Kopfblock.
    Erst NACH der Einzelinstanz-Sperre aufrufen — sonst rotierte ein abgewiesener
    Zweitstart der laufenden Instanz die Datei weg. Rueckgabe: Pfad oder None."""
    if _sink is None:
        return None
    try:
        p = path or log_path()
        kopf = kopfblock(app_version, programm_dir)
        if not _sink.open(p, kopf):
            return None
        os.environ[_ENV_LOGPFAD] = p      # fuer den DMX-Worker-Prozess
        return p
    except Exception:
        return None


def richte_python_logging_ein() -> None:
    """Python-``logging`` (Bibliotheken) und ``warnings`` auf stderr — und damit
    ins Sitzungs-Log. Nur, wenn noch niemand einen Handler gesetzt hat."""
    try:
        import logging
        root = logging.getLogger()
        if not root.handlers:
            h = logging.StreamHandler(sys.stderr)
            h.setFormatter(logging.Formatter("[%(name)s] %(levelname)s: %(message)s"))
            root.addHandler(h)
            debug = os.environ.get("LIGHTOS_DEBUG", "").strip().lower() in (
                "1", "true", "yes", "on")
            root.setLevel(logging.DEBUG if debug else logging.WARNING)
        logging.captureWarnings(True)
    except Exception:
        pass


# ── Still scheiternde Stellen ────────────────────────────────────────────────
_STILL_MAX_JE_TAG = 5
_still_gesehen: set[tuple[str, str, str]] = set()
_still_je_tag: dict[str, int] = {}


def melde_still(tag: str, exc: BaseException | None = None, text: str = "") -> None:
    """Eine Zeile ``[still:<tag>] …`` fuer einen bisher verschluckten Fehler.

    Gedrosselt: jede ``(tag, Fehlertyp, Meldung)``-Kombination genau einmal, je
    ``tag`` hoechstens ``_STILL_MAX_JE_TAG`` verschiedene (dann ein Hinweis, dass
    weitere unterdrueckt werden) — auch im 44-Hz-Pfad also kein Spam. Darf nie
    werfen."""
    try:
        art = type(exc).__name__ if exc is not None else ""
        meldung = (str(exc) if exc is not None else "")[:300]
        key = (tag, art, meldung + text[:100])
        if key in _still_gesehen:
            return
        _still_gesehen.add(key)
        n = _still_je_tag.get(tag, 0) + 1
        _still_je_tag[tag] = n
        if n > _STILL_MAX_JE_TAG:
            if n == _STILL_MAX_JE_TAG + 1:
                print(f"[still:{tag}] weitere Fehlerarten an dieser Stelle "
                      "werden nicht mehr gemeldet")
            return
        teile = [p for p in (text, f"{art}: {meldung}" if exc is not None else "") if p]
        zeile = f"[still:{tag}] " + " — ".join(teile)
        print(zeile)
        _kindprozess_anhaengen(zeile)
    except Exception:
        pass


_ENV_LOGPFAD = "LIGHTOS_SESSION_LOG"


def _kindprozess_anhaengen(zeile: str) -> None:
    """Im DMX-Worker (eigener Prozess, ``spawn``) gibt es keinen Tee — dessen
    stdout geht nur ins Terminal. Die seltenen ``[still:…]``-Zeilen haengt er
    deshalb direkt an das Sitzungs-Log der App an (Pfad erbt er ueber die
    Umgebung). Im App-Prozess selbst passiert hier nichts."""
    try:
        if _sink is not None:
            return
        pfad = os.environ.get(_ENV_LOGPFAD)
        if not pfad or not os.path.isfile(pfad):
            return
        jetzt = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        with open(pfad, "a", encoding="utf-8", errors="replace") as f:
            f.write(f"{jetzt}   <Prozess {os.getpid()}> {zeile}\n")
    except Exception:
        pass


def _still_reset() -> None:
    """Dedup-Speicher leeren (Tests)."""
    _still_gesehen.clear()
    _still_je_tag.clear()


# ── Laufzeit-Infos (GPU, Bildschirme, DMX, MIDI, Show …) ─────────────────────
def merke(schluessel: str, wert, *, loggen: bool = True) -> None:
    """Haelt eine erst zur Laufzeit bekannte Systeminfo fest (fuer das
    Diagnosepaket) und schreibt sie als ``[diagnose]``-Zeile ins Log — nur, wenn
    sie sich geaendert hat."""
    try:
        text = anonymisiere(str(wert))
        with _laufzeit_lock:
            if _laufzeit.get(schluessel) == text:
                return
            _laufzeit[schluessel] = text
        if loggen:
            print(f"[diagnose] {schluessel}: {text}")
    except Exception:
        pass


def laufzeit_infos() -> dict[str, str]:
    with _laufzeit_lock:
        return dict(_laufzeit)


def gpu_aus_viz_meldung(meldung) -> dict | None:
    """Zerlegt die Zeile ``[viz] GPU-Tier: high (grund=…, renderer=…,
    maxTextures=…, …)``, die der Visualizer per ``console.warn`` schreibt und
    die als Qt-Meldung ankommt. ``None``, wenn es nicht diese Zeile ist.

    Der Renderer-String enthaelt selbst Kommas und Klammern ("ANGLE (AMD,
    Radeon … Direct3D11 …, D3D11)") — er reicht deshalb bis zum festen
    Nachbarfeld ``, maxTextures=``."""
    try:
        if not meldung or "GPU-Tier:" not in meldung:
            return None
        import re
        m = re.search(r"\[viz\] GPU-Tier:\s*(\S+)\s*\((.*)\)\s*$", meldung.strip())
        if not m:
            return None
        stufe, innen = m.group(1), m.group(2)
        r = re.search(r"renderer=(.*?)(?:, maxTextures=|$)", innen)
        if not r:
            return None
        g = re.search(r"grund=(.*?)(?:, renderer=|$)", innen)
        rest = innen[r.end(1):].lstrip(", ")
        return {"stufe": stufe, "renderer": r.group(1).strip(),
                "grund": g.group(1).strip() if g else "", "details": rest}
    except Exception:
        return None


def merke_viz_gpu(meldung) -> bool:
    """Aufruf aus dem Qt-Meldungs-Handler (``main.py``): ist ``meldung`` die
    GPU-Tier-Zeile des Visualizers, den Renderer-String fuer ``systeminfo.txt``
    festhalten. True = erkannt. Billig fuer alle anderen Meldungen, wirft nie."""
    try:
        info = gpu_aus_viz_meldung(meldung)
        if not info:
            return False
        merke("Visualizer GPU-Renderer", info["renderer"])
        einzel = ", ".join(t for t in (
            f"Stufe {info['stufe']}",
            f"Grund: {info['grund']}" if info["grund"] else "",
            info["details"]) if t)
        merke("Visualizer GPU-Details", einzel, loggen=False)
        return True
    except Exception:
        return False


# ── Systeminfo ───────────────────────────────────────────────────────────────
def _standard_programm_dir() -> str:
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", None) or os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def git_commit(programm_dir: str | None = None) -> str:
    """Commit-Kennung aus ``.git`` lesen — ohne ``git``-Aufruf (Start bleibt
    schnell, und auf Testrechnern fehlt git oft). Leer, wenn unbekannt."""
    try:
        wurzel = programm_dir or _standard_programm_dir()
        git = os.path.join(wurzel, ".git")
        if os.path.isfile(git):                     # Worktree: "gitdir: …"
            with open(git, encoding="utf-8") as f:
                zeile = f.read().strip()
            if not zeile.startswith("gitdir:"):
                return ""
            git = zeile.split(":", 1)[1].strip()
            if not os.path.isabs(git):
                git = os.path.join(wurzel, git)
        if not os.path.isdir(git):
            return ""
        with open(os.path.join(git, "HEAD"), encoding="utf-8") as f:
            head = f.read().strip()
        if not head.startswith("ref:"):
            return head[:12]
        ref = head.split(":", 1)[1].strip()
        zweig = ref.rsplit("/", 1)[-1]
        kandidaten = [git]
        common = os.path.join(git, "commondir")
        if os.path.isfile(common):
            with open(common, encoding="utf-8") as f:
                kandidaten.append(os.path.normpath(os.path.join(git, f.read().strip())))
        for g in kandidaten:
            p = os.path.join(g, *ref.split("/"))
            if os.path.isfile(p):
                with open(p, encoding="utf-8") as f:
                    return f"{f.read().strip()[:12]} ({zweig})"
            packed = os.path.join(g, "packed-refs")
            if os.path.isfile(packed):
                with open(packed, encoding="utf-8") as f:
                    for z in f:
                        if z.strip().endswith(" " + ref):
                            return f"{z.split()[0][:12]} ({zweig})"
        return f"? ({zweig})"
    except Exception:
        return ""


BUILD_INFO_NAME = "build_info.json"


def build_info(programm_dir: str | None = None) -> dict:
    """Inhalt der beim Bauen eingebetteten ``build_info.json`` (Commit, Zweig,
    Datum — geschrieben von ``packaging/windows/build_info.py``). Leer, wenn es
    sie nicht gibt oder sie nicht lesbar ist."""
    try:
        wurzel = programm_dir or _standard_programm_dir()
        with open(os.path.join(wurzel, BUILD_INFO_NAME), encoding="utf-8") as f:
            daten = json.load(f)
        return daten if isinstance(daten, dict) else {}
    except Exception:
        return {}


def build_commit(programm_dir: str | None = None) -> str:
    """``<Commit, 12 Stellen> (<Zweig>, gebaut <Datum>)`` aus der eingebetteten
    Build-Info. Leer, wenn unbekannt."""
    info = build_info(programm_dir)
    commit = str(info.get("commit") or "").strip()
    if not commit:
        return ""
    zusatz = [str(info[k]) for k in ("ref",) if info.get(k)]
    if info.get("datum"):
        zusatz.append(f"gebaut {info['datum']}")
    return commit[:12] + (f" ({', '.join(zusatz)})" if zusatz else "")


def commit_text(programm_dir: str | None = None) -> str:
    """Commit fuer Kopfblock/Systeminfo. Gefroren (Setup-Build) gibt es kein
    ``.git`` — dort zaehlt die eingebettete Build-Info. Im Quellbetrieb zaehlt
    ``.git``; eine liegen gebliebene ``build_info.json`` eines lokalen Builds
    waere dort veraltet und kommt nur zum Zug, wenn ``.git`` nichts hergibt."""
    if getattr(sys, "frozen", False):
        # erst der uebergebene Ordner, dann das Bundle selbst (_MEIPASS)
        return (build_commit(programm_dir)
                or (build_commit(None) if programm_dir else "")
                or git_commit(programm_dir))
    return git_commit(programm_dir) or build_commit(programm_dir)


#: IMAGE_FILE_MACHINE_* -> Kurzname.
_MASCHINEN = {0xAA64: "ARM64", 0x8664: "x64", 0x014C: "x86", 0x01C4: "ARM"}
_MASCHINEN_NAMEN = {"AMD64": "x64", "X86_64": "x64", "X64": "x64", "EM64T": "x64",
                    "ARM64": "ARM64", "AARCH64": "ARM64",
                    "X86": "x86", "I386": "x86", "I686": "x86", "ARM": "ARM"}


def _maschine_kurz(name) -> str:
    return _MASCHINEN_NAMEN.get(str(name or "").strip().upper(), "")


def windows_architektur(wow_maschine: int | None, native_maschine: int | None,
                        *, machine: str = "", env=None, bits: int = 64) -> str:
    """Text der Zeile ``Architektur:`` — reine Funktion, alle Werte kommen herein
    (damit unter Linux testbar).

    ``wow_maschine``/``native_maschine`` sind die beiden Ausgaben von
    ``IsWow64Process2`` (``IMAGE_FILE_MACHINE_*``) oder ``None``, wenn der Aufruf
    nicht ging. Achtung: fuer einen Prozess, der NICHT unter WOW64 laeuft, ist
    ``wow_maschine`` 0 — das gilt auch fuer ein x64-Python auf einem ARM64-Geraet
    (x64-Emulation ist kein WOW64). Die Prozess-Architektur kommt deshalb aus
    ``machine`` (``platform.machine()``) bzw. ``PROCESSOR_ARCHITECTURE``.

    Rueckfall ohne Systemaufruf: ``PROCESSOR_ARCHITEW6432`` nennt bei einem
    32-Bit-Prozess die echte Maschine; ein emuliertes x64-Python auf ARM64
    verraet nur ``PROCESSOR_IDENTIFIER`` ("ARMv8 …"). Nie leer."""
    env = env if env is not None else {}
    rueckfall = not native_maschine
    prozess = ""
    if wow_maschine:
        prozess = _MASCHINEN.get(wow_maschine, "")
    prozess = (prozess or _maschine_kurz(machine)
               or _maschine_kurz(env.get("PROCESSOR_ARCHITECTURE")))
    if not prozess and bits == 32:
        prozess = "x86"
    if native_maschine:
        nativ = _MASCHINEN.get(native_maschine, hex(native_maschine))
    else:
        nativ = _maschine_kurz(env.get("PROCESSOR_ARCHITEW6432"))
        if not nativ and "ARM" in env.get("PROCESSOR_IDENTIFIER", "").upper():
            nativ = "ARM64"
        if not nativ:
            nativ = _maschine_kurz(env.get("PROCESSOR_ARCHITECTURE")) or prozess
    if not prozess and not nativ:
        text = f"unbekannt ({bits} Bit)"
    elif not prozess:
        text = f"Prozess unbekannt ({bits} Bit) auf {nativ}"
    elif prozess == nativ:
        text = f"{prozess} nativ"
    elif nativ == "ARM64":
        text = f"{prozess}-Prozess auf ARM64 (Emulation)"
    elif prozess == "x86" and nativ == "x64":
        text = "x86-Prozess auf x64 (WOW64)"
    else:
        text = f"{prozess}-Prozess auf {nativ}"
    if bits == 32 or prozess in ("x86", "ARM"):
        text = f"32 Bit: {text}"
    if rueckfall:
        text += " [Rueckfall: aus Umgebungsvariablen, IsWow64Process2 ohne Ergebnis]"
    return text


def _iswow64process2() -> tuple[int, int] | None:
    """``(Prozess-Maschine, native Maschine)`` aus ``IsWow64Process2`` oder
    ``None`` (kein Windows, Windows < 10 1511, Aufruf gescheitert).

    STAB-33: ``argtypes``/``restype`` sind Pflicht. Ohne sie gibt
    ``GetCurrentProcess()`` das Pseudo-Handle (-1) als 32-Bit-``int`` zurueck und
    ctypes reicht es so weiter — auf x64 ein ungueltiges Handle, der Aufruf
    scheitert und die Zeile blieb leer."""
    try:
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
        k32.GetCurrentProcess.restype = wintypes.HANDLE
        k32.GetCurrentProcess.argtypes = []
        k32.IsWow64Process2.restype = wintypes.BOOL
        k32.IsWow64Process2.argtypes = [wintypes.HANDLE,
                                        ctypes.POINTER(wintypes.USHORT),
                                        ctypes.POINTER(wintypes.USHORT)]
        proc = wintypes.USHORT(0)
        nativ = wintypes.USHORT(0)
        if not k32.IsWow64Process2(k32.GetCurrentProcess(), ctypes.byref(proc),
                                   ctypes.byref(nativ)):
            return None
        return int(proc.value), int(nativ.value)
    except Exception:
        return None


def _windows_architektur() -> str:
    """Prozess- und Maschinen-Architektur unter Windows. Ein x64-Python auf einem
    ARM64-Geraet meldet ueber ``platform.machine()`` "AMD64" (emuliert) — erst
    ``IsWow64Process2`` verraet die echte Maschine."""
    bits = struct.calcsize("P") * 8
    try:
        machine = platform.machine()
    except Exception:
        machine = ""
    try:
        paar = _iswow64process2()
    except Exception:
        paar = None
    wow, nativ = paar if paar else (None, None)
    return windows_architektur(wow, nativ, machine=machine, env=os.environ,
                               bits=bits)


def basis_infos(app_version: str = "?", programm_dir: str | None = None
                ) -> list[tuple[str, str]]:
    """Was schon VOR der QApplication feststeht. Jede Zeile einzeln abgesichert."""
    zeilen: list[tuple[str, str]] = []

    def feld(name, fn):
        try:
            wert = fn()
        except Exception as e:                      # noqa: BLE001
            wert = f"? ({type(e).__name__})"
        zeilen.append((name, anonymisiere(str(wert))))

    feld("LightOS", lambda: app_version)
    feld("Commit", lambda: commit_text(programm_dir) or "unbekannt")
    feld("Gefroren (Installer-Build)",
         lambda: "ja" if getattr(sys, "frozen", False) else "nein (Quellbetrieb)")
    feld("Betriebssystem", lambda: platform.platform())
    if sys.platform == "win32":
        feld("Windows", lambda: " ".join(p for p in platform.win32_ver() if p))
        feld("Architektur", _windows_architektur)
    elif sys.platform == "darwin":
        feld("macOS", lambda: platform.mac_ver()[0])
    else:
        feld("Distribution", _linux_distribution)
    feld("Maschine", lambda: f"{platform.machine()} | Prozess {struct.calcsize('P') * 8} Bit")
    feld("Python", lambda: f"{platform.python_version()} "
                           f"({platform.python_implementation()}) {sys.executable}")
    feld("PySide6/Qt", _qt_versionen)
    feld("Datenordner", app_data_dir)
    feld("Sitzungs-Log", log_path)
    feld("Arbeitsordner", os.getcwd)
    feld("Sprache/Codierung", lambda: f"{_locale()} | stdout "
                                      f"{getattr(sys.__stdout__, 'encoding', None)}")
    feld("Anzeige", _anzeige_umgebung)
    return zeilen


def _linux_distribution() -> str:
    try:
        d = platform.freedesktop_os_release()
        return d.get("PRETTY_NAME") or d.get("NAME", "?")
    except Exception:
        return "?"


def _locale() -> str:
    try:
        import locale
        return str(locale.getlocale())
    except Exception:
        return "?"


def _anzeige_umgebung() -> str:
    teile = []
    for var in ("QT_QPA_PLATFORM", "XDG_SESSION_TYPE", "WAYLAND_DISPLAY",
                "QT_SCALE_FACTOR", "QTWEBENGINE_CHROMIUM_FLAGS"):
        if os.environ.get(var):
            teile.append(f"{var}={os.environ[var]}")
    return "; ".join(teile) or "-"


def _qt_versionen() -> str:
    if "PySide6" not in sys.modules:
        try:
            import PySide6  # noqa: F401
        except Exception:
            return "PySide6 nicht importierbar"
    import PySide6
    from PySide6 import QtCore
    return f"PySide6 {PySide6.__version__} / Qt {QtCore.qVersion()}"


def bildschirm_infos() -> list[str]:
    """Bildschirme der laufenden QApplication (leer ohne QApplication)."""
    try:
        if "PySide6.QtGui" not in sys.modules:
            return []
        from PySide6.QtGui import QGuiApplication
        if QGuiApplication.instance() is None:
            return []
        raus = []
        for i, s in enumerate(QGuiApplication.screens()):
            g = s.geometry()
            raus.append(f"#{i} {s.name()}: {g.width()}x{g.height()} logisch, "
                        f"Skalierung {s.devicePixelRatio():g}, "
                        f"{s.logicalDotsPerInch():.0f} dpi, {s.refreshRate():.0f} Hz")
        return raus
    except Exception as e:
        return [f"? ({type(e).__name__}: {e})"]


def dmx_infos() -> list[str]:
    """Eingerichtete DMX-Ausgaenge — nur, wenn der App-Zustand schon existiert
    (das Diagnosepaket aus der Kommandozeile startet keine Ausgabe)."""
    try:
        mod = sys.modules.get("src.core.app_state")
        state = getattr(mod, "_state", None) if mod else None
        if state is None:
            return []
        raus = []
        for e in state.output_manager.ausgabe_status():
            zustand = {True: "sendet", False: "sendet NICHT", None: "unbekannt"}.get(
                e.get("verbunden"), "?")
            problem = f" — Problem: {e['problem']}" if e.get("problem") else ""
            raus.append(f"U{e.get('universum')} {e.get('weg')} → "
                        f"{e.get('ziel') or '(Standard)'}: {zustand}{problem}")
        return raus or ["keine Ausgaenge eingerichtet"]
    except Exception as e:
        return [f"? ({type(e).__name__}: {e})"]


def show_info() -> str:
    """Geladene Show (Name, Geraeteanzahl) — leer ohne App-Zustand."""
    try:
        mod = sys.modules.get("src.core.app_state")
        state = getattr(mod, "_state", None) if mod else None
        if state is None:
            return ""
        name = getattr(state, "show_name", None)
        name = f"'{name}'" if name else "(keine Show-Datei geladen, Arbeitsstand)"
        return f"{name} mit {len(state.get_patched_fixtures())} Geraet(en)"
    except Exception as e:
        return f"? ({type(e).__name__}: {e})"


def melde_show_geladen(state) -> None:
    """Aufruf aus dem Show-Laden: Name + Geraeteanzahl festhalten."""
    try:
        merke("Show", f"'{getattr(state, 'show_name', '?')}' mit "
                      f"{len(state.get_patched_fixtures())} Geraet(en)")
    except Exception as e:
        melde_still("diagnose.show", e)


def midi_infos() -> list[str]:
    try:
        mod = sys.modules.get("src.core.midi.midi_manager")
        mgr = getattr(mod, "_manager", None) if mod else None
        if mgr is None:
            return []
        ein = sorted(getattr(mgr, "_inputs", {}) or {})
        aus = getattr(mgr, "_output_name", "") or "-"
        backend = "python-rtmidi" if "rtmidi" in sys.modules else "WinMM/keins"
        return [f"Eingaenge offen: {', '.join(ein) if ein else '-'}",
                f"Ausgang: {aus}", f"Backend: {backend}"]
    except Exception as e:
        return [f"? ({type(e).__name__}: {e})"]


def kopfblock(app_version: str = "?", programm_dir: str | None = None) -> str:
    zeilen = [f"\n=== LightOS-Sitzung {_cl._ts()} | PID {os.getpid()} ==="]
    zeilen += [f"  {k}: {v}" for k, v in basis_infos(app_version, programm_dir)]
    zeilen.append("  (Bildschirme, GPU, DMX, MIDI und Show folgen als "
                  "[diagnose]-Zeilen, sobald bekannt)")
    zeilen.append("=" * 60)
    return "\n".join(zeilen) + "\n"


def melde_laufzeit_umgebung() -> None:
    """Nach dem Aufbau des Hauptfensters: Bildschirme, DMX und MIDI ins Log
    nachtragen (der Kopfblock entsteht vor der QApplication)."""
    for i, z in enumerate(bildschirm_infos()):
        merke(f"Bildschirm {i}", z)
    for i, z in enumerate(dmx_infos()):
        merke(f"DMX {i}", z)
    for z in midi_infos():
        k, _, v = z.partition(": ")
        merke(f"MIDI {k}", v)
    show = show_info()
    if show:
        merke("Show", show)


def systeminfo_text(app_version: str = "?", programm_dir: str | None = None) -> str:
    zeilen = [f"LightOS-Systeminfo, erstellt {_cl._ts()}", ""]
    zeilen += [f"{k}: {v}" for k, v in basis_infos(app_version, programm_dir)]
    for titel, werte in (("Bildschirme", bildschirm_infos()),
                         ("DMX-Ausgaenge", dmx_infos()), ("MIDI", midi_infos())):
        if werte:
            zeilen += ["", f"{titel}:"] + [f"  {anonymisiere(w)}" for w in werte]
    if show_info():
        zeilen += ["", f"Show: {anonymisiere(show_info())}"]
    lz = laufzeit_infos()
    if lz:
        zeilen += ["", "Waehrend der Sitzung gemeldet:"]
        zeilen += [f"  {k}: {v}" for k, v in sorted(lz.items())]
    else:
        zeilen += ["", "(Keine Laufzeit-Infos: Paket ausserhalb der laufenden App "
                       "erstellt — siehe [diagnose]-Zeilen im Log.)"]
    return "\n".join(zeilen) + "\n"


# ── Einstellungen ohne private Inhalte ───────────────────────────────────────
_GEHEIM = ("token", "pass", "secret", "geheim", "auth", "key", "cookie")
_PERSOENLICH = ("recent", "zuletzt", "path", "pfad", "file", "datei", "dir",
                "ordner", "show", "name", "ip", "host", "url")


def _wert_zusammenfassen(schluessel: str, wert) -> str:
    k = schluessel.lower()
    if any(g in k for g in _GEHEIM) and not isinstance(wert, (bool, dict)):
        return "<ausgeblendet>"
    if isinstance(wert, bool) or wert is None or isinstance(wert, (int, float)):
        return repr(wert)
    if isinstance(wert, str):
        if any(p in k for p in _PERSOENLICH) or "/" in wert or "\\" in wert:
            return f"<Text, {len(wert)} Zeichen>"
        return repr(anonymisiere(wert[:60]))
    if isinstance(wert, (list, tuple)):
        return f"<Liste, {len(wert)} Eintraege>"
    return f"<{type(wert).__name__}>"


def _einstellungen_flach(daten, praefix: str = "", tiefe: int = 0) -> list[str]:
    raus = []
    if isinstance(daten, dict) and tiefe < 4:
        for k in sorted(daten, key=str):
            v = daten[k]
            name = f"{praefix}{k}"
            if isinstance(v, dict) and not any(g in str(k).lower() for g in _GEHEIM):
                raus += _einstellungen_flach(v, name + ".", tiefe + 1)
            else:
                raus.append(f"{name} = {_wert_zusammenfassen(str(k), v)}")
    else:
        raus.append(f"{praefix or '(Wurzel)'} = {_wert_zusammenfassen(praefix, daten)}")
    return raus


def einstellungen_text() -> str:
    """Schluessel der Einstellungsdateien mit unbedenklichen Werten (Zahlen,
    Schalter); Texte, Pfade, Namen und Geheimnisse nur als Platzhalter."""
    d = app_data_dir()
    zeilen = ["LightOS-Einstellungen (ohne private Inhalte: Texte/Pfade/Namen nur "
              "als Platzhalter, Geheimnisse ausgeblendet)", ""]
    for name in ("ui_prefs.json", "bibliothek_download.json", "universes.json"):
        pfad = os.path.join(d, name)
        zeilen.append(f"[{name}]")
        if not os.path.exists(pfad):
            zeilen += ["  (nicht vorhanden)", ""]
            continue
        try:
            with open(pfad, encoding="utf-8") as f:
                daten = json.load(f)
            if name == "universes.json" and isinstance(daten, list):
                # Ausgaben-Konfiguration: Typ je Universum ist der Kern jeder
                # DMX-Fernhilfe; das Ziel (COM-Port/IP) bleibt drin, ohne Namen.
                for r in daten:
                    if isinstance(r, dict):
                        zeilen.append(
                            f"  U{r.get('num')}: {r.get('output') or 'Disabled'} "
                            f"→ {r.get('patch') or '(Standard)'}"
                            + (f" (extern U{r.get('out_universe')})"
                               if r.get("out_universe") not in (None, "") else ""))
            else:
                zeilen += ["  " + z for z in _einstellungen_flach(daten)]
        except Exception as e:
            zeilen.append(f"  (nicht lesbar: {type(e).__name__})")
        zeilen.append("")
    return "\n".join(zeilen) + "\n"


def datenordner_text() -> str:
    """Nur NAMEN und Groessen der obersten Ebene — kein Inhalt."""
    d = app_data_dir()
    zeilen = [f"Datenordner {anonymisiere(d)} (nur Namen/Groessen, kein Inhalt)", ""]
    try:
        for name in sorted(os.listdir(d)):
            p = os.path.join(d, name)
            try:
                if os.path.isdir(p):
                    zeilen.append(f"  {name}/  ({len(os.listdir(p))} Eintraege)")
                else:
                    zeilen.append(f"  {name}  ({os.path.getsize(p)} Bytes)")
            except Exception:
                zeilen.append(f"  {name}  (?)")
    except Exception as e:
        zeilen.append(f"  (nicht lesbar: {type(e).__name__})")
    return "\n".join(zeilen) + "\n"


# ── Diagnosepaket ────────────────────────────────────────────────────────────
PAKET_INHALT = (
    "• die Sitzungs-Logs (aktuelle und vorige Sitzungen)\n"
    "• das Absturzprotokoll crash.log\n"
    "• Systeminfo: LightOS-Version, Betriebssystem, Python/Qt, Bildschirme, "
    "GPU, DMX-Ausgaenge, MIDI-Geraete\n"
    "• eine Liste der Einstellungen (Zahlen und Schalter; Texte, Pfade und "
    "Geheimnisse nur als Platzhalter)\n"
    "• die Datei-NAMEN im Datenordner\n\n"
    "NICHT enthalten: Show-Dateien, Datenbanken, Snaps, Buehnen. Dein "
    "Benutzername in Pfaden wird durch ~ bzw. %USERNAME% ersetzt.")

_LIESMICH = ("LightOS-Diagnosepaket\n=====================\n\nEnthaelt:\n"
             + PAKET_INHALT + "\n\nlogs/      Sitzungs-Logs (lightos.log = letzte "
             "Sitzung, .1 = davor …)\ncrash/     Absturzprotokoll\n"
             "systeminfo.txt, einstellungen.txt, datenordner.txt\n")


#: ``Windows fatal exception: code 0x…`` — Codes, die KEIN Absturz sind.
#:
#: ``faulthandler`` haengt unter Windows einen Vectored Exception Handler ein, der
#: jede Ausnahme mit gesetztem Fehlerbit (0x8…/0xC…) als "fatal" samt Thread-
#: Stand schreibt — auch First-Chance-Ausnahmen, die das Betriebssystem bzw. COM
#: gleich danach selbst behandelt; die App laeuft weiter. Einen Filter kennt
#: ``faulthandler.enable`` nicht (nur ``file``/``all_threads``), deshalb wird
#: hier nur GEKENNZEICHNET. Bewusst eine kurze Liste bekannter COM/RPC-Hinweise:
#: alles andere (access violation, 0xC0000005, stack overflow …) bleibt, wie es
#: ist.
HARMLOSE_WINDOWS_CODES: dict[str, str] = {
    "0x8001010d": "RPC_E_CANTCALLOUT_ININPUTSYNCCALL — COM-Aufruf waehrend einer "
                  "synchronen Eingabenachricht, typisch bei Bildschirmlesern/"
                  "UI-Automation",
    "0x8001010e": "RPC_E_WRONG_THREAD — COM-Objekt aus einem anderen Thread "
                  "angesprochen, COM lehnt den Aufruf ab",
    "0x80010108": "RPC_E_DISCONNECTED — das COM-Gegenueber ist schon weg",
    "0x800706ba": "RPC_S_SERVER_UNAVAILABLE — der angesprochene Dienst "
                  "antwortet nicht",
}
_FATAL_ANFAENGE = ("Windows fatal exception:", "Fatal Python error:")


def kennzeichne_harmlose_ausnahmen(text: str) -> tuple[str, dict[str, int], int]:
    """Setzt hinter jede ``Windows fatal exception: code <bekannt harmlos>``-
    Zeile eine Zeile ``^ kein Absturz: COM-Hinweis <code> …``. Das Original
    bleibt vollstaendig stehen (auch der Thread-Stand).

    Rueckgabe: ``(Text, {code: Anzahl}, andere)`` — ``andere`` zaehlt die
    uebrigen "fatal"-Zeilen (echte Abstuerze), die NICHT angefasst werden."""
    harmlos: dict[str, int] = {}
    andere = 0
    if not text or "fatal" not in text.lower():
        return text, harmlos, andere
    import re
    muster = re.compile(r"^Windows fatal exception: code (0x[0-9a-fA-F]+)\s*$")
    raus = []
    for zeile in text.splitlines(keepends=True):
        raus.append(zeile)
        nackt = zeile.rstrip("\r\n")
        if not nackt.startswith(_FATAL_ANFAENGE):
            continue
        m = muster.match(nackt)
        code = m.group(1).lower() if m else ""
        if code in HARMLOSE_WINDOWS_CODES:
            harmlos[code] = harmlos.get(code, 0) + 1
            ende = zeile[len(nackt):] or "\n"
            raus.append(f"    ^ kein Absturz: COM-Hinweis {code} "
                        f"({HARMLOSE_WINDOWS_CODES[code]}). LightOS lief weiter; "
                        "der folgende Thread-Stand ist nur eine Momentaufnahme."
                        + ende)
        else:
            andere += 1
    return "".join(raus), harmlos, andere


def _liesmich_absturzhinweise(befunde: list[tuple[str, dict[str, int], int]]) -> str:
    """Abschnitt fuer LIESMICH.txt — nur, wenn ein harmloser Code vorkam."""
    if not any(h for _n, h, _a in befunde):
        return ""
    zeilen = ["", "Hinweise zum Absturzprotokoll", "-----------------------------"]
    for name, harmlos, andere in befunde:
        for code, n in sorted(harmlos.items()):
            zeilen.append(
                f"{name}: {n}× 'Windows fatal exception: code {code}' = "
                f"kein Absturz: COM-Hinweis {code} "
                f"({HARMLOSE_WINDOWS_CODES[code].split(' — ')[0]}). Windows "
                "meldet das intern, LightOS lief weiter. Die Stellen sind in "
                "der Datei mit '^ kein Absturz' gekennzeichnet.")
        if harmlos and andere:
            zeilen.append(
                f"{name}: {andere} weitere 'fatal'-Eintraege sind NICHT als "
                "harmlos bekannt und unveraendert — das koennen echte "
                "Abstuerze sein.")
    return "\n".join(zeilen) + "\n"


def standard_ziel() -> str:
    """Desktop (falls vorhanden), sonst Home — dort findet ein Tester die Datei."""
    home = os.path.expanduser("~")
    ordner = home
    for kandidat in ("Desktop", "Schreibtisch"):
        p = os.path.join(home, kandidat)
        if os.path.isdir(p):
            ordner = p
            break
    stempel = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    return os.path.join(ordner, f"LightOS-Diagnose-{stempel}.zip")


def _logdateien() -> list[tuple[str, str]]:
    """(Pfad, Name im zip) aller Logdateien, die es gibt."""
    raus = []

    def mit_backups(pfad, ziel_ordner, anzahl):
        for p in [pfad] + [f"{pfad}.{i}" for i in range(1, anzahl + 1)]:
            if os.path.isfile(p):
                raus.append((p, f"{ziel_ordner}/{os.path.basename(p)}"))

    mit_backups(log_path(), "logs", BACKUPS)
    try:
        mit_backups(crash_log_path(), "crash", 3)
    except Exception:
        pass
    # Altbestand: vor STAB-30 schrieb nur der pythonw-Start nach <Daten>/lightos.log
    mit_backups(os.path.join(app_data_dir(), LOG_NAME), "logs/alt", 2)
    la = os.path.join(app_data_dir(), "last_alive.txt")
    if os.path.isfile(la):
        raus.append((la, "crash/last_alive.txt"))
    return raus


def _lies_text(pfad: str) -> str:
    groesse = os.path.getsize(pfad)
    with open(pfad, "rb") as f:
        if groesse > _PAKET_MAX_JE_DATEI:
            f.seek(groesse - _PAKET_MAX_JE_DATEI)
            kopf = f"(… erste {groesse - _PAKET_MAX_JE_DATEI} Bytes gekuerzt)\n"
        else:
            kopf = ""
        return kopf + f.read().decode("utf-8", errors="replace")


def erstelle_diagnosepaket(ziel: str | None = None, app_version: str = "?",
                           programm_dir: str | None = None) -> str:
    """Schreibt das zip und gibt seinen Pfad zurueck (wirft bei Schreibfehler —
    der Aufrufer zeigt die Meldung). Alle Texte werden anonymisiert."""
    ziel = ziel or standard_ziel()
    if os.path.isdir(ziel):
        ziel = os.path.join(ziel, os.path.basename(standard_ziel()))
    parent = os.path.dirname(os.path.abspath(ziel))
    os.makedirs(parent, exist_ok=True)
    try:
        if _sink is not None:
            _sink.flush()
    except Exception:
        pass
    eintraege: list[tuple[str, str]] = [("LIESMICH.txt", _LIESMICH)]
    befunde: list[tuple[str, dict[str, int], int]] = []
    for pfad, name in _logdateien():
        if pfad.lower().endswith(_VERBOTENE_ENDUNGEN):
            continue
        try:
            text = anonymisiere(_lies_text(pfad))
            if name.startswith("crash/"):
                # STAB-33: COM-Hinweise sehen in crash.log wie Abstuerze aus.
                try:
                    text, harmlos, andere = kennzeichne_harmlose_ausnahmen(text)
                    befunde.append((name, harmlos, andere))
                except Exception:
                    pass
            eintraege.append((name, text))
        except Exception as e:
            eintraege.append((name + ".fehler.txt",
                              f"nicht lesbar: {type(e).__name__}: {e}\n"))
    for name, fn in (("systeminfo.txt", lambda: systeminfo_text(app_version, programm_dir)),
                     ("einstellungen.txt", einstellungen_text),
                     ("datenordner.txt", datenordner_text)):
        try:
            eintraege.append((name, anonymisiere(fn())))
        except Exception as e:
            eintraege.append((name, f"nicht erstellbar: {type(e).__name__}: {e}\n"))
    try:
        eintraege[0] = ("LIESMICH.txt", _LIESMICH + _liesmich_absturzhinweise(befunde))
    except Exception:
        pass
    tmp = ziel + ".tmp"
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, text in eintraege:
            if name.lower().endswith(_VERBOTENE_ENDUNGEN):
                continue
            zf.writestr(name, text)
    os.replace(tmp, ziel)
    return ziel


def cli_diagnose(ziel: str | None, app_version: str = "?",
                 programm_dir: str | None = None) -> int:
    """``main.py --diagnose [ZIEL.zip]``: Paket ohne Fenster und ohne App-Start
    schreiben. 0 = ok, 1 = Fehler."""
    try:
        pfad = erstelle_diagnosepaket(ziel or None, app_version, programm_dir)
    except Exception as e:
        print(f"[diagnose] ERROR: Diagnosepaket nicht geschrieben: {e}",
              file=sys.stderr)
        return 1
    print(f"[diagnose] Diagnosepaket geschrieben: {pfad}")
    print("[diagnose] Bitte diese Datei an die LightOS-Hilfe schicken. Enthalten:")
    print(PAKET_INHALT)
    return 0
