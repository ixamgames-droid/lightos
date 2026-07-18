"""XPLAT-01 — QtWebEngine-Linux-Sandbox-Fallback.

Auf verbreiteten Linux-Setups (pip-PySide6 ohne setuid ``chrome-sandbox``,
Container/Docker, root) startet der Chromium-Renderprozess nicht → der eingebettete
3D-Visualizer bleibt schwarz. ``_setup_webengine_diagnostics`` hängt darum auf Linux
``--no-sandbox --disable-gpu-sandbox`` an; Windows/macOS bleiben unberührt.
"""
from __future__ import annotations
import importlib

import pytest

main = importlib.import_module("main")

SANDBOX = "--no-sandbox --disable-gpu-sandbox"


def _flags(platform_name, env=None, existing=""):
    return main._webengine_sandbox_flags(platform_name, env or {}, existing)


# ── reine Helfer-Funktion ────────────────────────────────────────────────────

@pytest.mark.parametrize("plat", ["linux", "linux2"])
def test_linux_default_adds_sandbox_flags(plat):
    assert _flags(plat) == SANDBOX


@pytest.mark.parametrize("plat", ["win32", "cygwin", "darwin"])
def test_non_linux_adds_nothing(plat):
    assert _flags(plat) == ""


@pytest.mark.parametrize("val", ["0", "false", "no", "off", "OFF", "False", " no "])
def test_linux_optout_env_keeps_sandbox(val):
    assert _flags("linux", {"LIGHTOS_WEBENGINE_NO_SANDBOX": val}) == ""


@pytest.mark.parametrize("val", ["1", "true", "yes", ""])
def test_linux_non_optout_values_still_add(val):
    # Nur ausdrücklich falsy-Werte wählen ab; alles andere behält den Fix.
    assert _flags("linux", {"LIGHTOS_WEBENGINE_NO_SANDBOX": val}) == SANDBOX


def test_user_own_sandbox_choice_has_precedence():
    assert _flags("linux", {}, existing="--foo --no-sandbox --bar") == ""
    assert _flags("linux", {}, existing="--disable-gpu-sandbox") == ""


def test_empty_or_none_existing_is_safe():
    assert _flags("linux", {}, existing="") == SANDBOX
    assert _flags("linux", {}, existing=None) == SANDBOX


# ── Verdrahtung in _setup_webengine_diagnostics ──────────────────────────────

def test_windows_setup_does_not_add_sandbox(monkeypatch):
    monkeypatch.setattr(main.sys, "platform", "win32")
    monkeypatch.delenv("QTWEBENGINE_CHROMIUM_FLAGS", raising=False)
    monkeypatch.delenv("LIGHTOS_WEBENGINE_FLAGS", raising=False)
    main._setup_webengine_diagnostics()
    flags = main.os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
    assert "sandbox" not in flags            # Windows-Pfad unberührt
    assert "backgrounding" in flags          # Basis-Anti-Drossel-Flags weiter da


def test_linux_setup_adds_sandbox(monkeypatch):
    monkeypatch.setattr(main.sys, "platform", "linux")
    monkeypatch.delenv("QTWEBENGINE_CHROMIUM_FLAGS", raising=False)
    monkeypatch.delenv("LIGHTOS_WEBENGINE_FLAGS", raising=False)
    monkeypatch.delenv("LIGHTOS_WEBENGINE_NO_SANDBOX", raising=False)
    main._setup_webengine_diagnostics()
    flags = main.os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
    assert "--no-sandbox" in flags
    assert "--disable-gpu-sandbox" in flags
    assert "backgrounding" in flags          # Basis-Flags bleiben erhalten


def test_linux_setup_respects_optout(monkeypatch):
    monkeypatch.setattr(main.sys, "platform", "linux")
    monkeypatch.delenv("QTWEBENGINE_CHROMIUM_FLAGS", raising=False)
    monkeypatch.delenv("LIGHTOS_WEBENGINE_FLAGS", raising=False)
    monkeypatch.setenv("LIGHTOS_WEBENGINE_NO_SANDBOX", "0")
    main._setup_webengine_diagnostics()
    flags = main.os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
    assert "sandbox" not in flags            # abgewählt -> Sandbox bleibt
