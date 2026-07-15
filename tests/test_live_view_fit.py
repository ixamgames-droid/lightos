"""QOL-05: Auto-Fit-Zoom der 2D-Bühne.

Kompakte, aus dem 3D-Visualizer projizierte Rigs lagen als überlappender Klumpen
im 1200×800-Weltraum. Beim Laden (und per „Einpassen"-Button) zoomt/zentriert die
2D-Ansicht jetzt so, dass die Fixtures die Fläche mit Rand füllen — NICHT-destruktiv
(die Positionen bleiben unverändert, nur die Ansicht skaliert).
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.ui.views.live_view import _compute_fit_zoom, LiveView

_app = QApplication.instance() or QApplication([])


class TestComputeFitZoom(unittest.TestCase):
    """Reine Fit-Zoom-Funktion (kein Qt)."""

    def test_cluster_zooms_in(self):
        # kompaktes Rig (schmales Bbox) -> hineinzoomen, damit es die Flaeche fuellt
        self.assertGreater(_compute_fit_zoom(220, 60, 900, 700), 1.0)

    def test_large_rig_zooms_out(self):
        # grosses Rig -> herauszoomen (passt sonst nicht rein)
        self.assertLess(_compute_fit_zoom(1100, 700, 900, 700), 1.0)

    def test_clamped(self):
        self.assertEqual(_compute_fit_zoom(5, 5, 900, 700), 4.0)       # winzig -> Cap
        self.assertEqual(_compute_fit_zoom(9000, 9000, 900, 700), 0.25)  # riesig -> Floor

    def test_degenerate_bbox_safe(self):
        # Bbox 0 (ein Punkt) -> kein Div/0, geklemmter Zoom
        z = _compute_fit_zoom(0, 0, 900, 700)
        self.assertTrue(0.25 <= z <= 4.0)


class TestLiveViewFit(unittest.TestCase):
    def _mk(self):
        lv = LiveView()
        lv.resize(1000, 800)
        lv._scroll.viewport().resize(900, 700)
        return lv

    def test_force_fit_spreads_cluster(self):
        lv = self._mk()
        try:
            lv._canvas._positions = {i: (300.0 + i * 3, 250.0 + (i % 3) * 3)
                                     for i in range(12)}   # enger Klumpen
            z0 = lv._canvas.zoom
            lv._fit_2d_to_fixtures(force=True)
            self.assertGreater(lv._canvas.zoom, z0, "Klumpen sollte hineingezoomt werden")
        finally:
            lv.close(); lv.deleteLater()

    def test_non_force_leaves_wellspread_view(self):
        lv = self._mk()
        try:
            # Fixtures fuellen die Flaeche schon (grosses Bbox) -> Zoom NICHT anfassen
            lv._canvas.set_zoom(1.0)
            lv._canvas._positions = {0: (60.0, 60.0), 1: (1150.0, 60.0),
                                     2: (60.0, 760.0), 3: (1150.0, 760.0)}
            z0 = lv._canvas.zoom
            lv._fit_2d_to_fixtures(force=False)
            self.assertEqual(lv._canvas.zoom, z0, "gut gefuellte Ansicht darf bleiben")
        finally:
            lv.close(); lv.deleteLater()

    def test_single_fixture_no_crash(self):
        lv = self._mk()
        try:
            lv._canvas._positions = {0: (600.0, 400.0)}
            lv._fit_2d_to_fixtures(force=True)   # < 2 Fixtures -> No-Op, kein Crash
        finally:
            lv.close(); lv.deleteLater()

    def test_zoom_change_persists(self):
        # Review-Regression (HIGH): eine Zoom-Aenderung MUSS wieder persistieren
        # (der Persist-Aufruf war beim Einfuegen aus _on_zoom_changed gerutscht).
        lv = self._mk()
        try:
            lv._state.live_view_meta = {}
            lv._zoom_slider.setValue(260)
            self.assertEqual(lv._state.live_view_meta.get("zoom"), lv._canvas.zoom)
            self.assertGreater(lv._state.live_view_meta.get("zoom", 0), 1.0)
        finally:
            lv.close(); lv.deleteLater()

    def test_autofit_respects_saved_zoom(self):
        # Review-Regression (MEDIUM): Auto-Fit beim Laden NUR ohne gespeicherten Zoom.
        lv = self._mk()
        try:
            lv._canvas._positions = {i: (300.0 + i * 3, 250.0) for i in range(8)}
            fits = []
            lv._fit_2d_to_fixtures = lambda *a, **k: fits.append(1)
            lv._state.live_view_meta = {"zoom": 1.0}      # bewusst gespeichert
            lv._on_show_loaded_2d(); _app.processEvents()
            self.assertEqual(len(fits), 0, "gespeicherter Zoom darf NICHT ueberschrieben werden")
            lv._state.live_view_meta = {}                 # kein gespeicherter Zoom
            lv._on_show_loaded_2d(); _app.processEvents()
            self.assertGreaterEqual(len(fits), 1, "ohne saved zoom soll auto-gefittet werden")
        finally:
            lv.close(); lv.deleteLater()


if __name__ == "__main__":
    unittest.main()
