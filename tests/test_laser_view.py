"""Headless-Tests fuer die Laser-Steuerseite (LAS-02).

Deckt ab: Capability-Erkennung, Tab-Sichtbarkeit im Programmer (Muster wie
test_programmer_caps_tabs), Template/Regler-Aufbau, Kopf-Modi A/B/A+B
(Mehrkopf attr#N inkl. ENG-03-Guard) und Laser-Muster-Paletten
(PaletteType.LASER, Aufnahme/Anwenden-Roundtrip).
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


class _Rng:
    def __init__(self, lo, hi, name, kind=""):
        self.range_from = lo
        self.range_to = hi
        self.name = name
        self.kind = kind


class _Ch:
    def __init__(self, attr, num, ranges=None, name=""):
        self.attribute = attr
        self.channel_number = num
        self.ranges = ranges or []
        self.name = name or attr


class _FX:
    def __init__(self, fid, chans, fixture_type="laser", name="Laser"):
        self.fid = fid
        self.label = name
        self.fixture_name = name
        self.fixture_type = fixture_type
        self.universe = 1
        self.address = 1
        self._chans = chans


class _FakeState:
    """Minimaler Programmer-State (attr#N-Konvention wie AppState)."""

    def __init__(self, fixtures):
        self._fixtures = list(fixtures)
        self.programmer: dict[int, dict[str, int]] = {}
        self.calls: list[tuple] = []

    def get_patched_fixtures(self):
        return list(self._fixtures)

    def get_selected_fids(self):
        return [f.fid for f in self._fixtures]

    def set_programmer_value(self, fid, attr, value, undoable=False, head=0):
        key = attr if head == 0 else f"{attr}#{head}"
        self.programmer.setdefault(fid, {})[key] = int(value)
        self.calls.append((fid, attr, int(value), head))

    def get_programmer_value(self, fid, attr, head=0):
        key = attr if head == 0 else f"{attr}#{head}"
        return self.programmer.get(fid, {}).get(key)


def _l2600ish_channels():
    """Kompaktes L2600-artiges Layout: Gruppe A + B (2. Vorkommen = Kopf 1),
    laser_bank existiert nur einmal (wie am echten Geraet)."""
    shutter_ranges = [_Rng(0, 0, "Aus", "closed"), _Rng(1, 99, "Auto"),
                      _Rng(100, 199, "Sound", "sound"),
                      _Rng(255, 255, "Muster", "open")]
    return [
        _Ch("shutter", 1, shutter_ranges, "A: Laser An/Aus"),
        _Ch("laser_bank", 2, [_Rng(0, 223, "Bänke 1-14"),
                              _Rng(224, 255, "Bank 0")], "A: Musterbank"),
        _Ch("gobo_wheel", 3, [_Rng(0, 255, "Muster", "gobo")],
            "A: Musterauswahl"),
        _Ch("laser_x", 4, [_Rng(0, 127, "Position statisch"),
                           _Rng(128, 255, "Dynamisch")], "A: X-Bewegung"),
        _Ch("shutter", 5, shutter_ranges, "B: Laser An/Aus"),
        _Ch("gobo_wheel", 6, [_Rng(0, 255, "Muster", "gobo")],
            "B: Musterauswahl"),
        _Ch("laser_x", 7, [_Rng(0, 127, "Position statisch"),
                           _Rng(128, 255, "Dynamisch")], "B: X-Bewegung"),
    ]


def _make_view(monkeypatch, fixtures):
    import src.ui.views.laser_view as lv
    state = _FakeState(fixtures)
    monkeypatch.setattr(lv, "get_state", lambda: state)
    monkeypatch.setattr(lv, "get_channels_for_patched", lambda f: f._chans)
    view = lv.LaserView(follow_selection=False)
    return view, state


# ---------------------------------------------------------------------------
# Capability-Erkennung
# ---------------------------------------------------------------------------

def test_fixture_has_laser_capability(monkeypatch):
    _app()
    import src.ui.views.laser_view as lv
    # Die Kanal-Erkennung läuft jetzt über den Klassifikator
    # (capability.is_laser_fixture → app_state.get_channels_for_patched).
    import src.core.app_state as app_state
    monkeypatch.setattr(app_state, "get_channels_for_patched",
                        lambda f: f._chans, raising=False)

    assert lv.fixture_has_laser_capability(
        _FX(1, [], fixture_type="laser")) is True
    # Kein Typ, aber laser_*-Kanaele (z. B. QXF-Import mit Typ 'other').
    assert lv.fixture_has_laser_capability(
        _FX(2, [_Ch("laser_x", 1)], fixture_type="other")) is True
    assert lv.fixture_has_laser_capability(
        _FX(3, [_Ch("color_r", 1)], fixture_type="par")) is False


# ---------------------------------------------------------------------------
# Tab-Sichtbarkeit im Programmer (Muster: test_programmer_caps_tabs)
# ---------------------------------------------------------------------------

def _isolate_prefs(tmp_path, monkeypatch):
    import src.ui.views.programmer_view as pv
    monkeypatch.setattr(pv, "_PREFS_DIR", str(tmp_path))
    monkeypatch.setattr(pv, "_PREFS_PATH", str(tmp_path / "ui_prefs.json"))


def _build_pv(tmp_path, monkeypatch, fixtures: dict):
    import src.ui.views.programmer_view as pvmod
    import src.ui.views.laser_view as lv
    from src.ui.views.programmer_view import ProgrammerView

    _isolate_prefs(tmp_path, monkeypatch)
    monkeypatch.setattr(pvmod, "get_channels_for_patched", lambda f: f._chans)
    monkeypatch.setattr(lv, "get_channels_for_patched", lambda f: f._chans)

    pv = ProgrammerView()
    monkeypatch.setattr(pv._state, "get_patched_fixtures",
                        lambda: list(fixtures.values()))
    monkeypatch.setattr(pv, "_build_group_tab", lambda *a, **k: QLabel("x"))
    monkeypatch.setattr(pv, "_push_selection_to_preview", lambda *a, **k: None)
    monkeypatch.setattr(pv, "_update_fixture_combo", lambda *a, **k: None)
    monkeypatch.setattr(pv._color_preview, "set_fixtures", lambda *a, **k: None)
    return pv


def test_laser_tab_hidden_for_par(tmp_path, monkeypatch):
    _app()
    fixtures = {1: _FX(1, [_Ch("color_r", 1)], fixture_type="par")}
    pv = _build_pv(tmp_path, monkeypatch, fixtures)
    pv._selected_fids = [1]
    pv._rebuild_attr_editor()
    assert pv._main_tabs.isTabVisible(pv._laser_tab_index) is False


def test_laser_tab_visible_for_laser(tmp_path, monkeypatch):
    _app()
    fixtures = {2: _FX(2, _l2600ish_channels(), fixture_type="laser")}
    pv = _build_pv(tmp_path, monkeypatch, fixtures)
    pv._selected_fids = [2]
    pv._rebuild_attr_editor()
    assert pv._main_tabs.isTabVisible(pv._laser_tab_index) is True


def test_laser_tab_visible_mixed_selection(tmp_path, monkeypatch):
    _app()
    fixtures = {
        1: _FX(1, [_Ch("color_r", 1)], fixture_type="par"),
        2: _FX(2, _l2600ish_channels(), fixture_type="laser"),
    }
    pv = _build_pv(tmp_path, monkeypatch, fixtures)
    pv._selected_fids = [1, 2]
    pv._rebuild_attr_editor()
    assert pv._main_tabs.isTabVisible(pv._laser_tab_index) is True


# ---------------------------------------------------------------------------
# LaserView: Template, Kopf-Modi, Schreiben
# ---------------------------------------------------------------------------

def test_template_rows_and_head_box(monkeypatch):
    _app()
    view, _state = _make_view(
        monkeypatch, [_FX(1, _l2600ish_channels())])

    # Ein Regler je Laser-Attribut (Union, nicht je Kanal-Vorkommen).
    # `shutter` steckt in den Betriebsart-Kacheln und bekommt KEINE eigene
    # Regler-Zeile mehr (LAS-11: keine Doppelung Kachel + Slider).
    assert set(view._rows) == {"laser_bank", "gobo_wheel", "laser_x"}
    assert "shutter" not in view._rows
    # Gruppe A/B vorhanden (Attribute doppelt) -> Umschalter sichtbar.
    assert view._max_head_count() == 2
    # Modus-Kacheln aus den Shutter-Ranges.
    tiles = view._mode_lay.count() - 1  # minus Stretch
    assert tiles == 4


def _row_group_boxes(view):
    """Die benannten Regler-Gruppen (QGroupBox) im Scroll-Bereich, in
    Anzeige-Reihenfolge."""
    from PySide6.QtWidgets import QGroupBox
    boxes = []
    for i in range(view._rows_lay.count()):
        w = view._rows_lay.itemAt(i).widget()
        if isinstance(w, QGroupBox):
            boxes.append(w)
    return boxes


def test_rows_grouped_by_meaning(monkeypatch):
    """LAS-11: Regler sind nach Bedeutung gruppiert (Muster / Bewegung …),
    nicht mehr eine flache Kanal-Liste."""
    _app()
    view, _state = _make_view(monkeypatch, [_FX(1, _l2600ish_channels())])
    titles = [b.title() for b in _row_group_boxes(view)]
    # Muster (gobo_wheel, laser_bank) und Bewegung (laser_x) sind vorhanden;
    # Reihenfolge: Muster vor Bewegung.
    assert "Muster" in titles
    assert "Bewegung & Geschwindigkeit" in titles
    assert titles.index("Muster") < titles.index(
        "Bewegung & Geschwindigkeit")
    # Nur Gruppen mit vorhandenen Attributen tauchen auf — hier keine
    # Farb-/Zeichnen-Kanäle im Kompakt-Layout.
    assert "Farbe" not in titles


def test_advanced_group_collapsed_and_toggles(monkeypatch):
    """Technische Kanäle landen in einer eingeklappten, aufklappbaren Gruppe;
    Umschalten zeigt/versteckt die Regler-Zeilen."""
    _app()
    # laser_grating ist in KEINER Kern-Gruppe -> „Weitere Kanäle".
    chans = _l2600ish_channels() + [_Ch("laser_grating", 8,
                                        [_Rng(0, 255, "Gitter")], "Gitter")]
    view, _state = _make_view(monkeypatch, [_FX(1, chans)])

    adv = next((b for b in _row_group_boxes(view)
                if b.title() == "Weitere Kanäle"), None)
    assert adv is not None
    assert adv.isCheckable() is True
    assert adv.isChecked() is False                      # eingeklappt
    row = view._rows["laser_grating"]
    assert row.isVisibleTo(view) is False                # Zeile versteckt

    adv.setChecked(True)                                 # aufklappen
    assert row.isVisibleTo(view) is True
    adv.setChecked(False)
    assert row.isVisibleTo(view) is False


def test_write_respects_head_mode(monkeypatch):
    _app()
    view, state = _make_view(monkeypatch, [_FX(1, _l2600ish_channels())])

    view._write_value("laser_x", 100)                    # Modus A (Default)
    assert (1, "laser_x", 100, 0) in state.calls
    assert not any(c[3] == 1 for c in state.calls)

    state.calls.clear()
    view._set_head_mode("B")
    view._write_value("laser_x", 120)
    assert state.calls == [(1, "laser_x", 120, 1)]
    assert state.get_programmer_value(1, "laser_x", head=1) == 120

    state.calls.clear()
    view._set_head_mode("AB")
    view._write_value("gobo_wheel", 42)
    assert (1, "gobo_wheel", 42, 0) in state.calls
    assert (1, "gobo_wheel", 42, 1) in state.calls


def test_single_occurrence_attr_not_written_on_head_b(monkeypatch):
    """ENG-03-Guard: laser_bank existiert nur 1x — Kopf-B-Modus darf keinen
    Bogus-Key laser_bank#1 erzeugen."""
    _app()
    view, state = _make_view(monkeypatch, [_FX(1, _l2600ish_channels())])
    view._set_head_mode("B")
    view._write_value("laser_bank", 200)
    assert state.calls == []
    view._set_head_mode("AB")
    view._write_value("laser_bank", 200)
    assert state.calls == [(1, "laser_bank", 200, 0)]


def test_row_change_writes_and_loads_back(monkeypatch):
    _app()
    view, state = _make_view(monkeypatch, [_FX(1, _l2600ish_channels())])
    row = view._rows["laser_x"]
    row._slider.setValue(64)
    assert state.get_programmer_value(1, "laser_x") == 64
    # Reload zeigt den gespeicherten Wert wieder an.
    state.programmer[1]["laser_x"] = 99
    view._load_values()
    assert row._slider.value() == 99


def test_no_laser_selected_shows_hint(monkeypatch):
    _app()
    view, _state = _make_view(
        monkeypatch, [])
    assert "Kein Laser" in view._info.text()
    assert view._head_box.isVisibleTo(view) is False


def test_network_laser_shows_safety_box(monkeypatch):
    """LAS-12: der Fähigkeits-Klassifikator steuert das Safety-Box-Gating —
    ein Netzwerk-Streaming-Laser (Klasse B) zeigt Scharf/Not-Aus + Figur."""
    _app()
    fx = _FX(2, _l2600ish_channels())
    fx.protocol = "etherdream"
    view, _state = _make_view(monkeypatch, [fx])
    assert view._network_fids == [2]
    assert view._safety_box.isVisibleTo(view) is True


def test_dmx_laser_hides_safety_box(monkeypatch):
    """Reiner DMX-Muster-Laser (Klasse A, L2600) → keine Netzwerk-Safety-Box."""
    _app()
    view, _state = _make_view(monkeypatch, [_FX(1, _l2600ish_channels())])
    assert view._network_fids == []
    assert view._safety_box.isVisibleTo(view) is False


# ---------------------------------------------------------------------------
# Laser-Muster-Paletten (PaletteType.LASER)
# ---------------------------------------------------------------------------

def test_laser_palette_roundtrip(monkeypatch):
    """record_from_programmer filtert auf Laser-Attribute (inkl. attr#N),
    apply_to_programmer schreibt sie kopf-korrekt zurueck."""
    _app()
    from src.core.engine.palette import Palette, PaletteType

    fx = _FX(1, _l2600ish_channels())
    state = _FakeState([fx])
    import src.core.app_state as app_state
    monkeypatch.setattr(app_state, "get_state", lambda: state)
    monkeypatch.setattr(app_state, "get_channels_for_patched",
                        lambda f: f._chans)

    state.set_programmer_value(1, "shutter", 255)
    state.set_programmer_value(1, "laser_x", 64)
    state.set_programmer_value(1, "laser_x", 120, head=1)
    state.set_programmer_value(1, "gobo_wheel", 42)
    # Nicht-Laser-Attribut darf NICHT in der Laser-Palette landen.
    state.programmer[1]["color_r"] = 255

    p = Palette(name="Test-Muster", type=PaletteType.LASER)
    p.record_from_programmer([1])
    assert p.fixture_values[1]["laser_x"] == 64
    assert p.fixture_values[1]["laser_x#1"] == 120
    assert p.fixture_values[1]["shutter"] == 255
    assert "color_r" not in p.fixture_values[1]

    state.programmer.clear()
    p.apply_to_programmer([1])
    assert state.get_programmer_value(1, "laser_x") == 64
    assert state.get_programmer_value(1, "laser_x", head=1) == 120
    assert state.get_programmer_value(1, "shutter") == 255
    assert state.get_programmer_value(1, "color_r") is None


def test_palette_type_laser_registered():
    from src.core.engine.palette import Palette, PaletteType
    allowed = Palette.ATTR_GROUPS[PaletteType.LASER]
    assert "laser_x" in allowed and "gobo_wheel" in allowed
    # Serialisierung rundet ueber den Enum-Wert.
    p = Palette(name="x", type=PaletteType.LASER)
    assert Palette.from_dict(p.to_dict()).type == PaletteType.LASER


def test_save_palette_records_selection(monkeypatch):
    _app()
    import src.ui.views.laser_view as lv
    from src.core.engine.palette import PaletteType, get_palette_manager

    view, state = _make_view(monkeypatch, [_FX(1, _l2600ish_channels())])
    # record_from_programmer laeuft ueber src.core.app_state.get_state.
    import src.core.app_state as app_state
    monkeypatch.setattr(app_state, "get_state", lambda: state)
    monkeypatch.setattr(app_state, "get_channels_for_patched",
                        lambda f: f._chans)
    monkeypatch.setattr(
        lv.QInputDialog, "getText",
        staticmethod(lambda *a, **k: ("Kreis gross", True)))

    state.set_programmer_value(1, "laser_x", 77)
    view._save_palette()

    manager = get_palette_manager()
    saved = manager.find("Kreis gross")
    try:
        assert saved is not None
        assert saved.type == PaletteType.LASER
        assert saved.fixture_values[1]["laser_x"] == 77
    finally:
        if saved is not None:
            manager.remove(saved)
