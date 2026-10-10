# -*- mode: python ; coding: utf-8 -*-
# XPLAT-47: PyInstaller-Spec fuer den Windows-Build von LightOS.
#
# Bauen (auf Windows, im Repo-Root, mit installierten requirements.txt):
#     python packaging/demo_shows.py        (DEMO-8: Demo-Shows -> demo_shows/)
#     python -m PyInstaller --noconfirm --clean packaging/windows/LightOS.spec
# Ergebnis: dist/LightOS/LightOS.exe (+ _internal/). Danach baut
# packaging/windows/LightOS.iss daraus das Setup (LightOS-Setup.exe).
#
# ONEDIR, nicht onefile: QtWebEngine (3D-Visualizer) startet einen eigenen
# Prozess (QtWebEngineProcess.exe) und braucht seine Ressourcen als echte
# Dateien; onefile entpackte bei JEDEM Start ~300 MB in einen Temp-Ordner.
#
# Was ausser Python-Code mitkommt, steht in bundle_inhalt.py (dort auch, warum
# nur Git-bekannte Dateien gepackt werden — und die eine Ausnahme: die beim
# Bauen erzeugten Demo-Shows, DEMO-8).
import os
import sys

from PyInstaller.utils.hooks import collect_submodules

REPO = os.path.abspath(os.path.join(SPECPATH, "..", ".."))  # noqa: F821 (SPECPATH kommt von PyInstaller)
sys.path.insert(0, SPECPATH)  # noqa: F821
sys.path.insert(0, REPO)      # fuer collect_submodules("src")
import bundle_inhalt  # noqa: E402

hiddenimports = list(bundle_inhalt.HIDDEN_IMPORTS)
# Alle LightOS-Module — auch die nur in Funktionen importierten. Billig und
# schuetzt vor einem fehlenden Modul, das erst beim Klick auf einen Menuepunkt
# auffiele.
hiddenimports += collect_submodules("src")

if not bundle_inhalt.erzeugte_dateien(REPO):
    print("WARNUNG (DEMO-8): keine Demo-Shows in demo_shows/ — vorher "
          "'python packaging/demo_shows.py' ausfuehren. Der Selbsttest der "
          "gepackten exe meldet das als Fehler.")

a = Analysis(  # noqa: F821
    [os.path.join(REPO, "main.py")],
    pathex=[REPO],
    binaries=[],
    datas=bundle_inhalt.datas(REPO),
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=list(bundle_inhalt.EXCLUDES),
    noarchive=False,
)
pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LightOS",
    icon=os.path.join(REPO, "assets", "icons", "lightos.ico"),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # GUI-App: kein Konsolenfenster (stdout -> lightos.log)
    disable_windowed_traceback=False,
)

coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="LightOS",
)
