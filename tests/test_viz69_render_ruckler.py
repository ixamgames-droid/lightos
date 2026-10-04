"""VIZ-69: Ruckler im 3D-Visualizer — Shader-Neukompilierung + Schatten je Frame.

**Was ruckelte.** Zwei Kosten, gemessen an der Bierpong-Show (24 Spots, Intel
UHD 630) im echten Fenster:

1. **Standbilder von 0,3 bis 2,2 s** bei Hell/Dunkel-Wechseln. Dunkle Geraete
   bekamen ``spot.visible = false``. In three.js r128 gehoert die Zahl der
   sichtbaren SpotLights (und der sichtbaren Schatten-Spots) zum
   Programmschluessel jedes beleuchteten Materials — jede neue Kombination
   kompilierte alle Lit-Shader neu. Jetzt bleibt der Spot sichtbar, dunkel
   heisst ``intensity = 0``.
2. **Schatten-Durchlauf in jedem Frame**, auch beim reinen Kamera-Orbit und bei
   reinen Farbwechseln. Eine Shadow-Map haengt nur an der Lage von Licht und
   Schattenwerfern; ``scene/shadow_update.js`` zeichnet sie nur noch neu, wenn
   sich genau die aendert.

Die Pruefungen laufen ueber die ECHTE Produktiv-Seite und den echten
``dmxBatch``-Pfad (wie ``test_viz13_scene_modules_smoke.py``). Der
Neubau-Zaehler stammt aus der Render-Closure selbst; er zaehlt auch dann, wenn
offscreen kein WebGL zeichnet — die Entscheidung "jetzt neu" faellt vor dem
GL-Aufruf.
"""
import json
import os
import re
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineSettings, QWebEngineProfile
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtCore import QObject, QUrl, Signal, Slot
from _qt_lifecycle import destroy_webengine_view  # XPLAT-09

_app = QApplication.instance() or QApplication([])

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCENE_SRC = os.path.join(_REPO, "src", "ui", "visualizer", "scene_src")
_HTML_PATH = os.path.join(_REPO, "src", "ui", "visualizer", "stage_scene.html")

_LOAD_TIMEOUT_S = 40.0
_POLL_TIMEOUT_S = 10.0
_POLL_INTERVAL_S = 0.05

# 1:1 aus visualizer_window.py::VisualizerBridge (bridge.js guardet jeden
# Connect mit ``if (bridge.X)``).
_SIGNAL_SPECS = [
    ("fixtureAdded", (str,)), ("fixtureRemoved", (int,)), ("dmxBatch", (str,)),
    ("allFixtures", (str,)), ("settingsChanged", (str,)),
    ("viewModeChanged", (str,)), ("editModeChanged", (str,)),
    ("stageLoaded", (str,)), ("addStageObject", (str,)),
    ("addStageObjectData", (str,)), ("removeStageObject", (str,)),
    ("selectStageObject", (str,)), ("applyFixtureTransform", (str,)),
    ("alignSelected", (str,)), ("distributeSelected", (str,)),
    ("cameraReset", ()), ("brightnessSignal", (float,)),
    ("brightnessAutoSignal", ()), ("updateStageObject", (str,)),
    ("resizeModeSignal", (bool,)), ("pixelRatioSignal", (float,)),
]


def _make_mock_bridge_class():
    attrs = {name: Signal(*types) for name, types in _SIGNAL_SPECS}

    @Slot()
    def requestFixtures(self):
        pass

    @Slot(result=str)
    def pollControl(self):
        return "{}"

    attrs["requestFixtures"] = requestFixtures
    attrs["pollControl"] = pollControl
    attrs["requestFullResync"] = Signal()
    return type("MockVisualizerBridgeViz69", (QObject,), attrs)


_MockBridge = _make_mock_bridge_class()


def _pump(seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        _app.processEvents()
        time.sleep(_POLL_INTERVAL_S)


# XPLAT-15: uebrig gebliebene Top-Level-Widgets nach jedem Test WIRKLICH abbauen
# (Begruendung: tests/_qt_lifecycle.py).
import pytest as _pytest_xplat15                      # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402  XPLAT-15


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    from PySide6.QtWidgets import QApplication as _QApp
    destroy_all_top_level_widgets(_QApp.instance())


_FIDS = (690001, 690002, 690003)


def _batch(r, g, b, intensity, pan=128, tilt=128):
    return json.dumps([{"fid": fid, "r": r, "g": g, "b": b,
                        "intensity": intensity, "pan": pan, "tilt": tilt}
                       for fid in _FIDS])


class Viz69RenderRucklerTest(unittest.TestCase):
    def setUp(self):
        self._view = QWebEngineView()
        try:
            profile = self._view.page().profile()
            profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.NoCache)
        except Exception:
            pass
        s = self._view.settings()
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        self._bridge_obj = _MockBridge()
        self._channel = QWebChannel(self._view)
        self._channel.registerObject("bridge", self._bridge_obj)
        self._view.page().setWebChannel(self._channel)
        self._loaded_ok = []
        self._view.loadFinished.connect(self._loaded_ok.append)

    def tearDown(self):
        destroy_webengine_view(self._view, _pump)
        self._view = None

    # ── Helfer (Muster: test_viz13_scene_modules_smoke.py) ───────────────────
    def _load_and_wait(self):
        url = QUrl.fromLocalFile(_HTML_PATH)
        url.setQuery(f"v={int(time.time() * 1000)}")
        self._view.load(url)
        deadline = time.monotonic() + _LOAD_TIMEOUT_S
        while not self._loaded_ok and time.monotonic() < deadline:
            _app.processEvents()
            time.sleep(_POLL_INTERVAL_S)
        self.assertTrue(self._loaded_ok and self._loaded_ok[-1], "Seite nicht geladen")
        self._poll_until_true("!!window.__lightosAppReady")

    def _eval(self, js_expr):
        box = []
        self._view.page().runJavaScript(js_expr, lambda result: box.append(result))
        deadline = time.monotonic() + _POLL_TIMEOUT_S
        while not box and time.monotonic() < deadline:
            _app.processEvents()
            time.sleep(_POLL_INTERVAL_S)
        self.assertTrue(box, f"runJavaScript-Callback nie ausgeloest fuer: {js_expr}")
        return box[0]

    def _poll_until_true(self, js_expr, timeout_s=_POLL_TIMEOUT_S):
        deadline = time.monotonic() + timeout_s
        last = None
        while time.monotonic() < deadline:
            last = self._eval(js_expr)
            if last:
                return last
            time.sleep(_POLL_INTERVAL_S)
        self.fail(f"Timeout beim Warten auf '{js_expr}' (letzter Wert: {last!r})")

    def _emit_until_true(self, emit_fn, js_expr, timeout_s=_POLL_TIMEOUT_S):
        deadline = time.monotonic() + timeout_s
        last = None
        while time.monotonic() < deadline:
            emit_fn()
            last = self._eval(js_expr)
            if last:
                return last
            time.sleep(_POLL_INTERVAL_S)
        self.fail(f"Timeout nach wiederholtem Emit: '{js_expr}' (letzter Wert: {last!r})")

    def _rig_aufbauen(self):
        self._load_and_wait()
        payload = json.dumps([
            {"fid": fid, "type": "moving_head", "x": i * 2.0, "y": 6, "z": 0,
             "r": 255, "g": 255, "b": 255, "intensity": 255}
            for i, fid in enumerate(_FIDS)])
        self._emit_until_true(
            lambda: self._bridge_obj.allFixtures.emit(payload),
            f"Object.keys(window.__lightos.fixtures).length === {len(_FIDS)}",
            timeout_s=10.0)

    def _spot_zustand(self):
        return json.loads(self._eval("""
            (function(){
              const fx = window.__lightos.fixtures; const out = [];
              for (const fid in fx) { const s = fx[fid].spot;
                if (s) out.push([s.visible, s.castShadow, s.intensity]); }
              return JSON.stringify(out);
            })()"""))

    def _tick(self):
        """Einen Frame deterministisch rendern, Neubau-Zaehler zurueckgeben."""
        return self._eval(
            "(function(){ const L = window.__lightos; L.requestRender();"
            " L.__renderTick(); return L.shadowUpdateStats().neubauten; })()")

    # ── (1) Hell/Dunkel aendert den Shader-Schluessel nicht ──────────────────
    def test_dunkel_ist_intensity_null_nicht_unsichtbar(self):
        """Hell/Dunkel-Wechsel duerfen weder visible noch castShadow umschalten.

        Beides steckt in r128 im Programmschluessel (numSpotLights /
        numSpotLightShadows) — jedes Umschalten kostete eine Neukompilierung
        aller Lit-Shader. Rot ohne Fix: der dunkle Spot war ``visible=false``.
        """
        self._rig_aufbauen()
        hell = self._spot_zustand()
        self.assertEqual(len(hell), len(_FIDS))
        self.assertTrue(all(v for v, _c, _i in hell), "heller Spot unsichtbar")

        # Dimmer offen, Farbe schwarz (A3D-25/A3D-28) -> dunkel.
        self._emit_until_true(
            lambda: self._bridge_obj.dmxBatch.emit(_batch(0, 0, 0, 255)),
            "Object.values(window.__lightos.fixtures)"
            ".every(f => f.spot && f.spot.intensity === 0)")
        dunkel = self._spot_zustand()
        self.assertTrue(all(v for v, _c, _i in dunkel),
                        "dunkler Spot wurde unsichtbar geschaltet — das wechselt "
                        "den Shader-Programmschluessel (VIZ-69)")
        self.assertEqual([c for _v, c, _i in dunkel], [c for _v, c, _i in hell],
                         "Hell/Dunkel hat die Schatten-Zuteilung veraendert")
        self.assertTrue(all(i == 0 for _v, _c, i in dunkel),
                        "dunkel muss weiterhin 'kein Licht' heissen (intensity 0)")

        # Wieder hell -> Licht kommt zurueck, ohne Sichtbarkeitswechsel.
        self._emit_until_true(
            lambda: self._bridge_obj.dmxBatch.emit(_batch(255, 80, 0, 255)),
            "Object.values(window.__lightos.fixtures)"
            ".every(f => f.spot && f.spot.intensity > 0)")
        self.assertTrue(all(v for v, _c, _i in self._spot_zustand()))

    def test_dunkel_beim_anlegen_ist_intensity_null(self):
        self._load_and_wait()
        payload = json.dumps([{"fid": 690010, "type": "par", "x": 0, "y": 4,
                               "z": 0, "r": 0, "g": 0, "b": 0, "intensity": 255}])
        self._emit_until_true(
            lambda: self._bridge_obj.allFixtures.emit(payload),
            "!!window.__lightos.fixtures['690010']")
        s = json.loads(self._eval(
            "JSON.stringify((function(){ const s = window.__lightos.fixtures['690010'].spot;"
            " return [s.visible, s.intensity]; })())"))
        self.assertEqual(s, [True, 0])

    # ── (2) Shadow-Map nur bei Lage-Aenderung ─────────────────────────────────
    def test_schatten_nur_bei_lageaenderung(self):
        self._rig_aufbauen()
        self.assertFalse(self._eval(
            "window.__lightos.shadowUpdateStats().autoUpdate"),
            "shadowMap.autoUpdate ist an — three.js zeichnet dann jeden Frame neu")
        # Einschwingen: Aufbau + erster DMX-Stand duerfen neu zeichnen.
        self._emit_until_true(
            lambda: self._bridge_obj.dmxBatch.emit(_batch(255, 255, 255, 255)),
            "Object.values(window.__lightos.fixtures).every(f => f.spot.intensity > 0)")
        self._tick()
        n0 = self._tick()
        self.assertEqual(self._tick(), n0, "ruhende Szene zeichnet Schatten neu")

        # Kamera-Orbit: Shadow-Maps sind kamera-unabhaengig.
        n_kam = self._eval(
            "(function(){ const L = window.__lightos; const c = L.view.activeCam;"
            " c.position.x += 3; c.position.z -= 2; c.lookAt(0, 1, 0);"
            " L.requestRender(); L.__renderTick();"
            " return L.shadowUpdateStats().neubauten; })()")
        self.assertEqual(n_kam, n0, "Kamerabewegung hat die Shadow-Map neu gezeichnet")

        # Reine Farb-/Dimmerwechsel inkl. 0 -> hell: Map speichert Tiefe, nicht Licht.
        self._emit_until_true(
            lambda: self._bridge_obj.dmxBatch.emit(_batch(0, 0, 0, 0)),
            "Object.values(window.__lightos.fixtures).every(f => f.spot.intensity === 0)")
        self.assertEqual(self._tick(), n0, "Abdunkeln hat die Shadow-Map neu gezeichnet")
        self._emit_until_true(
            lambda: self._bridge_obj.dmxBatch.emit(_batch(255, 0, 120, 255)),
            "Object.values(window.__lightos.fixtures).every(f => f.spot.intensity > 0)")
        self.assertEqual(self._tick(), n0, "Aufhellen hat die Shadow-Map neu gezeichnet")

        # Pan/Tilt bewegt Kopf + Lichtrichtung -> Schatten MUSS neu.
        self._emit_until_true(
            lambda: self._bridge_obj.dmxBatch.emit(_batch(255, 0, 120, 255, pan=20, tilt=200)),
            "(function(){ const f = window.__lightos.fixtures['%d'];"
            " return Math.abs(f._lastPanRad || 0) > 0.1; })()" % _FIDS[0])
        self.assertGreater(self._tick(), n0, "Pan/Tilt-Aenderung ohne Schatten-Neubau")

        # Fixture-Transform (Bridge-Direktpfad) -> ebenfalls neu.
        n1 = self._tick()
        self._bridge_obj.applyFixtureTransform.emit(json.dumps(
            {"fid": _FIDS[1], "x": 5.0, "y": 6.0, "z": 3.0,
             "rotX": 0, "rotY": 45, "rotZ": 0}))
        _pump(0.3)
        self.assertGreater(self._tick(), n1, "Fixture-Transform ohne Schatten-Neubau")


class Viz69QuelltextTest(unittest.TestCase):
    """Regeln, die sich am Quelltext pruefen lassen — laufen auch ohne GPU."""

    def _js(self, *teile):
        return open(os.path.join(_SCENE_SRC, *teile), encoding="utf-8").read()

    def test_kein_laufzeit_umschalten_von_spot_visible(self):
        for teile in (("fixtures", "builders.js"), ("fixtures", "fixtures.js")):
            code = "\n".join(z for z in self._js(*teile).splitlines()
                             if not z.lstrip().startswith("//"))
            self.assertNotRegex(code, r"\bspot\.visible\s*=",
                                f"{teile[-1]} schaltet spot.visible — kompiliert Shader neu")

    def test_castshadow_nur_in_der_budget_verteilung(self):
        """castShadow der Spots wird nur in syncSpotShadowBudget (Patchen)
        und beim Bau (false) gesetzt — nie im DMX-Pfad."""
        builders = self._js("fixtures", "builders.js")
        self.assertNotRegex(builders, r"spot\.castShadow\s*=")
        fixtures = self._js("fixtures", "fixtures.js")
        self.assertEqual(len(re.findall(r"spot\.castShadow\s*=", fixtures)), 2)

    def test_render_closure_bereitet_schatten_vor(self):
        app = self._js("app.js")
        self.assertIn("prepareShadowMap()", app)
        modul = self._js("scene", "shadow_update.js")
        self.assertIn("renderer.shadowMap.autoUpdate = false", modul)

    def test_schatten_dach_ist_acht(self):
        self.assertRegex(self._js("fixtures", "fixtures.js"),
                         r"(?m)^const SHADOW_SPOT_HARD_CAP = 8;")


if __name__ == "__main__":
    unittest.main()
