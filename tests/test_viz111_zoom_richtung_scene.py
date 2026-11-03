"""VIZ-111 (Teil 1+2): Zoom-Laufrichtung je Profil im 3D-Kegel.

Gemessen in echter QWebEngine an ``stage_scene.html``: ein Geraet kommt mit
``zoomInverted`` (so wie ``VisualizerBridge._fixture_to_dict`` es schickt).
Dann ergibt DMX 0 den WEITEN und DMX 255 den ENGEN Kegel — mit den festen
Typ-Faktoren 0,45/1,90 ebenso wie mit einer FM-64-Spanne eng..weit.

★ Gegenprobe: ohne Angabe (Feld fehlt bzw. false) bleibt alles wie vorher.
"""
import json
import math
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


class ZoomRichtungSceneTest(unittest.TestCase):
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

    def _geraet(self, fid, wmin=0, wmax=0, umgekehrt=None):
        d = {"fid": fid, "label": f"P{fid}", "type": "par", "model": "par",
             "nHeads": 0, "x": fid * 2.0, "y": 6.0, "z": 0.0,
             "rotX": 0, "rotY": 0, "rotZ": 0,
             "beamAngleMin": wmin, "beamAngleMax": wmax}
        if umgekehrt is not None:
            d["zoomInverted"] = umgekehrt
        self._bridge_obj.fixtureAdded.emit(json.dumps(d))
        self._poll_until_true(f"!!window.__lightos.fixtures[{fid}]")

    def _zoom(self, fid, zoom):
        _dmx_push(self._view, json.dumps([{
            "fid": fid, "intensity": 255, "r": 255, "g": 255, "b": 255,
            "pan": 128, "tilt": 128, "zoom": zoom,
        }]))
        _pump(0.4)

    def _mess(self, fid):
        """Halber Kegelwinkel (Grad) aus Geometrie x Weiten-Skalierung und der
        Winkel des SpotLights (Grad)."""
        roh = self._eval(
            f"(function(){{const f=window.__lightos.fixtures[{fid}];"
            f"const p=f.beam.geometry.parameters;"
            f"const k=(typeof f._optikK==='number')?f._optikK:1;"
            f"return JSON.stringify({{kegel: Math.atan(p.radius*k/p.height)*180/Math.PI,"
            f" spot: f.spot.angle*180/Math.PI}});}})()")
        return json.loads(roh)

    def _tan_faktor(self, kegel_grad, basis_grad=18.0):
        return (math.tan(math.radians(kegel_grad))
                / math.tan(math.radians(basis_grad)))

    # ── Messungen ────────────────────────────────────────────────────────────

    def test_umgekehrt_ohne_profilwinkel_dmx0_ist_weit(self):
        """Typ-Faktoren: DMX 0 -> 1,90 (weit), DMX 255 -> 0,45 (eng)."""
        self._load_and_wait()
        self._geraet(1, umgekehrt=True)
        self._zoom(1, 0)
        weit = self._mess(1)
        self.assertAlmostEqual(self._tan_faktor(weit["kegel"]), 1.90, delta=1e-3,
                               msg="umgekehrtes Profil: DMX 0 muss WEIT sein")
        self.assertAlmostEqual(weit["spot"], 21.6 * 1.90, delta=0.05)
        self._zoom(1, 255)
        eng = self._mess(1)
        self.assertAlmostEqual(self._tan_faktor(eng["kegel"]), 0.45, delta=1e-3)
        self.assertAlmostEqual(eng["spot"], 21.6 * 0.45, delta=0.05)

    def test_umgekehrt_mit_fm64_spanne(self):
        """FM-64-Spanne 10..40°: umgekehrt ist DMX 0 = 40°, DMX 255 = 10°."""
        self._load_and_wait()
        self._geraet(1, wmin=10, wmax=40, umgekehrt=True)
        self._zoom(1, 0)
        weit = self._mess(1)
        self.assertAlmostEqual(weit["kegel"], 20.0, delta=0.05)
        self.assertAlmostEqual(weit["spot"], 24.0, delta=0.05)
        self._zoom(1, 255)
        eng = self._mess(1)
        self.assertAlmostEqual(eng["kegel"], 5.0, delta=0.05)
        self.assertAlmostEqual(eng["spot"], 6.0, delta=0.05)

    def test_fester_winkel_bleibt_fest_auch_umgekehrt(self):
        self._load_and_wait()
        self._geraet(1, wmin=20, wmax=20, umgekehrt=True)
        for z in (0, 255):
            self._zoom(1, z)
            self.assertAlmostEqual(self._mess(1)["kegel"], 10.0, delta=0.05)

    def test_gegenprobe_ohne_angabe_unveraendert(self):
        """Feld fehlt bzw. false: DMX 0 eng, DMX 255 weit — wie vor VIZ-111."""
        self._load_and_wait()
        self._geraet(1)                       # Feld fehlt ganz
        self._geraet(2, umgekehrt=False)
        self._geraet(3, wmin=10, wmax=40)     # FM-64 ohne Umkehr
        for fid in (1, 2):
            self._zoom(fid, 0)
            self.assertAlmostEqual(self._tan_faktor(self._mess(fid)["kegel"]),
                                   0.45, delta=1e-3)
            self._zoom(fid, 255)
            self.assertAlmostEqual(self._tan_faktor(self._mess(fid)["kegel"]),
                                   1.90, delta=1e-3)
        self._zoom(3, 0)
        self.assertAlmostEqual(self._mess(3)["kegel"], 5.0, delta=0.05)
        self._zoom(3, 255)
        self.assertAlmostEqual(self._mess(3)["kegel"], 20.0, delta=0.05)


if __name__ == "__main__":
    unittest.main()
