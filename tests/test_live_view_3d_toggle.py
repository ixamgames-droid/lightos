"""Live View: Umschalten zwischen 2D-Canvas und eingebetteter 3D-Ansicht.

Testet die Routing-Logik von ``LiveView._set_view_3d`` ueber einen schlanken
Stub (echte Methode via Klassenattribut) — ohne echtes QWebEngineView, damit der
Test schnell und headless-stabil bleibt. Die ``_viz3d`` ist vorgesetzt, so dass
der Lazy-Create-Pfad (der den WebView erzeugen wuerde) uebersprungen wird.
"""
from __future__ import annotations
import os
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.ui.views.live_view import LiveView


class _Btn:
    def __init__(self):
        self._checked = False

    def setChecked(self, v):
        self._checked = bool(v)

    def isChecked(self):
        return self._checked


class _Stack:
    def __init__(self):
        self.current = None
        self.widgets = []

    def addWidget(self, w):
        self.widgets.append(w)

    def setCurrentWidget(self, w):
        self.current = w


class _Toggle3DStub:
    _set_view_3d = LiveView._set_view_3d

    def __init__(self, viz):
        self._btn_view2d = _Btn()
        self._btn_view3d = _Btn()
        self._viz3d = viz
        self._scroll = object()
        self._view_stack = _Stack()
        self._minimap = SimpleNamespace(hide=lambda: None, show=lambda: None)
        self._reloaded = False
        self._canvas = SimpleNamespace(
            _reload_positions_safe=lambda: setattr(self, "_reloaded", True))


def test_toggle_to_3d_shows_embedded_and_calls_on_shown():
    calls = {"shown": 0, "hidden": 0}
    viz = SimpleNamespace(
        on_shown=lambda: calls.__setitem__("shown", calls["shown"] + 1),
        on_hidden=lambda: calls.__setitem__("hidden", calls["hidden"] + 1),
    )
    s = _Toggle3DStub(viz)
    s._set_view_3d(True)
    assert s._view_stack.current is viz
    assert calls["shown"] == 1
    assert s._btn_view3d.isChecked() and not s._btn_view2d.isChecked()


def test_toggle_back_to_2d_reloads_canvas_and_pauses_3d():
    calls = {"hidden": 0}
    viz = SimpleNamespace(
        on_shown=lambda: None,
        on_hidden=lambda: calls.__setitem__("hidden", calls["hidden"] + 1),
    )
    s = _Toggle3DStub(viz)
    s._set_view_3d(True)
    s._set_view_3d(False)
    assert s._view_stack.current is s._scroll
    assert s._reloaded is True            # 2D-Canvas neu geladen (spiegelt 3D-Moves)
    assert calls["hidden"] == 1           # 3D-Timer pausiert
    assert s._btn_view2d.isChecked() and not s._btn_view3d.isChecked()


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
