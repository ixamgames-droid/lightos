"""VIZ-87: Stufenwechsel mit grosser Buehne — kein doppelter Neubau, das
Pending-Gate bekommt sein Echo sofort.

Testbericht (Windows, Buehnen-Show mit 23 Elementen): jeder Wechsel der
Render-Qualitaet dauerte 4-11 s, im Log stand "pending stage snapshot blieb aus
- Gate geoeffnet".

Hergang: ein Stufenwechsel laedt die Seite neu. Die frische Seite baut die
Buehne sofort aus dem Poll-Zustand (Token N). 400 ms nach ``loadFinished``
schickt Python dieselbe Buehne mit neuem Token N+1 (``_apply_stage`` setzt
dabei das Pending-Gate) — und ``loadStageJson`` riss bei neuem Token ALLES ab
und baute neu. Danach kam jedes Element noch zweimal als ``addStageData``
(``push_stage_definition`` + Reassert nach 1,2 s), und
``updateStageObjectProps`` baute dabei Trussen, LED-Wand, Treppe usw. auch bei
unveraenderter Groesse neu. Unter ANGLE (Shader-Uebersetzung nach HLSL) kostet
das Sekunden; das Echo, auf das das Gate wartet, kam erst nach dem zweiten
Neubau — oft nach dem 6-s-Rueckfall.

Jetzt: gleiche Buehne + neuer Token -> Token uebernehmen, Echo schicken, nichts
neu bauen. ``addStageData`` ohne Aenderung baut nichts neu. Geprueft an der
echten Seite (offscreen) ueber Mesh-Identitaeten und die Echos an die Bruecke.
"""
import json
import os
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, QUrl, Signal, Slot
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication

from _qt_lifecycle import destroy_webengine_view, destroy_all_top_level_widgets  # noqa: E402
import pytest

_app = QApplication.instance() or QApplication([])

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_HTML_PATH = os.path.join(_REPO, "src", "ui", "visualizer", "stage_scene.html")


@pytest.fixture(autouse=True)
def _keine_fenster_lecks():
    yield
    destroy_all_top_level_widgets(QApplication.instance())


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
        # Einmal-Events ueber den Pull-Kanal — wie in der App: Python->JS-
        # Signale kommen nach dem Laden nicht zuverlaessig an (bridge.js).
        if not self.events:
            return "{}"
        out, self.events = self.events, []
        return json.dumps({"events": out})

    @Slot(str)
    def reportGpuTier(self, tier):
        self.verbunden = True

    @Slot(str)
    def stageListChanged(self, j):
        self.echos.append(json.loads(j))

    attrs.update(requestFixtures=requestFixtures, pollControl=pollControl,
                 reportGpuTier=reportGpuTier, stageListChanged=stageListChanged,
                 requestFullResync=Signal())
    return type("MockBridgeViz87", (QObject,), attrs)


_MockBridge = _mock_bridge_class()


def _pump(seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        _app.processEvents()
        time.sleep(0.02)


def _buehne(token, dx=0.0, n=12):
    typen = ["platform", "truss_h", "truss_v", "wall", "led_wall", "speaker",
             "riser_stairs", "bar_counter", "beer_table", "high_table", "foh_desk",
             "dj_booth"]
    objekte = []
    for i in range(n):
        objekte.append({
            "id": f"el{i:02d}", "type": typen[i % len(typen)],
            "position": {"x": (i % 4) * 3.0 + dx, "y": 0.5, "z": (i // 4) * 3.0},
            "size": {"x": 2.0, "y": 1.0, "z": 1.5},
            "rotation": 0.25 * i, "color": "#445566", "name": f"Element {i}",
        })
    return {"name": "Gross", "objects": objekte, "fixtures": [], "_reloadToken": token}


class StufenwechselBuehneTest(unittest.TestCase):
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
        self._bridge_obj.echos = []
        self._bridge_obj.events = []
        self._bridge_obj.verbunden = False
        self._channel = QWebChannel(self._view)
        self._channel.registerObject("bridge", self._bridge_obj)
        self._view.page().setWebChannel(self._channel)
        self._ok = []
        self._view.loadFinished.connect(self._ok.append)
        url = QUrl.fromLocalFile(_HTML_PATH)
        url.setQuery(f"v={int(time.time() * 1000)}&gputier=low")
        self._view.load(url)
        ende = time.monotonic() + 40
        while not self._ok and time.monotonic() < ende:
            _app.processEvents()
            time.sleep(0.05)
        self.assertTrue(self._ok and self._ok[-1])
        ende = time.monotonic() + 10
        while time.monotonic() < ende and not self._eval("!!window.__lightosAppReady"):
            time.sleep(0.05)
        # Bruecke verbunden? (Echos gehen ueber bridge.stageListChanged.) Der
        # Connect meldet als Erstes die Stufe (reportGpuTier).
        ende = time.monotonic() + 15
        while time.monotonic() < ende and not self._bridge_obj.verbunden:
            _app.processEvents()
            time.sleep(0.02)
        self.assertTrue(self._bridge_obj.verbunden, "WebChannel nie verbunden")
        _pump(0.3)

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

    def _laden(self, buehne):
        self._eval("window.__lightos.loadStageJson(%s); 1" % json.dumps(json.dumps(buehne)))

    def _add_stage_data(self, d):
        self._bridge_obj.events.append({"t": "addStageData", "j": json.dumps(d)})

    def _meshes(self):
        return json.loads(self._eval(
            "(function(){ const o = {}; const S = window.__lightos.stageObjects;"
            " for (const k in S) o[k] = S[k].mesh.uuid; return JSON.stringify(o); })()"))

    def _warte_echo(self, token, timeout=5.0):
        ende = time.monotonic() + timeout
        while time.monotonic() < ende:
            if any(e.get("_reloadToken") == token for e in self._bridge_obj.echos):
                return [e for e in self._bridge_obj.echos if e.get("_reloadToken") == token]
            _app.processEvents()
            time.sleep(0.02)
        self.fail(f"kein Echo mit Token {token}: {[e.get('_reloadToken') for e in self._bridge_obj.echos]}")

    def test_gleiche_buehne_neuer_token_kein_neubau_aber_echo(self):
        self._laden(_buehne(1))
        self._warte_echo(1)
        vorher = self._meshes()
        self.assertEqual(len(vorher), 12)
        # Der Stufenwechsel-Fall: dieselbe Buehne mit neuem Token.
        self._laden(_buehne(2))
        echos = self._warte_echo(2)
        self.assertEqual(sorted(o["id"] for o in echos[-1]["objects"]), sorted(vorher),
                         "Echo traegt die vollstaendige Buehne — das Gate oeffnet")
        self.assertEqual(self._meshes(), vorher, "dieselbe Buehne darf nicht neu gebaut werden")

    def test_geaenderte_buehne_wird_neu_gebaut(self):
        self._laden(_buehne(1))
        self._warte_echo(1)
        vorher = self._meshes()
        self._laden(_buehne(2, dx=0.5))
        self._warte_echo(2)
        nachher = self._meshes()
        self.assertEqual(sorted(nachher), sorted(vorher))
        self.assertTrue(all(nachher[k] != vorher[k] for k in vorher), "Aenderung -> Neubau")
        x = self._eval("window.__lightos.stageObjects['el00'].data.position.x")
        self.assertAlmostEqual(x, 0.5)

    def test_lokale_aenderung_seit_dem_load_erzwingt_neubau(self):
        """Verglichen wird mit dem Ist-Zustand, nicht mit dem letzten Load."""
        self._laden(_buehne(1))
        self._warte_echo(1)
        self._add_stage_data({
            "id": "el03", "type": "wall", "position": {"x": 7.0, "y": 0.5, "z": 0.0}})
        ende = time.monotonic() + 5
        while time.monotonic() < ende and abs(self._eval(
                "window.__lightos.stageObjects['el03'].data.position.x") - 7.0) > 1e-6:
            time.sleep(0.05)
        vorher = self._meshes()
        self._laden(_buehne(2))                 # Python-Stand: el03 wieder bei x=9
        self._warte_echo(2)
        self.assertNotEqual(self._meshes()["el03"], vorher["el03"])
        self.assertAlmostEqual(
            self._eval("window.__lightos.stageObjects['el03'].data.position.x"), 9.0)

    def test_add_stage_data_ohne_aenderung_baut_nichts_neu(self):
        b = _buehne(1)
        self._laden(b)
        self._warte_echo(1)
        vorher = self._meshes()
        for o in b["objects"]:                  # push_stage_definition/Reassert
            d = dict(o)
            d["reassert"] = True
            self._add_stage_data(d)
        _pump(1.0)
        self.assertEqual(self._bridge_obj.events, [], "Poll hat die Events abgeholt")
        self.assertEqual(self._meshes(), vorher, "unveraenderte Elemente nicht neu bauen")
        # Groessenaenderung baut weiter neu (Gruppen-Typ: Truss).
        d = dict(b["objects"][1])
        d["size"] = {"x": 4.0, "y": 1.0, "z": 1.5}
        self._add_stage_data(d)
        ende = time.monotonic() + 5
        while time.monotonic() < ende and self._meshes()["el01"] == vorher["el01"]:
            time.sleep(0.05)
        self.assertNotEqual(self._meshes()["el01"], vorher["el01"])
        self.assertEqual(self._eval("window.__lightos.stageObjects['el01'].data.size.x"), 4.0)
        # Farbaenderung kommt weiter an.
        d = dict(b["objects"][0])
        d["color"] = "#ff0000"
        self._add_stage_data(d)
        ende = time.monotonic() + 5
        while time.monotonic() < ende and self._eval(
                "window.__lightos.stageObjects['el00'].data.color") != "#ff0000":
            time.sleep(0.05)
        self.assertEqual(self._eval("window.__lightos.stageObjects['el00'].data.color"), "#ff0000")


if __name__ == "__main__":
    unittest.main()
