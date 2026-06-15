"""Tests fuer den zentralen, Qt-freien Farb-Helper color_attrs_for_fixture
(src/core/color_utils.py).

Mappt eine Ziel-RGB-Farbe auf die zu setzenden Attribut→Wert-Paare EINES
Fixtures anhand seiner echten Kanaele:
  (a) RGB(W)-Fixture → color_r/g/b (+ color_w wenn vorhanden)
  (b) Farbrad-Fixture (ein "color"-Kanal mit benannten Slots) → der dem Ziel
      naechste Slot-Mittelwert auf "color"
  (c) reines Weiss-Fixture (nur color_w) → color_w
  (d) leeres Fixture → {}
"""
import unittest

from src.core.color_utils import color_attrs_for_fixture, hex_to_rgb, color_word_hex


class _Range:
    def __init__(self, lo, hi, name="", kind=""):
        self.range_from = lo
        self.range_to = hi
        self.name = name
        self.kind = kind


class _Ch:
    def __init__(self, attr, ranges=None):
        self.attribute = attr
        self.ranges = ranges or []


class ColorAttrsForFixtureTest(unittest.TestCase):

    # (a) RGB / RGBW ----------------------------------------------------------
    def test_rgb_fixture(self):
        chans = [_Ch("color_r"), _Ch("color_g"), _Ch("color_b"), _Ch("intensity")]
        out = color_attrs_for_fixture(chans, (200, 100, 50))
        self.assertEqual(out, {"color_r": 200, "color_g": 100, "color_b": 50})
        self.assertNotIn("color_w", out)

    def test_rgbw_fixture_adds_white(self):
        chans = [_Ch("color_r"), _Ch("color_g"), _Ch("color_b"), _Ch("color_w")]
        # color_w = min(r,g,b)
        out = color_attrs_for_fixture(chans, (200, 100, 50))
        self.assertEqual(out, {"color_r": 200, "color_g": 100, "color_b": 50,
                               "color_w": 50})

    def test_rgb_clamps_input(self):
        chans = [_Ch("color_r"), _Ch("color_g"), _Ch("color_b")]
        out = color_attrs_for_fixture(chans, (300, -10, 128))
        self.assertEqual(out, {"color_r": 255, "color_g": 0, "color_b": 128})

    # (b) Farbrad -------------------------------------------------------------
    def _wheel(self):
        return [_Ch("color", [
            _Range(0, 9, "Weiß / Offen", "open"),
            _Range(10, 19, "Rot", "color"),
            _Range(20, 29, "Grün", "color"),
            _Range(30, 39, "Blau", "color"),
            _Range(140, 255, "Farbwechsel langsam → schnell", "rotate"),
        ])]

    def test_wheel_red(self):
        out = color_attrs_for_fixture(self._wheel(), (255, 0, 0))
        self.assertEqual(out, {"color": 14})   # Mitte von 10-19

    def test_wheel_green(self):
        out = color_attrs_for_fixture(self._wheel(), (0, 255, 0))
        self.assertEqual(out, {"color": 24})   # Mitte von 20-29

    def test_wheel_blue(self):
        out = color_attrs_for_fixture(self._wheel(), (0, 0, 255))
        self.assertEqual(out, {"color": 34})   # Mitte von 30-39

    def test_wheel_nearest_for_intermediate(self):
        # Orange (255,128,0) liegt naeher an Rot als an Gruen/Blau
        out = color_attrs_for_fixture(self._wheel(), (255, 128, 0))
        self.assertEqual(out, {"color": 14})

    def test_wheel_skips_unnamed_ranges(self):
        # Nur ein nicht-Farb-Slot -> kein Kandidat -> kein "color"-Output.
        chans = [_Ch("color", [_Range(0, 9, "Open", "open"),
                               _Range(10, 19, "Gobo-Mist", "color")])]
        out = color_attrs_for_fixture(chans, (255, 0, 0))
        self.assertEqual(out, {})

    def test_wheel_without_kind_uses_all_named(self):
        # Keine kind=="color"-Slots -> alle Ranges sind Kandidaten (nur die mit
        # erkennbarer Farbe im Namen zaehlen).
        chans = [_Ch("color", [_Range(10, 19, "Rot"), _Range(20, 29, "Blau")])]
        out = color_attrs_for_fixture(chans, (0, 0, 255))
        self.assertEqual(out, {"color": 24})

    # (c) reines Weiss --------------------------------------------------------
    def test_white_only_fixture(self):
        out = color_attrs_for_fixture([_Ch("color_w")], (200, 100, 50))
        self.assertEqual(out, {"color_w": 200})   # max(r,g,b)

    def test_white_named_attr(self):
        out = color_attrs_for_fixture([_Ch("white")], (10, 240, 30))
        self.assertEqual(out, {"white": 240})

    # (d) leer ----------------------------------------------------------------
    def test_empty_fixture(self):
        self.assertEqual(color_attrs_for_fixture([], (255, 0, 0)), {})

    def test_no_color_channels(self):
        chans = [_Ch("pan"), _Ch("tilt"), _Ch("intensity")]
        self.assertEqual(color_attrs_for_fixture(chans, (255, 0, 0)), {})

    def test_bad_rgb_input(self):
        self.assertEqual(color_attrs_for_fixture([_Ch("color_r")], None), {})


class ColorWordHelpersTest(unittest.TestCase):
    def test_hex_to_rgb(self):
        self.assertEqual(hex_to_rgb("#ff3030"), (255, 48, 48))
        self.assertEqual(hex_to_rgb("3060ff"), (48, 96, 255))
        self.assertEqual(hex_to_rgb("xxx"), (0, 0, 0))

    def test_color_word_hex(self):
        self.assertEqual(hex_to_rgb(color_word_hex("Rot")), (255, 48, 48))
        self.assertIsNone(color_word_hex("Gobo 1"))
        self.assertIsNone(color_word_hex("Farbrotation"))
        # "Hellblau" nicht als "Blau"
        self.assertNotEqual(color_word_hex("Hellblau"), color_word_hex("Blau"))

    def test_mirrors_preset_tile_wordlist(self):
        # Die Core-Spiegelung muss mit der UI-Wortliste uebereinstimmen.
        from src.ui.widgets.preset_tile import _NAME_COLOR_WORDS as UI_WORDS
        from src.core.color_utils import _NAME_COLOR_WORDS as CORE_WORDS
        self.assertEqual(CORE_WORDS, UI_WORDS)


if __name__ == "__main__":
    unittest.main()
