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
