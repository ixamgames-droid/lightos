"""VIZ-71: Qualitaetsstufen Niedrig / Hoch / Maximal.

=========  =======  ====================  =================  ======================
Stufe      Push     Pixeldichte           Schatten           dyn. Aufloesung
=========  =======  ====================  =================  ======================
Niedrig    15 Hz    hoechstens 1,25       8, PCF             bei Kamerabewegung
Hoch       30 Hz    hoechstens 2          8, PCFSoft         nur wenn Frame > 18 ms
Maximal    44 Hz    volle Geraetedichte   16, PCFSoft        nie
=========  =======  ====================  =================  ======================

``auto`` laesst die GPU-Probe zwischen Niedrig und Hoch waehlen; Maximal gibt es
nur von Hand (Einstellungen-Tab des 3D-Fensters). Python-Teil ohne GPU, dazu
ein Szenen-Teil gegen die echte Seite (offscreen).
"""
import json
import os
import re
import time
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QComboBox, QLabel
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineSettings, QWebEngineProfile
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtCore import QObject, QUrl, Signal, Slot
from _qt_lifecycle import destroy_webengine_view  # XPLAT-09

import src.ui.visualizer.visualizer_window as VW
from src.ui.visualizer import quality_tiers as QT

_app = QApplication.instance() or QApplication([])

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCENE = os.path.join(_REPO, "src", "ui", "visualizer", "scene_src")
_HTML_PATH = os.path.join(_REPO, "src", "ui", "visualizer", "stage_scene.html")

import pytest as _pytest_xplat15                      # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402  XPLAT-15


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    from PySide6.QtWidgets import QApplication as _QApp
    destroy_all_top_level_widgets(_QApp.instance())


def _js(*teile):
    return open(os.path.join(_SCENE, *teile), encoding="utf-8").read()


def _js_tabelle():
    """TIER_PROFILES aus quality_tiers.js -> {stufe: {feld: wert}}."""
    quelle = _js("scene", "quality_tiers.js")
    out = {}
    for stufe in ("low", "high", "max"):
        block = re.search(stufe + r": Object\.freeze\(\{(.*?)\}\)", quelle, re.S).group(1)
        felder = dict(re.findall(r"(\w+): ([^,\n]+)", block))
        out[stufe] = {k: v.strip().strip("'") for k, v in felder.items()}
    return out


# ── Python-Seite ─────────────────────────────────────────────────────────────
class TabelleTest(unittest.TestCase):
    def test_push_takt_je_stufe(self):
        self.assertEqual(QT.PUSH_HZ, {"low": 15, "high": 30, "max": 44})
        self.assertEqual([QT.push_tick_ms(t) for t in ("low", "high", "max")], [66, 33, 22])
        self.assertEqual(QT.push_tick_ms("auto"), 33, "auto bis zur Meldung = Hoch")

    def test_maximal_ist_der_dmx_ausgabetakt(self):
        from src.core.dmx.output_manager import TARGET_HZ
        self.assertEqual(QT.PUSH_HZ["max"], TARGET_HZ,
                         "schneller als die DMX-Ausgabe gibt es nichts Neues")

    def test_js_und_python_tabelle_stimmen_ueberein(self):
        js = _js_tabelle()
        for stufe, hz in QT.PUSH_HZ.items():
            self.assertEqual(int(js[stufe]["pushHz"]), hz, stufe)
        self.assertEqual(js["low"]["pixelRatioCap"], "1.25")
        self.assertEqual(js["high"]["pixelRatioCap"], "2")
        self.assertEqual(js["max"]["pixelRatioCap"], "null")
        self.assertEqual([js[s]["shadowCap"] for s in ("low", "high", "max")], ["8", "8", "16"])
        self.assertEqual([js[s]["softShadows"] for s in ("low", "high", "max")],
                         ["false", "true", "true"])
        self.assertEqual([js[s]["dynamicResolution"] for s in ("low", "high", "max")],
                         ["always", "slow", "never"])

    def test_maximal_dach_bleibt_unter_der_kippgrenze(self):
        dach = int(re.search(r"(?m)^const SHADOW_SPOT_HARD_CAP_MAX = (\d+);",
                             _js("fixtures", "fixtures.js")).group(1))
        self.assertEqual(dach, 16)
        self.assertLessEqual(dach, 20, "gemessene Kippgrenze: 24 gut / 26 Absturz")
        self.assertIn("SHADOW_SPOT_HARD_CAP_MAX", _js("fixtures", "fixtures.js")
                      .split("function schattenDach()", 1)[1].split("}", 1)[0])

    def test_probe_waehlt_nie_maximal(self):
        quelle = _js("scene", "renderer.js")
        probe = quelle.split("function probeGpuTier()", 1)[1].split("\nexport const gpuTier", 1)[0]
        self.assertIn("forced === 'max'", probe, "max muss per ?gputier waehlbar sein")
        self.assertNotIn("? 'max'", probe)
        self.assertRegex(probe, r"return \(maxTex <= 16 \|\| weakChip\) \? 'low' : 'high';")


class AnleitungTest(unittest.TestCase):
    def test_anleitung_nennt_die_stufen_in_zahlen(self):
        """Die 3D-Anleitung erklaert die Stufen mit den Zahlen des Codes."""
        pfad = os.path.join(_REPO, "docs", "anleitung_3d_visualizer_2026",
                            "ANLEITUNG_3D_BUEHNE.md")
        text = open(pfad, encoding="utf-8").read()
        for name, stufe in (("Niedrig", "low"), ("Hoch", "high"), ("Maximal", "max")):
            zeile = re.search(r"(?m)^\| \*\*%s\*\*.*$" % name, text)
            self.assertIsNotNone(zeile, f"Tabellenzeile {name} fehlt")
            self.assertIn(f"{QT.PUSH_HZ[stufe]} pro Sekunde", zeile.group(0))
        self.assertIn("16, weich", text)


class PraeferenzTest(unittest.TestCase):
    def test_max_ist_eine_gueltige_praeferenz(self):
        with patch("src.ui.views.programmer_view._load_prefs",
                   return_value={"viz_quality_tier": "MAX"}):
            self.assertEqual(VW.quality_tier_pref(), "max")

    def test_max_reist_als_query(self):
        class _V:
            urls = []

            def load(self, url):
                self.urls.append(url)
        v = _V()
        with patch.object(VW, "quality_tier_pref", return_value="max"):
            VW.load_stage_html(v)
        self.assertIn("gputier=max", v.urls[0].query())

    def test_auswahl_im_einstellungen_tab(self):
        combo = QComboBox()
        try:
            # dieselben Eintraege wie _build_settings_tab
            quelle = open(VW.__file__, encoding="utf-8").read()
            block = quelle.split("self._combo_quality = QComboBox()", 1)[1].split(
                "self._combo_quality.setToolTip", 1)[0]
            eintraege = re.findall(r'addItem\("([^"]+)", "(\w+)"\)', block)
            self.assertEqual([d for _t, d in eintraege], ["auto", "high", "low", "max"])
            self.assertIn("Maximal", dict((d, t) for t, d in eintraege)["max"])
            for text, daten in eintraege:
                combo.addItem(text, daten)
            fake = SimpleNamespace(_combo_quality=combo, _on_reload_scene=MagicMock())
            combo.setCurrentIndex(3)
            gespeichert = {}
            with patch("src.ui.views.programmer_view._save_prefs",
                       side_effect=gespeichert.update):
                VW.VisualizerWindow._on_quality_tier_changed(fake, 3)
            self.assertEqual(gespeichert, {"viz_quality_tier": "max"})
            fake._on_reload_scene.assert_called_once()
        finally:
            combo.deleteLater()
            _app.processEvents()

    def test_anzeige_der_aktiven_stufe(self):
        lbl = QLabel()
        try:
            VW.VisualizerWindow._on_gpu_tier_reported(SimpleNamespace(_lbl_gpu_tier=lbl), "max")
            self.assertEqual(lbl.text(), "aktiv: Maximal")
        finally:
            lbl.deleteLater()
            _app.processEvents()


class PushTaktTest(unittest.TestCase):
    def _besitzer(self, state):
        from src.ui.visualizer.visualizer_service import VisualizerService

        class _Seite(QObject):
            def runJavaScript(self, *_a):
                pass

        class _View(QObject):
            loadStarted = Signal()

            def __init__(self):
                super().__init__()
                self._s = _Seite()

            def page(self):
                return self._s
        class _Besitzer:          # weakref-faehig wie Fenster/View
            pass
        b = _Besitzer()
        b._view, b._bridge = _View(), VW.VisualizerBridge(state)
        b._service = VisualizerService(state)
        b._dmx_push = VW.create_dmx_push(b)
        from src.ui.visualizer.visualizer_service import VisualizerTarget
        b._target = VisualizerTarget("t", lambda s: None, emit_payloads=b._dmx_push.push)
        b._service.attach_target(b._target)
        b._service.set_target_active(b._target, True)
        return b

    def test_gemeldete_stufe_setzt_takt_von_kanal_und_service(self):
        from src.core.app_state import get_state
        from src.core.show.show_file import reset_show
        reset_show()
        b = self._besitzer(get_state())
        try:
            for stufe, ms in (("low", 66), ("max", 22), ("high", 33)):
                b._bridge.reportGpuTier(stufe)
                self.assertAlmostEqual(b._dmx_push.min_interval_s, 1.0 / QT.PUSH_HZ[stufe])
                self.assertEqual(b._target.tick_ms, ms)
                self.assertEqual(b._service._timer.interval(), ms)
        finally:
            b._service.shutdown()
            b._bridge.dispose()


# ── Szenen-Teil (echte Seite, offscreen) ─────────────────────────────────────
_SIGNAL_SPECS = [
    ("fixtureAdded", (str,)), ("fixtureRemoved", (int,)),
    ("allFixtures", (str,)), ("settingsChanged", (str,)),
    ("viewModeChanged", (str,)), ("editModeChanged", (str,)),
    ("stageLoaded", (str,)), ("pixelRatioSignal", (float,)),
]


def _mock_bridge_class():
    attrs = {n: Signal(*t) for n, t in _SIGNAL_SPECS}

    @Slot()
    def requestFixtures(self):
        pass

    @Slot(result=str)
    def pollControl(self):
        return "{}"

    @Slot(str)
    def reportGpuTier(self, tier):
        self.gemeldet = tier

    attrs.update(requestFixtures=requestFixtures, pollControl=pollControl,
                 reportGpuTier=reportGpuTier, requestFullResync=Signal())
    return type("MockBridgeViz71Stufen", (QObject,), attrs)


_MockBridge = _mock_bridge_class()


def _pump(seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        _app.processEvents()
        time.sleep(0.02)


class StufenSzeneTest(unittest.TestCase):
    def setUp(self):
        self._view = QWebEngineView()
        try:
            self._view.page().profile().setHttpCacheType(
                QWebEngineProfile.HttpCacheType.NoCache)
        except Exception:
            pass
        s = self._view.settings()
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        self._bridge_obj = _MockBridge()
        self._channel = QWebChannel(self._view)
        self._channel.registerObject("bridge", self._bridge_obj)
        self._view.page().setWebChannel(self._channel)
        self._ok = []
        self._view.loadFinished.connect(self._ok.append)

    def tearDown(self):
        destroy_webengine_view(self._view, _pump)
        self._view = None

    def _eval(self, js):
        box = []
        self._view.page().runJavaScript(js, box.append)
        ende = time.monotonic() + 10
        while not box and time.monotonic() < ende:
            _app.processEvents()
            time.sleep(0.01)
        self.assertTrue(box, js)
        return box[0]

    def _laden(self, stufe):
        url = QUrl.fromLocalFile(_HTML_PATH)
        url.setQuery(f"v={int(time.time() * 1000)}&gputier={stufe}")
        self._view.load(url)
        ende = time.monotonic() + 40
        while not self._ok and time.monotonic() < ende:
            _app.processEvents()
            time.sleep(0.05)
        self.assertTrue(self._ok and self._ok[-1])
        ende = time.monotonic() + 10
        while time.monotonic() < ende and not self._eval("!!window.__lightosAppReady"):
            time.sleep(0.05)

    def _zustand(self):
        return json.loads(self._eval(
            "(function(){ const L = window.__lightos; return JSON.stringify({"
            " tier: L.gpuTier, cap: L.pixelRatioCap, pr: L.pixelRatio(),"
            " base: L.basePixelRatio(), typ: L.shadowMapType(),"
            " dach: L.shadowBudgetInfo().hardCap, dyn: L.dynamicResolutionInfo() }); })()"))

    def _kamerafahrt(self):
        # zwei Kamera-Updates in verschiedenen "Frames" (>= 8 ms auseinander)
        self._eval("(function(){ const L = window.__lightos; L.__noteCameraMotion();"
                   " const t = performance.now(); while (performance.now() - t < 12) {}"
                   " L.__noteCameraMotion(); return 1; })()")

    def test_niedrig(self):
        self._laden("low")
        z = self._zustand()
        self.assertEqual(z["tier"], "low")
        self.assertEqual(z["cap"], 1.25)
        self.assertEqual(z["typ"], 1, "Niedrig: einfache PCF-Schatten")
        self.assertEqual(z["dach"], 8)
        self._eval("window.__lightos.setDeviceRatio(3)")
        self.assertEqual(self._zustand()["pr"], 1.25, "Deckel 1,25 eingehalten")
        # dynamische Aufloesung: immer bei Kamerafahrt
        self._kamerafahrt()
        z = self._zustand()
        self.assertLess(z["dyn"]["scale"], 1)
        self.assertAlmostEqual(z["pr"], 1.25 * z["dyn"]["scale"], places=4)
        # Resize waehrend der Fahrt: Absenkung bleibt, neue Basis
        self._eval("window.__lightos.setDeviceRatio(1); window.dispatchEvent(new Event('resize')); 1")
        z = self._zustand()
        self.assertLess(z["dyn"]["scale"], 1, "Resize hob die Absenkung auf")
        self.assertAlmostEqual(z["pr"], 1.0 * z["dyn"]["scale"], places=4)
        self.assertEqual(self._bridge_obj.__dict__.get("gemeldet", "low"), "low")

    def test_hoch(self):
        self._laden("high")
        z = self._zustand()
        self.assertEqual((z["cap"], z["typ"], z["dach"]), (2, 2, 8))
        self._eval("window.__lightos.setDeviceRatio(3)")
        self.assertEqual(self._zustand()["pr"], 2)
        self.assertEqual(z["dyn"]["mode"], "slow")

    def test_maximal(self):
        self._laden("max")
        z = self._zustand()
        self.assertEqual(z["tier"], "max")
        self.assertIsNone(z["cap"], "Maximal: kein Deckel (Infinity -> null)")
        self.assertEqual(z["typ"], 2, "Maximal: weiche Schatten (PCFSoft)")
        self.assertLessEqual(z["dach"], 16)
        self.assertGreaterEqual(z["dach"], 8)
        self._eval("window.__lightos.setDeviceRatio(3)")
        self.assertEqual(self._zustand()["pr"], 3, "volle Geraete-Pixeldichte")
        self._kamerafahrt()
        self.assertEqual(self._zustand()["dyn"]["scale"], 1, "Maximal senkt nie ab")


if __name__ == "__main__":
    unittest.main()
