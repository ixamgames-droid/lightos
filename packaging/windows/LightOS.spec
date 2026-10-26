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

from PyInstaller.utils.hooks import collect_dynamic_libs, collect_submodules

REPO = os.path.abspath(os.path.join(SPECPATH, "..", ".."))  # noqa: F821 (SPECPATH kommt von PyInstaller)
sys.path.insert(0, SPECPATH)  # noqa: F821
sys.path.insert(0, REPO)      # fuer collect_submodules("src")
import bundle_inhalt  # noqa: E402

hiddenimports = list(bundle_inhalt.HIDDEN_IMPORTS)
# Alle LightOS-Module — auch die nur in Funktionen importierten. Billig und
# schuetzt vor einem fehlenden Modul, das erst beim Klick auf einen Menuepunkt
# auffiele.
hiddenimports += collect_submodules("src")

# OUT-76: mitgelieferte DLLs (libusb fuer uDMX-Adapter) in den Ordner ihres
# Pakets. Fehlt das Paket beim Bauen, bleibt der Build moeglich — der
# Selbsttest der gepackten exe meldet es als Fehler.
binaries = []
for paket in bundle_inhalt.DYNAMISCHE_BIBLIOTHEKEN:
    try:
        gefunden = collect_dynamic_libs(paket)
    except Exception as e:  # noqa: BLE001
        gefunden = []
        print(f"WARNUNG (OUT-76): {paket}: {type(e).__name__}: {e}")
    if not gefunden:
        print(f"WARNUNG (OUT-76): keine DLL aus {paket} — uDMX-Adapter laufen "
              "im Setup dann nicht (requirements.txt installiert?).")
    binaries += gefunden

if not bundle_inhalt.erzeugte_dateien(REPO):
    print("WARNUNG (DEMO-8): keine Demo-Shows in demo_shows/ — vorher "
          "'python packaging/demo_shows.py' ausfuehren. Der Selbsttest der "
          "gepackten exe meldet das als Fehler.")

a = Analysis(  # noqa: F821
    [os.path.join(REPO, "main.py")],
    pathex=[REPO],
    binaries=binaries,
    datas=bundle_inhalt.datas(REPO),
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=list(bundle_inhalt.EXCLUDES),
    noarchive=False,
    # LIZ-2 (LGPL): die Python-Teile von PySide6 und shiboken6 als lesbare
    # .py-Dateien neben ihre DLLs legen, nicht ins Archiv der exe — so bleibt
    # auch dieser Teil der Bibliothek austauschbar.
    module_collection_mode=dict(bundle_inhalt.OFFEN_MITLIEFERN),
)

# LIZ-2: von Qt nur, was LightOS oder ein mitgeliefertes Qt-Plugin wirklich
# laedt. PyInstaller sammelt sonst den ganzen QML-Ordner ein — mit Modulen, die
# es nur unter der GPLv3 gibt (Qt Charts, Qt Quick 3D, Qt Virtual Keyboard …).
import fremdkomponenten  # noqa: E402
import qt_umfang  # noqa: E402

a.binaries, a.datas, _qt = qt_umfang.auswahl(a.binaries, a.datas)
print(f"LIZ-2: {len(_qt['entfernt'])} Qt-Dateien entfallen; es bleiben "
      + ", ".join(_qt["qt_bleibt"]))
if _qt["fehler"]:
    raise SystemExit("LIZ-2 (Qt-Umfang):\n  " + "\n  ".join(_qt["fehler"]))

# LIZ-4: oben (neben python312.dll) die neueste VCRUNTIME140/_1 des Bundles —
# Windows laedt je Name nur die obere, Qt ist mit einer neueren gebaut als Python.
import vc_laufzeit  # noqa: E402

a.binaries, a.datas, _vc = vc_laufzeit.angleichen(a.binaries, a.datas)
print("LIZ-4: Microsoft-Laufzeit oben: "
      + ", ".join(f"{n} {v}" for n, v in _vc["oben"].items())
      + ("; ersetzt: " + "; ".join(_vc["ersetzt"]) if _vc["ersetzt"] else ""))
if _vc["fehler"]:
    raise SystemExit("LIZ-4 (Microsoft-Laufzeit):\n  " + "\n  ".join(_vc["fehler"]))

# LIZ-2: jede Datei des Bundles ihrer Herkunft zuordnen und gegen die Liste der
# erlaubten Fremd-Komponenten pruefen; die Lizenztexte der Pakete (in der
# installierten Fassung) und die Liste dieses Builds kommen ins Bundle. Ein
# Paket ohne Eintrag, eine geaenderte Lizenzangabe, ein fehlender Text: kein
# Setup.
_lizenzen, _befunde = fremdkomponenten.pruefe_und_schreibe(
    list(a.pure) + list(a.binaries) + list(a.datas) + list(a.scripts),
    repo=REPO,
    arbeitsordner=os.path.join(workpath, "fremdlizenzen"),  # noqa: F821
    eigene=(workpath,))  # noqa: F821
if _befunde:
    raise SystemExit("LIZ-2 (Fremd-Komponenten): das Bundle passt nicht zu "
                     "packaging/windows/fremdkomponenten.py:\n  "
                     + "\n  ".join(_befunde))
a.datas += [(os.path.join(ziel, os.path.basename(quelle)), quelle, "DATA")
            for quelle, ziel in _lizenzen]
print(f"LIZ-2: {len(_lizenzen)} Lizenzdateien ins Bundle (licenses/).")

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
