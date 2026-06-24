"""Headless-Tests fuer den 5-Zonen-Programmer (LAYOUT-01..07).

Prueft, dass ProgrammerView in beiden Layout-Modi baut, der Umschalter den Modus
wechselt und die neuen Zonen-Widgets existieren und nicht werfen.
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _isolate_prefs(tmp_path, monkeypatch):
    """ui_prefs.json auf eine Temp-Datei umleiten (echte Prefs nicht anfassen)."""
    import src.ui.views.programmer_view as pv
    monkeypatch.setattr(pv, "_PREFS_DIR", str(tmp_path))
    monkeypatch.setattr(pv, "_PREFS_PATH", str(tmp_path / "ui_prefs.json"))


def test_programmer_classic_builds(tmp_path, monkeypatch):
    _app()
    _isolate_prefs(tmp_path, monkeypatch)
    from src.ui.views.programmer_view import ProgrammerView

    pv = ProgrammerView()
    assert pv._layout_mode == "zones"            # Default seit Phase 0 = Zonen
    assert pv._snap_file_panel is not None
    # WP-5: einheitliche Tab-Leiste statt der frueheren Attribut-Tabs.
    assert hasattr(pv, "_main_tabs")
    assert hasattr(pv, "_attr_group_tabs")


def test_programmer_zones_has_five_zones(tmp_path, monkeypatch):
    _app()
    _isolate_prefs(tmp_path, monkeypatch)
    from src.ui.views.programmer_view import ProgrammerView

    pv = ProgrammerView()
    assert pv._layout_mode == "zones"             # Default ist bereits Zonen

    # LINKS / MITTE / UNTEN / RECHTS
    assert hasattr(pv, "_fixture_list")           # LINKS
    assert pv._snap_file_panel is not None        # RECHTS (Snap-Browser, Effekt-Preview entfernt I2.7)
    # MITTE: WP-5 — EINE Tab-Leiste statt Kategorie-Leiste + Stack.
    # M2.1: "Gobo" als eigener Tab (standardmaessig versteckt, nur bei
    # Gobo-faehigen Fixtures sichtbar) zwischen Position und Weitere.
    # M-Map: "Mapping" (Kanal-Mapping) zwischen Weitere und Helper, ebenfalls
    # standardmaessig versteckt (nur bei Pan/Tilt-Geraeten sichtbar).
    labels = [pv._main_tabs.tabText(i) for i in range(pv._main_tabs.count())]
    assert labels == ["Intensity", "Color", "Position", "Gobo", "Weitere",
                      "Mapping", "Hilfe", "EFX", "Matrix", "Paletten"], labels
    # Gobo-, Mapping-, Position- und EFX-Tab sind ohne Auswahl ausgeblendet.
    assert pv._main_tabs.isTabVisible(pv._gobo_tab_index) is False
    assert pv._main_tabs.isTabVisible(pv._mapping_tab_index) is False
    assert pv._main_tabs.isTabVisible(pv._position_tab_index) is False
    assert pv._main_tabs.isTabVisible(pv._efx_tab_index) is False
    assert pv._tile_preview is not None           # UNTEN

    # Tab-Wechsel wirft nicht.
    for i in range(pv._main_tabs.count()):
        pv._main_tabs.setCurrentIndex(i)

    # Zonen-Widgets nehmen Daten an, ohne zu werfen.
    pv._tile_preview.set_fixtures([1, 2, 3])


def test_mapping_tab_visible_for_movinghead(tmp_path, monkeypatch):
    """Regression (M-Map): Der „Mapping"-Tab erscheint, sobald ein Pan/Tilt-Geraet
    (Moving Head/Spider) ausgewaehlt ist, und bleibt bei PAR / ohne Auswahl
    versteckt. Frueher fehlte der Einblend-Schalter -> Tab blieb dauerhaft weg."""
    _app()
    _isolate_prefs(tmp_path, monkeypatch)
    import src.ui.views.programmer_view as pvmod
    from src.ui.views.programmer_view import ProgrammerView
    from PySide6.QtWidgets import QLabel

    class _Ch:
        def __init__(self, attr, num):
            self.attribute = attr
            self.channel_number = num

    class _FX:
        def __init__(self, fid, label, chans):
            self.fid = fid
            self.label = label
            self.universe = 1
            self.address = 1
            self._chans = chans

    fixtures = {
        1: _FX(1, "MH", [_Ch("pan", 1), _Ch("tilt", 2), _Ch("color_r", 3)]),
        2: _FX(2, "Spider", [_Ch("tilt", 1), _Ch("tilt", 2), _Ch("color_r", 3)]),
        3: _FX(3, "PAR", [_Ch("dimmer", 1), _Ch("color_r", 2)]),
    }
    monkeypatch.setattr(pvmod, "get_channels_for_patched", lambda f: f._chans)

    pv = ProgrammerView()
    monkeypatch.setattr(pv._state, "get_patched_fixtures",
                        lambda: list(fixtures.values()))
    # Schwergewichtige Bau-Schritte isolieren — getestet wird die Tab-Sichtbarkeit.
    monkeypatch.setattr(pv, "_build_group_tab", lambda *a, **k: QLabel("x"))
    monkeypatch.setattr(pv, "_push_selection_to_preview", lambda *a, **k: None)
    monkeypatch.setattr(pv, "_update_fixture_combo", lambda *a, **k: None)
    monkeypatch.setattr(pv._color_preview, "set_fixtures", lambda *a, **k: None)

    idx = pv._mapping_tab_index
    assert pv._main_tabs.isTabVisible(idx) is False        # nichts ausgewaehlt

    pv._selected_fids = [1]
    pv._rebuild_attr_editor()
    assert pv._main_tabs.isTabVisible(idx) is True         # Moving Head (pan/tilt)

    pv._selected_fids = [2]
    pv._rebuild_attr_editor()
    assert pv._main_tabs.isTabVisible(idx) is True         # Spider (2x tilt)

    pv._selected_fids = [3]
    pv._rebuild_attr_editor()
    assert pv._main_tabs.isTabVisible(idx) is False        # PAR (kein pan/tilt)

    pv._selected_fids = [3, 1]
    pv._rebuild_attr_editor()
    assert pv._main_tabs.isTabVisible(idx) is True         # gemischt, MH dabei

    pv._selected_fids = []
    pv._rebuild_attr_editor()
    assert pv._main_tabs.isTabVisible(idx) is False


def test_programmer_layout_toggle_roundtrip(tmp_path, monkeypatch):
    _app()
    _isolate_prefs(tmp_path, monkeypatch)
    from src.ui.views.programmer_view import ProgrammerView

    pv = ProgrammerView()
    assert pv._layout_mode == "zones"             # Default = Zonen
    assert pv._tile_preview is not None
    pv._toggle_layout()                           # zones -> classic
    assert pv._layout_mode == "classic"
    # Zonen-Referenzen nach Wechsel invalidiert.
    assert pv._tile_preview is None

    # Modus wurde persistiert.
    import src.ui.views.programmer_view as pvmod
    assert pvmod._load_prefs().get("programmer_layout") == "classic"

    pv._toggle_layout()                           # classic -> zones (Roundtrip)
    assert pv._layout_mode == "zones"
    assert pv._tile_preview is not None
    assert pvmod._load_prefs().get("programmer_layout") == "zones"


def test_fixture_tile_preview_collapse(tmp_path, monkeypatch):
    _app()
    from src.ui.widgets.fixture_tile_preview import FixtureTilePreview

    w = FixtureTilePreview()
    assert w.is_collapsed() is False
    w.toggle_collapsed()
    assert w.is_collapsed() is True
    w.set_fixtures([1, 2])           # darf eingeklappt nicht werfen
    w.set_collapsed(False)
    assert w.is_collapsed() is False


def test_effect_mini_preview_play(tmp_path, monkeypatch):
    _app()
    from src.ui.widgets.effect_mini_preview import EffectMiniPreview
    from src.core.engine.rgb_matrix import RgbAlgorithm

    w = EffectMiniPreview(cols=8, rows=2)
    w.play(algorithm=RgbAlgorithm.CHASE, color1=(0, 255, 0), speed=4.0, label="X")
    w.play(algorithm="Rainbow")      # String-Variante
    w.play(algorithm="Unbekannt")    # Fallback ohne Exception
    w._grid.refresh()                # ein Frame rendern
