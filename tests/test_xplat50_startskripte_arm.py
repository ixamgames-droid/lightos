"""XPLAT-50: start.bat / start.ps1 raten auf Windows-ARM nicht mehr zu ARM64-Python.

Entscheidung XPLAT-46: auf Windows-ARM ist x64-Python der empfohlene Weg, weil
natives ARM64-Python kein QtWebEngine und damit keinen 3D-Visualizer hat
(XPLAT-45). Die Startskripte warnten trotzdem bei x64 ("ARM64-Python nutzen")
und nannten ``winget ... --arch arm64`` - eine Option, die winget nicht kennt.

Die Skripte laufen nur unter Windows; geprueft wird deshalb ihr Text.
"""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SKRIPTE = ("start.bat", "start.ps1")


def _text(name: str) -> str:
    return (ROOT / name).read_bytes().decode("utf-8")


@pytest.mark.parametrize("name", SKRIPTE)
class TestStartskripte:
    def test_kein_rat_zu_arm64_python(self, name):
        text = _text(name)
        assert "--arch arm64" not in text
        assert "ARM64-Python nutzen" not in text
        assert "Fuer beste Stabilitaet/Performance" not in text

    def test_x64_auf_arm_wird_nicht_als_problem_gemeldet(self, name):
        for zeile in _text(name).splitlines():
            if "WARN" in zeile:
                assert "emuliert" not in zeile, zeile

    def test_natives_arm64_bekommt_den_hinweis_ohne_3d(self, name):
        text = _text(name)
        assert "ohne 3D-Visualizer" in text
        assert "x64-Python empfohlen" in text
        assert "--architecture x64" in text

    def test_geprueft_wird_das_python_nicht_die_shell(self, name):
        # Massgeblich ist die Architektur des Interpreters, der main.py startet -
        # eine x64-Shell kann ein ARM64-venv starten und umgekehrt.
        text = _text(name)
        assert "sysconfig" in text and "win-arm64" in text
        pruefung = text.index("win-arm64")
        start = text.rindex("main.py")
        assert pruefung < start, "der Hinweis muss vor dem Start kommen"


def test_start_bat_behaelt_crlf_und_ascii():
    roh = (ROOT / "start.bat").read_bytes()
    roh.decode("ascii")
    assert b"\r\n" in roh and b"\n" not in roh.replace(b"\r\n", b"")


def test_start_bat_hinweis_ohne_klammern_im_block():
    # Eine ")" in einer echo-Zeile beendet in cmd einen (...)-Block vorzeitig.
    tiefe = 0
    for zeile in _text("start.bat").splitlines():
        z = zeile.strip()
        if z.upper().startswith("REM"):
            continue
        if tiefe > 0 and z.lower().startswith("echo"):
            assert "(" not in z and ")" not in z, zeile
        tiefe += z.count("(") - z.count(")")
    assert tiefe == 0


def test_dmx_protokoll_stellt_arm64_nicht_als_vorzug_hin():
    text = (ROOT / "docs" / "DMX_PROTOCOL.md").read_text(encoding="utf-8")
    assert "Kein x64-Emulations-Overhead" not in text
    abschnitt = text.split("## ARM64 (Snapdragon) Kompatibilität", 1)[1].split("\n## ", 1)[0]
    assert "x64-Python" in abschnitt
