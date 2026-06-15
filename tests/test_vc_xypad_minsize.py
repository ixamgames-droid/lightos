"""VC-Audit 2026-06-13 (A4): XY-Pad Feld-Modus Mindestgröße.

Ein reiner Klick (ohne Ziehen) erzeugte ein 0×0-Feld → EFX-Figur kollabierte auf
einen Punkt. _normalized_area erzwingt jetzt eine Mindestkantenlänge und hält das
Zentrum so, dass das Feld komplett im Pad (0..1) bleibt.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.core.engine.function_manager import get_function_manager
from src.core.engine.efx import EfxInstance, EfxFixture, EfxAlgorithm
from src.ui.virtualconsole.vc_xypad import VCXYPad

_app = QApplication.instance() or QApplication([])


class NormalizedAreaTest(unittest.TestCase):
    def test_pure_click_gets_min_size(self):
        pad = VCXYPad()
        pad._area = (0.5, 0.5, 0.5, 0.5)        # reiner Klick — 0×0
        cx, cy, w, h = pad._normalized_area()
        self.assertGreaterEqual(w, pad._MIN_AREA)
        self.assertGreaterEqual(h, pad._MIN_AREA)
        self.assertAlmostEqual(cx, 0.5)
        self.assertAlmostEqual(cy, 0.5)

    def test_corner_click_center_clamped_inside(self):
        pad = VCXYPad()
        pad._area = (1.0, 1.0, 1.0, 1.0)        # Klick in die Ecke
        cx, cy, w, h = pad._normalized_area()
        # Feld muss komplett im Pad bleiben: cx + w/2 <= 1, cx - w/2 >= 0
        self.assertLessEqual(cx + w / 2.0, 1.0 + 1e-9)
        self.assertGreaterEqual(cx - w / 2.0, -1e-9)
        self.assertLessEqual(cy + h / 2.0, 1.0 + 1e-9)
        self.assertGreaterEqual(cy - h / 2.0, -1e-9)

    def test_large_area_unchanged(self):
        pad = VCXYPad()
        pad._area = (0.2, 0.2, 0.8, 0.8)
        cx, cy, w, h = pad._normalized_area()
        self.assertAlmostEqual(w, 0.6)
        self.assertAlmostEqual(h, 0.6)
        self.assertAlmostEqual(cx, 0.5)
        self.assertAlmostEqual(cy, 0.5)

    def test_none_without_area(self):
        pad = VCXYPad()
        self.assertIsNone(pad._normalized_area())


class ApplyAreaMinSizeTest(unittest.TestCase):
    def setUp(self):
        self.fm = get_function_manager()
        self.fm.stop_all()
        self._pre = {f.id for f in self.fm.all()}
        self.efx = EfxInstance("mh")
        self.efx.algorithm = EfxAlgorithm.EIGHT
        self.efx.fixtures = [EfxFixture(fid=5)]
        self.fm.add(self.efx)

    def tearDown(self):
        self.fm.stop_all()
        for f in list(self.fm.all()):
            if f.id not in self._pre:
                self.fm.remove(f.id)

    def test_click_does_not_collapse_efx(self):
        pad = VCXYPad()
        pad.mode = "area"
        pad.efx_function_id = self.efx.id
        pad._area = (0.5, 0.5, 0.5, 0.5)        # reiner Klick
        pad._apply_area()
        self.assertGreaterEqual(self.efx.width, pad._MIN_AREA * 255 - 0.5)
        self.assertGreaterEqual(self.efx.height, pad._MIN_AREA * 255 - 0.5)
        # _area wurde an die erzwungene Geometrie angeglichen (Paint = Wirkung)
        x0, y0, x1, y1 = pad._area
        self.assertGreater(x1 - x0, 0)
        self.assertGreater(y1 - y0, 0)


if __name__ == "__main__":
    unittest.main()
