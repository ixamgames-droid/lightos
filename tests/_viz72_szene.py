"""VIZ-72 / XPLAT-53: gemeinsames Geruest der drei Szenen-Testdateien.

``test_viz72_spot_pool_umgebung.py`` lief in der Windows-ARM64-CI 186-287 s —
bei 300 s Segmentlimit. Die Datei ist deshalb in drei geteilt
(Stufen/Vergabe, Bewegung, Umgebung); was alle drei brauchen, steht hier:
Mock-Bridge, Buehne, und die Basisklasse mit Seite laden, Auswerten, Rig, DMX.

Keine Tests in dieser Datei. Die Testdateien importieren ``QWebEngineView``
selbst — daran erkennen der Segment-Runner (WebEngine-Spur) und ``conftest``
(Exit-Haertung) ein WebEngine-Modul.
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
from _viz_dmx import dmx_push as _dmx_push

_app = QApplication.instance() or QApplication([])

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCENE_SRC = os.path.join(_REPO, "src", "ui", "visualizer", "scene_src")
_HTML_PATH = os.path.join(_REPO, "src", "ui", "visualizer", "stage_scene.html")

_LOAD_TIMEOUT_S = 40.0
_POLL_TIMEOUT_S = 10.0
_POLL_INTERVAL_S = 0.05

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
    return type("MockVisualizerBridgeViz72", (QObject,), attrs)


_MockBridge = _make_mock_bridge_class()


def _pump(seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        _app.processEvents()
        time.sleep(_POLL_INTERVAL_S)


_N = 12
_FIDS = tuple(720001 + i for i in range(_N))

# Buehne: drei gleiche Traversen (ein Material), ein Podest, eine Wand.
_BUEHNE = {"_reloadToken": 7272, "objects": [
    {"id": "t1", "type": "truss_h", "position": {"x": 0, "y": 6, "z": 0},
     "size": {"x": 8, "y": 0.4, "z": 0.4}, "color": "#a0a0a8", "rotation": 0},
    {"id": "t2", "type": "truss_h", "position": {"x": 0, "y": 6, "z": -3},
     "size": {"x": 8, "y": 0.4, "z": 0.4}, "color": "#a0a0a8", "rotation": 0},
    {"id": "t3", "type": "truss_v", "position": {"x": -4, "y": 3, "z": 0},
     "size": {"x": 0.4, "y": 6, "z": 0.4}, "color": "#a0a0a8", "rotation": 0},
    {"id": "p1", "type": "platform", "position": {"x": 0, "y": 0.5, "z": -2},
     "size": {"x": 10, "y": 1.0, "z": 6}, "color": "#3a2c24", "rotation": 0},
    {"id": "w1", "type": "wall", "position": {"x": 0, "y": 4, "z": -6},
     "size": {"x": 12, "y": 8, "z": 0.3}, "color": "#14141c", "rotation": 0.3},
]}


class Viz72SzeneBasis(unittest.TestCase):
    """Frischer ``QWebEngineView`` je Test, ECHTE Produktiv-Seite."""

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
        self._loaded_ok = []
        self._view.loadFinished.connect(self._loaded_ok.append)

    def tearDown(self):
        destroy_webengine_view(self._view, _pump)
        self._view = None

    # ── Helfer ───────────────────────────────────────────────────────────────
    def _load_and_wait(self, tier="high"):
        url = QUrl.fromLocalFile(_HTML_PATH)
        url.setQuery(f"v={int(time.time() * 1000)}&gputier={tier}")
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

    def _json(self, js_expr):
        return json.loads(self._eval(f"JSON.stringify({js_expr})"))

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

    def _tick(self):
        self._eval("(function(){ const L = window.__lightos; L.requestRender();"
                   " L.__renderTick(); return 1; })()")

    def _rig(self, n=_N, tier="high", typ="par"):
        self._load_and_wait(tier)
        payload = json.dumps([
            {"fid": 720001 + i, "type": typ, "x": i * 1.5 - 8, "y": 6, "z": 0,
             "r": 0, "g": 0, "b": 0, "intensity": 0} for i in range(n)])
        self._emit_until_true(
            lambda: self._bridge_obj.allFixtures.emit(payload),
            f"Object.keys(window.__lightos.fixtures).length === {n}", timeout_s=10.0)

    def _dmx(self, werte):
        """werte: {fid: intensitaet}; Farbe weiss."""
        batch = json.dumps([{"fid": f, "r": 255, "g": 255, "b": 255, "intensity": i,
                             "pan": 128, "tilt": 128} for f, i in werte.items()])
        _dmx_push(self._view, batch)
        probe = next(iter(werte))
        self._poll_until_true(
            "(function(){ const f = window.__lightos.fixtures['%d'];"
            " return Math.abs(f.spot.intensity - %f) < 1e-6; })()"
            % (probe, (werte[probe] / 255.0 * 3.0) if werte[probe] else 0.0))
        self._tick()

    def _pool(self):
        return self._json("window.__lightos.spotPoolInfo()")
