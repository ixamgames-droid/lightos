"""Tests fuer die 6 neuen koordinatenbasierten Matrix-Algorithmen (I2.3/I2.5).

Prueft: Robustheit (keine Exception, korrekte Laenge) fuer alle Groessen,
Determinismus (gleiche Phase → gleiche Pixel) und gezielte Verhaltens-Asserts.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.engine.rgb_matrix import RgbMatrixInstance, RgbAlgorithm


def make_matrix(algo: RgbAlgorithm, cols: int, rows: int,
                phase: float = 0.0, **params) -> list:
    """Hilfsfunktion: Matrix erzeugen und direkt rendern."""
    m = RgbMatrixInstance(name="t", cols=cols, rows=rows,
                          algorithm=algo, color1=(255, 0, 0))
    m.params.update(params)
    return m._render(phase)


# ── Alle neuen Algorithmen und Groessen ─────────────────────────────────────
NEW_ALGOS = [
    RgbAlgorithm.CENTER_OUT,
    RgbAlgorithm.OUTER_IN,
    RgbAlgorithm.BOUNCE_H,
    RgbAlgorithm.BOUNCE_V,
    RgbAlgorithm.DIAG_WAVE,
    RgbAlgorithm.SPIRAL,
]

SIZES = [(1, 1), (1, 8), (8, 1), (5, 3), (4, 4)]
PHASES = [0.0, 3.7, 50.0]


class TestRobustheit(unittest.TestCase):
    """Kein Exception, korrekte Pixelanzahl fuer alle Groessen und Phasen."""

    def test_laenge_und_keine_exception(self):
        for algo in NEW_ALGOS:
            for cols, rows in SIZES:
                for phase in PHASES:
                    with self.subTest(algo=algo.name, cols=cols, rows=rows, phase=phase):
                        pixels = make_matrix(algo, cols, rows, phase)
                        self.assertEqual(
                            len(pixels), cols * rows,
                            msg=f"{algo.name} {cols}x{rows} @ {phase}: len={len(pixels)}, erwartet {cols*rows}"
                        )
                        # Alle Eintraege muessen (R,G,B)-Tupel sein
                        for px in pixels:
                            self.assertEqual(len(px), 3)


# ── Determinismus ────────────────────────────────────────────────────────────

class TestDeterminismus(unittest.TestCase):
    """Gleiche Phase → exakt gleiche Pixel (keine Zufalls-Elemente in neuen Algos)."""

    def test_spiral_deterministisch(self):
        """SPIRAL nutzt math.atan2/hypot — muss deterministisch sein."""
        m = RgbMatrixInstance(name="t", cols=6, rows=6,
                              algorithm=RgbAlgorithm.SPIRAL,
                              color1=(255, 0, 0))
        self.assertEqual(m._render(2.0), m._render(2.0))

    def test_center_out_deterministisch(self):
        m = RgbMatrixInstance(name="t", cols=5, rows=3,
                              algorithm=RgbAlgorithm.CENTER_OUT,
                              color1=(255, 0, 0))
        self.assertEqual(m._render(1.5), m._render(1.5))

    def test_diag_wave_deterministisch(self):
        m = RgbMatrixInstance(name="t", cols=4, rows=4,
                              algorithm=RgbAlgorithm.DIAG_WAVE,
                              color1=(255, 0, 0))
        self.assertEqual(m._render(7.0), m._render(7.0))


# ── Gezielte Verhaltens-Asserts ──────────────────────────────────────────────

class TestCenterOut(unittest.TestCase):
    """CENTER_OUT: expandierender Ring ab Mitte."""

    def test_mittelzelle_leuchtet_phase0(self):
        """cols=5, rows=1, phase=0.0: Mittelzelle (idx 2) an, Randzelle (idx 0) aus."""
        pixels = make_matrix(RgbAlgorithm.CENTER_OUT, 5, 1, 0.0)
        self.assertEqual(pixels[2], (255, 0, 0),
                         "Mittelzelle muss bei phase=0 leuchten")
        self.assertEqual(pixels[0], (0, 0, 0),
                         "Randzelle muss bei phase=0 aus sein")


class TestOuterIn(unittest.TestCase):
    """OUTER_IN: kontrahierender Ring von aussen nach innen."""

    def test_rand_an_mitte_aus_phase0(self):
        """cols=5, rows=1, phase=0.0: Randzelle (idx 0) an, Mitte (idx 2) aus."""
        pixels = make_matrix(RgbAlgorithm.OUTER_IN, 5, 1, 0.0)
        self.assertEqual(pixels[0], (255, 0, 0),
                         "Randzelle muss bei phase=0 leuchten")
        self.assertEqual(pixels[2], (0, 0, 0),
                         "Mittelzelle muss bei phase=0 aus sein")


class TestBounceH(unittest.TestCase):
    """BOUNCE_H: Pingpong-Laeufer ueber Spalten."""

    def test_links_an_phase0(self):
        """cols=5, rows=1, phase=0.0: Pixel ganz links an, ganz rechts aus."""
        pixels = make_matrix(RgbAlgorithm.BOUNCE_H, 5, 1, 0.0)
        self.assertEqual(pixels[0], (255, 0, 0),
                         "Linke Zelle muss bei phase=0 leuchten")
        self.assertEqual(pixels[4], (0, 0, 0),
                         "Rechte Zelle muss bei phase=0 aus sein")

    def test_rechts_an_phase4(self):
        """cols=5, rows=1, phase=4.0: Pixel ganz rechts an."""
        pixels = make_matrix(RgbAlgorithm.BOUNCE_H, 5, 1, 4.0)
        self.assertEqual(pixels[4], (255, 0, 0),
                         "Rechte Zelle muss bei phase=4 leuchten (Bounce-Umkehr)")


class TestDiagWave(unittest.TestCase):
    """DIAG_WAVE: wandernde Diagonalbande, default width=1."""

    def test_nur_diagonalstart_phase0(self):
        """cols=3, rows=3, phase=0.0, width=1:
        Zelle (col=0,row=0) → band=0 → an;
        Zelle (col=1,row=0) → band=1 → aus."""
        pixels = make_matrix(RgbAlgorithm.DIAG_WAVE, 3, 3, 0.0)
        self.assertEqual(pixels[0], (255, 0, 0),
                         "Zelle (0,0) muss bei phase=0 leuchten (band=0 < 1)")
        self.assertEqual(pixels[1], (0, 0, 0),
                         "Zelle (1,0) muss bei phase=0 aus sein (band=1 nicht < 1)")


class TestSpiral(unittest.TestCase):
    """SPIRAL: rotierender Spiralarm."""

    def test_nicht_alle_nicht_keiner(self):
        """cols=6, rows=6, phase=1.0: mindestens 1 Pixel an und nicht alle an."""
        pixels = make_matrix(RgbAlgorithm.SPIRAL, 6, 6, 1.0)
        anzahl_an = sum(1 for px in pixels if px != (0, 0, 0))
        self.assertGreater(anzahl_an, 0,
                           "SPIRAL muss bei phase=1 mindestens 1 Pixel einschalten")
        self.assertLess(anzahl_an, 36,
                        "SPIRAL darf bei phase=1 nicht alle 36 Pixel einschalten")


if __name__ == "__main__":
    unittest.main()
