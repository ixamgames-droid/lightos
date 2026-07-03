"""VIZ-11 Schritt 7: Rotationsvererbung fuer an Buehnen-Elemente gedockte
Fixtures — Python rechnet, JS bleibt flach (Design (d)/Orchestrator-
Entscheidung 7).

Deckt drei Dinge ab, die ueber den reinen SceneGraph-Test
(``test_scene_graph_undo.py::SceneGraphChildPropagationTest``) hinausgehen:
  1. Property-Panel-Aenderung (``_on_stage_property_changed`` ->
     ``_apply_stage_element_props``) rotiert ein Stage-Element mit gedockter
     Fixture -> Welt-Pos orbitiert um den Pivot, ry erbt die Parent-Drehung,
     UND der bestehende ``applyFixtureTransform``-Push-Pfad wird getroffen.
  2. Undock beim Live-View-Drag (Orchestrator-Entscheidung 6, bereits in
     Schritt 6 verdrahtet via ``fixtureDockChanged``/Positions-Schreibpfad)
     bleibt intakt -- reine Regressionsabsicherung im selben Modul.
  3. Reload-Churn-Guard (Design-Risiko "RELOAD-CHURN"): waehrend eines
     Stage-Reloads gesendete ``fixtureDockChanged(fid, '')``-Events (JS
     raeumt beim Buehnenwechsel alte Objekte weg) duerfen NICHT als
     User-Undock durchschlagen; erst das finale ``stageListChanged``-Echo
     hebt den Guard wieder auf.

Nutzt das SimpleNamespace-Fake-Pattern aus test_viz10_ui_repairs.py fuer die
VisualizerWindow-Methoden (kein QWebEngineView noetig) und einen ECHTEN
AppState (wie test_scene_graph_undo.py) fuer die Graph-Adapter.
"""
import math
import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import src.ui.visualizer.visualizer_window as VW
from src.core.app_state import get_state
from src.core.show.show_file import reset_show
from src.core.stage.stage_definition import StageDefinition
from src.core.undo import get_undo_stack


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


class _StageWindowFake(SimpleNamespace):
    """Minimal-Fake fuer die Stage-Property/Sync-Methoden von
    VisualizerWindow (unbound Aufruf: ``VW.VisualizerWindow._method(fake, ...)``)."""


class DockedRotationInheritanceTest(unittest.TestCase):
    """Property-Panel dreht ein Truss-Element -> gedockte Fixture folgt
    (Design (d): world_pos orbitiert um Pivot, world_rot.ry += parent.ry)."""

    def setUp(self):
        _app()
        reset_show()
        self.state = get_state()
        get_undo_stack().clear()

    def tearDown(self):
        get_undo_stack().clear()

    def _fake_window(self, el):
        bridge = MagicMock()
        fake = _StageWindowFake(
            _state=self.state,
            _bridge=bridge,
            _current_stage=self._stage,
            _selected_stage_id=el.id,
            _stage_tree=MagicMock(),
            _stage_name_edit=MagicMock(),
            _stage_spin_x=MagicMock(), _stage_spin_y=MagicMock(), _stage_spin_z=MagicMock(),
            _stage_spin_w=MagicMock(), _stage_spin_h=MagicMock(), _stage_spin_d=MagicMock(),
            _stage_spin_rot=MagicMock(),
            _suppress_property_signals=False,
            _stage_dirty=False,
            _selected_stage_element=lambda: el,
            # Klassenattribut nachbilden (SimpleNamespace hat keinen
            # Klassenattribut-Fallback).
            _STAGE_PROP_KEYS=VW.VisualizerWindow._STAGE_PROP_KEYS,
        )
        # Echte (unbound) Datenlogik-Methoden mit einbinden -- reine
        # Property-Uebernahme/JS-Payload-Bau/Graph-Sync, keine weiteren
        # GUI-Abhaengigkeiten ausser den oben bereits gemockten Widgets.
        fake._stage_element_props = lambda e: VW.VisualizerWindow._stage_element_props(fake, e)
        fake._apply_stage_element_props = lambda e, props: VW.VisualizerWindow._apply_stage_element_props(fake, e, props)
        fake._sync_stage_node_to_scene = lambda e: VW.VisualizerWindow._sync_stage_node_to_scene(fake, e)
        fake._push_stage_rotation_to_children = lambda e: VW.VisualizerWindow._push_stage_rotation_to_children(fake, e)
        return fake

    def _dock_fixture_to(self, fid: int, el_id: str, local_offset=(2.0, 0.0, 0.0)):
        """Legt eine Fixture per Legacy-API an und dockt sie an ``el_id`` an
        (analog zum bestehenden Andock-Fluss: erst Weltposition setzen, dann
        docken -- reparent(keep_world=True) rechnet die lokale Transform)."""
        parent_world = self.state._scene.world_pos(el_id)
        world_pos = (
            parent_world[0] + local_offset[0],
            parent_world[1] + local_offset[1],
            parent_world[2] + local_offset[2],
        )
        self.state.visualizer_positions[fid] = world_pos
        self.state.visualizer_docks[fid] = el_id

    def test_property_panel_rotation_orbits_docked_fixture(self):
        self._stage = StageDefinition(name="T")
        el = self._stage.add("truss_h", x=0.0, y=8.0, z=0.0, w=4.0, h=0.3, d=0.3, name="Truss")
        # Graph-Knoten fuer das Element MUSS existieren, bevor gedockt wird
        # (Andocken haengt an Nodes, nicht an StageElement-Instanzen direkt).
        fake0 = self._fake_window(el)
        VW.VisualizerWindow._sync_stage_node_to_scene(fake0, el)

        self._dock_fixture_to(1, el.id, local_offset=(2.0, 0.0, 0.0))
        self.assertEqual(self.state.visualizer_docks.get(1), el.id)
        self.assertEqual(self.state.visualizer_positions.get(1), (2.0, 8.0, 0.0))

        # Property-Panel: 90 Grad drehen.
        fake = self._fake_window(el)
        fake._stage_name_edit.text.return_value = el.name
        fake._stage_spin_x.value.return_value = el.x
        fake._stage_spin_y.value.return_value = el.y
        fake._stage_spin_z.value.return_value = el.z
        fake._stage_spin_w.value.return_value = el.w
        fake._stage_spin_h.value.return_value = el.h
        fake._stage_spin_d.value.return_value = el.d
        fake._stage_spin_rot.value.return_value = 90.0  # Grad

        VW.VisualizerWindow._on_stage_property_changed(fake)

        self.assertAlmostEqual(el.rotation, math.radians(90.0), places=6)

        # Welt-Pos der Fixture orbitiert um den Truss-Pivot (0,8,0):
        # lokal (2,0,0) bei 90 Grad Parent-Drehung -> Welt-Offset (0,0,2).
        wx, wy, wz = self.state.visualizer_positions[1]
        self.assertAlmostEqual(wx, 0.0, places=5)
        self.assertAlmostEqual(wy, 8.0, places=5)
        self.assertAlmostEqual(wz, 2.0, places=5)

        # Welt-Rotation der Fixture erbt die Parent-Y-Drehung (ry += 90).
        rx, ry, rz = self.state.visualizer_rotations[1]
        self.assertAlmostEqual(ry, 90.0, places=5)

        # Bestehender Push-Pfad wurde getroffen (Kind-Transform an JS).
        fake._bridge.push_apply_fixture_transform.assert_called()
        call_args = fake._bridge.push_apply_fixture_transform.call_args
        fid_arg = call_args[0][0]
        self.assertEqual(fid_arg, 1)

    def test_property_panel_rotation_is_undoable(self):
        self._stage = StageDefinition(name="T")
        el = self._stage.add("truss_h", x=0.0, y=8.0, z=0.0, w=4.0, h=0.3, d=0.3, name="Truss")
        fake0 = self._fake_window(el)
        VW.VisualizerWindow._sync_stage_node_to_scene(fake0, el)
        self._dock_fixture_to(1, el.id, local_offset=(2.0, 0.0, 0.0))

        fake = self._fake_window(el)
        fake._stage_name_edit.text.return_value = el.name
        fake._stage_spin_x.value.return_value = el.x
        fake._stage_spin_y.value.return_value = el.y
        fake._stage_spin_z.value.return_value = el.z
        fake._stage_spin_w.value.return_value = el.w
        fake._stage_spin_h.value.return_value = el.h
        fake._stage_spin_d.value.return_value = el.d
        fake._stage_spin_rot.value.return_value = 90.0

        VW.VisualizerWindow._on_stage_property_changed(fake)
        self.assertAlmostEqual(self.state.visualizer_rotations[1][1], 90.0, places=5)

        self.assertTrue(get_undo_stack().undo())
        self.assertAlmostEqual(el.rotation, 0.0, places=6)
        # Kind-Rotation/-Position wieder am Ausgangswert. (0,0,0)-Rotation
        # gilt als "keine explizite Rotation" und wird per Legacy-Semantik
        # aus visualizer_rotations ausgeblendet, s. scene_adapters.py
        # _SceneBackedDict._snapshot -> .get(...) statt [...].)
        self.assertEqual(self.state.visualizer_rotations.get(1, (0.0, 0.0, 0.0))[1], 0.0)
        wx, wy, wz = self.state.visualizer_positions[1]
        self.assertAlmostEqual(wx, 2.0, places=5)
        self.assertAlmostEqual(wz, 0.0, places=5)


class ReloadChurnGuardTest(unittest.TestCase):
    """fixtureDockChanged('') waehrend eines Stage-Reloads darf keinen echten
    Undock ausloesen (Design-Risiko RELOAD-CHURN)."""

    def setUp(self):
        _app()
        reset_show()
        self.state = get_state()
        get_undo_stack().clear()
        self.bridge = VW.VisualizerBridge(self.state)

    def tearDown(self):
        self.bridge.dispose()
        get_undo_stack().clear()

    def test_dock_change_ignored_while_reloading(self):
        self.state.visualizer_positions[1] = (2.0, 8.0, 0.0)
        self.state.visualizer_docks[1] = "el_truss"
        self.assertEqual(self.state.visualizer_docks.get(1), "el_truss")

        self.bridge._reloading_stage = True
        self.bridge.fixtureDockChanged("1", "")

        # Guard aktiv -> Dock bleibt unveraendert, kein Command gepusht.
        self.assertEqual(self.state.visualizer_docks.get(1), "el_truss")
        self.assertFalse(get_undo_stack().can_undo())

    def test_dock_change_applies_after_guard_cleared_by_final_echo(self):
        self.state.visualizer_positions[1] = (2.0, 8.0, 0.0)
        self.state.visualizer_docks[1] = "el_truss"

        self.bridge._reloading_stage = True
        self.bridge.fixtureDockChanged("1", "")  # unterdrueckt
        self.assertEqual(self.state.visualizer_docks.get(1), "el_truss")

        # Finales JS-Echo nach loadStageJson hebt den Guard auf.
        self.bridge.stageListChanged("[]")
        self.assertFalse(self.bridge._reloading_stage)

        # Jetzt ist ein echter Undock wieder ein normaler User-Vorgang.
        self.bridge.fixtureDockChanged("1", "")
        self.assertNotIn(1, self.state.visualizer_docks)

    def test_dock_change_outside_reload_is_a_real_undock(self):
        self.state.visualizer_positions[1] = (2.0, 8.0, 0.0)
        self.state.visualizer_docks[1] = "el_truss"

        self.bridge.fixtureDockChanged("1", "")

        self.assertNotIn(1, self.state.visualizer_docks)
        self.assertTrue(get_undo_stack().can_undo())

    def test_push_stage_definition_sets_and_relies_on_echo_to_clear_guard(self):
        from src.core.stage.stage_definition import StageDefinition

        self.assertFalse(self.bridge._reloading_stage)
        self.bridge.push_stage_definition(StageDefinition(name="T"))
        self.assertTrue(self.bridge._reloading_stage)

        self.bridge.stageListChanged("[]")
        self.assertFalse(self.bridge._reloading_stage)


if __name__ == "__main__":
    unittest.main()
