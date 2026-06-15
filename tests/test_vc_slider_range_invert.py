"""VC-Audit 2026-06-13 (A1): Fader-Leitplanken — Invert + Min/Max-Range.

Der Fader bildet seinen Hub 0..255 auf [range_min, range_max] ab; invert dreht
die Richtung. min==max darf keinen Division-by-zero auslösen, und der Effektivwert
muss serialisiert round-trippen.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.ui.virtualconsole.vc_slider import VCSlider, SliderMode

_app = QApplication.instance() or QApplication([])


class EffectiveValueTest(unittest.TestCase):
    def _slider(self, **kw):
        s = VCSlider("T")
        s.mode = SliderMode.SPEED   # harmloser Modus ohne Pflicht-Bindung
        for k, v in kw.items():
            setattr(s, k, v)
        return s

    def test_full_range_is_identity(self):
        s = self._slider()
        s._value = 0
        self.assertEqual(s._effective_value(), 0)
        s._value = 255
        self.assertEqual(s._effective_value(), 255)
        s._value = 128
        self.assertEqual(s._effective_value(), 128)

    def test_partial_range_maps(self):
        s = self._slider(range_min=100, range_max=200)
        s._value = 0
        self.assertEqual(s._effective_value(), 100)
        s._value = 255
        self.assertEqual(s._effective_value(), 200)
        s._value = 128                       # Mitte ~150
        self.assertAlmostEqual(s._effective_value(), 150, delta=1)

    def test_invert_flips(self):
        s = self._slider(invert=True)
        s._value = 0
        self.assertEqual(s._effective_value(), 255)
        s._value = 255
        self.assertEqual(s._effective_value(), 0)

    def test_invert_with_range(self):
        s = self._slider(invert=True, range_min=50, range_max=150)
        s._value = 0                         # invert -> oberer Wert
        self.assertEqual(s._effective_value(), 150)
        s._value = 255
        self.assertEqual(s._effective_value(), 50)

    def test_min_equals_max_no_div_zero(self):
        s = self._slider(range_min=77, range_max=77)
        for raw in (0, 50, 128, 255):
            s._value = raw
            self.assertEqual(s._effective_value(), 77)

    def test_swapped_bounds_tolerated(self):
        s = self._slider(range_min=200, range_max=50)
        s._value = 0
        self.assertEqual(s._effective_value(), 50)
        s._value = 255
        self.assertEqual(s._effective_value(), 200)

    def test_result_always_clamped(self):
        s = self._slider(range_min=0, range_max=255)
        s._value = 999                       # value-Setter würde clampen; hier direkt
        self.assertLessEqual(s._effective_value(), 255)
        self.assertGreaterEqual(s._effective_value(), 0)


class SerializationTest(unittest.TestCase):
    def test_roundtrip(self):
        s = VCSlider("X")
        s.invert = True
        s.range_min = 30
        s.range_max = 210
        s2 = VCSlider("Y")
        s2.apply_dict(s.to_dict())
        self.assertTrue(s2.invert)
        self.assertEqual(s2.range_min, 30)
        self.assertEqual(s2.range_max, 210)

    def test_defaults_when_absent(self):
        s = VCSlider("Z")
        s.apply_dict({"type": "VCSlider", "mode": SliderMode.LEVEL})
        self.assertFalse(s.invert)
        self.assertEqual(s.range_min, 0)
        self.assertEqual(s.range_max, 255)


if __name__ == "__main__":
    unittest.main()
