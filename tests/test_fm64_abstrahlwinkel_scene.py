"""FM-64 (Teil 1): der Abstrahlwinkel aus dem Profil bestimmt den 3D-Kegel.

Gemessen in echter QWebEngine an der Szene, die auch die App zeigt
(``stage_scene.html``): ein Geraet kommt mit ``beamAngleMin``/``beamAngleMax``
(voller Winkel in Grad, so wie ``VisualizerBridge._fixture_to_dict`` sie
schickt) und der Kegel hat danach genau diesen Winkel — fest, oder bei einer
Zoom-Spanne je nach Zoomwert zwischen eng und weit.

★ Gegenprobe: ohne Angabe (0/0) bleibt alles exakt wie vorher — PAR PI/10,
LED-Bar PI/14, Zoom ueber die festen Faktoren 0,45 .. 1,90.
"""
import json
import os
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineSettings, QWebEngineProfile
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtCore import QObject, QUrl, Signal, Slot
from _qt_lifecycle import destroy_webengine_view  # XPLAT-09
from _viz_dmx import dmx_push as _dmx_push  # VIZ-71: DMX per runJavaScript wie die Produktion

_app = QApplication.instance() or QApplication([])

_HTML_PATH = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "src", "ui", "visualizer", "stage_scene.html"))

_LOAD_TIMEOUT_S = 40.0
_POLL_TIMEOUT_S = 10.0
_POLL_INTERVAL_S = 0.05

_SIGNAL_SPECS = [
    ("fixtureAdded", (str,)), ("fixtureRemoved", (int,)), ("dmxBatch", (str,)),
    ("allFixtures", (str,)), ("settingsChanged", (str,)), ("viewModeChanged", (str,)),
    ("editModeChanged", (str,)), ("stageLoaded", (str,)), ("addStageObject", (str,)),
    ("addStageObjectData", (str,)), ("removeStageObject", (str,)),
    ("selectStageObject", (str,)), ("applyFixtureTransform", (str,)),
    ("alignSelected", (str,)), ("distributeSelected", (str,)),
    ("arrangeSelected", (str,)), ("cameraReset", ()),
    ("brightnessSignal", (float,)), ("brightnessAutoSignal", ()),
    ("updateStageObject", (str,)), ("resizeModeSignal", (bool,)),
    ("pixelRatioSignal", (float,)),
]


def _make_mock_bridge_class():
    attrs = {name: Signal(*arg_types) for name, arg_types in _SIGNAL_SPECS}

    @Slot()
    def requestFixtures(self):
        self._request_fixtures_calls = getattr(self, "_request_fixtures_calls", 0) + 1

    attrs["requestFixtures"] = requestFixtures

    @Slot(result=str)
    def pollControl(self):
        return getattr(self, "_poll_payload", "{}")

    attrs["pollControl"] = pollControl

    @Slot(str, str)
    def fixtureDockChanged(self, fid, dock):
        pass

    attrs["fixtureDockChanged"] = fixtureDockChanged

    @Slot(str)
    def fixtureTransformChanged(self, j):
        self._transforms = getattr(self, "_transforms", []) + [j]

    attrs["fixtureTransformChanged"] = fixtureTransformChanged
    attrs["requestFullResync"] = Signal()
    return type("MockVisualizerBridge", (QObject,), attrs)


_MockVisualizerBridge = _make_mock_bridge_class()


def _pump(seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        _app.processEvents()
        time.sleep(_POLL_INTERVAL_S)


class AbstrahlwinkelSceneTest(unittest.TestCase):
    def setUp(self):
        self.assertTrue(os.path.isfile(_HTML_PATH), f"stage_scene.html fehlt: {_HTML_PATH}")
        self._view = QWebEngineView()
        try:
            profile = self._view.page().profile()
            profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.NoCache)
            profile.setPersistentCookiesPolicy(
                QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies)
        except Exception:
            pass
        s = self._view.settings()
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        self._bridge_obj = _MockVisualizerBridge()
        self._channel = QWebChannel(self._view)
        self._channel.registerObject("bridge", self._bridge_obj)
        self._view.page().setWebChannel(self._channel)
        self._loaded_ok = []
        self._view.loadFinished.connect(self._loaded_ok.append)

    def tearDown(self):
        destroy_webengine_view(self._view, _pump)   # XPLAT-09
        self._view = None

    # ── Helfer ───────────────────────────────────────────────────────────────

    def _load_and_wait(self):
        self._loaded_ok.clear()
        url = QUrl.fromLocalFile(_HTML_PATH)
        # QA-86: Stufe fest, sonst waehlt die GPU-Probe des Testrechners
        # (Windows/ANGLE meldet 16 Textur-Einheiten -> 'low', Prisma gedeckelt).
        url.setQuery(f"v={int(time.time() * 1000)}&gputier=high")
        self._view.load(url)
        deadline = time.monotonic() + _LOAD_TIMEOUT_S
        while not self._loaded_ok and time.monotonic() < deadline:
            _app.processEvents()
            time.sleep(_POLL_INTERVAL_S)
        self.assertTrue(self._loaded_ok, "loadFinished nie ausgeloest (Timeout)")
        self.assertTrue(self._loaded_ok[-1], "loadFinished(ok=False)")
        self._poll_until_true("!!window.__lightosAppReady")
        # Auf die verdrahtete Bridge warten: tryChannel() laeuft asynchron
        # (setTimeout + Retry), ein emit davor verpufft ersatzlos.
        deadline = time.monotonic() + _POLL_TIMEOUT_S
        while time.monotonic() < deadline:
            if getattr(self._bridge_obj, "_request_fixtures_calls", 0) > 0:
                return
            _app.processEvents()
            time.sleep(_POLL_INTERVAL_S)
        self.fail("JS hat den WebChannel nicht verdrahtet")

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
        self.fail(f"Timeout beim Warten auf truthy '{js_expr}' (letzter: {last!r})")


    # ── Helfer ───────────────────────────────────────────────────────────────

    def _geraet(self, fid, typ="par", wmin=0, wmax=0):
        self._bridge_obj.fixtureAdded.emit(json.dumps({
            "fid": fid, "label": f"P{fid}", "type": typ, "model": typ,
            "nHeads": 0, "x": fid * 2.0, "y": 6.0, "z": 0.0,
            "rotX": 0, "rotY": 0, "rotZ": 0,
            "beamAngleMin": wmin, "beamAngleMax": wmax,
        }))
        self._poll_until_true(f"!!window.__lightos.fixtures[{fid}]")

    def _zoom(self, fid, zoom):
        _dmx_push(self._view, json.dumps([{
            "fid": fid, "intensity": 255, "r": 255, "g": 255, "b": 255,
            "pan": 128, "tilt": 128, "zoom": zoom,
        }]))
        _pump(0.4)

    def _mess(self, fid):
        """Halber Kegelwinkel (Grad) aus Geometrie x Weiten-Skalierung und
        der Winkel des SpotLights (Grad)."""
        roh = self._eval(
            f"(function(){{const f=window.__lightos.fixtures[{fid}];"
            f"const p=f.beam.geometry.parameters;"
            f"const k=(typeof f._optikK==='number')?f._optikK:1;"
            f"return JSON.stringify({{kegel: Math.atan(p.radius*k/p.height)*180/Math.PI,"
            f" bau: Math.atan(p.radius/p.height)*180/Math.PI,"
            f" spot: f.spot.angle*180/Math.PI, basisSpot: f.baseSpotAngle*180/Math.PI}});}})()")
        return json.loads(roh)

    # ── Messungen ────────────────────────────────────────────────────────────

    def test_fester_winkel_aus_dem_profil(self):
        self._load_and_wait()
        self._geraet(1, wmin=20, wmax=20)
        m = self._mess(1)
        self.assertAlmostEqual(m["bau"], 10.0, delta=0.05,
                               msg="Kegel nicht mit dem Profilwinkel (20° voll) gebaut")
        self.assertAlmostEqual(m["basisSpot"], 12.0, delta=0.05)

    def test_fester_winkel_ignoriert_den_zoomkanal(self):
        self._load_and_wait()
        self._geraet(1, wmin=20, wmax=20)
        self._zoom(1, 255)
        m = self._mess(1)
        self.assertAlmostEqual(m["kegel"], 10.0, delta=0.05)

    def test_zoom_spanne_laeuft_von_eng_nach_weit(self):
        self._load_and_wait()
        self._geraet(1, wmin=10, wmax=40)
        self.assertAlmostEqual(self._mess(1)["bau"], 12.5, delta=0.05,
                               msg="Grundstellung = Mitte der Spanne (25° voll)")
        self._zoom(1, 0)
        eng = self._mess(1)
        self.assertAlmostEqual(eng["kegel"], 5.0, delta=0.05, msg="DMX 0 = eng (10°)")
        self.assertAlmostEqual(eng["spot"], 6.0, delta=0.05)
        self._zoom(1, 255)
        weit = self._mess(1)
        self.assertAlmostEqual(weit["kegel"], 20.0, delta=0.05, msg="DMX 255 = weit (40°)")
        self.assertAlmostEqual(weit["spot"], 24.0, delta=0.05)

    def test_ohne_angabe_bleibt_alles_wie_vorher(self):
        """Gegenprobe: 0/0 = Ableitung aus Typ und Zoom wie bisher."""
        import math
        self._load_and_wait()
        self._geraet(1, typ="par")
        self._geraet(2, typ="led_bar")
        par, bar = self._mess(1), self._mess(2)
        self.assertAlmostEqual(par["bau"], 18.0, delta=0.05)    # PI/10
        self.assertAlmostEqual(bar["bau"], 180 / 14, delta=0.05)  # PI/14
        self.assertAlmostEqual(par["basisSpot"], 21.6, delta=0.05)
        self._zoom(1, 255)
        z = self._mess(1)
        # alter Faktor ZOOM_WEIT = 1,90 auf Radius UND SpotLight
        self.assertAlmostEqual(math.tan(math.radians(z["kegel"])),
                               1.90 * math.tan(math.radians(18.0)), delta=1e-3)
        self.assertAlmostEqual(z["spot"], 21.6 * 1.90, delta=0.05)


if __name__ == "__main__":
    unittest.main()

