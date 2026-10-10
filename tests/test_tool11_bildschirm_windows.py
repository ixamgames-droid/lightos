"""TOOL-11 (1)+(3): ``anleitungsbilder --bildschirm`` unter Windows und mit ``--alle``.

(1) Codex-Review #853: die Sandbox verlangte fuer ``--bildschirm`` immer
    ``DISPLAY`` und setzte ``QT_QPA_PLATFORM=xcb``. Unter Windows gibt es weder
    das eine noch das andere - das Werkzeug brach sofort mit "DISPLAY ist leer"
    ab, die 3D-Bilder liessen sich dort gar nicht bauen.
(3) Codex-Review #860: ``--alle`` startet je Anleitung einen eigenen Prozess,
    reichte ``--bildschirm`` aber nicht weiter - alle 3D-Szenen fielen still als
    „uebersprungen“ weg.

Die Sandbox laeuft im eigenen Prozess (sie biegt ``os.environ`` und das cwd um
und verweigert sich nach einem ``src``-Import).
"""
import importlib.util
import os
import subprocess
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(REPO, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)


def test_plattform_plugin_je_system():
    from anleitungsbilder import sandbox
    assert sandbox.bildschirm_plattform("win32") == "windows"
    assert sandbox.bildschirm_plattform("darwin") == "cocoa"
    assert sandbox.bildschirm_plattform("linux") == "xcb"


_SANDBOX_PROBE = r"""
import os, shutil, sys
sys.path.insert(0, sys.argv[1])
sys.platform = sys.argv[2]          # die Sandbox fragt die Plattform zur Laufzeit
os.environ.pop("DISPLAY", None)
from anleitungsbilder import sandbox
try:
    sb = sandbox.einrichten(bildschirm=True)
except SystemExit as e:
    print("ABBRUCH", e.code)
else:
    print("QPA", os.environ["QT_QPA_PLATFORM"])
    print("XAUTH", "XAUTHORITY" in os.environ)
    os.chdir(sys.argv[3])
    shutil.rmtree(sb.basis, ignore_errors=True)
"""


def _probe(plattform: str) -> str:
    env = dict(os.environ)
    env.pop("DISPLAY", None)
    env.pop("XAUTHORITY", None)
    r = subprocess.run([sys.executable, "-c", _SANDBOX_PROBE, TOOLS, plattform, REPO],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60, cwd=REPO, env=env)
    assert r.returncode == 0, r.stderr[-2000:]
    return r.stdout


def test_windows_bildschirm_ohne_display():
    out = _probe("win32")
    assert "ABBRUCH" not in out, out
    assert "QPA windows" in out
    assert "XAUTH False" in out


def test_linux_ohne_display_bricht_weiter_ab():
    out = _probe("linux")
    assert "ABBRUCH" in out and "DISPLAY" in out, out


@pytest.fixture
def werkzeug():
    """Das Skript ``tools/anleitungsbilder.py`` (gleichnamig mit dem Paket)."""
    spec = importlib.util.spec_from_file_location(
        "anleitungsbilder_cli_tool11", os.path.join(TOOLS, "anleitungsbilder.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("bildschirm", [True, False])
def test_alle_reicht_bildschirm_weiter(werkzeug, monkeypatch, bildschirm):
    befehle = []

    class _Ergebnis:
        returncode = 0

    monkeypatch.setattr(subprocess, "run",
                        lambda befehl, **kw: befehle.append(list(befehl)) or _Ergebnis())
    argv = ["--alle"] + (["--bildschirm"] if bildschirm else [])
    args = werkzeug._argumente(argv)
    auftraege = [("eins", [], "docs/eins/img"), ("zwei", [], "docs/zwei/img")]
    assert werkzeug._je_anleitung_ein_prozess(args, auftraege, set()) == 0
    assert len(befehle) == 2
    for befehl in befehle:
        assert ("--bildschirm" in befehl) is bildschirm, befehl
