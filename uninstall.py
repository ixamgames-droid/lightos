r"""LightOS Uninstaller.

Entfernt was install.py angelegt hat. Liest install_manifest.json wenn vorhanden,
sonst Fallback auf bekannte Pfade.

Was wird entfernt:
- venv/                  (Virtual Environment)
- data/                  (nur Nutzerdateien aus der Zeit VOR dem Datenumzug
                          XPLAT-44; data/controller_library gehoert zum Programm
                          und bleibt. Eine Nutzerdatei, die im App-Datenordner
                          noch FEHLT oder dort nur frisch und leer angelegt ist
                          - LightOS hat sie seit dem Update nie uebernommen -,
                          ist der einzige Stand und bleibt ebenfalls)
- shows/                 (Shows im Programmordner - nur nach ausdruecklicher
                          Rueckfrage, mit --yes oder --keep-shows nie)
- Desktop\LightOS.lnk    (nur die EIGENE: im Manifest genannt oder mit Ziel
                          in diesem Programmordner - die Verknuepfung einer
                          zweiten Installation bleibt)
- install_manifest.json
- __pycache__ unter src/

Was NUR mit --purge entfernt wird (XPLAT-49):
- App-Datenordner        (%APPDATA%/LightOS bzw. ~/.local/share/LightOS: eigene
                          Shows, Show-DB, Universen, MIDI-Mappings, Gruppen,
                          Modifier, Fixture-Bibliothek, Snaps, Buehnen, Profile,
                          Auto-Save, Logs)

Usage:
    python uninstall.py                  (interaktiv - fragt jeden Bereich)
    python uninstall.py --yes            (Installation ohne Rueckfrage entfernen;
                                          App-Datenordner und Shows bleiben)
    python uninstall.py --purge          (zusaetzlich den App-Datenordner, nach
                                          Sicherheitsfrage)
    python uninstall.py --purge --yes    (dasselbe ohne Sicherheitsfrage)
    python uninstall.py --keep-shows     (Shows behalten - im Programmordner UND,
                                          bei --purge, im App-Datenordner)
    python uninstall.py --keep-appdata   (App-Datenordner behalten, auch bei --purge)
    python uninstall.py --keep-venv      (venv/ behalten)
    python uninstall.py --dry-run        (nur anzeigen was geloescht wuerde)
"""
from __future__ import annotations
import os
import sys
import json
import shutil
import argparse
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
MANIFEST_PATH = ROOT / "install_manifest.json"
# XPLAT-10: dieselbe Aufloesung wie App und Installer — sonst raeumt uninstall.py
# auf Linux ~/LightOS weg (vom alten Installer angelegt, meist leer) und LAESST die
# echten Nutzerdaten in ~/.local/share/LightOS stehen.
sys.path.insert(0, str(ROOT))
from src.core.paths import app_data_dir, USER_DATA_FILES   # noqa: E402
# Nur Standardbibliothek + paths: laeuft auch mit dem System-Python ohne venv.
from src.core.datenumzug import ist_uebernommen   # noqa: E402

APPDATA_DIR = Path(app_data_dir())
VENV_DIR = ROOT / "venv"

# XPLAT-44: die Nutzerdaten (Show-DB, Universen, MIDI, Gruppen, Modifier) liegen
# im App-Datenordner, nicht mehr in data/. Die Fragen muessen das sagen — sonst
# loescht, wer den App-Ordner fuer "nur Snapshots" haelt, ungewarnt die Show.
# XPLAT-49: data/controller_library ist versioniert (Programm, keine Nutzerdaten).
DATA_BEHALTEN = ("controller_library",)
DATA_FRAGE = ("data/ aufraeumen? (nur der alte Datenstand von VOR dem Update - "
              "die aktuellen Nutzerdaten liegen im App-Datenordner; die "
              "mitgelieferten Vorlagen in data/controller_library bleiben)")

# XPLAT-49: eigene Shows liegen standardmaessig in <App-Datenordner>/shows.
APPDATA_SHOWS = "shows"
APPDATA_INHALT = ("eigene Shows, Show-DB, Universen, MIDI-Mappings, Gruppen, "
                  "Modifier, Fixture-Bibliothek, Snaps, Buehnen, Profile, "
                  "Auto-Save, Logs")


def appdata_frage(shows_bleiben: bool = False) -> str:
    if shows_bleiben:
        return (f"{APPDATA_DIR}/ WIRKLICH loeschen? (ALLE Nutzerdaten: Show-DB, "
                "Universen, MIDI-Mappings, Gruppen, Modifier, Fixture-Bibliothek, "
                "Snaps, Buehnen, Profile, Auto-Save, Logs - nur eigene Shows in "
                f"{APPDATA_DIR / APPDATA_SHOWS} bleiben!)")
    return (f"{APPDATA_DIR}/ WIRKLICH loeschen? (ALLE Nutzerdaten: eigene Shows, "
            "Show-DB, Universen, MIDI-Mappings, Gruppen, Modifier, "
            "Fixture-Bibliothek, Snaps, Buehnen, Profile, Auto-Save, Logs!)")


def kinder_ausser(ordner: Path, behalten: tuple[str, ...]) -> list[Path]:
    """Direkte Eintraege von ``ordner`` ohne die geschuetzten Namen.

    Der Vergleich ignoriert Gross-/Kleinschreibung: unter Windows und macOS ist
    ein von Hand angelegtes ``Shows`` derselbe Ordner wie ``shows`` - die App
    speichert dorthin, ``iterdir()`` liefert aber die Schreibweise der Platte.
    """
    if not ordner.is_dir():
        return []
    schutz = {b.casefold() for b in behalten}
    return sorted(k for k in ordner.iterdir() if k.name.casefold() not in schutz)


def nicht_uebernommen(data_dir: Path) -> tuple[str, ...]:
    """Nutzerdateien in ``data/``, die im App-Datenordner (noch) fehlen.

    Der Datenumzug XPLAT-44 kopiert erst beim ersten Start nach dem Update. Lief
    LightOS seitdem nie, ist ``data/current_show.db`` kein "alter Datenstand",
    sondern der einzige - der bleibt stehen, auch unter ``--yes``.

    "Fehlt" heisst dasselbe wie beim Umzug selbst (``datenumzug.ist_uebernommen``):
    ein frisch angelegtes, inhaltlich leeres Ziel (``[]``, ``{}``, eine Show-DB
    ohne Patch) ist keine Kopie - es sei denn, der Umzugs-Marker fuehrt die
    Datei als erledigt. Ein unlesbares Ziel zaehlt ebenfalls nicht als Kopie,
    und auch nicht ein ANDERER Stand, ueber den der Umzug fuer diesen Ordner
    nie entschieden hat (zweite Installation mit schon gefuelltem App-Ordner).
    """
    if not data_dir.is_dir():
        return ()
    fehlt = []
    for name in USER_DATA_FILES:
        if not (data_dir / name).is_file():
            continue
        try:
            uebernommen = ist_uebernommen(name, str(data_dir), str(APPDATA_DIR))
        except Exception as e:      # im Zweifel bleibt der alte Stand stehen
            warn(f"{name}: Stand im App-Datenordner nicht pruefbar ({e})")
            uebernommen = False
        if not uebernommen:
            fehlt.append(name)
    return tuple(fehlt)


def data_ziele(data_dir: Path) -> tuple[list[Path], tuple[str, ...]]:
    """(zu loeschende Eintraege von ``data/``, geschuetzte Nutzerdateien)."""
    einzig = nicht_uebernommen(data_dir)
    praefixe = tuple(n.casefold() for n in einzig)
    ziele = []
    for kind in kinder_ausser(data_dir, DATA_BEHALTEN):
        # samt SQLite-Begleitdateien (-wal/-shm/-journal) der Show-DB
        if praefixe and kind.name.casefold().startswith(praefixe):
            continue
        ziele.append(kind)
    return ziele, einzig


def info(msg: str):
    print(f"[uninstall] {msg}")


def warn(msg: str):
    print(f"[uninstall] WARN: {msg}")


def load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        try:
            with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            warn(f"Manifest unlesbar: {e}")
    return {}


def confirm(prompt: str, default: bool = True) -> bool:
    suffix = " [J/n]" if default else " [j/N]"
    try:
        response = input(prompt + suffix + " ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    if not response:
        return default
    return response in ("j", "y", "ja", "yes")


def remove_path(path: Path, dry_run: bool):
    if not path.exists():
        info(f"Nicht vorhanden (skip): {path}")
        return
    if dry_run:
        info(f"WUERDE LOESCHEN: {path}")
        return
    try:
        if path.is_file() or path.is_symlink():
            path.unlink()
            info(f"Datei entfernt: {path}")
        else:
            shutil.rmtree(path)
            info(f"Verzeichnis entfernt: {path}")
    except Exception as e:
        warn(f"Konnte nicht entfernen ({path}): {e}")


def standard_verknuepfung() -> Path:
    """``LightOS.lnk`` auf dem Desktop - der Ort, an den install.py sie legt."""
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
        ) as k:
            desktop = winreg.QueryValueEx(k, "Desktop")[0]
            desktop = os.path.expandvars(desktop)
    except Exception:
        desktop = str(Path.home() / "Desktop")
    return Path(desktop) / "LightOS.lnk"


def verknuepfung_ziele(pfad: Path) -> tuple[str, ...]:
    """Ziel und Arbeitsordner einer ``.lnk`` - leer, wenn nicht ermittelbar.

    Ueber PowerShell/WScript.Shell wie install.py beim Anlegen (kein
    zusaetzliches Paket). Ausserhalb von Windows gibt es nichts aufzuloesen.
    """
    if os.name != "nt":
        return ()
    ps = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:LIGHTOS_LNK);"
          "[Console]::OutputEncoding=[Text.Encoding]::UTF8;"
          "$s.TargetPath;$s.WorkingDirectory")
    try:
        aus = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            check=True, capture_output=True, timeout=30,
            env={**os.environ, "LIGHTOS_LNK": str(pfad)},
        ).stdout.decode("utf-8", errors="replace")
    except Exception as e:
        warn(f"Ziel der Verknuepfung nicht lesbar ({pfad}): {e}")
        return ()
    return tuple(z.strip() for z in aus.splitlines() if z.strip())


def _schluessel(pfad) -> str:
    try:
        p = os.path.realpath(str(pfad))
    except (OSError, ValueError):
        p = os.path.abspath(str(pfad))
    return os.path.normcase(p)


def liegt_im_programmordner(pfad: str) -> bool:
    try:
        wurzel, p = _schluessel(ROOT), _schluessel(pfad)
        return os.path.commonpath([wurzel, p]) == wurzel
    except ValueError:              # anderes Laufwerk
        return False


def eigene_verknuepfung(manifest_pfad: str | None, ziele=None) -> Path | None:
    """Die Verknuepfung DIESER Installation - oder ``None``.

    Eigen ist sie, wenn das Manifest sie nennt oder ihr Ziel bzw. Arbeitsordner
    im eigenen Programmordner liegt. Ohne Manifest einfach ``LightOS.lnk`` vom
    Desktop zu nehmen, loeschte auf einem Rechner mit zwei Checkouts die
    Verknuepfung der ANDEREN Installation. ``ziele`` ist die Aufloesung
    (Vorgabe: ``verknuepfung_ziele``) - in Tests austauschbar.

    Auch die im Manifest genannte bleibt, wenn sie NACHWEISLICH woandershin
    zeigt: eine zweite Installation legt ihre ``LightOS.lnk`` an denselben
    Platz und ueberschreibt die erste - das Manifest der ersten nennt den Pfad
    dann weiter. Ist das Ziel nicht ermittelbar, gilt das Manifest.
    """
    if manifest_pfad:
        kandidat = Path(manifest_pfad)
        if kandidat.exists() or kandidat.is_symlink():
            gefunden = (ziele or verknuepfung_ziele)(kandidat)
            if gefunden and not any(liegt_im_programmordner(z) for z in gefunden):
                info(f"Verknuepfung wird BEHALTEN: {kandidat} zeigt inzwischen "
                     f"auf eine andere Installation ({gefunden[0]})")
                return None
        return kandidat
    kandidat = standard_verknuepfung()
    if not (kandidat.exists() or kandidat.is_symlink()):
        return None
    gefunden = (ziele or verknuepfung_ziele)(kandidat)
    if any(liegt_im_programmordner(z) for z in gefunden):
        return kandidat
    if gefunden:
        info(f"Verknuepfung wird BEHALTEN: {kandidat} zeigt auf eine andere "
             f"Installation ({gefunden[0]})")
    else:
        info(f"Verknuepfung wird BEHALTEN: {kandidat} - ohne Manifest ist nicht "
             "feststellbar, ob sie zu dieser Installation gehoert")
    return None


def remove_shortcut(shortcut: Path | None, dry_run: bool):
    """Entfernt die von ``eigene_verknuepfung`` bestaetigte Verknuepfung.

    ``None`` heisst: keine eigene gefunden - dann wird NICHTS angefasst (frueher
    fiel das auf ``LightOS.lnk`` vom Desktop zurueck, egal wem sie gehoerte).
    """
    if shortcut is not None:
        remove_path(Path(shortcut), dry_run)


def main():
    p = argparse.ArgumentParser(description="LightOS Uninstaller")
    p.add_argument("--yes", action="store_true",
                   help="Keine Rueckfragen - Installation entfernen. Der "
                        "App-Datenordner und shows/ bleiben (dafuer: --purge)")
    p.add_argument("--purge", action="store_true",
                   help="AUCH den App-Datenordner loeschen (eigene Shows, Show-DB, "
                        "MIDI-Mappings, Bibliothek, Snaps, Buehnen, Logs). Fragt "
                        "nach, ausser zusammen mit --yes")
    p.add_argument("--keep-shows", action="store_true",
                   help="Shows behalten: shows/ im Programmordner und, bei --purge, "
                        "shows/ im App-Datenordner")
    p.add_argument("--keep-appdata", action="store_true",
                   help="App-Datenordner behalten (gewinnt gegen --purge)")
    p.add_argument("--keep-venv", action="store_true",
                   help="venv/ behalten")
    p.add_argument("--dry-run", action="store_true",
                   help="Nur anzeigen, nichts loeschen")
    args = p.parse_args()

    info("=" * 60)
    info("LightOS Uninstaller")
    info("=" * 60)

    manifest = load_manifest()
    if manifest:
        info(f"Manifest gefunden (Version {manifest.get('version', '?')}, "
             f"Arch {manifest.get('arch', '?')})")
    else:
        info("Kein Manifest gefunden - nutze Default-Pfade")

    if args.dry_run:
        info("DRY-RUN: nichts wird wirklich entfernt")

    targets = []

    # 1. venv
    if not args.keep_venv:
        if args.yes or confirm(f"venv loeschen? ({VENV_DIR})"):
            targets.append(("venv", VENV_DIR))

    # 2. data/ - nur Nutzerdateien, data/controller_library gehoert zum Programm
    data_dir = ROOT / "data"
    data_aufraeumen = args.yes or confirm(DATA_FRAGE)
    if data_aufraeumen:
        ziele, einzig = data_ziele(data_dir)
        for kind in ziele:
            targets.append(("data", kind))
        if einzig:
            warn(f"data/: {', '.join(einzig)} wird BEHALTEN - LightOS hat den "
                 "Stand seit dem Update nicht in den App-Datenordner uebernommen "
                 "(dort fehlt die Datei, ist leer oder traegt einen anderen "
                 "Stand, ueber den noch nicht entschieden ist). Das kann der "
                 "einzige Stand dieser Nutzerdaten sein.")

    # 3. shows/ im Programmordner - nie ohne ausdrueckliches Ja (XPLAT-49:
    #    --yes ist kein Ja zu eigenen Shows)
    if args.keep_shows:
        info("shows/ wird BEHALTEN (--keep-shows)")
    elif args.yes:
        info("shows/ wird BEHALTEN (--yes loescht keine eigenen Shows)")
    elif confirm("shows/ loeschen? (deine eigenen .lshow Dateien im "
                 "Programmordner!)", default=False):
        targets.append(("shows", ROOT / "shows"))
    else:
        info("shows/ wird BEHALTEN")

    # 4. App-Datenordner - nur mit --purge (XPLAT-49)
    if args.keep_appdata:
        info(f"App-Datenordner wird BEHALTEN (--keep-appdata): {APPDATA_DIR}")
    elif not args.purge:
        info(f"App-Datenordner wird BEHALTEN: {APPDATA_DIR}")
        info(f"  Dort liegt: {APPDATA_INHALT}.")
        info("  Loeschen nur ausdruecklich mit --purge.")
    else:
        warn(f"--purge: der App-Datenordner {APPDATA_DIR} soll geloescht werden.")
        warn(f"  Dort liegt: {APPDATA_INHALT}.")
        if args.keep_shows:
            info(f"  --keep-shows: eigene Shows bleiben in "
                 f"{APPDATA_DIR / APPDATA_SHOWS}")
        if args.yes or confirm(appdata_frage(args.keep_shows), default=False):
            if args.keep_shows:
                # Aussparen statt vorher wegsichern: eine Kopie kann scheitern
                # oder unvollstaendig sein, ein nicht angefasster Ordner nicht.
                for kind in kinder_ausser(APPDATA_DIR, (APPDATA_SHOWS,)):
                    targets.append(("appdata", kind))
            else:
                targets.append(("appdata", APPDATA_DIR))
        else:
            info("App-Datenordner wird BEHALTEN")

    # 5. Shortcut - nur die eigene (Manifest oder Ziel im Programmordner)
    shortcut = None
    if args.yes or confirm("Desktop-Verknuepfung loeschen?"):
        # jetzt aufloesen: das Ziel liegt in venv/, das gleich geloescht wird
        shortcut = eigene_verknuepfung(manifest.get("shortcut"))
    else:
        info("Verknuepfung wird BEHALTEN")

    # 6. Pycache cleanup (immer wenn nicht --keep-venv)
    if not args.keep_venv:
        targets.append(("pycache", ROOT / "src"))  # nur __pycache__ Unterordner

    # Ausfuehren
    info("")
    info("Loesche ...")
    for label, p in targets:
        if label == "pycache":
            # Spezial: nur __pycache__/__pycache__/ Unterordner
            count = 0
            for sub in p.rglob("__pycache__"):
                remove_path(sub, args.dry_run)
                count += 1
            info(f"  {count} __pycache__ Verzeichnisse entfernt")
        else:
            remove_path(p, args.dry_run)

    # Shortcut
    remove_shortcut(shortcut, args.dry_run)

    # Manifest selbst
    if not args.keep_appdata:
        if MANIFEST_PATH.exists():
            remove_path(MANIFEST_PATH, args.dry_run)

    # data/ selbst nur, wenn nichts mehr drin ist (ohne Vorlagen-Ordner)
    if data_aufraeumen and data_dir.is_dir() and not args.dry_run:
        try:
            if not any(data_dir.iterdir()):
                data_dir.rmdir()
        except OSError:
            pass

    info("")
    info("Fertig.")
    if args.dry_run:
        info("(DRY-RUN - nichts wurde wirklich geloescht)")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        info("Abgebrochen.")
        sys.exit(1)
