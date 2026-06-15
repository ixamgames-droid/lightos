"""APC-Probier To-Do #8: XY-Pad „Feld"-Modus.

Im Feld-Modus zieht man ein Rechteck auf → setzt Zentrum (x_offset/y_offset) und
Größe (width/height) eines Ziel-EFX: „mach hier deine Acht". Der Pad-Bereich
entspricht dem Pan/Tilt-Raum 0..255.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.core.engine.function_manager import get_function_manager
from src.core.engine.efx import EfxInstance, EfxFixture, EfxAlgorithm
from src.ui.virtualconsole.vc_xypad import VCXYPad

_app = QApplication.instance() or QApplication([])


class XYPadAreaTest(unittest.TestCase):
    def setUp(self):
        self.fm = get_function_manager()
        self.fm.stop_all()
        self._pre = {f.id for f in self.fm.all()}
        self.efx = EfxInstance("mh")
        self.efx.algorithm = EfxAlgorithm.EIGHT
        self.efx.fixtures = [EfxFixture(fid=5), EfxFixture(fid=6)]
        self.fm.add(self.efx)

    def tearDown(self):
        self.fm.stop_all()
        for f in list(self.fm.all()):
            if f.id not in self._pre:
                self.fm.remove(f.id)

    def test_is_effect_bound_only_in_area_mode(self):
        pad = VCXYPad()
        self.assertFalse(pad.is_effect_bound())
        pad.mode = "area"
        pad.efx_function_id = self.efx.id
        self.assertTrue(pad.is_effect_bound())
        self.assertEqual(pad.live_effect_function_id(), self.efx.id)

    def test_apply_area_sets_efx_center_and_size(self):
        pad = VCXYPad()
        pad.mode = "area"
        pad.efx_function_id = self.efx.id
        pad._area = (0.25, 0.25, 0.75, 0.75)   # Mitte 0.5/0.5, Größe 0.5/0.5
        pad._apply_area()
        self.assertAlmostEqual(self.efx.x_offset, 127.5, places=1)
        self.assertAlmostEqual(self.efx.y_offset, 127.5, places=1)
        self.assertAlmostEqual(self.efx.width, 127.5, places=1)
        self.assertAlmostEqual(self.efx.height, 127.5, places=1)

    def test_apply_area_corner_box(self):
        pad = VCXYPad()
        pad.mode = "area"
        pad.efx_function_id = self.efx.id
        pad._area = (0.0, 0.0, 0.5, 0.25)      # oben links, Mitte 0.25/0.125
        pad._apply_area()
        self.assertAlmostEqual(self.efx.x_offset, 0.25 * 255, places=1)
        self.assertAlmostEqual(self.efx.y_offset, 0.125 * 255, places=1)
        self.assertAlmostEqual(self.efx.width, 0.5 * 255, places=1)
        self.assertAlmostEqual(self.efx.height, 0.25 * 255, places=1)

    def test_apply_area_noop_without_area(self):
        pad = VCXYPad()
        pad.mode = "area"
        pad.efx_function_id = self.efx.id
        before = (self.efx.x_offset, self.efx.width)
        pad._apply_area()                       # kein _area -> nichts ändern
        self.assertEqual((self.efx.x_offset, self.efx.width), before)

    def test_serialization_roundtrip(self):
        pad = VCXYPad("Feld")
        pad.mode = "area"
        pad.efx_function_id = 7
        pad._area = (0.1, 0.2, 0.3, 0.4)
        pad2 = VCXYPad()
        pad2.apply_dict(pad.to_dict())
        self.assertEqual(pad2.mode, "area")
        self.assertEqual(pad2.efx_function_id, 7)
        self.assertEqual(pad2._area, (0.1, 0.2, 0.3, 0.4))

    def test_renders_both_modes(self):
        pad = VCXYPad()
        pad.grab()                  # position
        pad.mode = "area"
        pad.grab()                  # area, kein Feld
        pad._area = (0.2, 0.2, 0.6, 0.7)
        pad.grab()                  # area mit Feld


if __name__ == "__main__":
    unittest.main()
