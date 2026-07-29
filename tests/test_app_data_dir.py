"""XPLAT-04 — zentraler, plattformabhaengiger App-Datenordner (`src.core.paths`).

Vorher loeste jede Fundstelle den Ordner selbst auf → auf Linux/macOS landete alles
im nicht-XDG-konformen `~/LightOS`. `app_data_dir()` zentralisiert das; **Windows
bleibt byte-identisch** (`%APPDATA%/LightOS`).
"""
from __future__ import annotations
import os

import pytest

from src.core import paths


def _call(monkeypatch, plat, env):
    monkeypatch.setattr(paths.sys, "platform", plat)
    for k in ("APPDATA", "XDG_DATA_HOME"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return paths.app_data_dir()


# ── Windows (byte-identisch zum alten Verhalten) ─────────────────────────────

def test_windows_uses_appdata(monkeypatch):
    got = _call(monkeypatch, "win32", {"APPDATA": r"C:\Users\X\AppData\Roaming"})
    assert got == os.path.join(r"C:\Users\X\AppData\Roaming", "LightOS")


def test_windows_byte_identical_to_old_pattern(monkeypatch):
    # Das alte Muster war ueberall os.path.join(os.environ.get("APPDATA", ~), "LightOS").
    monkeypatch.setattr(paths.sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", r"C:\Users\X\AppData\Roaming")
    old = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "LightOS")
    assert paths.app_data_dir() == old


def test_windows_empty_appdata_falls_back_home(monkeypatch):
    got = _call(monkeypatch, "win32", {"APPDATA": ""})
    assert got == os.path.join(os.path.expanduser("~"), "LightOS")


# ── Linux (XDG) ──────────────────────────────────────────────────────────────

def test_linux_uses_xdg_data_home(monkeypatch):
    got = _call(monkeypatch, "linux", {"XDG_DATA_HOME": "/home/x/.local/share"})
    assert got == os.path.join("/home/x/.local/share", "LightOS")


def test_linux_default_local_share(monkeypatch):
    got = _call(monkeypatch, "linux", {})
    assert got == os.path.join(os.path.expanduser("~"), ".local", "share", "LightOS")


def test_linux_ignores_appdata(monkeypatch):
    # Auf Linux darf ein (untypisch) gesetztes APPDATA NICHT greifen.
    got = _call(monkeypatch, "linux", {"APPDATA": "/should/not/be/used"})
    assert "should/not/be/used" not in got.replace("\\", "/")
    assert os.path.basename(got) == "LightOS"


# ── macOS ────────────────────────────────────────────────────────────────────

def test_macos_application_support(monkeypatch):
    got = _call(monkeypatch, "darwin", {})
    assert got == os.path.join(
        os.path.expanduser("~"), "Library", "Application Support", "LightOS")


# ── Invariante ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("plat", ["win32", "linux", "darwin", "freebsd12"])
def test_always_ends_with_lightos(monkeypatch, plat):
    env = {"APPDATA": r"C:\a"} if plat == "win32" else {}
    got = _call(monkeypatch, plat, env)
    assert os.path.basename(got) == "LightOS"
    assert got  # nie leer


# ── XPLAT-10: niemand loest den Ordner mehr selbst auf ───────────────────────
# Hintergrund: XPLAT-04 hatte `app_data_dir()` eingefuehrt, aber vier aktive
# Fundstellen bauten den Pfad weiter selbst (`main.py`, `install.py`,
# `uninstall.py`, `tools/build_full_show.py`). Auf Linux fiel das auseinander:
# `main.py` schrieb crash.log/last_alive/Running-Flags nach ~/LightOS, waehrend
# `visualizer_window._viz_crash_log_path` und `tools/collect_crash_report.py`
# ueber `app_data_dir()` mit ~/.local/share/LightOS arbeiteten — das Crash-Intake
# sah die Abstuerze der App also gar nicht. Dieser Waechter haelt das geschlossen.

import re                                                          # noqa: E402
import subprocess                                                  # noqa: E402

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Nur hier darf APPDATA vorkommen: das ist die zentrale Aufloesung selbst.
_ALLOWED = {os.path.join("src", "core", "paths.py")}

# Nicht gescannt: venv (fremder Code), tools/_archiv (stillgelegt), tests
# (duerfen das alte Muster zu Vergleichszwecken nennen — siehe oben).
_SKIP_PREFIXES = ("venv", ".git", os.path.join("tools", "_archiv"), "tests")

_APPDATA_SELFRESOLVE = re.compile(r"""environ(?:\.get\(|\[)\s*["']APPDATA["']""")


def _tracked_python_files():
    out = subprocess.run(["git", "ls-files", "*.py"], cwd=_REPO_ROOT,
                         capture_output=True, text=True, check=True).stdout
    for rel in out.splitlines():
        rel = rel.strip()
        if not rel or rel.startswith(_SKIP_PREFIXES):
            continue
        yield rel


def test_no_module_resolves_appdata_itself():
    offenders = []
    for rel in _tracked_python_files():
        if rel.replace("/", os.sep) in _ALLOWED:
            continue
        with open(os.path.join(_REPO_ROOT, rel), encoding="utf-8", errors="replace") as f:
            for lineno, line in enumerate(f, 1):
                if _APPDATA_SELFRESOLVE.search(line):
                    offenders.append(f"{rel}:{lineno}: {line.strip()}")
    assert not offenders, (
        "Diese Stellen loesen den App-Datenordner selbst ueber APPDATA auf statt ueber "
        "src.core.paths.app_data_dir() (XPLAT-04/-10) — auf Linux/macOS zeigen sie damit "
        "woandershin als der Rest der App:\n  " + "\n  ".join(offenders))


def test_main_appdata_dir_matches_central_resolution():
    """`main._appdata_dir()` (crash.log, last_alive, Running-Flags) muss denselben
    Ordner liefern wie `app_data_dir()` — sonst schreibt die App ihre Crash-Spur
    dorthin, wo das Crash-Intake nicht nachsieht."""
    # main.py hat schweren Top-Level-Code (PySide6/MainWindow-Import) -> Quelltext
    # statt Import pruefen: die Funktion muss an app_data_dir() delegieren.
    src = open(os.path.join(_REPO_ROOT, "main.py"), encoding="utf-8").read()
    body = src.split("def _appdata_dir(", 1)
    assert len(body) == 2, "main.py hat kein _appdata_dir() mehr — Test anpassen"
    # bis zur naechsten Top-Level-Definition
    fn = re.split(r"\n(?:def |class |if |from |import )", body[1], maxsplit=1)[0]
    assert "_app_data_dir()" in fn or "app_data_dir()" in fn, (
        "main._appdata_dir() delegiert nicht an src.core.paths.app_data_dir() "
        f"(XPLAT-10). Rumpf war:\n{fn}")
    assert not _APPDATA_SELFRESOLVE.search(fn), (
        "main._appdata_dir() loest APPDATA wieder selbst auf (XPLAT-10)")
