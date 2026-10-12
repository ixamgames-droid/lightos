"""LIZ-2: Welche Teile von Qt ins Windows-Bundle kommen — und welche nicht.

Befund (12.10.2026, echtes Bundle aus ``LightOS.spec``): PyInstaller sammelt den
GANZEN QML-Ordner von Qt ein, sobald ein Modul ``Qt6Quick.dll`` braucht — und
QtWebEngine (3D-Visualizer) braucht sie. Damit lagen 130 Qt-Bibliotheken im
Bundle, obwohl LightOS kein QML benutzt; darunter sieben Module, die es in der
Open-Source-Ausgabe von Qt NICHT unter der LGPL gibt, sondern nur unter der
GPLv3: Qt Charts, Qt Data Visualization, Qt Graphs, Qt Quick 3D, Qt Quick 3D
Physics, Qt Quick Timeline, Qt Virtual Keyboard (Quelle: Qt-Dokumentation 6.12,
„Qt Licensing“ und die Lizenz-Abschnitte der Modulseiten).

Regel dieses Moduls: im Bundle bleibt von Qt nur, was LightOS oder ein
mitgeliefertes Qt-Plugin wirklich laedt.

* Der QML-Ordner und die QML-Diagnose-Plugins entfallen ganz (LightOS laedt
  kein QML; die Qt-Dokumentation verlangt die QML-Importe von QtWebEngine nur
  fuer die Qt-Quick-Einbindung, nicht fuer QtWebEngineWidgets).
* Von den Bibliotheken ``PySide6/Qt6*.dll`` bleibt die Huelle ueber die
  DLL-Importe: alles, was eine verbleibende Binaerdatei (Python-Erweiterung,
  Plugin, ``QtWebEngineProcess.exe``) direkt oder mittelbar importiert.
* Einzelne Plugins entfallen ausdruecklich (``ENTFAELLT_DATEIEN``).

Was danach uebrig ist, prueft ``fremdkomponenten.py`` gegen die Liste der
erlaubten Qt-Module — ein Nur-GPL-Modul oder ein unbekanntes Modul im Bundle
bricht den Bau ab.

Bewusst OHNE PyInstaller-Import (wie ``bundle_inhalt.py``): die Tests laufen
auch auf Linux. ``LightOS.spec`` reicht die Listen aus ``Analysis`` herein und
bekommt die gefilterten zurueck.
"""
from __future__ import annotations

import fnmatch
import os

#: Ordner im Bundle (``/``-Schreibweise, mit Schraegstrich am Ende), die ganz
#: entfallen.
ENTFAELLT_ORDNER: tuple[str, ...] = (
    "PySide6/qml/",                  # QML-Module: LightOS laedt kein QML
    "PySide6/plugins/qmltooling/",   # QML-Debugger/-Profiler
)

#: Einzelne Dateien bzw. Muster (``fnmatch``, ``/``-Schreibweise), die entfallen.
ENTFAELLT_DATEIEN: tuple[str, ...] = (
    # Qt Virtual Keyboard (nur GPLv3): Eingabe-Plugin, zieht Qt6VirtualKeyboard.dll.
    "PySide6/plugins/platforminputcontexts/qtvirtualkeyboardplugin.dll",
    # TLS ueber OpenSSL: das Plugin zieht libcrypto/libssl an — und PyInstaller
    # nimmt dafuer die ERSTE OpenSSL im PATH des Bau-Rechners (Git, ein JDK …).
    # Herkunft und Version waeren damit dem Zufall ueberlassen. LightOS benutzt
    # QtNetwork/TLS nicht (Chromium und Python bringen ihre eigene TLS mit);
    # braucht Qt doch einmal TLS, nimmt es das Windows-eigene Schannel-Plugin.
    "PySide6/plugins/tls/qopensslbackend.dll",
    # Uebersetzungen von Modulen, die nicht mitkommen.
    "PySide6/translations/qtlocation_*.qm",
)

#: Bibliotheken, die nur bleiben, wenn eine verbleibende Binaerdatei sie
#: importiert (Namen klein, ohne Ordner). Die OpenSSL des Bau-Rechners haengt
#: allein am oben entfernten Qt-Plugin.
NUR_MIT_ABNEHMER: tuple[str, ...] = (
    "libcrypto-3-x64.dll",
    "libssl-3-x64.dll",
)

#: Qt-Bibliotheken, ohne die LightOS nicht laeuft. Fiele eine davon aus der
#: Huelle, stimmt etwas am Filter nicht — dann lieber kein Bundle.
PFLICHT_QT: tuple[str, ...] = (
    "Qt6Core.dll",
    "Qt6Gui.dll",
    "Qt6Widgets.dll",
    "Qt6Multimedia.dll",
    "Qt6WebChannel.dll",
    "Qt6WebEngineCore.dll",
    "Qt6WebEngineWidgets.dll",
)

_BINAER_ENDUNGEN = (".dll", ".pyd", ".exe")


def _ziel(eintrag) -> str:
    """Zielpfad eines TOC-Eintrags in ``/``-Schreibweise."""
    return str(eintrag[0]).replace("\\", "/")


def ist_qt_bibliothek(ziel: str) -> bool:
    """``PySide6/Qt6<Name>.dll`` — die Bibliotheken, ueber die die Huelle
    entscheidet. Plugins und alles andere unter ``PySide6/`` gehoeren nicht
    dazu."""
    ziel = ziel.replace("\\", "/")
    kopf, _, name = ziel.rpartition("/")
    return (kopf.lower() == "pyside6" and name.lower().startswith("qt6")
            and name.lower().endswith(".dll"))


def entfaellt(ziel: str) -> bool:
    """Steht die Datei in einem Ordner bzw. auf einem Muster, das entfaellt?"""
    ziel = ziel.replace("\\", "/")
    klein = ziel.lower()
    if any(klein.startswith(o.lower()) for o in ENTFAELLT_ORDNER):
        return True
    return any(fnmatch.fnmatchcase(klein, m.lower()) for m in ENTFAELLT_DATEIEN)


def pe_importe(pfad: str) -> set[str]:
    """Namen (klein) der DLLs, die ``pfad`` importiert — auch verzoegert
    geladene. Braucht ``pefile`` (kommt mit PyInstaller); nur beim Bauen
    aufgerufen."""
    import pefile
    pe = pefile.PE(pfad, fast_load=True)
    try:
        pe.parse_data_directories(directories=[
            pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"],
            pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT"]])
        aus: set[str] = set()
        for attr in ("DIRECTORY_ENTRY_IMPORT", "DIRECTORY_ENTRY_DELAY_IMPORT"):
            for e in getattr(pe, attr, None) or []:
                aus.add(e.dll.decode("ascii", "replace").lower())
        return aus
    finally:
        pe.close()


def auswahl(binaries, datas, importe=pe_importe):
    """Filtert die TOC-Listen eines PyInstaller-Laufs.

    ``binaries``/``datas``: Listen aus ``(ziel, quelle, typ)``; ``importe(quelle)``
    liefert die Namen (klein) der importierten DLLs einer Binaerdatei.

    Rueckgabe ``(binaries, datas, bericht)``. ``bericht`` ist ein Woerterbuch:
    ``entfernt`` (Zielpfade, sortiert), ``qt_bleibt`` (Namen der verbleibenden
    Qt-Bibliotheken), ``fehler`` (Liste — leer heisst in Ordnung).
    """
    binaries = list(binaries)
    datas = list(datas)
    entfernt: list[str] = []
    fehler: list[str] = []

    def behalten_nach_muster(liste):
        aus = []
        for e in liste:
            if entfaellt(_ziel(e)):
                entfernt.append(_ziel(e))
            else:
                aus.append(e)
        return aus

    binaries = behalten_nach_muster(binaries)
    datas = behalten_nach_muster(datas)

    # Importe aller verbleibenden Binaerdateien — auch solcher, die PyInstaller
    # als DATA fuehrt (kommt bei der Neueinordnung vor).
    kandidaten = [e for e in binaries + datas
                  if _ziel(e).lower().endswith(_BINAER_ENDUNGEN)]
    imp: dict[str, set[str]] = {}
    for e in kandidaten:
        try:
            imp[_ziel(e)] = {n.lower() for n in importe(e[1])}
        except Exception as ex:  # noqa: BLE001 — kaputte Datei: melden, nicht raten
            fehler.append(f"{_ziel(e)}: Importe nicht lesbar ({type(ex).__name__}: {ex})")
            imp[_ziel(e)] = set()

    qt = {os.path.basename(z).lower(): z for z in imp if ist_qt_bibliothek(z)}
    qt_ziele = set(qt.values())
    bleibt: set[str] = set()
    offen = [qt[n] for z in imp if z not in qt_ziele for n in imp[z] if n in qt]
    while offen:
        z = offen.pop()
        if z in bleibt:
            continue
        bleibt.add(z)
        offen.extend(qt[n] for n in imp[z] if n in qt)
    weg = qt_ziele - bleibt

    # Anhaengsel: nur, solange jemand Verbleibendes sie importiert. Bis nichts
    # mehr faellt — libssl braucht libcrypto, faellt aber selbst.
    while True:
        gebraucht = set()
        for z, namen in imp.items():
            if z not in weg:
                gebraucht |= namen
        neu_weg = {z for z in imp if z not in weg
                   and os.path.basename(z).lower() in NUR_MIT_ABNEHMER
                   and os.path.basename(z).lower() not in gebraucht}
        if not neu_weg:
            break
        weg |= neu_weg

    def ohne_weg(liste):
        aus = []
        for e in liste:
            if _ziel(e) in weg:
                entfernt.append(_ziel(e))
            else:
                aus.append(e)
        return aus

    binaries = ohne_weg(binaries)
    datas = ohne_weg(datas)

    qt_bleibt = sorted(os.path.basename(z) for z in bleibt)
    if qt:      # ein Bundle ganz ohne Qt gibt es nur in Tests
        vorhanden = {n.lower() for n in qt_bleibt}
        for name in PFLICHT_QT:
            if name.lower() not in vorhanden:
                fehler.append(f"{name} fiele aus dem Bundle — der Qt-Filter stimmt nicht")
    return binaries, datas, {"entfernt": sorted(entfernt), "qt_bleibt": qt_bleibt,
                             "fehler": fehler}
