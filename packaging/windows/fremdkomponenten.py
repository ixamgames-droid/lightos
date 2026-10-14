"""LIZ-2: Fremde Komponenten im Windows-Bundle — die Liste, gegen die gebaut wird.

LightOS selbst ist nicht Open Source; das Windows-Setup liefert aber Python,
Qt/PySide6 (mit QtWebEngine/Chromium und FFmpeg) und rund 35 Python-Pakete mit.
Deren Lizenzen erlauben die Weitergabe, verlangen aber, dass Lizenztext und
Urheberhinweise beiliegen (und die LGPL, dass die Bibliothek austauschbar
bleibt und ihre Quelle genannt ist).

Dieses Modul haelt drei Dinge zusammen:

1. ``PAKETE``, ``QT_BIBLIOTHEKEN``, ``EINGEBETTET`` — was im Bundle liegen DARF,
   mit Lizenz und Bezugsquelle. ``THIRD_PARTY_NOTICES.md`` nennt dasselbe;
   ``tests/test_liz2_fremdlizenzen_setup.py`` vergleicht beide.
2. ``erfasse`` / ``befunde`` — beim Bauen wird JEDE Datei des Bundles ihrer
   Herkunft zugeordnet (ueber die RECORD-Listen der installierten Pakete, nicht
   ueber requirements.txt: dort stehen weder die mittelbaren Abhaengigkeiten
   noch Python, Qt-Plugins oder mitgezogene DLLs). Ein Paket ohne Eintrag, eine
   geaenderte Lizenzangabe, ein fehlender Lizenztext, eine Datei unbekannter
   Herkunft, ein Qt-Modul ohne Eintrag oder eines, das es nur unter der GPL
   gibt: der Bau bricht ab.
3. ``schreibe_lizenzen`` — kopiert die Lizenzdateien der Pakete in der
   installierten Fassung ins Bundle (``licenses/pakete/<Name>-<Version>/``),
   dazu Pythons eigene ``LICENSE.txt``, und schreibt
   ``licenses/BUNDLE-KOMPONENTEN.txt`` mit Name, Version, Lizenz und
   Bezugsquelle jeder Komponente dieses einen Builds. Die Versionen stehen
   bewusst NUR dort: requirements.txt legt sie nicht fest.

Bewusst OHNE PyInstaller-Import (wie ``bundle_inhalt.py``): die Tests laufen
auch auf Linux. ``LightOS.spec`` ruft ``pruefe_und_schreibe`` auf.
"""
from __future__ import annotations

import os
import re
import shutil

# ── Python-Pakete ────────────────────────────────────────────────────────────

#: Lizenz, unter der wir Qt und PySide6 nutzen und weitergeben. Die Pakete
#: selbst nennen die Auswahl „LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only“.
QT_LIZENZ = "LGPL-3.0-only"
_QT_ANGABE = ("LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only",)
_QT_TEXTE = ("LGPL-3.0.txt", "GPL-3.0.txt")
_PYSIDE_QUELLE = "https://download.qt.io/official_releases/QtForPython/pyside6/"

#: Jede Distribution, die im Bundle liegen darf. Schluessel: Paketname in
#: Kleinschreibung mit ``-`` (PEP 503).
#:   lizenz   — wie wir sie ausweisen (SPDX-Schreibweise);
#:   quelle   — Bezugsquelle des Quelltexts;
#:   angaben  — Lizenzangaben der Paket-Metadaten, die dazu passen, wenn sie
#:              anders lauten als ``lizenz`` (s. ``lizenzangabe``);
#:   texte    — Lizenztexte unter ``licenses/``, wenn das Paket selbst keinen
#:              mitbringt (oder nur einen Verweis, wie PySide6).
PAKETE: dict[str, dict] = {
    "bidict": {"lizenz": "MPL-2.0", "quelle": "https://github.com/jab/bidict"},
    "blinker": {"lizenz": "MIT", "quelle": "https://github.com/pallets-eco/blinker",
                "angaben": ("MIT License",)},
    "cffi": {"lizenz": "MIT-0", "quelle": "https://github.com/python-cffi/cffi"},
    "click": {"lizenz": "BSD-3-Clause", "quelle": "https://github.com/pallets/click"},
    # Nicht in jedem Bundle: am Test-Rechner fehlte es, auf dem Runner der
    # Pipeline kam es mit (Farbausgabe fuer click unter Windows) — der Bau der
    # Pipeline brach daran ab, bis dieser Eintrag stand. Genau dafuer ist die
    # Pruefung da.
    "colorama": {"lizenz": "BSD-3-Clause", "quelle": "https://github.com/tartley/colorama",
                 "angaben": ("BSD License",)},
    "flask": {"lizenz": "BSD-3-Clause", "quelle": "https://github.com/pallets/flask"},
    "flask-socketio": {"lizenz": "MIT",
                       "quelle": "https://github.com/miguelgrinberg/Flask-SocketIO",
                       "angaben": ("MIT License",)},
    "h11": {"lizenz": "MIT", "quelle": "https://github.com/python-hyper/h11",
            "angaben": ("MIT License",)},
    "importlib-resources": {"lizenz": "Apache-2.0",
                            "quelle": "https://github.com/python/importlib_resources"},
    "itsdangerous": {"lizenz": "BSD-3-Clause",
                     "quelle": "https://github.com/pallets/itsdangerous",
                     "angaben": ("BSD License",)},
    "jinja2": {"lizenz": "BSD-3-Clause", "quelle": "https://github.com/pallets/jinja",
               "angaben": ("BSD License",)},
    "libusb-package": {"lizenz": "Apache-2.0",
                       "quelle": "https://github.com/pyocd/libusb-package",
                       "angaben": ("Apache Software License",)},
    "markupsafe": {"lizenz": "BSD-3-Clause",
                   "quelle": "https://github.com/pallets/markupsafe"},
    "numpy": {"lizenz": "BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0",
              "quelle": "https://github.com/numpy/numpy"},
    "packaging": {"lizenz": "Apache-2.0 OR BSD-2-Clause",
                  "quelle": "https://github.com/pypa/packaging"},
    "pycparser": {"lizenz": "BSD-3-Clause", "quelle": "https://github.com/eliben/pycparser"},
    "pyinstaller": {"lizenz": "GPL-2.0-or-later WITH Bootloader-exception",
                    "quelle": "https://github.com/pyinstaller/pyinstaller",
                    "angaben": ("GNU General Public License v2 (GPLv2)",)},
    "pyinstaller-hooks-contrib": {
        "lizenz": "Apache-2.0",
        "quelle": "https://github.com/pyinstaller/pyinstaller-hooks-contrib",
        "angaben": ("Apache Software License / GNU General Public License v2 (GPLv2)",)},
    "pyserial": {"lizenz": "BSD-3-Clause", "quelle": "https://github.com/pyserial/pyserial",
                 "angaben": ("BSD License",), "texte": ("BSD-3-Clause-pyserial.txt",)},
    "pyside6-addons": {"lizenz": QT_LIZENZ, "quelle": _PYSIDE_QUELLE,
                       "angaben": _QT_ANGABE, "texte": _QT_TEXTE},
    "pyside6-essentials": {"lizenz": QT_LIZENZ, "quelle": _PYSIDE_QUELLE,
                           "angaben": _QT_ANGABE, "texte": _QT_TEXTE},
    "pyside6-pdf": {"lizenz": QT_LIZENZ, "quelle": _PYSIDE_QUELLE,
                    "angaben": _QT_ANGABE, "texte": _QT_TEXTE},
    "pyside6-webengine": {"lizenz": QT_LIZENZ, "quelle": _PYSIDE_QUELLE,
                          "angaben": _QT_ANGABE, "texte": _QT_TEXTE},
    "python-engineio": {"lizenz": "MIT",
                        "quelle": "https://github.com/miguelgrinberg/python-engineio"},
    "python-osc": {"lizenz": "Unlicense", "quelle": "https://github.com/attwad/python-osc",
                   "angaben": ("Freely Distributable",),
                   "texte": ("Unlicense-python-osc.txt",)},
    "python-rtmidi": {"lizenz": "MIT",
                      "quelle": "https://github.com/SpotlightKid/python-rtmidi",
                      "angaben": ("MIT License",)},
    "python-socketio": {"lizenz": "MIT",
                        "quelle": "https://github.com/miguelgrinberg/python-socketio"},
    "pyusb": {"lizenz": "BSD-3-Clause", "quelle": "https://github.com/pyusb/pyusb",
              "angaben": ("BSD License",)},
    "setuptools": {"lizenz": "MIT", "quelle": "https://github.com/pypa/setuptools"},
    "shiboken6": {"lizenz": QT_LIZENZ, "quelle": _PYSIDE_QUELLE,
                  "angaben": _QT_ANGABE, "texte": _QT_TEXTE},
    "simple-websocket": {"lizenz": "MIT",
                         "quelle": "https://github.com/miguelgrinberg/simple-websocket",
                         "angaben": ("MIT License",)},
    "soundcard": {"lizenz": "BSD-3-Clause", "quelle": "https://github.com/bastibe/SoundCard",
                  "angaben": ("BSD License",)},
    "sqlalchemy": {"lizenz": "MIT", "quelle": "https://github.com/sqlalchemy/sqlalchemy"},
    "typing-extensions": {"lizenz": "PSF-2.0",
                          "quelle": "https://github.com/python/typing_extensions"},
    "werkzeug": {"lizenz": "BSD-3-Clause", "quelle": "https://github.com/pallets/werkzeug"},
    "wsproto": {"lizenz": "MIT", "quelle": "https://github.com/python-hyper/wsproto"},
}

#: Steht in requirements.txt, liegt aber NICHT im Bundle — mit Grund. Ein neuer
#: Eintrag in requirements.txt muss hier oder in ``PAKETE`` auftauchen.
NICHT_IM_BUNDLE: dict[str, str] = {
    "pyside6": "Sammelpaket ohne eigene Dateien im Bundle; seine Teile stehen "
               "einzeln in PAKETE (pyside6-essentials, pyside6-addons, shiboken6 …)",
}

# ── Qt ───────────────────────────────────────────────────────────────────────

#: Qt-Bibliotheken, die im Bundle liegen duerfen: Dateiname ohne ``Qt6`` und
#: ``.dll`` -> Modul laut Qt-Dokumentation. Alle gibt es unter der LGPLv3
#: (Lizenz-Abschnitte der Modulseiten, Qt 6.12). Was ``qt_umfang.auswahl``
#: uebrig laesst, muss hier stehen.
QT_BIBLIOTHEKEN: dict[str, str] = {
    "Core": "Qt Core",
    "Gui": "Qt GUI",
    "Widgets": "Qt Widgets",
    "Network": "Qt Network",
    "OpenGL": "Qt OpenGL",
    "PrintSupport": "Qt Print Support",
    "Multimedia": "Qt Multimedia",
    "MultimediaWidgets": "Qt Multimedia",
    "Pdf": "Qt PDF",
    "Positioning": "Qt Positioning",
    "Qml": "Qt Qml",
    "QmlMeta": "Qt Qml",
    "QmlModels": "Qt Qml",
    "QmlWorkerScript": "Qt Qml",
    "Quick": "Qt Quick",
    "QuickWidgets": "Qt Quick Widgets",
    "SerialPort": "Qt Serial Port",
    "Svg": "Qt SVG",
    "WebChannel": "Qt WebChannel",
    "WebEngineCore": "Qt WebEngine",
    "WebEngineWidgets": "Qt WebEngine",
}

#: Qt-Module, die es in der Open-Source-Ausgabe NICHT unter der LGPL gibt,
#: sondern nur unter der GPLv3 (Qt-Dokumentation 6.12, „Qt Licensing“:
#: „Modules available under GNU General Public License v3“, dazu die Seiten von
#: Qt Charts und Qt Data Visualization). Namensanfang der Bibliothek ohne
#: ``Qt6`` -> Modul. Keine Datei davon darf ins Bundle.
QT_NUR_GPL: dict[str, str] = {
    "CanvasPainter": "Qt Canvas Painter",
    "Charts": "Qt Charts",
    "Coap": "Qt CoAP",
    "DataVisualization": "Qt Data Visualization",
    "Graphs": "Qt Graphs",
    "Grpc": "Qt GRPC",
    "HttpServer": "Qt HTTP Server",
    "Lottie": "Qt Lottie Animation",
    "Mqtt": "Qt MQTT",
    "NetworkAuth": "Qt Network Authorization",
    "QmlCompiler": "Qt Qml Compiler",
    "Quick3D": "Qt Quick 3D",
    "QuickTimeline": "Qt Quick Timeline",
    "VirtualKeyboard": "Qt Virtual Keyboard",
    "WaylandCompositor": "Qt Wayland Compositor",
}

#: Plugin-Ordner unter ``PySide6/plugins/``, die im Bundle liegen duerfen.
QT_PLUGIN_ORDNER: dict[str, str] = {
    "generic": "Qt GUI",
    "iconengines": "Qt SVG",
    "imageformats": "Qt GUI, Qt Image Formats, Qt SVG, Qt PDF",
    "multimedia": "Qt Multimedia",
    "networkinformation": "Qt Network",
    "platforms": "Qt GUI",
    "position": "Qt Positioning",
    "styles": "Qt Widgets",
    "tls": "Qt Network",
}

# ── Eingebettet: fremde Bibliotheken INNERHALB der Pakete und von Python ─────

#: (Name, Lizenz, Bezugsquelle, Muster auf den Zielpfad im Bundle — klein, mit
#: ``/``). Erkannt an den Dateien; eine Binaerdatei direkt unter ``PySide6/``,
#: die weder Qt-Bibliothek noch PySide6 selbst ist, muss auf eines der Muster
#: passen.
EINGEBETTET: tuple[tuple[str, str, str, str], ...] = (
    ("FFmpeg", "LGPL-2.1-or-later", "https://ffmpeg.org/download.html",
     r"^pyside6/(avcodec|avformat|avutil|swresample|swscale)-\d+\.dll$"),
    ("Mesa llvmpipe (opengl32sw.dll)", "MIT",
     "https://download.qt.io/development_releases/prebuilt/llvmpipe/windows/",
     r"^pyside6/opengl32sw\.dll$"),
    ("OpenBLAS (in numpy)", "BSD-3-Clause", "https://github.com/OpenMathLib/OpenBLAS",
     r"^numpy\.libs/libscipy_openblas[\w-]*\.dll$"),
    ("libusb", "LGPL-2.1-or-later", "https://github.com/libusb/libusb",
     r"(^|/)libusb-1\.0\.dll$"),
    ("OpenSSL (in Python)", "Apache-2.0", "https://www.openssl.org/source/",
     r"^lib(crypto|ssl)-3\.dll$"),
    ("libffi (in Python)", "MIT", "https://github.com/libffi/libffi",
     r"^libffi-\d+\.dll$"),
    ("SQLite (in Python)", "Public Domain", "https://www.sqlite.org/download.html",
     r"^sqlite3\.dll$"),
    ("Microsoft Visual C++ Laufzeit", "Microsoft (nicht Open Source)",
     "https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist",
     r"(^|/)(msvcp|vcruntime|concrt|vccorlib|vcomp)\d+[\w-]*\.dll$"),
)

#: Lizenztext unter ``licenses/`` zu einer eingebetteten Bibliothek, wenn sie
#: selbst keinen mitbringt (Erzeugung: ``fremdlizenzen_sammeln.py``).
EINGEBETTET_TEXTE: dict[str, str] = {
    "Mesa llvmpipe (opengl32sw.dll)": "Mesa-opengl32sw.txt",
}

#: LIZ-2 (Rest): Teile aus den PySide6-Paketen, deren Fremdlizenzen die Pakete
#: NICHT mitbringen. Zielpfad im Bundle (klein, ``/``) -> (Sammeldatei unter
#: ``licenses/``, Kopfzeile darin mit der Version, Art der Versionsermittlung).
#: Die Sammeldatei beschreibt genau EINE Version; liegt eine andere im Bundle,
#: bricht der Bau ab — dann ``fremdlizenzen_sammeln.py`` neu laufen lassen.
SAMMELDATEIEN: dict[str, tuple[str, str, str]] = {
    "pyside6/qt6webenginecore.dll": ("QtWebEngine-THIRD-PARTY.txt",
                                     "Qt-WebEngine-Version:", "pe"),
    "pyside6/opengl32sw.dll": ("Mesa-opengl32sw.txt", "Mesa-Version:", "mesa"),
}

#: Gehoert zu Windows 10/11 und darf NICHT ins Bundle (``qt_umfang`` laesst es
#: weg): die Universal C Runtime. PyInstaller sammelte sie aus dem PATH des
#: Bau-Rechners ein.
WINDOWS_EIGEN = r"^(api-ms-win-[\w-]+|ucrtbase)\.dll$"

#: Python selbst: Lizenz, Bezugsquelle; den Text kopiert der Bau aus der
#: Installation (``LICENSE.txt`` — enthaelt auch die Hinweise zu bzip2, libffi,
#: OpenSSL, SQLite, zlib … des Windows-Builds).
PYTHON = {"lizenz": "PSF-2.0", "quelle": "https://www.python.org/downloads/source/"}
PYTHON_LIZENZDATEI = "LICENSE.txt"

#: Namen der Lizenzdateien, die aus den Paketen mitkommen.
_LIZENZDATEI = re.compile(r"(?i)^(licen[cs]e|copying|notice|authors|copyright)")

#: Wohin im Bundle (relativ, ``/``).
ORDNER = "licenses"
ORDNER_PAKETE = "licenses/pakete"
LISTE = "licenses/BUNDLE-KOMPONENTEN.txt"
PYTHON_ZIEL = "licenses/Python-LICENSE.txt"


def normal(name: str) -> str:
    """Paketname in der Schreibweise der Tabelle (PEP 503)."""
    return re.sub(r"[-_.]+", "-", str(name)).lower()


def lizenzangabe(meta) -> str:
    """Was die Metadaten eines Pakets zur Lizenz sagen — EINE Zeichenkette.

    Reihenfolge: ``License-Expression`` (neu, eindeutig), sonst die
    ``License ::``-Klassifizierer (mit `` / `` verbunden), sonst die erste
    Zeile von ``License``. ``meta`` braucht ``get`` und ``get_all``.
    """
    ausdruck = (meta.get("License-Expression") or "").strip()
    if ausdruck:
        return ausdruck
    klass = [c.split("::")[-1].strip() for c in (meta.get_all("Classifier") or [])
             if c.startswith("License ::")]
    if klass:
        return " / ".join(klass)
    zeilen = (meta.get("License") or "").strip().splitlines()
    return zeilen[0].strip() if zeilen else ""


def angabe_passt(angabe: str, eintrag: dict) -> bool:
    """Passt die Lizenzangabe der Metadaten zum Eintrag der Tabelle?"""
    a = (angabe or "").strip().lower()
    erlaubt = {eintrag["lizenz"].lower()} | {x.lower() for x in eintrag.get("angaben", ())}
    return a in erlaubt


def ist_lizenzdatei(rel: str) -> bool:
    """Lizenzdatei eines Pakets: liegt in seinem ``.dist-info`` (auch in dem
    eines mitgelieferten Unterpakets, z. B. unter ``setuptools/_vendor``) und
    heisst wie eine."""
    rel = str(rel).replace("\\", "/")
    if ".dist-info/" not in rel:
        return False
    # PEP 639: was unter <paket>.dist-info/licenses/ liegt, IST eine Lizenzdatei
    # — auch ``dragon4_LICENSE.txt`` (numpy). Aeltere Pakete legen sie direkt
    # ins dist-info; dort entscheidet der Name.
    if ".dist-info/licenses/" in rel:
        return True
    return bool(_LIZENZDATEI.match(rel.rsplit("/", 1)[-1]))


def qt_stamm(ziel: str) -> str | None:
    """``PySide6/Qt6WebEngineCore.dll`` -> ``WebEngineCore``; sonst ``None``."""
    ziel = ziel.replace("\\", "/")
    kopf, _, name = ziel.rpartition("/")
    if kopf.lower() != "pyside6":
        return None
    m = re.match(r"(?i)^qt6(.+)\.dll$", name)
    return m.group(1) if m else None


def nur_gpl_modul(stamm: str) -> str | None:
    """Name des Nur-GPL-Moduls, zu dem die Bibliothek gehoert — sonst ``None``."""
    for anfang in sorted(QT_NUR_GPL, key=len, reverse=True):
        if stamm.lower().startswith(anfang.lower()):
            return QT_NUR_GPL[anfang]
    return None


def eingebettet(ziel: str) -> str | None:
    """Name der eingebetteten Fremdbibliothek, zu der die Datei gehoert."""
    klein = ziel.replace("\\", "/").lower()
    for name, _lizenz, _quelle, muster in EINGEBETTET:
        if re.search(muster, klein):
            return name
    return None


# ── Erfassen ─────────────────────────────────────────────────────────────────

def _unter(pfad: str, ordner: str | None) -> bool:
    if not ordner:
        return False
    pfad = os.path.normcase(os.path.abspath(pfad))
    ordner = os.path.normcase(os.path.abspath(ordner))
    return pfad == ordner or pfad.startswith(ordner.rstrip("\\/") + os.sep)


def erfasse(eintraege, besitzer, python_basis=None, eigene=()):
    """Ordnet jede Datei des Bundles ihrer Herkunft zu.

    ``eintraege``: ``(ziel, quelle, typ)`` aus dem PyInstaller-Lauf;
    ``besitzer``: ``{normierter Quellpfad: Paketname}`` (s. ``besitzer_karte``);
    ``python_basis``: Ordner der Python-Installation (``sys.base_prefix``);
    ``eigene``: Ordner, deren Dateien LightOS selbst gehoeren oder beim Bauen
    entstehen (Repo, Arbeitsordner von PyInstaller).

    Rueckgabe: Woerterbuch mit
      ``pakete``      {Paketname (normal): [Zielpfade]},
      ``python``      [Zielpfade] aus der Python-Installation,
      ``eingebettet`` {Name: [Zielpfade]},
      ``ohne``        [(ziel, quelle)] — Herkunft unbekannt.
    """
    pakete: dict[str, list[str]] = {}
    python: list[str] = []
    drin: dict[str, list[str]] = {}
    ohne: list[tuple[str, str]] = []
    for eintrag in eintraege:
        ziel, quelle = str(eintrag[0]).replace("\\", "/"), eintrag[1]
        if not quelle or quelle == "-":      # „-“: Namensraum-Paket ohne Datei
            continue
        teil = eingebettet(ziel)
        if teil:
            drin.setdefault(teil, []).append(ziel)
        schluessel = os.path.normcase(os.path.abspath(quelle))
        if schluessel in besitzer:
            pakete.setdefault(normal(besitzer[schluessel]), []).append(ziel)
        elif any(_unter(quelle, o) for o in eigene):
            pass
        elif _unter(quelle, python_basis):
            python.append(ziel)
        else:
            # Auch eine Datei, die wie eine bekannte Bibliothek HEISST: kommt
            # sie von irgendwo auf dem Bau-Rechner, ist ihre Herkunft unbekannt.
            ohne.append((ziel, quelle))
    return {"pakete": pakete, "python": python, "eingebettet": drin, "ohne": ohne}


def qt_befunde(ziele) -> list[str]:
    """Was an den Qt-Dateien im Bundle nicht stimmt (``ziele``: alle Zielpfade)."""
    aus: list[str] = []
    for ziel in sorted({str(z).replace("\\", "/") for z in ziele}):
        klein = ziel.lower()
        if not klein.startswith("pyside6/"):
            continue
        stamm = qt_stamm(ziel)
        if stamm is not None:
            modul = nur_gpl_modul(stamm)
            if modul:
                aus.append(f"{ziel}: {modul} gibt es nur unter der GPLv3, nicht "
                           "unter der LGPL — darf nicht ins Setup")
            elif stamm not in QT_BIBLIOTHEKEN:
                aus.append(f"{ziel}: Qt-Bibliothek ohne Eintrag in "
                           "fremdkomponenten.QT_BIBLIOTHEKEN — Lizenz des Moduls "
                           "klaeren, eintragen und in THIRD_PARTY_NOTICES.md nennen")
            continue
        if klein.startswith("pyside6/qml/"):
            aus.append(f"{ziel}: QML-Modul im Bundle — LightOS laedt kein QML, "
                       "der Ordner soll entfallen (qt_umfang.py)")
            continue
        if klein.startswith("pyside6/plugins/"):
            teile = ziel.split("/")
            art = teile[2] if len(teile) > 3 else ""
            if "virtualkeyboard" in klein:
                aus.append(f"{ziel}: Qt Virtual Keyboard gibt es nur unter der "
                           "GPLv3 — darf nicht ins Setup")
            elif art not in QT_PLUGIN_ORDNER:
                aus.append(f"{ziel}: Qt-Plugin-Ordner „{art}“ ohne Eintrag in "
                           "fremdkomponenten.QT_PLUGIN_ORDNER")
            continue
        if ziel.count("/") == 1 and klein.endswith((".dll", ".exe")):
            name = klein.rsplit("/", 1)[-1]
            if (name.startswith("pyside6") or name == "qtwebengineprocess.exe"
                    or eingebettet(ziel)):
                continue
            aus.append(f"{ziel}: Binaerdatei unbekannter Herkunft unter PySide6/ — "
                       "in fremdkomponenten.EINGEBETTET eintragen oder entfernen")
    return aus


def texte_im_bundle(ziele) -> set[str]:
    """Namen der Lizenztexte, die direkt unter ``licenses/`` im Bundle liegen."""
    aus = set()
    for ziel in ziele:
        teile = str(ziel).replace("\\", "/").split("/")
        if len(teile) == 2 and teile[0].lower() == ORDNER:
            aus.add(teile[1])
    return aus


def befunde(erfasst: dict, pakete_info: dict, texte,
            python_lizenz: str | None = None) -> list[str]:
    """Alles, was zwischen Bundle und Tabelle nicht stimmt — leer = in Ordnung.

    ``pakete_info``: ``{Paketname (normal): {"name", "version", "angabe",
    "lizenzdateien": [(rel, absolut)]}}``; ``texte``: Namen der Lizenztexte, die
    unter ``licenses/`` INS BUNDLE kommen (nicht: die im Repo liegen — eine
    Datei, die Git nicht kennt, packt ``bundle_inhalt`` nicht ein);
    ``python_lizenz``: Pfad zu Pythons ``LICENSE.txt`` (oder ``None``).
    """
    texte = set(texte)
    aus: list[str] = []
    for name in sorted(erfasst["pakete"]):
        info = pakete_info.get(name, {})
        anzeige = f"{info.get('name', name)} {info.get('version', '?')}"
        eintrag = PAKETE.get(name)
        if eintrag is None:
            aus.append(f"{anzeige}: liegt im Bundle ({len(erfasst['pakete'][name])} "
                       "Dateien), steht aber nicht in fremdkomponenten.PAKETE — "
                       "Lizenz klaeren, eintragen und in THIRD_PARTY_NOTICES.md nennen")
            continue
        if not angabe_passt(info.get("angabe", ""), eintrag):
            aus.append(f"{anzeige}: das Paket nennt als Lizenz „{info.get('angabe', '')}“, "
                       f"eingetragen ist „{eintrag['lizenz']}“ — pruefen, ob sich die "
                       "Lizenz geaendert hat, dann Tabelle und Hinweise anpassen")
        for t in eintrag.get("texte", ()):
            if t not in texte:
                aus.append(f"{anzeige}: Lizenztext licenses/{t} kommt nicht ins "
                           "Bundle (fehlt im Repo oder ist Git nicht bekannt)")
        if not eintrag.get("texte") and not info.get("lizenzdateien"):
            aus.append(f"{anzeige}: das Paket bringt keinen Lizenztext mit und die "
                       "Tabelle nennt keinen unter licenses/ — Text aus der "
                       "Originalquelle ablegen und unter „texte“ eintragen")
    if erfasst["python"] and not (python_lizenz and os.path.isfile(python_lizenz)):
        aus.append("Python: LICENSE.txt der Python-Installation nicht gefunden — "
                   "ohne sie fehlt dem Setup der Lizenztext von Python")
    for ziel, quelle in sorted(erfasst["ohne"]):
        aus.append(f"{ziel}: Herkunft unbekannt (kommt von {quelle}) — gehoert zu "
                   "keinem installierten Paket, nicht zu Python und nicht zum Repo; "
                   "das Setup darf nichts Zufaelliges vom Bau-Rechner enthalten")
    return aus


def pe_dateiversion(daten: bytes) -> str | None:
    """Dateiversion ``a.b.c`` aus der Versionsressource einer Windows-DLL
    (``VS_FIXEDFILEINFO``, erkannt an ihrer Signatur ``0xFEEF04BD``)."""
    i = daten.find(b"\xbd\x04\xef\xfe")
    if i < 0 or len(daten) < i + 16:
        return None
    ms, ls = int.from_bytes(daten[i + 8:i + 12], "little"), \
        int.from_bytes(daten[i + 12:i + 16], "little")
    return f"{ms >> 16}.{ms & 0xFFFF}.{ls >> 16}"


def mesa_version(daten: bytes) -> str | None:
    """Mesa-Version, mit der sich ``opengl32sw.dll`` selbst ausweist."""
    m = re.search(rb"Mesa (\d+\.\d+\.\d+)", daten)
    return m.group(1).decode("ascii") if m else None


def _kopf_wert(text: str, kopf: str) -> str | None:
    for zeile in text.splitlines()[:40]:
        if zeile.startswith(kopf):
            return zeile[len(kopf):].strip()
    return None


def sammeldatei_befunde(eintraege, lizenz_ordner: str, texte) -> list[str]:
    """Liegt zu Qt WebEngine und Mesa die Sammeldatei bei — fuer genau die
    Version im Bundle? ``eintraege``: ``(ziel, quelle, …)``; ``lizenz_ordner``:
    ``licenses/`` im Repo; ``texte``: Namen der Texte, die ins Bundle kommen."""
    texte = set(texte)
    aus: list[str] = []
    for eintrag in eintraege:
        ziel = str(eintrag[0]).replace("\\", "/").lower()
        if ziel not in SAMMELDATEIEN:
            continue
        datei, kopf, art = SAMMELDATEIEN[ziel]
        wie = ("python packaging/windows/fremdlizenzen_sammeln.py "
               + ("webengine" if art == "pe" else "mesa"))
        if datei not in texte:
            aus.append(f"{eintrag[0]}: Sammeldatei licenses/{datei} kommt nicht ins "
                       f"Bundle (fehlt im Repo oder ist Git nicht bekannt) — {wie}")
            continue
        try:
            with open(os.path.join(lizenz_ordner, datei), encoding="utf-8") as f:
                soll = _kopf_wert(f.read(), kopf)
            with open(eintrag[1], "rb") as f:
                daten = f.read()
        except OSError as e:
            aus.append(f"{eintrag[0]}: {type(e).__name__}: {e}")
            continue
        ist = pe_dateiversion(daten) if art == "pe" else mesa_version(daten)
        if ist is None or soll is None or ist != soll:
            aus.append(f"{eintrag[0]}: Version im Bundle „{ist}“, licenses/{datei} "
                       f"beschreibt „{soll}“ — Sammeldatei neu erzeugen ({wie}) "
                       "und einchecken")
    return aus


def windows_eigene(ziele) -> list[str]:
    """Dateien im Bundle, die zu Windows selbst gehoeren (Universal C Runtime)."""
    return [f"{z}: gehoert zu Windows 10/11 und soll nicht ins Setup "
            "(qt_umfang.ENTFAELLT_DATEIEN)"
            for z in sorted({str(z).replace("\\", "/") for z in ziele})
            if re.search(WINDOWS_EIGEN, z.lower())]


# ── Schreiben ────────────────────────────────────────────────────────────────

def _quelle_mit_version(name: str, version: str, quelle: str) -> str:
    return f"{quelle}  (bezogen ueber https://pypi.org/project/{name}/{version}/)"


def liste_text(erfasst: dict, pakete_info: dict, python_version: str,
               qt_dateien=()) -> str:
    """Inhalt von ``BUNDLE-KOMPONENTEN.txt`` — die Liste DIESES Builds."""
    z = ["Fremde Komponenten in diesem LightOS-Installationspaket",
         "=======================================================",
         "",
         "Erzeugt beim Bauen aus dem Inhalt des Pakets (nicht von Hand gepflegt).",
         "Erklaerungen, Pflichten und Urheberhinweise: THIRD_PARTY_NOTICES.md.",
         "Lizenztexte: dieser Ordner; die der Python-Pakete unter pakete/.",
         "",
         "Python",
         "------",
         f"Python {python_version} | {PYTHON['lizenz']} | {PYTHON['quelle']}",
         "  Lizenztext: Python-LICENSE.txt (mit den Hinweisen zu den im "
         "Windows-Build enthaltenen Bibliotheken)",
         "",
         "Python-Pakete",
         "-------------"]
    for name in sorted(erfasst["pakete"]):
        info = pakete_info.get(name, {})
        eintrag = PAKETE.get(name, {})
        anzeige, version = info.get("name", name), info.get("version", "?")
        z.append(f"{anzeige} {version} | {eintrag.get('lizenz', '?')} | "
                 + _quelle_mit_version(anzeige, version, eintrag.get("quelle", "?")))
        texte = [f"pakete/{anzeige}-{version}/"] if info.get("lizenzdateien") else []
        texte += list(eintrag.get("texte", ()))
        z.append("  Lizenztext: " + ", ".join(texte))
    staemme = sorted({s for s in (qt_stamm(d) for d in qt_dateien) if s})
    if staemme:
        z += ["", "Qt-Bibliotheken (aus den PySide6-Paketen)",
              "------------------------------------------",
              f"Lizenz: {QT_LIZENZ} (LGPL-3.0.txt, GPL-3.0.txt). Jede liegt als "
              "eigene Datei unter _internal/PySide6/ und ist austauschbar."]
        for s in staemme:
            z.append(f"Qt6{s}.dll | {QT_BIBLIOTHEKEN.get(s, '?')}")
        if "WebEngineCore" in staemme:
            z.append("  Chromium und die Fremdbibliotheken in Qt WebEngine: "
                     + SAMMELDATEIEN["pyside6/qt6webenginecore.dll"][0])
    if erfasst["eingebettet"]:
        z += ["", "In den Paketen bzw. in Python enthaltene Bibliotheken",
              "-----------------------------------------------------"]
        tabelle = {n: (l, q) for n, l, q, _m in EINGEBETTET}
        for name in sorted(erfasst["eingebettet"]):
            lizenz, quelle = tabelle[name]
            dateien = sorted({d.rsplit("/", 1)[-1] for d in erfasst["eingebettet"][name]})
            kurz = ", ".join(dateien[:6]) + (" …" if len(dateien) > 6 else "")
            z.append(f"{name} | {lizenz} | {quelle}")
            z.append(f"  Dateien: {kurz}")
            if name in EINGEBETTET_TEXTE:
                z.append(f"  Lizenztext: {EINGEBETTET_TEXTE[name]}")
    return "\n".join(z) + "\n"


def schreibe_lizenzen(arbeitsordner: str, erfasst: dict, pakete_info: dict,
                      python_lizenz: str | None, python_version: str,
                      qt_dateien=()) -> list[tuple[str, str]]:
    """Legt die erzeugten Lizenzdateien in ``arbeitsordner`` ab und liefert
    ``[(quelle_absolut, zielordner_im_bundle), …]`` fuer PyInstaller."""
    if os.path.isdir(arbeitsordner):
        shutil.rmtree(arbeitsordner)
    aus: list[tuple[str, str]] = []

    def ablegen(rel: str, schreiben) -> None:
        pfad = os.path.join(arbeitsordner, *rel.split("/"))
        os.makedirs(os.path.dirname(pfad), exist_ok=True)
        schreiben(pfad)
        aus.append((pfad, os.path.dirname(rel)))

    for name in sorted(erfasst["pakete"]):
        info = pakete_info.get(name, {})
        ordner = f"{ORDNER_PAKETE}/{info.get('name', name)}-{info.get('version', '0')}"
        for rel, absolut in info.get("lizenzdateien", ()):
            # Pfad ab dem dist-info-Ordner; bei mitgelieferten Unterpaketen
            # (setuptools/_vendor/x.dist-info/LICENSE) bleibt deren Name stehen.
            teile = rel.replace("\\", "/").split("/")
            i = max(k for k, t in enumerate(teile) if t.endswith(".dist-info"))
            stamm = teile[i][:-len(".dist-info")].rsplit("-", 1)[0]
            eigen = normal(stamm) == name and i == 0
            unter = "/".join(teile[i + 1:] if eigen else teile[i:])
            unter = re.sub(r"^licenses/", "", unter)
            ablegen(f"{ordner}/{unter}", lambda p, a=absolut: shutil.copyfile(a, p))
    if erfasst["python"] and python_lizenz and os.path.isfile(python_lizenz):
        ablegen(PYTHON_ZIEL, lambda p: shutil.copyfile(python_lizenz, p))
    text = liste_text(erfasst, pakete_info, python_version, qt_dateien)

    def liste_schreiben(pfad: str) -> None:
        with open(pfad, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)

    ablegen(LISTE, liste_schreiben)
    return aus


# ── Die Stelle fuer LightOS.spec ─────────────────────────────────────────────

def besitzer_karte():
    """``({Quellpfad: Paketname}, {Paketname (normal): info})`` aus den
    installierten Paketen des Bau-Rechners (``importlib.metadata``)."""
    import importlib.metadata as md
    karte: dict[str, str] = {}
    info: dict[str, dict] = {}
    for d in md.distributions():
        name = d.metadata["Name"]
        if not name:
            continue
        lizenzdateien = []
        for f in d.files or []:
            try:
                absolut = os.path.abspath(str(d.locate_file(f)))
            except Exception:  # noqa: BLE001
                continue
            karte[os.path.normcase(absolut)] = name
            rel = str(f).replace("\\", "/")
            if ist_lizenzdatei(rel) and os.path.isfile(absolut):
                lizenzdateien.append((rel, absolut))
        info[normal(name)] = {"name": name, "version": d.version,
                              "angabe": lizenzangabe(d.metadata),
                              "lizenzdateien": sorted(lizenzdateien)}
    return karte, info


def pruefe_und_schreibe(eintraege, repo: str, arbeitsordner: str,
                        eigene=(), python_basis: str | None = None):
    """Fuer ``LightOS.spec``: prueft das Bundle gegen die Tabelle und legt die
    Lizenzdateien an.

    Rueckgabe ``(datas, befunde)``. Bei Befunden ist ``datas`` leer — der
    Aufrufer bricht den Bau ab.
    """
    import platform
    import sys
    eintraege = list(eintraege)
    python_basis = python_basis or sys.base_prefix
    karte, info = besitzer_karte()
    erfasst = erfasse(eintraege, karte, python_basis=python_basis,
                      eigene=(repo,) + tuple(eigene))
    # Der Startlader (LightOS.exe) stammt aus PyInstaller und steht in keiner
    # der Listen — PyInstaller gehoert deshalb immer dazu.
    erfasst["pakete"].setdefault("pyinstaller", [])
    python_lizenz = os.path.join(python_basis, PYTHON_LIZENZDATEI)
    ziele = [str(e[0]) for e in eintraege]
    gefunden = befunde(erfasst, info, texte_im_bundle(ziele), python_lizenz)
    gefunden += qt_befunde(ziele) + windows_eigene(ziele)
    gefunden += sammeldatei_befunde(eintraege, os.path.join(repo, ORDNER),
                                    texte_im_bundle(ziele))
    if gefunden:
        return [], gefunden
    datas = schreibe_lizenzen(arbeitsordner, erfasst, info, python_lizenz,
                              platform.python_version(), qt_dateien=ziele)
    return datas, []


def tabelle_markdown() -> str:
    """Die Paket-Tabelle fuer ``THIRD_PARTY_NOTICES.md`` (zum Einfuegen)."""
    z = ["| Paket | Lizenz | Bezugsquelle |", "|---|---|---|"]
    for name in sorted(PAKETE):
        z.append(f"| {name} | {PAKETE[name]['lizenz']} | <{PAKETE[name]['quelle']}> |")
    return "\n".join(z)


if __name__ == "__main__":
    print(tabelle_markdown())
