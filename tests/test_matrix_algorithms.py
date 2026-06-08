"""Tests fuer die konsolidierten Grundalgorithmen (Phase 3).

Chase/Wipe/Wave/Gradient ersetzen die fruehere Vielzahl an Richtungs-/Bewegungs-
Varianten; Bewegung/Achse/Ursprung sind jetzt Parameter. Prueft Robustheit
(keine Exception, korrekte Laenge, Kanal 0..255), Determinismus und gezielte
Verhaltens-Asserts (Aequivalenz zu den frueheren Einzel-Algorithmen).
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.engine.rgb_matrix import RgbMatrixInstance, RgbAlgorithm


def make_matrix(algo: RgbAlgorithm, cols: int, rows: int,
                phase: float = 0.0, **params) -> list:
    m = RgbMatrixInstance(name="t", cols=cols, rows=rows, algorithm=algo,
                          color1=(255, 0, 0), color2=(0, 0, 255), color3=(0, 255, 0))
    m.params.update(params)
    return m._render(phase)


def lit_idx(pixels):
    return [i for i, p in enumerate(pixels) if p != (0, 0, 0)]


BASE_ALGOS = [RgbAlgorithm.CHASE, RgbAlgorithm.WIPE, RgbAlgorithm.WAVE, RgbAlgorithm.GRADIENT]
SIZES = [(1, 1), (1, 8), (8, 1), (5, 3), (4, 4)]
PHASES = [0.0, 3.7, 50.0]
MOVEMENTS = ["normal", "bounce", "center_out", "outside_in"]
AXES = ["H", "V", "Diag"]
ORIGINS = ["left", "right", "top", "bottom", "center", "radial"]


class TestRobustheit(unittest.TestCase):
    def test_base_algos_laenge_und_range(self):
        for algo in BASE_ALGOS:
            for cols, rows in SIZES:
                for phase in PHASES:
                    with self.subTest(algo=algo.name, cols=cols, rows=rows, phase=phase):
                        px = make_matrix(algo, cols, rows, phase)
                        self.assertEqual(len(px), cols * rows)
                        for p in px:
                            self.assertEqual(len(p), 3)
                            for ch in p:
                                self.assertTrue(0 <= ch <= 255)

    def test_chase_all_movements_axes(self):
        for mv in MOVEMENTS:
            for ax in AXES:
                for cols, rows in SIZES:
                    with self.subTest(movement=mv, axis=ax, cols=cols, rows=rows):
                        px = make_matrix(RgbAlgorithm.CHASE, cols, rows, 2.0,
                                         movement=mv, axis=ax)
                        self.assertEqual(len(px), cols * rows)

    def test_wave_all_origins(self):
        for origin in ORIGINS:
            for cols, rows in SIZES:
                with self.subTest(origin=origin, cols=cols, rows=rows):
                    px = make_matrix(RgbAlgorithm.WAVE, cols, rows, 1.3, origin=origin)
                    self.assertEqual(len(px), cols * rows)


class TestDeterminismus(unittest.TestCase):
    def test_gleiche_phase_gleiche_pixel(self):
        for algo in BASE_ALGOS:
            with self.subTest(algo=algo.name):
                self.assertEqual(make_matrix(algo, 6, 4, 2.0),
                                 make_matrix(algo, 6, 4, 2.0))


class TestChaseMovement(unittest.TestCase):
    """Aequivalenz zu den frueheren Einzel-Algorithmen (jetzt Parameter)."""

    def test_normal_h_links_an_phase0(self):
        # ex-Chase Horizontal: phase 0 → idx 0 an, Rest aus (1 Laeufer, Breite 1).
        # after_fade=0 -> harter Läufer ohne Schweif (Default ist jetzt 30 %).
        px = make_matrix(RgbAlgorithm.CHASE, 5, 1, 0.0, axis="H",
                         movement="normal", after_fade=0.0)
        self.assertEqual(lit_idx(px), [0])
        self.assertEqual(px[0], (255, 0, 0))

    def test_center_out_mitte_an_phase0(self):
        # ex-Center→Außen: phase 0 → Mittelzelle an, Rand aus.
        px = make_matrix(RgbAlgorithm.CHASE, 5, 1, 0.0, movement="center_out")
        self.assertEqual(px[2], (255, 0, 0))
        self.assertEqual(px[0], (0, 0, 0))

    def test_outside_in_rand_an_phase0(self):
        # ex-Außen→Center: phase 0 → Rand an, Mitte aus.
        px = make_matrix(RgbAlgorithm.CHASE, 5, 1, 0.0, movement="outside_in")
        self.assertEqual(px[0], (255, 0, 0))
        self.assertEqual(px[2], (0, 0, 0))

    def test_bounce_h_pingpong(self):
        # ex-Bounce H: phase 0 → links, phase 4 → rechts (cols=5).
        self.assertEqual(make_matrix(RgbAlgorithm.CHASE, 5, 1, 0.0,
                                     movement="bounce", axis="H")[0], (255, 0, 0))
        self.assertEqual(make_matrix(RgbAlgorithm.CHASE, 5, 1, 4.0,
                                     movement="bounce", axis="H")[4], (255, 0, 0))

    def test_fade_tail_comet(self):
        # ex-Komet: Schweif (fade>0) → Kopf voll hell, dahinter dunkler.
        px = make_matrix(RgbAlgorithm.CHASE, 8, 1, 0.0, axis="H", fade=0.5)
        self.assertEqual(px[0], (255, 0, 0), "Kopf bei phase 0 voll hell")
        self.assertLess(max(px[1]), 255, "hinter dem Kopf dunkler")

    def test_color_cycle_wechselt_pro_runde(self):
        # ex-Chase Multicolor: Farbe wechselt durch die Sequence pro Durchlauf.
        m = RgbMatrixInstance(cols=4, rows=1, algorithm=RgbAlgorithm.CHASE,
                              color1=(255, 0, 0), color2=(0, 255, 0), color3=(0, 0, 255))
        m.params.update(dict(axis="H", color_cycle=True))
        # Runde 0 → erste Farbe, Runde 1 (phase=cols) → zweite Farbe.
        c_round0 = [p for p in m._render(0.0) if p != (0, 0, 0)][0]
        c_round1 = [p for p in m._render(4.0) if p != (0, 0, 0)][0]
        self.assertEqual(c_round0, (255, 0, 0))
        self.assertEqual(c_round1, (0, 255, 0))


class TestWave(unittest.TestCase):
    def test_radial_deterministisch(self):
        # ex-Ripple: radiale Welle, deterministisch (kein random).
        self.assertEqual(make_matrix(RgbAlgorithm.WAVE, 5, 5, 2.0, origin="radial"),
                         make_matrix(RgbAlgorithm.WAVE, 5, 5, 2.0, origin="radial"))

    def test_left_origin_brightness_wave(self):
        # ex-Welle H: Helligkeitswelle in c1 — mind. eine helle und eine dunkle Zelle.
        px = make_matrix(RgbAlgorithm.WAVE, 8, 1, 1.0, origin="left")
        helligkeiten = {max(p) for p in px}
        self.assertGreater(len(helligkeiten), 1, "Welle muss Helligkeitsunterschiede zeigen")


class TestGradient(unittest.TestCase):
    def test_smooth_kein_schwarz(self):
        # Verlauf mischt nur Sequence-Farben (alle != schwarz) → nie komplett aus.
        px = make_matrix(RgbAlgorithm.GRADIENT, 8, 1, 1.3, axis="H", blend="smooth")
        self.assertTrue(all(sum(p) > 0 for p in px))

    def test_steps_nur_sequence_farben(self):
        # ex-Color Scroll: harte Baender → jeder Pixel ist exakt eine Sequence-Farbe.
        seq = {(255, 0, 0), (0, 0, 255), (0, 255, 0)}
        px = make_matrix(RgbAlgorithm.GRADIENT, 9, 1, 0.0, axis="H", blend="steps")
        for p in px:
            self.assertIn(p, seq)


class TestSpiralTextur(unittest.TestCase):
    """SPIRAL bleibt eigenstaendige Textur (nicht konsolidiert)."""

    def test_nicht_alle_nicht_keiner(self):
        px = make_matrix(RgbAlgorithm.SPIRAL, 6, 6, 1.0)
        an = len(lit_idx(px))
        self.assertGreater(an, 0)
        self.assertLess(an, 36)

    def test_deterministisch(self):
        self.assertEqual(make_matrix(RgbAlgorithm.SPIRAL, 6, 6, 2.0),
                         make_matrix(RgbAlgorithm.SPIRAL, 6, 6, 2.0))


if __name__ == "__main__":
    unittest.main()
