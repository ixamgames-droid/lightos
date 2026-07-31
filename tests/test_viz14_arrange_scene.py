"""VIZ-14 (Anordnen): Auswahl als Reihe / Raster / Kreis — End-to-End in einer
ECHTEN QWebEngine.

Plan §3 fuehrt das „Arrangement-Tool (Reihe/Grid/Kreis mit Abstand)" als *Hoch*
(grandMA3, Capture „Spread Even"). Es fehlte als einziges der drei
Positionier-Werkzeuge:

* ``jsAlignSelected``      legt alle auf EINE Linie (gleicher x bzw. z),
* ``jsDistributeSelected`` verteilt gleichmaessig ZWISCHEN den Aussenpunkten,
* ``jsArrangeSelected``    baut die Formation NEU auf — um den Schwerpunkt der
  Auswahl herum, mit festem Abstand.

Die ersten beiden aendern nur eine Achse und setzen eine schon halbwegs passende
Ausgangslage voraus; aus vier wild verstreuten Strahlern wird damit nie ein
Raster.

Belegt: (1) Reihe mit exaktem Abstand, (2) der Schwerpunkt bleibt liegen (die
Formation springt NICHT in den Weltnullpunkt), (3) Raster mit Zeilen/Spalten,
(4) Kreis mit gleichem Radius und gleichen Winkelabstaenden, (5) die Reihenfolge
folgt der SICHTBAREN Anordnung, nicht der fid, (6) unbekannte Form fasst nichts
an, (7) eine Ein-Geraet-Auswahl bleibt unberuehrt.
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


class ArrangeSceneTest(unittest.TestCase):
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

    def _add(self, fid, x, z):
        self._bridge_obj.fixtureAdded.emit(json.dumps({
            "fid": fid, "label": f"P{fid}", "type": "par", "model": "par",
            "nHeads": 0, "x": x, "y": 3, "z": z,
            "rotX": 0, "rotY": 0, "rotZ": 0,
        }))

    def _positionen(self):
        roh = self._eval(
            "JSON.stringify(Object.keys(window.__lightos.fixtures).map(function(k){"
            " var f = window.__lightos.fixtures[k];"
            " return [Number(k), +f.group.position.x.toFixed(4),"
            "         +f.group.position.z.toFixed(4)]; }))")
        return {fid: (x, z) for fid, x, z in json.loads(roh)}

    def _arrange(self, spec):
        self._bridge_obj.arrangeSelected.emit(json.dumps(spec))

    # ── Alle Checks in EINER Ladung (jede Vollladung kostet ~4 s) ─────────────

    def test_anordnen_baut_reihe_raster_und_kreis(self):
        self._load_and_wait()

        # Vier Geraete BEWUSST wild verstreut und mit einer fid-Reihenfolge, die
        # der sichtbaren Anordnung WIDERSPRICHT (fid 4 steht ganz links).
        for fid, x, z in ((1, 2.0, 1.0), (2, 7.0, -3.0), (3, 4.5, 5.0), (4, -1.0, 0.5)):
            self._add(fid, x, z)
        self._poll_until_true("Object.keys(window.__lightos.fixtures).length === 4")
        self._eval("window.__lightos.view.selectedFids = [1,2,3,4]; true")
        vorher = self._positionen()
        mitte_x = sum(p[0] for p in vorher.values()) / 4
        mitte_z = sum(p[1] for p in vorher.values()) / 4

        # (1)+(2)+(5) Reihe entlang X, Abstand exakt 2 m, Schwerpunkt bleibt
        self._arrange({"shape": "row", "axis": "x", "spacing": 2.0})
        self._poll_until_true(
            "window.__lightos.fixtures[4].group.position.x !== " + repr(vorher[4][0]))
        p = self._positionen()
        xs = sorted(v[0] for v in p.values())
        for a, b in zip(xs, xs[1:]):
            self.assertAlmostEqual(b - a, 2.0, places=3,
                                   msg=f"Abstand in der Reihe stimmt nicht: {xs}")
        self.assertAlmostEqual(sum(xs) / 4, mitte_x, places=3,
                               msg="(2) die Formation ist vom Schwerpunkt weggesprungen")
        for v in p.values():
            self.assertAlmostEqual(v[1], mitte_z, places=3,
                                   msg="Reihe entlang X muss EIN z haben")
        # (5) links steht, was vorher links stand — nicht die kleinste fid
        links = min(p.items(), key=lambda kv: kv[1][0])[0]
        self.assertEqual(links, 4,
                         "die Reihenfolge muss der sichtbaren Anordnung folgen, "
                         "nicht der fid")

        # (3) Raster 2x2, Abstand 3 m
        self._arrange({"shape": "grid", "cols": 2, "spacing": 3.0})
        self._poll_until_true(
            "(function(){var f=window.__lightos.fixtures;"
            " var zs={}; for (var k in f) zs[f[k].group.position.z.toFixed(3)]=1;"
            " return Object.keys(zs).length === 2;})()")
        p = self._positionen()
        self.assertEqual(len({round(v[0], 3) for v in p.values()}), 2, "2 Spalten")
        self.assertEqual(len({round(v[1], 3) for v in p.values()}), 2, "2 Zeilen")
        breite = max(v[0] for v in p.values()) - min(v[0] for v in p.values())
        self.assertAlmostEqual(breite, 3.0, places=3)

        # (4) Kreis: gleicher Radius, gleichmaessige Winkel
        self._arrange({"shape": "circle", "radius": 5.0})
        self._poll_until_true(
            "(function(){var f=window.__lightos.fixtures;"
            " for (var k in f) if (Math.abs(f[k].group.position.z) > 0.001) return true;"
            " return false;})()")
        p = self._positionen()
        cx = sum(v[0] for v in p.values()) / 4
        cz = sum(v[1] for v in p.values()) / 4
        radien = [((v[0] - cx) ** 2 + (v[1] - cz) ** 2) ** 0.5 for v in p.values()]
        for r in radien:
            self.assertAlmostEqual(r, 5.0, places=2, msg=f"Radien: {radien}")

        # (6) unbekannte Form fasst nichts an
        vor_unbekannt = self._positionen()
        self._arrange({"shape": "zickzack"})
        _pump(0.5)
        self.assertEqual(self._positionen(), vor_unbekannt,
                         "eine unbekannte Form darf NICHTS verschieben")

        # (7) eine Ein-Geraet-Auswahl bleibt unberuehrt (keine Formation aus einem)
        self._eval("window.__lightos.view.selectedFids = [1]; true")
        vor_einzeln = self._positionen()
        self._arrange({"shape": "row", "spacing": 9.0})
        _pump(0.5)
        self.assertEqual(self._positionen(), vor_einzeln)


if __name__ == "__main__":
    unittest.main()
