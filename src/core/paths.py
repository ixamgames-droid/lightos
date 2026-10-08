"""XPLAT-04: Zentrale, plattformabhaengige Aufloesung des App-Datenordners.

Vorher loeste JEDE Fundstelle den Ordner selbst auf — meist
``os.environ.get("APPDATA", expanduser("~"))`` + ``"LightOS"``. Auf Linux/macOS ist
``APPDATA`` nicht gesetzt, also landete ALLES im sichtbaren, nicht-XDG-konformen
``~/LightOS`` (verstopft das Home + kollidiert mit Backup/Sync). Dieser Helfer
zentralisiert die Aufloesung:

* **Windows** (``win32``): unveraendert ``%APPDATA%/LightOS`` — byte-identisch zum
  bisherigen Verhalten (kein Datenumzug auf Windows/WinARM).
* **Linux/BSD**: ``$XDG_DATA_HOME/LightOS`` bzw. ``~/.local/share/LightOS`` (XDG).
* **macOS**: ``~/Library/Application Support/LightOS``.

Importiert NUR ``os`` + ``sys`` -> keine Zyklen; auch von Low-Level-Modulen
(``bpm_cache``, ``fixture_db`` …) sicher importierbar.
"""
from __future__ import annotations
import os
import sys

_APP = "LightOS"


def app_data_dir() -> str:
    """Basis-Verzeichnis fuer LightOS-Nutzerdaten (Show-DB, Snaps, Stages, Caches …).

    Legt das Verzeichnis NICHT an (die Aufrufer tun das je nach Bedarf) und haengt
    KEINE Unterpfade an — dafuer ``os.path.join(app_data_dir(), …)`` verwenden.
    """
    # ueber eine Variable statt direkt ``sys.platform``, sonst wertet Pyright die
    # Zweige host-spezifisch als "unreachable" (statische Plattform-Narrowing).
    plat = sys.platform
    if plat == "win32":
        # ``or`` (nicht get-default): faengt auch ein leer gesetztes APPDATA ab.
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    elif plat == "darwin":
        base = os.path.join(os.path.expanduser("~"), "Library", "Application Support")
    else:  # Linux/BSD & Co. -> XDG
        base = os.environ.get("XDG_DATA_HOME") or os.path.join(
            os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, _APP)


def crash_log_path() -> str:
    """Pfad des gemeinsamen ``crash.log`` — EINE Quelle fuer ``main.py`` und
    ``visualizer_window``. Legt das Verzeichnis an.

    **QA-CRASHLOG-TESTS:** ``LIGHTOS_CRASH_LOG`` biegt die Datei um; ``conftest.py``
    setzt das auf ein tmp-Verzeichnis. Vorher schrieb die Testsuite in die ECHTE
    Absturz-Historie des Nutzers — gemessen 24 Zeilen aus einem einzigen Lauf von
    ``test_a3d_gesture_batch.py -k broken_entry``, weil mehrere Tests absichtlich
    Fehler durch ``_bridge_slot_guard`` schicken. Der Test-Filter des Intakes
    (``collect_crash_report._is_test_frame``) kann das **nicht** auffangen: ein
    Fehler aus einem Bridge-Slot hat ausschliesslich ``src/``-Frames, weil
    ``exc.__traceback__`` erst am ``try`` IM Wrapper beginnt und der aufrufende
    Test-Frame darueber liegt. Deshalb muss die Isolation auf der SCHREIBSEITE
    passieren, nicht beim Auswerten.

    Bewusst NICHT ueber ein umgebogenes ``app_data_dir()`` geloest: das muss im
    Test echt bleiben (``conftest.py`` haengt ``LIGHTOS_FIXTURE_DB`` daran).
    """
    override = os.environ.get("LIGHTOS_CRASH_LOG")
    if override:
        parent = os.path.dirname(override)
        if parent:
            os.makedirs(parent, exist_ok=True)
        return override
    d = app_data_dir()
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "crash.log")


def sacn_cid_path() -> str:
    """Pfad der persistenten sACN-CID (OUT-06) — dieselbe Bauart wie
    ``crash_log_path()``: ``LIGHTOS_SACN_CID`` hat Vorrang, sonst der Datenordner.

    Legt hier bewusst **kein** Verzeichnis an: die CID entsteht lazy und darf einen
    Start nicht mit einem Ordner-Nebeneffekt belasten. Wer schreibt, legt an
    (``src/core/dmx/sacn_cid.py``).

    ``tests/conftest.py`` setzt den Override auf eine PID-eigene tmp-Datei —
    andernfalls fasste jeder Testlauf die echte sACN-Identitaet der Installation an
    (Waechter ``tests/test_app_data_dir.py::test_suite_never_writes_the_real_sacn_cid``).
    """
    override = os.environ.get("LIGHTOS_SACN_CID")
    if override:
        return override
    return os.path.join(app_data_dir(), "sacn_cid")


# ── XPLAT-44: Nutzerdaten, die frueher CWD-relativ unter ``data/`` lagen ──────
#
# Entscheidung des Projektinhabers (2026-10-05): ALLE Nutzerdaten liegen im
# App-Datenordner. Vorher hingen diese fuenf Dateien am ARBEITSVERZEICHNIS
# (``data/…`` relativ zum CWD) — wer LightOS nicht ueber ``start.sh`` /
# ``start.bat`` / ``start.ps1`` startete (Verknuepfung ohne Arbeitsordner,
# ``python <pfad>/main.py`` aus einem anderen Ordner, Paket), bekam ein zweites
# ``data/`` neben dem Aufrufer, und Universen/MIDI/Gruppen wirkten "verschwunden".
#
# Das hier ist die EINE Liste dessen, was Nutzerdaten sind. Was NICHT darin
# steht, bleibt mitgelieferte Repo-Ware und an seinem Ort:
#   * ``data/controller_library/*.json`` (Vorlagen, repo-relativ ueber
#     ``__file__`` aufgeloest, ``controller_library._BUILTIN_DIR``),
#   * ``fixtures/`` (Fixture-Definitionen), ``shows/demo_*.lshow`` (Demos),
#     ``assets/``.
# ``src/core/datenumzug.py`` uebernimmt beim ersten Start genau diese Dateien
# aus einem vorhandenen alten ``data/``.
#: Dateiname -> Override-Umgebungsvariable (``None`` = keine).
USER_DATA_FILES: dict[str, str | None] = {
    "current_show.db": "LIGHTOS_SHOW_DB",
    "universes.json": "LIGHTOS_UNIVERSES_JSON",
    "midi_mappings.json": None,
    "channel_groups.json": None,
    "channel_modifiers.json": None,
}


def user_data_file(name: str) -> str:
    """Pfad einer Nutzerdaten-Datei im App-Datenordner (XPLAT-44).

    Eine gesetzte Override-Variable (``LIGHTOS_SHOW_DB``,
    ``LIGHTOS_UNIVERSES_JSON``) hat Vorrang — dieselbe Bauart wie
    ``crash_log_path()``; Tests und Werkzeuge lenken so auf Wegwerf-Pfade um.

    Legt KEIN Verzeichnis an (wer schreibt, legt an: ``ensure_parent_dir``).
    Unbekannte Namen sind ein Fehler: so kann keine neue Nutzerdatei an der
    Liste (und damit an der Erststart-Uebernahme) vorbei entstehen.
    """
    if name not in USER_DATA_FILES:
        raise ValueError(f"unbekannte Nutzerdaten-Datei: {name!r} "
                         "(in paths.USER_DATA_FILES eintragen)")
    var = USER_DATA_FILES[name]
    if var:
        override = os.environ.get(var)
        if override:
            return override
    return os.path.join(app_data_dir(), name)


def ensure_parent_dir(path: str) -> str:
    """Legt den Elternordner von ``path`` an (falls es einen gibt) und gibt
    ``path`` zurueck — fuer Schreibstellen: ``open(ensure_parent_dir(p), "w")``."""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    return path


# ── XPLAT-47: mitgelieferte (schreibgeschuetzte) Programmdateien ─────────────
#
# Im Quellbetrieb liegen ``assets/``, ``fixtures/``, ``data/controller_library``
# und die Visualizer-Dateien im Repo. Im gefrorenen Windows-Build (PyInstaller,
# onedir, ``packaging/windows/``) liegen sie unter ``sys._MEIPASS`` (dem
# ``_internal``-Ordner neben ``LightOS.exe``) — in derselben relativen Anordnung
# wie im Repo. Der Installationsordner ist dort ``C:\Program Files\LightOS``
# und damit SCHREIBGESCHUETZT: was hierueber aufgeloest wird, wird nur GELESEN.
# Alles Schreibende gehoert in ``app_data_dir()``.


def ist_gefroren() -> bool:
    """True im gepackten Build (PyInstaller setzt ``sys.frozen``)."""
    return bool(getattr(sys, "frozen", False))


def programm_dir() -> str:
    """Wurzel der mitgelieferten Programmdateien (nur lesen!).

    * Quellbetrieb: das Repo (zwei Ebenen ueber ``src/core``).
    * Gefroren: ``sys._MEIPASS`` (PyInstaller); fehlt das, der Ordner der exe.
    """
    if ist_gefroren():
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return os.path.abspath(meipass)
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def programm_datei(*teile: str) -> str:
    """Pfad einer mitgelieferten Datei/eines Ordners unter ``programm_dir()``."""
    return os.path.join(programm_dir(), *teile)
