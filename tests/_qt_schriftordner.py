"""Fester Qt-Schriftordner fuer Windows-Offscreen-Tests (QA-99, QA-114, CDX-69).

QA-99: Unter Windows bringt die Qt-Plattform „offscreen“ keine Schriftquelle
mit. Ohne QT_QPA_FONTDIR kennt sie KEINE Schrift (QFontDatabase.families()
leer), jeder Text wird mit Ersatzkaestchen vermessen — „Probe Text 123“ ist
dann 168 statt 78 Pixel breit. Layout-Tests (sizeHint, Textbreiten,
abgeschnittene Knoepfe) werden davon rot, ohne dass am Code etwas ist:
gemessen 18.10.2026 auf main, 9 Dateien im Windows-Gate. Linux und macOS
finden Schriften ueber fontconfig/CoreText — dort bleibt alles, wie es ist.
Ein vom Aufrufer gesetztes QT_QPA_FONTDIR gewinnt. Muss vor der ersten
QApplication stehen (die Plattform liest die Variable beim Start).

QA-114: NICHT der ganze Windows-Schriftordner. Liegen dort weitere Schriften
(z. B. aus Office), nimmt Qt fuer die Standardschrift die alphabetisch erste
Familie („AGA Arabesque“: Text 279 statt 148 px breit), QtWebEngine erbt sie
als sans-serif — gemessen 02.11.2026 auf einem Windows-Rechner, 13 Testdateien
rot ohne Fehler im Code. Deshalb ein fester Ordner im Temp nur mit den
Schriften unten: jeder Windows-Rechner misst dann wie die CI.

CDX-69: Parallele Testprozesse (``tools/verify_segmented.ps1``, 4 Worker)
teilen sich den Ordner. Ohne Absprache konnte bei kaltem Cache ein Prozess den
Ordner als fehlend sehen, ein zweiter ihn fertig veroeffentlichen und der
erste ihn dann als „beschaedigt“ loeschen — waehrend der zweite ihn schon als
QT_QPA_FONTDIR benutzt. Pruefen, Ersetzen und Anlegen laufen deshalb unter
einer Sperrdatei; einen Ordner, der passt, loescht nie jemand.

Eigenes Modul (nicht in conftest), damit Testprozesse die Regel laden koennen,
ohne den ganzen Test-Aufbau von conftest mitzuziehen.
"""
import contextlib
import hashlib
import os
import shutil
import sys
import tempfile
import time
import uuid

TEST_SCHRIFTEN = ("arial.ttf", "arialbd.ttf", "segoeui.ttf", "segoeuib.ttf",
                  "seguisym.ttf", "consola.ttf")
SPERRDATEI = "lightos_qt_schriften.lock"
_SPERRE_WARTEN_S = 120.0


def schriftordner_passt(ordner, quellen):
    """True, wenn ``ordner`` genau die Dateien aus ``quellen`` (Name, Groesse)
    enthaelt — nichts fehlt, nichts Fremdes dazu."""
    try:
        if sorted(os.listdir(ordner)) != sorted(name for name, _, _ in quellen):
            return False
        return all(os.path.getsize(os.path.join(ordner, name)) == groesse
                   for name, groesse, _ in quellen)
    except OSError:
        return False


@contextlib.contextmanager
def _sperre(basis, warten_s=_SPERRE_WARTEN_S):
    """Exklusive Sperre ueber ``basis``/SPERRDATEI zwischen Prozessen.

    Die Sperre haengt am offenen Dateigriff, nicht an der Existenz der Datei:
    stirbt ein Prozess, gibt das Betriebssystem sie frei — keine Altsperren.
    Die Datei selbst bleibt liegen (sie zu loeschen oeffnet ein neues Rennen).
    Wartet hoechstens ``warten_s`` Sekunden, sonst OSError."""
    fd = os.open(os.path.join(basis, SPERRDATEI), os.O_RDWR | os.O_CREAT, 0o666)
    try:
        if sys.platform.startswith("win"):
            import msvcrt
            frist = time.monotonic() + warten_s
            while True:
                try:
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if time.monotonic() >= frist:
                        raise
                    time.sleep(0.05)
            try:
                yield
            finally:
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            frist = time.monotonic() + warten_s
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError:
                    if time.monotonic() >= frist:
                        raise
                    time.sleep(0.05)
            try:
                yield
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def fester_schriftordner(quelle, basis):
    """Kopiert die ``TEST_SCHRIFTEN`` aus ``quelle`` in einen Ordner unter
    ``basis`` und gibt ihn zurueck; None, wenn keine davon in ``quelle`` liegt.

    Der Name haengt an Groesse und Zeitstempel der Quellen: alle Testprozesse
    (auch parallele Segmente) teilen sich denselben Ordner, und eine per Update
    getauschte Schrift ergibt einen neuen. Aufgebaut wird in einem eigenen
    Ordner und erst fertig umbenannt — ein halb kopierter Ordner ist nie sichtbar.
    Passt der Ordner schon, geht es ohne Sperre; sonst wird unter der Sperre
    neu geprueft, und nur ein dort bestaetigt beschaedigter Ordner wird ersetzt."""
    quellen = []
    for name in TEST_SCHRIFTEN:
        try:
            st = os.stat(os.path.join(quelle, name))
        except OSError:
            continue
        quellen.append((name, st.st_size, st.st_mtime_ns))
    if not quellen:
        return None
    kennung = hashlib.sha1(repr(quellen).encode("utf-8")).hexdigest()[:12]
    ziel = os.path.join(basis, f"lightos_qt_schriften_{kennung}")
    if schriftordner_passt(ziel, quellen):
        return ziel
    with _sperre(basis):
        if schriftordner_passt(ziel, quellen):  # ein anderer Prozess war schneller
            return ziel
        if os.path.lexists(ziel):           # beschaedigt (Datei fehlt/fremd) -> weg
            # Erst beiseite benennen, dann loeschen: ``ziel`` ist danach sofort
            # frei, auch wenn das Loeschen (offene Datei) nicht ganz gelingt.
            alt = os.path.join(basis, f"lightos_qt_schriften_alt_{uuid.uuid4().hex[:8]}")
            os.rename(ziel, alt)
            shutil.rmtree(alt, ignore_errors=True)
        bau = tempfile.mkdtemp(prefix="lightos_qt_schriften_bau_", dir=basis)
        try:
            for name, _, _ in quellen:
                shutil.copyfile(os.path.join(quelle, name), os.path.join(bau, name))
            try:
                os.rename(bau, ziel)
            except OSError:
                # Ein Prozess ohne diese Sperre (aelterer Stand in einem anderen
                # Worktree) war schneller: dessen fertiger Ordner gilt.
                if not schriftordner_passt(ziel, quellen):
                    raise
            return ziel
        finally:
            shutil.rmtree(bau, ignore_errors=True)


def offscreen_schriftordner(umgebung, plattform=sys.platform):
    """Setzt in ``umgebung`` QT_QPA_FONTDIR auf einen festen Schriftordner
    (QA-114), wenn die Plattform „offscreen“ ist und noch kein Schriftordner
    gesetzt ist. Fehlen alle festen Schriften, bleibt es beim ganzen
    Windows-Ordner — besser als gar keine Schrift (QA-99).
    Gibt den gesetzten Ordner zurueck, sonst None."""
    if not plattform.startswith("win"):
        return None
    if umgebung.get("QT_QPA_PLATFORM", "").strip().lower() != "offscreen":
        return None
    if umgebung.get("QT_QPA_FONTDIR"):
        return None
    windows = umgebung.get("WINDIR") or umgebung.get("SystemRoot") or r"C:\Windows"
    ordner = os.path.join(windows, "Fonts")
    if not os.path.isdir(ordner):
        return None
    try:
        ordner = fester_schriftordner(ordner, tempfile.gettempdir()) or ordner
    except OSError:
        pass                                # Temp nicht beschreibbar / Sperre -> wie QA-99
    umgebung["QT_QPA_FONTDIR"] = ordner
    return ordner
