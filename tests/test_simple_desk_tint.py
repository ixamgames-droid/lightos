"""SDK-01: Simple Desk färbt die Fader nach Fixture (visuelle Gruppierung)."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import src.core.app_state as A
from src.core.app_state import get_state
from src.ui.views.simple_desk import SimpleDeskView

_app = QApplication.instance() or QApplication([])


class _F:
    def __init__(self, fid, universe, address, channel_count, label):
        self.fid = fid
        self.universe = universe
        self.address = address
        self.channel_count = channel_count
        self.label = label


class FaderTintTest(unittest.TestCase):
    def setUp(self):
        self.state = get_state()
        self._orig_patch = self.state._patch_cache
        self._orig_gc = A.get_channels_for_patched
        A.get_channels_for_patched = lambda fx: []      # Tooltip-Namen egal fuer den Test

    def tearDown(self):
        self.state._patch_cache = self._orig_patch
        A.get_channels_for_patched = self._orig_gc

    def test_tints_grouped_by_fixture(self):
        view = SimpleDeskView()
        view._universe = 1
        # 2 Fixtures je 4 Kanaele: CH 1-4 und CH 5-8 (Universe 1); CH 9+ frei.
        self.state._patch_cache = [
            _F(1, 1, 1, 4, "PAR 1"),
            _F(2, 1, 5, 4, "PAR 2"),
            _F(3, 2, 1, 4, "Other-Universe"),    # anderes Universe -> ignoriert
        ]
        view._apply_fixture_tints()

        # Kanaele 1-8 getintet, ab 9 neutral.
        self.assertNotEqual(view._faders[0].styleSheet(), "")   # CH1
        self.assertNotEqual(view._faders[3].styleSheet(), "")   # CH4
        self.assertNotEqual(view._faders[4].styleSheet(), "")   # CH5
        self.assertNotEqual(view._faders[7].styleSheet(), "")   # CH8
        self.assertEqual(view._faders[8].styleSheet(), "")      # CH9 frei

        # Verschiedene Fixtures -> verschiedene Farbe.
        self.assertNotEqual(view._faders[0].styleSheet(), view._faders[4].styleSheet())
        # Gleiche Fixture -> gleiche Farbe.
        self.assertEqual(view._faders[0].styleSheet(), view._faders[3].styleSheet())

    def test_reset_clears_tint(self):
        view = SimpleDeskView()
        view._universe = 1
        self.state._patch_cache = [_F(1, 1, 1, 2, "X")]
        view._apply_fixture_tints()
        self.assertNotEqual(view._faders[0].styleSheet(), "")
        # Patch leeren -> erneut anwenden -> neutral
        self.state._patch_cache = []
        view._apply_fixture_tints()
        self.assertEqual(view._faders[0].styleSheet(), "")


if __name__ == "__main__":
    unittest.main()
