# -*- mode: python ; coding: utf-8 -*-
# XPLAT-62: PyInstaller-Spec fuer den Linux-Build von LightOS (.deb).
#
# Bauen (auf Linux x86_64, im Repo-Root, mit installierten requirements.txt):
#     python packaging/demo_shows.py              (DEMO-8: Demo-Shows)
#     python packaging/windows/build_info.py      (STAB-33: Commit ins Bundle)
#     python -m PyInstaller --noconfirm --clean packaging/linux/LightOS.spec
#     python packaging/linux/baue_deb.py          (-> dist/deb/lightos_<v>_amd64.deb)
#
# Warum eine EIGENE Spec statt der Windows-Spec mit Plattformweiche: die
# Windows-Spec prueft das Bundle hart gegen Tabellen, die nur Windows-Dateien
# kennen (qt_umfang: Qt6*.dll-Importe; vc_laufzeit: VCRUNTIME; fremdkomponenten:
# *.dll-Muster, api-ms-win-*). Auf Linux liegen dort .so-Dateien — jede Weiche
# haette die halbe Windows-Spec umschalten muessen und den Windows-Bau
# gefaehrdet. GETEILT wird, was plattformneutral ist: bundle_inhalt.py
# (welche Repo-Dateien mitkommen, Hidden Imports, Excludes, offen gelieferte
# PySide6-Teile) und die Lizenzsammlung aus fremdkomponenten.py.
#
# ONEDIR wie unter Windows (QtWebEngine braucht echte Dateien; onefile
# entpackte bei jedem Start ~300 MB). Ergebnis: dist/LightOS/LightOS + _internal/.
import os
import sys

from PyInstaller.utils.hooks import collect_submodules

REPO = os.path.abspath(os.path.join(SPECPATH, "..", ".."))  # noqa: F821 (SPECPATH kommt von PyInstaller)
WIN = os.path.join(REPO, "packaging", "windows")
sys.path.insert(0, WIN)
sys.path.insert(0, REPO)      # fuer collect_submodules("src")
import bundle_inhalt  # noqa: E402

hiddenimports = list(bundle_inhalt.HIDDEN_IMPORTS)
hiddenimports += collect_submodules("src")

# libusb kommt unter Linux aus dem System (Paket-Abhaengigkeit libusb-1.0-0),
# nicht aus libusb_package — deshalb hier keine DYNAMISCHE_BIBLIOTHEKEN.

if not bundle_inhalt.erzeugte_dateien(REPO):
    print("WARNUNG (DEMO-8): keine Demo-Shows in demo_shows/ — vorher "
          "'python packaging/demo_shows.py' ausfuehren.")

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
    module_collection_mode=dict(bundle_inhalt.OFFEN_MITLIEFERN),
)

# LIZ-2 sinngemaess: den QML-Ordner nicht mitnehmen (LightOS laedt kein QML;
# darin lagen unter Windows Module, die es nur unter der GPLv3 gibt).
def _ohne_qml(eintraege):
    return [e for e in eintraege
            if "/qt/qml/" not in str(e[0]).replace("\\", "/").lower() + "/"
            and not str(e[0]).replace("\\", "/").lower().startswith("pyside6/qt/qml")]


a.binaries = _ohne_qml(a.binaries)
a.datas = _ohne_qml(a.datas)

# Fremdlizenzen wie unter Windows: jede Datei ihrem Paket zuordnen und dessen
# Lizenztexte (in der installierten Fassung) nach licenses/ legen. Die harte
# Pruefung gegen die Komponententabelle kennt nur Windows-Dateinamen — unter
# Linux erscheinen Befunde deshalb als WARNUNG (XPLAT-62, Rest: Linux-Tabelle).
import fremdkomponenten  # noqa: E402
import platform  # noqa: E402

_eintraege = list(a.pure) + list(a.binaries) + list(a.datas) + list(a.scripts)
try:
    _karte, _info = fremdkomponenten.besitzer_karte()
    _erfasst = fremdkomponenten.erfasse(
        _eintraege, _karte, python_basis=sys.base_prefix,
        eigene=(REPO, workpath))  # noqa: F821
    _erfasst["pakete"].setdefault("pyinstaller", [])
    _py_lizenz = os.path.join(
        sys.base_prefix, "lib",
        f"python{sys.version_info[0]}.{sys.version_info[1]}", "LICENSE.txt")
    if not os.path.isfile(_py_lizenz):
        print(f"WARNUNG (XPLAT-62): Python-Lizenz nicht gefunden: {_py_lizenz}")
        _py_lizenz = None
    _lizenzen = fremdkomponenten.schreibe_lizenzen(
        os.path.join(workpath, "fremdlizenzen"),  # noqa: F821
        _erfasst, _info, _py_lizenz, platform.python_version(),
        qt_dateien=[str(e[0]) for e in _eintraege])
except Exception as e:  # noqa: BLE001
    raise SystemExit(f"XPLAT-62 (Fremdlizenzen): {type(e).__name__}: {e}")
a.datas += [(os.path.join(ziel, os.path.basename(quelle)), quelle, "DATA")
            for quelle, ziel in _lizenzen]
print(f"XPLAT-62: {len(_lizenzen)} Lizenzdateien ins Bundle (licenses/).")

pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LightOS",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
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
