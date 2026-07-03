"""VIZ-10 Auftrag C: Tests fuer die 6 im Live-UI-Audit gefundenen Bugs.

Bewusst OHNE echte VisualizerWindow (QtWebEngine) - reine Logik ueber
Fake-self (SimpleNamespace) + echte Leichtgewicht-Qt-Widgets, analog
tests/test_visualizer_controls.py und tests/test_visualizer_bauraum_ui.py.

Abgedeckt:
  1) Tab<->Modus-Sync bidirektional (_on_tab_changed / _on_edit_mode_changed),
     ohne Rueckkopplungsschleife (_suppress_tab_mode_sync).
  2) Element-Palette wechselt automatisch in den Bühne-Modus + Statusmeldung.
  3) _update_status_counts() als zentraler Zaehler-Pfad.
  4) Spinbox-Fokus-Guard (_any_focused) verhindert das Ueberschreiben eines
     gerade getippten Werts durch ein JS-Echo.
"""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDoubleSpinBox, QTabWidget, QComboBox, QWidget

import src.ui.visualizer.visualizer_window as VW
from src.ui.visualizer.visualizer_window import _any_focused
from src.core.stage.stage_definition import StageDefinition

_app = QApplication.instance() or QApplication([])


# ============================================================================
# 1) Tab <-> Modus bidirektionale Synchronisation
# ============================================================================

class TabModeSyncTest(unittest.TestCase):
    def _fake(self):
        combo = QComboBox()
        combo.addItem("Ansehen", "view")
        combo.addItem("Fixtures bearbeiten", "edit")
        combo.addItem("Bühne bearbeiten", "stage")
        tabs = QTabWidget()
        tabs.addTab(QWidget(), "Fixtures")
        tabs.addTab(QWidget(), "Bühne")
        tabs.addTab(QWidget(), "Einstellungen")
        fake = SimpleNamespace(
            _combo_edit=combo,
            _tabs=tabs,
            _bridge=MagicMock(),
            _suppress_tab_mode_sync=False,
        )
        return fake

    def test_mode_stage_switches_to_stage_tab(self):
        fake = self._fake()
        VW.VisualizerWindow._on_edit_mode_changed(fake, 2)   # "stage"
        self.assertEqual(fake._tabs.currentIndex(), 1)

    def test_mode_edit_switches_to_fixture_tab(self):
        fake = self._fake()
        VW.VisualizerWindow._on_edit_mode_changed(fake, 1)   # "edit"
        self.assertEqual(fake._tabs.currentIndex(), 0)

    def test_mode_view_does_not_force_settings_tab_away(self):
        # Im "Ansehen"-Modus bleibt der Tab unangetastet - insbesondere darf
        # ein Wechsel in den Einstellungen-Tab (Index 2) NICHT zurueckspringen.
        fake = self._fake()
        fake._tabs.setCurrentIndex(2)
        VW.VisualizerWindow._on_edit_mode_changed(fake, 0)   # "view"
        self.assertEqual(fake._tabs.currentIndex(), 2)

    def test_click_fixtures_tab_sets_edit_mode(self):
        fake = self._fake()
        VW.VisualizerWindow._on_tab_changed(fake, 0)
        self.assertEqual(fake._combo_edit.currentData(), "edit")

    def test_click_stage_tab_sets_stage_mode(self):
        fake = self._fake()
        VW.VisualizerWindow._on_tab_changed(fake, 1)
        self.assertEqual(fake._combo_edit.currentData(), "stage")

    def test_click_settings_tab_leaves_mode_unchanged(self):
        fake = self._fake()
        fake._combo_edit.setCurrentIndex(2)   # "stage" aktiv
        VW.VisualizerWindow._on_tab_changed(fake, 2)   # Einstellungen
        self.assertEqual(fake._combo_edit.currentData(), "stage")

    def test_settings_tab_is_never_disabled(self):
        # Regression fuer den Audit-Befund "Einstellungen-Tab unerreichbar":
        # der Tab selbst darf durch die Sync-Logik nie disabled werden.
        fake = self._fake()
        for idx in (0, 1, 2):
            VW.VisualizerWindow._on_tab_changed(fake, idx)
            self.assertTrue(fake._tabs.isTabEnabled(2))

    def test_no_feedback_loop_reentrancy(self):
        # _on_tab_changed setzt den Combo -> loest _on_edit_mode_changed aus
        # (echtes Signal ueber currentIndexChanged) -> darf NICHT zurueck auf
        # den Tab wirken und eine Endlosschleife/falschen Sprung ausloesen.
        fake = self._fake()
        fake._combo_edit.currentIndexChanged.connect(
            lambda idx: VW.VisualizerWindow._on_edit_mode_changed(fake, idx))
        fake._tabs.setCurrentIndex(1)   # Buehne-Tab per Klick
        VW.VisualizerWindow._on_tab_changed(fake, 1)
        self.assertEqual(fake._tabs.currentIndex(), 1)
        self.assertEqual(fake._combo_edit.currentData(), "stage")
        self.assertFalse(fake._suppress_tab_mode_sync)   # Guard sauber zurueckgesetzt


# ============================================================================
# 2) Element-Palette: Auto-Moduswechsel + Statusmeldung
# ============================================================================

class AddStageElementAutoModeTest(unittest.TestCase):
    def tearDown(self):
        # _add_stage_element pusht seit VIZ-11 (Schritt 6) auf den GLOBALEN
        # UndoStack-Singleton — nicht in nachfolgende Tests durchsickern lassen.
        from src.core.undo import get_undo_stack
        get_undo_stack().clear()

    def _fake(self, cur_mode="view"):
        combo = QComboBox()
        combo.addItem("Ansehen", "view")
        combo.addItem("Fixtures bearbeiten", "edit")
        combo.addItem("Bühne bearbeiten", "stage")
        combo.setCurrentIndex({"view": 0, "edit": 1, "stage": 2}[cur_mode])
        tree = MagicMock()
        tree.topLevelItemCount.return_value = 0
        lbl = MagicMock()
        return SimpleNamespace(
            _state=SimpleNamespace(),
            _current_stage=StageDefinition(),
            _combo_edit=combo,
            _stage_tree=tree,
            _lbl_info=lbl,
            _bridge=MagicMock(),
            _stage_dirty=False,
            _selected_stage_id="",
            STAGE_TYPES=VW.VisualizerWindow.STAGE_TYPES,
            _apply_stage=MagicMock(),
            _sync_stage_node_to_scene=MagicMock(),
            _remove_stage_node_from_scene=MagicMock(),
        )

    def test_switches_from_view_to_stage_mode(self):
        fake = self._fake(cur_mode="view")
        VW.VisualizerWindow._add_stage_element(fake, "truss_h")
        self.assertEqual(fake._combo_edit.currentData(), "stage")

    def test_switches_from_edit_to_stage_mode(self):
        fake = self._fake(cur_mode="edit")
        VW.VisualizerWindow._add_stage_element(fake, "platform")
        self.assertEqual(fake._combo_edit.currentData(), "stage")

    def test_element_actually_added(self):
        fake = self._fake(cur_mode="view")
        VW.VisualizerWindow._add_stage_element(fake, "truss_h")
        self.assertEqual(len(fake._current_stage.elements), 1)
        self.assertEqual(fake._current_stage.elements[0].type, "truss_h")

    def test_status_message_shown(self):
        fake = self._fake(cur_mode="view")
        VW.VisualizerWindow._add_stage_element(fake, "truss_h")
        fake._lbl_info.setText.assert_called_once()
        msg = fake._lbl_info.setText.call_args[0][0]
        self.assertIn("hinzugefügt", msg)
        self.assertIn("Truss", msg)

    def test_dirty_flag_set(self):
        fake = self._fake(cur_mode="view")
        VW.VisualizerWindow._add_stage_element(fake, "platform")
        self.assertTrue(fake._stage_dirty)

    def test_already_in_stage_mode_still_adds_and_reports(self):
        fake = self._fake(cur_mode="stage")
        VW.VisualizerWindow._add_stage_element(fake, "wall")
        self.assertEqual(len(fake._current_stage.elements), 1)
        fake._lbl_info.setText.assert_called_once()


# ============================================================================
# 3) Zentrale Statuszeile
# ============================================================================

class UpdateStatusCountsTest(unittest.TestCase):
    def _fake(self, n_fixtures, n_elements):
        stage = StageDefinition()
        for _ in range(n_elements):
            stage.add("platform")
        lbl = MagicMock()
        return SimpleNamespace(
            _state=SimpleNamespace(visualizer_positions={i: (0, 0, 0) for i in range(n_fixtures)}),
            _current_stage=stage,
            _lbl_info=lbl,
        ), lbl

    def test_counts_reflect_state(self):
        fake, lbl = self._fake(3, 2)
        VW.VisualizerWindow._update_status_counts(fake)
        msg = lbl.setText.call_args[0][0]
        self.assertIn("3 Fixture", msg)
        self.assertIn("2 Bühnen-Elemente", msg)

    def test_zero_elements(self):
        fake, lbl = self._fake(0, 0)
        VW.VisualizerWindow._update_status_counts(fake)
        msg = lbl.setText.call_args[0][0]
        self.assertIn("0 Fixture", msg)
        self.assertIn("0 Bühnen-Elemente", msg)

    def test_apply_stage_refreshes_counts(self):
        # _apply_stage ist der zentrale Pfad fuer Buehnen-Wechsel/-Neuaufbau -
        # muss _update_status_counts triggern (Regression fuer "stale" Zaehler).
        stage = StageDefinition()
        stage.add("platform")
        fake = SimpleNamespace(
            _bridge=MagicMock(),
            _refresh_stage_tree=MagicMock(),
            _lbl_info=MagicMock(),
            _current_stage=stage,
            _state=SimpleNamespace(visualizer_positions={}),
            _update_status_counts=MagicMock(),
        )
        VW.VisualizerWindow._apply_stage(fake, stage)
        fake._update_status_counts.assert_called_once()


# ============================================================================
# 4) Spinbox-Fokus-Guard (_any_focused)
# ============================================================================

class AnyFocusedTest(unittest.TestCase):
    def test_no_widgets_focused(self):
        a, b = QDoubleSpinBox(), QDoubleSpinBox()
        self.assertFalse(_any_focused(a, b))

    def test_one_focused(self):
        a, b = QDoubleSpinBox(), QDoubleSpinBox()
        a.show()
        a.setFocus()
        a.activateWindow()
        QApplication.processEvents()
        # setFocus() ist im Offscreen-Plugin nicht garantiert synchron/global -
        # daher zusaetzlich direkt pruefen, dass hasFocus() ausgewertet wird.
        with patch.object(QDoubleSpinBox, "hasFocus", lambda self: self is a):
            self.assertTrue(_any_focused(a, b))
            self.assertFalse(_any_focused(b))

    def test_none_arg_is_safe(self):
        self.assertFalse(_any_focused(None, None))


class SpinboxFocusGuardIntegrationTest(unittest.TestCase):
    """Regression: JS-Echo (fixturePositionChanged) darf einen Wert nicht
    ueberschreiben, waehrend die Spinbox fokussiert ist (User tippt gerade)."""

    def _fake(self):
        item = MagicMock()
        item.data.return_value = 42
        patch_list = MagicMock()
        patch_list.currentItem.return_value = item
        spins = {}
        for name in ("_spin_x", "_spin_y", "_spin_z",
                     "_spin_rot_x", "_spin_rot_y", "_spin_rot_z"):
            sp = QDoubleSpinBox()
            sp.setRange(-180, 180)   # Standard-Range (0-99) waere zu eng fuer -8/99
            spins[name] = sp
        return SimpleNamespace(
            _patch_list=patch_list,
            _suppress_property_signals=False,
            **spins,
        )

    def test_position_echo_overwrites_when_unfocused(self):
        fake = self._fake()
        fake._spin_x.setValue(1.0)
        VW.VisualizerWindow._on_fixture_moved_from_js(fake, 42, 9.0, 2.0, 3.0)
        self.assertEqual(fake._spin_x.value(), 9.0)

    def test_position_echo_skipped_while_x_focused(self):
        fake = self._fake()
        fake._spin_x.setValue(-8.0)
        with patch.object(QDoubleSpinBox, "hasFocus", lambda self: self is fake._spin_x):
            VW.VisualizerWindow._on_fixture_moved_from_js(fake, 42, 99.0, 99.0, 99.0)
        # Der getippte Wert bleibt erhalten - das Echo wurde verworfen.
        self.assertEqual(fake._spin_x.value(), -8.0)

    def test_rotation_echo_skipped_while_focused(self):
        fake = self._fake()
        fake._spin_rot_y.setValue(45.0)
        with patch.object(QDoubleSpinBox, "hasFocus", lambda self: self is fake._spin_rot_y):
            VW.VisualizerWindow._on_fixture_rotated_from_js(fake, 42, 1.0, 2.0, 3.0)
        self.assertEqual(fake._spin_rot_y.value(), 45.0)

    def test_rotation_echo_applies_when_unfocused(self):
        fake = self._fake()
        VW.VisualizerWindow._on_fixture_rotated_from_js(fake, 42, 11.0, 22.0, 33.0)
        self.assertEqual(fake._spin_rot_x.value(), 11.0)
        self.assertEqual(fake._spin_rot_y.value(), 22.0)
        self.assertEqual(fake._spin_rot_z.value(), 33.0)


if __name__ == "__main__":
    unittest.main()
