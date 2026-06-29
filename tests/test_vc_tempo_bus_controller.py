"""Stufe 6 — neues All-in-One VCTempoBusController-Widget.

Deckt ab: Registrierung, Effekt-Kopplung (taktgleich), Faktor -> tempo_multiplier,
Quelle (fix/sound/tap) -> Bus-BPM/Rolle, Hit-Tests (Faktor/Sync/Quelle), Serialisierung.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QMouseEvent
from PySide6.QtCore import Qt, QPointF, QEvent
import pytest

_app = QApplication.instance() or QApplication([])

from src.core.engine.tempo_bus import get_tempo_bus_manager, reset_tempo_bus_manager
from src.core.engine.function_manager import get_function_manager
from src.core.engine.bpm_manager import get_bpm_manager
from src.core.engine.rgb_matrix import RgbMatrixInstance, RgbAlgorithm
from src.ui.virtualconsole.vc_tempo_bus_controller import VCTempoBusController


@pytest.fixture(autouse=True)
def _clean():
    reset_tempo_bus_manager()
    get_function_manager().from_dict({"functions": []})
    get_bpm_manager().set_locked(False)
    get_bpm_manager().reset()
    get_tempo_bus_manager().set_auto_sync(True)
    yield
    from src.core.show.show_file import reset_show
    reset_show()
    mgr = get_bpm_manager(); mgr.set_locked(False); mgr.reset()
    get_tempo_bus_manager().set_auto_sync(False)


def _matrix(name, bus_id="Global"):
    fm = get_function_manager()
    m = RgbMatrixInstance(name=name, cols=4, rows=1, algorithm=RgbAlgorithm.CHASE,
                          fixture_grid=[1, 2, 3, 4])
    m.tempo_bus_id = bus_id
    fm.add(m)
    return m


def _click(widget, rect):
    widget.resize(280, 196)
    c = rect.center()
    ev = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(c.x(), c.y()),
                     Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier)
    widget.mousePressEvent(ev)


def test_widget_registered():
    from src.ui.virtualconsole.vc_canvas import WIDGET_REGISTRY
    assert WIDGET_REGISTRY.get("VCTempoBusController") is VCTempoBusController


def test_couple_effect_assigns_bus_taktgleich():
    w = VCTempoBusController()
    w.tempo_bus_id = "A"
    m = _matrix("M", "Global")
    w.couple_effect(m.id)
    assert m.id in w._targets()
    assert m.tempo_bus_id == "A", "gekoppelter Effekt nicht auf den Controller-Bus gelegt"


def test_set_factor_drives_effect_multiplier():
    w = VCTempoBusController()
    w.tempo_bus_id = "A"
    m = _matrix("M", "Global")
    w.couple_effect(m.id)
    w.set_factor(2.0)
    assert abs(m.tempo_multiplier - 2.0) < 1e-9


def test_source_fix_sets_bus_bpm():
    tbm = get_tempo_bus_manager()
    w = VCTempoBusController()
    w.tempo_bus_id = "A"
    w.fixed_bpm = 140.0
    w.set_source("fix")
    busA = tbm.get("A")
    assert busA is not None and abs(busA.bpm - 140.0) < 2.0


def test_source_sound_makes_named_bus_sub_of_default():
    tbm = get_tempo_bus_manager()
    w = VCTempoBusController()
    w.tempo_bus_id = "B"
    w.set_source("sound")
    busB = tbm.get("B")
    assert busB is not None and busB.role == "sub", "Sound-Quelle: benannter Bus muss Sub des Default sein"


def test_hit_factor_cell_sets_factor():
    w = VCTempoBusController()
    w.resize(280, 196)
    # Faktor-Zelle fuer 2.0 finden
    target = next(r for r, f in w._factor_rects() if abs(f - 2.0) < 1e-6)
    _click(w, target)
    assert abs(w.factor - 2.0) < 1e-9


def test_hit_sync_reanchors_bus():
    tbm = get_tempo_bus_manager(); mgr = get_bpm_manager()
    mgr.set_manual_bpm(120.0)
    w = VCTempoBusController(); w.tempo_bus_id = "A"; w.resize(280, 196)
    busA = tbm.ensure_bus("A"); busA.set_bpm(120.0)
    busA.advance_frame(1.0); busA.advance_frame(1.0)
    assert busA.position() > 0.0
    _click(w, w._sync_rect())
    assert abs(busA.position()) < 1e-6, "SYNC jetzt hat den Bus nicht auf die Eins gesetzt"


def test_hit_source_button_sets_source():
    w = VCTempoBusController(); w.resize(280, 196)
    fix_rect = next(r for r, k in w._source_rects() if k == "fix")
    _click(w, fix_rect)
    assert w.source == "fix"


def test_roundtrip():
    w = VCTempoBusController()
    w.tempo_bus_id = "C"; w.source = "fix"; w.fixed_bpm = 145.0
    w.factor = 0.5; w.function_id = 5; w.function_ids = [6, 7]
    d = w.to_dict()
    assert d["type"] == "VCTempoBusController"
    w2 = VCTempoBusController()
    w2.apply_dict(d)
    assert w2.tempo_bus_id == "C"
    assert w2.source == "fix"
    assert abs(w2.fixed_bpm - 145.0) < 1e-9
    assert abs(w2.factor - 0.5) < 1e-9
    assert w2.function_id == 5 and w2.function_ids == [6, 7]


def test_remove_effect_unbinds_single():
    w = VCTempoBusController(); w.tempo_bus_id = "A"
    a = _matrix("A", "Global"); b = _matrix("B", "Global")
    w.couple_effect(a.id); w.couple_effect(b.id)
    assert set(w._targets()) == {a.id, b.id}
    w.remove_effect(a.id)
    assert a.id not in w._targets()
    assert b.id in w._targets()


def test_per_effect_param_key_default_and_roundtrip():
    w = VCTempoBusController(); w.tempo_bus_id = "A"
    m = _matrix("M", "Global"); w.couple_effect(m.id)
    assert w._key_for(m.id) == "tempo_multiplier"     # Default: Faktor steuert Tempo
    w.param_keys_per_id[m.id] = "speed"               # je Effekt waehlbar
    assert w._key_for(m.id) == "speed"
    w2 = VCTempoBusController(); w2.apply_dict(w.to_dict())
    assert w2.param_keys_per_id.get(m.id) == "speed"


def test_wheel_adjusts_fixed_bpm():
    w = VCTempoBusController(); w.source = "fix"; w.fixed_bpm = 128.0
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtCore import QPoint
    ev = QWheelEvent(QPointF(10, 10), QPointF(10, 10), QPoint(0, 0), QPoint(0, 120),
                     Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                     Qt.ScrollPhase.NoScrollPhase, False)
    w.wheelEvent(ev)
    assert w.fixed_bpm > 128.0
