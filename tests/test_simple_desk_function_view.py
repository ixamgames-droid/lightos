"""SD-01 + SD-02: Simple Desk zeigt pro Kanal ein Funktions-Kürzel und kann
die Fader nach Funktion (statt nach Fixture) einfärben."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import src.core.app_state as A
from src.core.app_state import get_state
from src.ui.views.simple_desk import (
    SimpleDeskView,
    channel_function_color,
    channel_function_abbrev,
    CHANNEL_FUNCTION_COLORS,
    _CHANNEL_FUNCTION_DEFAULT,
)

_app = QApplication.instance() or QApplication([])


class _Ch:
    def __init__(self, channel_number, name, attribute):
        self.channel_number = channel_number
        self.name = name
        self.attribute = attribute


class _F:
    def __init__(self, fid, universe, address, channel_count, label):
        self.fid = fid
        self.universe = universe
        self.address = address
        self.channel_count = channel_count
        self.label = label


# RGBW-Dimmer-Fixture: CH1 Dimmer, CH2-5 R/G/B/W
def _rgbw_channels(_fx):
    return [
        _Ch(1, "Dimmer", "dimmer"),
        _Ch(2, "Red", "color_r"),
        _Ch(3, "Green", "color_g"),
        _Ch(4, "Blue", "color_b"),
        _Ch(5, "White", "color_w"),
    ]


class HelperMapTest(unittest.TestCase):
    def test_color_lookup_known_and_unknown(self):
        self.assertEqual(channel_function_color("color_r"), "#ff4444")
        self.assertEqual(channel_function_color("dimmer"), "#ffcc00")
        self.assertEqual(channel_function_color("INTENSITY"), "#ffcc00")  # case-insensitiv
        self.assertEqual(channel_function_color("strobe"),
                         CHANNEL_FUNCTION_COLORS["shutter"])  # gleiche Farbgruppe
        self.assertEqual(channel_function_color("voellig_unbekannt"),
                         _CHANNEL_FUNCTION_DEFAULT)

    def test_abbrev_known_and_fallback(self):
        self.assertEqual(channel_function_abbrev("color_r"), "R")
        self.assertEqual(channel_function_abbrev("intensity"), "Dim")
        self.assertEqual(channel_function_abbrev("pan"), "Pan")
        # Unbekanntes Attribut -> erste Zeichen des Namens.
        self.assertEqual(channel_function_abbrev("xyz", "Strobe Speed"), "Str")
        self.assertEqual(channel_function_abbrev("", ""), "")


class FunctionViewTest(unittest.TestCase):
    def setUp(self):
        self.state = get_state()
        self._orig_patch = self.state._patch_cache
        self._orig_gc = A.get_channels_for_patched
        A.get_channels_for_patched = _rgbw_channels
        self.state._patch_cache = [_F(1, 1, 1, 5, "PAR 1")]

    def tearDown(self):
        self.state._patch_cache = self._orig_patch
        A.get_channels_for_patched = self._orig_gc

    def test_sd01_per_channel_abbrev(self):
        view = SimpleDeskView()
        view._universe = 1
        view._apply_fixture_tints()
        self.assertEqual(view._faders[0]._attr_text, "Dim")   # CH1
        self.assertEqual(view._faders[1]._attr_text, "R")     # CH2
        self.assertEqual(view._faders[2]._attr_text, "G")     # CH3
        self.assertEqual(view._faders[3]._attr_text, "B")     # CH4
        self.assertEqual(view._faders[4]._attr_text, "W")     # CH5
        # Voller Kontext bleibt im Tooltip.
        self.assertIn("Red", view._faders[1].toolTip())

    def test_sd02_default_is_fixture_grouping(self):
        view = SimpleDeskView()
        view._universe = 1
        view._apply_fixture_tints()
        # Default: alle Kanaele desselben Fixtures haben dieselbe (Fixture-)Farbe.
        self.assertEqual(view._faders[0].styleSheet(), view._faders[1].styleSheet())

    def test_sd02_function_mode_colors_per_function(self):
        view = SimpleDeskView()
        view._universe = 1
        view._color_by_function = True
        view._apply_fixture_tints()
        # Dimmer (#ffcc00) und Rot (#ff4444) -> unterschiedliche Fader-Farben.
        self.assertNotEqual(view._faders[0].styleSheet(), view._faders[1].styleSheet())
        # Rot-Kanal traegt die R-Funktionsfarbe (rgba 255,68,68).
        self.assertIn("255,68,68", view._faders[1].styleSheet())

    def test_toggle_handler_reapplies(self):
        view = SimpleDeskView()
        view._universe = 1
        view._apply_fixture_tints()
        grouped = view._faders[1].styleSheet()
        view._on_func_color_toggled(True)
        self.assertTrue(view._color_by_function)
        self.assertNotEqual(view._faders[1].styleSheet(), grouped)

    def test_reset_clears_label(self):
        view = SimpleDeskView()
        view._universe = 1
        view._apply_fixture_tints()
        self.assertEqual(view._faders[0]._attr_text, "Dim")
        self.state._patch_cache = []
        view._apply_fixture_tints()
        self.assertEqual(view._faders[0]._attr_text, "")


if __name__ == "__main__":
    unittest.main()
