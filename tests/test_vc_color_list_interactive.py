"""VC-Erweiterung 2026-06-13 (F3): VCColorList interaktiv.

Klick auf einen Swatch schaltet die Farbe an/aus, Rechtsklick entfernt sie —
über effect_live.do_action am Ziel-Effekt. Vorher war das Widget rein lesend.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication

from src.core.engine.function_manager import get_function_manager
from src.core.engine.rgb_matrix import RgbMatrixInstance, RgbAlgorithm
from src.ui.virtualconsole.vc_color_list import VCColorList

_app = QApplication.instance() or QApplication([])


class ColorListInteractiveTest(unittest.TestCase):
    def setUp(self):
        self.fm = get_function_manager()
        self.fm.stop_all()
        self.m = RgbMatrixInstance(name="cl", cols=2, rows=1,
                                   algorithm=RgbAlgorithm.COLORFADE, fixture_grid=[1, 2])
        self.m.colors.entries = [[(255, 0, 0), True], [(0, 255, 0), True],
                                 [(0, 0, 255), True]]
        self.fm.add(self.m)
        self.w = VCColorList()
        self.w.function_id = self.m.id
        self.w.resize(240, 72)

    def tearDown(self):
        self.fm.stop_all()
        self.fm.remove(self.m.id)

    def test_toggle_disables_color(self):
        self.assertTrue(self.m.colors.entries[1][1])
        self.w._do_color_action("toggle_color", 1)
        self.assertFalse(self.m.colors.entries[1][1])
        self.w._do_color_action("toggle_color", 1)
        self.assertTrue(self.m.colors.entries[1][1])

    def test_remove_color(self):
        self.w._do_color_action("remove_color", 0)
        self.assertEqual(len(self.m.colors.entries), 2)
        self.assertEqual(self.m.colors.entries[0][0], (0, 255, 0))

    def test_hit_swatch_maps_position(self):
        # Titelzeile (y < 18) trifft keinen Swatch
        self.assertIsNone(self.w._hit_swatch(QPoint(120, 8)))
        # erster Swatch links
        self.assertEqual(self.w._hit_swatch(QPoint(10, 45)), 0)
        # mittlerer Swatch
        self.assertEqual(self.w._hit_swatch(QPoint(120, 45)), 1)

    def test_hit_swatch_none_when_empty(self):
        self.m.colors.entries = []
        self.assertIsNone(self.w._hit_swatch(QPoint(120, 45)))


if __name__ == "__main__":
    unittest.main()
