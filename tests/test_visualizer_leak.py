"""Regression: der Visualizer leakt keinen State-Subscriber mehr.

Pre-existing Produktions-Leak (siehe entry_visualizer_liveview_stage /
project_spider_visualizer_3d_2026_06_21): ``VisualizerBridge.__init__`` ruft
``self._state.subscribe(self._on_state)``, aber ``AppState`` hatte KEIN
``unsubscribe``. Beim Schliessen des Visualizers wurde die Bridge zwar zerstoert,
ihr gebundener ``_on_state``-Callback blieb aber in ``AppState._callbacks``
haengen — hielt die tote Bridge am Leben und prunte bei jedem ``patch_changed``
weiter ``visualizer_positions``. Jedes erneute Oeffnen addierte einen weiteren
Leak.

Diese Tests weisen nach:
  1. ``AppState.unsubscribe`` entfernt den Callback (defensiv/idempotent).
  2. ``VisualizerBridge.dispose`` haengt sich vollstaendig aus ``_callbacks`` aus;
     wiederholtes Open+Close akkumuliert NICHTS.
  3. Der on_shown/on_hidden-Zyklus (eingebettete ``Visualizer3DView``) ist
     symmetrisch — kein Doppel-Subscribe, kein Rest nach Hide.
  4. ``VisualizerService.shutdown`` (VIZ-12 Schritt 4: der einzige echte
     Teardown-Pfad, App-Ende) meldet ALLE Service-Subscriber ab — ``hide()``/
     ``detach_target`` melden bewusst NICHTS ab (Dauerfenster).

Bewusst ohne QWebEngineView/echtes Fenster — getestet wird die reine
Subscriber-Buchhaltung (wie die uebrigen ``test_visualizer_*``).
"""
import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.core.app_state import get_state
from src.ui.visualizer.visualizer_window import VisualizerBridge, VisualizerWindow
from src.ui.visualizer.visualizer_service import VisualizerService, VisualizerTarget


def _app():
    return QApplication.instance() or QApplication([])


class AppStateUnsubscribeTest(unittest.TestCase):
    def test_unsubscribe_removes_callback(self):
        state = get_state()
        baseline = list(state._callbacks)

        def cb(event, data):
            pass

        state.subscribe(cb)
        self.assertIn(cb, state._callbacks)
        state.unsubscribe(cb)
        self.assertNotIn(cb, state._callbacks)
        self.assertEqual(state._callbacks, baseline)

    def test_unsubscribe_is_defensive(self):
        state = get_state()
        baseline = list(state._callbacks)

        def cb(event, data):
            pass

        # nie subscribed -> darf NICHT werfen
        state.unsubscribe(cb)
        # doppeltes unsubscribe nach einmaligem subscribe -> idempotent
        state.subscribe(cb)
        state.unsubscribe(cb)
        state.unsubscribe(cb)
        self.assertNotIn(cb, state._callbacks)
        self.assertEqual(state._callbacks, baseline)


class BridgeDisposeTest(unittest.TestCase):
    def setUp(self):
        _app()
        self.state = get_state()

    def test_dispose_unsubscribes_bridge(self):
        baseline = list(self.state._callbacks)
        bridge = VisualizerBridge(self.state)
        try:
            # genau EIN Subscriber dazu, und es ist der der Bridge
            self.assertEqual(len(self.state._callbacks), len(baseline) + 1)
            self.assertIn(bridge._on_state, self.state._callbacks)

            bridge.dispose()
            # nach dem Schliessen: KEIN Subscriber mehr -> Baseline wiederhergestellt
            self.assertNotIn(bridge._on_state, self.state._callbacks)
            self.assertEqual(self.state._callbacks, baseline)
        finally:
            bridge.dispose()   # Sicherheitsnetz, falls eine Assertion vorher kippt

    def test_dispose_is_idempotent(self):
        baseline = list(self.state._callbacks)
        bridge = VisualizerBridge(self.state)
        bridge.dispose()
        bridge.dispose()        # zweites dispose -> No-Op, kein Fehler
        self.assertEqual(self.state._callbacks, baseline)

    def test_repeated_open_close_does_not_accumulate(self):
        """Der Kern des Bugs: 'jedes erneute Oeffnen addiert einen weiteren Leak'.
        Nach 5x Open+Close muss die Subscriber-Liste exakt der Baseline gleichen."""
        baseline = list(self.state._callbacks)
        for _ in range(5):
            bridge = VisualizerBridge(self.state)
            self.assertEqual(len(self.state._callbacks), len(baseline) + 1)
            bridge.dispose()
            self.assertEqual(self.state._callbacks, baseline)
        self.assertEqual(self.state._callbacks, baseline)

    def test_shown_hidden_cycle_is_symmetric(self):
        """Spiegelt den on_shown()/on_hidden()-Zyklus der eingebetteten View:
        _activate() (Re-Arm) ist idempotent, dispose() (Hide) entfernt sauber."""
        baseline = list(self.state._callbacks)
        bridge = VisualizerBridge(self.state)        # __init__ -> subscribed
        try:
            bridge._activate()                       # on_shown re-arm -> kein Doppel
            self.assertEqual(len(self.state._callbacks), len(baseline) + 1)

            bridge.dispose()                         # on_hidden
            self.assertEqual(self.state._callbacks, baseline)

            bridge._activate()                       # erneutes on_shown
            self.assertEqual(len(self.state._callbacks), len(baseline) + 1)
            self.assertIn(bridge._on_state, self.state._callbacks)
        finally:
            bridge.dispose()
        self.assertEqual(self.state._callbacks, baseline)


class ServiceShutdownUnsubscribesTest(unittest.TestCase):
    """VIZ-12 Schritt 4: ``VisualizerWindow.closeEvent`` ruft nur noch
    ``hide()`` (Dauerfenster) — es gibt keinen Fenster-seitigen Voll-Teardown
    mehr. Der einzige verbleibende echte Teardown-Pfad ist
    ``VisualizerService.shutdown()`` (App-Ende, s. ``MainWindow.closeEvent``):
    meldet den EINEN Service-Subscriber ab. ``detach_target`` (z.B. via
    ``VisualizerWindow._release_state``, weiterhin als Sicherheitsnetz
    vorhanden) meldet bewusst NICHTS vom Service ab."""

    def setUp(self):
        _app()
        self.state = get_state()

    def test_shutdown_unsubscribes_the_one_service_subscriber(self):
        baseline = list(self.state._callbacks)
        svc = VisualizerService(self.state)
        target = VisualizerTarget("t", lambda s: None)
        svc.attach_target(target)
        self.assertEqual(len(self.state._callbacks), len(baseline) + 1)

        svc.shutdown()
        self.assertEqual(self.state._callbacks, baseline)
        self.assertFalse(svc.timer_running)

    def test_attach_detach_multiple_times_single_subscriber_no_leak(self):
        baseline = list(self.state._callbacks)
        svc = VisualizerService(self.state)
        t1 = VisualizerTarget("t1", lambda s: None)
        t2 = VisualizerTarget("t2", lambda s: None)
        try:
            svc.attach_target(t1)
            svc.attach_target(t2)
            svc.detach_target(t1)
            svc.attach_target(t1)
            self.assertEqual(len(self.state._callbacks), len(baseline) + 1,
                              "genau ein Service-Subscriber, egal wie viele Targets")
        finally:
            svc.shutdown()
        self.assertEqual(self.state._callbacks, baseline)


if __name__ == "__main__":
    unittest.main()
