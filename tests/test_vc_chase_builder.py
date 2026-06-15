"""APC-Probier To-Do #1: dediziertes Chase-Builder-Widget.

EIN Widget bündelt Farb-Palette (anhängen), gebaute Liste (Feedback), Aktions-
Buttons (Start/Clear/C−/C+/Richtung/Freeze/Commit) und Speed/Hold-Slider — alles
über den effect_live-Dispatcher auf einen Ziel-Effekt.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.core.engine.function_manager import get_function_manager
from src.core.engine.rgb_matrix import RgbMatrixInstance, RgbAlgorithm, ColorSequence
from src.ui.virtualconsole.vc_chase_builder import VCChaseBuilder, PALETTE
from src.ui.virtualconsole.vc_canvas import WIDGET_REGISTRY

_app = QApplication.instance() or QApplication([])


class VCChaseBuilderTest(unittest.TestCase):
    def setUp(self):
        self.fm = get_function_manager()
        self.fm.stop_all()
        self._pre = {f.id for f in self.fm.all()}
        self.m = RgbMatrixInstance(name="builder", cols=4, rows=1,
                                   algorithm=RgbAlgorithm.COLORFADE, fixture_grid=[1, 2, 3, 4])
        self.m.colors = ColorSequence([])
        self.fm.add(self.m)
        self.b = VCChaseBuilder()
        self.b.function_id = self.m.id

    def tearDown(self):
        self.fm.stop_all()
        for f in list(self.fm.all()):
            if f.id not in self._pre:
                self.fm.remove(f.id)

    def test_registered(self):
        self.assertIn("VCChaseBuilder", WIDGET_REGISTRY)
        self.assertIs(WIDGET_REGISTRY["VCChaseBuilder"], VCChaseBuilder)

    def test_effect_bound(self):
        self.assertTrue(self.b.is_effect_bound())
        self.assertEqual(self.b.live_effect_function_id(), self.m.id)
        self.assertIs(self.b._target(), self.m)

    def test_palette_appends_colors_in_order(self):
        self.b._add_palette_color(0)        # Rot
        self.b._add_palette_color(7)        # Blau
        self.assertEqual(self.m.colors.all_colors(), [PALETTE[0], PALETTE[7]])

    def test_clear_action(self):
        self.b._add_palette_color(0)
        self.b._add_palette_color(1)
        self.b._do("clear_colors")
        self.assertEqual(len(self.m.colors), 0)

    def test_next_prev_color(self):
        for i in (0, 1, 2):
            self.b._add_palette_color(i)
        self.m.colors.active_index = 0
        self.b._do("next_color")
        self.assertEqual(self.m.colors.active_index, 1)
        self.b._do("prev_color")
        self.assertEqual(self.m.colors.active_index, 0)

    def test_toggle_start_stops_and_starts(self):
        self.assertFalse(self.fm.is_running(self.m.id))
        self.b._toggle_start()
        self.assertTrue(self.fm.is_running(self.m.id))
        self.b._toggle_start()
        self.assertFalse(self.fm.is_running(self.m.id))

    def test_speed_slider_sets_param_and_norm(self):
        self.b._set_slider("speed", 1.0)
        self.assertEqual(self.b._speed_norm, 1.0)
        self.assertGreater(self.m.matrix_speed, 15)     # ~max der speed-Spec

    def test_hold_slider_sets_param(self):
        self.b._set_slider("hold", 1.0)
        self.assertEqual(self.b._hold_norm, 1.0)
        self.assertIn("hold", self.m.params)            # Hold-Param gesetzt

    def test_renders_without_crash(self):
        self.b.grab()                       # leere Liste
        self.b._add_palette_color(3)
        self.b._add_palette_color(8)
        self.fm.start(self.m.id)
        self.b.grab()                       # mit Liste + laufend
        self.m.do_action("toggle_freeze")
        self.b.grab()                       # eingefroren

    def test_serialization_roundtrip(self):
        self.b.function_id = 9
        self.b._speed_norm = 0.7
        self.b._hold_norm = 0.3
        b2 = VCChaseBuilder()
        b2.apply_dict(self.b.to_dict())
        self.assertEqual(b2.function_id, 9)
        self.assertAlmostEqual(b2._speed_norm, 0.7)
        self.assertAlmostEqual(b2._hold_norm, 0.3)
        self.assertEqual(self.b.to_dict()["type"], "VCChaseBuilder")


if __name__ == "__main__":
    unittest.main()
