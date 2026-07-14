"""UI-26 / QOL-01: 2D-Bühne aufräumen — Raster-Default, LOD-Labels, Nachbar-Gaps.

Sichert die drei Bausteine gegen Regression:
- QOL-01: Auto-Layout (Patch ohne gespeicherte Positionen) ist ein label-sicheres
  Raster (kein dicht gedrängter Bogen mehr) — keine zwei Fixtures näher als STEP.
- UI-26: `_lod_for_screen_gap` degradiert das Label nach Bildschirm-Nachbarabstand;
  `_compute_label_gaps` cacht die Welt-Abstände; `FixtureRenderer.draw(lod=…)`
  reduziert bei höherem LOD sichtbar den Text.
"""
import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage, QPainter, QColor

from src.ui.views.live_view import (
    StageCanvas, FixtureRenderer, _lod_for_screen_gap, _grid_positions,
)

_app = QApplication.instance() or QApplication([])


def _fixtures(n):
    return [SimpleNamespace(fid=i + 1, universe=1, address=i * 10 + 1,
                            label=f"PAR-{i + 1}", fixture_type="PAR")
            for i in range(n)]


class TestLodThresholds(unittest.TestCase):
    """Reine Schwellenfunktion (kein Qt) — 0=voll, 1=kurz, 2=aus."""

    def test_thresholds_and_boundaries(self):
        f = _lod_for_screen_gap
        self.assertEqual(f(60.0), 0)
        self.assertEqual(f(48.0), 0)      # Grenze inklusiv
        self.assertEqual(f(47.9), 1)
        self.assertEqual(f(30.0), 1)
        self.assertEqual(f(22.0), 1)      # Grenze inklusiv
        self.assertEqual(f(21.9), 2)
        self.assertEqual(f(10.0), 2)
        self.assertEqual(f(0.0), 2)


class TestGridLayout(unittest.TestCase):
    """QOL-01: Auto-Layout (`_grid_positions`) ist label-sicher — reine Funktion,
    deterministisch, unabhaengig von Szene/Adapter."""

    def test_no_overlap_and_in_bounds(self):
        for n in (1, 3, 12, 48, 200):
            pts = _grid_positions(n, world_w=1200.0)
            self.assertEqual(len(pts), n)
            # Kein Paar naeher als STEP (90 px) -> Label-Rect (~72 px) kollidiert nie
            for i in range(len(pts)):
                for j in range(i + 1, len(pts)):
                    d = ((pts[i][0] - pts[j][0]) ** 2 + (pts[i][1] - pts[j][1]) ** 2) ** 0.5
                    self.assertGreaterEqual(round(d, 3), 89.9,
                                            f"n={n}: Fixtures zu nah: {pts[i]} {pts[j]}")
            for (x, y) in pts:
                self.assertGreaterEqual(x, 0.0)
                self.assertGreaterEqual(y, 0.0)

    def test_single_and_zero(self):
        self.assertEqual(len(_grid_positions(1, 1200.0)), 1)
        self.assertEqual(_grid_positions(0, 1200.0), [])

    def test_load_positions_integration_smoke(self):
        """_load_positions läuft mit Mock-Fixtures durch (Raster-Zweig + Gap-Cache)
        ohne Crash und füllt Positionen + nn_gap."""
        c = StageCanvas()
        try:
            fx = _fixtures(6)
            c._state.get_patched_fixtures = lambda: list(fx)
            c._load_positions()
            self.assertTrue(c._positions)          # Positionen vergeben
            self.assertTrue(c._nn_gap)             # Nachbar-Abstände berechnet
            for fid in (f.fid for f in fx):
                self.assertIn(fid, c._positions)
        finally:
            c._state.__dict__.pop("get_patched_fixtures", None)
            c.deleteLater()


class TestNeighbourGaps(unittest.TestCase):
    """UI-26: nn_gap = Welt-Abstand zum naechsten Nachbarn; Einzelfixture -> 1e9."""

    def test_gaps(self):
        c = StageCanvas()
        try:
            c._positions = {1: (0.0, 0.0), 2: (100.0, 0.0), 3: (0.0, 40.0)}
            c._compute_label_gaps()
            self.assertAlmostEqual(c._nn_gap[1], 40.0, places=3)   # 3 (40) < 2 (100)
            self.assertAlmostEqual(c._nn_gap[3], 40.0, places=3)
            self.assertAlmostEqual(c._nn_gap[2], 100.0, places=3)  # 1 (100) < 3 (107.7)
        finally:
            c.deleteLater()

    def test_single_fixture_default(self):
        c = StageCanvas()
        try:
            c._positions = {5: (10.0, 10.0)}
            c._compute_label_gaps()
            self.assertGreaterEqual(c._nn_gap[5], 1e8)   # kein Nachbar -> volles Label
        finally:
            c.deleteLater()


class TestDrawLodReducesText(unittest.TestCase):
    """Hoeheres LOD zeichnet weniger Text (Label/%/Badge fallen weg); Icon bleibt."""

    @staticmethod
    def _render(lod):
        img = QImage(220, 130, QImage.Format.Format_ARGB32)
        bg = QColor("#0d1117")
        img.fill(bg)
        p = QPainter(img)
        FixtureRenderer.draw(p, "PAR", 110, 65, 30, QColor("#ff8800"),
                             intensity=200, label="12", effects=[object()],
                             zoom=1.0, lod=lod)
        p.end()
        return img

    @staticmethod
    def _non_bg_pixels(img):
        bg = QColor("#0d1117").rgb()
        return sum(1 for y in range(img.height()) for x in range(img.width())
                   if (img.pixel(x, y) & 0xFFFFFF) != (bg & 0xFFFFFF))

    def test_lod_monotonic_ink(self):
        i0 = self._non_bg_pixels(self._render(0))   # Icon + "PAR 12" + % + FX-Badge
        i1 = self._non_bg_pixels(self._render(1))   # Icon + "12"
        i2 = self._non_bg_pixels(self._render(2))   # nur Icon
        self.assertGreater(i0, i1, "LOD 0 sollte mehr Text zeichnen als LOD 1")
        self.assertGreater(i1, i2, "LOD 1 sollte mehr Text zeichnen als LOD 2")
        self.assertGreater(i2, 0, "Das Icon soll bei LOD 2 weiter gezeichnet werden")


if __name__ == "__main__":
    unittest.main()
