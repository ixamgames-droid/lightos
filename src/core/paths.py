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
