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
