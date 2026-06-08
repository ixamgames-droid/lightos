"""Tests fuer den vereinheitlichten Random-Algorithmus (Phase 4, #8.4 + #6).

Random waehlt NIE eine Luecke, haelt 'count' echte Fixtures aktiv, ist pro Phase
deterministisch (Vorschau == Output), und bietet mehrere Modi.
"""
import unittest

from src.core.engine.rgb_matrix import RgbMatrixInstance, RgbAlgorithm


def _rand(fixture_grid, cols, rows, phase, **params):
    m = RgbMatrixInstance(cols=cols, rows=rows, algorithm=RgbAlgorithm.RANDOM,
                          fixture_grid=fixture_grid)
    m.params = {"mode": "color", "count": 1, "rate": 1.0, "no_repeat": True}
    m.params.update(params)
    return m, m._render(phase)


def _on(px):
    return [i for i, p in enumerate(px) if p != (0, 0, 0)]


GAP_GRID = [None, 1, 2, 3, None, 5]   # echte Zellen: 1,2,3,5


class RandomTest(unittest.TestCase):

    def test_nie_luecke_ueber_viele_phasen(self):
        gaps = {0, 4}
        for ph in [i * 0.37 for i in range(60)]:
            _, px = _rand(GAP_GRID, 6, 1, ph, count=3)
            for i in _on(px):
                self.assertNotIn(i, gaps, f"Random hat Luecke {i} gewaehlt @ phase {ph}")

    def test_count_begrenzt_aktive(self):
        for ph in [0.0, 1.0, 2.5, 9.0]:
            _, px = _rand(GAP_GRID, 6, 1, ph, count=2, mode="color")
            self.assertLessEqual(len(_on(px)), 2)

    def test_count_groesser_als_echte_klemmt(self):
        # count 10 bei nur 4 echten → hoechstens 4 aktiv, nie eine Luecke
        _, px = _rand(GAP_GRID, 6, 1, 0.0, count=10)
        self.assertLessEqual(len(_on(px)), 4)

    def test_deterministisch_pro_phase(self):
        m, px1 = _rand(GAP_GRID, 6, 1, 2.5, count=2)
        self.assertEqual(px1, m._render(2.5), "gleiche Phase → gleiche Pixel")

    def test_no_repeat_disjunkt_zum_vorgaenger(self):
        # Per Konstruktion: bei no_repeat ist die Auswahl eines Buckets disjunkt
        # zur (rohen) Auswahl des Vorgaengers, solange es genug echte Zellen gibt.
        real = [1, 2, 3, 5]
        m = RgbMatrixInstance(cols=6, rows=1, algorithm=RgbAlgorithm.RANDOM,
                              fixture_grid=GAP_GRID)
        for b in range(1, 40):
            prev_raw = set(m._random_selection(real, 1, b - 1, "all", 6, 1, False))
            sel = set(m._random_selection(real, 1, b, "all", 6, 1, True))
            self.assertTrue(sel.isdisjoint(prev_raw),
                            f"Bucket {b}: Auswahl {sel} ueberlappt Vorgaenger {prev_raw}")

    def test_scope_row_leuchtet_ganze_reihe(self):
        # 4x2, alle echt, scope row, count 1 → eine ganze Reihe (4 Zellen) an
        grid = list(range(8))
        m = RgbMatrixInstance(cols=4, rows=2, algorithm=RgbAlgorithm.RANDOM, fixture_grid=grid)
        m.params = {"mode": "color", "count": 1, "rate": 1.0, "scope": "row"}
        lit = _on(m._render(0.0))
        self.assertEqual(len(lit), 4, "scope row mit count 1 → genau eine Reihe (4 Zellen)")
        rows = {i // 4 for i in lit}
        self.assertEqual(len(rows), 1)

    def test_modi_laufen_ohne_fehler(self):
        for mode in ("color", "dimmer", "strobe", "flash", "sparkle", "pulse"):
            for ph in [0.0, 0.3, 0.5, 1.2]:
                _, px = _rand(GAP_GRID, 6, 1, ph, mode=mode, count=2)
                self.assertEqual(len(px), 6)
                for i in _on(px):
                    self.assertNotIn(i, {0, 4})

    def test_pulse_hat_helligkeitsverlauf(self):
        # Pulse: bei frac 0.5 (Phasenmitte) hell, bei frac 0.0 dunkel.
        _, px_mid = _rand(GAP_GRID, 6, 1, 0.5, mode="pulse", count=4, rate=1.0)
        self.assertGreater(len(_on(px_mid)), 0, "Pulse muss in der Bucket-Mitte leuchten")


if __name__ == "__main__":
    unittest.main()
