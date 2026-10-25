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
    "usb.core",      # OUT-68: pyusb, nur fuer uDMX-Adapter (rohes USB)
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
    ("LICENSE",),                                     # LIZ-1: Lizenztext
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


def pruefe_build_info(wurzel: str | None = None,
                      gefroren: bool | None = None) -> list[str]:
    """STAB-33: ein gepackter Build muss wissen, aus welchem Commit er stammt
    (``build_info.json`` im Bundle) — sonst steht im Diagnosepaket wieder
    ``Commit: unbekannt``. Im Quellbetrieb gibt es die Datei nicht (dort zaehlt
    ``.git``), deshalb nur gefroren ein Fehler."""
    gefroren = ist_gefroren() if gefroren is None else gefroren
    if not gefroren:
        return []
    from src.core import diagnose_log
    wurzel = wurzel or programm_dir()
    if not os.path.isfile(os.path.join(wurzel, diagnose_log.BUILD_INFO_NAME)):
        return [f"fehlt: {diagnose_log.BUILD_INFO_NAME} (vor dem Build "
                "packaging/windows/build_info.py ausfuehren)"]
    if not diagnose_log.build_commit(wurzel):
        return [f"{diagnose_log.BUILD_INFO_NAME}: nicht lesbar oder ohne Commit"]
    return []


def pruefe_udmx_bibliothek(gefroren: bool | None = None,
                           plattform: str | None = None,
                           maschine: str | None = None, laden=None) -> list[str]:
    """OUT-76: das Windows-Setup (x64) liefert pyusb und libusb mit — fehlt im
    gepackten Build eines davon, ist das ein Fehler (der Rauchtest der
    Setup-Pipeline bricht dann ab). Im Quellbetrieb, unter Linux/macOS und auf
    Windows-ARM64 bleibt uDMX optional: dort nur die Zeile ``optional uDMX``.

    Geladen wird nur die Bibliothek; kein USB-Geraet wird angefasst.
    ``laden`` (Tests) = Ersatz fuer ``udmx._usb_laden``.
    """
    import platform
    gefroren = ist_gefroren() if gefroren is None else gefroren
    plattform = sys.platform if plattform is None else plattform
    maschine = platform.machine() if maschine is None else maschine
    if not gefroren or not plattform.startswith("win") or maschine.upper() == "ARM64":
        return []
    try:
        if laden is None:
            from src.core.dmx.udmx import _usb_laden as laden
        _core, _util, backend = laden()
    except Exception as e:
        return [f"uDMX: pyusb fehlt im Setup ({type(e).__name__}: {e})"]
    if backend is None:
        return ["uDMX: libusb-1.0.dll fehlt im Setup oder laesst sich nicht "
                "laden (libusb-package, s. packaging/windows/bundle_inhalt.py)"]
    return []


#: LIZ-2: Lizenzdateien, die ein gepackter Build mitbringen muss (relativ zu
#: ``programm_dir()``, als Teile notiert wie ``PFLICHT_RESSOURCEN``). Die Liste
#: und Pythons Lizenztext entstehen beim Bauen
#: (``packaging/windows/fremdkomponenten.py``), die uebrigen liegen im Repo.
PFLICHT_LIZENZDATEIEN: tuple[str, ...] = tuple("/".join(teile) for teile in (
    ("licenses", "BUNDLE-KOMPONENTEN.txt"),
    ("licenses", "Python-LICENSE.txt"),
    ("licenses", "LGPL-3.0.txt"),
    ("licenses", "GPL-3.0.txt"),
))

#: LIZ-2 (Rest): Bibliothek im Programmordner -> Sammeldatei ihrer Fremdlizenzen
#: (``packaging/windows/fremdlizenzen_sammeln.py``).
SAMMELDATEIEN_JE_BIBLIOTHEK: tuple[tuple[str, str], ...] = tuple(
    ("/".join(dll), "/".join(text)) for dll, text in (
        (("PySide6", "Qt6WebEngineCore.dll"), ("licenses", "QtWebEngine-THIRD-PARTY.txt")),
        (("PySide6", "opengl32sw.dll"), ("licenses", "Mesa-opengl32sw.txt")),
    ))


def pruefe_fremdlizenzen(wurzel: str | None = None,
                         gefroren: bool | None = None) -> list[str]:
    """LIZ-2: ein gepackter Build liefert die Lizenztexte der fremden
    Bibliotheken mit — und von Qt nur, was in seiner eigenen Liste steht.

    Geprueft wird das FERTIGE Paket, unabhaengig vom Bauwerkzeug:

    * die Liste dieses Builds und die Lizenztexte liegen bei;
    * jede ``Qt6*.dll`` im Programmordner steht in der Liste (eine Bibliothek,
      die am Filter vorbei hineingeraten ist, faellt hier auf — Qt bietet
      einige Module nur unter der GPL an);
    * der QML-Ordner von Qt fehlt;
    * keine Datei der Universal C Runtime liegt bei (sie gehoert zu Windows
      und kaeme sonst aus einem zufaelligen Ordner des Bau-Rechners).

    Im Quellbetrieb gibt es weder Liste noch Bundle: dort nichts.
    """
    gefroren = ist_gefroren() if gefroren is None else gefroren
    if not gefroren:
        return []
    wurzel = wurzel or programm_dir()
    fehler = [f"Lizenzen: fehlt {rel}" for rel in PFLICHT_LIZENZDATEIEN
              if not os.path.isfile(os.path.join(wurzel, *rel.split("/")))]
    # LIZ-2 (Rest): Qt WebEngine (Chromium) und Mesa bringen ihre Fremdlizenzen
    # nicht mit — liegt die Bibliothek bei, muss ihre Sammeldatei dabei sein.
    for dll, text in SAMMELDATEIEN_JE_BIBLIOTHEK:
        if (os.path.isfile(os.path.join(wurzel, *dll.split("/")))
                and not os.path.isfile(os.path.join(wurzel, *text.split("/")))):
            fehler.append(f"Lizenzen: fehlt {text} (zu {dll})")
    if not _hat_datei(os.path.join(wurzel, "licenses", "pakete")):
        fehler.append("Lizenzen: der Ordner mit den Lizenztexten der "
                      "Python-Pakete ist leer oder fehlt")
    liste = ""
    try:
        with open(os.path.join(wurzel, *PFLICHT_LIZENZDATEIEN[0].split("/")),
                  encoding="utf-8") as f:
            liste = f.read()
    except OSError:
        pass
    qt_ordner = os.path.join(wurzel, "PySide6")
    try:
        namen = sorted(os.listdir(qt_ordner))
    except OSError:
        namen = []
    if liste:
        gelistet = {zeile.split("|")[0].strip().lower()
                    for zeile in liste.splitlines() if "|" in zeile}
        for name in namen:
            klein = name.lower()
            if (klein.startswith("qt6") and klein.endswith(".dll")
                    and klein not in gelistet):
                fehler.append(f"Lizenzen: {name} liegt im Programmordner, steht "
                              "aber nicht in der Liste der Fremd-Komponenten")
    if os.path.isdir(os.path.join(qt_ordner, "qml")):
        fehler.append("Lizenzen: der QML-Ordner von Qt liegt im Programmordner "
                      "(packaging/windows/qt_umfang.py laesst ihn weg)")
    try:
        oben = sorted(os.listdir(wurzel))
    except OSError:
        oben = []
    fremd = [n for n in oben if n.lower() == "ucrtbase.dll"
             or (n.lower().startswith("api-ms-win-") and n.lower().endswith(".dll"))]
    if fremd:
        fehler.append(f"Lizenzen: {len(fremd)} Datei(en) der Universal C Runtime im "
                      f"Programmordner ({fremd[0]} …) — gehoeren zu Windows, nicht ins Setup")
    return fehler


#: LIZ-4: Microsoft-Laufzeit, die oben im Programmordner liegt und von dort fuer
#: den ganzen Prozess geladen wird (Namen klein; s. packaging/windows/vc_laufzeit.py).
VC_LAUFZEIT_OBEN: tuple[str, ...] = ("vcruntime140.dll", "vcruntime140_1.dll")


def datei_fassung(pfad: str) -> tuple[int, ...] | None:
    """Dateiversion einer Windows-DLL (``(14, 44, 35211, 0)``) ueber die
    Windows-API; ``None`` ohne Versionsressource und ausserhalb von Windows."""
    if not sys.platform.startswith("win"):
        return None
    import ctypes
    from ctypes import wintypes
    ver = ctypes.WinDLL("version")
    ver.GetFileVersionInfoSizeW.argtypes = [wintypes.LPCWSTR, wintypes.LPDWORD]
    ver.GetFileVersionInfoSizeW.restype = wintypes.DWORD
    ver.GetFileVersionInfoW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD,
                                        wintypes.DWORD, wintypes.LPVOID]
    ver.VerQueryValueW.argtypes = [wintypes.LPCVOID, wintypes.LPCWSTR,
                                   ctypes.POINTER(ctypes.c_void_p),
                                   ctypes.POINTER(wintypes.UINT)]
    groesse = ver.GetFileVersionInfoSizeW(pfad, None)
    if not groesse:
        return None
    puffer = ctypes.create_string_buffer(groesse)
    if not ver.GetFileVersionInfoW(pfad, 0, groesse, puffer):
        return None
    zeiger, laenge = ctypes.c_void_p(), wintypes.UINT()
    if (not ver.VerQueryValueW(puffer, "\\", ctypes.byref(zeiger), ctypes.byref(laenge))
            or not zeiger.value or laenge.value < 16):
        return None
    # VS_FIXEDFILEINFO: Signatur, Strukturversion, FileVersionMS, FileVersionLS …
    sig, _struktur, ms, ls = (ctypes.c_uint32 * 4).from_address(zeiger.value)
    if sig != 0xFEEF04BD:
        return None
    return (ms >> 16, ms & 0xFFFF, ls >> 16, ls & 0xFFFF)


def geladene_datei(name: str) -> str | None:
    """Pfad der Datei, aus der dieser Prozess die DLL ``name`` geladen hat
    (``None``: nicht geladen, oder nicht Windows)."""
    if not sys.platform.startswith("win"):
        return None
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.WinDLL("kernel32")
    k32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    k32.GetModuleHandleW.restype = wintypes.HMODULE
    k32.GetModuleFileNameW.argtypes = [wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD]
    k32.GetModuleFileNameW.restype = wintypes.DWORD
    modul = k32.GetModuleHandleW(name)
    if not modul:
        return None
    puffer = ctypes.create_unicode_buffer(32768)
    return puffer.value if k32.GetModuleFileNameW(modul, puffer, len(puffer)) else None


def _fassung_text(fassung) -> str:
    return ".".join(str(t) for t in fassung) if fassung else "?"


def pruefe_vc_laufzeit(wurzel: str | None = None, gefroren: bool | None = None,
                       plattform: str | None = None, geladen=geladene_datei,
                       fassung=datei_fassung) -> tuple[list[str], str | None]:
    """LIZ-4: ``(fehler, berichtszeile)`` zur Microsoft-Laufzeit eines
    gepackten Windows-Builds.

    Windows laedt je Name nur EINE ``VCRUNTIME140(_1).dll``. Geprueft wird am
    laufenden Prozess: die geladene Datei liegt im Programmordner (ein PC ohne
    VC++-Redistributable hat keine andere) und keine gleichnamige Datei im
    Bundle ist neuer als sie (Qt ist mit einer neueren Laufzeit gebaut als
    Python). Quellbetrieb und andere Systeme: nichts (``([], None)``).
    """
    gefroren = ist_gefroren() if gefroren is None else gefroren
    plattform = sys.platform if plattform is None else plattform
    if not gefroren or not plattform.startswith("win"):
        return [], None
    wurzel = os.path.abspath(wurzel or programm_dir())
    kopien: dict[str, list[str]] = {n: [] for n in VC_LAUFZEIT_OBEN}
    for ordner, _unter, dateien in os.walk(wurzel):
        for d in dateien:
            if d.lower() in kopien:
                kopien[d.lower()].append(os.path.join(ordner, d))
    fehler, teile = [], []
    for name in VC_LAUFZEIT_OBEN:
        pfad = geladen(name)
        if pfad is None:
            teile.append(f"{name} nicht geladen")
            continue
        f_geladen = fassung(pfad)
        innen = os.path.normcase(os.path.abspath(pfad)).startswith(
            os.path.normcase(wurzel) + os.sep)
        teile.append(f"{name} {_fassung_text(f_geladen)} "
                     + ("(Programmordner)" if innen else f"(aus {os.path.dirname(pfad)})"))
        if not innen:
            fehler.append(f"Laufzeit: {name} kommt aus {os.path.dirname(pfad)}, nicht "
                          "aus dem Programmordner — ohne VC++-Redistributable fehlte sie")
        if f_geladen is None:
            fehler.append(f"Laufzeit: {name} ({pfad}) hat keine lesbare Dateiversion")
            continue
        for k in kopien[name]:
            f = fassung(k)
            if f is not None and f > f_geladen:
                fehler.append(f"Laufzeit: geladen ist {name} {_fassung_text(f_geladen)}, "
                              f"im Bundle liegt {os.path.relpath(k, wurzel)} in "
                              f"{_fassung_text(f)} (packaging/windows/vc_laufzeit.py)")
    return fehler, "Microsoft-Laufzeit: " + ", ".join(teile)


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
    fehler = (pruefe_module() + pruefe_ressourcen() + pruefe_code_stand()
              + pruefe_build_info() + pruefe_udmx_bibliothek()
              + pruefe_fremdlizenzen())
    demo_fehler, demo_zeile = pruefe_demo_shows()
    fehler += demo_fehler
    zeilen.append(demo_zeile)
    # LIZ-4: nach pruefe_module — dann sind Python UND Qt geladen.
    vc_fehler, vc_zeile = pruefe_vc_laufzeit()
    fehler += vc_fehler
    if vc_zeile:
        zeilen.append(vc_zeile)
    try:
        from src.core import diagnose_log
        zeilen.append(f"Commit: {diagnose_log.commit_text() or 'unbekannt'}")
    except Exception:
        pass
    for name in OPTIONALE_MODULE:
        rest = pruefe_module((name,))
        zeilen.append(f"optional {name}: {'fehlt — ' + rest[0] if rest else 'ok'}")
    try:
        # OUT-68: pyusb allein genuegt nicht — darunter braucht es libusb.
        from src.core.dmx.udmx import bibliothek_status
        zeilen.append(f"optional uDMX: {bibliothek_status()['text']}")
    except Exception as e:
        zeilen.append(f"optional uDMX: ? ({type(e).__name__}: {e})")
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
