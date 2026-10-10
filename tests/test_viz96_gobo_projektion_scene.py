"""VIZ-96 (B1 + B2): Gobo-Projektion mit Verdeckung — Szenen-Tests.

Bis VIZ-96 lag das Gobo als flache Scheibe auf der Flaeche, die der
Zentralstrahl trifft; ein Hindernis im Strahl ignorierte das Muster. Jetzt
traegt das Pool-Licht eines Geraets das Motiv als Maske im Licht-Loop
(``scene/gobo_projektion.js``), die Verdeckung kommt aus der Shadow-Map.

Gemessen wird ueber die ECHTE Seite (Produktiv-Push), ohne WebGL (offscreen ist
der Kontext verloren — eine Bildpruefung braucht ein Fenster und steht als
Sichtpruefung aus):

* Stufe Hoch: der Patch ist installiert (EIN Hook fuer alle beleuchteten
  Materialien, EIN zusaetzlicher Sampler, Textur-Reserve + 1) und landet im
  echten r128-Shader im Schattenzweig des Spot-Blocks;
* ein Geraet mit Gobo UND Pool-Licht mit Schatten projiziert: das Licht
  leuchtet, traegt Maske + Kachel + Winkel, die Bodenmuster-Scheibe ist
  ausgeblendet; ohne Gobo ist alles wie vorher;
* die Uniform-Werte legen jeden Randstrahl des sichtbaren Kegels auf sein
  Motiv-Teil — gemessen mit der Schattenmatrix von three und den Pixeln des
  Atlas, auch bei geschwenktem Kopf und gedrehtem Gobo;
* Gobo-Wechsel, Drehung, an/aus: Programmschluessel, Material-Versionen,
  Licht- und Schattenzahl bleiben gleich (VIZ-69: keine Neukompilierung);
* die Drehung folgt je Bild dem ANGEZEIGTEN (geglaetteten) Winkel (VIZ-92);
* mehr Gobo-Geraete als Pool-Lichter: nur die Halter projizieren, alle
  anderen behalten das Bodenmuster; kein Gobo-Geraet leuchtet unmaskiert
  (VIZ-92: kein voller Lichtkreis neben dem Muster);
* Stufe Niedrig: exakt das Verhalten vor VIZ-96 (kein Hook, Reserve 6,
  SpotLight mit Gobo aus, Bodenmuster sichtbar).
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
        return "{}"

    attrs["requestFixtures"] = requestFixtures
    attrs["pollControl"] = pollControl
    attrs["requestFullResync"] = Signal()
    return type("MockVisualizerBridgeViz96", (QObject,), attrs)


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


class _Range:
    def __init__(self, lo, hi, name):
        self.range_from, self.range_to, self.name = lo, hi, name
        self.kind = ""


class _Ch:
    def __init__(self, attribute, ranges=()):
        self.attribute = attribute
        self.ranges = list(ranges)


_FID = 960001


def _fx(fid, typ="moving_head"):
    return type("_Fx", (), {"fid": fid, "fixture_type": typ})()


_KANAELE = [
    _Ch("intensity"), _Ch("color_r"), _Ch("color_g"), _Ch("color_b"),
    _Ch("pan"), _Ch("tilt"),
    _Ch("gobo_wheel", [_Range(0, 9, "Offen / kein Gobo"),
                       _Range(10, 19, "Gobo 6 (Spirale)"),
                       _Range(20, 29, "Gobo 5 (Punkte)"),
                       _Range(30, 39, "Gobo 3"),
                       _Range(40, 49, "Gobo 1 (Ring-Spalte)"),
                       _Range(50, 59, "Gobo 2 (Ovale)"),
                       _Range(60, 69, "Gobo 4 (Tetris)"),
                       _Range(70, 79, "Gobo 7 (Zebra)")]),
    _Ch("gobo_rotation"),
]

_GRUND = {"intensity": 255, "color_r": 255, "color_g": 255, "color_b": 255,
          "pan": 128, "tilt": 128, "gobo_wheel": 0, "gobo_rotation": 0}


def _payload(fid=_FID, typ="moving_head", **attrs):
    a = dict(_GRUND)
    a.update(attrs)
    return _build_fixture_payload(_fx(fid, typ), a, _KANAELE)


def _geraet(fid=_FID, typ="moving_head", **lage):
    d = {"fid": fid, "type": typ, "model": typ,
         "x": 0, "y": 6, "z": 0, "rotX": 0, "rotY": 0, "rotZ": 0,
         "r": 0, "g": 0, "b": 0, "intensity": 0, "pan": 128, "tilt": 128}
    d.update(lage)
    return d


class _Basis(unittest.TestCase):
    GERAETE = None          # Liste fuer allFixtures; None = ein Moving Head
    TIER = "high"           # QA-86: jede Seite mit fester Stufe

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

    def _load_and_wait(self):
        url = QUrl.fromLocalFile(_HTML_PATH)
        url.setQuery(f"v={int(time.time() * 1000)}&gputier={self.TIER}")
        self._view.load(url)
        deadline = time.monotonic() + _LOAD_TIMEOUT_S
        while not self._loaded_ok and time.monotonic() < deadline:
            _app.processEvents()
            time.sleep(_POLL_INTERVAL_S)
        self.assertTrue(self._loaded_ok and self._loaded_ok[-1], "Seite nicht geladen")
        self._poll_until_true("!!window.__lightosAppReady")
        geraete = self.GERAETE or [_geraet()]
        self._emit_until_true(
            lambda: self._bridge_obj.allFixtures.emit(json.dumps(geraete)),
            "(function(){ const F = window.__lightos.fixtures; return %s.every(f => !!F[f]); })()"
            % json.dumps([str(g["fid"]) for g in geraete]))

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
        entries = []
        for p in payloads:
            self._seq += 1
            entries.append((self._seq, p))
        n = self._eval(push_script(entries))
        self.assertEqual(n, len(payloads), "Push erreichte das Geraet nicht")

    def _json(self, js):
        return json.loads(self._eval(js))

    def _bild(self, t=None):
        """Ein Renderbild (perFrame + Render-Gate), optional zur Uhrzeit t ms."""
        setze = "" if t is None else "window.__t96 = %r;" % float(t)
        return self._eval("(function(){ %s const L = window.__lightos;"
                          " L.__renderTick(); return 1; })()" % setze)

    def _uhr(self, t):
        self._eval("(function(){ window.__t96 = %r; window.__lightos.__glattUhr("
                   "() => window.__t96); return 1; })()" % float(t))


# ── Messwerkzeuge (JS) ───────────────────────────────────────────────────────

_ZUSTAND_JS = """
(function(){
  const L = window.__lightos, f = L.fixtures['%d'];
  const pool = L.spotPoolInfo(), g = L.goboProjektionInfo();
  const i = pool.halter.indexOf(%d);
  const l = i >= 0 ? L.spotPoolLights()[i] : null;
  return JSON.stringify({
    slot: i, pool: l ? l.intensity : null, schatten: l ? l.castShadow : null,
    winkel: l ? l.angle : null, halbschatten: l ? l.penumbra : null,
    param: (i >= 0 && g.param[i]) ? g.param[i] : null,
    projiziert: pool.goboProjiziert,
    spot: f.spot.intensity, spotWinkel: f.spot.angle, spotHalb: f.spot.penumbra,
    ebene: f.floorSpot.layers.mask, sichtbar: f.floorSpot.visible,
    muster: !!f.floorSpot.material.map, flag: !!f.goboProjiziert,
    index: g.index, aktiv: g.aktiv,
  });
})()
"""

# Alles, was in r128 zum Programmschluessel der beleuchteten Materialien
# gehoert bzw. eine Neukompilierung ausloest: Zusatzschluessel (Hook-Quelltext),
# Material-Versionen (needsUpdate), Zahl der Lichter/Schatten-Lichter.
_PROGRAMM_JS = """
(function(){
  const L = window.__lightos, T = window.THREE;
  let s = L.fixtures['%d'].group;
  while (s.parent) s = s.parent;
  const mats = new Set();
  s.traverse(o => {
    if (!o.material) return;
    for (const m of (Array.isArray(o.material) ? o.material : [o.material])) {
      if (m.isMeshStandardMaterial) mats.add(m);
    }
  });
  const schluessel = new Set();
  let version = 0;
  for (const m of mats) { schluessel.add(m.customProgramCacheKey()); version += m.version; }
  const r = L.renderInfo();
  return JSON.stringify({
    materialien: mats.size, schluessel: schluessel.size, version: version,
    programme: r.programme, lichter: r.lichter, spots: r.spots, schatten: r.schatten,
    pool: L.spotPoolInfo().groesse,
  });
})()
"""

_INSTALLATION_JS = """
(function(){
  const L = window.__lightos, T = window.THREE;
  const P = T.MeshStandardMaterial.prototype;
  const eigen = Object.prototype.hasOwnProperty.call(P, 'onBeforeCompile');
  const std = T.ShaderLib.standard.fragmentShader;
  const sh = { fragmentShader: std, uniforms: {} };
  P.onBeforeCompile.call(new T.MeshStandardMaterial(), sh);
  const fs = sh.fragmentShader;
  const anker = fs.indexOf('vSpotShadowCoord[ i ] ) : 1.0;');
  const atlas = sh.uniforms.lightosGoboMap ? sh.uniforms.lightosGoboMap.value : null;
  return JSON.stringify({
    eigen: eigen,
    standardSchluessel: new T.MeshStandardMaterial().customProgramCacheKey()
      === new T.MeshBasicMaterial().customProgramCacheKey(),
    gepatcht: fs !== std,
    sampler: (fs.match(/uniform\\s+sampler2D\\s+lightos\\w+/g) || []).length,
    maskeNachSchatten: anker >= 0 && fs.indexOf('lightosGoboParam[ i ]') > anker
      && fs.indexOf('lightosGoboParam[ i ]') < fs.indexOf('RE_Direct( directLight', anker),
    atlas: atlas ? [atlas.image.width, atlas.image.height, atlas.generateMipmaps === false,
                    atlas.minFilter === T.LinearFilter] : null,
    info: L.goboProjektionInfo(),
    budget: L.shadowBudgetInfo(),
    stufe: L.tierSettings.goboProjektion,
    kachelPx: L.__goboTexture('zebra').image.width,
  });
})()
"""

# Randstrahlen des sichtbaren Kegels durch die ECHTE Schattenmatrix des
# Pool-Lichts und die Uniform-Werte (wie im Shader) -> Motiv-Koordinate.
# Soll: 0,5 * GOBO_RAND * (sin th, -cos th). Dazu die Atlas-Pixel dort.
_ABBILDUNG_JS = """
(function(){
  const L = window.__lightos, T = window.THREE, f = L.fixtures['%d'];
  const pool = L.spotPoolInfo(), g = L.goboProjektionInfo();
  const i = pool.halter.indexOf(%d);
  if (i < 0 || !g.param[i]) return JSON.stringify({grund: 'kein Pool-Licht'});
  const l = L.spotPoolLights()[i], gpm = g.param[i];
  l.updateMatrixWorld(true); l.target.updateMatrixWorld(true);
  l.shadow.updateMatrices(l);
  const sh = { fragmentShader: T.ShaderLib.standard.fragmentShader, uniforms: {} };
  T.MeshStandardMaterial.prototype.onBeforeCompile.call(new T.MeshStandardMaterial(), sh);
  const cv = sh.uniforms.lightosGoboMap.value.image, ctx = cv.getContext('2d');
  const K = cv.width / g.spalten;
  const spalte = gpm[3] %% g.spalten, zeile = Math.floor(gpm[3] / g.spalten);
  const pixel = (u, v) => ctx.getImageData(
    Math.floor((spalte + u) * K), Math.floor((g.zeilen - 1 - zeile + (1 - v)) * K), 1, 1).data[0];
  const beam = f.beam, p = beam.geometry.parameters;
  beam.updateWorldMatrix(true, false);
  const N = %d;
  let fehler = 0; const hell = [], dunkel = [];
  for (let k = 0; k < 2 * N; k++) {
    const th = Math.PI * k / N;
    const P = beam.localToWorld(new T.Vector3(p.radius * Math.sin(th), -p.height / 2,
                                               p.radius * Math.cos(th)));
    const c = new T.Vector4(P.x, P.y, P.z, 1).applyMatrix4(l.shadow.matrix);
    const dx = c.x / c.w - 0.5, dy = c.y / c.w - 0.5;
    const u = gpm[1] * dx - gpm[2] * dy, v = gpm[2] * dx + gpm[1] * dy;
    fehler = Math.max(fehler, Math.abs(u - 0.31 * Math.sin(th)), Math.abs(v + 0.31 * Math.cos(th)));
    (k %% 2 === 0 ? hell : dunkel).push(pixel(u + 0.5, v + 0.5));
  }
  return JSON.stringify({ fehler: fehler, hell: hell, dunkel: dunkel, kachel: gpm[3],
    drehung: Math.atan2(gpm[2], gpm[1]), skala: Math.hypot(gpm[1], gpm[2]),
    kegel: beam.rotation.y, aktiv: L.bewegungGlaettungAktiv() });
})()
"""

_ALLE_JS = """
(function(){
  const L = window.__lightos, pool = L.spotPoolInfo(), g = L.goboProjektionInfo();
  const lichter = L.spotPoolLights();
  const slots = lichter.map((l, i) => ({
    fid: pool.halter[i], hell: l.intensity > 0, schatten: l.castShadow,
    maske: g.param[i] ? g.param[i][0] : 0,
  }));
  const geraete = {};
  for (const fid in L.fixtures) {
    const f = L.fixtures[fid];
    geraete[fid] = { ebene: f.floorSpot.layers.mask, muster: !!f.floorSpot.material.map,
                     sichtbar: f.floorSpot.visible, flag: !!f.goboProjiziert };
  }
  return JSON.stringify({ slots: slots, geraete: geraete, projiziert: pool.goboProjiziert,
                          schatten: pool.schatten, groesse: pool.groesse });
})()
"""

_RING = 45      # "Gobo 1 (Ring-Spalte)": 8 Boegen bei u = k/8
_ZEBRA = 75


def _kreis(d):
    return (d + math.pi) % (2 * math.pi) - math.pi


# ── Stufe Hoch: ein Geraet ───────────────────────────────────────────────────

class Viz96ProjektionTest(_Basis):
    def _z(self):
        return self._json(_ZUSTAND_JS % (_FID, _FID))

    def test_patch_installiert_ein_sampler_reserve_plus_eins(self):
        self._load_and_wait()
        z = self._json(_INSTALLATION_JS)
        self.assertTrue(z["stufe"])
        self.assertTrue(z["info"]["aktiv"])
        self.assertTrue(z["eigen"], "Hook an MeshStandardMaterial (alle beleuchteten Materialien)")
        self.assertTrue(z["gepatcht"])
        self.assertTrue(z["maskeNachSchatten"],
                        "Maske hinter dem Schattentest des Spot-Blocks, vor RE_Direct")
        self.assertEqual(z["sampler"], 1, "genau EIN zusaetzlicher Textur-Slot")
        self.assertEqual(z["info"]["slots"], 1)
        # EINE Textur mit allen sieben Motiven, ohne Mipmaps.
        px = z["kachelPx"]
        self.assertEqual(z["atlas"], [4 * px, 2 * px, True, True])
        self.assertEqual(sorted(z["info"]["index"].values()), list(range(7)))
        # Slot-Reserve: Schatten-Maps + Atlas + bisherige Reserve passen in die Units.
        b = z["budget"]
        self.assertEqual(b["goboSlots"], 1)
        self.assertEqual(b["reserve"], 7, "bisherige Reserve 6 + 1 fuer den Atlas")
        self.assertEqual(b["budget"], min(b["hardCap"], max(2, b["maxTextures"] - 7)))
        if b["maxTextures"] >= 9:
            self.assertLessEqual(b["budget"] + b["reserve"], b["maxTextures"])
        # 16-Unit-GPU (ANGLE): Hoch behaelt seine 8 Schatten-Lichter.
        self.assertEqual(min(8, max(2, 16 - b["reserve"])), 8)

    def test_gobo_halter_projiziert_und_blendet_bodenmuster_aus(self):
        self._load_and_wait()
        self._push(_payload(gobo_wheel=0))
        self._bild()
        offen = self._z()
        self.assertGreater(offen["pool"], 0.0)
        self.assertTrue(offen["schatten"])
        self.assertEqual(offen["param"][0], 0, "ohne Gobo keine Maske")
        self.assertEqual(offen["ebene"], 1)
        self.assertEqual(offen["projiziert"], [])
        self.assertAlmostEqual(offen["winkel"], offen["spotWinkel"], places=9)
        self.assertAlmostEqual(offen["halbschatten"], offen["spotHalb"], places=9)

        self._push(_payload(gobo_wheel=_RING))
        self._bild()
        z = self._z()
        self.assertEqual(z["projiziert"], [_FID])
        self.assertTrue(z["flag"])
        self.assertGreater(z["spot"], 0.0, "das Geraet bewirbt sich mit voller Staerke um ein Licht")
        self.assertAlmostEqual(z["pool"], z["spot"], places=9)
        self.assertTrue(z["schatten"], "projiziert wird nur mit Shadow-Map (Verdeckung)")
        self.assertEqual(z["param"][0], 1)
        self.assertEqual(z["param"][3], z["index"]["ring_slits"])
        # Bodenmuster-Scheibe ausgeblendet (Ebenen-Maske), ihr Zustand sonst unberuehrt.
        self.assertEqual(z["ebene"], 0)
        self.assertTrue(z["sichtbar"])
        self.assertTrue(z["muster"])
        # Das Licht oeffnet weiter als der Kegel (ganze Kachel), harter Rand.
        self.assertGreater(z["winkel"], z["spotWinkel"])
        self.assertAlmostEqual(z["halbschatten"], 0.05, places=9)

        # Wechsel des Motivs: andere Kachel, sonst nichts.
        self._push(_payload(gobo_wheel=_ZEBRA))
        self._bild()
        w = self._z()
        self.assertEqual(w["param"][3], w["index"]["zebra"])
        self.assertEqual(w["param"][0], 1)
        self.assertEqual(w["ebene"], 0)

        # Gobo aus: Maske weg, Licht wie ohne Gobo, Bodenfleck wieder da.
        self._push(_payload(gobo_wheel=0))
        self._bild()
        zu = self._z()
        self.assertEqual(zu["param"], [0, 1, 0, 0])
        self.assertEqual(zu["projiziert"], [])
        self.assertFalse(zu["flag"])
        self.assertEqual(zu["ebene"], 1)
        self.assertAlmostEqual(zu["winkel"], zu["spotWinkel"], places=9)
        self.assertAlmostEqual(zu["halbschatten"], zu["spotHalb"], places=9)
        self.assertGreater(zu["pool"], 0.0)

    def test_blackout_gibt_das_bodenmuster_frei(self):
        self._load_and_wait()
        self._push(_payload(gobo_wheel=_RING))
        self._bild()
        self.assertEqual(self._z()["ebene"], 0)
        self._push(_payload(gobo_wheel=_RING, intensity=0))
        self._bild()
        z = self._z()
        self.assertEqual(z["projiziert"], [])
        self.assertEqual(z["ebene"], 1, "nicht leuchtend = nicht projizierend")
        self.assertIn(z["pool"], (0.0, None))
        if z["param"] is not None:
            self.assertEqual(z["param"][0], 0)

    def test_wechsel_drehung_an_aus_aendern_nur_uniforms(self):
        self._load_and_wait()
        self._push(_payload(gobo_wheel=0))
        self._bild()
        self._bild()
        vorher = self._json(_PROGRAMM_JS % _FID)
        self.assertGreater(vorher["materialien"], 3)
        self.assertEqual(vorher["schluessel"], 1,
                         "alle beleuchteten Materialien tragen denselben Schluessel-Zusatz")
        self.assertEqual(vorher["schatten"], 1)
        param = []
        for attrs in ({"gobo_wheel": _RING}, {"gobo_wheel": _ZEBRA},
                      {"gobo_wheel": _ZEBRA, "gobo_rotation": 90},
                      {"gobo_wheel": 25, "gobo_rotation": 200, "pan": 100, "tilt": 150},
                      {"gobo_wheel": 0}, {"gobo_wheel": 65}):
            self._push(_payload(**attrs))
            self._bild()
            param.append(self._z()["param"])
            self.assertEqual(self._json(_PROGRAMM_JS % _FID), vorher,
                             f"{attrs}: Programmschluessel/Materialien/Lichtzahl veraendert")
        # ... waehrend die Uniform-Werte sich jedes Mal geaendert haben.
        for a, b in zip(param, param[1:]):
            self.assertNotEqual(a, b)

    def test_randstrahlen_treffen_ihr_motivteil(self):
        self._load_and_wait()
        faelle = [
            {"gobo_wheel": _RING},
            {"gobo_wheel": _RING, "gobo_rotation": 40},
            {"gobo_wheel": _RING, "pan": 100, "tilt": 150},
            {"gobo_wheel": _RING, "pan": 170, "tilt": 110, "gobo_rotation": 201},
        ]
        winkel = []
        for attrs in faelle:
            self._push(_payload(**attrs))
            self._bild()
            self._bild()
            z = self._json(_ABBILDUNG_JS % (_FID, _FID, 8))
            self.assertNotIn("grund", z)
            self.assertLess(z["fehler"], 6e-3,
                            f"{attrs}: Kegelrand liegt nicht auf GOBO_RAND des Motivs {z}")
            self.assertAlmostEqual(z["skala"], 1.0, places=6)
            # Ring-Spalte: 8 Boegen bei u = k/8 -> Randstrahl dort hell, dazwischen dunkel.
            self.assertEqual(len(z["hell"]), 8)
            self.assertTrue(all(v > 200 for v in z["hell"]), f"{attrs}: {z['hell']}")
            self.assertTrue(all(v < 40 for v in z["dunkel"]), f"{attrs}: {z['dunkel']}")
            winkel.append(z["drehung"])
        # Gobo-Drehung dreht die Maske um genau diesen Winkel mit.
        soll = 40 / 255 * 2 * math.pi
        self.assertAlmostEqual(abs(_kreis(winkel[1] - winkel[0])), soll, places=3)

    def test_drehung_folgt_je_bild_dem_angezeigten_winkel(self):
        self._load_and_wait()
        self._uhr(0)
        t = 0.0
        self._push(_payload(gobo_wheel=_RING, gobo_rotation=10))
        self._bild(t)
        for wert in (12, 14, 16):
            t += 1000 / 30
            self._uhr(t)
            self._push(_payload(gobo_wheel=_RING, gobo_rotation=wert))
        werte = []
        # Bilder im Abstand > 1/60 s (Bild-Deckel der Glaettung), das letzte
        # nach dem Ende des Stuecks (33 ms): dort steht das Ziel.
        for versatz in (5.0, 22.0, 40.0):
            self._bild(t + versatz)
            z = self._json(_ABBILDUNG_JS % (_FID, _FID, 8))
            self.assertNotIn("grund", z)
            self.assertLess(z["fehler"], 6e-3,
                            f"+{versatz} ms: Maske und Kegel laufen auseinander {z}")
            werte.append((z["drehung"], z["kegel"], z["aktiv"]))
        schritte = [_kreis(b[0] - a[0]) for a, b in zip(werte, werte[1:])]
        kegel = [_kreis(b[1] - a[1]) for a, b in zip(werte, werte[1:])]
        self.assertTrue(all(abs(s) > 1e-3 for s in schritte),
                        f"die Maske steht zwischen zwei DMX-Updates still: {werte}")
        for s, k in zip(schritte, kegel):
            self.assertAlmostEqual(abs(s), abs(k), places=4,
                                   msg="Maske dreht je Bild so weit wie der Kegel")
        self.assertTrue(werte[0][2], "im ersten Bild laeuft die Glaettung noch")
        self.assertAlmostEqual(werte[-1][1], 16 / 255 * 2 * math.pi, places=6)


# ── Mehr Gobo-Geraete als Lichter ────────────────────────────────────────────

_VIELE = [960100 + n for n in range(10)]


class Viz96PoolKopplungTest(_Basis):
    GERAETE = [_geraet(fid, x=-9 + 2 * n, z=(n % 2) * 2) for n, fid in enumerate(_VIELE)]

    def _alle(self):
        return self._json(_ALLE_JS)

    def test_nur_halter_projizieren_alle_anderen_behalten_das_bodenmuster(self):
        self._load_and_wait()
        self._push(*[_payload(fid, gobo_wheel=_RING) for fid in _VIELE])
        self._bild()
        self._bild()
        z = self._alle()
        self.assertEqual(z["groesse"], 8, "Stufe Hoch: 8 echte Lichter")
        halter = [s["fid"] for s in z["slots"] if s["fid"] is not None]
        self.assertEqual(len(halter), 8)
        self.assertEqual(sorted(z["projiziert"]), sorted(halter))
        for s in z["slots"]:
            self.assertTrue(s["hell"] and s["schatten"], s)
            self.assertEqual(s["maske"], 1, s)
        ohne = [fid for fid in _VIELE if fid not in halter]
        self.assertEqual(len(ohne), 2)
        for fid in _VIELE:
            g = z["geraete"][str(fid)]
            self.assertTrue(g["muster"] and g["sichtbar"], g)
            if fid in halter:
                self.assertEqual(g["ebene"], 0, f"Halter {fid}: Bodenmuster muss aus sein")
                self.assertTrue(g["flag"])
            else:
                self.assertEqual(g["ebene"], 1, f"{fid} ohne Licht behaelt das Bodenmuster")
                self.assertFalse(g["flag"])

    def test_gemischt_kein_gobo_geraet_leuchtet_unmaskiert(self):
        self._load_and_wait()
        mit = _VIELE[:5]
        self._push(*[_payload(fid, gobo_wheel=(_ZEBRA if fid in mit else 0)) for fid in _VIELE])
        self._bild()
        self._bild()
        z = self._alle()
        for s in z["slots"]:
            if s["fid"] is None or not s["hell"]:
                continue
            self.assertEqual(s["maske"], 1 if s["fid"] in mit else 0, s)
        for fid in _VIELE:
            g = z["geraete"][str(fid)]
            if fid not in mit:
                self.assertEqual(g["ebene"], 1, "ohne Gobo bleibt der Bodenfleck")
        # Verliert ein Halter sein Gobo-Licht (alle Gobo-Geraete dunkel), kommt
        # nichts Projiziertes mehr vor und jede Scheibe ist wieder freigegeben.
        self._push(*[_payload(fid, gobo_wheel=_ZEBRA, intensity=0) for fid in mit])
        self._bild()
        self._bild()
        z = self._alle()
        self.assertEqual(z["projiziert"], [])
        self.assertTrue(all(g["ebene"] == 1 for g in z["geraete"].values()))
        self.assertTrue(all(s["maske"] == 0 for s in z["slots"]))


class Viz96MaximalTest(_Basis):
    TIER = "max"
    GERAETE = [_geraet(960200 + n, x=-15 + 2 * n, z=(n % 2) * 2) for n in range(16)]

    def test_ohne_schatten_licht_keine_projektion_und_kein_lichtkreis(self):
        self._load_and_wait()
        fids = [g["fid"] for g in self.GERAETE]
        self._push(*[_payload(fid, gobo_wheel=_RING) for fid in fids])
        self._bild()
        self._bild()
        z = self._json(_ALLE_JS)
        b = self._json("JSON.stringify(window.__lightos.shadowBudgetInfo())")
        self.assertEqual(b["reserve"], 7)
        self.assertEqual(z["groesse"], 16)
        self.assertEqual(z["schatten"], min(16, max(2, b["maxTextures"] - 7)))
        self.assertEqual(len(z["projiziert"]), z["schatten"],
                         "es projizieren genau die Lichter mit Shadow-Map")
        for s in z["slots"]:
            if s["schatten"]:
                self.assertTrue(s["hell"])
                self.assertEqual(s["maske"], 1)
            else:
                # Nicht maskierbar -> dunkel (VIZ-92: kein voller Lichtkreis), Bodenmuster bleibt.
                self.assertFalse(s["hell"], s)
                self.assertEqual(z["geraete"][str(s["fid"])]["ebene"], 1)


# ── Stufe Niedrig: exakt wie vor VIZ-96 ──────────────────────────────────────

class Viz96NiedrigTest(_Basis):
    TIER = "low"

    def test_niedrig_ohne_patch_und_mit_bodenmuster(self):
        self._load_and_wait()
        z = self._json(_INSTALLATION_JS)
        self.assertFalse(z["stufe"])
        self.assertFalse(z["info"]["aktiv"])
        self.assertFalse(z["eigen"], "kein Hook: Shader bytegleich zu vorher")
        self.assertTrue(z["standardSchluessel"], "Programmschluessel wie three ihn liefert")
        self.assertFalse(z["gepatcht"])
        self.assertEqual(z["sampler"], 0)
        self.assertIsNone(z["atlas"])
        self.assertEqual(z["budget"]["reserve"], 6)
        self.assertEqual(z["budget"]["goboSlots"], 0)
        self._push(_payload(gobo_wheel=_RING))
        self._bild()
        g = self._json(_ZUSTAND_JS % (_FID, _FID))
        self.assertEqual(g["spot"], 0.0, "wie seit VIZ-92: SpotLight mit Gobo aus")
        self.assertIn(g["pool"], (0.0, None))
        self.assertEqual(g["projiziert"], [])
        self.assertFalse(g["flag"])
        self.assertEqual(g["ebene"], 1)
        self.assertTrue(g["muster"] and g["sichtbar"], "das flache Bodenmuster traegt das Bild")


# ── Echtes Bild (nur mit GL-Kontext) ─────────────────────────────────────────
# Offscreen bekommt die Seite auf manchen Rechnern einen echten GL-Kontext, auf
# anderen keinen (dann ueberspringt der Test). Aufbau: grauer Boden, ein Balken
# ("Traverse") auf 2,3 m Hoehe genau im Randstrahl th = 90 Grad, Kamera schraeg
# von oben. Gemessen werden einzelne Bildpunkte, deren Lage aus der Geometrie
# folgt (Randstrahlen des sichtbaren Kegels auf Boden bzw. Balkenoberseite).
_BILD_AUFBAU_JS = """
(function(){
  const L = window.__lightos, T = window.THREE, f = L.fixtures['%d'];
  let scene = f.group; while (scene.parent) scene = scene.parent;
  const cv = document.getElementsByTagName('canvas')[0];
  const gl = cv && (cv.getContext('webgl2') || cv.getContext('webgl'));
  if (!gl || gl.isContextLost()) return JSON.stringify({gl: false});
  L.settings.showCones = false; L.settings.showFloorSpots = false;
  Object.defineProperty(window, 'innerWidth', { value: 640, configurable: true });
  Object.defineProperty(window, 'innerHeight', { value: 480, configurable: true });
  window.dispatchEvent(new Event('resize'));
  const grau = () => new T.MeshStandardMaterial({ color: 0x909090, roughness: 0.9 });
  const boden = new T.Mesh(new T.BoxGeometry(30, 0.02, 30), grau());
  boden.position.y = 0.01; boden.receiveShadow = true; scene.add(boden);
  const BY = 0.02, TOP = 2.3;
  const i = L.spotPoolInfo().halter.indexOf(%d);
  if (i < 0) return JSON.stringify({gl: true, grund: 'kein Pool-Licht'});
  const Lp = L.spotPoolLights()[i].position.clone();
  const beam = f.beam, p = beam.geometry.parameters;
  beam.updateWorldMatrix(true, false);
  const strahl = (grad, y) => {
    const th = grad * Math.PI / 180;
    const d = beam.localToWorld(new T.Vector3(p.radius * Math.sin(th), -p.height / 2,
                                               p.radius * Math.cos(th))).sub(Lp);
    return Lp.clone().addScaledVector(d, (y - Lp.y) / d.y);
  };
  // Ring-Spalte: Boegen bei th = k * 45 Grad, Luecken dazwischen.
  const punkte = {
    mitte: new T.Vector3(Lp.x, BY, Lp.z),
    bogenFrei: strahl(270, BY), lueckeFrei: strahl(292.5, BY),
    bogenHinter: strahl(90, BY),
    balkenBogen: strahl(90, TOP), balkenLuecke: strahl(112.5, TOP),
  };
  const a = punkte.balkenBogen, b = punkte.balkenLuecke;
  const x0 = Math.min(a.x, b.x) - 0.25, x1 = Math.max(a.x, b.x) + 0.25;
  const z0 = Math.min(a.z, b.z) - 0.25, z1 = Math.max(a.z, b.z) + 0.25;
  const balken = new T.Mesh(new T.BoxGeometry(x1 - x0, 0.3, z1 - z0), grau());
  balken.position.set((x0 + x1) / 2, TOP - 0.15, (z0 + z1) / 2);
  balken.castShadow = true; balken.receiveShadow = true; balken.visible = false;
  scene.add(balken);
  const cam = new T.PerspectiveCamera(50, 640 / 480, 0.1, 100);
  cam.position.set(Lp.x, 11, Lp.z + 7); cam.lookAt(Lp.x, 0, Lp.z);
  cam.updateMatrixWorld(true);
  L.view.activeCam = cam;
  const W = gl.drawingBufferWidth, H = gl.drawingBufferHeight;
  const px = {};
  for (const k in punkte) {
    const n = punkte[k].clone().project(cam);
    px[k] = [Math.round((n.x * 0.5 + 0.5) * W), Math.round((n.y * 0.5 + 0.5) * H)];
  }
  window.__v96 = function(balkenDa) {
    balken.visible = !!balkenDa;
    L.requestRender(); L.__renderTick();
    const out = {}, buf = new Uint8Array(36);
    for (const k in px) {
      gl.readPixels(px[k][0] - 1, px[k][1] - 1, 3, 3, gl.RGBA, gl.UNSIGNED_BYTE, buf);
      let s = 0;
      for (let j = 0; j < 36; j += 4) s += buf[j] + buf[j + 1] + buf[j + 2];
      out[k] = s / 27;
    }
    out.verloren = gl.isContextLost();
    out.programme = L.renderInfo().programme;
    return JSON.stringify(out);
  };
  return JSON.stringify({ gl: true, W: W, H: H, px: px, balkenX: [x0, x1], mitteX: Lp.x });
})()
"""

_PROGRAMME_JS = """
(function(){
  const L = window.__lightos;
  return JSON.stringify(L.__programmInfo().map(p => {
    const q = p.quelle;
    // Die ausgerollte Maske des ersten Schatten-Lichts. (Der Kopf
    // `uniform vec4 lightosGoboParam[ n ]` steht in JEDEM gepatchten Programm,
    // auch in einem ohne Schatten — dort hinter einem toten #if.)
    const maske = q.indexOf('vec4 lightosGp = lightosGoboParam[ 0 ]');
    const schatten = maske >= 0 ? q.lastIndexOf('vSpotShadowCoord[ 0 ] ) : 1.0;', maske) : -1;
    return {
      name: p.name, sampler: p.sampler, maske: maske >= 0,
      spur: q.indexOf('lightosGobo') >= 0,
      atlas: q.split('uniform sampler2D lightosGoboMap;').length - 1,
      lage: maske >= 0 && schatten >= 0
        && q.slice(schatten, maske).indexOf('RE_Direct(') < 0
        && q.slice(schatten, maske).indexOf('#endif') < 0
        && q.indexOf('RE_Direct( directLight', maske) > maske,
      nacktesI: /lightosGoboParam\\[ i \\]/.test(q),
    };
  }));
})()
"""


class _BildBasis(_Basis):
    def _aufbau(self):
        self._load_and_wait()
        self._push(_payload(gobo_wheel=_RING))
        self._bild()
        self._bild()
        a = self._json(_BILD_AUFBAU_JS % (_FID, _FID))
        if not a.get("gl"):
            self.skipTest("kein GL-Kontext (offscreen) — Bildpruefung nur mit Grafikkarte")
        self.assertNotIn("grund", a)
        if a["W"] < 320 or a["H"] < 240:
            self.skipTest(f"Zeichenflaeche zu klein: {a}")
        return a

    def _messen(self, balken, **attrs):
        self._push(_payload(**attrs))
        self._bild()
        z = self._json("window.__v96(%s)" % ("true" if balken else "false"))
        if z["verloren"]:
            self.skipTest("GL-Kontext waehrend der Messung verloren")
        return z


class Viz96BildTest(_BildBasis):
    HELL = 40       # Abstand zum unbeleuchteten Bild, ab dem ein Punkt Licht traegt
    DUNKEL = 12     # ... bis zu dem er als unbeleuchtet gilt

    def test_muster_auf_dem_hindernis_und_schatten_dahinter(self):
        a = self._aufbau()
        self.assertGreater(a["balkenX"][0] - a["mitteX"], 0.3, "Balken darf die Mitte nicht decken")
        for balken in (False, True):
            null = self._messen(balken, gobo_wheel=_RING, intensity=0)
            if max(null[k] for k in ("mitte", "bogenFrei")) < 5:
                self.skipTest(f"leeres Bild (kein Rendern offscreen): {null}")
            offen = self._messen(balken, gobo_wheel=0)
            gobo = self._messen(balken, gobo_wheel=_RING)

            def d(bild, punkt):
                return bild[punkt] - null[punkt]

            # Ohne Gobo: voller Lichtkreis in der Mitte.
            self.assertGreater(d(offen, "mitte"), self.HELL, (balken, offen, null))
            # Mit Gobo nimmt die Maske dort Licht WEG (Ring-Spalte hat keine Mitte) ...
            self.assertLess(d(gobo, "mitte"), self.DUNKEL, (balken, gobo, null))
            # ... und legt den Bogen auf den Kegelrand, die Luecke bleibt dunkel.
            self.assertGreater(d(gobo, "bogenFrei"), self.HELL, (balken, gobo, null))
            self.assertLess(d(gobo, "lueckeFrei"), self.DUNKEL, (balken, gobo, null))
            if not balken:
                self.assertGreater(d(gobo, "bogenHinter"), self.HELL, (gobo, null))
            else:
                # Verdeckung: hinter dem Balken kommt das Muster NICHT durch ...
                self.assertLess(d(gobo, "bogenHinter"), self.DUNKEL,
                                f"Muster leuchtet durch das Hindernis: {gobo} / {null}")
                # ... es liegt stattdessen AUF dem Balken, mit dunkler Luecke daneben.
                self.assertGreater(d(gobo, "balkenBogen"), self.HELL, (gobo, null))
                self.assertLess(d(gobo, "balkenLuecke"), self.DUNKEL, (gobo, null))

    def test_uebersetzte_programme_bleiben_gleich_und_tragen_einen_atlas(self):
        self._aufbau()
        erstes = self._messen(True, gobo_wheel=_RING)
        zahl = erstes["programme"]
        self.assertGreater(zahl, 0)
        for attrs in ({"gobo_wheel": _ZEBRA}, {"gobo_wheel": _ZEBRA, "gobo_rotation": 77},
                      {"gobo_wheel": 0}, {"gobo_wheel": 25, "pan": 110, "tilt": 140},
                      {"gobo_wheel": 25, "intensity": 0}, {"gobo_wheel": _RING}):
            z = self._messen(True, **attrs)
            self.assertEqual(z["programme"], zahl,
                             f"{attrs}: neues Shader-Programm im Betrieb (VIZ-69)")
        progs = self._json(_PROGRAMME_JS)
        self.assertEqual(len(progs), zahl)
        mit = [p for p in progs if p["maske"]]
        self.assertGreater(len(mit), 0, "kein beleuchtetes Programm traegt die Maske")
        b = self._json("JSON.stringify(window.__lightos.shadowBudgetInfo())")
        pool = self._json("JSON.stringify(window.__lightos.spotPoolInfo())")
        for p in mit:
            self.assertTrue(p["lage"], f"{p['name']}: Maske nicht hinter dem Schattentest")
            self.assertEqual(p["atlas"], 1)
            self.assertFalse(p["nacktesI"])
            self.assertLessEqual(p["sampler"], b["maxTextures"])
        # Material ohne eigene Textur: Shadow-Maps + genau EIN weiterer Sampler.
        self.assertEqual(min(p["sampler"] for p in mit), pool["schatten"] + 1)
        # Unbeleuchtete Programme (Kegel, Bodenfleck, Sprites) bleiben unberuehrt;
        # ein beleuchtetes Programm OHNE Schatten belegt keinen Atlas-Slot.
        for p in progs:
            if p["name"] != "MeshStandardMaterial":
                self.assertFalse(p["spur"], p)
            elif not p["maske"]:
                self.assertEqual(p["sampler"], 0, p)


class Viz96BildNiedrigTest(_BildBasis):
    TIER = "low"

    def test_niedrig_kein_programm_traegt_die_maske(self):
        self._load_and_wait()
        self._push(_payload(gobo_wheel=0))
        self._bild()
        self._bild()
        progs = self._json(_PROGRAMME_JS)
        if not progs:
            self.skipTest("kein GL-Kontext (offscreen)")
        self.assertTrue(all(not p["spur"] for p in progs), "Niedrig: Shader wie vor VIZ-96")
        pool = self._json("JSON.stringify(window.__lightos.spotPoolInfo())")
        beleuchtet = [p["sampler"] for p in progs if p["name"] == "MeshStandardMaterial"]
        self.assertTrue(beleuchtet)
        self.assertEqual(max(beleuchtet), pool["schatten"], "nur die Shadow-Maps, kein Atlas")


if __name__ == "__main__":
    unittest.main()
