"""VIZ-LABELS + VIZ-POPOUT (Davids Auftrag 2026-07-18):

  Feature 1 — Label-Toggle: ein Schalter blendet die Fixture-Namens-Sprites
  ("#<fid> <Name>") im 3D-Visualizer ein/aus. Zentrale Quelle ist das AppState-
  Feld ``show_fixture_labels``; alle drei 3D-Ansichten (eingebettete Live-View-
  3D, Pop-out-Fenster, volles VisualizerWindow) lesen es in ihrem
  ``_collect_settings()`` und schreiben es bei ihrem Toggle -> keine Divergenz.

  Feature 2 — Pop-out: die eingebettete 3D-Ansicht laesst sich in ein eigenes,
  frei verschiebbares Fenster (Zweitmonitor) ausklinken. Umgesetzt als zweite
  ``Visualizer3DView``-Instanz (Reuse, kein Neubau) mit eigenem Service-Target
  ``live_view_popout`` in einem schlanken ``VisualizerPopoutWindow``. Beim
  Ausklinken faellt die eingebettete View auf 2D zurueck (GPU-Invariante: nie
  zwei WebGL-Szenen gleichzeitig). Schliessen == Andocken.

Testet die Python-Verdrahtung (die JS-Gating-Logik deckt
``test_viz_labels_js.py`` ab; die Modul-Import-Integritaet von ``labels.js``
deckt ``test_viz13_scene_modules_smoke.py`` ab). Headless via offscreen.
"""
import gc
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.core.app_state import get_state
from src.ui.visualizer.visualizer_service import get_visualizer_service


def _app():
    return QApplication.instance() or QApplication([])


def _pump(seconds=0.15):
    import time
    app = _app()
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.02)


def _dispose_view(view):
    """Symmetrischer Teardown einer echten Visualizer3DView im Test (kein
    Subscriber-/Target-Leak, s. test_visualizer_leak-Falle)."""
    try:
        view.on_hidden()                      # Target inaktiv + bridge.dispose()
    except Exception:
        pass
    try:
        svc = getattr(view, "_service", None)
        tgt = getattr(view, "_target", None)
        if svc is not None and tgt is not None:
            svc.detach_target(tgt)            # explizit (destroyed-Backstop braucht Event-Loop)
    except Exception:
        pass
    try:
        view.deleteLater()
    except Exception:
        pass
    _pump(0.1)


class AppStateLabelFlagTest(unittest.TestCase):
    def test_default_true(self):
        # Frische AppState-Instanz -> Default ist "Labels an" (heutiges Verhalten).
        from src.core.app_state import AppState
        s = AppState()
        self.assertTrue(s.show_fixture_labels)


class Visualizer3DViewLabelToggleTest(unittest.TestCase):
    def setUp(self):
        _app()
        self.state = get_state()
        self._prev = getattr(self.state, "show_fixture_labels", True)
        self.state.show_fixture_labels = True

    def tearDown(self):
        self.state.show_fixture_labels = self._prev

    def test_collect_settings_mirrors_appstate(self):
        from src.ui.visualizer.visualizer_view import Visualizer3DView
        view = Visualizer3DView(None)
        try:
            self.assertTrue(view._collect_settings()["showLabels"])
            self.state.show_fixture_labels = False
            self.assertFalse(view._collect_settings()["showLabels"])
        finally:
            _dispose_view(view)

    def test_button_toggle_writes_appstate(self):
        from src.ui.visualizer.visualizer_view import Visualizer3DView
        view = Visualizer3DView(None)
        try:
            # Button startet gemaess AppState (True) -> Umschalten schreibt AppState.
            self.assertTrue(view._btn_labels.isChecked())
            view._btn_labels.setChecked(False)
            self.assertFalse(self.state.show_fixture_labels)
            self.assertFalse(view._collect_settings()["showLabels"])
            view._btn_labels.setChecked(True)
            self.assertTrue(self.state.show_fixture_labels)
        finally:
            _dispose_view(view)

    def test_button_initial_state_reflects_appstate_off(self):
        # War der Schalter global aus, zeigt eine neu erzeugte View ihn auch aus.
        self.state.show_fixture_labels = False
        from src.ui.visualizer.visualizer_view import Visualizer3DView
        view = Visualizer3DView(None)
        try:
            self.assertFalse(view._btn_labels.isChecked())
        finally:
            _dispose_view(view)

    def test_on_shown_resyncs_button_from_appstate(self):
        """Review-Fix: die View wird bei Pop-out/Redock nur versteckt & wieder-
        verwendet. Wird der globale Schalter waehrend der Versteckt-Phase (z.B.
        im Pop-out/Vollfenster) umgelegt, MUSS on_shown den Button + Settings
        aus AppState nachziehen — sonst geht die Nutzerwahl still verloren."""
        from src.ui.visualizer.visualizer_view import Visualizer3DView
        view = Visualizer3DView(None)
        try:
            self.assertTrue(view._btn_labels.isChecked())
            view.on_hidden()
            # anderswo global ausgeschaltet:
            self.state.show_fixture_labels = False
            view.on_shown()
            self.assertFalse(view._btn_labels.isChecked(),
                             "on_shown zog den Label-Button nicht aus AppState nach")
            self.assertFalse(view._collect_settings()["showLabels"])
        finally:
            _dispose_view(view)


class Visualizer3DViewPopoutButtonTest(unittest.TestCase):
    def setUp(self):
        _app()

    def test_default_no_popout_button_and_mirror_target(self):
        from src.ui.visualizer.visualizer_view import Visualizer3DView
        view = Visualizer3DView(None)
        try:
            self.assertEqual(view._target_name, "live_view_mirror")
            self.assertFalse(hasattr(view, "_btn_popout"))
        finally:
            _dispose_view(view)

    def test_popout_button_present_when_enabled(self):
        from src.ui.visualizer.visualizer_view import Visualizer3DView
        view = Visualizer3DView(None, show_popout_button=True)
        try:
            self.assertTrue(hasattr(view, "_btn_popout"))
            # popOutRequested feuert beim Klick.
            fired = []
            view.popOutRequested.connect(lambda: fired.append(True))
            view._btn_popout.click()
            self.assertTrue(fired)
        finally:
            _dispose_view(view)

    def test_custom_target_name(self):
        from src.ui.visualizer.visualizer_view import Visualizer3DView
        view = Visualizer3DView(None, target_name="live_view_popout")
        try:
            self.assertEqual(view._target_name, "live_view_popout")
            self.assertEqual(view._target.name, "live_view_popout")
        finally:
            _dispose_view(view)


class VisualizerPopoutWindowTest(unittest.TestCase):
    def setUp(self):
        _app()
        self.state = get_state()
        # Service VOR dem Baseline-Snapshot materialisieren, damit sein EINER
        # Dauer-Subscriber in der Baseline steht (er wird beim Close NICHT
        # abgemeldet — nur der Bridge-Subscriber der Kind-View).
        self.svc = get_visualizer_service(self.state)

    def test_child_uses_popout_target_and_no_popout_button(self):
        from src.ui.visualizer.visualizer_view import VisualizerPopoutWindow
        win = VisualizerPopoutWindow(None)
        try:
            self.assertEqual(win.view._target_name, "live_view_popout")
            self.assertFalse(hasattr(win.view, "_btn_popout"))
            self.assertTrue(any(t.name == "live_view_popout" for t in self.svc._targets))
        finally:
            win.close()
            _pump(0.3)
            gc.collect()
            _pump(0.1)

    def test_close_emits_closed_and_detaches_target_no_leak(self):
        from src.ui.visualizer.visualizer_view import VisualizerPopoutWindow
        baseline = list(self.state._callbacks)
        win = VisualizerPopoutWindow(None)
        closed = []
        win.closed.connect(lambda: closed.append(True))
        win.show()
        _pump(0.2)
        win.close()
        _pump(0.3)
        gc.collect()
        _pump(0.2)
        self.assertTrue(closed, "closed-Signal wurde beim Schliessen nicht emittiert")
        self.assertFalse(
            any(t.name == "live_view_popout" for t in self.svc._targets),
            "live_view_popout-Target nach dem Schliessen nicht vom Service abgemeldet")
        # Kein Subscriber-Leak: der Bridge-Subscriber der Kind-View ist weg,
        # die Baseline (inkl. Dauer-Service-Subscriber) ist wiederhergestellt.
        self.assertEqual(self.state._callbacks, baseline)


class LiveViewPopoutFlowTest(unittest.TestCase):
    def setUp(self):
        _app()
        self.state = get_state()
        self._prev = getattr(self.state, "show_fixture_labels", True)

    def tearDown(self):
        self.state.show_fixture_labels = self._prev

    def _make_live_view(self):
        from src.ui.views.live_view import LiveView
        return LiveView()

    def test_banner_hidden_by_default(self):
        # isHidden() spiegelt den eigenen Show/Hide-Zustand unabhaengig davon, ob
        # das (im Test nie gezeigte) Top-Level-Fenster gemappt ist.
        lv = self._make_live_view()
        try:
            self.assertIsNotNone(getattr(lv, "_popout_banner", None), "_popout_banner fehlt")
            self.assertTrue(lv._popout_banner.isHidden())
            self.assertIsNone(lv._viz_popout)
        finally:
            lv.deleteLater()
            _pump(0.1)

    def test_popout_guard_no_second_gl_scene(self):
        """Ist bereits ausgeklinkt (_viz_popout gesetzt), darf ein 3D-Klick KEINE
        zweite eingebettete GL-Szene bauen — er bleibt in 2D und holt das
        Pop-out nach vorne (GPU-Invariante)."""
        lv = self._make_live_view()
        try:
            raised = {"n": 0}

            class _FakePopout:
                def raise_(self_):
                    raised["n"] += 1
                def activateWindow(self_):
                    pass

            lv._viz_popout = _FakePopout()
            self.assertIsNone(lv._viz3d)
            lv._set_view_3d(True)
            # KEINE eingebettete 3D-View erzeugt, 2D bleibt aktiv, Pop-out geraised.
            self.assertIsNone(lv._viz3d, "Guard verletzt: eingebettete 3D-View trotz Pop-out gebaut")
            self.assertTrue(lv._btn_view2d.isChecked())
            self.assertFalse(lv._btn_view3d.isChecked())
            self.assertGreaterEqual(raised["n"], 1)
        finally:
            lv._viz_popout = None
            lv.deleteLater()
            _pump(0.1)

    def test_on_popout_closed_docks_back(self):
        """_on_popout_closed raeumt den Pop-out-Zustand ab (Banner weg, Referenz
        None) und dockt zurueck auf 3D."""
        lv = self._make_live_view()
        try:
            # Ausgeklinkten Zustand simulieren (ohne echtes zweites GL-Fenster).
            class _FakePopout:
                def raise_(self_):
                    pass
                def activateWindow(self_):
                    pass
            lv._viz_popout = _FakePopout()
            lv._popout_banner.show()
            self.assertFalse(lv._popout_banner.isHidden())

            lv._on_popout_closed()
            # Referenz + Banner werden SOFORT abgeraeumt ...
            self.assertIsNone(lv._viz_popout)
            self.assertTrue(lv._popout_banner.isHidden())
            # ... das eigentliche Wieder-Andocken ist per singleShot deferred.
            _pump(0.1)
            self.assertTrue(lv._btn_view3d.isChecked())
        finally:
            try:
                lv._set_view_3d(False)   # eingebettete View disposen
            except Exception:
                pass
            lv.deleteLater()
            _pump(0.15)

    def test_redock_while_tab_hidden_does_not_activate_target(self):
        """Review-Fix (Sichtbarkeits-Gate): dockt das Pop-out zurueck, waehrend
        der Live-View-Tab verborgen ist, darf das eingebettete 3D-Target NICHT
        aktiv bleiben (sonst laeuft der Service-Timer fuer eine unsichtbare
        Page). LiveView wird im Test nie gezeigt -> isVisible() False."""
        lv = self._make_live_view()
        try:
            lv._redock_after_popout()   # _viz_popout ist None -> dockt an
            _pump(0.15)
            viz = lv._viz3d
            self.assertIsNotNone(viz, "3D-View beim Redock nicht erzeugt")
            self.assertFalse(
                viz._target.active,
                "eingebettetes 3D-Target trotz verborgenem Live-View-Tab aktiv")
        finally:
            try:
                lv._set_view_3d(False)
            except Exception:
                pass
            lv.deleteLater()
            _pump(0.15)

    def test_full_popout_cycle_real_window(self):
        """End-to-end wie der VC-Popout-Regressionstest: echtes Fenster auf/zu."""
        lv = self._make_live_view()
        try:
            lv._pop_out_3d()
            self.assertIsNotNone(lv._viz_popout, "Pop-out-Fenster wurde nicht erzeugt")
            self.assertFalse(lv._popout_banner.isHidden())
            _pump(0.2)
            lv._viz_popout.close()
            _pump(0.3)
            gc.collect()
            _pump(0.1)
            self.assertIsNone(lv._viz_popout, "Pop-out nach Close nicht abgeraeumt")
            self.assertTrue(lv._popout_banner.isHidden())
        finally:
            try:
                lv._set_view_3d(False)
            except Exception:
                pass
            lv.deleteLater()
            _pump(0.15)


if __name__ == "__main__":
    unittest.main()
