"""XPLAT-46: Plattform-Hinweise fuer Windows-ARM (Snapdragon).

Die nativen ``win_arm64``-Wheels von PySide6-Addons bringen KEIN QtWebEngine
mit (XPLAT-45, gemessen an 6.11.2) - mit nativem ARM64-Python fehlt also der
3D-Visualizer. Emuliertes x64-Python hat alles. Entscheidung des
Projektinhabers vom 05.10.2026: auf Windows-ARM wird x64-Python empfohlen,
ARM64-Python nur als Hinweis "ohne 3D".

Die Architektur des INTERPRETERS kommt aus ``sysconfig.get_platform()``;
``platform.machine()`` meldet auf emuliertem x64-Python teils 'ARM64' (Host).
"""
from __future__ import annotations

import os
import platform
import sysconfig

#: Ein Befehl, den die Hinweise woertlich nennen (winget kennt ``--architecture``).
X64_PYTHON_BEFEHL = "winget install Python.Python.3.12 --architecture x64"
#: Eindeutiger Aufruf mit dem x64-Interpreter (Codex #967: "py -3.12-64"
#: waehlt seit 3.11 auch ARM64) - ``--neu-venv`` baut das ARM64-venv neu.
X64_INSTALLER_AUFRUF = (
    r'"%LOCALAPPDATA%\Programs\Python\Python312\python.exe" install.py --neu-venv')


def _normiere(arch: str) -> str:
    a = (arch or "").strip().lower()
    if a.endswith("arm64") or a.endswith("aarch64"):
        return "arm64"
    if a.endswith("amd64") or a.endswith("x86_64") or a == "x64":
        return "x64"
    if a in ("x86", "i386", "i686", "win32"):
        return "x86"
    return a or "unknown"


def interpreter_arch() -> str:
    """'arm64' / 'x64' / 'x86' des laufenden Python - auch unter Emulation richtig."""
    return _normiere(sysconfig.get_platform())


def os_arch() -> str:
    """Architektur des Betriebssystems ('arm64' auf Snapdragon, auch unter Emulation)."""
    return _normiere(
        os.environ.get("PROCESSOR_ARCHITEW6432")
        or os.environ.get("PROCESSOR_ARCHITECTURE")
        or platform.machine()
    )


def ist_windows_arm_nativ(*, system: str | None = None,
                          py_arch: str | None = None) -> bool:
    """True, wenn LightOS mit nativem ARM64-Python unter Windows laeuft
    (der Fall ohne QtWebEngine)."""
    system = os.name if system is None else system
    py_arch = interpreter_arch() if py_arch is None else py_arch
    return system == "nt" and py_arch == "arm64"


def visualizer_startfehler_text(exc: BaseException | None = None, *,
                                system: str | None = None,
                                py_arch: str | None = None) -> str:
    """Text fuer die Meldung "Visualizer nicht verfuegbar".

    Auf Windows mit nativem ARM64-Python ist ein Importfehler die erwartete
    Folge der fehlenden QtWebEngine - "PySide6-Addons neu installieren" hilft
    dort nicht, nur x64-Python. Jeder andere Fall behaelt den alten Rat.
    """
    kopf = "Der 3D-Visualizer konnte nicht gestartet werden.\n\n"
    if isinstance(exc, ImportError) and ist_windows_arm_nativ(
            system=system, py_arch=py_arch):
        return (
            kopf
            + "LightOS laeuft hier mit nativem ARM64-Python. Dessen PySide6-"
            "Pakete enthalten kein QtWebEngine - ohne das gibt es keinen "
            "3D-Visualizer.\n\n"
            "Abhilfe: x64-Python installieren (laeuft auf Windows-ARM per "
            "Emulation, mit allen Funktionen) und install.py damit erneut "
            "ausfuehren - \"--neu-venv\" ersetzt das vorhandene ARM64-venv, "
            "ohne das bliebe es bestehen:\n"
            f"    {X64_PYTHON_BEFEHL}\n"
            f"    {X64_INSTALLER_AUFRUF}\n"
            "(\"py -0p\" zeigt alle Pythons mit Pfad; das x64-Python ist der "
            "Eintrag OHNE \"-arm64\".)\n\n"
            "Pruefen: python tools/qt_module_befund.py"
        )
    return kopf + "Bitte prüfe, ob PySide6 + PySide6-Addons korrekt installiert sind."
