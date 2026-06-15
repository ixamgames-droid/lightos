"""Auto-Patch Live View -> 3D-Visualizer.

Die Live View ist die Quelle der Top-Down-X/Z. Fixtures, die dort platziert
sind, erscheinen automatisch im 3D (gemeinsame Umrechnung in ``coords``); die
Hoehe (Y) ist 3D-eigen. Eine 3D-Verschiebung schreibt X/Z zurueck in die Live
View. Getestet wird die reine Datenlogik (kein WebView noetig).
"""
import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.stage.coords import (
    live_to_world3d, world3d_to_live, default_height_for, ORIGIN_PX,
)
from src.ui.visualizer.visualizer_window import VisualizerBridge


class CoordsTest(unittest.TestCase):
    def test_roundtrip_px(self):
        for px, py in [(0.0, 0.0), (300.0, 200.0), (517.0, 83.5), (-40.0, 999.0)]:
            x, z = live_to_world3d(px, py)
            rpx, rpy = world3d_to_live(x, z)
            self.assertAlmostEqual(rpx, px, places=6)
            self.assertAlmostEqual(rpy, py, places=6)

    def test_origin_maps_to_world_zero(self):
        self.assertEqual(live_to_world3d(*ORIGIN_PX), (0.0, 0.0))

    def test_default_height(self):
        self.assertEqual(default_height_for("moving_head"), 6.0)
        self.assertEqual(default_height_for("scanner"), 6.0)
        self.assertEqual(default_height_for("par"), 0.6)
        self.assertEqual(default_height_for(None), 0.6)


def _fake_fixture(fid, ftype):
    return SimpleNamespace(fid=fid, fixture_type=ftype)


class SyncFromLiveViewTest(unittest.TestCase):
    """``_sync_positions_from_live_view`` ueber ein Fake-State-Objekt — wir
    brauchen weder Qt-Eventloop noch echten Patch."""

    def _state(self, **kw):
        base = dict(
            live_view_positions={},
            visualizer_positions={},
            get_patched_fixtures=lambda: [],
        )
        base.update(kw)
        return SimpleNamespace(**base)

    def test_seeds_xz_from_live_view_with_type_height(self):
        state = self._state(
            live_view_positions={1: (300.0, 200.0), 2: (340.0, 260.0)},
            get_patched_fixtures=lambda: [
                _fake_fixture(1, "par"), _fake_fixture(2, "moving_head")],
        )
        VisualizerBridge._sync_positions_from_live_view(SimpleNamespace(_state=state))
        # fid1: Origin -> (0,0); par -> y=0.6
        self.assertEqual(state.visualizer_positions[1], (0.0, 0.6, 0.0))
        # fid2: (340-300)/20=2, (260-200)/20=3; moving_head -> y=6.0
        self.assertEqual(state.visualizer_positions[2], (2.0, 6.0, 3.0))

    def test_preserves_existing_3d_height(self):
        state = self._state(
            live_view_positions={1: (340.0, 260.0)},
            visualizer_positions={1: (99.0, 4.2, 99.0)},   # eigene 3D-Hoehe 4.2
            get_patched_fixtures=lambda: [_fake_fixture(1, "moving_head")],
        )
        VisualizerBridge._sync_positions_from_live_view(SimpleNamespace(_state=state))
        # X/Z folgen der Live View, Y (4.2) bleibt erhalten
        self.assertEqual(state.visualizer_positions[1], (2.0, 4.2, 3.0))

    def test_fixture_without_live_view_pos_is_untouched(self):
        state = self._state(
            live_view_positions={},
            get_patched_fixtures=lambda: [_fake_fixture(5, "par")],
        )
        changed = VisualizerBridge._sync_positions_from_live_view(
            SimpleNamespace(_state=state))
        self.assertFalse(changed)
        self.assertNotIn(5, state.visualizer_positions)


class WriteBackTest(unittest.TestCase):
    def test_3d_move_writes_back_to_live_view(self):
        state = SimpleNamespace(live_view_positions={})
        bridge_self = SimpleNamespace(_state=state)
        VisualizerBridge._write_back_to_live_view(bridge_self, 7, 2.0, 3.0)
        self.assertEqual(state.live_view_positions[7], world3d_to_live(2.0, 3.0))
        self.assertEqual(state.live_view_positions[7], (340.0, 260.0))


if __name__ == "__main__":
    unittest.main()
