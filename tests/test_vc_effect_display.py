"""Welle 4 (L-Restscope): VCEffectDisplay — eigenständiges Live-Render-Widget.

Rendert den gebundenen Effekt LIVE (Matrix-Pixel), zeigt Platzhalter ohne Bindung,
serialisiert die function_id und ist per Funktions-Drop bindbar.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication


def _app():
    return QApplication.instance() or QApplication([])


def _matrix():
    from src.core.engine.function_manager import get_function_manager
    from src.core.engine.rgb_matrix import RgbMatrixInstance, RgbAlgorithm
    fm = get_function_manager()
    m = RgbMatrixInstance(name="M", cols=4, rows=1, fixture_grid=[1, 2, 3, 4],
                          algorithm=RgbAlgorithm.CHASE)
    fm.add(m)
    return fm, m


def test_registered_and_droppable():
    _app()
    from src.ui.virtualconsole.vc_canvas import WIDGET_REGISTRY, VCCanvas
    from src.ui.virtualconsole.vc_effect_display import VCEffectDisplay
    assert WIDGET_REGISTRY.get("VCEffectDisplay") is VCEffectDisplay
    assert VCEffectDisplay in VCCanvas._droppable_types()


def test_unbound_shows_placeholder_no_pixels():
    _app()
    from src.ui.virtualconsole.vc_effect_display import VCEffectDisplay
    w = VCEffectDisplay()
    assert w.is_effect_bound() is False
    w._refresh_state()
    assert w._pixels == []                       # ohne Bindung kein Render


def test_bound_matrix_renders_pixels():
    _app()
    fm, m = _matrix()
    from src.ui.virtualconsole.vc_effect_display import VCEffectDisplay
    w = VCEffectDisplay()
    w.function_id = m.id
    assert w.is_effect_bound() is True
    w._refresh_state()
    assert w._cols == 4 and w._rows == 1
    assert len(w._pixels) == 4                   # 4×1 Matrix -> 4 Pixel
    assert all(len(px) == 3 for px in w._pixels)  # (r,g,b)


def test_serialization_roundtrip():
    _app()
    from src.ui.virtualconsole.vc_effect_display import VCEffectDisplay
    w = VCEffectDisplay()
    w.function_id = 42
    d = w.to_dict()
    assert d["type"] == "VCEffectDisplay" and d["function_id"] == 42
    w2 = VCEffectDisplay()
    w2.apply_dict(d)
    assert w2.function_id == 42
