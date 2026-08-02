"""VIZ-BEAM-OCCLUSION Teil 2 in einer ECHTEN Szene: der Kegel endet am Podest.

Die reine Rechnung steht in `test_viz_beam_stop.py`. Sie beweist, dass die
richtige Zahl gewaehlt wird — nicht, dass der Strahl den Koerper ueberhaupt
findet. Genau dazwischen sitzen die Fehler, die man erst am Geraet sieht:
falsche Eigenschaft (`stageObjects[id].mesh`), falsches Vorzeichen der
Richtung, ein `near`, das das eigene Gehaeuse trifft.

Deshalb hier der volle Weg: Buehnenobjekt anlegen -> Scheinwerfer darueber ->
Kegellaenge messen. Die Gegenprobe steht IM SELBEN Test: derselbe Scheinwerfer
ohne Podest darunter muss laenger strahlen. Ein Test, der nur „kurz" prueft,
waere auch dann gruen, wenn der Kegel aus einem ganz anderen Grund kurz ist.

EIGENE, schlanke Datei und EINE Ansicht fuer die ganze Klasse: jede
QWebEngine-Ladung kostet einen WebGL-Kontext, und der ist auf diesem Rechner
knapp (XPLAT-17).
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


class BeamStopSceneTest(unittest.TestCase):
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
        url.setQuery(f"v={int(time.time() * 1000)}")
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


    # ── Szenen-Helfer ────────────────────────────────────────────────────────

    def _mover(self, fid, x, z, y=6.0):
        """Moving Head, senkrecht nach unten gerichtet (Tilt 0 = gerade runter)."""
        self._bridge_obj.fixtureAdded.emit(json.dumps({
            "fid": fid, "label": f"MH{fid}", "type": "moving_head",
            "model": "moving_head", "nHeads": 0, "x": x, "y": y, "z": z,
            "rotX": 0, "rotY": 0, "rotZ": 0,
        }))
        self._poll_until_true(f"!!window.__lightos.fixtures[{fid}]")

    def _podest(self, sid, x, z, oberkante):
        """Podest mit Oberkante bei `oberkante` Metern."""
        hoehe = 0.4
        self._bridge_obj.addStageObjectData.emit(json.dumps({
            "id": sid, "type": "platform",
            "position": {"x": x, "y": oberkante - hoehe / 2, "z": z},
            "size": {"x": 3.0, "y": hoehe, "z": 3.0},
        }))
        self._poll_until_true(f"!!window.__lightos.stageObjects['{sid}']")

    def _dmx(self, fid, intensity=255):
        self._bridge_obj.dmxBatch.emit(json.dumps([{
            "fid": fid, "intensity": intensity, "r": 255, "g": 255, "b": 255,
            "pan": 128, "tilt": 128,
        }]))
        _pump(0.4)

    def _kegellaenge(self, fid):
        """Sichtbare Kegellaenge in Metern: Grundlaenge x Y-Skalierung."""
        return self._eval(
            f"(function(){{const f=window.__lightos.fixtures[{fid}];"
            f"return (f && f.beam) ? f.baseBeamLength * f.beam.scale.y : null;}})()")

    def _fleckhoehe(self, fid):
        return self._eval(
            f"(function(){{const f=window.__lightos.fixtures[{fid}];"
            f"return (f && f.floorSpot) ? f.floorSpot.position.y : null;}})()")

    # ── Die Messung ──────────────────────────────────────────────────────────

    def test_kegel_endet_am_podest_und_nicht_erst_am_boden(self):
        self._load_and_wait()

        # (1) Gegenprobe zuerst: freier Boden unter dem Scheinwerfer.
        self._mover(1, x=-4.0, z=0.0, y=6.0)
        self._dmx(1)
        frei = self._kegellaenge(1)
        self.assertIsNotNone(frei, "kein Kegel gebaut")
        self.assertGreater(frei, 1.0,
                           "Vorbedingung: ohne Hindernis strahlt er weit")

        # (2) Derselbe Aufbau MIT Podest darunter, Oberkante 1,5 m.
        self._podest("podest1", x=4.0, z=0.0, oberkante=1.5)
        self._mover(2, x=4.0, z=0.0, y=6.0)
        self._dmx(2)
        gestoppt = self._kegellaenge(2)
        self.assertIsNotNone(gestoppt)

        self.assertLess(
            gestoppt, frei,
            f"Kegel ueber dem Podest ({gestoppt:.2f} m) ist nicht kuerzer als "
            f"ueber freiem Boden ({frei:.2f} m) — der Strahl schiesst hindurch")
        # Von 6 m Haenge auf eine Oberkante bei 1,5 m sind es 4,5 m; mit
        # Toleranz fuer den Abstand Sockel<->Linse.
        self.assertLess(gestoppt, 5.2,
                        f"Kegel endet zu spaet ({gestoppt:.2f} m)")

    def test_lichtfleck_liegt_auf_dem_podest(self):
        """Der Fleck gehoert auf die Flaeche, die das Licht abbekommt — sonst
        leuchtet die Ansicht eine Stelle aus, die im Schatten des Podests liegt."""
        self._load_and_wait()
        self._mover(3, x=-4.0, z=2.0, y=6.0)
        self._dmx(3)
        am_boden = self._fleckhoehe(3)
        self.assertIsNotNone(am_boden)
        self.assertLess(am_boden, 0.2, "Vorbedingung: Fleck liegt am Boden")

        self._podest("podest2", x=4.0, z=2.0, oberkante=1.5)
        self._mover(4, x=4.0, z=2.0, y=6.0)
        self._dmx(4)
        auf_podest = self._fleckhoehe(4)
        self.assertGreater(
            auf_podest, 1.0,
            f"Lichtfleck liegt bei y={auf_podest} statt auf der Podest-Oberkante")

    def test_nach_oben_gerichtet_behaelt_den_vollen_kegel(self):
        """Die Falle aus der reinen Rechnung, hier in der Szene: „nichts
        getroffen" darf nicht zu Laenge 0 werden."""
        self._load_and_wait()
        self._mover(5, x=0.0, z=-4.0, y=1.0)
        self._dmx(5)
        # Kopf um 180 Grad kippen -> strahlt nach oben, trifft nichts.
        self._eval(
            "(function(){const f=window.__lightos.fixtures[5];"
            "if(f&&f.head){f.head.rotation.x=Math.PI;f.head.updateMatrixWorld();}"
            "return true;})()")
        self._dmx(5)
        laenge = self._kegellaenge(5)
        self.assertIsNotNone(laenge)
        self.assertGreater(laenge, 1.0,
                           f"nach oben gerichteter Kegel auf {laenge} geschrumpft")


if __name__ == "__main__":
    unittest.main()
