"""LAS-18b: Werksmuster-Picker — PatternSlot-Modell + Kachel-UI in der
LaserView (Klasse-A-Gate, Abruf schreibt Bank/Muster, merken/löschen)."""
from __future__ import annotations
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.core.laser.pattern_slots import PatternSlot


def _app():
    return QApplication.instance() or QApplication([])


# ------------------------------------------------------------- Modell -------

def test_slot_roundtrip_with_image():
    s = PatternSlot(name="Kreis", bank=32, pattern=7, image_path="a/b.jpg")
    d = s.to_dict()
    back = PatternSlot.from_dict(d)
    assert (back.name, back.bank, back.pattern, back.image_path) == \
        ("Kreis", 32, 7, "a/b.jpg")


def test_slot_roundtrip_without_image_omits_key():
    d = PatternSlot(name="X", bank=1, pattern=2).to_dict()
    assert "image_path" not in d
    assert PatternSlot.from_dict(d).image_path == ""


def test_slot_clamps_and_defaults():
    s = PatternSlot.from_dict({"bank": 999, "pattern": -5})
    assert (s.bank, s.pattern) == (255, 0)
    assert PatternSlot.from_dict({"bank": "kaputt"}).bank == 0


def test_slot_label_fallback():
    assert PatternSlot(name="Fächer", bank=1, pattern=2).label == "Fächer"
    assert PatternSlot(bank=32, pattern=7).label == "B32/M7"


# ------------------------------------------------------------- View ---------
# Nutzt die Fakes aus test_laser_view (gleiche Konventionen: attr#N-Programmer,
# L2600-artiges Kanal-Layout).

from test_laser_view import _FX, _make_view, _l2600ish_channels  # noqa: E402


def _view_with_slots(monkeypatch, fixtures, slots):
    view, state = _make_view(monkeypatch, fixtures)
    state.laser_patterns = list(slots)
    # Klassifikator liest Kanäle über app_state.get_channels_for_patched.
    import src.core.app_state as app_state
    monkeypatch.setattr(app_state, "get_channels_for_patched",
                        lambda f: f._chans, raising=False)
    view.refresh_from_selection()
    return view, state


def test_picker_visible_for_builtin_dmx_laser(monkeypatch):
    _app()
    view, _ = _view_with_slots(
        monkeypatch, [_FX(1, _l2600ish_channels())],
        [PatternSlot(name="Kreis", bank=10, pattern=42)])
    assert view._pattern_box.isVisibleTo(view) is True
    assert view._pattern_grid.count() == 1               # eine Kachel


def test_picker_hidden_for_network_laser(monkeypatch):
    _app()
    fx = _FX(2, _l2600ish_channels())
    fx.protocol = "etherdream"                            # Klasse B
    view, _ = _view_with_slots(monkeypatch, [fx], [])
    assert view._pattern_box.isVisibleTo(view) is False


def test_picker_hidden_without_pattern_channel(monkeypatch):
    _app()
    from test_laser_view import _Ch
    # Laser-Typ, aber KEIN gobo_wheel -> kein Picker.
    view, _ = _view_with_slots(
        monkeypatch, [_FX(3, [_Ch("laser_x", 1)])], [])
    assert view._pattern_box.isVisibleTo(view) is False


def test_apply_slot_writes_bank_and_pattern(monkeypatch):
    _app()
    view, state = _view_with_slots(
        monkeypatch, [_FX(1, _l2600ish_channels())], [])
    view._apply_pattern_slot(PatternSlot(name="K", bank=33, pattern=77))
    assert state.get_programmer_value(1, "laser_bank") == 33
    assert state.get_programmer_value(1, "gobo_wheel") == 77


def test_apply_slot_without_bank_channel(monkeypatch):
    _app()
    from test_laser_view import _Ch
    # Gerät ohne laser_bank (nur Musterauswahl): Bank wird NICHT geschrieben.
    view, state = _view_with_slots(
        monkeypatch, [_FX(4, [_Ch("gobo_wheel", 1), _Ch("laser_x", 2)])], [])
    view._apply_pattern_slot(PatternSlot(bank=9, pattern=55))
    assert state.get_programmer_value(4, "gobo_wheel") == 55
    assert state.get_programmer_value(4, "laser_bank") is None


def test_add_slot_captures_current_values(monkeypatch):
    _app()
    import src.ui.views.laser_view as lv
    view, state = _view_with_slots(
        monkeypatch, [_FX(1, _l2600ish_channels())], [])
    state.set_programmer_value(1, "laser_bank", 32)
    state.set_programmer_value(1, "gobo_wheel", 7)
    monkeypatch.setattr(lv.QInputDialog, "getText",
                        staticmethod(lambda *a, **k: ("Mein Kreis", True)))
    # Foto-Dialog: Abbrechen (kein Foto).
    from PySide6.QtWidgets import QFileDialog
    monkeypatch.setattr(QFileDialog, "getOpenFileName",
                        staticmethod(lambda *a, **k: ("", "")))
    view._add_pattern_slot()
    assert len(state.laser_patterns) == 1
    slot = state.laser_patterns[0]
    assert (slot.name, slot.bank, slot.pattern) == ("Mein Kreis", 32, 7)
    assert slot.image_path == ""


def test_add_slot_cancel_name_aborts(monkeypatch):
    _app()
    import src.ui.views.laser_view as lv
    view, state = _view_with_slots(
        monkeypatch, [_FX(1, _l2600ish_channels())], [])
    monkeypatch.setattr(lv.QInputDialog, "getText",
                        staticmethod(lambda *a, **k: ("", False)))
    view._add_pattern_slot()
    assert getattr(state, "laser_patterns", []) == []


def test_delete_slot_removes_only_that_slot(monkeypatch):
    _app()
    a = PatternSlot(name="A", bank=1, pattern=1)
    b = PatternSlot(name="B", bank=2, pattern=2)
    view, state = _view_with_slots(
        monkeypatch, [_FX(1, _l2600ish_channels())], [a, b])
    view._delete_pattern_slot(a)
    assert state.laser_patterns == [b]
    assert view._pattern_grid.count() == 1
