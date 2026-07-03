"""Undo/Redo fuer Szenegraph-Operationen (VIZ-11, Schritt 6).

Deckt den globalen UndoStack-Command-Katalog aus
``src/core/stage/scene_commands.py`` ab: TransformNode (inkl. Multi-Select
als EIN Command), SetParent (Dock/Undock), AddNode/RemoveNode (Stage-
Element), StageElementProperty, sowie den ``_suspended``-Guard (kein
Doppel-Push waehrend undo()/redo()). Nutzt den ECHTEN AppState (wie
test_patch_undo.py) statt eines Fakes, damit die Adapter-Views
(``_SceneBackedDict``/``_DockView``, siehe scene_adapters.py) real greifen.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.core.app_state import get_state
from src.core.show.show_file import reset_show
from src.core.stage import scene_commands as scmd
from src.core.stage.scene_graph import NodeKind, SceneNode, Transform
from src.core.stage.stage_definition import StageDefinition
from src.core.undo import get_undo_stack


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


class SceneGraphUndoTest(unittest.TestCase):

    def setUp(self):
        _app()
        reset_show()
        self.state = get_state()
        self.undo = get_undo_stack()
        self.undo.clear()  # Singleton ueber Prozess -> pro Test sauber starten

    def tearDown(self):
        self.undo.clear()

    # ── TransformNode (Fixture-Move) ────────────────────────────────────────

    def test_transform_fixture_undo_restores_old_position(self):
        self.state.visualizer_positions[1] = (1.0, 2.0, 3.0)
        old_pos = self.state.visualizer_positions[1]
        new_pos = (5.0, 6.0, 7.0)
        self.state.visualizer_positions[1] = new_pos

        scmd.push_transform_fixtures(self.state, [(1, old_pos, new_pos)])
        self.assertEqual(self.state.visualizer_positions[1], new_pos)

        self.assertTrue(self.undo.undo())
        self.assertEqual(self.state.visualizer_positions[1], old_pos)

        self.assertTrue(self.undo.redo())
        self.assertEqual(self.state.visualizer_positions[1], new_pos)

    def test_transform_multi_select_is_one_command(self):
        self.state.visualizer_positions[1] = (0.0, 6.0, 0.0)
        self.state.visualizer_positions[2] = (1.0, 6.0, 1.0)
        old1, old2 = self.state.visualizer_positions[1], self.state.visualizer_positions[2]
        new1, new2 = (10.0, 6.0, 10.0), (11.0, 6.0, 11.0)
        self.state.visualizer_positions[1] = new1
        self.state.visualizer_positions[2] = new2

        scmd.push_transform_fixtures(
            self.state, [(1, old1, new1), (2, old2, new2)], label="Multi bewegen",
        )
        self.assertEqual(self.undo.undo_label(), "Multi bewegen")

        # EIN undo() stellt BEIDE Fixtures gleichzeitig wieder her.
        self.assertTrue(self.undo.undo())
        self.assertEqual(self.state.visualizer_positions[1], old1)
        self.assertEqual(self.state.visualizer_positions[2], old2)
        # Kein zweites Undo noetig/verfuegbar fuer das zweite Fixture.
        self.assertFalse(self.undo.can_undo())

        self.assertTrue(self.undo.redo())
        self.assertEqual(self.state.visualizer_positions[1], new1)
        self.assertEqual(self.state.visualizer_positions[2], new2)

    def test_transform_noop_does_not_push(self):
        self.state.visualizer_positions[1] = (1.0, 2.0, 3.0)
        same = self.state.visualizer_positions[1]
        scmd.push_transform_fixtures(self.state, [(1, same, same)])
        self.assertFalse(self.undo.can_undo())

    # ── TransformNode (Fixture-Rotate) ──────────────────────────────────────

    def test_rotate_fixture_undo_restores_old_rotation(self):
        # Alt-Rotation bewusst != (0,0,0): der "pos"/"rot"-Adapter blendet
        # (0,0,0) als "keine explizite Rotation" aus dem dict aus (siehe
        # scene_adapters._SceneBackedDict._snapshot) -- (0,0,0) waere hier
        # kein aussagekraeftiger Alt-Zustand fuer den dict-Vergleich.
        self.state.visualizer_positions[1] = (0.0, 6.0, 0.0)
        self.state.visualizer_rotations[1] = (0.0, 10.0, 0.0)
        old_rot = self.state.visualizer_rotations[1]
        new_rot = (0.0, 45.0, 0.0)
        self.state.visualizer_rotations[1] = new_rot

        scmd.push_rotate_fixtures(self.state, [(1, old_rot, new_rot)])
        self.assertTrue(self.undo.undo())
        self.assertEqual(self.state.visualizer_rotations[1], old_rot)
        self.assertTrue(self.undo.redo())
        self.assertEqual(self.state.visualizer_rotations[1], new_rot)

    # ── SetParent (Dock/Undock) ──────────────────────────────────────────────

    def test_dock_undock_is_reversible(self):
        self.state.visualizer_positions[1] = (0.0, 8.0, 0.0)
        # Kein echtes Stage-Element noetig fuer den Adapter-Vertrag: die Dock-
        # View schreibt die sid unabhaengig von der Stage-Existenz durch.
        # push_dock_fixture erwartet (wie alle Commands) den bereits
        # angewendeten neuen Zustand (execute=False, siehe Docstring).
        self.state.visualizer_docks[1] = "el_truss"
        scmd.push_dock_fixture(self.state, 1, None, "el_truss", label="Andocken")
        self.assertEqual(self.state.visualizer_docks.get(1), "el_truss")

        self.assertTrue(self.undo.undo())
        self.assertIsNone(self.state.visualizer_docks.get(1))

        self.assertTrue(self.undo.redo())
        self.assertEqual(self.state.visualizer_docks.get(1), "el_truss")

    def test_undock_reversible(self):
        self.state.visualizer_positions[1] = (0.0, 8.0, 0.0)
        self.state.visualizer_docks[1] = "el_truss"
        self.state.visualizer_docks.pop(1, None)
        scmd.push_dock_fixture(self.state, 1, "el_truss", None, label="Abdocken")
        self.assertIsNone(self.state.visualizer_docks.get(1))

        self.assertTrue(self.undo.undo())
        self.assertEqual(self.state.visualizer_docks.get(1), "el_truss")

    # ── RemoveNode (Fixture-Delete) ──────────────────────────────────────────

    def test_remove_fixture_undo_restores_pos_rot_dock(self):
        self.state.visualizer_positions[1] = (2.0, 6.0, 3.0)
        self.state.visualizer_rotations[1] = (0.0, 90.0, 0.0)
        self.state.visualizer_docks[1] = "el_truss"

        scmd.push_remove_fixture(self.state, 1, label="Fixture löschen")
        # Aufrufer fuehrt die eigentliche Loeschung selbst aus (execute=False).
        self.state.visualizer_positions.pop(1, None)
        self.state.visualizer_docks.pop(1, None)
        self.state.visualizer_rotations.pop(1, None)
        self.assertNotIn(1, self.state.visualizer_positions)

        self.assertTrue(self.undo.undo())
        self.assertEqual(self.state.visualizer_positions[1], (2.0, 6.0, 3.0))
        self.assertEqual(self.state.visualizer_rotations[1], (0.0, 90.0, 0.0))
        self.assertEqual(self.state.visualizer_docks.get(1), "el_truss")

        self.assertTrue(self.undo.redo())
        self.assertNotIn(1, self.state.visualizer_positions)

    # ── AddNode / RemoveNode (Stage-Element) ────────────────────────────────

    def test_add_stage_element_undo_removes_it_again(self):
        stage = StageDefinition(name="T")
        el = stage.add("truss_h", x=0, y=8, z=0, w=4, h=0.3, d=0.3, name="Truss")
        calls = []
        scmd.push_add_stage_element(
            self.state, stage, el, label="Truss hinzufügen",
            on_change=lambda: calls.append(len(stage.elements)),
        )
        self.assertIsNotNone(stage.get(el.id))

        self.assertTrue(self.undo.undo())
        self.assertIsNone(stage.get(el.id))
        self.assertTrue(self.undo.redo())
        self.assertIsNotNone(stage.get(el.id))
        # on_change wurde bei push (do, execute=False -> kein Aufruf), undo,
        # redo aufgerufen -> mindestens 2 Aufrufe (undo + redo).
        self.assertGreaterEqual(len(calls), 2)

    def test_remove_stage_element_undo_restores_it(self):
        stage = StageDefinition(name="T")
        el = stage.add("platform", x=0, y=0.2, z=0, w=6, h=0.4, d=4, name="Bühne")
        scmd.push_remove_stage_element(
            self.state, stage, el, label="Bühne löschen",
            on_change=lambda: None,
        )
        stage.remove(el.id)
        self.assertIsNone(stage.get(el.id))

        self.assertTrue(self.undo.undo())
        restored = stage.get(el.id)
        self.assertIsNotNone(restored)
        self.assertEqual(restored.name, "Bühne")

        self.assertTrue(self.undo.redo())
        self.assertIsNone(stage.get(el.id))

    # ── StageElementProperty ─────────────────────────────────────────────────

    def test_stage_element_property_undo_restores_transform(self):
        stage = StageDefinition(name="T")
        el = stage.add("truss_h", x=0, y=8, z=0, w=4, h=0.3, d=0.3, name="Truss")
        old_props = {"name": el.name, "x": el.x, "y": el.y, "z": el.z,
                     "w": el.w, "h": el.h, "d": el.d, "rotation": el.rotation}

        el.rotation = 1.2
        el.x = 3.0
        new_props = {"name": el.name, "x": el.x, "y": el.y, "z": el.z,
                     "w": el.w, "h": el.h, "d": el.d, "rotation": el.rotation}

        applied = []
        scmd.push_stage_element_property(
            self.state, el, old_props, new_props,
            label="Truss ändern",
            apply_props=lambda props: applied.append(dict(props)),
        )
        self.assertTrue(self.undo.undo())
        self.assertEqual(el.rotation, old_props["rotation"])
        self.assertEqual(el.x, old_props["x"])

        self.assertTrue(self.undo.redo())
        self.assertEqual(el.rotation, new_props["rotation"])
        self.assertEqual(el.x, new_props["x"])
        self.assertTrue(len(applied) >= 2)

    def test_stage_element_property_noop_does_not_push(self):
        stage = StageDefinition(name="T")
        el = stage.add("truss_h", x=0, y=8, z=0, w=4, h=0.3, d=0.3, name="Truss")
        props = {"name": el.name, "x": el.x, "y": el.y, "z": el.z,
                 "w": el.w, "h": el.h, "d": el.d, "rotation": el.rotation}
        scmd.push_stage_element_property(
            self.state, el, props, dict(props),
            apply_props=lambda _p: None,
        )
        self.assertFalse(self.undo.can_undo())

    # ── Kein Doppel-Push waehrend undo()/redo() (_suspended-Guard) ──────────

    def test_no_push_recursion_during_undo(self):
        """apply_props/on_change duerfen selbst KEINEN neuen Command pushen
        (der bestehende _suspended-Guard in UndoStack.push() unterdrueckt
        das automatisch) — der Stack darf nach einem Undo nicht laenger sein
        als vorher."""
        stage = StageDefinition(name="T")
        el = stage.add("truss_h", x=0, y=8, z=0, w=4, h=0.3, d=0.3, name="Truss")
        old_props = {"name": el.name, "x": el.x, "y": el.y, "z": el.z,
                     "w": el.w, "h": el.h, "d": el.d, "rotation": el.rotation}
        el.x = 9.0
        new_props = dict(old_props); new_props["x"] = 9.0

        def _apply(props):
            # Simuliert einen Producer, der versehentlich waehrend do()/undo()
            # selbst erneut pushen wuerde (z.B. ein rekursiver JS-Echo-Pfad).
            scmd.push_stage_element_property(
                self.state, el, old_props, new_props, apply_props=lambda _p: None,
            )

        scmd.push_stage_element_property(
            self.state, el, old_props, new_props, apply_props=_apply,
        )
        self.assertEqual(len(self.undo._undo), 1)
        self.undo.undo()
        # Waehrend des Undo blieb der Stack bei 0 Eintraegen (kein Re-Push),
        # danach liegt das Command im Redo-Stack.
        self.assertEqual(len(self.undo._undo), 0)
        self.assertEqual(len(self.undo._redo), 1)


class SceneGraphChildPropagationTest(unittest.TestCase):
    """descendant_world_transforms (Rotationsvererbung, Design (d)) direkt
    auf dem SceneGraph — unabhaengig von AppState/GUI."""

    def setUp(self):
        _app()

    def test_descendant_world_transform_after_parent_rotation(self):
        from src.core.stage.scene_graph import SceneGraph

        graph = SceneGraph()
        graph.add(SceneNode(
            id="el_truss", kind=NodeKind.TRUSS_H,
            transform=Transform(pos_m=(0.0, 8.0, 0.0), rot_deg=(0.0, 0.0, 0.0)),
        ))
        graph.add(SceneNode(
            id="fix_1", kind=NodeKind.FIXTURE, fixture_id=1,
            transform=Transform(pos_m=(2.0, 0.0, 0.0), rot_deg=(0.0, 0.0, 0.0)),
            parent_id="el_truss",
        ))

        graph.set_transform("el_truss", rot_deg=(0.0, 90.0, 0.0))
        world = graph.descendant_world_transforms("el_truss")
        self.assertIn(1, world)
        wx, wy, wz = world[1].pos_m
        # 90-Grad-Drehung um Y: (2,0,0) lokal -> (0,0,2) Welt-Offset (Design (d)).
        self.assertAlmostEqual(wx, 0.0, places=5)
        self.assertAlmostEqual(wz, 2.0, places=5)
        self.assertAlmostEqual(world[1].rot_deg[1], 90.0, places=5)


if __name__ == "__main__":
    unittest.main()
