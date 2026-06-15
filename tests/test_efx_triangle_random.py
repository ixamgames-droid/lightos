"""EFX-Formen-Fixes 2026-06-12:
- TRIANGLE fährt jetzt ein echtes Dreieck (3 Eckpunkte, 3 Kanten) statt nur
  zwei Halb-Achsen.
- RANDOM fährt echte zufällige Wegpunkte in einem definierbaren Feld
  (width × height) und läuft kontinuierlich/endlos (nie wiederholend).
"""
import math
import unittest

from src.core.engine.efx import EfxInstance, EfxFixture, EfxAlgorithm


class TriangleTest(unittest.TestCase):
    def _efx(self):
        e = EfxInstance("tri")
        e.algorithm = EfxAlgorithm.TRIANGLE
        e.width = e.height = 100.0      # hw = hh = 50
        e.x_offset = e.y_offset = 128.0
        return e

    def test_three_distinct_corners(self):
        e = self._efx()
        v0 = e._calc(0.0)
        v1 = e._calc(1.0 / 3.0)
        v2 = e._calc(2.0 / 3.0)
        # Erwartete Ecken: Spitze oben, unten rechts, unten links.
        self.assertEqual((round(v0[0]), round(v0[1])), (128, 78))
        self.assertEqual((round(v1[0]), round(v1[1])), (178, 178))
        self.assertEqual((round(v2[0]), round(v2[1])), (78, 178))
        # drei verschiedene Punkte (echtes Dreieck, nicht 2 Achsen)
        self.assertEqual(len({(round(v[0]), round(v[1])) for v in (v0, v1, v2)}), 3)

    def test_closes_back_to_start(self):
        e = self._efx()
        self.assertEqual(e._calc(0.0), e._calc(1.0))

    def test_edge_midpoint_between_corners(self):
        e = self._efx()
        # Mitte der ersten Kante (v0->v1) bei phase 1/6.
        mx, my = e._calc(1.0 / 6.0)
        self.assertAlmostEqual(mx, (128 + 178) / 2, delta=1)
        self.assertAlmostEqual(my, (78 + 178) / 2, delta=1)


class RandomTest(unittest.TestCase):
    def _efx(self, w=100.0, h=60.0, seed=12345):
        e = EfxInstance("rnd")
        e.algorithm = EfxAlgorithm.RANDOM
        e.width, e.height = w, h
        e.x_offset = e.y_offset = 128.0
        e.random_seed = seed
        e.fixtures = [EfxFixture(fid=1)]
        return e

    def test_waypoints_within_area(self):
        e = self._efx(w=100.0, h=60.0)
        for k in range(50):
            x, y = e._random_waypoint(k)
            self.assertTrue(-50.0 <= x <= 50.0, x)
            self.assertTrue(-30.0 <= y <= 30.0, y)

    def test_waypoints_deterministic_per_seed(self):
        a = self._efx(seed=777)
        b = self._efx(seed=777)
        self.assertEqual([a._random_waypoint(k) for k in range(10)],
                         [b._random_waypoint(k) for k in range(10)])

    def test_sequence_does_not_repeat(self):
        e = self._efx()
        pts = [tuple(round(c, 3) for c in e._random_waypoint(k)) for k in range(40)]
        # weit überwiegend verschiedene Punkte (kein Konstant-/Kurz-Zyklus)
        self.assertGreater(len(set(pts)), 35)

    def test_random_xy_hits_waypoint_at_integers(self):
        e = self._efx()
        self.assertEqual(e._random_xy(3.0), e._random_waypoint(3))

    def test_advance_progresses_and_values_move(self):
        e = self._efx()
        e.start()
        e._advance(1.0)                     # speed_hz=0.5 default -> +0.5
        v1 = e._values()[1]
        e._advance(2.0)                     # +1.0 -> anderer Wegpunkt-Bereich
        v2 = e._values()[1]
        self.assertNotEqual(v1, v2)
        e.stop()

    def test_output_confined_to_area(self):
        e = self._efx(w=100.0, h=60.0)      # pan in [78,178], tilt in [98,158]
        e.start()
        for _ in range(40):
            e._advance(0.3)
            v = e._values()[1]
            self.assertTrue(78 <= v["pan"] <= 178, v["pan"])
            self.assertTrue(98 <= v["tilt"] <= 158, v["tilt"])
        e.stop()

    def test_reseed_changes_path(self):
        e = self._efx(seed=1)
        before = e._random_waypoint(5)
        self.assertTrue(e.do_action("reseed"))
        self.assertEqual(e._rand_progress, 0.0)
        # neuer Seed -> (mit hoher Wahrscheinlichkeit) anderer Wegpunkt
        self.assertNotEqual(before, e._random_waypoint(5))
        self.assertIn("reseed", dict(e.list_actions()))

    def test_serialization_keeps_seed(self):
        e = self._efx(seed=98765)
        e2 = EfxInstance.from_dict(e.to_dict())
        self.assertEqual(e2.random_seed, 98765)
        self.assertEqual(e2.algorithm, EfxAlgorithm.RANDOM)


if __name__ == "__main__":
    unittest.main()
