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

#: os.name des Rechners, auf dem die Tests laufen - vor jedem Monkeypatch.
ECHTES_OS_NAME = __import__("os").name

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


# ── Gegenpruefung: venv_arch() ausserhalb von Windows ──────────────────────
class _Lauf:
    def __init__(self, ausgabe: str):
        self.stdout, self.returncode = ausgabe + "\n", 0


def _venv_wie_unter_linux(installer, monkeypatch, tmp_path) -> Path:
    """Legt ein venv-Python im Linux-Layout (``bin/python``) in tmp_path an.

    os.name wird NICHT auf 'posix' umgestellt: pathlib benutzt dasselbe
    os-Modul und baut danach unter Windows einen PosixPath, den Python dort
    nicht anlegen kann (Gegenprobe Sitzung D). Umgekehrt macht das 'nt' der
    Fixture unter Linux aus jedem neuen Path einen WindowsPath ('\\tmp\\...'),
    den es nicht gibt - deshalb gilt hier wieder das echte os.name. Massgeblich
    fuer venv_arch() ist nur der Plattformstring aus dem venv, und der kommt
    aus dem Monkeypatch."""
    monkeypatch.setattr(installer.os, "name", ECHTES_OS_NAME)
    py = tmp_path / "venv" / "bin" / "python"
    py.parent.mkdir(parents=True)
    py.write_text("", encoding="utf-8")
    monkeypatch.setattr(installer, "venv_python", lambda: str(py))
    return py


@pytest.mark.parametrize("plat,erwartet", [
    ("linux-x86_64", "x64"), ("linux-aarch64", "arm64"),
    ("macosx-14.0-arm64", "arm64"), ("macosx-10.9-x86_64", "x64"),
    ("win-amd64", "x64"), ("win-arm64", "arm64"), ("win32", "x86"),
])
def test_venv_arch_normalisiert_jede_plattform(installer, monkeypatch, tmp_path,
                                               plat, erwartet):
    # sysconfig.get_platform() im venv: unter Linux/macOS 'linux-x86_64' usw. -
    # vorher kam der ganze String zurueck und stand so im Manifest.
    _venv_wie_unter_linux(installer, monkeypatch, tmp_path)
    monkeypatch.setattr(installer.subprocess, "run", lambda *a, **k: _Lauf(plat))
    assert installer.venv_arch() == erwartet


@pytest.mark.parametrize("plat", ["linux-x86_64", "linux-aarch64"])
def test_linux_manifest_und_create_venv_ohne_falsche_abweichung(
        installer, monkeypatch, capsys, tmp_path, plat):
    monkeypatch.setattr(installer, "detect_native_os_arch", lambda: "x64")
    arch = "x64" if plat.endswith("x86_64") else "arm64"
    monkeypatch.setattr(installer, "detect_arch", lambda: arch)
    _venv_wie_unter_linux(installer, monkeypatch, tmp_path)
    monkeypatch.setattr(installer.subprocess, "run", lambda *a, **k: _Lauf(plat))
    m = _manifest(installer)
    assert m["python_arch"] == m["arch"] == arch
    installer.show_summary()
    assert "install.py lief mit" not in capsys.readouterr().out
    # create_venv fragt nur bei echter Abweichung nach.
    monkeypatch.setattr(installer, "_frage_ja",
                        lambda *a: (_ for _ in ()).throw(AssertionError("Rueckfrage")))
    installer.create_venv()
    assert "Das vorhandene venv wurde mit" not in capsys.readouterr().out


# ── Gegenpruefung: Anfang und Ende eines Laufs widersprechen sich nicht ────
def _arm_runtime(installer, monkeypatch, capsys, venv, ausfuehrend, **kw):
    _archs(installer, monkeypatch, venv, ausfuehrend)
    monkeypatch.setattr(installer, "finde_x64_python", lambda: None)
    installer.check_arm_runtime(**kw)
    return [z for z in capsys.readouterr().out.splitlines() if "WARN" in z]


def test_arm_warnung_nennt_vorhandenes_x64_venv(installer, monkeypatch, capsys):
    # XPLAT-56: mit ARM64-Python wird das x64-venv nicht neu angelegt - keine
    # Rueckfrage, der Lauf geht weiter (nur mit --arm64-trotzdem wird gefragt).
    warn = _arm_runtime(installer, monkeypatch, capsys, "x64", "arm64")
    zusatz = [z for z in warn if "vorhandene venv ist x64-Python" in z]
    assert zusatz and "nicht neu angelegt" in zusatz[0]
    assert "Rueckfrage folgt" not in zusatz[0]
    warn = _arm_runtime(installer, monkeypatch, capsys, "x64", "arm64", trotzdem=True)
    assert any("Rueckfrage folgt" in z for z in warn)


def test_x64_installer_warnt_vor_vorhandenem_arm64_venv(installer, monkeypatch, capsys):
    warn = _arm_runtime(installer, monkeypatch, capsys, "arm64", "x64")
    zusatz = [z for z in warn if "vorhandene venv ist ARM64-Python" in z]
    assert zusatz and "nicht unterstuetzt (instabil, kein 3D)" in zusatz[0]
    assert "--neu-venv" in zusatz[0]


@pytest.mark.parametrize("kw", [{"use_venv": False}, {"neu_venv": True}])
def test_kein_venv_zusatz_ohne_venv_oder_bei_neuanlage(installer, monkeypatch, capsys, kw):
    for venv, ausfuehrend in MISCHFAELLE:
        warn = _arm_runtime(installer, monkeypatch, capsys, venv, ausfuehrend, **kw)
        assert not any("vorhandene venv" in z for z in warn)


def test_main_reicht_venv_optionen_an_check_arm_runtime(installer, monkeypatch):
    import sys
    gesehen = []
    for name in ("check_python", "install_requirements", "create_venv",
                 "create_shortcut", "show_summary", "write_manifest"):
        monkeypatch.setattr(installer, name, lambda *a, **k: None)
    monkeypatch.setattr(installer, "create_directories", lambda: [])
    monkeypatch.setattr(installer, "detect_arch", lambda: "x64")
    monkeypatch.setattr(installer, "check_arm_runtime",
                        lambda *a, **k: gesehen.append(a))
    for argv, erwartet in ((["--no-venv"], (False, False)),
                           (["--neu-venv"], (True, True)), ([], (True, False))):
        monkeypatch.setattr(sys, "argv", ["install.py", "--no-shortcut", *argv])
        installer.main()
        assert gesehen.pop() == erwartet
