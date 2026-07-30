"""A3D-23: Der eingebettete Live-View-3D-Spiegel behielt beim Stufenwechsel die alte Qualität.

Ein Wechsel der Render-Qualität ruft ``service.reload_all_targets()`` — und das
lädt nur die **aktiven** Targets neu (``[t for t in self._targets if t.active]``).
Der dauerhaft angedockte 3D-Spiegel ist im 2D-Modus bzw. auf einem anderen Tab
inaktiv (``on_hidden`` → ``set_target_active(False)``) und wird übersprungen.
``on_shown`` schaltete ihn nur wieder aktiv und resyncte Fixtures — **ohne**
Page-Reload. Die Stufe reist aber als ``gputier``-Query in der Seiten-URL (eine
Konstruktor-Entscheidung des Renderers, nicht nachpushbar), also rendert der
Spiegel mit der alten Stufe weiter, bis die Seite aus einem anderen Grund neu
lädt (Crash, aktiver Reload, App-Neustart).

Gefixt über einen Stempel an der Seite: ``load_stage_html`` merkt sich die
verwendete Stufe, ``page_tier_is_stale`` vergleicht sie mit der aktuell
persistierten, und ``on_shown`` lädt bei Abweichung neu.
"""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import src.ui.visualizer.visualizer_window as VW      # noqa: E402
import src.ui.visualizer.visualizer_view as VV        # noqa: E402


class _FakeView:
    """Minimal-Ersatz fuer die QWebEngineView: nur `load` + Attribut-Ablage."""

    def __init__(self):
        self.geladen = []

    def load(self, url):
        self.geladen.append(url)


class StempelTest(unittest.TestCase):
    def setUp(self):
        self._orig = VW.quality_tier_pref

    def tearDown(self):
        VW.quality_tier_pref = self._orig

    def test_load_stage_html_merkt_sich_die_stufe(self):
        VW.quality_tier_pref = lambda: "low"
        v = _FakeView()
        VW.load_stage_html(v)
        self.assertEqual(v._lightos_loaded_tier, "low")
        self.assertTrue(v.geladen, "die Seite muss trotzdem geladen werden")

    def test_stale_erkennt_den_wechsel(self):
        VW.quality_tier_pref = lambda: "low"
        v = _FakeView()
        VW.load_stage_html(v)
        self.assertFalse(VW.page_tier_is_stale(v))
        VW.quality_tier_pref = lambda: "high"
        self.assertTrue(VW.page_tier_is_stale(v))

    def test_ohne_stempel_wird_nicht_geraten(self):
        """Eine Seite, die nie ueber load_stage_html kam, hat keinen Vergleich —
        ein Reload waere geraten, nicht begruendet."""
        VW.quality_tier_pref = lambda: "high"
        self.assertFalse(VW.page_tier_is_stale(_FakeView()))

    def test_auto_ist_ein_wert_wie_jeder_andere(self):
        VW.quality_tier_pref = lambda: "auto"
        v = _FakeView()
        VW.load_stage_html(v)
        VW.quality_tier_pref = lambda: "low"
        self.assertTrue(VW.page_tier_is_stale(v))
        VW.quality_tier_pref = lambda: "auto"
        self.assertFalse(VW.page_tier_is_stale(v))


class EinblendenTest(unittest.TestCase):
    """``on_shown`` — der Ort, an dem der Spiegel es merken muss."""

    def _fake(self, stale: bool):
        f = SimpleNamespace(
            _bridge=MagicMock(),
            _service=MagicMock(),
            _target=object(),
            _view=_FakeView(),
            _loaded=True,
            _btn_labels=None,
            _state=SimpleNamespace(show_fixture_labels=True),
            _reload_own_page=MagicMock(),
            _collect_settings=MagicMock(return_value={}),
        )
        VW.page_tier_is_stale = lambda _v: stale
        return f

    def setUp(self):
        self._orig = VW.page_tier_is_stale

    def tearDown(self):
        VW.page_tier_is_stale = self._orig

    def test_veraltete_stufe_laedt_die_seite_neu(self):
        f = self._fake(True)
        VV.Visualizer3DView.on_shown(f)
        f._reload_own_page.assert_called_once_with()
        self.assertFalse(f._loaded,
                         "an die Seite, die gerade ersetzt wird, darf nichts "
                         "mehr gepusht werden")
        f._bridge.push_settings.assert_not_called()

    def test_gleiche_stufe_bleibt_beim_bestandsverhalten(self):
        """Der Normalfall: kein Reload, nur Reaktivieren + Resync."""
        f = self._fake(False)
        VV.Visualizer3DView.on_shown(f)
        f._reload_own_page.assert_not_called()
        f._service.set_target_active.assert_called_once()
        f._bridge.requestFixtures.assert_called_once_with()

    def test_target_wird_in_beiden_faellen_aktiv_geschaltet(self):
        """Sonst liefe der Service-Timer nicht — der Reload-Zweig darf das
        nicht ueberspringen."""
        f = self._fake(True)
        VV.Visualizer3DView.on_shown(f)
        f._service.set_target_active.assert_called_once()


if __name__ == "__main__":
    unittest.main()
