"""VIZ-14 (Fixture-Labels): persistente 3D-Labels ("#<fid> <Kurzname>") als Sprite-
Kind der Fixture-root-Gruppe, zoom-distanz-gegated — End-to-End in echter QWebEngine.

Belegt: (Ladung 1) Label wird gebaut, haengt an der Fixture-Gruppe, traegt den Text,
wird beim Entfernen mit aufgeraeumt, und fuehrt KEINEN Dauer-Render ein (der Zoom-Gate
piggybackt den Kamera-Dirty-Pfad, kein requestRender/Live-Probe); (Ladung 2) die
Sichtbarkeit haengt an der Kamera-Distanz (nah = sichtbar, fern = aus).

Eigene Isolate-Datei, bewusst NUR 2 Seiten-Ladungen (>~3 QWebEngine-Vollladungen/
Prozess kippen den offscreen-Chromium-Renderer) — Checks pro Ladung gebuendelt.
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
    ("alignSelected", (str,)), ("distributeSelected", (str,)), ("cameraReset", ()),
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
    attrs["requestFullResync"] = Signal()
    return type("MockVisualizerBridge", (QObject,), attrs)


_MockVisualizerBridge = _make_mock_bridge_class()

# Poll-"fixtures" ist ein JSON-STRING (bridge.js JSON.parse't ihn). Minimal-Fixture.
_FIXTURE = {"fid": 2, "type": "par", "x": 0, "y": 2, "z": 0, "label": "KEY"}
_FIXTURES_POLL = json.dumps({"fixtures": json.dumps([_FIXTURE])})
_REMOVE_POLL = json.dumps({"events": [{"t": "fixtureRemoved", "fid": 2}]})


def _pump(seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        _app.processEvents()
        time.sleep(_POLL_INTERVAL_S)


class FixtureLabelsSceneTest(unittest.TestCase):
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
        try:
            self._view.deleteLater()
        except Exception:
            pass
        _pump(0.2)

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

    def _stats(self):
        return json.loads(self._eval("JSON.stringify(window.__lightos.renderStats())"))

    def _tick(self):
        self._eval("window.__lightos.__renderTick(); true")

    def _settle(self, max_rounds=40):
        last = None
        for _ in range(max_rounds):
            self._tick()
            s = self._stats()
            if (not s["dirty"]) and (not s["live"]) and s["count"] == last:
                return s
            last = s["count"]
        self.fail(f"Render-Loop stabilisiert nicht: {self._stats()}")

    def test_label_builds_attaches_text_and_cleans_up_without_perpetual_render(self):
        self._load_and_wait()
        self._poll_until_true("!!window.__lightosAppReady")
        # Fixture via Poll ("fixtures"-Resync-Pfad) hinzufuegen.
        self._bridge_obj._poll_payload = _FIXTURES_POLL
        self._poll_until_true("!!(window.__lightos.fixtures && window.__lightos.fixtures['2'])", timeout_s=8.0)
        F = "window.__lightos.fixtures['2']"
        # Label existiert, ist ein Sprite mit Textur, haengt an der Fixture-Gruppe.
        self.assertEqual(self._eval(f"{F}.label && {F}.label.type"), "Sprite")
        self.assertEqual(self._eval(f"!!({F}.label.material && {F}.label.material.map)"), True,
                         "Label-Sprite hat keine Textur-Map")
        self.assertEqual(self._eval(f"{F}.label.parent === {F}.group"), True,
                         "Label haengt nicht an der Fixture-Gruppe (folgt sonst nicht)")
        # Text traegt fid + Kurzname.
        txt = self._eval(f"{F}.label.userData.text")
        self.assertIn("#2", str(txt))
        self.assertIn("KEY", str(txt))
        # ★ Regressions-Guard: Labels fuehren KEINEN Dauer-Render ein (Loop faellt in Idle).
        s = self._settle()
        self.assertFalse(s["live"], "Fixture-Labels fuehrten eine Dauer-Animation ein")
        c = s["count"]
        for _ in range(3):
            self._tick()
        self.assertEqual(self._stats()["count"], c,
                         "Fixture-Labels rendern dauerhaft (Gate offen ohne Kamerabewegung)")
        # ★ Textur-Leak-Guard: dispose der Label-Map beim Entfernen instrumentieren
        # (disposeObj disposed material.map NICHT -> ohne den expliziten Dispose
        # leckt jede Entfernung/jeder Resync eine CanvasTexture; genau das absichern).
        self._eval(
            "window.__labelMapDisposed = false;"
            "var _m = window.__lightos.fixtures['2'].label.material.map;"
            "var _orig = _m.dispose.bind(_m);"
            "_m.dispose = function(){ window.__labelMapDisposed = true; return _orig(); };"
            "true")
        # Aufraeumen: Fixture entfernen -> Label verschwindet mit der Gruppe.
        self._bridge_obj._poll_payload = _REMOVE_POLL
        self._poll_until_true("window.__lightos.fixtures['2'] === undefined", timeout_s=8.0)
        self.assertEqual(self._eval("window.__labelMapDisposed === true"), True,
                         "Label-Textur-Map wurde beim Entfernen NICHT disposed (Leck)")
        self._settle()   # nach dem Entfernen wieder Idle

    def test_label_visibility_is_camera_distance_gated(self):
        self._load_and_wait()
        self._poll_until_true("!!window.__lightosAppReady")
        self._bridge_obj._poll_payload = _FIXTURES_POLL
        self._poll_until_true("!!(window.__lightos.fixtures && window.__lightos.fixtures['2'])", timeout_s=8.0)
        self._settle()
        L = "window.__lightos.fixtures['2'].label"
        # Kamera nah an die Fixture (~6 m) -> Label sichtbar.
        self._eval("window.__lightos.view.activeCam.position.set(0, 2, 6); true")
        self._tick()
        self.assertEqual(self._eval(f"{L}.visible"), True, "Label nah nicht sichtbar")
        # Kamera weit weg (~200 m) -> Label aus (Auto-Declutter).
        self._eval("window.__lightos.view.activeCam.position.set(0, 2, 200); true")
        self._tick()
        self.assertEqual(self._eval(f"{L}.visible"), False, "Label fern nicht ausgeblendet")
        # Der Gate selbst erzeugt keinen Dauer-Render.
        s = self._settle()
        c = s["count"]
        for _ in range(3):
            self._tick()
        self.assertEqual(self._stats()["count"], c, "Zoom-Gate rendert dauerhaft")


if __name__ == "__main__":
    unittest.main()
