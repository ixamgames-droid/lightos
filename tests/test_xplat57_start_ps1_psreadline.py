"""XPLAT-57: start.ps1 erkennt die Architektur auch in einer interaktiven
Windows PowerShell 5.1.

Dort ist PSReadLine 2.0 geladen. Dessen DLL bringt einen eigenen Typ
``System.Runtime.InteropServices.RuntimeInformation`` ohne ``OSArchitecture``
mit, und der Kurzname im Skript loeste auf ihn auf. ``OSArchitecture`` und
``ProcessArchitecture`` waren dann still leer. Auf Windows-ARM fiel dadurch die
Warnung vor nativem ARM64-Python (XPLAT-51) genau dort aus, wo man das Skript
meist startet: mit ``.\\start.ps1`` aus einem offenen PowerShell-Fenster.
Gemessen am 29.10.2026 auf Windows 11 ARM.

Nachgestellt wird das ohne Fenster: ``Import-Module PSReadLine`` und danach das
Skript aufrufen.
"""
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
START_PS1 = ROOT / "start.ps1"
_KOPF = re.compile(r"\[start\] OS-Arch: (\S*) \| Prozess-Arch: (\S*)")


def _text() -> str:
    return START_PS1.read_bytes().decode("utf-8")


def test_typ_kommt_unter_windows_powershell_aus_mscorlib():
    text = _text()
    assert "RuntimeInformation, mscorlib" in text
    assert not re.search(
        r"\[System\.Runtime\.InteropServices\.RuntimeInformation\]::OSArchitecture",
        text), "Kurzname liefert mit PSReadLine 2.0 einen Typ ohne OSArchitecture"


def test_rueckfall_ueber_die_prozessor_kennung_wie_start_bat():
    text = _text()
    assert "PROCESSOR_IDENTIFIER" in text and "ARMv8" in text
    rueckfall = text.index("PROCESSOR_IDENTIFIER")
    assert rueckfall < text.index('Write-Host "[start] OS-Arch'), \
        "der Rueckfall muss vor der Kopfzeile und der ARM64-Pruefung greifen"


def test_skript_bleibt_ascii():
    assert all(b < 128 for b in START_PS1.read_bytes())


_POWERSHELL = shutil.which("powershell")
_nur_windows = pytest.mark.skipif(
    sys.platform != "win32" or not _POWERSHELL,
    reason="Windows PowerShell 5.1 mit PSReadLine nur unter Windows")


def _ps(befehl: str, cwd: Path) -> str:
    env = dict(os.environ)
    # start.ps1 findet in der Kopie kein venv und nimmt "python" aus dem PATH.
    env["PATH"] = os.path.dirname(sys.executable) + os.pathsep + env.get("PATH", "")
    r = subprocess.run(
        [_POWERSHELL or "powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-Command", befehl],
        cwd=str(cwd), env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=120)
    return (r.stdout or "") + "\n" + (r.stderr or "")


def _psreadline_verfuegbar(tmp_path) -> bool:
    aus = _ps("if (Get-Module -ListAvailable PSReadLine) { 'JA' } else { 'NEIN' }",
              tmp_path)
    return "JA" in aus


@_nur_windows
def test_gegenprobe_psreadline_verdeckt_den_kurznamen(tmp_path):
    """Belegt, dass der Aufbau unten den Fehler wirklich ausloest — sonst
    pruefte der Test nichts. Wo PSReadLine den Typ nicht (mehr) verdeckt,
    wird uebersprungen statt rot."""
    if not _psreadline_verfuegbar(tmp_path):
        pytest.skip("PSReadLine nicht installiert")
    probe = tmp_path / "probe.ps1"
    probe.write_text(
        'Write-Output ("KURZNAME=[" + '
        '[System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture + "]")\n',
        encoding="ascii")
    aus = _ps(f"Import-Module PSReadLine; & '{probe}'", tmp_path)
    if "KURZNAME=[]" not in aus:
        pytest.skip("PSReadLine verdeckt den Typ hier nicht: " + aus[-300:])


@_nur_windows
def test_kopfzeile_nennt_die_architektur_auch_mit_psreadline(tmp_path):
    if not _psreadline_verfuegbar(tmp_path):
        pytest.skip("PSReadLine nicht installiert")
    shutil.copyfile(START_PS1, tmp_path / "start.ps1")
    (tmp_path / "main.py").write_text('print("ATTRAPPE-MAIN")\n', encoding="ascii")
    ohne = _ps(f"& '{tmp_path / 'start.ps1'}'", tmp_path)
    mit = _ps(f"Import-Module PSReadLine; & '{tmp_path / 'start.ps1'}'", tmp_path)
    werte = {}
    for name, aus in (("ohne PSReadLine", ohne), ("mit PSReadLine", mit)):
        assert "ATTRAPPE-MAIN" in aus, (name, aus[-1500:])
        kopf = _KOPF.search(aus)
        assert kopf is not None, (name, aus[-1500:])
        assert kopf.group(1) and kopf.group(2), (
            f"{name}: Architektur leer — {kopf.group(0)!r}")
        werte[name] = kopf.groups()
    assert werte["mit PSReadLine"] == werte["ohne PSReadLine"]
