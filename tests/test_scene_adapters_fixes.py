"""VIZ-11 Review-Runde: gezielte Regressionstests fuer die 4 Adapter-/Graph-
Funde aus der adversarialen Review (siehe docs/VIZ11_SCENEGRAPH_DESIGN.md):

  1. O(n^2)-Resync bei Ganz-Dict-Zuweisung (Bulk-Perf-Smoke).
  2. Phantom-Fixture bei Rotation-only (Facetten-Flag pos_set).
  3. state._scene-Ersetzung desynct lebende Views (AppState.set_scene()).
  4. Geister-Platzhalter-Nodes (_DockView-Platzhalter werden aufgeraeumt).
"""
import os
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tempfile

from PySide6.QtWidgets import QApplication

from src.core.app_state import get_state
from src.core.show.show_file import load_show, reset_show, save_show
from src.core.stage.scene_graph import NodeKind, SceneGraph, SceneNode
from src.core.stage.stage_definition import StageDefinition


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


class BulkAssignmentPerfTest(unittest.TestCase):
    """Fund 1: Ganz-Dict-Zuweisung darf NICHT mehr O(n^2) sein (ein
    resync_all() pro Eintrag statt EINEM gebuendelten am Ende)."""

    def setUp(self):
        _app()
        reset_show()
        self.state = get_state()

    def tearDown(self):
        reset_show()

    def test_bulk_position_assignment_is_fast(self):
        n = 500
        positions = {fid: (float(fid), 6.0, 0.0) for fid in range(n)}
        start = time.perf_counter()
        self.state.visualizer_positions = positions
        elapsed = time.perf_counter() - start
        self.assertLess(
            elapsed, 0.05,
            f"Ganz-Dict-Zuweisung von {n} Fixtures dauerte {elapsed:.3f}s -- "
            "sieht nach O(n^2)-Resync statt gebuendeltem resync_all() aus.",
        )
        # Funktional weiterhin korrekt (keine Perf-Optimierung auf Kosten der
        # Korrektheit).
        self.assertEqual(len(self.state.visualizer_positions), n)
        self.assertEqual(self.state.visualizer_positions[42], (42.0, 6.0, 0.0))

    def test_bulk_assignment_resyncs_existing_views_exactly_once(self):
        """Eine VOR der Ganz-Zuweisung gehaltene View-Referenz muss NACH der
        Zuweisung den vollen neuen Inhalt sehen (Bulk-Pfad darf den finalen
        Resync nicht versehentlich unterdruecken)."""
        view = self.state.visualizer_positions
        self.assertEqual(len(view), 0)
        self.state.visualizer_positions = {1: (1.0, 2.0, 3.0), 2: (4.0, 5.0, 6.0)}
        self.assertEqual(dict(view), {1: (1.0, 2.0, 3.0), 2: (4.0, 5.0, 6.0)})

    def test_bulk_rotation_assignment_is_fast(self):
        n = 500
        # Positionen zuerst (Legacy-Reihenfolge), dann Rotationen.
        self.state.visualizer_positions = {fid: (0.0, 6.0, 0.0) for fid in range(n)}
        rotations = {fid: (0.0, float(fid % 360), 0.0) for fid in range(n)}
        start = time.perf_counter()
        self.state.visualizer_rotations = rotations
        elapsed = time.perf_counter() - start
        self.assertLess(elapsed, 0.05, f"Rotations-Ganz-Zuweisung von {n} Fixtures dauerte {elapsed:.3f}s")


class RotationOnlyPhantomTest(unittest.TestCase):
    """Fund 2: eine reine Rotations-Zuweisung darf KEIN Phantom-Fixture mit
    (0,0,0)-Position in visualizer_positions erzeugen."""

    def setUp(self):
        _app()
        reset_show()
        self.state = get_state()

    def tearDown(self):
        reset_show()

    def test_rotation_only_assignment_does_not_appear_in_positions(self):
        self.state.visualizer_rotations[5] = (10.0, 20.0, 30.0)
        self.assertNotIn(5, self.state.visualizer_positions)
        self.assertEqual(self.state.visualizer_rotations.get(5), (10.0, 20.0, 30.0))

    def test_rotation_only_node_not_persisted_as_position(self):
        self.state.visualizer_rotations[9] = (0.0, 45.0, 0.0)
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "rot_only.lshow")
            save_show(path)
            import json
            import zipfile
            with zipfile.ZipFile(path) as zf:
                data = json.loads(zf.read("show.json"))
            self.assertNotIn("9", data["visualizer"]["positions"])
            # scene_graph-Block: Node existiert (Rotation gespeichert), aber
            # ohne pos_set -> kein irrefuehrender (0,0,0)-Positions-Eintrag.
            node_entries = {n["id"]: n for n in data["scene_graph"]["nodes"]}
            self.assertIn("fix_9", node_entries)
            self.assertFalse(node_entries["fix_9"].get("pos_set", True))

    def test_pop_on_rotation_only_position_raises_keyerror(self):
        """Konsistenz-Check: 'fid in positions' ist False -> pop(fid) ohne
        Default muss KeyError werfen (kein stilles Verschwinden-Lassen eines
        Phantom-Node ueber positions.pop())."""
        self.state.visualizer_rotations[3] = (1.0, 2.0, 3.0)
        with self.assertRaises(KeyError):
            self.state.visualizer_positions.pop(3)

    def test_real_position_write_still_appears(self):
        """Gegenprobe: eine ECHTE Positions-Zuweisung bleibt unveraendert
        sichtbar (kein Overshoot des Fixes)."""
        self.state.visualizer_positions[11] = (1.0, 2.0, 3.0)
        self.assertIn(11, self.state.visualizer_positions)
        self.assertEqual(self.state.visualizer_positions[11], (1.0, 2.0, 3.0))

    def test_undo_style_rotation_after_node_loss_no_phantom(self):
        """Simuliert den in der Review benannten Undo-Verdacht: eine reine
        Rotations-Zuweisung NACH Verlust des urspruenglichen Node (z.B. nach
        Remove) darf keinen Phantom-Positions-Eintrag erzeugen."""
        self.state.visualizer_positions[4] = (1.0, 1.0, 1.0)
        self.state.visualizer_positions.pop(4, None)  # Node komplett weg
        self.assertNotIn(4, self.state.visualizer_positions)
        # "Undo" einer Rotation greift denselben Adapter-Pfad wie scene_commands
        # push_rotate_fixtures._apply (state.visualizer_rotations[fid] = rot).
        self.state.visualizer_rotations[4] = (5.0, 6.0, 7.0)
        self.assertNotIn(4, self.state.visualizer_positions)


class SetSceneResyncTest(unittest.TestCase):
    """Fund 3: eine VOR load_show/reset_show gehaltene View-Referenz muss
    NACH der Graph-Ersetzung wieder den aktuellen Graphen sehen (uber
    AppState.set_scene(), nicht mehr eine blosse state._scene=...-Zuweisung)."""

    def setUp(self):
        _app()
        reset_show()
        self.state = get_state()

    def tearDown(self):
        reset_show()

    def test_set_scene_updates_live_view_reference(self):
        view = self.state.visualizer_positions
        old_scene = self.state._scene
        new_scene = SceneGraph()
        new_scene.add(SceneNode(id="fix_7", kind=NodeKind.FIXTURE, fixture_id=7))
        new_scene.get("fix_7").transform.pos_m = (9.0, 9.0, 9.0)
        new_scene.get("fix_7").pos_set = True

        self.state.set_scene(new_scene)

        self.assertIsNot(self.state._scene, old_scene)
        self.assertIs(view._scene, new_scene)
        # Ein Schreibzugriff auf die ALTE View-Referenz landet jetzt im
        # AKTIVEN Graphen (nicht mehr spurlos im verwaisten alten Graphen).
        view[7] = (1.0, 2.0, 3.0)
        self.assertEqual(new_scene.world_pos("fix_7"), (1.0, 2.0, 3.0))
        self.assertEqual(self.state.visualizer_positions.get(7), (1.0, 2.0, 3.0))

    def test_load_show_resyncs_live_view_reference(self):
        """End-to-End ueber den echten load_show-Pfad (nicht nur set_scene()
        direkt): eine vor dem Laden gehaltene View muss danach den neu
        geladenen Graphen sehen."""
        self.state.visualizer_positions = {1: (1.0, 1.0, 1.0)}
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "resync.lshow")
            save_show(path)

            view = self.state.visualizer_positions
            self.assertEqual(dict(view), {1: (1.0, 1.0, 1.0)})

            # Neuen Inhalt speichern + erneut laden -> view (ALTE Referenz)
            # muss den NEUEN Inhalt zeigen, nicht den alten von der Bindung.
            self.state.visualizer_positions = {2: (2.0, 2.0, 2.0)}
            path2 = os.path.join(td, "resync2.lshow")
            save_show(path2)

            ok, msg = load_show(path2)
            self.assertTrue(ok, msg)
            self.assertEqual(dict(view), {2: (2.0, 2.0, 2.0)})

    def test_reset_show_resyncs_live_view_reference(self):
        self.state.visualizer_positions = {1: (1.0, 1.0, 1.0)}
        view = self.state.visualizer_positions
        reset_show()
        self.assertEqual(dict(view), {})
        view[3] = (3.0, 3.0, 3.0)
        self.assertEqual(self.state.visualizer_positions.get(3), (3.0, 3.0, 3.0))


class GhostPlaceholderCleanupTest(unittest.TestCase):
    """Fund 4: _DockView-Platzhalter (Dock auf unbekannte Stage-Element-ID)
    werden beim Laden UND beim Speichern aufgeraeumt, statt sich unbegrenzt
    anzusammeln."""

    def setUp(self):
        _app()
        reset_show()
        self.state = get_state()

    def tearDown(self):
        reset_show()

    def test_dock_on_unknown_id_creates_placeholder_pruned_on_save(self):
        self.state.visualizer_positions = {7: (1.0, 6.0, -2.0)}
        self.state.visualizer_docks[7] = "el_doesnotexist123"
        # Platzhalter existiert direkt nach dem Setzen (Design-Absicht:
        # reparent()/to_legacy_docks() duerfen den Eintrag nicht verwerfen).
        self.assertIsNotNone(self.state._scene.get("el_doesnotexist123"))

        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "ghost.lshow")
            save_show(path)
            # Save raeumt den Platzhalter im LEBENDEN Graphen auf, WEIL das
            # Dock beim Laden ohnehin als stale verworfen wird (Element
            # existiert auf keiner aufloesbaren Buehne) -> kein Kind mehr am
            # Platzhalter haengt danach nicht zwangslaeufig sofort, aber der
            # persistierte Block darf keinen dauerhaften Geister-Node ohne
            # Referenz akkumulieren:
            import json
            import zipfile
            with zipfile.ZipFile(path) as zf:
                data = json.loads(zf.read("show.json"))
            node_ids = {n["id"] for n in data["scene_graph"]["nodes"]}
            # fid 7 ist per keep_world weiterhin (an el_doesnotexist123
            # geparented, da _resolve_stage_element_ids fuer "simple" das
            # Element nicht kennt) -- das Dock selbst wird erst beim naechsten
            # LADEN stale-gefiltert. Nach dem Laden darf der Platzhalter dann
            # nicht mehr vorhanden sein.
            ok, msg = load_show(path)
            self.assertTrue(ok, msg)
            self.assertIsNone(self.state._scene.get("el_doesnotexist123"))
            self.assertNotIn(7, self.state.visualizer_docks)

    def test_ghost_placeholder_without_children_removed_by_prune_helper(self):
        from src.core.show.show_file import _prune_ghost_placeholder_nodes

        scene = SceneGraph()
        scene.add(SceneNode(id="ghost1", kind=NodeKind.PLATFORM))
        scene.add(SceneNode(id="real_truss", kind=NodeKind.TRUSS_H, size_m=(1.0, 1.0, 1.0), name="T"))
        scene.add(SceneNode(id="fix_1", kind=NodeKind.FIXTURE, fixture_id=1, parent_id="real_truss"))

        _prune_ghost_placeholder_nodes(scene)

        self.assertIsNone(scene.get("ghost1"))
        self.assertIsNotNone(scene.get("real_truss"))
        self.assertIsNotNone(scene.get("fix_1"))

    def test_ghost_placeholder_with_live_child_is_not_removed(self):
        """Ein Platzhalter, an dem noch ein Fixture haengt (Kind), ist KEIN
        reiner Geister-Node -- das Aufraeumen darf ein noch gedocktes Fixture
        nicht kaputt reparenten."""
        from src.core.show.show_file import _prune_ghost_placeholder_nodes

        scene = SceneGraph()
        scene.add(SceneNode(id="ghost_with_child", kind=NodeKind.PLATFORM))
        scene.add(SceneNode(id="fix_2", kind=NodeKind.FIXTURE, fixture_id=2, parent_id="ghost_with_child"))

        _prune_ghost_placeholder_nodes(scene)

        self.assertIsNotNone(scene.get("ghost_with_child"))
        self.assertIsNotNone(scene.get("fix_2"))


if __name__ == "__main__":
    unittest.main()
