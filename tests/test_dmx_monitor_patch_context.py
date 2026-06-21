"""U-4 / SD-03: Der DMX-Monitor zeigt pro gepatchter Zelle Geräte-Kürzel +
Kanal-Funktion (Farbe + Kürzel) und einen vollen Tooltip-Text."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPixmap

import src.core.app_state as A
from src.core.app_state import get_state
from src.ui.views.dmx_monitor_view import DmxMonitorView
from src.ui.views.simple_desk import channel_function_color, channel_function_abbrev

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


class DmxMonitorPatchContextTest(unittest.TestCase):
    def setUp(self):
        self.state = get_state()
        self._orig_patch = self.state._patch_cache
        self._orig_gc = A.get_channels_for_patched
        A.get_channels_for_patched = _rgbw_channels
        # Fixture „PAR 1" auf Universe 1, Adresse 1, 5 Kanäle.
        self.state._patch_cache = [_F(1, 1, 1, 5, "PAR 1")]

    def tearDown(self):
        self.state._patch_cache = self._orig_patch
        A.get_channels_for_patched = self._orig_gc

    def test_cell_info_built_per_channel(self):
        view = DmxMonitorView()
        self.addCleanup(view._timer.stop)
        view._refresh_patched()
        info = view._grid._cell_info
        # Adressen 1..5 sind belegt und tragen je (Kürzel, Attribut, Tooltip).
        self.assertEqual(info[1], ("PAR 1", "dimmer", "PAR 1 — Dimmer"))
        self.assertEqual(info[2][1], "color_r")
        self.assertEqual(info[5][1], "color_w")
        # Tooltip enthält Geräte- + Kanal-Name.
        self.assertIn("PAR 1", info[2][2])
        self.assertIn("Red", info[2][2])
        # Patched-Adressen weiterhin korrekt gesetzt (blauer Rahmen).
        self.assertTrue({1, 2, 3, 4, 5}.issubset(view._grid._patched_addrs))
        # Ungepatchte Adresse hat keinen Kontext.
        self.assertNotIn(50, info)

    def test_reuses_simple_desk_helpers(self):
        # Die Funktionsfarbe/-Kürzel kommen aus denselben Simple-Desk-Helfern.
        self.assertEqual(channel_function_abbrev("dimmer"), "Dim")
        self.assertEqual(channel_function_color("color_r"), "#ff4444")

    def test_other_universe_excluded(self):
        view = DmxMonitorView()
        self.addCleanup(view._timer.stop)
        # Fixture liegt auf Universe 1 -> bei Auswahl Universe 2 kein Kontext.
        idx = view._combo_univ.findData(2)
        view._combo_univ.setCurrentIndex(idx)
        view._refresh_patched()
        self.assertEqual(view._grid._cell_info, {})
        self.assertEqual(view._grid._patched_addrs, set())

    def test_paint_runs_without_error(self):
        view = DmxMonitorView()
        self.addCleanup(view._timer.stop)
        view._refresh_patched()
        view._grid.set_values([200] * 512)
        # paintEvent muss mit Patch-Kontext fehlerfrei rendern.
        pm = QPixmap(view._grid.sizeHint())
        view._grid.render(pm)


if __name__ == "__main__":
    unittest.main()
