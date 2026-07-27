"""LayeredEffect: Layer-Kette bis ins DMX + Listenoperationen des Editors.

Geborgen 2026-07-26 aus dem nie gemergten Branch `qa/effect-layer-editor`.

Warum eine eigene Datei: `tests/test_effect_layer_editor.py` liegt bereits auf main
und deckt Clamp-Reihenfolge + Popout/Redock sogar strenger ab als der Branch. Was
dort FEHLT, sind genau diese zwei Aussagen:

1. **Der Ausgabepfad ist ungetestet.** `EffectLayer.process()` wurde auf main von
   KEINEM Test aufgerufen; `LayeredEffect.write()` (eigene Implementierung, keine
   geerbte Basisroutine — Patch-Lookup, Layer-Kette, `max(0, min(255, int(val*255)))`,
   `addr = fixture.address + ch.channel_number - 1`) lief nirgends gegen ein echtes
   Universe. Die einzige LayeredEffect-Abdeckung war
   `test_core_engine.py::test_layered_effect_speed_scales_time` mit `fixture_ids=[]`,
   die nur `_elapsed` prueft — es wurde also nie ein Wert geschrieben.
2. **Die Listenoperationen des Editors** (`_add_layer`/`_move_up`/`_delete`) waren
   ungetestet.
"""
from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.core.dmx.universe import Universe
from src.core.engine.effect_func import LayeredEffect
from src.core.engine.effect_layers import EffectLayer, LayerType
from src.ui.views.effect_layer_editor import EffectLayerEditor


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


class EffectLayerChainTest(unittest.TestCase):
    def test_layer_chain_writes_the_clamped_dmx_value(self):
        """Constant/Multiply/Clamp-Pfad: die Kette muss echtes DMX erzeugen.

        0.5 (Constant) × 0.5 (Multiply) = 0.25, dann Clamp auf [0.3, 0.4] → 0.3
        → DMX int(0.3*255) = 76 auf Adresse 10.
        """
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


class EffectLayerEditorListOpsTest(unittest.TestCase):
    def setUp(self):
        _app()
        self.effect = LayeredEffect("Editor")
        self.effect.layers = [EffectLayer(type=LayerType.SIN)]
        self.editor = EffectLayerEditor(self.effect)

    def tearDown(self):
        self.editor.close()
        self.editor.deleteLater()
        _app().processEvents()

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


if __name__ == "__main__":
    unittest.main()
