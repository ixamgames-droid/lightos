"""APC-Probier To-Do #9: Farb-Kacheln sperren, wenn ein Effekt die Farbe besitzt.

effect_live.color_is_effect_driven() erkennt eine laufende RGB-/RGBW-Matrix;
VCColor._color_overridden() greift das für Programmer/Alle-Kacheln auf (die
dann ausgegraut werden). Effekt-Ziele sind ausgenommen.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.core.engine.function_manager import get_function_manager
from src.core.engine.rgb_matrix import RgbMatrixInstance, RgbAlgorithm, MatrixStyle
from src.core.engine import effect_live
from src.ui.virtualconsole.vc_color import VCColor, ColorTarget

_app = QApplication.instance() or QApplication([])


class ColorContextLockTest(unittest.TestCase):
    def setUp(self):
        self.fm = get_function_manager()
        self.fm.stop_all()
        self._pre = {f.id for f in self.fm.all()}
        self.m = RgbMatrixInstance(name="ctx", cols=4, rows=1,
                                   algorithm=RgbAlgorithm.RAINBOW, fixture_grid=[1, 2, 3, 4])
        self.fm.add(self.m)

    def tearDown(self):
        self.fm.stop_all()
        for f in list(self.fm.all()):
            if f.id not in self._pre:
                self.fm.remove(f.id)

    def test_not_driven_when_stopped(self):
        self.assertFalse(effect_live.color_is_effect_driven())

    def test_driven_when_rgb_matrix_running(self):
        self.fm.start(self.m.id)
        self.assertTrue(effect_live.color_is_effect_driven())

    def test_dimmer_style_does_not_drive_color(self):
        self.m.style = MatrixStyle.DIMMER
        self.fm.start(self.m.id)
        self.assertFalse(effect_live.color_is_effect_driven())

    def test_tile_overridden_only_for_programmer_targets(self):
        self.fm.start(self.m.id)
        prog = VCColor("p"); prog.target = ColorTarget.PROGRAMMER
        all_ = VCColor("a"); all_.target = ColorTarget.ALL
        eff = VCColor("e"); eff.target = ColorTarget.EFFECT
        self.assertTrue(prog._color_overridden())
        self.assertTrue(all_._color_overridden())
        self.assertFalse(eff._color_overridden())   # Effekt-Ziel füttert den Effekt

    def test_tile_not_overridden_when_idle(self):
        prog = VCColor("p"); prog.target = ColorTarget.PROGRAMMER
        self.assertFalse(prog._color_overridden())


if __name__ == "__main__":
    unittest.main()
