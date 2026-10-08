"""XPLAT-47: Was der Windows-Build ausser dem Python-Code mitliefert.

Eine reine Datenliste plus ein Sammler — bewusst OHNE PyInstaller-Import, damit
``tests/test_xplat47_windows_setup.py`` sie auf Linux pruefen kann.
``LightOS.spec`` importiert dieses Modul und reicht ``datas(repo)`` an
``Analysis(datas=…)`` weiter.

Anordnung: jede Datei landet im Bundle (``sys._MEIPASS``, der ``_internal``-
Ordner neben ``LightOS.exe``) unter DEMSELBEN relativen Pfad wie im Repo. Darauf
verlaesst sich ``src.core.paths.programm_datei`` — und die Stellen, die noch
``__file__``-relativ lesen (``visualizer_window.HTML_PATH``,
``src/web/app.py`` templates): PyInstaller setzt ``__file__`` gefrorener Module
auf ``<_MEIPASS>/<paket>/<modul>.py(c)``, ``dirname`` trifft also denselben Ordner.

★ Nur Dateien, die Git kennt (``git ls-files``): ``fixtures/`` und ``data/``
koennen auf einem Entwicklungsrechner private Laufzeitdaten enthalten
(``data/*.db``, ``data/*.json`` sind gitignored). Ein lokaler Build darf die nie
in ein Setup packen. Ohne Git (entpacktes Archiv) faellt der Sammler auf das
Dateisystem zurueck und laesst dabei ``__pycache__`` und ``*.pyc`` weg.
"""
from __future__ import annotations

import os
import subprocess

#: Ordner (relativ zum Repo), die vollstaendig mitkommen.
DATENORDNER: tuple[str, ...] = (
    "assets",                      # Icons, Theme, VC-Galerie, three.js
    "fixtures/bibliothek",         # eigene Geraete-Bibliothek (FM-56)
    "data/controller_library",     # Controller-Vorlagen (NICHT data/ insgesamt!)
    "src/ui/visualizer",           # stage_scene.html, three_local.js, scene_src/
    "src/web/templates",           # Web-Remote
    "examples",                    # Beispielskripte (README verweist darauf)
    "licenses",                    # Lizenztexte der Fremd-Komponenten
)

#: Einzeldateien (relativ zum Repo).
EINZELDATEIEN: tuple[str, ...] = (
    "THIRD_PARTY_NOTICES.md",
    # main.py als DATEI: audio_recorder liest APP_VERSION daraus (Rueckfall
    # ueber ``__main__`` existiert, die Datei ist der Normalweg).
    "main.py",
)

#: Dateiendungen, die nie ins Bundle gehoeren.
_AUSLASSEN_ENDUNGEN = (".pyc", ".pyo")


def _git_dateien(repo: str, rel: str) -> list[str] | None:
    try:
        aus = subprocess.run(["git", "ls-files", "-z", "--", rel], cwd=repo,
                             capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    dateien = [d for d in aus.stdout.decode("utf-8").split("\0") if d]
    return dateien or None


def _walk_dateien(repo: str, rel: str) -> list[str]:
    basis = os.path.join(repo, *rel.split("/"))
    if os.path.isfile(basis):
        return [rel]
    aus = []
    for wurzel, dirs, dateien in os.walk(basis):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for d in dateien:
            pfad = os.path.relpath(os.path.join(wurzel, d), repo)
            aus.append(pfad.replace(os.sep, "/"))
    return sorted(aus)


def dateien(repo: str) -> list[str]:
    """Alle mitzuliefernden Dateien, relativ zum Repo, mit ``/``."""
    aus: list[str] = []
    for rel in DATENORDNER + EINZELDATEIEN:
        liste = _git_dateien(repo, rel)
        if liste is None:
            liste = _walk_dateien(repo, rel)
        aus.extend(d for d in liste if not d.endswith(_AUSLASSEN_ENDUNGEN))
    return sorted(set(aus))


def datas(repo: str) -> list[tuple[str, str]]:
    """``[(quelldatei_absolut, zielordner_im_bundle), …]`` fuer PyInstaller."""
    aus = []
    for rel in dateien(repo):
        quelle = os.path.join(repo, *rel.split("/"))
        if not os.path.isfile(quelle):      # in Git, aber lokal geloescht
            continue
        ziel = os.path.dirname(rel) or "."
        aus.append((quelle, ziel))
    return aus


#: Module, die PyInstaller nicht selbst findet (Laden per Name zur Laufzeit).
HIDDEN_IMPORTS: tuple[str, ...] = (
    # Flask-SocketIO(async_mode="threading") laedt den Treiber per Name.
    "engineio.async_drivers.threading",
    "sqlalchemy.dialects.sqlite",
    "serial.tools.list_ports",
)

#: Grosse, nur optionale Pakete, die nie ins Setup sollen (BPM-Generator-
#: Engines librosa/Beat This!, s. requirements.txt) plus Test-/Tk-Ballast.
EXCLUDES: tuple[str, ...] = (
    "tkinter",
    "torch",
    "librosa",
    "beat_this",
    "numba",
    "llvmlite",
    "pytest",
    "tests",
)
