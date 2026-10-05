"""DOC-16: Sandbox fuer das Bild-Werkzeug — kein Byte in den echten Datenordner.

Das Werkzeug baut ein volles ``MainWindow``. Das greift beim Aufbau auf eine
ganze Reihe von Nutzerdateien zu: Fixture-Bibliothek (wird beim Oeffnen
migriert), ``recent.json``, ``auto_save.lshow``, ``crash.log``, die sACN-CID,
``ui_prefs.json`` und die frueher CWD-relativen ``data/``-Dateien
(``midi_mappings.json``, ``channel_groups.json``, ``universes.json``, die
Show-DB — seit XPLAT-44 im App-Datenordner). ``tools/_gen_env.py`` lenkt davon nur die Show-DB um; fuer ein
Werkzeug, das die ganze App startet, reicht das nicht (Befund aus der
Machbarkeitsprobe, ``capture_*_tempo_guide.py`` haben genau diese Luecke).

Deshalb hier:

1. :func:`einrichten` setzt **vor jedem src-Import** alle bekannten Schalter
   (Quelle: ``src/core/paths.py``, ``fixture_db.py``, ``app_state.py``,
   ``output_config.py``, ``remote_settings.py``, ``tests/conftest.py``) auf
   einen frischen ``mkdtemp``-Ordner und wechselt dorthin (``os.chdir``).
2. :func:`selbstpruefung` fragt NACH dem Import die tatsaechlich eingefrorenen
   Pfade der Module ab. Liegt einer ausserhalb der Sandbox, bricht das
   Werkzeug ab, bevor ein Fenster entsteht.
3. :func:`schnappschuss` / :func:`vergleiche` halten die echten Datenorte vor
   und nach dem Lauf fest (mtime + Groesse, Existenz) — Muster wie der
   Waechter in ``tests/test_app_data_dir.py``.
4. :func:`nebenwirkungen_abschalten` legt still, wofuer es keinen Schalter
   gibt: MIDI-Autoconnect (oeffnete in der Probe echte ALSA-Ports) und das
   Starten der Web-Remote.

Dieses Modul importiert selbst nichts aus ``src`` (ausser in den Funktionen,
die ausdruecklich NACH der Einrichtung laufen).
"""
from __future__ import annotations

import os
import sys
import tempfile
from dataclasses import dataclass, field

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Schalter, die nur AN/AUS sind (Wert "1").
_SCHALTER = (
    "LIGHTOS_NO_OUTPUT_THREAD",     # kein 44-Hz-Ausgabe-Thread
    "LIGHTOS_NO_AUDIO_AUTOSTART",   # keine Audio-Aufnahme beim Start
    "LIGHTOS_SERIAL_INPROC",        # kein multiprocessing-spawn fuer Enttec
    "LIGHTOS_NO_RECOVERY_PROMPT",   # keine Autosave-Wiederherstellungsfrage
    "LIGHTOS_NO_DATENUMZUG",        # XPLAT-44: kein Kopieren echter data/-Dateien
)

# Variablen, die Ausgabe/Netz in eine bestimmte Richtung lenken wuerden —
# in der Sandbox ungesetzt.
_ENTFERNEN = (
    "LIGHTOS_OUTPUT_IFACE",
    "LIGHTOS_REMOTE_TOKEN",
    "LIGHTOS_WEBENGINE_FLAGS",
)


@dataclass
class Sandbox:
    basis: str
    pfade: dict = field(default_factory=dict)

    def enthaelt(self, pfad: str) -> bool:
        if not pfad:
            return False
        p = os.path.realpath(os.path.abspath(pfad))
        b = os.path.realpath(self.basis)
        return p == b or p.startswith(b + os.sep)


def echter_home() -> str:
    """Das Home des Kontos laut Passwortdatenbank — unabhaengig von ``$HOME``."""
    try:
        import pwd                  # nur POSIX; auf Windows gilt expanduser
        return pwd.getpwuid(os.getuid()).pw_dir
    except Exception:
        return os.path.expanduser("~")


def echte_datenorte() -> list[str]:
    """Orte, die das Werkzeug NIE anfassen darf (fuer Schnappschuss + Abgleich).

    Wird VOR :func:`einrichten` aufgerufen, damit auch ein vom Nutzer bewusst
    gesetztes ``XDG_DATA_HOME``/``APPDATA`` erfasst wird.
    """
    home = echter_home()
    orte = [
        os.path.join(home, ".local", "share", "LightOS"),
        os.path.join(home, ".config", "LightOS"),
        os.path.join(home, "LightOS"),
        os.path.join(REPO, "data"),
        os.path.join(REPO, "shows"),
    ]
    for var in ("XDG_DATA_HOME", "APPDATA"):
        v = os.environ.get(var)
        if v:
            orte.append(os.path.join(v, "LightOS"))
    # Umgelenkte Einzeldateien: nur, wenn sie NICHT im System-Temp liegen. Die
    # Testsuite setzt diese Variablen auf eigene Wegwerf-Ordner unter /tmp, in
    # die parallel laufende Tests staendig schreiben — das ist kein Nutzer-
    # Datenort, und ein Abgleich dort schlug im segmentierten Gate falsch an.
    tmp = os.path.realpath(tempfile.gettempdir()) + os.sep
    for var in ("LIGHTOS_SHOW_DB", "LIGHTOS_FIXTURE_DB", "LIGHTOS_UNIVERSES_JSON"):
        v = os.environ.get(var)
        if v:
            ordner = os.path.dirname(os.path.abspath(v))
            if not (os.path.realpath(ordner) + os.sep).startswith(tmp):
                orte.append(ordner)
    # Doppelte raus, Reihenfolge stabil.
    gesehen, aus = set(), []
    for o in orte:
        o = os.path.abspath(o)
        if o not in gesehen:
            gesehen.add(o)
            aus.append(o)
    return aus


def einrichten(basis: str | None = None, *, bildschirm: bool = False) -> Sandbox:
    """Lenkt alle Datenpfade in ``basis`` (Default: frischer mkdtemp) um.

    MUSS vor dem ersten ``src``-Import laufen. Setzt hart (kein setdefault):
    eine geerbte Umgebung — etwa aus der Testsuite oder einer Shell, in der
    ``LIGHTOS_SHOW_DB`` auf eine echte DB zeigt — darf hier NICHT gewinnen.

    ``bildschirm=True`` (DOC-21, ``--bildschirm``): statt ``offscreen`` auf dem
    echten X11-Bildschirm (``xcb``) zeichnen — nur fuer 3D-Szenen, deren WebGL
    offscreen schwarz bleibt. Alle Datenpfade bleiben genauso umgelenkt.
    """
    if any(m == "src" or m.startswith("src.") for m in sys.modules):
        raise RuntimeError(
            "Sandbox zu spaet: src ist schon importiert — die Pfade der Module "
            "sind damit bereits eingefroren.")
    if bildschirm and not os.environ.get("DISPLAY"):
        raise SystemExit("[anleitungsbilder] --bildschirm braucht einen X11-Bildschirm "
                         "(DISPLAY ist leer).")
    # Die X-Anmeldung liegt sonst unter ~/.Xauthority — HOME wird gleich
    # umgelenkt. Nur der Verweis wird gemerkt, die Datei liest Xlib selbst.
    xauth = os.environ.get("XAUTHORITY") or os.path.expanduser("~/.Xauthority")
    basis = os.path.realpath(basis or tempfile.mkdtemp(prefix="lightos_doku_"))
    p = {
        "HOME": os.path.join(basis, "home"),
        # XPLAT-39 (Windows-Gate von B, 01.10.2026): expanduser("~") liest dort
        # USERPROFILE, nicht HOME — ohne diese Umlenkung meldete die
        # Selbstpruefung zu Recht "Sandbox undicht" und brach ab.
        "USERPROFILE": os.path.join(basis, "home"),
        "LOCALAPPDATA": os.path.join(basis, "localappdata"),
        "XDG_DATA_HOME": os.path.join(basis, "xdg", "data"),
        "XDG_CONFIG_HOME": os.path.join(basis, "xdg", "config"),
        "XDG_CACHE_HOME": os.path.join(basis, "xdg", "cache"),
        "XDG_STATE_HOME": os.path.join(basis, "xdg", "state"),
        "XDG_RUNTIME_DIR": os.path.join(basis, "xdg", "runtime"),
        "APPDATA": os.path.join(basis, "appdata"),
        "LIGHTOS_SHOW_DB": os.path.join(basis, "arbeit", "data", "current_show.db"),
        "LIGHTOS_FIXTURE_DB": os.path.join(basis, "xdg", "data", "LightOS", "fixtures.db"),
        "LIGHTOS_CRASH_LOG": os.path.join(basis, "arbeit", "crash.log"),
        "LIGHTOS_SACN_CID": os.path.join(basis, "arbeit", "sacn_cid"),
        "LIGHTOS_PREFS_DIR": os.path.join(basis, "xdg", "data", "LightOS"),
        "LIGHTOS_UNIVERSES_JSON": os.path.join(basis, "arbeit", "data", "universes.json"),
    }
    for k, v in p.items():
        # Ordner anlegen: fuer Verzeichnis-Variablen den Pfad selbst, fuer
        # Datei-Variablen den Elternordner.
        ist_datei = os.path.splitext(v)[1] != "" or k in ("LIGHTOS_SACN_CID",
                                                          "LIGHTOS_CRASH_LOG")
        os.makedirs(os.path.dirname(v) if ist_datei else v, exist_ok=True)
        os.environ[k] = v
    os.chmod(p["XDG_RUNTIME_DIR"], 0o700)
    for k in _SCHALTER:
        os.environ[k] = "1"
    for k in _ENTFERNEN:
        os.environ.pop(k, None)
    # Qt: offscreen, feste Skalierung (dpr 1.0 -> 1600x900 bleibt 1600x900).
    os.environ["QT_QPA_PLATFORM"] = "xcb" if bildschirm else "offscreen"
    if bildschirm and os.path.exists(xauth):
        os.environ["XAUTHORITY"] = xauth
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
    os.environ["QT_SCALE_FACTOR"] = "1"
    os.environ.pop("QT_SCREEN_SCALE_FACTORS", None)
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    sys.dont_write_bytecode = True
    # Kein Chromium-Sandbox-Zwang fuer die (hier ohnehin schwarze) WebEngine.
    os.environ["LIGHTOS_WEBENGINE_NO_SANDBOX"] = "1"
    # Arbeitsverzeichnis: bis XPLAT-44 waren data/*.json cwd-relativ; heute
    # liegen sie im (umgelenkten) App-Datenordner. Der Wechsel in die Sandbox
    # bleibt als zweite Sicherung fuer alles, was noch relativ aufloest.
    arbeit = os.path.join(basis, "arbeit")
    os.makedirs(os.path.join(arbeit, "data"), exist_ok=True)
    os.chdir(arbeit)
    # Ausgabe-Konfiguration der Sandbox: Universum 1 per Art-Net an die eigene
    # Loopback-Adresse. Es geht nichts raus (kein Ausgabe-Thread), aber die
    # Statusleiste zeigt einen eingerichteten Ausgang statt „U1 ohne Ausgang".
    with open(p["LIGHTOS_UNIVERSES_JSON"], "w", encoding="utf-8") as f:
        f.write('[{"num": 1, "output": "ArtNet", "patch": "127.0.0.1"}]\n')
    if REPO not in sys.path:
        sys.path.insert(0, REPO)
    return Sandbox(basis=basis, pfade=dict(p, cwd=arbeit))


def aufgeloeste_pfade() -> dict:
    """Die Pfade, die die geladenen Module TATSAECHLICH benutzen werden.

    Laeuft nach dem Import von src (dort werden mehrere Pfade beim Laden
    eingefroren). Relative Pfade werden gegen das aktuelle cwd aufgeloest —
    genau so, wie die App sie oeffnen wuerde.
    """
    from src.core import paths
    from src.core import app_state
    from src.core.database import fixture_db
    from src.ui.widgets import output_config
    from src.web import remote_settings
    from src.ui import main_window
    from src.ui.views import channel_groups_view
    return {
        "app_data_dir": paths.app_data_dir(),
        "crash_log": paths.crash_log_path(),
        "sacn_cid": paths.sacn_cid_path(),
        "fixture_db": os.path.abspath(fixture_db.DB_PATH),
        "show_db": os.path.abspath(app_state.SHOW_DB_PATH),
        "universes_json": os.path.abspath(output_config._UNIV_CONFIG_PATH),
        "ui_prefs": os.path.abspath(remote_settings._prefs_path()),
        "recent_json": os.path.abspath(main_window._recent_files_path()),
        "channel_groups": os.path.abspath(channel_groups_view._PERSIST_PATH),
        "midi_mappings": os.path.abspath(paths.user_data_file("midi_mappings.json")),
        "home": os.path.expanduser("~"),
        "cwd": os.getcwd(),
    }


def selbstpruefung(sb: Sandbox) -> dict:
    """Bricht ab (``SystemExit``), wenn irgendein Pfad ausserhalb liegt."""
    pf = aufgeloeste_pfade()
    draussen = {k: v for k, v in pf.items() if not sb.enthaelt(v)}
    if draussen:
        zeilen = "\n".join(f"  {k}: {v}" for k, v in sorted(draussen.items()))
        raise SystemExit(
            "[anleitungsbilder] ABBRUCH: Sandbox undicht — diese Pfade liegen "
            f"ausserhalb von {sb.basis}:\n{zeilen}")
    # Qt-Standardpfade zusaetzlich (QSettings, WebEngine-Profil, Caches).
    try:
        from PySide6.QtCore import QStandardPaths as QSP
        for loc in (QSP.StandardLocation.AppDataLocation,
                    QSP.StandardLocation.ConfigLocation,
                    QSP.StandardLocation.CacheLocation,
                    QSP.StandardLocation.GenericDataLocation):
            ort = QSP.writableLocation(loc)
            if ort and not sb.enthaelt(ort):
                raise SystemExit(
                    f"[anleitungsbilder] ABBRUCH: Qt-Pfad ausserhalb der Sandbox: {ort}")
    except ImportError:
        pass
    return pf


def schnappschuss(orte: list[str], tiefe: int = 3) -> dict:
    """{pfad: (mtime_ns, groesse)} fuer alle Dateien bis ``tiefe`` Ebenen."""
    snap: dict = {}
    for ort in orte:
        if not os.path.isdir(ort):
            snap[ort] = None          # Nicht-Existenz festhalten
            continue
        basis_tiefe = ort.rstrip(os.sep).count(os.sep)
        for wurzel, dirs, dateien in os.walk(ort):
            if wurzel.count(os.sep) - basis_tiefe >= tiefe:
                dirs[:] = []
            for d in dateien:
                p = os.path.join(wurzel, d)
                try:
                    st = os.stat(p)
                    snap[p] = (st.st_mtime_ns, st.st_size)
                except OSError:
                    pass
    return snap


# Dateien, die eine GLEICHZEITIG laufende LightOS-Instanz von selbst anfasst
# (main.py: last_alive.txt alle 4 s, Running-Flag, Instanz-Sperre, Autosave,
# crash.log). Nur wenn so eine Instanz laeuft, zaehlen Aenderungen daran nicht
# als Leck des Werkzeugs — sonst wuerde der Abgleich bei offener App flattern.
_LEBENSZEICHEN = ("last_alive.txt", "lightos.instance.lock", "auto_save.lshow",
                  "crash.log")


def laufende_instanz() -> bool:
    """Laeuft auf diesem Rechner gerade eine LightOS-App (``python … main.py``)?"""
    import re
    import subprocess
    try:
        r = subprocess.run(["pgrep", "-af", "main.py"], capture_output=True,
                           text=True, timeout=5)
    except Exception:
        return False
    muster = re.compile(r"python[\w.]*\s+(?:\S*/)?main\.py\b")
    eigen = str(os.getpid())
    return any(muster.search(z) and not z.startswith(eigen + " ")
               for z in r.stdout.splitlines())


def _ist_lebenszeichen(pfad: str) -> bool:
    name = os.path.basename(pfad)
    return name in _LEBENSZEICHEN or (name.startswith("lightos_running_")
                                      and name.endswith(".flag"))


def vergleiche(vorher: dict, nachher: dict, *, app_laeuft: bool = False) -> list[str]:
    """Liste der Aenderungen (leer = unberuehrt)."""
    diff = []
    for p in sorted(set(vorher) | set(nachher)):
        if app_laeuft and _ist_lebenszeichen(p):
            continue
        if vorher.get(p) != nachher.get(p):
            if p not in vorher:
                diff.append(f"neu: {p}")
            elif p not in nachher:
                diff.append(f"weg: {p}")
            else:
                diff.append(f"geaendert: {p}")
    return diff


def _datenbanken_freigeben() -> None:
    """XPLAT-42: alle SQLite-Handles des eigenen Prozesses schliessen.

    Windows loescht keine Datei, die ein Prozess noch offen haelt — Linux
    schon. Ohne das blieben nach jedem Lauf ``arbeit/data/current_show.db``
    (+ ``-wal``/``-shm``) und ``xdg/data/LightOS/fixtures.db`` liegen, und
    ``rmtree(ignore_errors=True)`` verschluckte es. Nur Module, die schon
    geladen sind — das Aufraeumen soll nichts neu importieren.
    """
    import gc
    try:
        from sqlalchemy.orm import close_all_sessions
        close_all_sessions()
    except Exception:
        pass
    st = sys.modules.get("src.core.app_state")
    if st is not None:
        try:
            eng = getattr(st.get_state(), "_show_engine", None)
            if eng is not None:
                eng.dispose()
        except Exception:
            pass
    fdb = sys.modules.get("src.core.database.fixture_db")
    if fdb is not None and getattr(fdb, "_engine", None) is not None:
        try:
            fdb._engine.dispose()
        except Exception:
            pass
        fdb._engine = None
    gc.collect()


def aufraeumen(sb: Sandbox, versuche: int = 5) -> list[str]:
    """Sandbox loeschen; Rueckgabe = Dateien, die trotzdem liegen blieben.

    XPLAT-42: erst die eigenen DB-Handles schliessen, dann loeschen — mit
    kurzen Wiederholungen, weil Windows eine gerade geschlossene Datei
    (Virenscanner, Indexdienst) gelegentlich noch Millisekunden sperrt. Was
    danach noch liegt, meldet der Aufrufer, statt es zu verschlucken.
    """
    import shutil
    import time
    _datenbanken_freigeben()
    for i in range(versuche):
        shutil.rmtree(sb.basis, ignore_errors=True)
        if not os.path.exists(sb.basis):
            return []
        if i + 1 < versuche:
            time.sleep(0.2)
    return sorted(os.path.join(w, f) for w, _d, dateien in os.walk(sb.basis)
                  for f in dateien)


def nebenwirkungen_abschalten() -> None:
    """Monkeypatches fuer alles ohne Env-Schalter. Nach dem src-Import aufrufen,
    VOR dem Bau des MainWindow (der Autoconnect-Timer startet im Konstruktor)."""
    from src.ui import main_window
    main_window.MainWindow._auto_connect_midi = lambda self: None
    try:
        from src.core.midi import midi_manager
        midi_manager.MidiManager.open_all_inputs = lambda self, *a, **k: None
    except Exception:
        pass
    try:
        from src.web import app as web_app

        def _kein_server(*_a, **_k):
            print("[anleitungsbilder] Web-Remote bleibt in der Sandbox aus.")
            return False
        web_app.start_server = _kein_server
    except Exception:
        pass
    # Die Enttec-Anzeige zaehlt sonst die seriellen Ports DIESES Rechners auf —
    # ein eingesteckter Adapter stuende mit Geraetepfad im Bild.
    main_window.MainWindow._enttec_port_gesucht = lambda self: None
    # Kein Auto-Save-Timer: die Sandbox ist ohnehin Wegwerf, aber ein Timer, der
    # mitten in einer Szene speichert, macht die Laufzeit unberechenbar.
    main_window.MainWindow._setup_autosave = lambda self: None
