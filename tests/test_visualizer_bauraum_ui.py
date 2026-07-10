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
