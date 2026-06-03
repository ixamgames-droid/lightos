"""Tests fuer den Zoom-Overlay in der Live-View (I2.9).

Testet _on_zoom_changed ueber einen schlanken Stub, der die echte Methode
per Klassenattribut-Referenz aufruft — kein vollstaendiges QWidget noetig.
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

from PySide6.QtWidgets import QApplication, QLabel

from src.ui.views.live_view import LiveView


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


class _ZoomStub:
    """Minimaler Stub, der _on_zoom_changed der echten LiveView-Klasse aufruft."""
    _on_zoom_changed = LiveView._on_zoom_changed

    def __init__(self):
        def _set(z):
            self._canvas.zoom = max(0.25, min(4.0, z))

        self._canvas = SimpleNamespace(zoom=1.0, set_zoom=_set)
        self._lbl_zoom = QLabel()
        self._persist_live_view_prefs = lambda: None


def test_zoom_200_percent():
    """200 als Slider-Wert => zoom=2.0, Label='200 %'."""
    _app()
    s = _ZoomStub()
    s._on_zoom_changed(200)
    assert s._canvas.zoom == 2.0, f"Erwartet 2.0, bekommen {s._canvas.zoom}"
    assert s._lbl_zoom.text() == "200 %", f"Erwartet '200 %', bekommen '{s._lbl_zoom.text()}'"


def test_zoom_50_percent():
    """50 als Slider-Wert => zoom=0.5, Label='50 %'."""
    _app()
    s = _ZoomStub()
    s._on_zoom_changed(50)
    assert s._canvas.zoom == 0.5, f"Erwartet 0.5, bekommen {s._canvas.zoom}"
    assert s._lbl_zoom.text() == "50 %", f"Erwartet '50 %', bekommen '{s._lbl_zoom.text()}'"


def test_zoom_100_percent():
    """100 als Slider-Wert => zoom=1.0, Label='100 %'."""
    _app()
    s = _ZoomStub()
    s._on_zoom_changed(100)
    assert s._canvas.zoom == 1.0, f"Erwartet 1.0, bekommen {s._canvas.zoom}"
    assert s._lbl_zoom.text() == "100 %", f"Erwartet '100 %', bekommen '{s._lbl_zoom.text()}'"
