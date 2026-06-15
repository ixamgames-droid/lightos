"""F-10: Auto-Save-Intervall konfigurierbar (1–60 min, Default 5).

Testet die Intervall-Aufloesung/Klemmung entkoppelt von der (schweren) MainWindow:
``MainWindow._autosave_minutes`` nutzt ``self`` nicht und liest nur die ui_prefs,
daher genuegt ein Dummy-Empfaenger + gepatchtes ``_load_prefs`` (keine echte
ui_prefs.json wird angefasst).
"""
import pytest

from src.ui.main_window import MainWindow
from src.ui.views import programmer_view


class _Dummy:
    pass


@pytest.mark.parametrize("prefs, expected", [
    ({}, 5),                                   # Default
    ({"autosave_minutes": 12}, 12),            # im Bereich
    ({"autosave_minutes": 1}, 1),              # untere Grenze
    ({"autosave_minutes": 60}, 60),            # obere Grenze
    ({"autosave_minutes": 999}, 60),           # zu gross -> geklemmt
    ({"autosave_minutes": 0}, 1),              # zu klein -> geklemmt
    ({"autosave_minutes": -5}, 1),             # negativ -> geklemmt
    ({"autosave_minutes": "abc"}, 5),          # unparsebar -> Default
])
def test_autosave_minutes_resolution(monkeypatch, prefs, expected):
    monkeypatch.setattr(programmer_view, "_load_prefs", lambda: dict(prefs))
    assert MainWindow._autosave_minutes(_Dummy()) == expected
