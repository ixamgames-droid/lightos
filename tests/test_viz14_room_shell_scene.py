"""VIZ-14: neutrale, abschaltbare Raum-Huelle — End-to-End in echter QWebEngine.

★ Das Item war ein WIDERSPRUCH, kein Feature-Wunsch: Plan §3 fuehrt „Raum-Box
statt Void" als *Hoch*, `grid_floor.js` haelt aber ausdruecklich fest, dass die
vorgerenderten Kulissen (theatre/rock/box) BEWUSST entfernt wurden und der
Visualizer leer startet. David hat 2026-07-31 entschieden: neutrale Huelle,
abschaltbar, Default AUS.

Der Test sichert genau die Eigenschaften ab, die sie von einer Kulisse trennen:

1. **Default AUS** — der Visualizer startet unveraendert leer.
2. **Sie faengt keine Eingabe** (`raycast` ist ein No-Op). Sonst bliebe der
   Klick an einer Wand haengen, statt den Boden zu treffen — und Zielen,
   Marquee und Platzieren waeren im Raum kaputt.
3. **Sie waechst mit dem Inhalt.** Eine feste Groesse wuerde bei einem grossen
   Rig mitten durchschneiden; das waere schlimmer als gar keine Huelle.
4. **In der 2D-Draufsicht ist sie immer aus** — die Decke laege dort genau
   zwischen Kamera und Buehne.
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
    attrs["requestFullResync"] = Signal()
    return type("MockVisualizerBridge", (QObject,), attrs)


_MockVisualizerBridge = _make_mock_bridge_class()


def _pump(seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        _app.processEvents()
        time.sleep(_POLL_INTERVAL_S)


class RoomShellSceneTest(unittest.TestCase):
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
        self._bridge_obj = _MockVisualizerBridge()
        self._channel = QWebChannel(self._view)
        self._channel.registerObject("bridge", self._bridge_obj)
        self._view.page().setWebChannel(self._channel)
        self._loaded_ok = []
        self._view.loadFinished.connect(self._loaded_ok.append)

    def tearDown(self):
        destroy_webengine_view(self._view, _pump)   # XPLAT-09
        self._view = None

    def _load_and_wait(self):
        self._loaded_ok.clear()
        url = QUrl.fromLocalFile(_HTML_PATH)
        url.setQuery(f"v={int(time.time() * 1000)}")
        self._view.load(url)
        deadline = time.monotonic() + _LOAD_TIMEOUT_S
        while not self._loaded_ok and time.monotonic() < deadline:
            _app.processEvents()
            time.sleep(_POLL_INTERVAL_S)
        self.assertTrue(self._loaded_ok and self._loaded_ok[-1], "Page nicht geladen")
        self._poll_until_true("!!window.__lightosAppReady")
        deadline = time.monotonic() + _POLL_TIMEOUT_S
        while time.monotonic() < deadline:
            if getattr(self._bridge_obj, "_request_fixtures_calls", 0) > 0:
                return
            _app.processEvents()
            time.sleep(_POLL_INTERVAL_S)
        self.fail("JS hat den WebChannel nicht verdrahtet")

    def _eval(self, js):
        box = []
        self._view.page().runJavaScript(js, lambda r: box.append(r))
        deadline = time.monotonic() + _POLL_TIMEOUT_S
        while not box and time.monotonic() < deadline:
            _app.processEvents()
            time.sleep(_POLL_INTERVAL_S)
        self.assertTrue(box, f"runJavaScript ohne Callback: {js}")
        return box[0]

    def _poll_until_true(self, js, timeout_s=_POLL_TIMEOUT_S):
        deadline = time.monotonic() + timeout_s
        last = None
        while time.monotonic() < deadline:
            last = self._eval(js)
            if last:
                return last
            time.sleep(_POLL_INTERVAL_S)
        self.fail(f"Timeout bei '{js}' (letzter: {last!r})")

    def _huelle(self):
        roh = self._eval("JSON.stringify(window.__lightos.roomShellInfo())")
        return json.loads(roh) if roh and roh != "null" else None

    def _settings(self, **kw):
        self._bridge_obj.settingsChanged.emit(json.dumps(kw))
        _pump(0.3)

    def _add(self, fid, x, z, y=3.0):
        self._bridge_obj.fixtureAdded.emit(json.dumps({
            "fid": fid, "label": f"P{fid}", "type": "par", "model": "par",
            "nHeads": 0, "x": x, "y": y, "z": z,
            "rotX": 0, "rotY": 0, "rotZ": 0}))

    def test_huelle_ist_neutral_abschaltbar_und_waechst_mit(self):
        self._load_and_wait()

        # (1) Default AUS — der Visualizer startet unveraendert leer
        self.assertIsNone(self._huelle(),
                          "die Raum-Huelle darf nicht ungefragt erscheinen")

        # Kleines Rig
        self._add(1, -3, -2)
        self._add(2, 3, 2)
        self._poll_until_true("Object.keys(window.__lightos.fixtures).length === 2")

        self._settings(showRoom=True)
        klein = self._huelle()
        self.assertIsNotNone(klein, "eingeschaltet muss eine Huelle da sein")

        # (2) faengt KEINE Eingabe. Gemessen mit einem ECHTEN Strahl aus der
        # Raummitte auf die Wand zu — eine Selbstauskunft waere kein Beleg.
        self.assertEqual(klein["raycastTreffer"], 0,
                         "die Huelle faengt Strahlen ab: Klicken, Zielen und "
                         "Marquee blieben an der Wand haengen")

        # (3) waechst mit dem Inhalt: weit auseinander -> deutlich groesser
        self._add(3, -25, -18, y=9.0)
        self._add(4, 25, 18, y=9.0)
        self._poll_until_true("Object.keys(window.__lightos.fixtures).length === 4")
        self._settings(showRoom=True)          # Neuaufbau anstossen
        gross = self._huelle()
        self.assertIsNotNone(gross)
        self.assertGreater(gross["breite"], klein["breite"] + 10,
                           f"Huelle waechst nicht mit: {klein} -> {gross}")
        self.assertGreater(gross["hoehe"], klein["hoehe"],
                           "hoehere Geraete brauchen mehr Kopffreiheit")

        # (4) 2D-Draufsicht: immer aus
        self._eval("window.__lightos.setViewMode('2D'); true")
        _pump(0.3)
        self.assertIsNone(self._huelle(),
                          "in der Draufsicht laege die Decke zwischen Kamera und Buehne")
        self._eval("window.__lightos.setViewMode('3D'); true")
        _pump(0.3)
        self.assertIsNotNone(self._huelle(), "zurueck in 3D muss sie wieder da sein")

        # ausschalten raeumt sie weg
        self._settings(showRoom=False)
        self.assertIsNone(self._huelle())


if __name__ == "__main__":
    unittest.main()
