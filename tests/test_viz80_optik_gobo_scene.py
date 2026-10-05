"""VIZ-80: Optik, Gobo und Prisma kommen ueber den ECHTEN Weg im 3D an.

Befund aus VIZ-79: ``_build_fixture_payload`` schickt zoom/iris/focus/frost,
gobo und prism/prism_rotation mit — aber ``applyDmxEntry`` -> ``updateFixture``
reichte nur r/g/b/intensity/pan/tilt/heads (+ Laser-Block) an die Handler.
Die Handler-Tests (test_viz_mh_optics, test_viz_gobo_3d,
test_viz_prisma_3d_scene, test_viz_optics_focus_frost_scene) rufen
``applyOptics``/``applyGobo``/``applyPrism`` DIREKT auf und sahen davon nichts.

Dieser Test geht deshalb den Produktivweg: Payload aus Python
(``_build_fixture_payload`` mit Profil-Kanaelen), angewandt per
``dmx_push.push_script`` bzw. ``applyDmx`` (Push) und ueber ``pollControl``
(Poll-Rueckfall), dazu der Neubau aus dem DMX-Cache (``addFixture``).
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

from src.ui.visualizer.dmx_push import push_script
from src.ui.visualizer.visualizer_service import _build_fixture_payload

_app = QApplication.instance() or QApplication([])

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_HTML_PATH = os.path.join(_REPO, "src", "ui", "visualizer", "stage_scene.html")

_LOAD_TIMEOUT_S = 40.0
_POLL_TIMEOUT_S = 10.0
_POLL_INTERVAL_S = 0.05

_SIGNAL_SPECS = [
    ("fixtureAdded", (str,)), ("fixtureRemoved", (int,)),
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
        # Poll-Rueckfall: ein gesetzter DMX-Stand geht GENAU einmal raus —
        # wie im Service, der die Zeilen beim Ausliefern als zugestellt merkt.
        dmx = getattr(self, "_poll_dmx", None)
        self._poll_dmx = None
        return json.dumps({"dmx": dmx}) if dmx else "{}"

    attrs["requestFixtures"] = requestFixtures
    attrs["pollControl"] = pollControl
    attrs["requestFullResync"] = Signal()
    return type("MockVisualizerBridgeViz80", (QObject,), attrs)


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


# ── Profil-Attrappe: ein Moving Head mit allen Optik-/Gobo-/Prisma-Kanaelen ──
class _Range:
    def __init__(self, lo, hi, name):
        self.range_from, self.range_to, self.name = lo, hi, name
        self.kind = ""


class _Ch:
    def __init__(self, attribute, ranges=()):
        self.attribute = attribute
        self.ranges = list(ranges)


_FID = 800001


class _Fx:
    fid = _FID
    fixture_type = "moving_head"


_KANAELE = [
    _Ch("intensity"), _Ch("color_r"), _Ch("color_g"), _Ch("color_b"),
    _Ch("pan"), _Ch("tilt"),
    _Ch("zoom"), _Ch("iris"), _Ch("focus"), _Ch("frost"),
    _Ch("gobo_wheel", [_Range(0, 9, "Offen"), _Range(10, 19, "Gobo 6 (Spirale)"),
                       _Range(20, 29, "Gobo 2 (Ovale)")]),
    _Ch("gobo_rotation"),
    _Ch("prism", [_Range(0, 9, "Aus"), _Range(10, 99, "6-fach Prisma"),
                  _Range(100, 255, "3 Facet Prism")]),
    _Ch("prism_rotation"),
]

_GRUND = {"intensity": 255, "color_r": 255, "color_g": 255, "color_b": 255,
          "pan": 128, "tilt": 128, "zoom": 128, "iris": 0, "focus": 128,
          "frost": 0, "gobo_wheel": 0, "gobo_rotation": 0, "prism": 0,
          "prism_rotation": 0}


def _payload(**attrs):
    """Payload genau so, wie der Service ihn baut (inkl. Gobo-Stil und
    Prisma-Facetten aus den Range-Namen)."""
    a = dict(_GRUND)
    a.update(attrs)
    return _build_fixture_payload(_Fx(), a, _KANAELE)


def _geraet(fid=_FID):
    # Wie ``_fixture_to_dict``: feste Nullen, Pan/Tilt Mitte.
    return {"fid": fid, "type": "moving_head", "model": "moving_head",
            "x": 0, "y": 6, "z": 0, "rotX": 0, "rotY": 0, "rotZ": 0,
            "r": 0, "g": 0, "b": 0, "intensity": 0, "pan": 128, "tilt": 128}


_ZUSTAND_JS = """
(function(){
  const f = window.__lightos.fixtures['%d'];
  if (!f) return 'null';
  const fs = f.floorSpot;
  return JSON.stringify({
    beamX: f.beam.scale.x, angle: f.spot.angle, base: f.baseSpotAngle,
    penumbra: f.spot.penumbra,
    map: !!(fs && fs.material.map),
    mapIstSpirale: !!(fs && fs.material.map
                      && fs.material.map === window.__lightos.__goboTexture('spiral')),
    goboRot: fs ? fs.rotation.z : null,
    prismN: f.prismCones ? f.prismCones.length : 0,
    prismHaengt: !!(f.prismGroup && f.prismGroup.parent),
    prismRot: f.prismGroup ? f.prismGroup.rotation.y : null,
    beamParentKinder: f.beam.parent ? f.beam.parent.children.length : 0,
  });
})()
"""


class Viz80OptikGoboPrismaSceneTest(unittest.TestCase):
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
        self._seq = 0

    def tearDown(self):
        destroy_webengine_view(self._view, _pump)
        self._view = None

    # ── Helfer ───────────────────────────────────────────────────────────────
    def _load_and_wait(self):
        url = QUrl.fromLocalFile(_HTML_PATH)
        url.setQuery(f"v={int(time.time() * 1000)}")
        self._view.load(url)
        deadline = time.monotonic() + _LOAD_TIMEOUT_S
        while not self._loaded_ok and time.monotonic() < deadline:
            _app.processEvents()
            time.sleep(_POLL_INTERVAL_S)
        self.assertTrue(self._loaded_ok and self._loaded_ok[-1], "Seite nicht geladen")
        self._poll_until_true("!!window.__lightosAppReady")
        self._emit_until_true(
            lambda: self._bridge_obj.allFixtures.emit(json.dumps([_geraet()])),
            "!!window.__lightos.fixtures['%d']" % _FID)

    def _eval(self, js_expr):
        box = []
        self._view.page().runJavaScript(js_expr, lambda result: box.append(result))
        deadline = time.monotonic() + _POLL_TIMEOUT_S
        while not box and time.monotonic() < deadline:
            _app.processEvents()
            time.sleep(0.01)
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

    def _push(self, *payloads):
        """Produktiv-Push: dasselbe Skript, das dmx_push.py per runJavaScript
        absetzt."""
        entries = []
        for p in payloads:
            self._seq += 1
            entries.append((self._seq, p))
        n = self._eval(push_script(entries))
        self.assertEqual(n, len(payloads), "Push erreichte das Geraet nicht")

    def _z(self):
        return json.loads(self._eval(_ZUSTAND_JS % _FID))

    # ── Zoom / Iris ──────────────────────────────────────────────────────────
    def test_zoom_aendert_kegelwinkel(self):
        self._load_and_wait()
        self._push(_payload(zoom=0))
        eng = self._z()
        self._push(_payload(zoom=255))
        weit = self._z()
        self.assertLess(eng["beamX"], 0.6, f"Zoom 0 kam nicht an: {eng}")
        self.assertGreater(weit["beamX"], 1.5, f"Zoom 255 kam nicht an: {weit}")
        self.assertGreater(weit["angle"], eng["angle"] * 2,
                           "SpotLight-Winkel folgt dem Zoom nicht")

    def test_iris_verengt_den_kegel(self):
        self._load_and_wait()
        self._push(_payload(iris=0))
        offen = self._z()
        self._push(_payload(iris=255))
        zu = self._z()
        self.assertAlmostEqual(zu["beamX"] / offen["beamX"], 0.30, places=2)

    # ── Fokus / Frost ────────────────────────────────────────────────────────
    def test_fokus_und_frost_machen_die_kante_weich(self):
        self._load_and_wait()
        self._push(_payload(focus=128, frost=0))
        scharf = self._z()["penumbra"]
        self._push(_payload(focus=0, frost=0))
        unscharf = self._z()["penumbra"]
        self._push(_payload(focus=128, frost=255))
        frost = self._z()
        self.assertAlmostEqual(scharf, 0.12, places=3)
        self.assertGreater(unscharf, 0.9, "Fokus 0 hat die Kante nicht erweicht")
        self.assertGreater(frost["penumbra"], 0.9, "Frost hat die Kante nicht erweicht")

    # ── Gobo ─────────────────────────────────────────────────────────────────
    def test_gobo_setzt_textur_im_bodenfleck_und_dreht_sie(self):
        self._load_and_wait()
        self._push(_payload(gobo_wheel=0))
        self.assertFalse(self._z()["map"], "offenes Rad darf kein Muster tragen")
        self._push(_payload(gobo_wheel=15, gobo_rotation=128))
        z = self._z()
        self.assertTrue(z["mapIstSpirale"], f"Gobo-Textur fehlt im Bodenfleck: {z}")
        self.assertAlmostEqual(z["goboRot"], 128 / 255 * 2 * math.pi, places=3)
        self._push(_payload(gobo_wheel=0, gobo_rotation=128))
        self.assertFalse(self._z()["map"], "Gobo raus -> Muster muss weg")

    # ── Prisma ───────────────────────────────────────────────────────────────
    def test_prisma_teilt_den_kegel_und_aus_laesst_einen(self):
        self._load_and_wait()
        self._push(_payload(prism=0))
        aus = self._z()
        self.assertEqual(aus["prismN"], 0)
        self.assertFalse(aus["prismHaengt"])
        self._push(_payload(prism=50, prism_rotation=255))
        an = self._z()
        self.assertEqual(an["prismN"], 5, f"6-fach-Prisma kam nicht an: {an}")
        self.assertTrue(an["prismHaengt"])
        self.assertAlmostEqual(an["prismRot"], 2 * math.pi, places=3)
        # Wiederverwendung: dieselben Kegel-Objekte beim naechsten Einschalten.
        self._eval("window.__lightos.fixtures['%d'].prismCones[0].__mark = 1" % _FID)
        self._push(_payload(prism=0))
        wieder_aus = self._z()
        self.assertEqual(wieder_aus["prismN"], 0)
        self.assertFalse(wieder_aus["prismHaengt"], "Prisma aus -> nur ein Kegel")
        self.assertEqual(wieder_aus["beamParentKinder"], aus["beamParentKinder"])
        self._push(_payload(prism=200))     # "3 Facet Prism"
        drei = self._z()
        self.assertEqual(drei["prismN"], 2)
        self.assertEqual(self._eval(
            "window.__lightos.fixtures['%d'].prismCones[0].__mark || 0" % _FID), 1,
            "Prisma-Kegel wurden neu gebaut statt wiederverwendet")

    # ── fehlend = unveraendert; Kanal entfallen = Grundstellung ───────────────
    def test_fehlendes_feld_heisst_unveraendert(self):
        self._load_and_wait()
        self._push(_payload(zoom=0, gobo_wheel=15, prism=50))
        vorher = self._z()
        # Teil-Eintrag (ohne Helligkeit/Pan/Tilt) ohne Optik-Felder: nichts anfassen.
        self._push({"fid": _FID, "r": 0, "g": 255, "b": 0})
        nachher = self._z()
        for k in ("beamX", "angle", "mapIstSpirale", "prismN"):
            self.assertEqual(nachher[k], vorher[k], k)
        # Ein Geraet OHNE die Kanaele bekommt keinen erfundenen Default.
        ohne = {"fid": _FID + 1, "r": 255, "g": 255, "b": 255, "intensity": 255,
                "pan": 128, "tilt": 128}
        self._emit_until_true(
            lambda: self._bridge_obj.fixtureAdded.emit(json.dumps(_geraet(_FID + 1))),
            "!!window.__lightos.fixtures['%d']" % (_FID + 1))
        self._push(ohne)
        z2 = json.loads(self._eval(_ZUSTAND_JS % (_FID + 1)))
        self.assertAlmostEqual(z2["beamX"], 1.0, places=6)
        self.assertAlmostEqual(z2["angle"], z2["base"], places=6)
        self.assertFalse(z2["map"])
        self.assertEqual(z2["prismN"], 0)

    def test_entfallener_kanal_faellt_auf_grundstellung(self):
        """Stale-Schutz: ein VOLLER Eintrag ohne das Feld, das das Geraet
        vorher hatte (Profilwechsel ohne Neubau), stellt zurueck."""
        self._load_and_wait()
        grund_penumbra = self._z()["penumbra"]
        self._push(_payload(zoom=0, focus=0, gobo_wheel=15, gobo_rotation=64,
                            prism=50))
        voll_ohne = {"fid": _FID, "r": 255, "g": 255, "b": 255, "intensity": 255,
                     "pan": 128, "tilt": 128}
        self._push(voll_ohne)
        z = self._z()
        self.assertAlmostEqual(z["beamX"], 1.0, places=6)
        self.assertAlmostEqual(z["angle"], z["base"], places=6)
        self.assertAlmostEqual(z["penumbra"], grund_penumbra, places=6)
        self.assertFalse(z["map"])
        self.assertAlmostEqual(z["goboRot"], 0.0, places=6)
        self.assertEqual(z["prismN"], 0)

    # ── Neubau aus dem Cache + Poll-Rueckfall ─────────────────────────────────
    def test_neubau_aus_dem_cache_behaelt_optik(self):
        self._load_and_wait()
        self._push(_payload(zoom=255, gobo_wheel=15, prism=50))
        self._eval("window.__lightos.fixtures['%d'].__alt = true" % _FID)
        self._emit_until_true(
            lambda: self._bridge_obj.fixtureAdded.emit(json.dumps(_geraet())),
            "(function(){ const f = window.__lightos.fixtures['%d'];"
            " return !!f && !f.__alt; })()" % _FID)
        z = self._z()
        self.assertGreater(z["beamX"], 1.5, "Neubau verlor den Zoom")
        self.assertTrue(z["mapIstSpirale"], "Neubau verlor das Gobo")
        self.assertEqual(z["prismN"], 5, "Neubau verlor das Prisma")

    def test_poll_rueckfall_bringt_optik_an(self):
        self._load_and_wait()
        self._bridge_obj._poll_dmx = json.dumps([_payload(zoom=0, gobo_wheel=15,
                                                          prism=50)])
        self._poll_until_true(
            "(function(){ const f = window.__lightos.fixtures['%d'];"
            " return !!(f && f.prismCones && f.prismCones.length === 5); })()" % _FID,
            timeout_s=8.0)
        z = self._z()
        self.assertLess(z["beamX"], 0.6)
        self.assertTrue(z["mapIstSpirale"])

    # ── Prisma-Kegel fangen keinen Klick (Review VIZ-80, L1) ────────────────
    def _pick_auf_poolkegel(self, i, nur_pool):
        """Bildpunkt mitten auf Pool-Kegel ``i`` durch denselben Fixture-Pick
        wie Klick/Hover/Zug schicken. ``nur_pool``: alle anderen Meshes des
        Geraets (Gehaeuse, Hauptstrahl, …) fuer diesen einen Pick stumm
        schalten, damit ein Treffer NUR vom Pool-Kegel kommen kann."""
        r = self._eval("""
        (function(){
          const L = window.__lightos;
          const f = L.fixtures['%d'];
          const k = f.prismPool.kegel[%d];
          const pool = new Set(f.prismPool.kegel);
          const gemerkt = [];
          if (%s) {
            f.group.traverse(o => {
              if (o.isMesh && !pool.has(o)) {
                gemerkt.push([o, Object.prototype.hasOwnProperty.call(o, 'raycast'), o.raycast]);
                o.raycast = () => {};
              }
            });
          }
          f.group.updateMatrixWorld(true);
          L.view.activeCam.updateMatrixWorld();
          if (!k.geometry.boundingBox) k.geometry.computeBoundingBox();
          const p = k.geometry.boundingBox.getCenter(k.position.clone());
          k.localToWorld(p);
          p.project(L.view.activeCam);
          L.__mouse.set(p.x, p.y);
          const fid = L.__pickFixture();
          for (const [o, eigen, fn] of gemerkt) {
            if (eigen) o.raycast = fn; else delete o.raycast;
          }
          return (fid === null || fid === undefined) ? 'null' : String(fid);
        })()""" % (_FID, i, "true" if nur_pool else "false"))
        return None if r == "null" else int(r)

    def test_prisma_kegel_fangen_keinen_klick(self):
        """three r128 prueft `visible` beim Raycast nicht: nach 6-fach -> 3-fach
        bleiben drei Pool-Kegel unsichtbar eingehaengt und duerfen keinen
        Klick abfangen. Die Kegel sind reine Deko — auch die sichtbaren."""
        self._load_and_wait()
        self._eval("window.__lightos.setViewMode('3D'); true")
        self._push(_payload(prism=50))      # 6-fach -> 5 Pool-Kegel
        self._push(_payload(prism=200))     # 3-fach -> 2 aktiv, 3 unsichtbar
        self.assertEqual(self._z()["prismN"], 2)
        n_pool = int(self._eval(
            "window.__lightos.fixtures['%d'].prismPool.kegel.length" % _FID))
        self.assertEqual(n_pool, 5)
        for i in range(n_pool):
            self.assertIsNone(self._pick_auf_poolkegel(i, nur_pool=True),
                              f"Prisma-Kegel {i} faengt einen Klick ab")
        # Gegenprobe: das Geraet selbst bleibt anklickbar.
        r = self._eval("""
        (function(){
          const L = window.__lightos;
          const f = L.fixtures['%d'];
          f.group.updateMatrixWorld(true);
          L.view.activeCam.updateMatrixWorld();
          const p = f.group.position.clone().project(L.view.activeCam);
          L.__mouse.set(p.x, p.y);
          return String(L.__pickFixture());
        })()""" % _FID)
        self.assertEqual(r, str(_FID), "Geraet nicht mehr anklickbar")


if __name__ == "__main__":
    unittest.main()
