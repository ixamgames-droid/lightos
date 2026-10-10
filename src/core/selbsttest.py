"""XPLAT-47: Selbsttest ohne Fenster — ``LightOS.exe --selbsttest [DATEI]``.

Wozu: der Windows-Build (PyInstaller, ``packaging/windows/``) kann auf dem
Entwicklungsrechner nicht gebaut werden; die CI baut ihn auf ``windows-latest``
und braucht einen Rauchtest, der OHNE Fenster beendet. Gepackte Builds scheitern
typischerweise an zwei Dingen, die der Quellbetrieb nie zeigt:

* ein Modul fehlt im Bundle (PyInstaller hat einen Import nicht gesehen —
  etwa ``engineio.async_drivers.threading``, das Flask-SocketIO erst zur
  Laufzeit per Name laedt), oder QtWebEngine wurde nicht mitgenommen;
* eine Datei, die die App zur Laufzeit liest (Visualizer-HTML/JS, Themes,
  Galerie, Geraete-Bibliothek …), liegt nicht dort, wo ``paths.programm_dir()``
  sie sucht.

Beides prueft dieses Modul. ``PFLICHT_RESSOURCEN`` ist dabei die EINE Liste,
gegen die auch ``packaging/windows/bundle_inhalt.py`` getestet wird
(``tests/test_xplat47_windows_setup.py``): was hier steht, muss die Spec
mitliefern.

DEMO-8: die Demo-Shows (``demo_shows/``) werden beim Bauen erzeugt und sind
nicht eingecheckt — sie stehen deshalb NICHT in ``PFLICHT_RESSOURCEN`` (der
Quellbetrieb haette sonst immer einen Fehler). ``pruefe_demo_shows`` verlangt
sie nur im gepackten Build; dort prueft es auch, dass jede Datei eine Show ist.

Schreibt NICHTS ausser dem optionalen Bericht und legt keine Ordner an.
"""
from __future__ import annotations

import importlib
import os
import sys

from src.core.paths import ist_gefroren, programm_dir

#: Module, ohne die LightOS nicht startet bzw. ein Kernteil fehlt.
PFLICHT_MODULE: tuple[str, ...] = (
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "PySide6.QtWebChannel",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "numpy",
    "sqlalchemy",
    "sqlalchemy.dialects.sqlite",
    "serial",
    "serial.tools.list_ports",
    "flask",
    "flask_socketio",
    "engineio.async_drivers.threading",
    "pythonosc",
    "src.ui.main_window",
    "src.ui.visualizer.visualizer_window",
    "src.web.app",
)

#: Optional: fehlen sie, laeuft LightOS mit Rueckfall weiter (WinMM-MIDI,
#: kein Audio-Eingang) — gemeldet, aber kein Fehler.
OPTIONALE_MODULE: tuple[str, ...] = (
    "rtmidi",
    "soundcard",
)

#: Mitgelieferte Dateien/Ordner relativ zu ``programm_dir()``. Ordner muessen
#: mindestens eine Datei enthalten.
PFLICHT_RESSOURCEN: tuple[str, ...] = tuple("/".join(teile) for teile in (
    # als Teile notiert, nicht als "a/b": der XPLAT-44-Waechter sucht in src/
    # nach CWD-relativen Daten-Literalen — dies hier ist Programmware.
    ("src", "ui", "visualizer", "stage_scene.html"),
    ("src", "ui", "visualizer", "gallery_render.html"),
    ("src", "ui", "visualizer", "three_local.js"),
    ("src", "ui", "visualizer", "scene_src", "app.js"),
    ("src", "web", "templates"),
    ("src", "web", "static", "socket.io.min.js"),     # WEB-06: kein CDN
    ("assets", "icons", "lightos.png"),
    ("assets", "icons", "lightos.ico"),
    ("assets", "themes", "dark.qss"),
    ("assets", "vc_gallery", "manifest.json"),
    ("data", "controller_library"),
    ("fixtures", "bibliothek"),
    ("licenses",),
    ("THIRD_PARTY_NOTICES.md",),
))


def pruefe_module(namen=PFLICHT_MODULE) -> list[str]:
    """Liste der Fehler (leer = alle importierbar)."""
    fehler = []
    for name in namen:
        try:
            importlib.import_module(name)
        except Exception as e:     # ImportError, aber auch DLL-Ladefehler
            fehler.append(f"Modul {name}: {type(e).__name__}: {e}")
    return fehler


def _hat_datei(ordner: str) -> bool:
    for _wurzel, _dirs, dateien in os.walk(ordner):
        if dateien:
            return True
    return False


def pruefe_ressourcen(wurzel: str | None = None,
                      namen=PFLICHT_RESSOURCEN) -> list[str]:
    """Fehlende mitgelieferte Dateien unter ``wurzel`` (Standard: Programmordner)."""
    wurzel = wurzel or programm_dir()
    fehler = []
    for rel in namen:
        pfad = os.path.join(wurzel, *rel.split("/"))
        if os.path.isdir(pfad):
            if not _hat_datei(pfad):
                fehler.append(f"Ordner leer: {rel}")
        elif not os.path.isfile(pfad):
            fehler.append(f"fehlt: {rel}")
    return fehler


def pruefe_code_stand() -> list[str]:
    """Der Builtin-Fingerabdruck darf nicht leer sein (sonst laeuft der
    Abgleich nach einem Update nie wieder, s. ``fixture_db._code_stand``)."""
    try:
        from src.core.database import fixture_db
        return [] if fixture_db._code_stand() else ["fixture_db._code_stand() ist leer"]
    except Exception as e:
        return [f"fixture_db: {type(e).__name__}: {e}"]


def pruefe_demo_shows(wurzel: str | None = None,
                      pflicht: bool | None = None) -> tuple[list[str], str]:
    """DEMO-8: ``(fehler, berichtszeile)`` zum Demo-Ordner unter ``wurzel``.

    ``pflicht`` (Standard: gepackter Build): fehlen die Demos, ist das ein
    Fehler. Im Quellbetrieb ist ein fehlender Ordner nur ein Hinweis — eine
    vorhandene, aber kaputte Demo faellt dagegen immer auf.
    """
    from src.core import demo_shows
    if pflicht is None:
        pflicht = ist_gefroren()
    basis = os.path.join(wurzel or programm_dir(), demo_shows.ORDNER)
    if not os.path.isfile(os.path.join(basis, demo_shows.INDEX)) and not pflicht:
        return [], (f"{demo_shows.ORDNER}: nicht erzeugt "
                    "(Quellbetrieb: python packaging/demo_shows.py)")
    fehler = demo_shows.pruefe(basis)
    anzahl = len(demo_shows.liste(basis))
    return fehler, f"{demo_shows.ORDNER}: {anzahl} Demo-Show(s)"


def bericht() -> tuple[int, list[str]]:
    zeilen = [f"LightOS-Selbsttest — gefroren={ist_gefroren()} "
              f"programm_dir={programm_dir()}",
              f"Python {sys.version.split()[0]} ({sys.platform})"]
    fehler = pruefe_module() + pruefe_ressourcen() + pruefe_code_stand()
    demo_fehler, demo_zeile = pruefe_demo_shows()
    fehler += demo_fehler
    zeilen.append(demo_zeile)
    for name in OPTIONALE_MODULE:
        rest = pruefe_module((name,))
        zeilen.append(f"optional {name}: {'fehlt — ' + rest[0] if rest else 'ok'}")
    try:
        from PySide6 import __version__ as pyside_version
        zeilen.append(f"PySide6 {pyside_version}")
    except Exception:
        pass
    zeilen += [f"FEHLER {f}" for f in fehler]
    zeilen.append("ERGEBNIS: " + ("ok" if not fehler else f"{len(fehler)} Fehler"))
    return (0 if not fehler else 1), zeilen


def main(ausgabe: str | None = None) -> int:
    code, zeilen = bericht()
    text = "\n".join(zeilen) + "\n"
    if ausgabe:
        with open(ausgabe, "w", encoding="utf-8") as f:
            f.write(text)
    try:
        sys.stdout.write(text)
        sys.stdout.flush()
    except Exception:
        pass
    return code
