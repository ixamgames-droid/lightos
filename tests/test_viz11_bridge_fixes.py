"""VIZ-11 Review-Runde: Bridge-/JS-/Undo-Cluster-Fixes.

Deckt drei Befunde aus der adversarialen 4-Linsen-Review + Live-Test ab
(siehe docs/VIZ11_SCENEGRAPH_DESIGN.md fuer die verbindlichen Invarianten):

  1. Stage-Echo-Race (major, LIVE reproduziert): ein stales/partielles
     stageListChanged-Echo darf den autoritativen Loesch-Abgleich in
     ``_on_stage_list_from_js`` (py_ids_to_remove) NICHT auf ein frisch
     angelegtes Buehnen-Element anwenden. Fix: Sequenz-Token
     (``push_stage_definition`` vergibt, JS echot ihn zurueck, ein AELTERER
     Token markiert das Echo als stale -> Loesch-Block wird uebersprungen).
  2. Drag-Dock erzeugt 2-3 separate Undo-Commands statt EINEM: JS buendelt
     das Drag-Ende jetzt zu einem einzigen ``fixtureGestureEnd``-Event
     (Position + optional Rotation + optional Dock), Python pusht dafuer
     GENAU EINEN ``push_transform_and_dock_fixture``-Command.
  3. ``_reloading_stage`` ohne Fallback: bleibt bei ausbleibendem finalen
     Echo (z.B. Renderer-Crash mitten im Reload) dauerhaft True. Fix:
     QTimer.singleShot-Fallback + Reset im renderProcessTerminated-
     Selbstheilungspfad (``_on_render_crash_giveup``).

EISERNE INVARIANTE (docs/VIZ11_SCENEGRAPH_DESIGN.md): VisualizerBridge nutzt
NUR dict-Standard-API auf den 5 Legacy-Feldern -- die Tests hier nutzen daher
denselben ECHTEN-AppState-Ansatz wie test_scene_graph_undo.py/
test_dock_rotation_follow.py (kein SimpleNamespace-Feld-Fake fuer
visualizer_positions/_rotations/_docks noetig, aber die VisualizerWindow-
Methoden werden als SimpleNamespace-Fake unbound aufgerufen, exakt wie in
test_dock_rotation_follow.py::_StageWindowFake)."""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest

import src.ui.visualizer.visualizer_window as VW
from src.core.app_state import get_state
from src.core.show.show_file import reset_show
from src.core.stage.stage_definition import StageDefinition
from src.core.undo import get_undo_stack


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


class _StageWindowFake(SimpleNamespace):
    """Minimal-Fake fuer VisualizerWindow-Methoden (unbound Aufruf), analog
    zu test_dock_rotation_follow.py::_StageWindowFake."""


def _fake_window(state, current_stage, bridge=None):
    fake = _StageWindowFake(
        _state=state,
        _bridge=bridge if bridge is not None else MagicMock(),
        _current_stage=current_stage,
        _selected_stage_id="",
        _stage_tree=MagicMock(),
        _stage_spin_x=MagicMock(), _stage_spin_y=MagicMock(), _stage_spin_z=MagicMock(),
        _stage_spin_w=MagicMock(), _stage_spin_h=MagicMock(), _stage_spin_d=MagicMock(),
        _stage_spin_rot=MagicMock(),
        _suppress_property_signals=False,
        _stage_dirty=False,
        # Keine Selektion -> Properties-Panel-Update-Zweig wird uebersprungen.
        _selected_stage_element=lambda: None,
    )
    fake._sync_stage_node_to_scene = lambda e: VW.VisualizerWindow._sync_stage_node_to_scene(fake, e)
    fake._remove_stage_node_from_scene = lambda eid: VW.VisualizerWindow._remove_stage_node_from_scene(fake, eid)
    fake._push_stage_rotation_to_children = lambda e: VW.VisualizerWindow._push_stage_rotation_to_children(fake, e)
    fake._refresh_stage_tree = lambda: None
    fake._update_status_counts = lambda: None
    return fake


# ============================================================================
# 1) Stage-Echo-Race: Sequenz-Token
# ============================================================================

class StageEchoTokenTest(unittest.TestCase):
    """push_stage_definition() vergibt einen Token, stageListChanged() echot
    ihn zurueck -- ein AELTERER Token (stale Echo) darf den destruktiven
    Loesch-Abgleich in _on_stage_list_from_js NICHT ausloesen."""

    def setUp(self):
        _app()
        reset_show()
        self.state = get_state()
        get_undo_stack().clear()
        self.bridge = VW.VisualizerBridge(self.state)

    def tearDown(self):
        self.bridge.dispose()
        get_undo_stack().clear()

    def test_push_stage_definition_increments_token_and_embeds_it(self):
        captured = {}
        self.bridge.stageLoaded.connect(lambda j: captured.__setitem__("json", j))
        self.assertEqual(self.bridge._stage_reload_token, 0)

        self.bridge.push_stage_definition(StageDefinition(name="A"))
        self.assertEqual(self.bridge._stage_reload_token, 1)
        import json as _json
        payload = _json.loads(captured["json"])
        self.assertEqual(payload["_reloadToken"], 1)

        self.bridge.push_stage_definition(StageDefinition(name="B"))
        self.assertEqual(self.bridge._stage_reload_token, 2)
        payload2 = _json.loads(captured["json"])
        self.assertEqual(payload2["_reloadToken"], 2)

    def test_current_token_echo_is_not_stale(self):
        self.bridge.push_stage_definition(StageDefinition(name="A"))
        received = {}
        self.bridge.pyStageListChanged.connect(
            lambda items, is_stale: received.update(items=items, is_stale=is_stale))
        import json as _json
        self.bridge.stageListChanged(_json.dumps({"objects": [], "_reloadToken": 1}))
        self.assertFalse(received["is_stale"])
        self.assertFalse(self.bridge._reloading_stage)

    def test_stale_token_echo_is_flagged(self):
        # Zwei Reloads kurz hintereinander (z.B. schneller Buehnenwechsel):
        # der erste Token (1) ist beim Eintreffen des zweiten Echos ueberholt.
        self.bridge.push_stage_definition(StageDefinition(name="A"))
        self.bridge.push_stage_definition(StageDefinition(name="B"))
        self.assertEqual(self.bridge._stage_reload_token, 2)

        received = {}
        self.bridge.pyStageListChanged.connect(
            lambda items, is_stale: received.update(items=items, is_stale=is_stale))
        import json as _json
        # Spaet eintreffendes Echo aus dem ERSTEN (ueberholten) Reload.
        self.bridge.stageListChanged(_json.dumps({"objects": [], "_reloadToken": 1}))
        self.assertTrue(received["is_stale"])

    def test_legacy_array_payload_without_token_is_never_stale(self):
        """Rueckwaertskompatibilitaet: stageListChanged("[]") (wie in
        test_dock_rotation_follow.py) traegt KEINEN Token -> immer aktuell."""
        self.bridge.push_stage_definition(StageDefinition(name="A"))
        received = {}
        self.bridge.pyStageListChanged.connect(
            lambda items, is_stale: received.update(items=items, is_stale=is_stale))
        self.bridge.stageListChanged("[]")
        self.assertFalse(received["is_stale"])
        self.assertEqual(received["items"], [])


class StaleEchoDoesNotDeleteFreshElementTest(unittest.TestCase):
    """LIVE-Szenario nachgestellt: Palette-Klick aus 'Ansehen' legt ein neues
    Buehnen-Element an (loest im echten Code einen Stage-Reload aus); trifft
    danach ein STALES Echo ein (Token des VORHERIGEN Reloads, das das neue
    Element noch nicht kennt), darf das Element NICHT aus _current_stage
    entfernt werden."""

    def setUp(self):
        _app()
        reset_show()
        self.state = get_state()
        get_undo_stack().clear()
        self.bridge = VW.VisualizerBridge(self.state)

    def tearDown(self):
        self.bridge.dispose()
        get_undo_stack().clear()

    def test_stale_echo_after_add_does_not_remove_new_element(self):
        stage = StageDefinition(name="T")
        # Reload 1 (z.B. Buehne aktivieren) faengt vor dem Element-Add an.
        self.bridge.push_stage_definition(stage)
        self.assertEqual(self.bridge._stage_reload_token, 1)

        fake = _fake_window(self.state, stage, bridge=self.bridge)

        # Element wird angelegt (wie _add_stage_element) UND ein weiterer
        # Reload wird angestossen (Modus-Wechsel/_apply_stage) -> Token 2.
        el = stage.add("platform", x=0.0, y=0.2, z=0.0, name="Neu")
        fake._sync_stage_node_to_scene(el)
        self.bridge.push_stage_definition(stage)
        self.assertEqual(self.bridge._stage_reload_token, 2)

        received = {}
        self.bridge.pyStageListChanged.connect(
            lambda items, is_stale: received.update(items=items, is_stale=is_stale))

        # STALES Echo trifft ein: Token 1 (aus dem UEBERHOLTEN ersten Reload),
        # Objektliste spiegelt den Stand VOR dem Element-Add (leer).
        import json as _json
        self.bridge.stageListChanged(_json.dumps({"objects": [], "_reloadToken": 1}))
        self.assertTrue(received["is_stale"])

        VW.VisualizerWindow._on_stage_list_from_js(fake, received["items"], received["is_stale"])

        # Das frisch angelegte Element MUSS ueberleben (kein py_ids_to_remove).
        self.assertIsNotNone(stage.get(el.id))
        self.assertEqual(len(stage.elements), 1)

    def test_current_echo_still_removes_elements_deleted_in_js(self):
        """Gegenprobe: ein AKTUELLES (nicht-stales) Echo muss den Loesch-
        Abgleich weiterhin ausfuehren (Regressionsschutz fuer den Normalfall,
        z.B. Element per JS-Hotkey/FAB geloescht)."""
        stage = StageDefinition(name="T")
        el = stage.add("platform", x=0.0, y=0.2, z=0.0, name="Weg")
        fake = _fake_window(self.state, stage, bridge=self.bridge)
        fake._sync_stage_node_to_scene(el)
        self.assertIsNotNone(self.state._scene.get(el.id))

        self.bridge.push_stage_definition(stage)
        self.assertEqual(self.bridge._stage_reload_token, 1)

        received = {}
        self.bridge.pyStageListChanged.connect(
            lambda items, is_stale: received.update(items=items, is_stale=is_stale))
        import json as _json
        # AKTUELLES Echo (Token 1, aktueller Token) mit leerer Liste -> JS hat
        # das Element nicht (mehr).
        self.bridge.stageListChanged(_json.dumps({"objects": [], "_reloadToken": 1}))
        self.assertFalse(received["is_stale"])

        VW.VisualizerWindow._on_stage_list_from_js(fake, received["items"], received["is_stale"])
        self.assertIsNone(stage.get(el.id))


# ============================================================================
# 2) Undo-Gestik-Buendelung: fixtureGestureEnd
# ============================================================================

class GestureBundlingTest(unittest.TestCase):
    """Ein Drag-Ende (Position + Dock, optional Rotation) darf nur GENAU
    EINEN Undo-Command erzeugen -- nicht 2-3 separate."""

    def setUp(self):
        _app()
        reset_show()
        self.state = get_state()
        self.undo = get_undo_stack()
        self.undo.clear()
        self.bridge = VW.VisualizerBridge(self.state)

    def tearDown(self):
        self.bridge.dispose()
        self.undo.clear()

    def test_position_and_dock_change_is_one_command(self):
        self.state.visualizer_positions[1] = (0.0, 6.0, 0.0)
        self.assertEqual(len(self.undo._undo), 0)

        import json as _json
        self.bridge.fixtureGestureEnd(_json.dumps({
            "fid": 1, "x": 3.0, "y": 6.0, "z": -2.0,
            "hasRotation": False,
            "hasDockChange": True, "dock": "el_truss",
        }))

        self.assertEqual(len(self.undo._undo), 1)
        self.assertEqual(self.state.visualizer_positions[1], (3.0, 6.0, -2.0))
        self.assertEqual(self.state.visualizer_docks.get(1), "el_truss")

        # EIN Undo macht Position UND Dock gemeinsam rueckgaengig.
        self.assertTrue(self.undo.undo())
        self.assertEqual(self.state.visualizer_positions[1], (0.0, 6.0, 0.0))
        self.assertNotIn(1, self.state.visualizer_docks)

    def test_position_rotation_and_dock_change_is_one_command_with_rotate_tool(self):
        self.state.visualizer_positions[1] = (0.0, 6.0, 0.0)
        self.state.visualizer_rotations[1] = (0.0, 0.0, 0.0)

        import json as _json
        self.bridge.fixtureGestureEnd(_json.dumps({
            "fid": 1, "x": 1.0, "y": 6.0, "z": 1.0,
            "hasRotation": True, "rx": 0.0, "ry": 45.0, "rz": 0.0,
            "hasDockChange": True, "dock": "el_truss",
        }))

        self.assertEqual(len(self.undo._undo), 1)
        self.assertEqual(self.state.visualizer_rotations[1], (0.0, 45.0, 0.0))
        self.assertEqual(self.state.visualizer_docks.get(1), "el_truss")

        self.assertTrue(self.undo.undo())
        self.assertEqual(self.state.visualizer_positions[1], (0.0, 6.0, 0.0))
        self.assertEqual(self.state.visualizer_rotations.get(1, (0.0, 0.0, 0.0)), (0.0, 0.0, 0.0))
        self.assertNotIn(1, self.state.visualizer_docks)

    def test_position_only_drag_without_dock_or_rotate_tool_is_one_command(self):
        """Freies Ziehen ohne Andocken/Drehen-Werkzeug: nur Position aendert
        sich -- weiterhin genau EIN Command (keine No-Op-Rotation/-Dock
        Nebenwirkungen)."""
        self.state.visualizer_positions[1] = (0.0, 6.0, 0.0)

        import json as _json
        self.bridge.fixtureGestureEnd(_json.dumps({
            "fid": 1, "x": 2.0, "y": 6.0, "z": 0.0,
            "hasRotation": False, "hasDockChange": False, "dock": "",
        }))

        self.assertEqual(len(self.undo._undo), 1)
        self.assertEqual(self.state.visualizer_positions[1], (2.0, 6.0, 0.0))
        self.assertNotIn(1, self.state.visualizer_docks)

    def test_undock_via_gesture_end_is_one_command(self):
        self.state.visualizer_positions[1] = (2.0, 6.0, 0.0)
        self.state.visualizer_docks[1] = "el_truss"

        import json as _json
        self.bridge.fixtureGestureEnd(_json.dumps({
            "fid": 1, "x": 2.0, "y": 6.0, "z": 0.0,
            "hasRotation": False,
            "hasDockChange": True, "dock": "",
        }))

        self.assertEqual(len(self.undo._undo), 1)
        self.assertNotIn(1, self.state.visualizer_docks)
        self.assertTrue(self.undo.undo())
        self.assertEqual(self.state.visualizer_docks.get(1), "el_truss")


# ============================================================================
# 3) Reload-Churn-Guard: Fallback bei ausbleibendem Echo
# ============================================================================

class ReloadGuardFallbackTest(unittest.TestCase):
    """_reloading_stage darf bei ausbleibendem finalen stageListChanged-Echo
    nicht fuer immer haengen bleiben."""

    def setUp(self):
        _app()
        reset_show()
        self.state = get_state()
        get_undo_stack().clear()
        self.bridge = VW.VisualizerBridge(self.state)

    def tearDown(self):
        self.bridge.dispose()
        get_undo_stack().clear()

    def test_timer_fallback_resets_guard_when_echo_never_arrives(self):
        # Sehr kurze Frist fuer den Test (sonst 3s Wartezeit).
        self.bridge._RELOAD_GUARD_FALLBACK_MS = 30
        self.bridge.push_stage_definition(StageDefinition(name="A"))
        self.assertTrue(self.bridge._reloading_stage)

        # Kein finales Echo trifft ein -> Fallback-Timer muss selbst
        # zuruecksetzen, statt fuer immer zu haengen.
        QTest.qWait(150)
        self.assertFalse(self.bridge._reloading_stage)

        # Ein echter Undock ist danach wieder ein normaler User-Vorgang.
        self.state.visualizer_positions[1] = (2.0, 8.0, 0.0)
        self.state.visualizer_docks[1] = "el_truss"
        self.bridge.fixtureDockChanged("1", "")
        self.assertNotIn(1, self.state.visualizer_docks)

    def test_final_echo_cancels_pending_fallback_timer(self):
        self.bridge._RELOAD_GUARD_FALLBACK_MS = 200
        self.bridge.push_stage_definition(StageDefinition(name="A"))
        self.assertIsNotNone(self.bridge._reload_guard_timer)

        self.bridge.stageListChanged("[]")
        self.assertFalse(self.bridge._reloading_stage)
        self.assertIsNone(self.bridge._reload_guard_timer)

    def test_render_crash_giveup_resets_guard_immediately(self):
        """Selbstheilungspfad (renderProcessTerminated -> RenderCrashGuard
        gibt nach 3 Neustarts auf -> _on_render_crash_giveup) muss den Guard
        SOFORT zuruecksetzen, nicht erst nach der Timer-Frist."""
        fake = SimpleNamespace(_bridge=self.bridge, _lbl_info=None)
        self.bridge.push_stage_definition(StageDefinition(name="A"))
        self.assertTrue(self.bridge._reloading_stage)
        self.assertIsNotNone(self.bridge._reload_guard_timer)

        VW.VisualizerWindow._on_render_crash_giveup(fake, "3D-Renderer abgestürzt")

        self.assertFalse(self.bridge._reloading_stage)
        self.assertIsNone(self.bridge._reload_guard_timer)

        self.state.visualizer_positions[1] = (2.0, 8.0, 0.0)
        self.state.visualizer_docks[1] = "el_truss"
        self.bridge.fixtureDockChanged("1", "")
        self.assertNotIn(1, self.state.visualizer_docks)


if __name__ == "__main__":
    unittest.main()
