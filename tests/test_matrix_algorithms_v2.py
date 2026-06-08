"""Tests fuer die eigenstaendigen Textur-Algorithmen (nach der Phase-3-Konsolidierung).

Radar/Spirale/Sine-Plasma/Windrad/Atmen/Strobe/Feuer/Regen bleiben bewusst eigene
Algorithmen (kein Verschmelzen). Prueft Robustheit, Determinismus (ausser den
zufallsbasierten) und gezieltes Verhalten.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.engine.rgb_matrix import RgbMatrixInstance, RgbAlgorithm


def make_matrix(algo: RgbAlgorithm, cols: int, rows: int,
                phase: float = 0.0, **params) -> list:
    m = RgbMatrixInstance(name="t", cols=cols, rows=rows, algorithm=algo,
                          color1=(255, 0, 0), color2=(0, 0, 255))
    m.params.update(params)
    return m._render(phase)


# Texturen (auch die zufallsbasierten fuer den Robustheits-Test).
TEXTURE_ALGOS = [
    RgbAlgorithm.RADAR,
    RgbAlgorithm.SPIRAL,
    RgbAlgorithm.SINEPLASMA,
    RgbAlgorithm.PINWHEEL,
    RgbAlgorithm.BREATHE,
    RgbAlgorithm.STROBE,
    RgbAlgorithm.FIRE,
    RgbAlgorithm.RAIN,
    RgbAlgorithm.RANDOM,
]
# Deterministisch (ohne random).
DETERMINISTIC = [RgbAlgorithm.RADAR, RgbAlgorithm.SPIRAL, RgbAlgorithm.SINEPLASMA,
                 RgbAlgorithm.PINWHEEL, RgbAlgorithm.BREATHE, RgbAlgorithm.STROBE]

SIZES = [(1, 1), (1, 8), (8, 1), (5, 3), (4, 4)]
PHASES = [0.0, 3.7, 50.0]


class TestRobustheit(unittest.TestCase):
    def test_laenge_und_range(self):
        for algo in TEXTURE_ALGOS:
            for cols, rows in SIZES:
                for phase in PHASES:
                    with self.subTest(algo=algo.name, cols=cols, rows=rows, phase=phase):
                        px = make_matrix(algo, cols, rows, phase)
                        self.assertEqual(len(px), cols * rows)
                        for p in px:
                            self.assertEqual(len(p), 3)
                            for ch in p:
                                self.assertTrue(0 <= ch <= 255,
                                                f"{algo.name}: Kanal {ch} ausserhalb 0..255")


class TestDeterminismus(unittest.TestCase):
    def test_gleiche_phase_gleiche_pixel(self):
        for algo in DETERMINISTIC:
            with self.subTest(algo=algo.name):
                self.assertEqual(make_matrix(algo, 6, 4, 2.0),
                                 make_matrix(algo, 6, 4, 2.0))


class TestVerhalten(unittest.TestCase):
    def test_strobe_an_aus(self):
        self.assertEqual(make_matrix(RgbAlgorithm.STROBE, 4, 1, 0.0)[0], (255, 0, 0))
        self.assertEqual(make_matrix(RgbAlgorithm.STROBE, 4, 1, 1.0)[0], (0, 0, 0))

    def test_breathe_startet_dunkel(self):
        self.assertEqual(make_matrix(RgbAlgorithm.BREATHE, 4, 1, 0.0)[0], (0, 0, 0))

    def test_pinwheel_nutzt_beide_farben(self):
        px = make_matrix(RgbAlgorithm.PINWHEEL, 6, 6, 0.0)
        self.assertIn((255, 0, 0), px)
        self.assertIn((0, 0, 255), px)

    def test_radar_strahl_vorhanden(self):
        px = make_matrix(RgbAlgorithm.RADAR, 6, 6, 1.0)
        an = sum(1 for p in px if p != (0, 0, 0))
        self.assertGreater(an, 0)
        self.assertLess(an, 36)


if __name__ == "__main__":
    unittest.main()
