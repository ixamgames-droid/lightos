"""QA-10: EffectLayerEditor erhält geordnete Clamp-Grenzen."""
from PySide6.QtWidgets import QApplication

from src.core.engine.effect_func import LayeredEffect
from src.core.engine.effect_layers import EffectLayer, LayerType
from src.ui.views.effect_layer_editor import EffectLayerEditor


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_effect_layer_editor_keeps_clamp_bounds_ordered_and_redocks():
    """Min/Max-Editorwerte dürfen keinen widersprüchlichen Clamp erzeugen."""
    _app()
    effect = LayeredEffect("Clamp")
    effect.layers = [EffectLayer(type=LayerType.CLAMP, min_val=0.0, max_val=1.0)]
    view = EffectLayerEditor(effect)
    view.show()

    try:
        view._list.setCurrentRow(0)
        view._spin_min.setValue(3.0)
        layer = effect.layers[0]
        assert (layer.min_val, layer.max_val) == (3.0, 3.0)
        assert view._spin_max.value() == 3.0

        view._spin_max.setValue(-2.0)
        assert (layer.min_val, layer.max_val) == (-2.0, -2.0)
        assert view._spin_min.value() == -2.0

        for _ in range(3):
            view._toggle_editor_popout()
            assert view._editor_window is not None
            view._toggle_editor_popout()
            assert view._editor_window is None
            assert view._editor_scroll.widget() is view._editor_body
    finally:
        view.close()
