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
    """VIZ-14: aus drei Top-Level-Modi wurden zwei Achsen.

    Die Tests dieser Klasse nagelten bis 2026-08-02 die BIDIREKTIONALE Kopplung
    fest (Tab setzt Modus, Modus setzt Tab, abgesichert durch einen
    Reentrancy-Guard). Nach Davids Entscheidung sind „Fixtures bearbeiten" und
    „Bühne bearbeiten" **Werkzeuge innerhalb eines Bauen-Modus** — der Tab waehlt
    das Werkzeug, der Combo den Modus, und es fliesst nur noch in eine Richtung.

    Die Absichten der alten Tests bleiben erhalten, nur ihre Erwartung wechselt
    von „schreibt zurueck" auf „leitet ab".
    """

    def _fake(self, modus="view", tab=0, werkzeug="edit"):
        combo = QComboBox()
        combo.addItem("Ansehen", "view")
        combo.addItem("Bauen", "build")
        combo.setCurrentIndex({"view": 0, "build": 1}[modus])
        tabs = QTabWidget()
        for name in ("Fixtures", "Bühne", "Einstellungen"):
            tabs.addTab(QWidget(), name)
        tabs.setCurrentIndex(tab)
        fake = SimpleNamespace(
            _combo_edit=combo,
            _tabs=tabs,
            _bridge=MagicMock(),
            _build_tool=werkzeug,
        )
        # Stub-Falle (Second Brain: reference_lightos_trap_stub_state_attributes):
        # ein SimpleNamespace traegt keine Methoden der Klasse. Die zwei, die die
        # Handler intern aufrufen, muessen ausdruecklich angebunden werden.
        fake._apply_edit_state = lambda: VW.VisualizerWindow._apply_edit_state(fake)
        fake._set_build_mode = lambda build=True: VW.VisualizerWindow._set_build_mode(fake, build)
        return fake

    def _modus(self, fake):
        return VW.VisualizerWindow._apply_edit_state(fake)

    def test_modus_fasst_den_tab_nicht_mehr_an(self):
        """Frueher sprang der Tab mit dem Modus mit. Das ist entfallen: der Tab
        gehoert dem Nutzer, der Modus sagt nur, ob etwas anfassbar ist."""
        fake = self._fake(modus="view", tab=2)
        VW.VisualizerWindow._on_edit_mode_changed(fake, 1)   # -> Bauen
        self.assertEqual(fake._tabs.currentIndex(), 2,
                         "der Einstellungen-Tab bleibt offen")

    def test_tabklick_im_ansehen_modus_macht_nichts_anfassbar(self):
        """Die eigentliche Verhaltensaenderung. Vorher setzte ein Klick auf den
        Bühne-Tab den Bearbeitungsmodus — wer nur die Liste sehen wollte, machte
        damit ungewollt alles anfassbar."""
        fake = self._fake(modus="view", tab=1)
        self.assertEqual(self._modus(fake), "view")
        self.assertEqual(fake._combo_edit.currentData(), "view")

    def test_tabklick_im_bauen_modus_waehlt_das_werkzeug(self):
        """Die erhaltene Absicht des alten `click_*_tab_sets_*_mode`."""
        fake = self._fake(modus="build", tab=0)
        self.assertEqual(self._modus(fake), "edit")
        fake._tabs.setCurrentIndex(1)
        self.assertEqual(self._modus(fake), "stage")

    def test_einstellungen_lassen_das_werkzeug_unveraendert(self):
        """Wortgleiche Absicht wie frueher `click_settings_tab_leaves_mode_unchanged`."""
        fake = self._fake(modus="build", tab=1)
        self.assertEqual(self._modus(fake), "stage")
        fake._tabs.setCurrentIndex(2)
        self.assertEqual(self._modus(fake), "stage")

    def test_settings_tab_is_never_disabled(self):
        # Regression fuer den Audit-Befund "Einstellungen-Tab unerreichbar":
        # der Tab selbst darf durch die Modus-Logik nie disabled werden.
        fake = self._fake(modus="build")
        for idx in (0, 1, 2):
            fake._tabs.setCurrentIndex(idx)
            VW.VisualizerWindow._on_tab_changed(fake, idx)
            self.assertTrue(fake._tabs.isTabEnabled(2))

    def test_keine_rueckkopplung_mehr_moeglich(self):
        """Frueher brauchte es einen Reentrancy-Guard, weil Tab und Modus sich
        gegenseitig setzten. Jetzt schreibt keiner der beiden den anderen —
        die Schleife ist strukturell weg, nicht nur abgesichert."""
        fake = self._fake(modus="build", tab=0)
        fake._combo_edit.currentIndexChanged.connect(
            lambda idx: VW.VisualizerWindow._on_edit_mode_changed(fake, idx))
        fake._tabs.currentChanged.connect(
            lambda idx: VW.VisualizerWindow._on_tab_changed(fake, idx))

        fake._tabs.setCurrentIndex(1)          # Nutzer klickt Bühne

        self.assertEqual(fake._tabs.currentIndex(), 1, "der Tab bleibt, wo er ist")
        self.assertEqual(fake._combo_edit.currentData(), "build",
                         "der Modus wurde NICHT umgeschrieben")
        self.assertEqual(fake._bridge.push_edit_mode.call_args[0][0], "stage")


class AddStageElementAutoModeTest(unittest.TestCase):
    def tearDown(self):
        # _add_stage_element pusht seit VIZ-11 (Schritt 6) auf den GLOBALEN
        # UndoStack-Singleton — nicht in nachfolgende Tests durchsickern lassen.
        from src.core.undo import get_undo_stack
        get_undo_stack().clear()

    def _fake(self, cur_mode="view"):
        # VIZ-14: zwei Modi; welches Werkzeug gilt, sagt der Tab.
        combo = QComboBox()
        combo.addItem("Ansehen", "view")
        combo.addItem("Bauen", "build")
        combo.setCurrentIndex(0 if cur_mode == "view" else 1)
        tabs = QTabWidget()
        for name in ("Fixtures", "Bühne", "Einstellungen"):
            tabs.addTab(QWidget(), name)
        tabs.setCurrentIndex(0 if cur_mode in ("view", "edit") else 1)
        tree = MagicMock()
        tree.topLevelItemCount.return_value = 0
        lbl = MagicMock()
        fake = SimpleNamespace(
            _state=SimpleNamespace(),
            _current_stage=StageDefinition(),
            _combo_edit=combo,
            _tabs=tabs,
            _build_tool="edit",
            _stage_tree=tree,
            _lbl_info=lbl,
            _bridge=MagicMock(),
            _stage_dirty=False,
            _selected_stage_id="",
            STAGE_TYPES=VW.VisualizerWindow.STAGE_TYPES,
            _apply_stage=MagicMock(),
            _sync_stage_node_to_scene=MagicMock(),
            _remove_stage_node_from_scene=MagicMock(),
            # Seit b65eb9c/2026-07-11 laufen Add/Delete inkrementell und
            # pflegen Baum + Statuszeile direkt (kein _apply_stage-Reload).
            _refresh_stage_tree=MagicMock(),
            _update_status_counts=MagicMock(),
        )
        fake._apply_edit_state = lambda: VW.VisualizerWindow._apply_edit_state(fake)
        fake._set_build_mode = lambda build=True: VW.VisualizerWindow._set_build_mode(fake, build)
        return fake

    def test_aus_ansehen_wird_bauen_am_buehnen_tab(self):
        """Erhaltene Absicht des alten `switches_from_view_to_stage_mode`: wer
        ein Bühnenelement anlegt, muss es anfassen koennen. Seit VIZ-14 sind das
        ZWEI Achsen — Bauen-Modus UND Bühnen-Tab."""
        fake = self._fake(cur_mode="view")
        VW.VisualizerWindow._add_stage_element(fake, "truss_h")
        self.assertEqual(fake._combo_edit.currentData(), "build")
        self.assertEqual(fake._tabs.currentIndex(), 1)
        self.assertEqual(fake._bridge.push_edit_mode.call_args[0][0], "stage")

    def test_aus_fixtures_bauen_wird_buehne_bauen(self):
        fake = self._fake(cur_mode="edit")
        VW.VisualizerWindow._add_stage_element(fake, "platform")
        self.assertEqual(fake._combo_edit.currentData(), "build")
        self.assertEqual(fake._tabs.currentIndex(), 1)
        self.assertEqual(fake._bridge.push_edit_mode.call_args[0][0], "stage")

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
            # _apply_stage armiert seit 4025631/2026-07-11 zwei Timer auf
            # diese Methoden — im Fake stummschalten.
            _reassert_current_stage_after_load=MagicMock(),
            _clear_stale_pending_stage_ids=MagicMock(),
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
