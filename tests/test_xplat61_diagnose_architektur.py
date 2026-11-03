"""XPLAT-61: Die Diagnose-Zeile ``Architektur:`` meldete auf einem ARM64-Rechner
mit emuliertem x64-Python (venv ``win-amd64``, PySide6 ``win_amd64``)
"ARM64 nativ".

Ursache: ``platform.machine()`` liefert ab Python 3.12 unter Windows die
Architektur des Rechners (WMI) — auch im emulierten x64-Prozess "ARM64".
``IsWow64Process2`` meldet fuer x64-Emulation (kein WOW64) als Prozess-Maschine
0, also entschied ``platform.machine()``: Prozess = Rechner = ARM64 -> "nativ".
Jetzt kommt die Prozess-Architektur aus ``sysconfig.get_platform()`` (Bauart des
Interpreters), die Rechner-Architektur weiter aus ``IsWow64Process2``.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core import diagnose_log as d  # noqa: E402

_X64, _ARM64, _X86, _KEIN_WOW = 0x8664, 0xAA64, 0x014C, 0


@pytest.mark.parametrize("wow, nativ, machine, interpreter, erwartet", [
    # Befund Sitzung B: ARM64-Rechner, x64-Python emuliert, machine() = ARM64
    (_KEIN_WOW, _ARM64, "ARM64", "win-amd64",
     "x64-Prozess auf ARM64 (Emulation)"),
    (_KEIN_WOW, _ARM64, "ARM64", "win-arm64", "ARM64 nativ"),
    (_KEIN_WOW, _X64, "AMD64", "win-amd64", "x64 nativ"),
])
def test_architektur_trennt_prozess_und_rechner(wow, nativ, machine,
                                                interpreter, erwartet):
    assert d.windows_architektur(wow, nativ, machine=machine, env={}, bits=64,
                                 interpreter=interpreter) == erwartet


def test_emuliertes_x64_heisst_nie_nativ_auch_im_rueckfall():
    """Ohne IsWow64Process2: Interpreter x64, PROCESSOR_IDENTIFIER verraet ARM."""
    text = d.windows_architektur(
        None, None, machine="ARM64",
        env={"PROCESSOR_ARCHITECTURE": "AMD64",
             "PROCESSOR_IDENTIFIER": "ARMv8 (64-bit) Family 8 Model 1"},
        bits=64, interpreter="win-amd64")
    assert text.startswith("x64-Prozess auf ARM64 (Emulation)"), text
    assert "nativ" not in text


@pytest.mark.parametrize("plattform, kurz", [
    ("win-amd64", "x64"), ("win-arm64", "ARM64"), ("win32", "x86"),
    ("linux-x86_64", "x64"), ("macosx-11.0-arm64", "ARM64"), ("", ""),
    ("unsinn", ""),
])
def test_interpreter_bauart(plattform, kurz):
    assert d._interpreter_kurz(plattform) == kurz


def test_linux_x86_64_nativ():
    assert d.windows_architektur(_KEIN_WOW, _X64, machine="x86_64", env={},
                                 bits=64, interpreter="linux-x86_64") == "x64 nativ"


def test_kopfzeile_nutzt_die_bauart_des_interpreters(monkeypatch):
    """Die Zeile im Kopfblock: machine() sagt ARM64 (WMI), der Interpreter ist
    aber win-amd64 -> Emulation, nicht "ARM64 nativ"."""
    monkeypatch.setattr(d, "_iswow64process2", lambda: (_KEIN_WOW, _ARM64))
    monkeypatch.setattr(d.platform, "machine", lambda: "ARM64")
    monkeypatch.setattr(d.sysconfig, "get_platform", lambda: "win-amd64")
    assert d._windows_architektur() == "x64-Prozess auf ARM64 (Emulation)"
    monkeypatch.setattr(d.sysconfig, "get_platform", lambda: "win-arm64")
    assert d._windows_architektur() == "ARM64 nativ"
