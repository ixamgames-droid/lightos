"""Tests fuer Branch fix/visualizer-state-leaks (Audit-Paket 3).

Beim Entfernen/Loeschen von Fixtures muessen ALLE per-fid-Visualizer-Zustaende
zusammen aufgeraeumt werden — sonst bleiben Docks/Rotationen (und beim Unpatch
auch die 2D-Position) verwaist in der Show liegen und werden bei
fid-Wiederverwendung faelschlich erneut angewendet.

Getestet wird die reine Datenlogik ueber Fake-State (SimpleNamespace), genau wie
test_visualizer_autopatch — KEIN echter Bridge-Konstruktor (der wuerde einen
State-Subscriber leaken, der spaetere Tests kippt).
"""
import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.ui.visualizer.visualizer_window import VisualizerBridge


def _emit_stub(sink=None):
    return SimpleNamespace(emit=(lambda *a: sink.append(a[0] if len(a) == 1 else a))
                           if sink is not None else (lambda *a: None))


class RemoveFixtureFromSceneTest(unittest.TestCase):
    def test_pops_positions_docks_and_rotations(self):
        state = SimpleNamespace(
            visualizer_positions={1: (0, 0, 0), 2: (1, 1, 1)},
            visualizer_docks={1: "t1"},
            visualizer_rotations={1: 90.0},
        )
        emitted: list = []
        bself = SimpleNamespace(_state=state, fixtureRemoved=_emit_stub(emitted))
        VisualizerBridge.remove_fixture_from_scene(bself, 1)
        self.assertNotIn(1, state.visualizer_positions)
        self.assertNotIn(1, state.visualizer_docks)
        self.assertNotIn(1, state.visualizer_rotations)
        self.assertEqual(emitted, [1])
        self.assertIn(2, state.visualizer_positions, "andere Fixtures bleiben")


class FixtureDeletedSlotTest(unittest.TestCase):
    def test_js_delete_pops_all_three(self):
        state = SimpleNamespace(
            visualizer_positions={5: (0, 0, 0)},
            visualizer_docks={5: "t"},
            visualizer_rotations={5: 30.0},
        )
        emitted: list = []
        bself = SimpleNamespace(_state=state, pyFixtureDeleted=_emit_stub(emitted))
        VisualizerBridge.fixtureDeleted(bself, "5")
        self.assertNotIn(5, state.visualizer_positions)
        self.assertNotIn(5, state.visualizer_docks)
        self.assertNotIn(5, state.visualizer_rotations)
        self.assertEqual(emitted, [5])


class PatchChangedPruneTest(unittest.TestCase):
    def test_unpatch_prunes_all_visualizer_dicts_and_live_view_pos(self):
        state = SimpleNamespace(
            visualizer_positions={1: (0, 0, 0), 2: (1, 1, 1)},
            visualizer_docks={1: "t1", 2: "t2"},
            visualizer_rotations={1: 90.0, 2: 45.0},
            live_view_positions={1: (10, 10), 2: (20, 20)},
            get_patched_fixtures=lambda: [SimpleNamespace(fid=2)],  # fid 1 weg
        )
        bself = SimpleNamespace(_state=state, fixtureRemoved=_emit_stub())
        bself.remove_fixture_from_scene = (
            lambda fid: VisualizerBridge.remove_fixture_from_scene(bself, fid))
        VisualizerBridge._on_state(bself, "patch_changed", None)
        # fid 1 ist stale -> in JEDEM Dict entfernt
        self.assertNotIn(1, state.visualizer_positions)
        self.assertNotIn(1, state.visualizer_docks)
        self.assertNotIn(1, state.visualizer_rotations)
        self.assertNotIn(1, state.live_view_positions)
        # fid 2 bleibt unangetastet
        self.assertIn(2, state.visualizer_positions)
        self.assertIn(2, state.visualizer_docks)
        self.assertIn(2, state.visualizer_rotations)
        self.assertIn(2, state.live_view_positions)


if __name__ == "__main__":
    unittest.main()
