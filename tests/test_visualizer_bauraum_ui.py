"""Tests fuer Branch fix/bauraum-ui-bugs (Audit-Paket 4).

- Einzeltasten-Shortcuts (V/E/F/S/D) duerfen die Texteingabe in Feldern nicht
  kapern: ``_should_pass_key_to_text`` entscheidet, ob die Taste stattdessen als
  Text ans fokussierte Feld geht.
- ``_on_delete_stage``: Loeschen der AKTIVEN Buehne setzt auf die leere
  Default-Buehne zurueck (Szene + active_stage_name), statt die geloeschte
  Buehne weiter zu rendern; Loeschen einer anderen Buehne haelt die aktive
  Combo-Auswahl; Loesch-Fehler wird gemeldet.

Reine Logik ueber Fake-self / echte Leichtgewicht-Widgets — KEINE echte
VisualizerWindow (die zieht QtWebEngine hoch).
"""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLineEdit, QPushButton, QSpinBox
from PySide6.QtCore import Qt

import src.ui.visualizer.visualizer_window as VW
from src.ui.visualizer.visualizer_window import _should_pass_key_to_text

_app = QApplication.instance() or QApplication([])


class ShortcutGuardTest(unittest.TestCase):
    def test_letter_passes_to_line_edit(self):
        le = QLineEdit()
        self.assertTrue(_should_pass_key_to_text(
            le, Qt.Key.Key_V, Qt.KeyboardModifier.NoModifier))
        self.assertTrue(_should_pass_key_to_text(
            le, Qt.Key.Key_S, Qt.KeyboardModifier.ShiftModifier))

    def test_letter_passes_to_spinbox(self):
        self.assertTrue(_should_pass_key_to_text(
            QSpinBox(), Qt.Key.Key_E, Qt.KeyboardModifier.NoModifier))

    def test_non_shortcut_key_not_guarded(self):
        self.assertFalse(_should_pass_key_to_text(
            QLineEdit(), Qt.Key.Key_A, Qt.KeyboardModifier.NoModifier))

    def test_ctrl_modifier_not_guarded(self):
        # Strg+V (Einfuegen) muss als Shortcut durchgehen, nicht als Text
        self.assertFalse(_should_pass_key_to_text(
            QLineEdit(), Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier))

    def test_non_text_widget_not_guarded(self):
        self.assertFalse(_should_pass_key_to_text(
            QPushButton(), Qt.Key.Key_V, Qt.KeyboardModifier.NoModifier))
        self.assertFalse(_should_pass_key_to_text(
            None, Qt.Key.Key_V, Qt.KeyboardModifier.NoModifier))


class StageSelectionStateTest(unittest.TestCase):
    """Die lokale Auswahl darf nicht auf einer alten JS-Auswahl stehen bleiben."""

    def test_tree_selection_updates_persistent_selected_stage_id(self):
        from src.core.stage.stage_definition import StageElement

        selected = StageElement(
            id="selected-stage", type="truss_h", x=0, y=8, z=0,
            w=8, h=0.3, d=0.3, rotation=0, color="#999999", name="Truss",
        )
        fake = SimpleNamespace(
            _selected_stage_element=lambda: selected,
            _selected_stage_id="stale-stage",
            _suppress_property_signals=False,
            _stage_name_edit=MagicMock(),
            _stage_spin_x=MagicMock(), _stage_spin_y=MagicMock(),
            _stage_spin_z=MagicMock(), _stage_spin_w=MagicMock(),
            _stage_spin_h=MagicMock(), _stage_spin_d=MagicMock(),
            _stage_spin_rot=MagicMock(), _stage_color_preview=MagicMock(),
            _bridge=MagicMock(), _btn_resize_mode=MagicMock(),
        )
        fake._btn_resize_mode.isChecked.return_value = False

        VW.VisualizerWindow._on_stage_tree_selected(fake)

        self.assertEqual(fake._selected_stage_id, "selected-stage")
        fake._bridge.push_select_stage_object.assert_called_once_with("selected-stage")

    def test_partial_stage_echo_cannot_remove_or_reselect_new_element(self):
        """Ein Reload-Echo ist erst mit der kompletten ID-Menge autoritativ."""
        from src.core.stage.stage_definition import StageDefinition

        stage = StageDefinition(name="Test")
        old = stage.add("truss_h", name="Fronttruss")
        new = stage.add("audience", name="Publikum")
        fake = SimpleNamespace(
            _current_stage=stage,
            _pending_stage_ids=frozenset({old.id, new.id}),
            _selected_stage_id=old.id,
            _stage_name_edit=QLineEdit(),
            _stage_spin_x=QSpinBox(), _stage_spin_y=QSpinBox(),
            _stage_spin_z=QSpinBox(), _stage_spin_w=QSpinBox(),
            _stage_spin_h=QSpinBox(), _stage_spin_d=QSpinBox(),
            _stage_spin_rot=QSpinBox(),
        )

        # Das alte Teil-Echo darf weder das neue Element entfernen noch die
        # nachfolgende JS-Selektion auf ein unbekanntes Objekt uebernehmen.
        VW.VisualizerWindow._on_stage_list_from_js(
            fake, [old.to_js_dict()], is_stale=False)
        VW.VisualizerWindow._on_stage_selection_from_js(fake, "stale-stage")

        self.assertEqual({el.id for el in stage.elements}, {old.id, new.id})
        self.assertEqual(fake._selected_stage_id, old.id)
        self.assertEqual(fake._pending_stage_ids, frozenset({old.id, new.id}))

    def test_partial_stage_echo_reasserts_missing_saved_objects(self):
        """Ein Teil-Snapshot repariert die 3D-Szene statt die Bühne zu kürzen."""
        from src.core.stage.stage_definition import StageDefinition

        stage = StageDefinition(name="Mehrteilig")
        floor = stage.add("floor", name="Boden")
        truss = stage.add("truss_h", name="Truss")
        wall = stage.add("led_wall", name="LED")
        bridge = MagicMock()
        fake = SimpleNamespace(
            _current_stage=stage,
            _pending_stage_ids=frozenset({floor.id, truss.id, wall.id}),
            _last_stage_reassert_ids=None,
            _bridge=bridge,
            _selected_stage_id="",
            _stage_name_edit=QLineEdit(),
            _stage_spin_x=QSpinBox(), _stage_spin_y=QSpinBox(),
            _stage_spin_z=QSpinBox(), _stage_spin_w=QSpinBox(),
            _stage_spin_h=QSpinBox(), _stage_spin_d=QSpinBox(),
            _stage_spin_rot=QSpinBox(),
        )

        VW.VisualizerWindow._on_stage_list_from_js(
            fake, [floor.to_js_dict()], is_stale=False)

        self.assertEqual({e.id for e in stage.elements}, {floor.id, truss.id, wall.id})
        self.assertEqual(
            [c.args[0].id for c in bridge.push_add_stage_object_data.call_args_list],
            [truss.id, wall.id],
        )

    def test_reassert_gives_up_after_three_attempts_and_unfreezes_sync(self):
        """Ein dauerhaft nicht baubares JS-Element darf die Session nicht einfrieren.

        Live-Befund 2026-07-11: wirft ein Element-Build auf der GPU-gestressten
        Seite dauerhaft, echo't JS immer dieselbe Teilmenge. Der Early-Return
        blockierte dann Selektion + Positions-Sync für den Rest der Session.
        Nach 3 Nachsende-Versuchen muss der Sync für die baubaren Elemente
        weiterlaufen (Python behält die fehlenden autoritativ im Modell).
        """
        from src.core.stage.stage_definition import StageDefinition

        stage = StageDefinition(name="Zäh")
        floor = stage.add("floor", name="Boden")
        truss = stage.add("truss_h", name="Truss")
        bridge = MagicMock()
        bridge._reloading_stage = False
        fake = SimpleNamespace(
            _current_stage=stage,
            _pending_stage_ids=frozenset({floor.id, truss.id}),
            _last_stage_reassert_ids=None,
            _bridge=bridge,
            _selected_stage_id="",
            _stage_dirty=False,
            _suppress_property_signals=False,
            _sync_stage_node_to_scene=MagicMock(),
            _push_stage_rotation_to_children=MagicMock(),
            _refresh_stage_tree=MagicMock(),
            _update_status_counts=MagicMock(),
            _selected_stage_element=lambda: None,
            _stage_name_edit=QLineEdit(),
            _stage_spin_x=QSpinBox(), _stage_spin_y=QSpinBox(),
            _stage_spin_z=QSpinBox(), _stage_spin_w=QSpinBox(),
            _stage_spin_h=QSpinBox(), _stage_spin_d=QSpinBox(),
            _stage_spin_rot=QSpinBox(),
        )

        echo = [dict(floor.to_js_dict(), position={"x": 9.0, "y": 0.0, "z": 0.0})]
        # Versuche 1-3: identische Teilmenge -> jeweils Nachsenden + Early-Return.
        for _ in range(3):
            VW.VisualizerWindow._on_stage_list_from_js(fake, echo, is_stale=False)
            self.assertEqual({e.id for e in stage.elements}, {floor.id, truss.id})
        self.assertEqual(bridge.push_add_stage_object_data.call_count, 3)
        self.assertEqual(floor.x, 0.0)   # Early-Return: Update noch nicht angewandt

        # Versuch 4: aufgeben -> Gate öffnen, Update der baubaren Elemente läuft.
        VW.VisualizerWindow._on_stage_list_from_js(fake, echo, is_stale=False)
        self.assertIsNone(fake._pending_stage_ids)
        self.assertEqual(floor.x, 9.0)
        # Truss bleibt autoritativ im Modell (kein Löschen durch Teilmenge).
        self.assertEqual({e.id for e in stage.elements}, {floor.id, truss.id})

    def test_stale_echo_cannot_resurrect_unknown_elements(self):
        """Ein überholtes Echo (alter Token) darf keine Elemente wiederbeleben."""
        from src.core.stage.stage_definition import StageDefinition

        stage = StageDefinition(name="Aktuell")
        keep = stage.add("floor", name="Boden")
        ghost = {
            "id": "el_geloescht", "type": "platform", "name": "Zombie",
            "position": {"x": 0, "y": 0, "z": 0},
            "size": {"x": 1, "y": 1, "z": 1}, "rotation": 0, "color": "#123456",
        }
        fake = SimpleNamespace(
            _current_stage=stage,
            _pending_stage_ids=None,
            _last_stage_reassert_ids=None,
            _selected_stage_id="",
            _stage_dirty=False,
            _suppress_property_signals=False,
            _sync_stage_node_to_scene=MagicMock(),
            _push_stage_rotation_to_children=MagicMock(),
            _refresh_stage_tree=MagicMock(),
            _update_status_counts=MagicMock(),
            _selected_stage_element=lambda: None,
            _stage_name_edit=QLineEdit(),
            _stage_spin_x=QSpinBox(), _stage_spin_y=QSpinBox(),
            _stage_spin_z=QSpinBox(), _stage_spin_w=QSpinBox(),
            _stage_spin_h=QSpinBox(), _stage_spin_d=QSpinBox(),
            _stage_spin_rot=QSpinBox(),
        )

        VW.VisualizerWindow._on_stage_list_from_js(
            fake, [keep.to_js_dict(), ghost], is_stale=True)

        self.assertEqual({e.id for e in stage.elements}, {keep.id})

    def test_js_selection_is_ignored_while_a_stage_property_is_edited(self):
        """Ein nachlaufendes 3D-Echo darf die Texteingabe nicht umhängen."""
        focused = QSpinBox()
        focused.show()
        focused.setFocus()
        _app.processEvents()
        fake = SimpleNamespace(
            _selected_stage_id="edited-stage",
            _pending_stage_ids=None,
            _stage_name_edit=QLineEdit(),
            _stage_spin_x=focused,
            _stage_spin_y=QSpinBox(), _stage_spin_z=QSpinBox(),
            _stage_spin_w=QSpinBox(), _stage_spin_h=QSpinBox(),
            _stage_spin_d=QSpinBox(), _stage_spin_rot=QSpinBox(),
        )

        VW.VisualizerWindow._on_stage_selection_from_js(fake, "old-stage")

        self.assertEqual(fake._selected_stage_id, "edited-stage")
        focused.close()


class StageObjectDeletedGuardTest(unittest.TestCase):
    """stageObjectDeleted ist die einzige Modell-Schrumpf-Tür — sie braucht
    dieselben Stale-/Reload-Guards wie der stageListChanged-Reconcile."""

    def _fake(self, stage, bridge, pending=None):
        return SimpleNamespace(
            _current_stage=stage,
            _bridge=bridge,
            _pending_stage_ids=pending,
            _selected_stage_id="",
            _stage_dirty=False,
            _remove_stage_node_from_scene=MagicMock(),
            _refresh_stage_tree=MagicMock(),
            _update_status_counts=MagicMock(),
        )

    def _stage_with_truss(self):
        from src.core.stage.stage_definition import StageDefinition
        stage = StageDefinition(name="Del-Test")
        el = stage.add("truss_h", name="Truss")
        return stage, el

    def test_user_delete_applies(self):
        stage, el = self._stage_with_truss()
        bridge = MagicMock()
        bridge._reloading_stage = False
        bridge._poll_events = []
        fake = self._fake(stage, bridge)

        VW.VisualizerWindow._on_stage_object_deleted_from_js(fake, el.id)

        self.assertEqual(stage.elements, [])
        self.assertTrue(fake._stage_dirty)

    def test_delete_echo_ignored_during_reload(self):
        stage, el = self._stage_with_truss()
        bridge = MagicMock()
        bridge._reloading_stage = True
        bridge._poll_events = []
        fake = self._fake(stage, bridge)

        VW.VisualizerWindow._on_stage_object_deleted_from_js(fake, el.id)

        self.assertEqual([e.id for e in stage.elements], [el.id])

    def test_delete_echo_ignored_for_pending_reload_ids(self):
        stage, el = self._stage_with_truss()
        bridge = MagicMock()
        bridge._reloading_stage = False
        bridge._poll_events = []
        fake = self._fake(stage, bridge, pending=frozenset({el.id}))

        VW.VisualizerWindow._on_stage_object_deleted_from_js(fake, el.id)

        self.assertEqual([e.id for e in stage.elements], [el.id])

    def test_delete_echo_ignored_when_readd_is_queued(self):
        """Undo/Redo-Interleaving: ein überholtes Lösch-Echo darf ein gerade
        wieder angefordertes Element nicht aus dem Modell entfernen."""
        import json as _json
        stage, el = self._stage_with_truss()
        bridge = MagicMock()
        bridge._reloading_stage = False
        bridge._poll_events = [
            {"t": "addStageData", "j": _json.dumps({"id": el.id})},
        ]
        fake = self._fake(stage, bridge)

        VW.VisualizerWindow._on_stage_object_deleted_from_js(fake, el.id)

        self.assertEqual([e.id for e in stage.elements], [el.id])


class DeleteStageTest(unittest.TestCase):
    def _fake(self, active_name, combo_data):
        combo = MagicMock()
        combo.currentData.return_value = combo_data
        name = combo_data[1] if combo_data else ""
        return SimpleNamespace(
            _combo_stage=combo,
            _state=SimpleNamespace(active_stage_name=active_name),
            _current_stage=SimpleNamespace(name=name),
            _selected_stage_id="something",
            _reload_stage_combo=MagicMock(),
            _apply_stage=MagicMock(),
            _refresh_patch_list=MagicMock(),
            _select_stage_in_combo=MagicMock(),
        )

    def test_delete_active_resets_to_empty(self):
        fake = self._fake("MyStage", ("user", "MyStage"))
        with patch.object(VW.QMessageBox, "question",
                          return_value=VW.QMessageBox.StandardButton.Yes), \
             patch.object(VW, "delete_stage", return_value=True):
            VW.VisualizerWindow._on_delete_stage(fake)
        self.assertEqual(fake._state.active_stage_name, "simple")
        self.assertEqual(fake._selected_stage_id, "")
        fake._reload_stage_combo.assert_called_once()
        fake._apply_stage.assert_called_once()
        fake._select_stage_in_combo.assert_called_once_with("default", "simple")

    def test_delete_inactive_keeps_active_selection(self):
        fake = self._fake("OtherStage", ("user", "MyStage"))
        with patch.object(VW.QMessageBox, "question",
                          return_value=VW.QMessageBox.StandardButton.Yes), \
             patch.object(VW, "delete_stage", return_value=True):
            VW.VisualizerWindow._on_delete_stage(fake)
        self.assertEqual(fake._state.active_stage_name, "OtherStage")
        fake._apply_stage.assert_not_called()
        fake._select_stage_in_combo.assert_called_once_with("user", "OtherStage")

    def test_delete_failure_warns_and_aborts(self):
        fake = self._fake("MyStage", ("user", "MyStage"))
        with patch.object(VW.QMessageBox, "question",
                          return_value=VW.QMessageBox.StandardButton.Yes), \
             patch.object(VW.QMessageBox, "warning") as warn, \
             patch.object(VW, "delete_stage", return_value=False):
            VW.VisualizerWindow._on_delete_stage(fake)
        warn.assert_called_once()
        fake._reload_stage_combo.assert_not_called()

    def test_delete_non_user_stage_shows_info(self):
        fake = self._fake("simple", ("default", "simple"))
        with patch.object(VW.QMessageBox, "information") as info, \
             patch.object(VW.QMessageBox, "question") as q:
            VW.VisualizerWindow._on_delete_stage(fake)
        info.assert_called_once()
        q.assert_not_called()


if __name__ == "__main__":
    unittest.main()
