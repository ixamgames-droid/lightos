"""FM-6/7: zentrales viz_model_for-Routing + 2D-Bar-Symbole.

viz_model_for (app_state) ist die EINZIGE Quelle fuer das Render-Modell von
Multi-Emitter-Geraeten — genutzt vom 3D-Modell (VisualizerBridge._viz_model_for),
vom 2D-Top-Down-Symbol (live_view.FixtureRenderer) und von den Listen-Icons
(mini_icons.fixture_icon_for) sowie der Patch-Spiegel-Option. Diese Tests nageln
die Routing-Entscheidung fest und pruefen, dass die neuen Bar-Symbole gezeichnet
und geroutet werden.
"""
import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import src.core.app_state as AS


def _chans(*attrs):
    return [SimpleNamespace(attribute=a) for a in attrs]


_MOVER = ["pan", "tilt", "color_r", "color_g", "color_b"] * 4
_PAR = ["color_r", "color_g", "color_b"] * 4
_SPIDER_DUAL = ["tilt", "tilt", "color_r", "color_g", "color_b", "color_w",
                "color_r", "color_g", "color_b", "color_w"]
_SPIDER_SINGLE = ["pan", "tilt", "color_r", "color_g", "color_b",
                  "color_r", "color_g", "color_b"]        # 1 Pan -> kein mover_bar
_PLAIN_PAR = ["color_r", "color_g", "color_b"]            # 1 Bank -> None


class VizModelForTest(unittest.TestCase):
    """Reine Layout-Logik ueber gemocktes get_channels_for_patched."""

    def setUp(self):
        self._saved = AS.get_channels_for_patched

    def tearDown(self):
        AS.get_channels_for_patched = self._saved

    def _model(self, attrs):
        AS.get_channels_for_patched = lambda f: _chans(*attrs)
        return AS.viz_model_for(SimpleNamespace())

    def test_mover_bar(self):
        self.assertEqual(self._model(_MOVER), "mover_bar")

    def test_par_bar(self):
        self.assertEqual(self._model(_PAR), "par_bar")

    def test_classic_dual_bar_spider(self):
        self.assertEqual(self._model(_SPIDER_DUAL), "spider")

    def test_single_head_spider_is_not_mover_bar(self):
        # Nur EIN Pan (QLC+-Spider) -> spider, nicht mover_bar.
        self.assertEqual(self._model(_SPIDER_SINGLE), "spider")

    def test_plain_par_returns_none(self):
        # <2 Farb-Banks -> kein Multi-Emitter -> None (Aufrufer nutzt fixture_type).
        self.assertIsNone(self._model(_PLAIN_PAR))


class VizModelDelegateTest(unittest.TestCase):
    """VisualizerBridge._viz_model_for delegiert an viz_model_for (FM-7)."""

    def setUp(self):
        self._saved = AS.get_channels_for_patched

    def tearDown(self):
        AS.get_channels_for_patched = self._saved

    def _bridge_model(self, attrs, ftype):
        from src.ui.visualizer.visualizer_window import VisualizerBridge
        AS.get_channels_for_patched = lambda f: _chans(*attrs)
        f = SimpleNamespace(fixture_type=ftype)
        return VisualizerBridge._viz_model_for(SimpleNamespace(), f)

    def test_mover_bar_via_bridge(self):
        self.assertEqual(self._bridge_model(_MOVER, "moving_head"), "mover_bar")

    def test_par_bar_via_bridge(self):
        self.assertEqual(self._bridge_model(_PAR, "led_bar"), "par_bar")

    def test_non_spider_falls_back_to_fixture_type(self):
        self.assertEqual(self._bridge_model(_PLAIN_PAR, "par"), "par")


class BarSymbolRenderSmokeTest(unittest.TestCase):
    """FixtureRenderer.draw zeichnet die neuen Bar-Typen ohne Fehler."""

    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls._app = QApplication.instance() or QApplication([])

    def _draw(self, render_type):
        from PySide6.QtGui import QPixmap, QPainter, QColor
        from src.ui.views.live_view import FixtureRenderer
        pm = QPixmap(80, 80)
        pm.fill(QColor("black"))
        painter = QPainter(pm)
        try:
            FixtureRenderer.draw(
                painter, render_type, 40, 40, 24, QColor(255, 80, 80),
                220, "1", pan=90, tilt=140)
        finally:
            painter.end()

    def test_par_bar_draws(self):
        self._draw("par_bar")       # darf nicht werfen

    def test_mover_bar_draws(self):
        self._draw("mover_bar")


class BarListIconRoutingTest(unittest.TestCase):
    """mini_icons.fixture_icon_for routet par_bar/mover_bar/spider ueber das
    zentrale viz_model_for auf die dedizierten Icon-Maler."""

    def test_registry_has_new_kinds(self):
        import src.ui.widgets.mini_icons as MI
        self.assertIn("fx_par_bar", MI._PAINTERS)
        self.assertIn("fx_mover_bar", MI._PAINTERS)

    def _routed_kind(self, model):
        import src.ui.widgets.mini_icons as MI
        calls = []
        saved_kind = MI.icon_for_kind
        saved_fn, saved_loaded = MI._viz_model_for_fn, MI._viz_model_for_loaded
        MI.icon_for_kind = lambda kind, size=16: (calls.append(kind) or "ICON")
        MI._viz_model_for_loaded = True
        MI._viz_model_for_fn = lambda f: model
        try:
            MI.fixture_icon_for(SimpleNamespace(fixture_type="moving_head"))
        finally:
            MI.icon_for_kind = saved_kind
            MI._viz_model_for_fn, MI._viz_model_for_loaded = saved_fn, saved_loaded
        return calls

    def test_mover_bar_icon(self):
        self.assertEqual(self._routed_kind("mover_bar"), ["fx_mover_bar"])

    def test_par_bar_icon(self):
        self.assertEqual(self._routed_kind("par_bar"), ["fx_par_bar"])

    def test_spider_icon(self):
        self.assertEqual(self._routed_kind("spider"), ["fx_spider"])

    def test_none_falls_back_to_type_icon(self):
        # model None -> kein Multi-Emitter-Icon, delegiert an fixture_icon (fx_<type>)
        self.assertEqual(self._routed_kind(None), ["fx_moving_head"])


if __name__ == "__main__":
    unittest.main()
