r"""LightOS Installer.

Installiert alle Abhaengigkeiten in einer virtuellen Umgebung und legt eine
Desktop-Verknuepfung sowie Default-Daten an.

Funktioniert auf Windows x64 und auf Windows-ARM mit x64-Python (per
Emulation, XPLAT-46). Natives ARM64-Python ist nicht unterstuetzt (instabil,
kein 3D) - x64-Python nehmen (XPLAT-51). Der Installer bricht dann ab
(Exit-Code 3) und nennt den Weg zu x64-Python (Entscheidung E-2, XPLAT-56).
Massgeblich ist das Python, mit dem LightOS danach laeuft: bleibt ein
vorhandenes x64-venv stehen, laeuft er auch mit ARM64-Python durch.
``--arm64-trotzdem`` umgeht den Abbruch - nur fuer Tests und Entwicklung.

Usage:
    python install.py [--no-venv] [--no-shortcut] [--dev] [--neu-venv]
    py -3.12 install.py ...      (Windows mit mehreren Pythons: Version waehlen)

Was wird installiert/erstellt:
- venv/                        (Python Virtual Environment, ~250 MB)
- data/                        (nur mitgelieferte Vorlagen, z. B. controller_library/)
- App-Datenordner              (ALLE Nutzerdaten seit XPLAT-44: Shows, Show-DB,
                               universes.json, MIDI-Mappings, Modifier, Recent-Files,
                               Stages, Input-Profile, Snapshots, Auto-Save)
                               Windows %APPDATA%/LightOS, Linux ~/.local/share/LightOS,
                               macOS ~/Library/Application Support/LightOS — aufgeloest
                               von src/core/paths.app_data_dir() (XPLAT-04/-10)
- Desktop\LightOS.lnk          (nur Windows; Standard, OHNE Rueckfrage —
                               --no-shortcut laesst sie weg)
- install_manifest.json        (Liste aller installierten Dateien fuer uninstall.py)

Eine Startmenue-Verknuepfung legt das Script NICHT an (DOC-62: hier stand bis
2026-10-08 eine, die es nie gab). Die Test-Abhaengigkeiten (pytest & Co.,
``requirements-dev.txt``) installiert es ebenfalls nicht — auch nicht mit
``--dev`` (das holt nur pyinstaller); s. INSTALL.md „Entwickeln und Tests".
"""
from __future__ import annotations
import sys
import os
import json
import shutil
import subprocess
import platform
import sysconfig
import argparse
import re
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
VENV_DIR = ROOT / "venv"
MANIFEST_PATH = ROOT / "install_manifest.json"
# XPLAT-10: Datenordner ueber die zentrale Aufloesung, nicht selbst gebaut — sonst
# legt der Installer auf Linux ~/LightOS/{stages,input_profiles,snaps} an, waehrend
# die App ihre Daten nach ~/.local/share/LightOS schreibt. src/core/paths importiert
# nur os+sys, laeuft also auch hier vor dem venv mit dem System-Python.
# STAB-39: Installer legt die Ordner der App an — bewusst am echten Datenordner (nur als
# Skript; beim Import aus Tests bleibt es bei deren Sandkasten).
if __name__ == "__main__":
    os.environ.setdefault("LIGHTOS_ECHTE_DATEN", "1")
sys.path.insert(0, str(ROOT))
from src.core.paths import app_data_dir            # noqa: E402

APPDATA_DIR = Path(app_data_dir())

PYTHON_MIN = (3, 11)
OPTIONAL_REQUIREMENTS = {
    "python-rtmidi",
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


# IMAGE_FILE_MACHINE_* Konstanten (winnt.h) fuer IsWow64Process2.
_IMAGE_MACHINE = {
    0x0: "unknown",
    0x14C: "x86",
    0x1C4: "arm",     # ARMNT (32-bit)
    0x8664: "x64",    # AMD64
    0xAA64: "arm64",  # ARM64
}


def normalize_arch(raw: str | None) -> str:
    m = (raw or "").strip().lower()
    if m in ("amd64", "x86_64", "x64", "win-amd64"):
        return "x64"
    if m in ("arm64", "aarch64", "win-arm64"):
        return "arm64"
    if m in ("x86", "i386", "win32"):
        return "x86"
    return m or "unknown"


def detect_python_arch() -> str:
    """Architektur des LAUFENDEN Python-Interpreters (= welche Wheels gelten).

    Nutzt sysconfig.get_platform() ('win-amd64' / 'win-arm64' / 'win32'), das auch
    unter ARM64-Emulation korrekt den Interpreter-Build meldet. platform.machine()
    ist hier unzuverlaessig (liefert auf emuliertem x64-Python teils 'ARM64').
    """
    plat = sysconfig.get_platform()
    if plat == "win32":
        return "x86"
    if plat.startswith("win-"):
        return normalize_arch(plat.split("-", 1)[1])
    return normalize_arch(platform.machine())


# Rueckwaerts-kompatibler Alias: "die" Arch meint die des Interpreters.
def detect_arch() -> str:
    """Liefert 'x64' oder 'arm64' oder 'x86' oder 'unknown' (Interpreter-Arch)."""
    return detect_python_arch()


def _windows_native_machine() -> str | None:
    """Native OS-Architektur via IsWow64Process2 (zuverlaessig auch unter Emulation).

    Liefert None, wenn die API nicht verfuegbar ist oder der Aufruf scheitert.
    """
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes
        k = ctypes.windll.kernel32
        k.IsWow64Process2.restype = wintypes.BOOL
        k.IsWow64Process2.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.USHORT),
            ctypes.POINTER(wintypes.USHORT),
        ]
        proc = wintypes.USHORT(0)
        native = wintypes.USHORT(0)
        if not k.IsWow64Process2(
            k.GetCurrentProcess(), ctypes.byref(proc), ctypes.byref(native)
        ):
            return None
        arch = _IMAGE_MACHINE.get(native.value)
        return arch if arch and arch != "unknown" else None
    except Exception:
        return None


def detect_native_os_arch() -> str:
    """Liefert die native OS-Architektur (auf Windows auch unter Emulation korrekt)."""
    if os.name != "nt":
        return normalize_arch(platform.machine())
    native = _windows_native_machine()
    if native:
        return native
    # Fallback: Umgebungsvariablen (klassisches WOW64 setzt PROCESSOR_ARCHITEW6432).
    return normalize_arch(
        os.environ.get("PROCESSOR_ARCHITEW6432")
        or os.environ.get("PROCESSOR_ARCHITECTURE")
        or platform.machine()
    )


# XPLAT-46 (Entscheidung 05.10.2026): auf Windows-ARM ist x64-Python der
# empfohlene Weg. Die nativen win_arm64-Wheels von PySide6-Addons haben kein
# QtWebEngine (XPLAT-45) - mit ARM64-Python fehlt der 3D-Visualizer.
# XPLAT-51: dazu stuerzte LightOS mit einem ARM64-venv in 6 von 12 Starts ab
# (Access Violation nach 8,6 bis 9,5 s, wechselnde Stelle im Hauptthread), mit
# x64-Python und derselben PySide6-Version nie. Natives ARM64-Python gilt
# deshalb als nicht unterstuetzt. XPLAT-56 (Entscheidung E-2, 25.10.2026): der
# Installer bricht ab, wenn LightOS danach mit nativem ARM64-Python liefe
# (Exit-Code ARM64_EXIT_CODE); die Startskripte warnen weiter nur.
ARM64_NICHT_UNTERSTUETZT = (
    "Natives ARM64-Python ist nicht unterstuetzt (instabil, kein 3D) - "
    "x64-Python nehmen.")
X64_PYTHON_BEFEHL = "winget install Python.Python.3.12 --architecture x64"
# Codex #967: "py -3.12-64" heisst seit Python 3.11 nur "nicht 32-bit" und
# waehlt bei parallel installiertem ARM64-Python nicht sicher x64. Eindeutig
# ist der Pfad des x64-Interpreters (Standardort des python.org-/winget-
# Installers; ARM64 liegt in "Python312-arm64").
X64_PYTHON_STANDARDPFAD = r"%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
#: Exit-Code beim Abbruch wegen nativem ARM64-Python (1/2 sind schon vergeben).
ARM64_EXIT_CODE = 3
#: Ausnahme-Schalter gegen den Abbruch - nur fuer Tests und Entwicklung.
ARM64_TROTZDEM_SCHALTER = "--arm64-trotzdem"

# Zeilen aus "py -0p": " -V:3.12 *   C:\...\python.exe" (py >= 3.11) bzw.
# " -3.12-64   C:\...\python.exe" (aelterer Launcher).
_PY_LISTE_ZEILE = re.compile(r"^\s*-(?:V:)?(?P<tag>\S+?)\s+(?:\*\s+)?(?P<pfad>\S.*?\.exe)\s*$",
                             re.IGNORECASE)


def x64_python_aus_liste(ausgabe: str) -> str | None:
    """Pfad eines x64-Python aus der Ausgabe von ``py -0p`` (oder None).

    Der python.org-Installer registriert x64 als Tag "3.12", ARM64 als
    "3.12-arm64" und 32-bit als "3.12-32" (aeltere Launcher: "3.12-64").
    Der Python-Install-Manager (Standard ab 3.14) schreibt den optionalen
    Zusatz in eckigen Klammern: "3.14[-64]" - gemessen am Windows-ARM-PC,
    ohne die Klammern zu entfernen fand die Suche dort kein x64-Python."""
    for zeile in (ausgabe or "").splitlines():
        m = _PY_LISTE_ZEILE.match(zeile)
        if not m:
            continue
        tag = m.group("tag").lower().split("/")[-1]
        tag = tag.replace("[", "").replace("]", "")
        pfad = m.group("pfad").strip()
        if "arm64" in tag or "arm64" in pfad.lower() or tag.endswith("-32"):
            continue
        if re.fullmatch(r"3\.\d+(-64)?", tag):
            return pfad
    return None


def finde_x64_python() -> str | None:
    """Sucht per py-Launcher ein installiertes x64-Python (nur Windows)."""
    if os.name != "nt":
        return None
    try:
        r = subprocess.run(["py", "-0p"], capture_output=True, text=True, timeout=20)
    except Exception:
        return None
    return x64_python_aus_liste((r.stdout or "") + "\n" + (r.stderr or ""))


def x64_installer_aufruf(pfad: str | None = None) -> str:
    """Eindeutiger Befehl, um install.py mit x64-Python neu zu starten; baut
    ein vorhandenes (ARM64-)venv dabei neu (``--neu-venv``)."""
    return f'"{pfad or X64_PYTHON_STANDARDPFAD}" install.py --neu-venv'


def auf_windows_arm() -> bool:
    """True auf Windows mit ARM64-Prozessor (egal, welches Python laeuft)."""
    return os.name == "nt" and detect_native_os_arch() == "arm64"


def voraussichtliche_ziel_arch(use_venv: bool = True, neu_venv: bool = False) -> str:
    """Architektur des Python, mit dem LightOS nach diesem Lauf liefe - VOR
    ``create_venv`` (XPLAT-56).

    Ein vorhandenes venv bekannter Architektur bleibt, wenn nicht ``--neu-venv``
    gesetzt ist (mit ARM64-Python baut ``create_venv`` es nicht um, s. dort):
    dann zaehlt das venv. Sonst - kein venv, venv nicht startbar, ``--neu-venv``
    oder ``--no-venv`` - das Python, das install.py ausfuehrt: in dieses wird
    installiert bzw. aus ihm entsteht das neue venv. Ein vorhandenes, aber
    nicht startbares venv zaehlt damit wie "kein venv" - seine Architektur ist
    nicht belegbar, also gilt das ausfuehrende (im Zweifel Abbruch)."""
    if use_venv and not neu_venv:
        va = venv_arch()
        if va != "unknown":
            return va
    return detect_arch()


def x64_weg(pfad: str | None = None) -> str:
    """Anleitung "x64-Python installieren, dann install.py damit neu"."""
    return (f"x64-Python installieren ({X64_PYTHON_BEFEHL}), "
            f"dann: {x64_installer_aufruf(pfad)}")


def arm64_abbruch(grund: str, weg: str, trotzdem: bool = False):
    """Bricht den Installer mit ``ARM64_EXIT_CODE`` ab (XPLAT-56) - ausser mit
    ``--arm64-trotzdem`` (nur Tests/Entwicklung), dann nur eine Warnung."""
    if trotzdem:
        warn(f"{grund} {ARM64_NICHT_UNTERSTUETZT} Laeuft wegen "
             f"{ARM64_TROTZDEM_SCHALTER} trotzdem weiter - nur fuer Tests/Entwicklung.")
        return
    error(f"{grund} {ARM64_NICHT_UNTERSTUETZT}")
    error(f"Installation abgebrochen (Exit-Code {ARM64_EXIT_CODE}). So geht es: {weg}")
    raise SystemExit(ARM64_EXIT_CODE)


def pruefe_arm64_vorab(use_venv: bool = True, neu_venv: bool = False,
                       trotzdem: bool = False):
    """Abbruch vor dem ersten Schritt, wenn install.py mit nativem ARM64-Python
    laeuft und LightOS danach damit liefe (neues venv, ``--neu-venv``,
    ``--no-venv``, kein startbares venv). Bleibt ein x64-venv stehen, laeuft
    der Lauf durch: pip und LightOS nutzen dann das x64-Python des venv.

    Der umgekehrte Mischfall (x64-Python, vorhandenes ARM64-venv) entscheidet
    sich erst an der Rueckfrage in ``create_venv`` - dafuer ``pruefe_arm64_ziel``."""
    if not auf_windows_arm() or detect_arch() != "arm64":
        return
    if voraussichtliche_ziel_arch(use_venv, neu_venv) != "arm64":
        return
    grund = ("install.py laeuft mit nativem ARM64-Python, und LightOS liefe danach "
             + ("damit (--no-venv)." if not use_venv else "mit einem ARM64-venv."))
    arm64_abbruch(grund, x64_weg(finde_x64_python()), trotzdem)


def pruefe_arm64_ziel(use_venv: bool = True, trotzdem: bool = False):
    """Abbruch nach ``create_venv``, wenn das venv (bzw. bei ``--no-venv`` das
    ausfuehrende Python) nativ ARM64 ist - etwa ein vorhandenes ARM64-venv, das
    ein x64-Installer nicht neu anlegen durfte (Rueckfrage mit Nein, kein
    Terminal). Ohne venv-Neubau gibt es keinen Grund, Pakete hineinzulegen."""
    if not auf_windows_arm() or ziel_arch(use_venv) != "arm64":
        return
    if use_venv and detect_arch() != "arm64":
        grund = "Das vorhandene venv ist natives ARM64-Python und wurde nicht neu angelegt."
        weg = (f"venv mit diesem x64-Python neu anlegen: "
               f"{x64_installer_aufruf(sys.executable)}")
    else:
        grund = "LightOS liefe mit nativem ARM64-Python."
        weg = x64_weg(finde_x64_python())
    arm64_abbruch(grund, weg, trotzdem)


def check_arm_runtime(use_venv: bool = True, neu_venv: bool = False,
                      trotzdem: bool = False):
    """Hinweise zur Python-Architektur auf Windows-ARM (XPLAT-46/-56).

    Nur Ausgabe - abgebrochen wird in ``pruefe_arm64_vorab``/``pruefe_arm64_ziel``.
    Der Warnblock betrifft das Python, das install.py ausfuehrt. Bleibt ein
    vorhandenes venv anderer Architektur stehen, sagt ein Zusatz, was fuer das
    venv gilt - sonst widersprachen sich Anfang und Zusammenfassung eines Laufs
    (Gegenpruefung XPLAT-52)."""
    py_arch = detect_arch()
    os_arch = detect_native_os_arch()
    info(f"Python-Architektur: {py_arch} | OS-Architektur: {os_arch}")
    if os.name != "nt" or os_arch != "arm64":
        return
    va = venv_arch() if use_venv and not neu_venv else "unknown"
    if va == py_arch:
        va = "unknown"
    if py_arch == "arm64":
        warn("!" * 60)
        warn(ARM64_NICHT_UNTERSTUETZT)
        warn(
            "Instabil: mit nativem ARM64-Python stuerzte LightOS in 6 von 12 "
            "Starts ab (Access Violation). Kein 3D-Visualizer: die ARM64-Pakete von "
            "PySide6-Addons enthalten kein QtWebEngine. python-rtmidi baut hier "
            "nur mit MSVC Build Tools (MIDI geht sonst ueber den WinMM-Weg)."
        )
        warn(f"So geht es: {x64_weg(finde_x64_python())}")
        if va != "unknown":
            if trotzdem:
                warn(f"Das gilt fuer dieses Python. Das vorhandene venv ist {va}-Python "
                     "und bleibt, wenn es nicht neu angelegt wird (Rueckfrage folgt) - "
                     f"LightOS laeuft dann mit {va}-Python.")
            else:
                warn(f"Das gilt fuer dieses Python. Das vorhandene venv ist {va}-Python "
                     "und bleibt (mit ARM64-Python wird es nicht neu angelegt) - "
                     f"LightOS laeuft mit {va}-Python, die Installation laeuft weiter.")
        elif trotzdem:
            warn(f"Die Installation laeuft wegen {ARM64_TROTZDEM_SCHALTER} weiter - "
                 "nur fuer Tests/Entwicklung, auf eigenes Risiko.")
        else:
            warn(f"Die Installation bricht deshalb ab (Exit-Code {ARM64_EXIT_CODE}).")
        warn("!" * 60)
    else:
        info("x64-Python unter Emulation auf Windows-ARM - empfohlener Weg, "
             "der 3D-Visualizer ist verfuegbar.")
        if va == "arm64":
            warn(f"Das vorhandene venv ist ARM64-Python. {ARM64_NICHT_UNTERSTUETZT} "
                 "Bei der folgenden Rueckfrage mit j antworten "
                 "(oder: install.py --neu-venv), sonst bricht die Installation ab.")


def venv_arch() -> str:
    """Architektur des Python im vorhandenen venv ('unknown', wenn es sich
    nicht starten laesst)."""
    py = venv_python()
    if not Path(py).exists():
        return "unknown"
    try:
        r = subprocess.run([py, "-c", "import sysconfig; print(sysconfig.get_platform())"],
                           capture_output=True, text=True, timeout=60)
    except Exception:
        return "unknown"
    plat = (r.stdout or "").strip().lower()
    if r.returncode != 0 or not plat:
        return "unknown"
    if plat == "win32":
        return "x86"
    # 'win-amd64' -> 'amd64'; sonst steht die Maschine am Ende:
    # 'linux-x86_64' -> 'x86_64', 'macosx-14.0-arm64' -> 'arm64'.
    return normalize_arch(plat.rsplit("-", 1)[-1])


def _frage_ja(frage: str) -> bool:
    """Ja/Nein-Rueckfrage; ohne Terminal (Skript, CI) immer Nein."""
    try:
        if not sys.stdin or not sys.stdin.isatty():
            return False
        return input(f"{frage} [j/N] ").strip().lower() in ("j", "ja", "y", "yes")
    except (EOFError, OSError):
        return False


def create_venv(neu: bool = False, trotzdem: bool = False):
    """Legt das venv an. Ein vorhandenes bleibt — ausser ``neu`` (``--neu-venv``)
    oder es wurde mit einer ANDEREN Architektur gebaut als das Python, das
    gerade install.py ausfuehrt (Codex #967: wer auf Windows-ARM nach dem
    Hinweis x64-Python installiert, behielt sonst sein ARM64-venv und damit
    weiter keinen 3D-Visualizer); dann wird nachgefragt.

    XPLAT-56: mit nativem ARM64-Python auf Windows-ARM wird kein venv gebaut
    (ausser ``trotzdem``) - ein vorhandenes x64-venv bleibt ohne Rueckfrage,
    ein Neubau bricht ab (Absicherung hinter ``pruefe_arm64_vorab``)."""
    arm64_schutz = auf_windows_arm() and detect_arch() == "arm64" and not trotzdem
    if VENV_DIR.exists():
        if not neu:
            va, pa = venv_arch(), detect_arch()
            if arm64_schutz and va not in ("unknown", "arm64"):
                info(f"Das vorhandene venv ist {va}-Python und bleibt - mit nativem "
                     "ARM64-Python wird es nicht neu angelegt (XPLAT-56).")
            elif va != "unknown" and pa != "unknown" and va != pa:
                warn(f"Das vorhandene venv wurde mit {va}-Python gebaut, "
                     f"install.py laeuft mit {pa}-Python.")
                neu = _frage_ja("venv mit diesem Python neu anlegen?")
                if not neu:
                    warn("venv bleibt unveraendert. Neu anlegen mit: "
                         "python install.py --neu-venv (mit dem gewuenschten Python).")
        if not neu:
            info(f"venv existiert bereits: {VENV_DIR}")
            return
        if arm64_schutz:
            arm64_abbruch("Ein neues venv entstuende aus nativem ARM64-Python.",
                          x64_weg(finde_x64_python()))
        info(f"Entferne altes venv: {VENV_DIR}")
        shutil.rmtree(VENV_DIR)
    if arm64_schutz:
        arm64_abbruch("Ein neues venv entstuende aus nativem ARM64-Python.",
                      x64_weg(finde_x64_python()))
    info(f"Erstelle venv in {VENV_DIR} ...")
    subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)], check=True)


def venv_python() -> str:
    if os.name == "nt":
        return str(VENV_DIR / "Scripts" / "python.exe")
    return str(VENV_DIR / "bin" / "python")


def venv_pip() -> list[str]:
    return [venv_python(), "-m", "pip"]


def verknuepfung_python(use_venv: bool = True, executable: str | None = None) -> str:
    """XPLAT-48: das Python fuer die Desktop-Verknuepfung — ``pythonw.exe``
    (startet ohne Konsolenfenster), sonst ``python.exe`` daneben.

    Mit ``--no-venv`` gibt es kein ``venv/``: dann das Python, in das gerade
    installiert wurde (``sys.executable``). Vorher zeigte die Verknuepfung
    auch dann auf ``venv\\Scripts\\pythonw.exe`` — also ins Leere."""
    python = venv_python() if use_venv else (executable or sys.executable)
    pyw = os.path.join(os.path.dirname(python), "pythonw.exe")
    return pyw if os.path.exists(pyw) else python


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
                "Die App startet trotzdem, einzelne Features (MIDI ueber python-rtmidi) "
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
        APPDATA_DIR / "snaps",
    ]
    for d in dirs:
        if not d.exists():
            d.mkdir(parents=True, exist_ok=True)
            created.append(str(d))
            info(f"Verzeichnis erstellt: {d}")
    return created


def create_shortcut(use_venv: bool = True):
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
    target = verknuepfung_python(use_venv)
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
        info("  (ohne Verknuepfung installieren: --no-shortcut)")
        return shortcut_path
    except Exception as e:
        warn(f"Verknuepfung fehlgeschlagen: {e}")
        return None


def ziel_arch(use_venv: bool = True) -> str:
    """Architektur des Python, mit dem LightOS laufen wird (XPLAT-52).

    Bei vorhandenem venv ist das dessen Architektur (``venv_arch()``) - nicht
    die des Python, das install.py ausfuehrt: bleibt ein x64-venv stehen und
    install.py laeuft mit ARM64-Python (oder umgekehrt), zaehlt das venv.
    Ohne venv (``--no-venv`` oder venv nicht startbar) das ausfuehrende."""
    if use_venv:
        va = venv_arch()
        if va != "unknown":
            return va
    return detect_arch()


def write_manifest(created_dirs: list[str], shortcut: str | None,
                   use_venv: bool = True):
    py_arch = ziel_arch(use_venv)
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
        "installer_python_arch": detect_arch(),
        "platform": platform.platform(),
    }
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    info(f"Manifest gespeichert: {MANIFEST_PATH}")


def show_summary(use_venv: bool = True):
    py_arch = ziel_arch(use_venv)
    installer_arch = detect_arch()
    os_arch = detect_native_os_arch()
    # Mit --no-venv gibt es kein venv/: die Befehle nennen dann das Python, in
    # das installiert wurde (Codex-Review zu DOC-62).
    py = venv_python() if use_venv else sys.executable
    info("=" * 60)
    info("Installation abgeschlossen!")
    info("=" * 60)
    info(f"Python-Architektur: {py_arch}" + (" (venv)" if use_venv else ""))
    if py_arch != installer_arch:
        info(f"install.py lief mit:  {installer_arch}-Python")
    info(f"OS-Architektur:     {os_arch}")
    if os.name == "nt" and os_arch == "arm64" and py_arch == "arm64":
        warn(f"{ARM64_NICHT_UNTERSTUETZT} Mit x64-Python geht alles "
             f"({X64_PYTHON_BEFEHL}, dann {x64_installer_aufruf()}).")
    info(f"venv:        {VENV_DIR if use_venv else '- (--no-venv)'}")
    info(f"AppData:     {APPDATA_DIR}")
    info("")
    info("Starten mit:")
    info(f"  {py} main.py")
    if os.name == "nt":
        info("oder Desktop-Verknuepfung doppelklicken")
    info("")
    info("Beispiel-Setups (vorkonfigurierte Patches/MIDI) siehe examples/")
    info("")
    info("Testsuite (nur fuer Entwicklung) braucht zusaetzlich:")
    info(f"  {py} -m pip install -r requirements-dev.txt")
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
    p.add_argument("--neu-venv", action="store_true",
                   help="Vorhandenes venv loeschen und mit diesem Python neu anlegen "
                        "(z. B. nach dem Wechsel auf x64-Python auf Windows-ARM)")
    p.add_argument(ARM64_TROTZDEM_SCHALTER, dest="arm64_trotzdem", action="store_true",
                   help="NUR fuer Tests/Entwickler: auf Windows-ARM trotz nativem "
                        "ARM64-Python weiterinstallieren statt abzubrechen (nicht "
                        "unterstuetzt: instabil, kein 3D - XPLAT-51/-56)")
    args = p.parse_args()

    info(f"LightOS Installer - Arch: {detect_arch()}")
    check_python()
    use_venv = not args.no_venv
    trotzdem = args.arm64_trotzdem
    check_arm_runtime(use_venv, args.neu_venv, trotzdem=trotzdem)
    pruefe_arm64_vorab(use_venv, args.neu_venv, trotzdem=trotzdem)

    if use_venv:
        create_venv(neu=args.neu_venv, trotzdem=trotzdem)
    else:
        info("Skip venv (--no-venv)")
    pruefe_arm64_ziel(use_venv, trotzdem=trotzdem)

    install_requirements(use_venv)

    if args.dev:
        py = venv_python() if use_venv else sys.executable
        info("Installiere Dev-Dependencies ...")
        subprocess.run([py, "-m", "pip", "install", "pyinstaller>=6.0.0"], check=False)

    created = create_directories()

    shortcut = None
    if not args.no_shortcut:
        shortcut = create_shortcut(use_venv)

    write_manifest(created, shortcut, use_venv)
    show_summary(use_venv)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        error("Abgebrochen.")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        error(f"Subprocess Fehler: {e}")
        sys.exit(2)
