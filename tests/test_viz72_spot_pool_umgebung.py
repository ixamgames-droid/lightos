"""VIZ-72: Spot-Pool (feste Zahl echter Lichter) und zusammengefasste Umgebung.

**Was langsam war** (gemessen offscreen an der Buehnen-Show: 80 Geraete, 68 mit
Strahl, 23 Buehnenobjekte; Stufe Hoch, 1280x720, Median je Bild):

    main (68 SpotLights)        54,6 ms
    nur 8 SpotLights            19,8 ms
    ohne Kegel                  51,2 ms
    ohne Geraete-Gehaeuse       45,2 ms

In three.js r128 rechnet jedes beleuchtete Material in jedem Pixel ALLE
sichtbaren Lichter durch. Jetzt gibt es nur noch einen Pool echter Lichter je
Qualitaetsstufe (Niedrig 4 / Hoch 8 / Maximal 16), vergeben an die hellsten
Strahlen mit Hysterese; die Lichterzahl aendert sich nie wegen DMX (VIZ-69:
sie steckt im Programmschluessel). Im Ansehen-Modus werden die
Buehnenobjekte je Material zu einem Koerper zusammengefasst; Bauen-Modi, 2D und
eine Auswahl zeigen wieder die Einzelobjekte. Picking/Andocken gehen weiter
gegen die (unsichtbaren) Originale.

Laeuft ueber die ECHTE Produktiv-Seite (Muster test_viz69_render_ruckler.py).
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


import pytest as _pytest_xplat15                      # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402  XPLAT-15


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    from PySide6.QtWidgets import QApplication as _QApp
    destroy_all_top_level_widgets(_QApp.instance())


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


class Viz72SzeneTest(unittest.TestCase):
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

    # ── (1) Lichterzahl konstant, Pool-Groesse je Stufe ──────────────────────
    def test_lichterzahl_ist_konstant_und_haengt_an_der_stufe(self):
        self._rig()
        self._dmx({f: 255 for f in _FIDS})
        info = self._json("window.__lightos.renderInfo()")
        self.assertEqual(info["spots"], 8, "Stufe Hoch: genau 8 echte SpotLights")
        self.assertEqual(info["schatten"], 8)
        self.assertEqual(
            self._eval("Object.values(window.__lightos.fixtures)"
                       ".filter(f => f.spot && f.spot.parent).length"), 0,
            "Geraete-Spots haengen noch in der Szene")
        programme = info["programme"]
        # Hell/Dunkel/Teil-dunkel/Farbe: Lichter- und Programmzahl bleiben.
        for schritt in range(6):
            werte = {f: (0 if (i + schritt) % 3 == 0 else 40 + 30 * i)
                     for i, f in enumerate(_FIDS)}
            werte[_FIDS[0]] = 0 if schritt % 2 else 255
            self._dmx(werte)
            jetzt = self._json("window.__lightos.renderInfo()")
            self.assertEqual(jetzt["spots"], 8, f"Schritt {schritt}: Lichterzahl geaendert")
            self.assertEqual(jetzt["schatten"], 8, f"Schritt {schritt}: Schattenzahl geaendert")
            self.assertEqual(jetzt["programme"], programme,
                             f"Schritt {schritt}: Shader neu kompiliert")
            self.assertTrue(self._eval(
                "window.__lightos.spotPoolLights().every(l => l.visible)"),
                "Pool-Licht unsichtbar geschaltet (Programmschluessel, VIZ-69)")

    def test_kleines_rig_behaelt_ein_licht_je_geraet(self):
        self._rig(n=3)
        self._dmx({f: 255 for f in _FIDS[:3]})
        p = self._pool()
        self.assertEqual(p["groesse"], 3)
        self.assertEqual(p["schatten"], 3)
        self.assertEqual(sorted(p["halter"]), list(_FIDS[:3]))

    def test_stufen_niedrig_und_maximal(self):
        self._rig(n=20, tier="low")
        self.assertEqual(self._pool()["groesse"], 4)
        self.assertEqual(self._json("window.__lightos.renderInfo()")["spots"], 4)

    def test_stufe_maximal(self):
        self._rig(n=20, tier="max")
        self.assertEqual(self._pool()["groesse"], 16)
        self.assertEqual(self._pool()["schatten"], 16)

    # ── (2) Vergabe an die hellsten, mit Hysterese ───────────────────────────
    def test_pool_vergibt_an_die_hellsten(self):
        self._rig()
        # Helligkeit steigt mit dem Index: die 8 hellsten sind die letzten 8.
        werte = {f: 20 + 19 * i for i, f in enumerate(_FIDS)}
        self._dmx(werte)
        self.assertEqual(sorted(self._pool()["halter"]), list(_FIDS[4:]))
        self.assertEqual(self._pool()["leuchtend"], 8)

        # Pool-Licht steht dort, wo das Geraete-Licht frueher hing:
        # spot.position (r128-Vorgabe 0,1,0) im Koordinatensystem der Gruppe.
        lage = self._json("""(function(){ const L = window.__lightos;
            const l = L.spotPoolLights()[0]; const fid = L.spotPoolInfo().halter[0];
            const f = L.fixtures[fid]; f.group.updateMatrixWorld(true);
            const v = f.spot.position.clone().applyMatrix4(f.group.matrixWorld);
            return [l.position.distanceTo(v), l.target.position.distanceTo(f.spot.target.position),
                    Math.abs(l.intensity - f.spot.intensity)]; })()""")
        self.assertLess(max(lage), 1e-6, lage)

        # Hysterese: knapp heller als der schwaechste Halter -> kein Wechsel.
        vorher = self._pool()
        schwaechster = _FIDS[4]
        werte[_FIDS[3]] = werte[schwaechster] + 5
        self._dmx(werte)
        self.assertEqual(self._pool()["halter"], vorher["halter"],
                         "Vergabe flattert ohne Hysterese")
        # Deutlich heller -> verdraengt den Schwaechsten.
        werte[_FIDS[3]] = 255
        self._dmx(werte)
        halter = self._pool()["halter"]
        self.assertIn(_FIDS[3], halter)
        self.assertNotIn(schwaechster, halter)

    def test_dunkler_halter_behaelt_platz_bis_er_gebraucht_wird(self):
        """Abdunkeln + Aufhellen derselben Geraete: Lichter bleiben, wo sie
        waren -> kein Schattendurchlauf (VIZ-69: Farbe/Dimmer kostet keinen)."""
        self._rig(n=4)
        hell = {f: 255 for f in _FIDS[:4]}
        self._dmx(hell)
        self._tick()
        h0 = self._pool()["halter"]
        n0 = self._eval("window.__lightos.shadowUpdateStats().neubauten")
        self._dmx({f: 0 for f in _FIDS[:4]})
        self.assertEqual(self._pool()["leuchtend"], 0)
        self._dmx(hell)
        self.assertEqual(self._pool()["halter"], h0)
        self.assertEqual(self._eval("window.__lightos.shadowUpdateStats().neubauten"), n0,
                         "Hell/Dunkel hat die Shadow-Maps neu gezeichnet")

    def test_vergabe_rein(self):
        """Die Vergabe-Regel als reine Funktion (Map fid -> Helligkeit)."""
        self._load_and_wait()
        r = self._json("""(function(){ const V = window.__lightos.__spotPoolVergeben;
          const m = (o) => new Map(Object.entries(o).map(([k, v]) => [Number(k), v]));
          return {
            frei: V([null, null], m({1: 1, 2: 3, 3: 2})),
            knapp: V([1, 3], m({1: 1.0, 2: 1.2, 3: 2})),
            deutlich: V([1, 3], m({1: 1.0, 2: 1.3, 3: 2})),
            dunkel: V([1, 3], m({1: 0, 2: 0.1, 3: 2})),
            weg: V([9, 3], m({2: 0.5, 3: 2})),
          }; })()""")
        self.assertEqual(r["frei"], [2, 3])
        self.assertEqual(r["knapp"], [1, 3])
        self.assertEqual(r["deutlich"], [2, 3])
        self.assertEqual(r["dunkel"], [2, 3])
        self.assertEqual(r["weg"], [2, 3])

    # ── (3) Umgebung: Ansehen zusammengefasst, Bauen einzeln ─────────────────
    def _buehne(self):
        self._load_and_wait()
        self._emit_until_true(
            lambda: self._bridge_obj.stageLoaded.emit(json.dumps(_BUEHNE)),
            "Object.keys(window.__lightos.stageObjects).length === 5")
        self._eval("window.__lightos.setEditMode('view'); 1")
        self._tick()

    def _sichtbar(self):
        return self._json("Object.fromEntries(Object.entries(window.__lightos.stageObjects)"
                          ".map(([k, s]) => [k, s.mesh.visible]))")

    def test_umgebung_im_ansehen_modus_zusammengefasst(self):
        self._buehne()
        u = self._json("window.__lightos.umgebungInfo()")
        self.assertTrue(u["aktiv"])
        self.assertEqual(u["objekteZusammengefasst"], 5)
        # Traversen (gleiches Material) -> 1, Podest -> 1, Wand -> 1.
        self.assertEqual(u["koerper"], 3)
        self.assertFalse(any(self._sichtbar().values()), "Originale zusaetzlich sichtbar")
        # Ruhende Szene baut nicht neu.
        n = u["neubauten"]
        self._tick()
        self._tick()
        self.assertEqual(self._json("window.__lightos.umgebungInfo()")["neubauten"], n)

    def test_bauen_modus_zeigt_einzelobjekte_und_rueckweg(self):
        self._buehne()
        for modus in ("stage", "edit"):
            self._eval(f"window.__lightos.setEditMode('{modus}'); 1")
            self._tick()
            u = self._json("window.__lightos.umgebungInfo()")
            self.assertFalse(u["aktiv"], f"Modus {modus}: noch zusammengefasst")
            self.assertTrue(all(self._sichtbar().values()),
                            f"Modus {modus}: Einzelobjekte unsichtbar")
            self._eval("window.__lightos.setEditMode('view'); 1")
            self._tick()
            self.assertTrue(self._json("window.__lightos.umgebungInfo()")["aktiv"])
        # 2D-Draufsicht: einzeln (halbtransparenter 2D-Stil).
        self._eval("window.__lightos.setViewMode('2D'); 1")
        self._tick()
        self.assertFalse(self._json("window.__lightos.umgebungInfo()")["aktiv"])
        self.assertTrue(all(self._sichtbar().values()))
        self._eval("window.__lightos.setViewMode('3D'); 1")
        self._tick()
        self.assertTrue(self._json("window.__lightos.umgebungInfo()")["aktiv"])

    def test_aenderung_im_ansehen_modus_baut_neu(self):
        self._buehne()
        n = self._json("window.__lightos.umgebungInfo()")["neubauten"]
        self._bridge_obj.removeStageObject.emit("t2")
        self._poll_until_true("!window.__lightos.stageObjects['t2']")
        self._tick()
        u = self._json("window.__lightos.umgebungInfo()")
        self.assertEqual(u["neubauten"], n + 1)
        self.assertEqual(u["objekteZusammengefasst"], 4)

    def test_picking_und_andocken_unberuehrt(self):
        self._buehne()
        self.assertTrue(self._json("window.__lightos.umgebungInfo()")["aktiv"])
        # Andocken: im Ansehen-Modus (zusammengefasst) dasselbe Ziel wie im
        # Bauen-Modus (Einzelobjekte) — an mehreren Stellen.
        punkte = [(0, 0), (0, -3), (-4, 0), (3, -2), (0, -6)]
        ansehen = [self._json(f"window.__lightos.__findDockTarget({x}, {z})")
                   for x, z in punkte]
        self._eval("window.__lightos.setEditMode('edit'); 1")
        self._tick()
        self.assertFalse(self._json("window.__lightos.umgebungInfo()")["aktiv"])
        bauen = [self._json(f"window.__lightos.__findDockTarget({x}, {z})")
                 for x, z in punkte]
        self.assertEqual(ansehen, bauen)
        self.assertTrue(any(z is not None for z in ansehen), ansehen)
        self._eval("window.__lightos.setEditMode('view'); 1")
        self._tick()
        self.assertTrue(self._json("window.__lightos.umgebungInfo()")["aktiv"])
        # Sammelkoerper sind nie Treffer eines Raycasts.
        treffer = self._eval("""(function(){
            const T = window.THREE; const L = window.__lightos;
            const rc = new T.Raycaster(new T.Vector3(0, 50, -2), new T.Vector3(0, -1, 0));
            const alle = Object.values(L.stageObjects).map(s => s.mesh);
            const hits = rc.intersectObjects(alle, true);
            return hits.length > 0 && hits.every(h => !h.object.userData.umgebungKoerper); })()""")
        self.assertTrue(treffer, "Raycast gegen die Originale liefert nichts")


class Viz72QuelltextTest(unittest.TestCase):
    def _js(self, *teile):
        return open(os.path.join(_SCENE_SRC, *teile), encoding="utf-8").read()

    def test_geraete_spot_nicht_mehr_in_der_szene(self):
        code = "\n".join(z for z in self._js("fixtures", "fixtures.js").splitlines()
                         if not z.lstrip().startswith("//"))
        self.assertNotIn("root.add(spot)", code)

    def test_render_closure_vergibt_vor_den_schatten(self):
        app = self._js("app.js")
        rumpf = app.split("function renderFrame()", 1)[1].split("\n}\n", 1)[0]
        self.assertLess(rumpf.index("syncSpotPool()"), rumpf.index("prepareShadowMap()"))
        self.assertLess(rumpf.index("syncUmgebung()"), rumpf.index("prepareShadowMap()"))

    def test_stufentabelle_echte_lichter(self):
        q = self._js("scene", "quality_tiers.js")
        for stufe, n in (("low", 4), ("high", 8), ("max", 16)):
            block = q.split(stufe + ": Object.freeze({", 1)[1].split("})", 1)[0]
            self.assertIn(f"realLights: {n},", block, stufe)


if __name__ == "__main__":
    unittest.main()
