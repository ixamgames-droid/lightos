"""Tests fuer ColorFade (Phase 4, Anforderung #8.7 / #12).

Crossfade des ganzen Feldes durch die Color-Sequence; deaktivierte Farben werden
uebersprungen; Hold/Ping-Pong; live ueber Sequence/Aktionen steuerbar.
"""
import unittest

from src.core.engine.rgb_matrix import RgbMatrixInstance, RgbAlgorithm, ColorSequence


def _cf(colors, enabled_mask=None, **params):
    m = RgbMatrixInstance(cols=2, rows=1, algorithm=RgbAlgorithm.COLORFADE,
                          fixture_grid=[1, 2])
    seq = ColorSequence(colors)
    if enabled_mask is not None:
        for i, on in enumerate(enabled_mask):
            seq.set_enabled(i, on)
    m.colors = seq
    m.params = {"hold": 1.0}   # Hold=1 → exakt die Stufenfarbe (leicht testbar)
    m.params.update(params)
    return m


class ColorFadeTest(unittest.TestCase):

    R, G, B = (255, 0, 0), (0, 255, 0), (0, 0, 255)

    def test_cycelt_durch_aktive_farben(self):
        m = _cf([self.R, self.G, self.B])
        self.assertEqual(m._render(0.0)[0], self.R)
        self.assertEqual(m._render(1.0)[0], self.G)
        self.assertEqual(m._render(2.0)[0], self.B)
        self.assertEqual(m._render(3.0)[0], self.R)   # wrap

    def test_deaktivierte_farbe_uebersprungen(self):
        # Gruen deaktiviert → nur Rot/Blau erscheinen.
        m = _cf([self.R, self.G, self.B], enabled_mask=[True, False, True])
        seen = {m._render(float(p))[0] for p in range(6)}
        self.assertNotIn(self.G, seen, "deaktiviertes Gruen darf nie erscheinen")
        self.assertIn(self.R, seen)
        self.assertIn(self.B, seen)

    def test_ganzes_feld_einheitlich(self):
        m = _cf([self.R, self.G, self.B])
        m.cols, m.rows = 4, 2
        m.fixture_grid = list(range(8))
        px = m._render(1.0)
        self.assertTrue(all(p == px[0] for p in px), "alle Zellen gleiche Farbe")

    def test_eine_farbe_konstant(self):
        m = _cf([self.R])
        self.assertEqual(m._render(0.0)[0], self.R)
        self.assertEqual(m._render(2.7)[0], self.R)

    def test_crossfade_zwischen_farben(self):
        # hold=0 → bei t=0.5 Mischfarbe zwischen Rot und Gruen.
        m = _cf([self.R, self.G], hold=0.0)
        mid = m._render(0.5)[0]
        self.assertTrue(0 < mid[0] < 255 and 0 < mid[1] < 255,
                        f"Crossfade-Mischfarbe erwartet, got {mid}")

    def test_pingpong_kehrt_um(self):
        normal = _cf([self.R, self.G, self.B], pingpong=False)
        pingpong = _cf([self.R, self.G, self.B], pingpong=True)
        # Ohne Ping-Pong: Schritt 3 → wrap auf Rot. Mit Ping-Pong: Schritt 3 → zurueck auf Gruen.
        self.assertEqual(normal._render(3.0)[0], self.R)
        self.assertEqual(pingpong._render(3.0)[0], self.G)

    def test_live_farbe_hinzufuegen_wirkt(self):
        """do_action('add_color') erweitert die Sequence live (VC-Aktion)."""
        m = _cf([self.R, self.G])
        m.do_action("add_color", rgb=self.B)
        seen = {m._render(float(p))[0] for p in range(6)}
        self.assertIn(self.B, seen, "neu hinzugefuegte Farbe erscheint im Fade")


if __name__ == "__main__":
    unittest.main()
