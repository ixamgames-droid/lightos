"""VIZ-10 (Phase 0 Sofortpaket): Tests fuer die Stabilitaets-Bausteine.

Deckt die reine, Qt-freie bzw. leicht mockbare Logik ab (siehe
test_visualizer_controls.py fuer das etablierte Fake-Pattern — echte
VisualizerWindow/QWebEngineView werden bewusst NICHT instanziiert):

  1. ``_bridge_slot_guard``: Fehler in einem Bridge-Slot wird geloggt (nicht nur
     print), NICHT weitergereicht (Bridge/App darf nicht crashen), und
     wiederholte identische Fehler werden gedrosselt (STAB-01-Dedup).
  2. ``RenderCrashGuard``: reine Absturz-Schleifen-Logik (max. N Neustarts in
     einem gleitenden Zeitfenster).
  3. Dirty-Flag-Uebergaenge (Element hinzugefuegt/geloescht/geaendert -> dirty,
     nach erfolgreichem Speichern -> sauber) + closeEvent-Entscheidungslogik
     (QMessageBox gemockt, wie in test_visualizer_controls.py).
"""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import src.ui.visualizer.visualizer_window as VW

_app = QApplication.instance() or QApplication([])


# ============================================================================
# 1) _bridge_slot_guard
# ============================================================================

class BridgeSlotGuardTest(unittest.TestCase):
    def setUp(self):
        # Dedup-State ist modulglobal -> zwischen Tests isolieren, sonst
        # beeinflusst der Timing-Drossel-Test aus einem frueheren Testlauf
        # den naechsten (gleiche Signatur "context:ValueError@...").
        VW._viz_log_dedup = VW._cl.ExceptionDedup(min_interval=5.0)

    def test_exception_is_swallowed_not_propagated(self):
        @VW._bridge_slot_guard
        def boom(self_):
            raise ValueError("kaputt")

        # Darf NICHT nach aussen werfen -> Bridge/App bleibt am Leben.
        result = boom(MagicMock())
        self.assertIsNone(result)

    def test_success_path_returns_value_unchanged(self):
        @VW._bridge_slot_guard
        def ok(self_, x):
            return x * 2

        self.assertEqual(ok(MagicMock(), 21), 42)

    def test_exception_is_logged_via_crash_log(self):
        @VW._bridge_slot_guard
        def boom(self_):
            raise RuntimeError("diagnostizierbar")

        with patch.object(VW, "log_bridge_exception") as log_mock:
            boom(MagicMock())
            log_mock.assert_called_once()
            ctx, exc = log_mock.call_args[0]
            self.assertEqual(ctx, "boom")
            self.assertIsInstance(exc, RuntimeError)

    def test_repeated_identical_errors_are_throttled(self):
        """STAB-01-Dedup: derselbe Fehler an derselben Stelle darf das
        crash.log nicht mit Volltext-Tracebacks fluten."""
        writes = []
        with patch.object(VW, "_viz_log_write", side_effect=writes.append), \
             patch("time.monotonic", side_effect=[0.0, 0.1, 0.2, 0.3]):
            for _ in range(4):
                try:
                    raise ValueError("sturm")
                except ValueError as e:
                    VW.log_bridge_exception("sameSlot", e)
        # Erster Aufruf schreibt den Volltext, die naechsten 3 (< 5s Fenster)
        # werden gedrosselt -> nur EIN Traceback-Write in kurzer Folge.
        full_tracebacks = [w for w in writes if "Python Exception" in w]
        self.assertEqual(len(full_tracebacks), 1)

    def test_throttle_resets_after_min_interval(self):
        writes = []
        with patch.object(VW, "_viz_log_write", side_effect=writes.append), \
             patch("time.monotonic", side_effect=[0.0, 10.0]):
            for _ in range(2):
                try:
                    raise ValueError("sturm2")
                except ValueError as e:
                    VW.log_bridge_exception("otherSlot", e)
        full_tracebacks = [w for w in writes if "Python Exception" in w]
        self.assertEqual(len(full_tracebacks), 2)

    def test_wrapper_preserves_function_name(self):
        @VW._bridge_slot_guard
        def myNamedSlot(self_):
            pass

        self.assertEqual(myNamedSlot.__name__, "myNamedSlot")


# ============================================================================
# 2) RenderCrashGuard (Crash-Schleifen-Schutz)
# ============================================================================

class RenderCrashGuardTest(unittest.TestCase):
    def test_allows_up_to_max_restarts_within_window(self):
        guard = VW.RenderCrashGuard(max_restarts=3, window_s=60.0)
        self.assertTrue(guard.should_restart(0.0))
        self.assertTrue(guard.should_restart(1.0))
        self.assertTrue(guard.should_restart(2.0))

    def test_denies_after_max_restarts_within_window(self):
        guard = VW.RenderCrashGuard(max_restarts=3, window_s=60.0)
        for t in (0.0, 1.0, 2.0):
            self.assertTrue(guard.should_restart(t))
        # 4. Absturz im selben Fenster -> aufgeben.
        self.assertFalse(guard.should_restart(3.0))

    def test_old_crashes_fall_out_of_sliding_window(self):
        guard = VW.RenderCrashGuard(max_restarts=3, window_s=60.0)
        for t in (0.0, 1.0, 2.0):
            guard.should_restart(t)
        # Weit ausserhalb des 60s-Fensters -> die alten 3 zaehlen nicht mehr.
        self.assertTrue(guard.should_restart(100.0))

    def test_reset_clears_history(self):
        guard = VW.RenderCrashGuard(max_restarts=3, window_s=60.0)
        for t in (0.0, 1.0, 2.0):
            guard.should_restart(t)
        guard.reset()
        # Direkt danach wieder voller Kontingent, selbst innerhalb des Fensters.
        self.assertTrue(guard.should_restart(2.5))
        self.assertTrue(guard.should_restart(2.6))
        self.assertTrue(guard.should_restart(2.7))
        self.assertFalse(guard.should_restart(2.8))

    def test_install_render_crash_guard_wires_signal_and_reloads(self):
        """install_render_crash_guard verbindet renderProcessTerminated;
        beim Ausloesen wird (innerhalb des Kontingents) neu geladen."""
        page = MagicMock()
        view = MagicMock()
        view.page.return_value = page

        with patch.object(VW, "load_stage_html") as load_mock:
            guard = VW.install_render_crash_guard(view)
            page.renderProcessTerminated.connect.assert_called_once()
            handler = page.renderProcessTerminated.connect.call_args[0][0]
            status = SimpleNamespace(name="CrashedTerminationStatus")
            handler(status, -1)
            load_mock.assert_called_once_with(view)

    def test_install_render_crash_guard_gives_up_after_limit(self):
        page = MagicMock()
        view = MagicMock()
        view.page.return_value = page
        status_cb = MagicMock()

        # install_render_crash_guard loggt JEDEN Absturz zusaetzlich ueber
        # log_bridge_exception (das selbst intern time.monotonic() fuer die
        # Dedup-Drossel braucht) -> log_bridge_exception mocken, damit hier
        # NUR guard.should_restart()s eigener time.monotonic()-Aufruf zaehlt.
        with patch.object(VW, "load_stage_html"), \
             patch.object(VW, "log_bridge_exception"), \
             patch("time.monotonic", side_effect=[0.0, 1.0, 2.0, 3.0]):
            guard = VW.install_render_crash_guard(view, status_cb=status_cb)
            handler = page.renderProcessTerminated.connect.call_args[0][0]
            status = SimpleNamespace(name="CrashedTerminationStatus")
            for _ in range(4):
                handler(status, -1)
        status_cb.assert_called_once()
        self.assertIn("neu öffnen", status_cb.call_args[0][0])


# ============================================================================
# 3) Dirty-Flag + closeEvent-Entscheidungslogik
# ============================================================================

class DirtyFlagTransitionsTest(unittest.TestCase):
    """Ruft die (ungebundenen) VisualizerWindow-Methoden auf einem leichten
    Fake auf — dasselbe Muster wie test_visualizer_controls.py."""

    def tearDown(self):
        # _add_stage_element/_delete_selected_stage_element pushen seit
        # VIZ-11 (Schritt 6) auf den GLOBALEN UndoStack-Singleton — nicht in
        # nachfolgende Tests im selben Prozess durchsickern lassen.
        from src.core.undo import get_undo_stack
        get_undo_stack().clear()

    def _fake_stage(self, elements=None):
        from src.core.stage.stage_definition import StageDefinition
        stage = StageDefinition(name="Test")
        stage.elements = list(elements or [])
        return stage

    def _fake_window(self, stage_dirty=False):
        # VIZ-11 (Schritt 6): _add_stage_element/_delete_selected_stage_element
        # pushen jetzt einen Undo-Command (scene_commands.push_add_stage_element/
        # push_remove_stage_element) und synchronisieren den SceneGraph-Knoten
        # (self._state._scene) -- der Fake braucht dafuer einen echten
        # (leeren) SceneGraph statt eines reinen MagicMock.
        from src.core.stage.scene_graph import SceneGraph
        stage = self._fake_stage()
        fake_state = SimpleNamespace(_scene=SceneGraph(), _notify_scene_changed=lambda: None)
        fake = SimpleNamespace(
            _state=fake_state,
            _current_stage=stage,
            _stage_dirty=stage_dirty,
            STAGE_TYPES=VW.VisualizerWindow.STAGE_TYPES,
            _combo_edit=MagicMock(),
            _apply_stage=MagicMock(),
            _stage_tree=MagicMock(topLevelItemCount=MagicMock(return_value=0)),
            _bridge=MagicMock(),
            _selected_stage_id="",
            _sync_stage_node_to_scene=MagicMock(),
            _remove_stage_node_from_scene=MagicMock(),
            # Seit b65eb9c/2026-07-11 laufen Add/Delete inkrementell und
            # pflegen Baum + Statuszeile direkt (kein _apply_stage-Reload).
            _refresh_stage_tree=MagicMock(),
            _update_status_counts=MagicMock(),
        )
        fake._combo_edit.currentData.return_value = "stage"
        return fake

    def test_add_stage_element_marks_dirty(self):
        fake = self._fake_window(stage_dirty=False)
        VW.VisualizerWindow._add_stage_element(fake, "platform")
        self.assertTrue(fake._stage_dirty)

    def test_delete_selected_stage_element_marks_dirty(self):
        from src.core.stage.stage_definition import StageElement
        el = StageElement(id="e1", type="platform", x=0, y=0, z=0,
                          w=1, h=1, d=1, rotation=0, color="#fff", name="P")
        fake = self._fake_window(stage_dirty=False)
        fake._current_stage.elements.append(el)
        fake._selected_stage_element = MagicMock(return_value=el)
        VW.VisualizerWindow._delete_selected_stage_element(fake)
        self.assertTrue(fake._stage_dirty)

    def test_delete_with_nothing_selected_stays_clean(self):
        fake = self._fake_window(stage_dirty=False)
        fake._selected_stage_element = MagicMock(return_value=None)
        VW.VisualizerWindow._delete_selected_stage_element(fake)
        self.assertFalse(fake._stage_dirty)

    def test_save_stage_resets_dirty_on_success(self):
        fake = self._fake_window(stage_dirty=True)
        fake._reload_stage_combo = MagicMock()
        fake._select_stage_in_combo = MagicMock()
        fake._state = SimpleNamespace(active_stage_name="")
        with patch.object(VW, "QInputDialog") as dlg, \
             patch.object(VW, "save_stage", return_value="/tmp/x.json"), \
             patch.object(VW, "QMessageBox"):
            dlg.getText.return_value = ("MeineBühne", True)
            VW.VisualizerWindow._on_save_stage(fake)
        self.assertFalse(fake._stage_dirty)

    def test_save_stage_keeps_dirty_when_save_fails(self):
        fake = self._fake_window(stage_dirty=True)
        fake._reload_stage_combo = MagicMock()
        fake._select_stage_in_combo = MagicMock()
        fake._state = SimpleNamespace(active_stage_name="")
        with patch.object(VW, "QInputDialog") as dlg, \
             patch.object(VW, "save_stage", return_value=None), \
             patch.object(VW, "QMessageBox"):
            dlg.getText.return_value = ("MeineBühne", True)
            VW.VisualizerWindow._on_save_stage(fake)
        self.assertTrue(fake._stage_dirty)

    def test_save_stage_cancelled_dialog_keeps_dirty(self):
        fake = self._fake_window(stage_dirty=True)
        with patch.object(VW, "QInputDialog") as dlg:
            dlg.getText.return_value = ("", False)
            VW.VisualizerWindow._on_save_stage(fake)
        self.assertTrue(fake._stage_dirty)


class ConfirmCloseWithUnsavedStageTest(unittest.TestCase):
    def _fake(self, stage_dirty):
        return SimpleNamespace(
            _stage_dirty=stage_dirty,
            _on_save_stage=MagicMock(),
        )

    def test_clean_state_closes_without_dialog(self):
        fake = self._fake(stage_dirty=False)
        with patch.object(VW.QMessageBox, "question") as q:
            result = VW.VisualizerWindow._confirm_close_with_unsaved_stage(fake)
            q.assert_not_called()
        self.assertTrue(result)

    def test_cancel_blocks_close(self):
        fake = self._fake(stage_dirty=True)
        with patch.object(VW.QMessageBox, "question",
                          return_value=VW.QMessageBox.StandardButton.Cancel):
            result = VW.VisualizerWindow._confirm_close_with_unsaved_stage(fake)
        self.assertFalse(result)
        fake._on_save_stage.assert_not_called()

    def test_discard_closes_without_saving(self):
        fake = self._fake(stage_dirty=True)
        with patch.object(VW.QMessageBox, "question",
                          return_value=VW.QMessageBox.StandardButton.Discard):
            result = VW.VisualizerWindow._confirm_close_with_unsaved_stage(fake)
        self.assertTrue(result)
        fake._on_save_stage.assert_not_called()

    def test_save_calls_save_path_and_closes_if_now_clean(self):
        fake = self._fake(stage_dirty=True)

        def _do_save():
            fake._stage_dirty = False   # simuliert erfolgreiches Speichern

        fake._on_save_stage.side_effect = _do_save
        with patch.object(VW.QMessageBox, "question",
                          return_value=VW.QMessageBox.StandardButton.Save):
            result = VW.VisualizerWindow._confirm_close_with_unsaved_stage(fake)
        self.assertTrue(result)
        fake._on_save_stage.assert_called_once()

    def test_save_dialog_aborted_still_dirty_blocks_close(self):
        """User waehlt 'Speichern', bricht aber den Namens-Dialog ab -> dirty
        bleibt True -> Schliessen wird trotzdem abgebrochen (keine stillen
        Datenverluste)."""
        fake = self._fake(stage_dirty=True)
        # _on_save_stage aendert _stage_dirty NICHT (Abbruch im Dialog).
        with patch.object(VW.QMessageBox, "question",
                          return_value=VW.QMessageBox.StandardButton.Save):
            result = VW.VisualizerWindow._confirm_close_with_unsaved_stage(fake)
        self.assertFalse(result)
        fake._on_save_stage.assert_called_once()


class _MinimalVisualizerWindow(VW.VisualizerWindow):
    """VisualizerWindow.closeEvent() ruft ``super().closeEvent(event)`` —
    das braucht ein ECHTES (shiboken-initialisiertes) QMainWindow-Objekt vom
    Typ VisualizerWindow. Diese Subklasse ueberspringt das schwere
    VisualizerWindow.__init__ (QWebEngineView, Toolbars, ...) und ruft nur
    QMainWindow.__init__ — fuer den closeEvent-Reihenfolge-Test reicht das."""

    def __init__(self):
        VW.QMainWindow.__init__(self)


class CloseEventIntegrationTest(unittest.TestCase):
    """closeEvent (VIZ-12 Schritt 4, Dauerfenster): Reihenfolge Abfrage VOR
    ``hide()``. Confirmed close versteckt das Fenster (KEIN Voll-Teardown
    mehr); cancel ignoriert das Event und laesst das Fenster unangetastet."""

    def _fake(self, confirm_result):
        win = _MinimalVisualizerWindow()
        win._confirm_close_with_unsaved_stage = MagicMock(return_value=confirm_result)
        win.hide = MagicMock()
        return win

    def test_confirmed_close_hides_window(self):
        from PySide6.QtGui import QCloseEvent
        win = self._fake(confirm_result=True)
        event = QCloseEvent()
        VW.VisualizerWindow.closeEvent(win, event)
        win.hide.assert_called_once()
        self.assertFalse(event.isAccepted(), "Fenster wird versteckt, nicht destruktiv geschlossen")

    def test_cancelled_close_skips_hide(self):
        from PySide6.QtGui import QCloseEvent
        win = self._fake(confirm_result=False)
        event = QCloseEvent()
        VW.VisualizerWindow.closeEvent(win, event)
        win.hide.assert_not_called()
        self.assertFalse(event.isAccepted())


class MainWindowRespectsVetoTest(unittest.TestCase):
    """Review-Blocker VIZ-10 (Veto-Semantik unveraendert seit VIZ-12 Schritt 4):
    main_window darf ein per Dialog abgebrochenes close() (Rueckgabe False,
    kommt jetzt aus dem Dauerfenster-``closeEvent``s ``event.ignore()``) beim
    ECHTEN App-Ende nicht ignorieren — sonst faehrt die App trotz 'Abbrechen'
    runter und die ungespeicherte Buehne geht still verloren. ``_open_visualizer``
    selbst kennt seit Schritt 4 gar kein Veto mehr (ruft bei existierendem
    Fenster nur noch show()/raise_()/activateWindow(), nie close())."""

    def _fake_viz(self, close_result):
        # Review-Blocker-Fix VIZ-12: MainWindow.closeEvent fragt das Veto jetzt
        # ueber confirm_app_exit() ab (close() liefert beim Dauerfenster IMMER
        # False und taugt nicht mehr als Signal).
        return SimpleNamespace(
            confirm_app_exit=MagicMock(return_value=close_result),
            close=MagicMock(return_value=close_result),
            deleteLater=MagicMock(),
            raise_=MagicMock(),
            activateWindow=MagicMock(),
        )

    def test_open_visualizer_shows_existing_window(self):
        """VIZ-12 Schritt 4 (Dauerfenster): existiert das Fenster bereits,
        wird es NUR noch gezeigt/nach vorn geholt — kein close()/deleteLater()/
        Neubau mehr (Kamera/Modus/Helligkeit bleiben erhalten)."""
        import src.ui.main_window as MW
        viz = SimpleNamespace(
            show=MagicMock(),
            showNormal=MagicMock(),
            isMinimized=MagicMock(return_value=False),
            raise_=MagicMock(),
            activateWindow=MagicMock(),
            deleteLater=MagicMock(),
            close=MagicMock(),
        )
        fake = SimpleNamespace(_visualizer_window=viz)
        MW.MainWindow._open_visualizer(fake)
        viz.show.assert_called_once()
        viz.raise_.assert_called_once()
        viz.activateWindow.assert_called_once()
        viz.close.assert_not_called()
        viz.deleteLater.assert_not_called()
        self.assertIs(fake._visualizer_window, viz)

    def test_open_visualizer_restores_minimized_window(self):
        """Live-Befund VIZ-12: show() restauriert ein MINIMIERTES Fenster
        nicht (Qt-WindowMinimized-State bleibt) -> _open_visualizer muss
        showNormal() nutzen, sonst holt das Menue das Fenster nie zurueck."""
        import src.ui.main_window as MW
        viz = SimpleNamespace(
            show=MagicMock(),
            showNormal=MagicMock(),
            isMinimized=MagicMock(return_value=True),
            raise_=MagicMock(),
            activateWindow=MagicMock(),
            deleteLater=MagicMock(),
            close=MagicMock(),
        )
        fake = SimpleNamespace(_visualizer_window=viz)
        MW.MainWindow._open_visualizer(fake)
        viz.showNormal.assert_called_once()
        viz.show.assert_not_called()
        viz.raise_.assert_called_once()
        viz.activateWindow.assert_called_once()

    def test_main_close_event_ignored_when_visualizer_vetoes(self):
        import src.ui.main_window as MW
        from PySide6.QtGui import QCloseEvent
        viz = self._fake_viz(close_result=False)
        output_manager = SimpleNamespace(stop=MagicMock())
        fake = SimpleNamespace(
            _visualizer_window=viz,
            _state=SimpleNamespace(output_manager=output_manager,
                                   playback_engine=None),
        )
        event = QCloseEvent()
        MW.MainWindow.closeEvent(fake, event)
        self.assertFalse(event.isAccepted())
        output_manager.stop.assert_not_called()
        viz.confirm_app_exit.assert_called_once()
        # Dauerfenster: close() darf im Veto-Pfad NICHT benutzt werden
        # (liefert immer False -> App liesse sich nie beenden).
        viz.close.assert_not_called()


if __name__ == "__main__":
    unittest.main()
