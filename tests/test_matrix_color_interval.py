"""MXP-01: Color Change Interval fuer den CHASE-Algorithmus.

Die Farbe der Color-Sequence wechselt erst alle N Durchlaeufe (color_interval).
- 1 = jeder Durchlauf (Default = bisheriges color_cycle-Verhalten, Alt-Shows).
- 2 = Farbe bleibt 2 Durchlaeufe gleich, usw.
Zusaetzlich: der Parameter ist live steuerbar (list_params) und wird geklemmt
(set_param), und er persistiert ueber das params-Dict (to_dict/apply_dict).
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.engine.rgb_matrix import RgbMatrixInstance, RgbAlgorithm, ColorSequence


def _render(p, interval=None):
    m = RgbMatrixInstance(name="t", cols=4, rows=1, algorithm=RgbAlgorithm.CHASE)
    m.colors = ColorSequence([(255, 0, 0), (0, 0, 255)])   # rot, blau (beide aktiv)
    m.params.update(color_cycle=True, color_order="normal", runner_width=1)
    if interval is not None:
        m.params["color_interval"] = interval
    return m._render(p)


def _dominant(pixels):
    r = max((px[0] for px in pixels), default=0)
    b = max((px[2] for px in pixels), default=0)
    if r > b:
        return "red"
    if b > r:
        return "blue"
    return "none"


class ColorIntervalTest(unittest.TestCase):
    def test_default_is_per_round(self):
        # Ohne color_interval = bisheriges Verhalten: Wechsel pro Durchlauf
        # (length_hint = 4 Spalten). p<4 -> Farbe 0 (rot), p>=4 -> Farbe 1 (blau).
        self.assertEqual(_dominant(_render(1.0)), "red")
        self.assertEqual(_dominant(_render(5.0)), "blue")

    def test_interval_1_equals_default(self):
        self.assertEqual(_dominant(_render(1.0, 1)), "red")
        self.assertEqual(_dominant(_render(5.0, 1)), "blue")

    def test_interval_2_holds_two_rounds(self):
        # length_hint*interval = 8. p in [0,8) -> rot, p in [8,16) -> blau.
        self.assertEqual(_dominant(_render(1.0, 2)), "red")
        self.assertEqual(_dominant(_render(5.0, 2)), "red")   # frueher haette hier blau gestanden
        self.assertEqual(_dominant(_render(9.0, 2)), "blue")

    def test_interval_4(self):
        # length_hint*interval = 16. p<16 -> rot, p in [16,32) -> blau.
        self.assertEqual(_dominant(_render(10.0, 4)), "red")
        self.assertEqual(_dominant(_render(20.0, 4)), "blue")

    def test_live_param_listed_and_clamped(self):
        m = RgbMatrixInstance(name="t", cols=4, rows=1, algorithm=RgbAlgorithm.CHASE)
        self.assertNotIn("color_interval", [s.key for s in m.list_params()])
        m.params["color_cycle"] = True
        keys = [s.key for s in m.list_params()]
        self.assertIn("color_interval", keys)        # live steuerbar
        self.assertTrue(m.set_param("color_interval", 4))
        self.assertEqual(m.params["color_interval"], 4)
        m.set_param("color_interval", 999)           # > max 16 -> geklemmt
        self.assertEqual(m.params["color_interval"], 16)
        m.set_param("color_interval", 0)             # < min 1 -> geklemmt
        self.assertEqual(m.params["color_interval"], 1)

    def test_persisted_round_trip(self):
        m = RgbMatrixInstance(name="t", cols=4, rows=1, algorithm=RgbAlgorithm.CHASE)
        m.params.update(color_cycle=True, color_interval=8)
        m2 = RgbMatrixInstance(name="x", cols=4, rows=1, algorithm=RgbAlgorithm.CHASE)
        m2.apply_dict(m.to_dict())
        self.assertEqual(m2.params.get("color_interval"), 8)


if __name__ == "__main__":
    unittest.main()
