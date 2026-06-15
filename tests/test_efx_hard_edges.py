"""EFX harte Kanten 2026-06-15.

David wollte Formen mit SCHARFEN Ecken (Quadrat, Raute, Trapez), nicht
„verschliffen". Frueher waren SQUARE und DIAMOND trigonometrische Naeherungen,
die die Ecken diagonal abschnitten (Quadrat erreichte (hw,hh) nie). Jetzt sind
alle vier (Dreieck/Quadrat/Raute/Trapez) echte Polygone: die Phase laeuft die
Eckpunkte linear ab, die Figur faehrt exakt in jede Ecke.
"""
import unittest

from src.core.engine.efx import EfxInstance, EfxAlgorithm


class HardEdgeTest(unittest.TestCase):
    def _efx(self, algo):
        e = EfxInstance("e")
        e.algorithm = algo
        e.width = e.height = 100.0   # hw = hh = 50, Zentrum 128
        e.x_offset = e.y_offset = 128.0
        return e

    def test_square_reaches_all_four_corners(self):
        e = self._efx(EfxAlgorithm.SQUARE)
        corners = [tuple(round(c) for c in e._calc(i / 4.0)) for i in range(4)]
        self.assertEqual(corners,
                         [(78, 78), (178, 78), (178, 178), (78, 178)])
        # Die echte Ecke (178,178) MUSS exakt getroffen werden (frueher abgeschnitten).
        self.assertIn((178, 178), corners)

    def test_square_edges_are_straight(self):
        # Auf einer Kante bleibt eine Koordinate konstant (echte gerade Kante).
        e = self._efx(EfxAlgorithm.SQUARE)
        # Erste Kante v0->v1: y konstant = 78 (Oberkante).
        for k in range(1, 10):
            _, y = e._calc((k / 10.0) * 0.25)
            self.assertAlmostEqual(y, 78, delta=1)

    def test_diamond_is_rhombus(self):
        e = self._efx(EfxAlgorithm.DIAMOND)
        corners = [tuple(round(c) for c in e._calc(i / 4.0)) for i in range(4)]
        self.assertEqual(corners,
                         [(128, 78), (178, 128), (128, 178), (78, 128)])

    def test_trapez_top_narrower_than_bottom(self):
        e = self._efx(EfxAlgorithm.TRAPEZ)
        v_top_l = e._calc(0.0)
        v_top_r = e._calc(0.25)
        v_bot_r = e._calc(0.5)
        v_bot_l = e._calc(0.75)
        top_width = abs(v_top_r[0] - v_top_l[0])
        bot_width = abs(v_bot_r[0] - v_bot_l[0])
        self.assertLess(top_width, bot_width)        # Oberkante schmaler
        self.assertEqual(round(v_top_l[1]), 78)      # Oberkante oben
        self.assertEqual(round(v_bot_l[1]), 178)     # Unterkante unten

    def test_all_polygons_close_back_to_start(self):
        for algo in (EfxAlgorithm.SQUARE, EfxAlgorithm.DIAMOND,
                     EfxAlgorithm.TRAPEZ, EfxAlgorithm.TRIANGLE):
            e = self._efx(algo)
            self.assertEqual(e._calc(0.0), e._calc(1.0), algo.value)

    def test_rotation_applies_to_polygon(self):
        # Quadrat um 90 Grad gedreht ist wieder ein Quadrat (gleiche Eckmenge).
        e = self._efx(EfxAlgorithm.SQUARE)
        base = {tuple(round(c) for c in e._calc(i / 4.0)) for i in range(4)}
        e.rotation = 90.0
        rot = {tuple(round(c) for c in e._calc(i / 4.0)) for i in range(4)}
        self.assertEqual(base, rot)

    def test_serialization_roundtrip_trapez(self):
        e = self._efx(EfxAlgorithm.TRAPEZ)
        e2 = EfxInstance.from_dict(e.to_dict())
        self.assertEqual(e2.algorithm, EfxAlgorithm.TRAPEZ)


if __name__ == "__main__":
    unittest.main()
