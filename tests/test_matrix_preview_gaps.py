"""Tests fuer die Luecken-Erkennung der Effekt-Vorschau (Phase 1).

`is_gap()` entscheidet, ob eine Matrix-Zelle eine bewusste Luecke ist
(raeumlich vorhanden, aber kein Fixture → in der Vorschau sichtbar leer,
kein Effekt-Output). Geprueft an genau den in der Anforderung genannten
Mustern.
"""
import unittest

from src.core.engine.rgb_matrix import is_gap, grid_from_positions


def _gap_mask(grid):
    """Liste der is_gap()-Ergebnisse fuer alle Zellen (zum kompakten Vergleich)."""
    return [is_gap(grid, i) for i in range(len(grid))]


class IsGapTest(unittest.TestCase):

    def test_empty_grid_has_no_gaps(self):
        """Leeres fixture_grid (keine Zuweisung) = geraeteunabhaengige Demo →
        keine Luecken, damit die Such-/Demo-Vorschau alle Zellen zeigt."""
        self.assertFalse(is_gap([], 0))
        self.assertFalse(is_gap([], 5))

    def test_2x4_pattern_o_x_x_o__x_o_o_x(self):
        """Obere Reihe o x x o, untere Reihe x o o x (o=Luecke, x=Fixture)."""
        # row-major, cols=4, rows=2
        grid = [None, 1, 2, None,
                3, None, None, 4]
        self.assertEqual(
            _gap_mask(grid),
            [True, False, False, True,
             False, True, True, False],
        )

    def test_3x3_empty_center(self):
        """3×3 mit leerer Mitte: nur idx 4 ist Luecke."""
        grid = [1, 2, 3,
                4, None, 6,
                7, 8, 9]
        self.assertEqual([i for i, g in enumerate(_gap_mask(grid)) if g], [4])

    def test_single_occupied_cell(self):
        """1×3, nur die mittlere Zelle besetzt → idx 0 und 2 sind Luecken."""
        grid = [None, 1, None]
        self.assertEqual(_gap_mask(grid), [True, False, True])

    def test_empty_first_and_last(self):
        grid = [None, 1, 2, None]
        self.assertEqual(_gap_mask(grid), [True, False, False, True])

    def test_out_of_range_is_gap(self):
        """Index ausserhalb eines (nicht leeren) Grids = Luecke (defensive)."""
        grid = [1, 2]
        self.assertTrue(is_gap(grid, 2))
        self.assertTrue(is_gap(grid, -1))

    def test_consistent_with_grid_from_positions(self):
        """Aus positions_json gebautes Grid: nicht belegte Zellen sind Luecken."""
        # 4×2-Raster: Fixtures bei (1,0),(2,0),(0,1),(3,1) → o x x o / x o o x
        positions = {"1,0": 1, "2,0": 2, "0,1": 3, "3,1": 4}
        grid = grid_from_positions(positions, cols=4, rows=2)
        self.assertEqual(grid, [None, 1, 2, None, 3, None, None, 4])
        self.assertEqual(
            _gap_mask(grid),
            [True, False, False, True, False, True, True, False],
        )


if __name__ == "__main__":
    unittest.main()
