r"""LightOS Installer.

Installiert alle Abhaengigkeiten in einer virtuellen Umgebung und legt
Start-Verknuepfungen sowie Default-Daten an.

Funktioniert auf Windows x64 UND ARM64.

Usage:
    python install.py [--no-venv] [--no-shortcut] [--dev]

Was wird installiert/erstellt:
- venv/                        (Python Virtual Environment, ~250 MB)
- data/                        (lokale Show-DB, MIDI-Mappings, Modifier)
- %APPDATA%/LightOS/           (Recent-Files, Stages, Input-Profile, Snapshots, Auto-Save)
- Desktop\LightOS.lnk          (optional, --no-shortcut zum Ueberspringen)
- Start-Menu\LightOS\LightOS.lnk (optional)
- install_manifest.json        (Liste aller installierten Dateien fuer uninstall.py)
"""
from __future__ import annotations
import sys
import os
import json
import shutil
import subprocess
import platform
import argparse
import re
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
VENV_DIR = ROOT / "venv"
MANIFEST_PATH = ROOT / "install_manifest.json"
APPDATA_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "LightOS"

PYTHON_MIN = (3, 11)
OPTIONAL_REQUIREMENTS = {
    "python-rtmidi",
    "winrt-windows.devices.midi",
    "winrt-windows.devices.enumeration",
    "winrt-windows.foundation",
    "winrt-windows.foundation.collections",
}


def info(msg: str):
    print(f"[install] {msg}")


def warn(msg: str):
    print(f"[install] WARN: {msg}")


def error(msg: str):
    print(f"[install] ERROR: {msg}")


def check_python():
    if sys.version_info[:2] < PYTHON_MIN:
        error(f"Python {PYTHON_MIN[0]}.{PYTHON_MIN[1]}+ erforderlich. "
              f"Aktuell: {sys.version.split()[0]}")
        sys.exit(1)
    info(f"Python {sys.version.split()[0]} OK")


def normalize_arch(raw: str | None) -> str:
    m = (raw or "").strip().lower()
    if m in ("amd64", "x86_64"):
        return "x64"
    if m in ("arm64", "aarch64"):
        return "arm64"
    if m in ("x86", "i386"):
        return "x86"
    return m or "unknown"


def detect_arch() -> str:
    """Liefert 'x64' oder 'arm64' oder 'x86' oder 'unknown'."""
    return normalize_arch(platform.machine())


def detect_native_os_arch() -> str:
    """Liefert die native OS-Architektur (auf Windows auch unter Emulation korrekt)."""
    if os.name != "nt":
        return detect_arch()
    # Unter WOW64 ist PROCESSOR_ARCHITEW6432 gesetzt und zeigt auf die native Arch.
    return normalize_arch(
        os.environ.get("PROCESSOR_ARCHITEW6432")
        or os.environ.get("PROCESSOR_ARCHITECTURE")
        or platform.machine()
    )


def check_arm_runtime():
    """Hinweise, wenn auf ARM64 ein emuliertes Python genutzt wird."""
    py_arch = detect_arch()
    os_arch = detect_native_os_arch()
    info(f"Python-Architektur: {py_arch} | OS-Architektur: {os_arch}")
    if os.name == "nt" and os_arch == "arm64" and py_arch != "arm64":
        warn(
            "Du bist auf Windows ARM64, aber Python laeuft nicht nativ als ARM64. "
            "Bitte ARM64-Python installieren, sonst laufen DMX/MIDI/Qt ggf. nur per Emulation."
        )
        warn("Empfohlen: winget install Python.Python.3.13 --arch arm64")


def create_venv():
    if VENV_DIR.exists():
        info(f"venv existiert bereits: {VENV_DIR}")
        return
    info(f"Erstelle venv in {VENV_DIR} ...")
    subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)], check=True)


def venv_python() -> str:
    if os.name == "nt":
        return str(VENV_DIR / "Scripts" / "python.exe")
    return str(VENV_DIR / "bin" / "python")


def venv_pip() -> list[str]:
    return [venv_python(), "-m", "pip"]


def _load_requirements(req_path: Path) -> list[str]:
    lines: list[str] = []
    with open(req_path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            lines.append(line)
    return lines


def _requirement_name(req_line: str) -> str:
    base = req_line.split(";", 1)[0].strip()
    return re.split(r"[<>=!~\s\[]", base, maxsplit=1)[0].lower()


def _split_requirements(lines: list[str]) -> tuple[list[str], list[str]]:
    core: list[str] = []
    optional: list[str] = []
    for line in lines:
        name = _requirement_name(line)
        if name in OPTIONAL_REQUIREMENTS:
            optional.append(line)
        else:
            core.append(line)
    return core, optional


def _install_via_temp_requirements(pip_cmd: list[str], lines: list[str], label: str) -> int:
    if not lines:
        return 0
    req_tmp = ROOT / f".tmp_{label}.requirements.txt"
    try:
        req_tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
        result = subprocess.run(pip_cmd + ["install", "-r", str(req_tmp)], capture_output=False)
        return result.returncode
    finally:
        try:
            req_tmp.unlink(missing_ok=True)
        except Exception:
            pass


def install_requirements(use_venv: bool):
    py = venv_python() if use_venv else sys.executable
    pip_cmd = [py, "-m", "pip"]

    info("Aktualisiere pip ...")
    subprocess.run(pip_cmd + ["install", "--upgrade", "pip"], check=False)

    req = ROOT / "requirements.txt"
    if not req.exists():
        error("requirements.txt fehlt!")
        sys.exit(1)

    req_lines = _load_requirements(req)
    core_reqs, optional_reqs = _split_requirements(req_lines)

    info(f"Installiere Kern-Abhaengigkeiten ({len(core_reqs)} Pakete) ...")
    core_rc = _install_via_temp_requirements(pip_cmd, core_reqs, "core")
    if core_rc != 0:
        error("Kern-Abhaengigkeiten konnten nicht vollstaendig installiert werden.")
        sys.exit(2)

    if optional_reqs:
        info(f"Installiere optionale Pakete ({len(optional_reqs)}) ...")
        opt_rc = _install_via_temp_requirements(pip_cmd, optional_reqs, "optional")
        if opt_rc != 0:
            warn(
                "Optionale Pakete konnten nicht vollstaendig installiert werden. "
                "Die App startet trotzdem, einzelne Features (MIDI 2.0 / rtmidi) "
                "koennen fehlen."
            )
            for req_line in optional_reqs:
                rc = _install_via_temp_requirements(pip_cmd, [req_line], "optional_single")
                if rc != 0:
                    warn(f"Optional nicht installiert: {req_line}")


def create_directories():
    """Legt App-Verzeichnisse an. Sammelt sie im Manifest fuer uninstall."""
    created = []
    dirs = [
        ROOT / "data",
        ROOT / "shows",
        ROOT / "fixtures" / "custom",
        APPDATA_DIR,
        APPDATA_DIR / "stages",
        APPDATA_DIR / "input_profiles",
    ]
    for d in dirs:
        if not d.exists():
            d.mkdir(parents=True, exist_ok=True)
            created.append(str(d))
            info(f"Verzeichnis erstellt: {d}")
    return created


def create_shortcut():
    """Erstellt eine Desktop-Verknuepfung (nur Windows)."""
    if os.name != "nt":
        return None
    try:
        import winreg
        # Desktop-Pfad aus Registry
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
        ) as k:
            desktop = winreg.QueryValueEx(k, "Desktop")[0]
            desktop = os.path.expandvars(desktop)
    except Exception:
        desktop = str(Path.home() / "Desktop")

    if not os.path.isdir(desktop):
        warn(f"Desktop nicht gefunden: {desktop}")
        return None

    shortcut_path = os.path.join(desktop, "LightOS.lnk")
    # pythonw.exe -> startet OHNE Konsolenfenster; Fallback auf python.exe.
    target = str(venv_python())
    pyw = target.replace("python.exe", "pythonw.exe")
    if os.path.exists(pyw):
        target = pyw
    arguments = f'"{ROOT / "main.py"}"'
    working_dir = str(ROOT)

    # Verknuepfung via PowerShell erstellen (kein zusaetzliches pip-Paket noetig)
    ps = (
        f'$ws=New-Object -ComObject WScript.Shell;'
        f'$s=$ws.CreateShortcut("{shortcut_path}");'
        f'$s.TargetPath="{target}";'
        f'$s.Arguments=\'{arguments}\';'
        f'$s.WorkingDirectory="{working_dir}";'
        f'$s.IconLocation="{ROOT / "assets" / "icons" / "lightos.ico"}";'
        f'$s.WindowStyle=7;'
        f'$s.Save();'
    )
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            check=True, capture_output=True
        )
        info(f"Verknuepfung erstellt: {shortcut_path}")
        return shortcut_path
    except Exception as e:
        warn(f"Verknuepfung fehlgeschlagen: {e}")
        return None


def write_manifest(created_dirs: list[str], shortcut: str | None):
    py_arch = detect_arch()
    os_arch = detect_native_os_arch()
    manifest = {
        "version": "1.0",
        "install_root": str(ROOT),
        "venv": str(VENV_DIR),
        "appdata": str(APPDATA_DIR),
        "directories_created": created_dirs,
        "shortcut": shortcut,
        "python_version": sys.version.split()[0],
        "python_arch": py_arch,
        "os_arch": os_arch,
        "python_emulated_on_arm64": bool(os_arch == "arm64" and py_arch != "arm64"),
        "arch": py_arch,
        "platform": platform.platform(),
    }
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    info(f"Manifest gespeichert: {MANIFEST_PATH}")


def show_summary():
    py_arch = detect_arch()
    os_arch = detect_native_os_arch()
    info("=" * 60)
    info("Installation abgeschlossen!")
    info("=" * 60)
    info(f"Python-Architektur: {py_arch}")
    info(f"OS-Architektur:     {os_arch}")
    if os.name == "nt" and os_arch == "arm64" and py_arch != "arm64":
        warn("Python laeuft emuliert auf ARM64. Fuer native Performance ARM64-Python nutzen.")
    info(f"venv:        {VENV_DIR}")
    info(f"AppData:     {APPDATA_DIR}")
    info("")
    info("Starten mit:")
    if os.name == "nt":
        info(f"  {VENV_DIR / 'Scripts' / 'python.exe'} main.py")
        info("oder Desktop-Verknuepfung doppelklicken")
    else:
        info(f"  {VENV_DIR / 'bin' / 'python'} main.py")
    info("")
    info("Beispiel-Setups (vorkonfigurierte Patches/MIDI) siehe examples/")
    info("")
    info("Deinstallieren mit:")
    info("  python uninstall.py")


def main():
    p = argparse.ArgumentParser(description="LightOS Installer")
    p.add_argument("--no-venv", action="store_true",
                   help="Direkt ins aktuelle Python installieren (kein venv)")
    p.add_argument("--no-shortcut", action="store_true",
                   help="Keine Desktop-Verknuepfung erstellen")
    p.add_argument("--dev", action="store_true",
                   help="Inklusive Dev-Dependencies (pyinstaller etc.)")
    args = p.parse_args()

    info(f"LightOS Installer - Arch: {detect_arch()}")
    check_python()
    check_arm_runtime()

    use_venv = not args.no_venv
    if use_venv:
        create_venv()
    else:
        info("Skip venv (--no-venv)")

    install_requirements(use_venv)

    if args.dev:
        py = venv_python() if use_venv else sys.executable
        info("Installiere Dev-Dependencies ...")
        subprocess.run([py, "-m", "pip", "install", "pyinstaller>=6.0.0"], check=False)

    created = create_directories()

    shortcut = None
    if not args.no_shortcut:
        shortcut = create_shortcut()

    write_manifest(created, shortcut)
    show_summary()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        error("Abgebrochen.")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        error(f"Subprocess Fehler: {e}")
        sys.exit(2)
