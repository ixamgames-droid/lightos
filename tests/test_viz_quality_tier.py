"""VIZ-15 (Teil 2): Qualitätsstufe — Auto-Erkennung + manueller Override.

Die Stufe ist geräte-gebunden (ui_prefs.json, Key ``viz_quality_tier``) und
reist als ``gputier``-Query mit JEDEM ``load_stage_html``-Aufruf — damit greift
sie für alle Targets (Vollfenster, eingebettete 3D-View, Crash-Guard-Reload,
"Szene neu laden"). 'auto' hängt bewusst KEINEN Query an: dann entscheidet die
JS-Probe (renderer.js#probeGpuTier, abgedeckt im QtWebEngine-Smoke).
"""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QComboBox, QLabel

import src.ui.visualizer.visualizer_window as VW

_app = QApplication.instance() or QApplication([])


class QualityTierPrefTest(unittest.TestCase):
    def test_valid_values_pass_through(self):
        for val in ("auto", "high", "low", "LOW", "High"):
            with patch("src.ui.views.programmer_view._load_prefs",
                       return_value={"viz_quality_tier": val}):
                self.assertEqual(VW.quality_tier_pref(), val.lower())

    def test_missing_or_invalid_falls_back_to_auto(self):
        for prefs in ({}, {"viz_quality_tier": "ultra"}, {"viz_quality_tier": 3}):
            with patch("src.ui.views.programmer_view._load_prefs",
                       return_value=prefs):
                self.assertEqual(VW.quality_tier_pref(), "auto")

    def test_prefs_error_falls_back_to_auto(self):
        with patch("src.ui.views.programmer_view._load_prefs",
                   side_effect=OSError("kaputt")):
            self.assertEqual(VW.quality_tier_pref(), "auto")


class _UrlCaptureView:
    def __init__(self):
        self.urls = []

    def load(self, url):
        self.urls.append(url)


class LoadStageHtmlTierQueryTest(unittest.TestCase):
    def _query_for(self, tier):
        view = _UrlCaptureView()
        with patch.object(VW, "quality_tier_pref", return_value=tier):
            VW.load_stage_html(view)
        self.assertEqual(len(view.urls), 1)
        return view.urls[0].query()

    def test_auto_adds_no_tier_query(self):
        q = self._query_for("auto")
        self.assertIn("v=", q)
        self.assertNotIn("gputier", q)

    def test_forced_low_travels_in_query(self):
        q = self._query_for("low")
        self.assertIn("v=", q)          # Cache-Buster bleibt erhalten
        self.assertIn("gputier=low", q)

    def test_forced_high_travels_in_query(self):
        self.assertIn("gputier=high", self._query_for("high"))


class QualityComboHandlerTest(unittest.TestCase):
    def _fake(self):
        combo = QComboBox()
        combo.addItem("Automatisch (empfohlen)", "auto")
        combo.addItem("Hoch (Desktop-GPU)", "high")
        combo.addItem("Niedrig (schwache/mobile GPU)", "low")
        return SimpleNamespace(
            _combo_quality=combo,
            _on_reload_scene=MagicMock(),
        )

    def test_change_persists_pref_and_reloads_scene(self):
        fake = self._fake()
        fake._combo_quality.setCurrentIndex(2)  # "low"
        saved = {}
        with patch("src.ui.views.programmer_view._save_prefs",
                   side_effect=saved.update):
            VW.VisualizerWindow._on_quality_tier_changed(fake, 2)
        self.assertEqual(saved, {"viz_quality_tier": "low"})
        fake._on_reload_scene.assert_called_once()

    def test_save_error_still_reloads(self):
        fake = self._fake()
        fake._combo_quality.setCurrentIndex(1)
        with patch("src.ui.views.programmer_view._save_prefs",
                   side_effect=OSError("Platte voll")):
            VW.VisualizerWindow._on_quality_tier_changed(fake, 1)
        fake._on_reload_scene.assert_called_once()


class GpuTierReportTest(unittest.TestCase):
    def test_bridge_slot_forwards_tier(self):
        fake = SimpleNamespace(pyGpuTierReported=MagicMock())
        VW.VisualizerBridge.reportGpuTier(fake, "low")
        fake.pyGpuTierReported.emit.assert_called_once_with("low")

    def test_bridge_slot_ignores_empty(self):
        fake = SimpleNamespace(pyGpuTierReported=MagicMock())
        VW.VisualizerBridge.reportGpuTier(fake, "")
        fake.pyGpuTierReported.emit.assert_not_called()

    def test_window_label_shows_german_tier_name(self):
        lbl = QLabel("aktiv: –")
        fake = SimpleNamespace(_lbl_gpu_tier=lbl)
        VW.VisualizerWindow._on_gpu_tier_reported(fake, "low")
        self.assertEqual(lbl.text(), "aktiv: Niedrig")
        VW.VisualizerWindow._on_gpu_tier_reported(fake, "high")
        self.assertEqual(lbl.text(), "aktiv: Hoch")


if __name__ == "__main__":
    unittest.main()
