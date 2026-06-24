"""Headless-Tests: Position- und EFX-Tab im Programmer nur sichtbar bei Pan/Tilt.

Prueft, dass beide Tabs ausgeblendet sind, wenn die Auswahl keine Pan/Tilt-
Kanaele besitzt (Strahler/RGB-Spider), und sichtbar sind, sobald ein Moving
Head oder Tilt-Spider ausgewaehlt wird.
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _isolate_prefs(tmp_path, monkeypatch):
    """ui_prefs.json auf eine Temp-Datei umleiten."""
    import src.ui.views.programmer_view as pv
    monkeypatch.setattr(pv, "_PREFS_DIR", str(tmp_path))
    monkeypatch.setattr(pv, "_PREFS_PATH", str(tmp_path / "ui_prefs.json"))


class _Ch:
    def __init__(self, attr: str, num: int):
        self.attribute = attr
        self.channel_number = num


class _FX:
    def __init__(self, fid: int, label: str, chans):
        self.fid = fid
        self.label = label
        self.universe = 1
        self.address = 1
        self._chans = chans


def _build_pv(tmp_path, monkeypatch, fixtures: dict):
    """Hilfsfunktion: ProgrammerView mit gemockter Geraetebasis aufbauen."""
    import src.ui.views.programmer_view as pvmod
    from src.ui.views.programmer_view import ProgrammerView

    _isolate_prefs(tmp_path, monkeypatch)
    monkeypatch.setattr(pvmod, "get_channels_for_patched", lambda f: f._chans)

    pv = ProgrammerView()
    monkeypatch.setattr(pv._state, "get_patched_fixtures",
                        lambda: list(fixtures.values()))
    # Schwere Bau-Schritte isolieren — nur Tab-Sichtbarkeit wird geprueft.
    monkeypatch.setattr(pv, "_build_group_tab", lambda *a, **k: QLabel("x"))
    monkeypatch.setattr(pv, "_push_selection_to_preview", lambda *a, **k: None)
    monkeypatch.setattr(pv, "_update_fixture_combo", lambda *a, **k: None)
    monkeypatch.setattr(pv._color_preview, "set_fixtures", lambda *a, **k: None)
    return pv


# ---------------------------------------------------------------------------
# Testfaelle
# ---------------------------------------------------------------------------

def test_position_efx_hidden_for_dimmer(tmp_path, monkeypatch):
    """Reines Dimmer/PAR-Fixture: Position- und EFX-Tab bleiben ausgeblendet."""
    _app()
    fixtures = {
        1: _FX(1, "PAR", [_Ch("dimmer", 1), _Ch("color_r", 2), _Ch("color_g", 3)]),
    }
    pv = _build_pv(tmp_path, monkeypatch, fixtures)

    pv._selected_fids = [1]
    pv._rebuild_attr_editor()

    assert pv._main_tabs.isTabVisible(pv._position_tab_index) is False, \
        "Position-Tab muss bei Dimmer versteckt sein"
    assert pv._main_tabs.isTabVisible(pv._efx_tab_index) is False, \
        "EFX-Tab muss bei Dimmer versteckt sein"


def test_position_efx_hidden_for_rgb_spider(tmp_path, monkeypatch):
    """RGB-Spider (kein Pan/Tilt): Position/EFX weg, Matrix-Tab bleibt."""
    _app()
    fixtures = {
        2: _FX(2, "RGB-Spider", [_Ch("color_r", 1), _Ch("color_g", 2),
                                  _Ch("color_b", 3), _Ch("dimmer", 4)]),
    }
    pv = _build_pv(tmp_path, monkeypatch, fixtures)

    pv._selected_fids = [2]
    pv._rebuild_attr_editor()

    assert pv._main_tabs.isTabVisible(pv._position_tab_index) is False
    assert pv._main_tabs.isTabVisible(pv._efx_tab_index) is False
    # Matrix-Tab darf NICHT veraendert werden (RGB-Spider benoetigt ihn).
    assert pv._main_tabs.isTabVisible(pv._matrix_tab_index) is True


def test_position_efx_visible_for_moving_head(tmp_path, monkeypatch):
    """Moving Head (pan + tilt): Position- und EFX-Tab sichtbar."""
    _app()
    fixtures = {
        3: _FX(3, "MH", [_Ch("pan", 1), _Ch("tilt", 2),
                          _Ch("color_r", 3), _Ch("dimmer", 4)]),
    }
    pv = _build_pv(tmp_path, monkeypatch, fixtures)

    pv._selected_fids = [3]
    pv._rebuild_attr_editor()

    assert pv._main_tabs.isTabVisible(pv._position_tab_index) is True, \
        "Position-Tab muss bei Moving Head sichtbar sein"
    assert pv._main_tabs.isTabVisible(pv._efx_tab_index) is True, \
        "EFX-Tab muss bei Moving Head sichtbar sein"


def test_position_efx_visible_for_tilt_spider(tmp_path, monkeypatch):
    """Tilt-Spider (nur tilt): Position- und EFX-Tab sichtbar."""
    _app()
    fixtures = {
        4: _FX(4, "Tilt-Spider", [_Ch("tilt", 1), _Ch("tilt", 2),
                                   _Ch("color_r", 3)]),
    }
    pv = _build_pv(tmp_path, monkeypatch, fixtures)

    pv._selected_fids = [4]
    pv._rebuild_attr_editor()

    assert pv._main_tabs.isTabVisible(pv._position_tab_index) is True
    assert pv._main_tabs.isTabVisible(pv._efx_tab_index) is True


def test_position_efx_hidden_when_no_selection(tmp_path, monkeypatch):
    """Keine Auswahl: Position- und EFX-Tab ausgeblendet."""
    _app()
    fixtures = {
        3: _FX(3, "MH", [_Ch("pan", 1), _Ch("tilt", 2)]),
    }
    pv = _build_pv(tmp_path, monkeypatch, fixtures)

    # Zuerst Moving Head auswaehlen (macht Tabs sichtbar), dann Auswahl leeren.
    pv._selected_fids = [3]
    pv._rebuild_attr_editor()
    assert pv._main_tabs.isTabVisible(pv._position_tab_index) is True

    pv._selected_fids = []
    pv._rebuild_attr_editor()
    assert pv._main_tabs.isTabVisible(pv._position_tab_index) is False
    assert pv._main_tabs.isTabVisible(pv._efx_tab_index) is False


def test_position_efx_visible_mixed_selection(tmp_path, monkeypatch):
    """Gemischte Auswahl (PAR + MH): Tabs sichtbar, weil MH Pan/Tilt hat."""
    _app()
    fixtures = {
        1: _FX(1, "PAR", [_Ch("dimmer", 1)]),
        3: _FX(3, "MH", [_Ch("pan", 1), _Ch("tilt", 2)]),
    }
    pv = _build_pv(tmp_path, monkeypatch, fixtures)

    pv._selected_fids = [1, 3]
    pv._rebuild_attr_editor()

    assert pv._main_tabs.isTabVisible(pv._position_tab_index) is True
    assert pv._main_tabs.isTabVisible(pv._efx_tab_index) is True
