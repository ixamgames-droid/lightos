"""QA-LIVE-Regression fuer den Effect-Layer-Editor."""
from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.core.engine.effect_func import LayeredEffect
from src.core.engine.effect_layers import EffectLayer, LayerType
from src.core.dmx.universe import Universe
from src.ui.views.effect_layer_editor import EffectLayerEditor


_app = QApplication.instance() or QApplication([])


class EffectLayerEditorTest(unittest.TestCase):
    def setUp(self):
        self.effect = LayeredEffect("Layer QA")
        self.effect.layers = [EffectLayer(type=LayerType.SIN)]
        self.editor = EffectLayerEditor(self.effect)
        self.editor.show()
        _app.processEvents()
        self.editor._list.setCurrentRow(0)

    def tearDown(self):
        self.editor.close()
        self.editor.deleteLater()
        _app.processEvents()

    def test_editor_keeps_clamp_bounds_ordered(self):
        """Min > Max darf nicht als stiller, invertierter Clamp gespeichert werden."""
        self.editor._spin_min.setValue(2.0)
        self.assertEqual(self.effect.layers[0].min_val, 2.0)
        self.assertEqual(self.effect.layers[0].max_val, 2.0)

        self.editor._spin_max.setValue(-1.0)
        self.assertEqual(self.effect.layers[0].min_val, -1.0)
        self.assertEqual(self.effect.layers[0].max_val, -1.0)

    def test_layer_add_reorder_and_delete_updates_model(self):
        self.editor._add_combo.setCurrentText(LayerType.MULTIPLY.value)
        self.editor._add_layer()
        self.assertEqual([l.type for l in self.effect.layers],
                         [LayerType.SIN, LayerType.MULTIPLY])

        self.editor._move_up()
        self.assertEqual([l.type for l in self.effect.layers],
                         [LayerType.MULTIPLY, LayerType.SIN])

        self.editor._delete()
        self.assertEqual([l.type for l in self.effect.layers], [LayerType.SIN])

    def test_popout_and_redock_keep_the_same_editor_body(self):
        body = self.editor._editor_body
        self.editor._toggle_editor_popout()
        self.assertIsNotNone(self.editor._editor_window)
        self.assertIs(self.editor._editor_window_scroll.widget(), body)

        self.editor._toggle_editor_popout()
        _app.processEvents()
        self.assertIsNone(self.editor._editor_window)
        self.assertIs(self.editor._editor_scroll.widget(), body)

    def test_layer_chain_writes_the_clamped_dmx_value(self):
        """Constant/Multiply/Clamp-Pfad: der Editor modelliert eine echte Ausgabe-Kette."""
        effect = LayeredEffect("DMX chain")
        effect.fixture_ids = [7]
        effect.layers = [
            EffectLayer(type=LayerType.CONSTANT, value=0.5),
            EffectLayer(type=LayerType.MULTIPLY, amplitude=0.5),
            EffectLayer(type=LayerType.CLAMP, min_val=0.3, max_val=0.4),
        ]
        effect._running = True
        fixture = SimpleNamespace(fid=7, universe=1, address=10)
        channel = SimpleNamespace(attribute="intensity", channel_number=1)
        universe = Universe(1)

        with mock.patch("src.core.app_state.get_channels_for_patched",
                        return_value=[channel]):
            effect.write({1: universe}, [fixture], 0.0)

        self.assertEqual(universe.get_channel(10), int(0.3 * 255))


if __name__ == "__main__":
    unittest.main()
