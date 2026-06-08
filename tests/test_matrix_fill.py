"""Tests fuer den NEUEN, zeitlichen Fill-Algorithmus (WP-3 / Abschnitt 4).

Fill fuellt die echten Fixtures NACHEINANDER in der gewaehlten Reihenfolge.
Style bestimmt die Art (Dimmer/Shutter = Helligkeit up/down/random; RGB/RGBW =
Farbe target/random/sequence). Luecken (None) bekommen nie Output (#6).
"""
import unittest

from src.core.engine.rgb_matrix import (RgbMatrixInstance, RgbAlgorithm,
                                         MatrixStyle, ColorSequence)


def _fill(grid, cols, rows, t=8.0, style=MatrixStyle.DIMMER, **params):
    m = RgbMatrixInstance(cols=cols, rows=rows, algorithm=RgbAlgorithm.FILL,
                          fixture_grid=grid)
    m.style = style
    is_int = style in (MatrixStyle.DIMMER, MatrixStyle.SHUTTER)
    base = {
        "fill_mode": "up" if is_int else "target",
        "fill_dir": "left", "fill_speed": 1.0, "fade": 0.0,
        "hold": 0.0, "loop_mode": "stay",
    }
    base.update(params)
    m.params = base
    return m._render(t)


def _on(px):
    return [i for i, p in enumerate(px) if p != (0, 0, 0)]


class FillTest(unittest.TestCase):

    def test_stay_fuellt_am_ende_alle_echten(self):
        # loop_mode=stay, grosse Zeit -> alle echten Fixtures gefuellt.
        self.assertEqual(_on(_fill([10, 11, 12, 13], 4, 1, t=50.0)), [0, 1, 2, 3])

    def test_luecken_nie_an(self):
        # 4x2: echte Zellen = [1,2,4,7]; Luecken (None) bleiben immer aus.
        grid = [None, 1, 2, None, 3, None, None, 4]
        self.assertEqual(_on(_fill(grid, 4, 2, t=50.0)), [1, 2, 4, 7])

    def test_progressiv_mehr_ueber_zeit(self):
        # 'up': je spaeter, desto mehr Fixtures sind hell (Schritt fuer Schritt).
        early = len(_on(_fill([1, 2, 3, 4, 5, 6, 7, 8], 8, 1, t=2.0)))
        late = len(_on(_fill([1, 2, 3, 4, 5, 6, 7, 8], 8, 1, t=6.0)))
        self.assertLess(early, late)

    def test_richtung_links_vs_rechts(self):
        # Bei t=2 (Tempo 1.0) sind 2 Fixtures gefuellt — je nach Reihenfolge.
        links = _on(_fill([1, 2, 3, 4], 4, 1, t=2.0, fill_dir="left"))
        rechts = _on(_fill([1, 2, 3, 4], 4, 1, t=2.0, fill_dir="right"))
        self.assertEqual(links, [0, 1])
        self.assertEqual(rechts, [2, 3])

    def test_center_out_mitte_zuerst(self):
        # 5x1, t=3 -> 3 Fixtures, Mitte zuerst -> idx 1,2,3.
        lit = _on(_fill([1, 2, 3, 4, 5], 5, 1, t=3.0, fill_dir="center_out"))
        self.assertEqual(sorted(lit), [1, 2, 3])

    def test_down_startet_voll_und_leert(self):
        # 'down': zu Beginn alle an, mit der Zeit nacheinander aus.
        voll = len(_on(_fill([1, 2, 3, 4], 4, 1, t=0.0, fill_mode="down")))
        spaet = len(_on(_fill([1, 2, 3, 4], 4, 1, t=50.0, fill_mode="down")))
        self.assertEqual(voll, 4)
        self.assertEqual(spaet, 0)

    def test_empty_grid_behandelt_alle_als_echt(self):
        # Ohne Zuweisung (Demo/Preview) gelten alle Zellen als echt.
        self.assertEqual(_on(_fill([], 4, 1, t=50.0)), [0, 1, 2, 3])

    def test_color_target_progressiv_und_farbe(self):
        # RGB-Style, target: fuellt zur aktiven Farbe; mehr Fixtures ueber Zeit.
        m = RgbMatrixInstance(cols=4, rows=1, algorithm=RgbAlgorithm.FILL,
                              fixture_grid=[1, 2, 3, 4])
        m.style = MatrixStyle.RGB
        m.colors = ColorSequence([(255, 0, 0)])
        m.params = {"fill_mode": "target", "fill_dir": "left", "fill_speed": 1.0,
                    "fade": 0.0, "hold": 0.0, "loop_mode": "stay"}
        self.assertLess(len(_on(m._render(1.5))), len(_on(m._render(50.0))))
        full = m._render(50.0)
        self.assertEqual(full[0], (255, 0, 0))

    def test_color_sequence_reihenfolge(self):
        # RGB-Style, sequence: Fixtures bekommen die Farben der Reihe nach.
        m = RgbMatrixInstance(cols=3, rows=1, algorithm=RgbAlgorithm.FILL,
                              fixture_grid=[1, 2, 3])
        m.style = MatrixStyle.RGB
        m.colors = ColorSequence([(255, 0, 0), (0, 255, 0), (0, 0, 255)])
        m.params = {"fill_mode": "sequence", "fill_dir": "left", "fill_speed": 1.0,
                    "fade": 0.0, "hold": 0.0, "loop_mode": "stay"}
        px = m._render(50.0)
        self.assertEqual(px[0], (255, 0, 0))
        self.assertEqual(px[1], (0, 255, 0))
        self.assertEqual(px[2], (0, 0, 255))

    def test_set_param_live_fill_speed(self):
        """set_param('fill_speed', ...) wirkt sofort (VC-Slider-Pfad)."""
        m = RgbMatrixInstance(cols=4, rows=1, algorithm=RgbAlgorithm.FILL,
                              fixture_grid=[1, 2, 3, 4])
        m.params = {"fill_mode": "up", "fill_dir": "left", "loop_mode": "stay"}
        self.assertTrue(m.set_param("fill_speed", 3.0))
        self.assertAlmostEqual(m.params["fill_speed"], 3.0, places=3)

    def test_robust_alle_modi_und_loops(self):
        # Keine Exception, korrekte Laenge, Kanal 0..255 ueber alle Kombinationen.
        for style in (MatrixStyle.RGB, MatrixStyle.RGBW,
                      MatrixStyle.DIMMER, MatrixStyle.SHUTTER):
            for mode in ("up", "down", "random", "target", "sequence"):
                for loop in ("restart", "stay", "reverse", "fadeout"):
                    m = RgbMatrixInstance(cols=5, rows=3, algorithm=RgbAlgorithm.FILL,
                                          fixture_grid=list(range(1, 16)))
                    m.style = style
                    m.params = {"fill_mode": mode, "fill_dir": "center_out",
                                "fill_speed": 1.3, "fade": 0.4, "hold": 2.0,
                                "loop_mode": loop}
                    for ph in (0.0, 2.7, 12.3, 40.0):
                        px = m._render(ph)
                        self.assertEqual(len(px), 15)
                        for c in px:
                            self.assertTrue(all(0 <= ch <= 255 for ch in c))


if __name__ == "__main__":
    unittest.main()
