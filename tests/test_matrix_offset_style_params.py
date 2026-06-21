"""MXP-02 (Phasen-Versatz) + MXP-03 (Dimmer/Shutter min/max + Weissanteil live).

Diese Parameter sind jetzt über list_params/get_param/set_param live steuerbar
(VC/MIDI), geklemmt und werden persistiert.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.engine.rgb_matrix import RgbMatrixInstance, RgbAlgorithm


def _m():
    return RgbMatrixInstance(name="t", cols=4, rows=1,
                             algorithm=RgbAlgorithm.CHASE, fixture_grid=[1, 2, 3, 4])


class ListedTest(unittest.TestCase):
    def test_keys_listed(self):
        keys = [s.key for s in _m().list_params()]
        for k in ("offset", "intensity_min", "intensity_max",
                  "shutter_min", "shutter_max"):
            self.assertIn(k, keys)
        # white_amount entfaellt aus list_params: RGBW erzeugt echtes Weiss
        # automatisch ueber den W-Kanal (kein "Weissanteil"-Regler mehr).
        self.assertNotIn("white_amount", keys)


class SetGetClampTest(unittest.TestCase):
    def test_style_params_clamped(self):
        m = _m()
        self.assertTrue(m.set_param("intensity_max", 300))
        self.assertEqual(m.get_param("intensity_max"), 255)
        self.assertEqual(m.intensity_max, 255)
        m.set_param("white_amount", 50)
        self.assertEqual(m.white_amount, 50)
        m.set_param("white_amount", 999)
        self.assertEqual(m.white_amount, 100)
        m.set_param("shutter_min", -5)
        self.assertEqual(m.shutter_min, 0)

    def test_offset_set_get_clamped(self):
        m = _m()
        m.set_param("offset", 3.0)
        self.assertEqual(m.get_param("offset"), 3.0)
        m.set_param("offset", 99)
        self.assertEqual(m.get_param("offset"), 16.0)


class OffsetRenderTest(unittest.TestCase):
    def test_offset_shifts_phase(self):
        # CHASE: render(phase=0, offset=2) == render(phase=2, offset=0)
        m1 = _m(); m1.params["offset"] = 2.0
        m2 = _m(); m2.params["offset"] = 0.0
        self.assertEqual(m1._render(0.0), m2._render(2.0))


class PersistenceTest(unittest.TestCase):
    def test_offset_persisted(self):
        m = _m(); m.set_param("offset", 4.0)
        m2 = _m(); m2.apply_dict(m.to_dict())
        self.assertEqual(m2.get_param("offset"), 4.0)

    def test_style_params_persisted(self):
        m = _m()
        m.set_param("intensity_min", 33)
        m.set_param("shutter_max", 200)
        m2 = _m(); m2.apply_dict(m.to_dict())
        self.assertEqual(m2.intensity_min, 33)
        self.assertEqual(m2.shutter_max, 200)


if __name__ == "__main__":
    unittest.main()
