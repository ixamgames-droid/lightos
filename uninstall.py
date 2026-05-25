r"""LightOS Uninstaller.

Entfernt was install.py angelegt hat. Liest install_manifest.json wenn vorhanden,
sonst Fallback auf bekannte Pfade.

Was wird entfernt (optional pro Bereich abfragbar):
- venv/                  (Virtual Environment)
- data/                  (lokale Show-DB, Mappings, Modifier)
- shows/                 (eigene Shows - per Default ERHALTEN, --shows zum Loeschen)
- %APPDATA%/LightOS/     (Snapshots, Stages, Profile, Auto-Save)
- Desktop\LightOS.lnk
- install_manifest.json

Usage:
    python uninstall.py                  (interaktiv - fragt jeden Bereich)
    python uninstall.py --yes            (alles ohne Rueckfrage entfernen)
    python uninstall.py --keep-shows     (Shows behalten)
    python uninstall.py --keep-appdata   (AppData behalten)
    python uninstall.py --dry-run        (nur anzeigen was geloescht wuerde)
"""
from __future__ import annotations
import os
import sys
import json
import shutil
import argparse
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
MANIFEST_PATH = ROOT / "install_manifest.json"
APPDATA_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "LightOS"
VENV_DIR = ROOT / "venv"


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


def remove_shortcut(shortcut_path: str | None, dry_run: bool):
    if not shortcut_path:
        # Versuch auf bekanntem Pfad
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
        shortcut_path = os.path.join(desktop, "LightOS.lnk")
    p = Path(shortcut_path)
    remove_path(p, dry_run)


def main():
    p = argparse.ArgumentParser(description="LightOS Uninstaller")
    p.add_argument("--yes", action="store_true",
                   help="Keine Rueckfragen - alles entfernen (ausser explizit ausgeschlossen)")
    p.add_argument("--keep-shows", action="store_true",
                   help="shows/ behalten")
    p.add_argument("--keep-appdata", action="store_true",
                   help="%%APPDATA%%/LightOS/ behalten")
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

    # 2. data/
    if args.yes or confirm(f"data/ loeschen? (Show-DB, MIDI-Mappings, Modifier)"):
        targets.append(("data", ROOT / "data"))

    # 3. shows/
    if not args.keep_shows:
        if confirm("shows/ loeschen? (deine eigenen .lshow Dateien!)", default=False):
            targets.append(("shows", ROOT / "shows"))
        else:
            info("shows/ wird BEHALTEN")
    else:
        info("shows/ wird BEHALTEN (--keep-shows)")

    # 4. AppData
    if not args.keep_appdata:
        if args.yes or confirm(f"%APPDATA%/LightOS/ loeschen? (Snapshots, Stages, Profile, Auto-Save)"):
            targets.append(("appdata", APPDATA_DIR))

    # 5. Shortcut
    shortcut = manifest.get("shortcut")
    if args.yes or confirm("Desktop-Verknuepfung loeschen?"):
        info(f"Suche Verknuepfung: {shortcut or '(default)'}")
        # Wird unten gesondert behandelt
    else:
        shortcut = None
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
    if shortcut is not None or (args.yes and not args.keep_appdata):
        remove_shortcut(shortcut, args.dry_run)

    # Manifest selbst
    if not args.dry_run and not args.keep_appdata:
        if MANIFEST_PATH.exists():
            try:
                MANIFEST_PATH.unlink()
                info(f"Manifest entfernt: {MANIFEST_PATH}")
            except Exception:
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
