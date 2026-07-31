"""VIZ-14: der Platzier-Geist — End-to-End in einer ECHTEN QWebEngine.

Platzieren war blind: Rechtsklick in die Szene setzt das naechste noch
unplatzierte Geraet an diese Stelle — man sah WEDER wo es landet, NOCH ob es an
einer Traverse haengen wird, NOCH ueberhaupt, dass gerade etwas zu platzieren
ist. Der Geist zeigt alle drei Dinge, bevor geklickt wird (Plan §3
„Drag&Drop + Ghost-Preview, Auto-Hang auf Truss" — das Ghost-Stueck).

Belegt: (1) ohne offene Platzierung KEIN Geist (er darf nicht im Weg stehen,
wenn es nichts zu platzieren gibt), (2) mit offener Platzierung folgt er dem
Zeiger im Bau-Modus, (3) im Ansehen-Modus bleibt er weg (dort platziert man
nicht), (4) er faengt keine Eingabe — sonst schluckte ausgerechnet die Vorschau
den Klick, der platzieren soll.
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

    @Slot(str)
    def placeFixture(self, j):
        self._placed = getattr(self, "_placed", []) + [j]

    attrs["placeFixture"] = placeFixture
    attrs["requestFullResync"] = Signal()
    return type("MockVisualizerBridge", (QObject,), attrs)


_MockVisualizerBridge = _make_mock_bridge_class()


def _pump(seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        _app.processEvents()
        time.sleep(_POLL_INTERVAL_S)


class PlaceGhostSceneTest(unittest.TestCase):
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
        self._view.resize(800, 600)
        # Ohne echtes Layout liefert getBoundingClientRect() 0x0 und die
        # A3D-41-NaN-Waechter verwerfen jede Zeiger-Eingabe still (Lehre aus
        # dem Deselect-Test: der war zweimal rot, ohne dass Code fehlte).
        self._view.show()
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

    def _geist(self):
        return json.loads(self._eval("JSON.stringify(window.__lightos.placeGhostInfo())"))

    def _hover(self, x, y):
        """Zeiger bewegen — ueber den ECHTEN Hover-Pfad (globaler mousemove)."""
        self._eval(
            f"window.dispatchEvent(new MouseEvent('mousemove', "
            f"{{clientX: {x}, clientY: {y}, bubbles: true}})); true")
        _pump(0.2)

    def test_geist_folgt_dem_zeiger_nur_wenn_es_etwas_zu_platzieren_gibt(self):
        self._load_and_wait()
        self._eval("window.__lightos.setEditMode('edit'); true")

        # (1) nichts offen -> kein Geist
        self._hover(400, 320)
        self.assertFalse(self._geist()["sichtbar"],
                         "ohne offene Platzierung darf kein Geist im Weg stehen")

        # (2) etwas offen -> Geist folgt dem Zeiger
        self._eval("window.__lightos.setPlaceableCount(2); true")
        self._hover(360, 300)
        g1 = self._geist()
        self.assertTrue(g1["sichtbar"], "mit offener Platzierung fehlt der Geist")
        self._hover(520, 380)
        g2 = self._geist()
        self.assertTrue(g2["sichtbar"])
        self.assertNotEqual((round(g1["x"], 2), round(g1["z"], 2)),
                            (round(g2["x"], 2), round(g2["z"], 2)),
                            "der Geist folgt dem Zeiger nicht")

        # (4) er faengt keine Eingabe: ein Strahl von schraeg oben mitten
        # durch ihn darf ihn NICHT treffen — sonst schluckte ausgerechnet die
        # Vorschau den Klick, der platzieren soll. Gemessen, nicht behauptet.
        self.assertEqual(g2["raycastTreffer"], 0,
                         "der Geist faengt Strahlen ab und wuerde den "
                         "Platzier-Klick schlucken")

        # (3) Ansehen-Modus: kein Geist (dort platziert man nicht)
        self._eval("window.__lightos.setEditMode('view'); true")
        self._hover(400, 320)
        self.assertFalse(self._geist()["sichtbar"],
                         "im Ansehen-Modus hat der Geist nichts zu suchen")


if __name__ == "__main__":
    unittest.main()
