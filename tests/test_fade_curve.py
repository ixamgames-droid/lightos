"""Unit-Tests fuer FadeCurve (reines Datenmodell, keine Qt-Abhaengigkeit)."""
from __future__ import annotations
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.engine import fade_curve as fc
from src.core.engine.fade_curve import FadeCurve


class TestFadeCurveBasics(unittest.TestCase):
    def test_endpoints(self):
        c = fc.linear()
        self.assertAlmostEqual(c.eval(0.0), 0.0)
        self.assertAlmostEqual(c.eval(1.0), 1.0)

    def test_linear_midpoint(self):
        c = fc.linear()
        self.assertAlmostEqual(c.eval(0.5), 0.5)
        self.assertAlmostEqual(c.eval(0.25), 0.25)

    def test_clamping_out_of_range(self):
        c = fc.linear()
        self.assertAlmostEqual(c.eval(-5.0), 0.0)
        self.assertAlmostEqual(c.eval(5.0), 1.0)

    def test_output_always_in_unit_range(self):
        for c in fc.presets():
            for i in range(101):
                t = i / 100.0
                y = c.eval(t)
                self.assertGreaterEqual(y, 0.0, f"{c.name} @ {t}")
                self.assertLessEqual(y, 1.0, f"{c.name} @ {t}")

    def test_monotonic_non_decreasing(self):
        # Alle Presets sind monoton steigend (kein Ueberschwingen)
        for c in fc.presets():
            prev = -1.0
            for i in range(101):
                y = c.eval(i / 100.0)
                self.assertGreaterEqual(
                    y + 1e-6, prev, f"{c.name} nicht monoton bei {i}")
                prev = y


class TestSnap(unittest.TestCase):
    def test_snap_holds_then_jumps(self):
        c = fc.snap()
        # bleibt bei 0 bis fast zum Ende
        self.assertAlmostEqual(c.eval(0.0), 0.0)
        self.assertAlmostEqual(c.eval(0.5), 0.0)
        self.assertAlmostEqual(c.eval(0.99), 0.0, places=2)
        # springt am Ende auf 1
        self.assertAlmostEqual(c.eval(1.0), 1.0)


class TestEasing(unittest.TestCase):
    def test_ease_in_slower_than_linear_early(self):
        c = fc.ease_in()
        # langsamer Start: bei t=0.3 unter der Geraden
        self.assertLess(c.eval(0.3), 0.3)

    def test_ease_out_faster_than_linear_early(self):
        c = fc.ease_out()
        # schneller Start: bei t=0.3 ueber der Geraden
        self.assertGreater(c.eval(0.3), 0.3)


class TestSerialisation(unittest.TestCase):
    def test_round_trip(self):
        for c in fc.presets():
            d = c.to_dict()
            c2 = FadeCurve.from_dict(d)
            self.assertEqual(c.name, c2.name)
            self.assertEqual(c.mode, c2.mode)
            for i in range(0, 101, 5):
                t = i / 100.0
                self.assertAlmostEqual(c.eval(t), c2.eval(t), places=4)

    def test_normalize_inserts_endpoints(self):
        c = FadeCurve(points=[(0.5, 0.5)])
        xs = [p[0] for p in c.points]
        self.assertEqual(xs[0], 0.0)
        self.assertEqual(xs[-1], 1.0)

    def test_normalize_sorts(self):
        c = FadeCurve(points=[(1.0, 1.0), (0.3, 0.2), (0.0, 0.0)])
        xs = [p[0] for p in c.points]
        self.assertEqual(xs, sorted(xs))

    def test_is_linear_default(self):
        self.assertTrue(fc.linear().is_linear_default())
        self.assertFalse(fc.snap().is_linear_default())
        self.assertFalse(fc.ease_in().is_linear_default())


if __name__ == "__main__":
    unittest.main()
