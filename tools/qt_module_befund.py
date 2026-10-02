"""XPLAT-45: welche Qt-Module bringt das installierte PySide6 mit?

Anlass: auf Windows-ARM64 enthalten die nativen ``win_arm64``-Wheels von
PySide6-Addons KEIN QtWebEngine (gemessen an 6.11.2 auf dem CI-Runner
``windows-11-arm``) - damit fehlt der 3D-Visualizer. Der Rig-PC (Snapdragon)
laeuft deshalb mit x64-Python unter Emulation. Die CI faehrt dieses Werkzeug
in beiden Konfigurationen und schreibt den Befund ins Log:

    python tools/qt_module_befund.py                      Befund, Exit 0
    python tools/qt_module_befund.py --erwarte-webengine  Exit 1 ohne QtWebEngine

Bringt ein natives ARM64-Wheel eines Tages QtWebEngine mit, meldet das
Werkzeug es ausdruecklich - dann sind XPLAT-45/XPLAT-46 neu zu bewerten.
"""
from __future__ import annotations

import argparse
import importlib
import platform
import sys
import sysconfig

MODULE = (
    "QtCore", "QtGui", "QtWidgets", "QtOpenGL", "QtOpenGLWidgets", "QtSvg",
    "QtMultimedia", "QtWebChannel", "QtWebEngineCore", "QtWebEngineWidgets",
)
WEBENGINE = "QtWebEngineWidgets"


def interpreter_arch() -> str:
    """'arm64' / 'x64' / … des INTERPRETERS - auch unter Emulation richtig
    (``platform.machine()`` meldet auf emuliertem x64-Python teils 'ARM64')."""
    p = sysconfig.get_platform().lower()
    if p.endswith("arm64") or p.endswith("aarch64"):
        return "arm64"
    if p.endswith("amd64") or p.endswith("x86_64"):
        return "x64"
    return p


def befund(importer=importlib.import_module) -> dict[str, str | None]:
    """``{Modul: None (laedt) | Fehlertext}`` fuer jedes Modul aus ``MODULE``."""
    ergebnis: dict[str, str | None] = {}
    for name in MODULE:
        try:
            importer(f"PySide6.{name}")
            ergebnis[name] = None
        except Exception as e:   # ImportError, aber auch DLL-Ladefehler
            ergebnis[name] = f"{type(e).__name__}: {e}"
    return ergebnis


def main(argv=None, importer=importlib.import_module) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--erwarte-webengine", action="store_true",
                    help="Exit 1, wenn QtWebEngineWidgets nicht laedt")
    args = ap.parse_args(argv)
    try:
        version = importer("PySide6").__version__
    except Exception as e:
        print(f"[qt-befund] PySide6 laedt nicht: {e}")
        return 1
    arch = interpreter_arch()
    print(f"[qt-befund] Python {sys.version.split()[0]}, Interpreter {arch} "
          f"({sysconfig.get_platform()}), Maschine {platform.machine()}, "
          f"PySide6 {version}")
    ergebnis = befund(importer)
    for name, fehler in ergebnis.items():
        print(f"  {'ok   ' if fehler is None else 'FEHLT'} {name}"
              + ("" if fehler is None else f"  ({fehler})"))
    webengine = ergebnis[WEBENGINE] is None
    if arch == "arm64":
        if webengine:
            print("[qt-befund] *** NEU: QtWebEngine im nativen ARM64-Wheel vorhanden - "
                  "XPLAT-45/XPLAT-46 neu bewerten (natives ARM64 koennte den "
                  "3D-Visualizer jetzt tragen).")
        else:
            print("[qt-befund] Natives ARM64: kein QtWebEngine - der 3D-Visualizer "
                  "braucht hier x64-Python (XPLAT-45).")
    if args.erwarte_webengine and not webengine:
        print("[qt-befund] FEHLER: QtWebEngine erwartet, aber nicht ladbar.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
