"""Tests fuer das generische Parameter-Modell + ColorSequence (Phase 2).

Prueft:
  A) ColorSequence: add/remove/toggle/next/prev/enabled_colors/selected/move.
  B) color1/2/3-Kompatibilitaet (Properties auf die Sequence, Fallback).
  C) Persistenz: color_sequence round-trip + Alt-Show-Seed aus color1/2/3.
  D) list_params: nur sinnvolle Keys je Algorithmus.
  E) get_param/set_param live (clamp) + do_action (Farb-/Richtungs-Aktionen).
"""
import unittest

from src.core.engine.rgb_matrix import (
    RgbMatrixInstance, RgbAlgorithm, ColorSequence,
)


class ColorSequenceTest(unittest.TestCase):

    def test_add_remove_toggle(self):
        seq = ColorSequence([(255, 0, 0), (0, 255, 0)])
        self.assertEqual(len(seq), 2)
        seq.add((0, 0, 255))
        self.assertEqual(seq.all_colors(), [(255, 0, 0), (0, 255, 0), (0, 0, 255)])
        seq.toggle(1)  # gruen deaktivieren
        self.assertEqual(seq.enabled_colors(), [(255, 0, 0), (0, 0, 255)])
        seq.remove(0)
        self.assertEqual(seq.all_colors(), [(0, 255, 0), (0, 0, 255)])

    def test_enabled_colors_never_empty(self):
        """Auch wenn alle Farben aus sind, liefert enabled_colors() >=1 (Fallback)."""
        seq = ColorSequence([(10, 20, 30)])
        seq.set_enabled(0, False)
        self.assertEqual(seq.enabled_colors(), [(10, 20, 30)])

    def test_next_prev_selected(self):
        seq = ColorSequence([(1, 1, 1), (2, 2, 2), (3, 3, 3)])
        self.assertEqual(seq.selected(), (1, 1, 1))
        seq.next()
        self.assertEqual(seq.selected(), (2, 2, 2))
        seq.prev(); seq.prev()
        self.assertEqual(seq.selected(), (3, 3, 3))  # wrap-around

    def test_move(self):
        seq = ColorSequence([(1, 1, 1), (2, 2, 2), (3, 3, 3)])
        seq.move(0, 2)
        self.assertEqual(seq.all_colors(), [(2, 2, 2), (3, 3, 3), (1, 1, 1)])

    def test_clamp_on_add(self):
        seq = ColorSequence([(999, -5, 12.7)])
        self.assertEqual(seq.color_at(0), (255, 0, 13))


class ColorCompatTest(unittest.TestCase):

    def test_color123_properties(self):
        m = RgbMatrixInstance(color1=(255, 0, 0), color2=(0, 255, 0), color3=(0, 0, 255))
        self.assertEqual(m.color1, (255, 0, 0))
        self.assertEqual(m.color2, (0, 255, 0))
        self.assertEqual(m.color3, (0, 0, 255))
        m.color2 = (10, 20, 30)
        self.assertEqual(m.colors.color_at(1), (10, 20, 30))

    def test_color_fallback_when_fewer(self):
        """Sequence auf 1 Farbe reduziert → color2/color3 crashen nicht (Fallback)."""
        m = RgbMatrixInstance()
        m.colors = ColorSequence([(7, 7, 7)])
        self.assertEqual(m.color1, (7, 7, 7))
        self.assertEqual(m.color3, (7, 7, 7))  # graceful, kein IndexError


class PersistenceTest(unittest.TestCase):

    def test_roundtrip_sequence(self):
        m = RgbMatrixInstance()
        m.colors = ColorSequence([(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)])
        m.colors.set_enabled(1, False)
        m.colors.active_index = 2
        restored = RgbMatrixInstance.from_dict(m.to_dict())
        self.assertEqual(restored.colors.all_colors(),
                         [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)])
        self.assertEqual(restored.colors.enabled_colors(),
                         [(255, 0, 0), (0, 0, 255), (255, 255, 0)])
        self.assertEqual(restored.colors.active_index, 2)

    def test_legacy_seed_from_color123(self):
        """Alt-Show ohne color_sequence → Sequence wird aus color1/2/3 geseedet."""
        d = {
            "name": "alt", "cols": 3, "rows": 1, "fixture_grid": [1, 2, 3],
            "algorithm": "Plain",
            "color1": [255, 0, 0], "color2": [0, 255, 0], "color3": [0, 0, 255],
        }
        m = RgbMatrixInstance.from_dict(d)
        self.assertEqual(m.colors.all_colors(), [(255, 0, 0), (0, 255, 0), (0, 0, 255)])


class ParamModelTest(unittest.TestCase):

    def test_list_params_rainbow_has_no_colors(self):
        m = RgbMatrixInstance(algorithm=RgbAlgorithm.RAINBOW)
        keys = [s.key for s in m.list_params()]
        self.assertIn("speed", keys)
        self.assertIn("intensity", keys)
        self.assertNotIn("colors", keys)  # Rainbow erzeugt eigene HSV-Farben (colors=0)

    def test_list_params_chase_has_colors_and_runners(self):
        m = RgbMatrixInstance(algorithm=RgbAlgorithm.CHASE)
        keys = [s.key for s in m.list_params()]
        for k in ("speed", "intensity", "direction", "colors", "runner_count",
                  "runner_width", "invert"):
            self.assertIn(k, keys, f"{k} fehlt in CHASE-Params")

    def test_set_param_speed_intensity(self):
        m = RgbMatrixInstance()
        self.assertTrue(m.set_param("speed", 3.5))
        self.assertEqual(m.matrix_speed, 3.5)
        m.set_param("intensity", 2.0)            # clamp 0..1
        self.assertEqual(m.intensity, 1.0)

    def test_set_param_algo_key_clamped(self):
        m = RgbMatrixInstance(algorithm=RgbAlgorithm.CHASE)
        m.set_param("runner_count", 999)         # spec max = 16
        self.assertEqual(m.params["runner_count"], 16)
        m.set_param("invert", True)
        self.assertEqual(m.params["invert"], True)

    def test_set_param_direction(self):
        m = RgbMatrixInstance()
        m.set_param("direction", "reverse")
        self.assertEqual(m.direction, "reverse")
        m.set_param("direction", False)
        self.assertEqual(m.direction, "forward")

    def test_set_param_colors_from_list(self):
        m = RgbMatrixInstance()
        m.set_param("colors", [(1, 2, 3), (4, 5, 6)])
        self.assertEqual(m.colors.all_colors(), [(1, 2, 3), (4, 5, 6)])

    def test_set_param_affects_render(self):
        """Live-Param-Aenderung wirkt sofort im _render (kein Snapshot beim Start)."""
        m = RgbMatrixInstance(algorithm=RgbAlgorithm.PLAIN, cols=2, rows=1,
                              fixture_grid=[1, 2])
        m.start()
        m.set_param("color1", (12, 34, 56))
        self.assertEqual(m._render(0.0)[0], (12, 34, 56))

    def test_do_action_colors(self):
        m = RgbMatrixInstance()
        m.colors = ColorSequence([(255, 0, 0)])
        m.do_action("add_color", rgb=(0, 255, 0))
        self.assertEqual(m.colors.all_colors(), [(255, 0, 0), (0, 255, 0)])
        m.do_action("next_color")
        self.assertEqual(m.colors.selected(), (0, 255, 0))
        m.do_action("toggle_color")              # aktive (gruen) deaktivieren
        self.assertEqual(m.colors.enabled_colors(), [(255, 0, 0)])
        m.do_action("remove_color", index=1)
        self.assertEqual(m.colors.all_colors(), [(255, 0, 0)])

    def test_do_action_reverse_direction(self):
        m = RgbMatrixInstance()
        self.assertEqual(m.direction, "forward")
        self.assertTrue(m.do_action("reverse_direction"))
        self.assertEqual(m.direction, "reverse")

    def test_do_action_unknown(self):
        self.assertFalse(RgbMatrixInstance().do_action("flux_capacitor"))


if __name__ == "__main__":
    unittest.main()
