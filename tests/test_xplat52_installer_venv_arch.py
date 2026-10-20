"""XPLAT-52: Manifest und Zusammenfassung nennen die Architektur des venv.

``write_manifest()`` und ``show_summary()`` nahmen ``detect_arch()`` - das
Python, das install.py ausfuehrt. Bleibt ein x64-venv stehen und install.py
laeuft mit ARM64-Python, stand im Manifest ``python_arch: arm64`` und am Ende
"kein 3D", obwohl das venv 3D kann - umgekehrt fehlte die Warnung, obwohl das
venv ARM64 bleibt. Massgeblich ist bei vorhandenem venv ``venv_arch()``.

Nichts wird echt installiert: VENV_DIR/MANIFEST_PATH zeigen in tmp_path, die
Architekturen kommen aus Monkeypatches.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

#: (Architektur des venv, Architektur des ausfuehrenden Python)
MISCHFAELLE = [("x64", "arm64"), ("arm64", "x64")]


@pytest.fixture
def installer(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(ROOT))
    import install
    monkeypatch.setattr(install, "VENV_DIR", tmp_path / "venv")
    monkeypatch.setattr(install, "MANIFEST_PATH", tmp_path / "install_manifest.json")
    monkeypatch.setattr(install.os, "name", "nt")
    monkeypatch.setattr(install, "detect_native_os_arch", lambda: "arm64")
    return install


def _archs(installer, monkeypatch, venv, ausfuehrend):
    monkeypatch.setattr(installer, "venv_arch", lambda: venv)
    monkeypatch.setattr(installer, "detect_arch", lambda: ausfuehrend)


def _manifest(installer) -> dict:
    installer.write_manifest([], None)
    return json.loads(installer.MANIFEST_PATH.read_text(encoding="utf-8"))


@pytest.mark.parametrize("venv,ausfuehrend", MISCHFAELLE)
class TestMischfaelle:
    def test_manifest_nennt_das_venv(self, installer, monkeypatch, venv, ausfuehrend):
        _archs(installer, monkeypatch, venv, ausfuehrend)
        m = _manifest(installer)
        assert m["python_arch"] == venv
        assert m["arch"] == venv
        assert m["python_emulated_on_arm64"] is (venv != "arm64")
        assert m["installer_python_arch"] == ausfuehrend

    def test_zusammenfassung_nennt_das_venv(self, installer, monkeypatch, capsys,
                                            venv, ausfuehrend):
        _archs(installer, monkeypatch, venv, ausfuehrend)
        installer.show_summary()
        out = capsys.readouterr().out
        zeile = next(z for z in out.splitlines() if "Python-Architektur:" in z)
        assert zeile.split("Python-Architektur:", 1)[1].split()[0] == venv
        warnt = any("WARN" in z and "ARM64-Python" in z for z in out.splitlines())
        # Warnung genau dann, wenn das venv ARM64 ist - nicht das ausfuehrende.
        assert warnt is (venv == "arm64")


class TestOhneVenv:
    def test_no_venv_nennt_das_ausfuehrende(self, installer, monkeypatch, capsys):
        _archs(installer, monkeypatch, "x64", "arm64")
        installer.write_manifest([], None, use_venv=False)
        m = json.loads(installer.MANIFEST_PATH.read_text(encoding="utf-8"))
        assert m["python_arch"] == "arm64"
        installer.show_summary(use_venv=False)
        out = capsys.readouterr().out
        assert any("WARN" in z and "ARM64-Python" in z for z in out.splitlines())

    def test_venv_nicht_startbar_faellt_auf_das_ausfuehrende_zurueck(
            self, installer, monkeypatch):
        _archs(installer, monkeypatch, "unknown", "x64")
        assert _manifest(installer)["python_arch"] == "x64"

    def test_echtes_venv_arch_ohne_venv_ist_unknown(self, installer, monkeypatch):
        # Ohne venv/ startet venv_arch() keinen Prozess.
        def _kein_prozess(*a, **k):
            raise AssertionError("kein Unterprozess erwartet")
        monkeypatch.setattr(installer.subprocess, "run", _kein_prozess)
        monkeypatch.setattr(installer, "detect_arch", lambda: "x64")
        assert installer.venv_arch() == "unknown"
        assert installer.ziel_arch() == "x64"


def test_main_reicht_use_venv_an_das_manifest(installer, monkeypatch):
    import sys
    gesehen = []
    for name in ("check_python", "check_arm_runtime", "install_requirements",
                 "create_venv", "create_shortcut", "show_summary"):
        monkeypatch.setattr(installer, name, lambda *a, **k: None)
    monkeypatch.setattr(installer, "create_directories", lambda: [])
    monkeypatch.setattr(installer, "detect_arch", lambda: "x64")
    monkeypatch.setattr(installer, "write_manifest",
                        lambda c, s, use_venv=True: gesehen.append(use_venv))
    monkeypatch.setattr(sys, "argv", ["install.py", "--no-venv", "--no-shortcut"])
    installer.main()
    assert gesehen == [False]
