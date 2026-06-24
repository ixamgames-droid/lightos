"""VIZ-01 + VIZ-04: Visualizer-Aufraeumen der 2D-Live-View-Positionen beim Unpatch
und Spider-Tilt-Default.

Reine Datenlogik ueber Fake-State/Fake-self (SimpleNamespace), genau wie
test_visualizer_state_leaks — KEIN echter Bridge-Konstruktor (der wuerde einen
State-Subscriber leaken, der spaetere Tests kippt).
"""
import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.ui.visualizer.visualizer_window import VisualizerBridge


def _emit_stub():
    return SimpleNamespace(emit=lambda *a: None)


class LiveViewUnpatchPruneTest(unittest.TestCase):
    """VIZ-01: Ein NUR in 2D platziertes Fixture (kein visualizer_positions-
    Eintrag) muss beim Unpatch trotzdem aus live_view_positions verschwinden —
    sonst bleibt es als Leiche gespeichert und wird bei fid-Wiederverwendung
    faelschlich reaktiviert."""

    def test_2d_only_fixture_pruned_from_live_view(self):
        state = SimpleNamespace(
            visualizer_positions={2: (1, 1, 1)},          # fid 3 NICHT enthalten
            visualizer_docks={},
            visualizer_rotations={},
            live_view_positions={2: (20, 20), 3: (30, 30)},
            get_patched_fixtures=lambda: [SimpleNamespace(fid=2)],  # fid 3 weg
        )
        bself = SimpleNamespace(_state=state, fixtureRemoved=_emit_stub())
        bself.remove_fixture_from_scene = (
            lambda fid: VisualizerBridge.remove_fixture_from_scene(bself, fid))
        VisualizerBridge._on_state(bself, "patch_changed", None)
        # fid 3 war NUR in live_view_positions -> trotzdem entfernt (VIZ-01)
        self.assertNotIn(3, state.live_view_positions)
        # noch gepatchtes fid 2 bleibt unangetastet
        self.assertIn(2, state.live_view_positions)
        self.assertIn(2, state.visualizer_positions)

    def test_3d_placed_fixture_still_pruned(self):
        """Regression: der bisherige Pfad (fid in visualizer_positions) raeumt
        weiterhin alle Dicts inkl. live_view_positions ab."""
        state = SimpleNamespace(
            visualizer_positions={1: (0, 0, 0), 2: (1, 1, 1)},
            visualizer_docks={1: "t1"},
            visualizer_rotations={1: 90.0},
            live_view_positions={1: (10, 10), 2: (20, 20)},
            get_patched_fixtures=lambda: [SimpleNamespace(fid=2)],  # fid 1 weg
        )
        bself = SimpleNamespace(_state=state, fixtureRemoved=_emit_stub())
        bself.remove_fixture_from_scene = (
            lambda fid: VisualizerBridge.remove_fixture_from_scene(bself, fid))
        VisualizerBridge._on_state(bself, "patch_changed", None)
        self.assertNotIn(1, state.visualizer_positions)
        self.assertNotIn(1, state.live_view_positions)
        self.assertIn(2, state.live_view_positions)


class SpiderTiltDefaultTest(unittest.TestCase):
    """VIZ-04: _fixture_to_dict sendet fuer Spider 180° als Tilt-Default (statt
    generisch 270°), wenn kein expliziter tilt_range_deg gesetzt ist."""

    def _bself(self, model):
        state = SimpleNamespace(
            visualizer_positions={}, visualizer_rotations={}, visualizer_docks={})
        return SimpleNamespace(_state=state, _viz_model_for=lambda f: model)

    def test_spider_default_tilt_is_180(self):
        f = SimpleNamespace(fid=1, label="Spider", fixture_type="moving_head")
        d = VisualizerBridge._fixture_to_dict(self._bself("spider"), f)
        self.assertEqual(d["tiltRange"], 180)

    def test_non_spider_default_tilt_is_270(self):
        f = SimpleNamespace(fid=1, label="MH", fixture_type="moving_head")
        d = VisualizerBridge._fixture_to_dict(self._bself("moving_head"), f)
        self.assertEqual(d["tiltRange"], 270)

    def test_explicit_tilt_range_respected_for_spider(self):
        f = SimpleNamespace(fid=1, label="Spider", fixture_type="moving_head",
                            tilt_range_deg=240)
        d = VisualizerBridge._fixture_to_dict(self._bself("spider"), f)
        self.assertEqual(d["tiltRange"], 240)


if __name__ == "__main__":
    unittest.main()
