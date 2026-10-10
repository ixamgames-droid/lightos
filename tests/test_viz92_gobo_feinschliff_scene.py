"""VIZ-92: Gobo-Feinschliff und Eigenschatten der Geraete (Szenen-Tests).

Befunde (Projektinhaber 08.10., Gobo-Live-Demo, Stufe Hoch, generischer MH16)
und was hier ueber die ECHTE Seite (Produktiv-Push) gemessen wird:

1. Neben dem Gobo-Muster lag am Boden noch die volle runde Lichtflaeche des
   Strahlers (SpotLight mit 30 %). -> Mit Gobo leuchtet kein unmaskiertes
   Licht mehr (seit VIZ-96 traegt das Pool-Licht auf Hoch/Maximal das Gobo als
   Maske, auf Niedrig bleibt es dunkel), das Bodenmuster traegt keinen
   Pool-Verlauf, und kein heller Motiv-Pixel liegt weit ausserhalb des
   Kegelrands (Zebra-Balken liefen bis 0,94 des Scheibenradius).
2. Zebra kantig/pixelig: 128-px-Textur auf mehreren Metern Bodenfleck. ->
   Texel am Boden kleiner als 2 cm, Mipmaps + anisotrope Filterung.
3. Rotierende Gobos ruckelten (Winkel nur je DMX-Update). -> Je Renderbild
   gleich grosse Winkelschritte; das Bodenmuster dreht in JEDEM Bild mit und
   jeder Teilstrahl endet weiter auf hellem Muster.
4. Der Gobo-Fleck hing beim Schwenken stufenweise nach. -> Kopf, Kegel,
   Bodenmuster und Pool-Ziel folgen je Bild dem ANGEZEIGTEN Kopf.
5. Geraete warfen ihren eigenen Schatten (Pool-Licht 1 m ueber dem Sockel,
   der Strahl lief durch Sockel/Buegel/Kopf). -> Lichtursprung an der Linse,
   Schattenkamera ab SCHATTEN_NEAR: kein Strahl von der Lichtquelle zum Boden
   unter der Linse trifft das eigene Gehaeuse jenseits von SCHATTEN_NEAR —
   fuer alle Geraetetypen mit Schatten-Licht.

Kein WebGL noetig (offscreen geht der Kontext verloren): gemessen werden
Szenenzustand, Textur-Pixel (2D-Canvas) und Strahlengaenge (Raycaster).
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
    return type("MockVisualizerBridgeViz92", (QObject,), attrs)


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


_FID = 920001


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

    def _z(self):
        return json.loads(self._eval(_ZUSTAND_JS % _FID))

    def _json(self, js):
        return json.loads(self._eval(js))

    def _bild(self, t=None):
        """Ein Renderbild (perFrame + Render-Gate), optional zur Uhrzeit t ms."""
        setze = "" if t is None else "window.__t92 = %r;" % float(t)
        return self._eval("(function(){ %s const L = window.__lightos;"
                          " L.__renderTick(); return 1; })()" % setze)

    def _uhr(self, t):
        self._eval("(function(){ window.__t92 = %r; window.__lightos.__glattUhr("
                   "() => window.__t92); return 1; })()" % float(t))


# ── Messwerkzeuge (JS) ───────────────────────────────────────────────────────

_STILE = ["ring_slits", "ovals", "circle_of_circles", "tetris", "dots", "spiral", "zebra"]

# Groesster Abstand (Anteil des Textur-Radius) eines hellen Motiv-Pixels von
# der Mitte, je Stil — der Kegelrand liegt bei GOBO_RAND (0,62).
_MUSTER_RADIUS_JS = """
(function(){
  const L = window.__lightos, out = {};
  for (const stil of %s) {
    const c = L.__goboTexture(stil).image, g = c.getContext('2d');
    const d = g.getImageData(0, 0, c.width, c.height).data, M = c.width / 2;
    let rmax = 0;
    for (let y = 0; y < c.height; y++) for (let x = 0; x < c.width; x++) {
      if (d[(y * c.width + x) * 4] > 127) {
        const r = Math.hypot(x + 0.5 - M, y + 0.5 - M) / M;
        if (r > rmax) rmax = r;
      }
    }
    out[stil] = rmax;
  }
  return JSON.stringify(out);
})()
""" % json.dumps(_STILE)

_LICHT_JS = """
(function(){
  const L = window.__lightos, f = L.fixtures['%d'];
  const i = L.spotPoolInfo().halter.indexOf(%d);
  const l = i >= 0 ? L.spotPoolLights()[i] : null;
  const fm = f.floorSpot.material;
  return JSON.stringify({
    spot: f.spot.intensity,
    pool: l ? l.intensity : null,
    alphaMap: fm.alphaMap === null ? 'null'
      : (fm.alphaMap === L.poolFalloffTexture() ? 'falloff' : 'andere'),
    muster: !!fm.map,
    // VIZ-96: traegt das Pool-Licht das Gobo als Maske (Projektion)?
    projektion: L.goboProjektionInfo().aktiv,
    maske: (i >= 0 && L.goboProjektionInfo().param[i]) ? L.goboProjektionInfo().param[i][0] : 0,
  });
})()
"""

# Textur-Guete und Texelgroesse des Bodenmusters in Metern (groesste Halbachse
# der Bodenscheibe / halbe Texturbreite).
_TEXEL_JS = """
(function(){
  const L = window.__lightos, T = window.THREE, f = L.fixtures['%d'];
  const disc = f.floorSpot, tex = disc.material.map;
  disc.updateWorldMatrix(true, false);
  const e = disc.matrixWorld.elements;
  const a = e[0], b = e[4], c = e[2], d = e[6];
  const s1 = a*a + b*b + c*c + d*d, det = a*d - b*c;
  const smax = Math.sqrt(Math.max(0, s1/2 + Math.sqrt(Math.max(0, s1*s1/4 - det*det))));
  const halbachse = smax * disc.geometry.parameters.radius;
  const strahl = f.beam.material.map;
  return JSON.stringify({
    breite: tex.image.width, halbachse: halbachse,
    texel: 2 * halbachse / tex.image.width,
    mipmap: tex.generateMipmaps === true && tex.minFilter === T.LinearMipmapLinearFilter,
    aniso: tex.anisotropy,
    strahlBreite: strahl.image.width,
    strahlMipmap: strahl.generateMipmaps === true && strahl.minFilter === T.LinearMipmapLinearFilter,
  });
})()
"""

# Angezeigter Zustand je Bild: Gobo-Winkel des Kegels, Winkel der Bodenmatrix,
# Pan/Tilt und ob das Pool-Ziel auf der Achse des ANGEZEIGTEN Kopfes liegt.
_BILD_JS = """
(function(){
  const L = window.__lightos, T = window.THREE, f = L.fixtures['%d'];
  f.floorSpot.updateWorldMatrix(true, false);
  const e = f.floorSpot.matrixWorld.elements;
  f.head.updateWorldMatrix(true, false);
  const o = new T.Vector3(); f.head.getWorldPosition(o);
  const q = new T.Quaternion(); f.head.getWorldQuaternion(q);
  const dir = new T.Vector3(0, -1, 0).applyQuaternion(q);
  const t = -o.y / dir.y;
  const hx = o.x + dir.x * t, hz = o.z + dir.z * t;
  return JSON.stringify({
    gobo: f.beam.rotation.y, disc: Math.atan2(e[2], e[0]),
    pan: f.yoke.rotation.y, tilt: f.head.rotation.x,
    zielAbw: Math.hypot(f.spotTarget.position.x - hx, f.spotTarget.position.z - hz),
    aktiv: L.bewegungGlaettungAktiv(),
    beamOpacity: f.beam.material.opacity, fleck: f.floorSpot.visible,
  });
})()
"""

# Eigenschatten: Strahlen von der Lichtquelle (Pool-Licht des Geraets) zum
# Boden unter der Linse und zu 8 Punkten am Kegelrand (80 %%) — trifft einer
# davon das EIGENE Gehaeuse (castShadow-Meshes, beide Seiten: die Shadow-Map
# zeichnet in r128 die Rueckseiten) jenseits der Schattenkamera-Nahgrenze,
# liegt dort sein Schatten.
_EIGENSCHATTEN_JS = """
(function(){
  const L = window.__lightos, T = window.THREE, f = L.fixtures['%d'];
  const i = L.spotPoolInfo().halter.indexOf(%d);
  if (i < 0) return JSON.stringify({fehler: 'kein Pool-Licht'});
  const l = L.spotPoolLights()[i];
  const soll = L.__lichtUrsprung(f, new T.Vector3());
  const meshes = [];
  f.group.updateMatrixWorld(true);
  f.group.traverse(o => { if (o.isMesh && o.castShadow) meshes.push(o); });
  const seiten = meshes.map(m => m.material.side);
  meshes.forEach(m => { m.material.side = T.DoubleSide; });
  const rc = new T.Raycaster();
  const beam = f.beam, p = beam.geometry.parameters;
  beam.updateWorldMatrix(true, false);
  const ziele = [f.spotTarget.position.clone()];
  for (let k = 0; k < 8; k++) {
    const th = k / 8 * Math.PI * 2;
    ziele.push(beam.localToWorld(new T.Vector3(0.8 * p.radius * Math.sin(th), -p.height / 2,
                                                0.8 * p.radius * Math.cos(th))));
  }
  let treffer = 0, naechster = Infinity, strahlen = 0;
  for (const z of ziele) {
    const dir = z.clone().sub(l.position);
    const weite = dir.length();
    if (!(weite > 1e-6)) continue;
    rc.set(l.position, dir.normalize());
    rc.near = 0; rc.far = weite;
    strahlen++;
    for (const h of rc.intersectObjects(meshes, false)) {
      if (h.distance > l.shadow.camera.near) { treffer++; naechster = Math.min(naechster, h.distance); }
    }
  }
  meshes.forEach((m, j) => { m.material.side = seiten[j]; });
  return JSON.stringify({
    treffer: treffer, strahlen: strahlen, meshes: meshes.length,
    naechster: isFinite(naechster) ? naechster : null,
    near: l.shadow.camera.near, schatten: l.castShadow,
    abw: l.position.distanceTo(soll), leuchtet: l.intensity > 0,
  });
})()
"""


def _schritte(werte):
    return [b - a for a, b in zip(werte, werte[1:])]


def _kreis(d):
    return (d + math.pi) % (2 * math.pi) - math.pi


# ── 1 + 2: Muster statt Kreis, Textur-Guete ─────────────────────────────────

class Viz92MusterTest(_Basis):
    def test_mit_gobo_kein_voller_lichtkreis(self):
        self._load_and_wait()
        self._push(_payload(gobo_wheel=0))
        self._bild()
        offen = self._json(_LICHT_JS % (_FID, _FID))
        self.assertGreater(offen["spot"], 0.0)
        self.assertGreater(offen["pool"], 0.0, offen)
        self.assertEqual(offen["alphaMap"], "falloff")
        for rad in (25, 45, 65, 75):
            self._push(_payload(gobo_wheel=rad))
            self._bild()
            z = self._json(_LICHT_JS % (_FID, _FID))
            # Ein UNMASKIERTES Licht waere am Boden der volle runde Fleck neben
            # dem Muster. Seit VIZ-96 (Stufe Hoch) darf das Pool-Licht leuchten,
            # aber nur mit dem Gobo als Maske (scene/gobo_projektion.js); ohne
            # Projektion (Stufe Niedrig, test_viz96_*) bleibt es dunkel.
            self.assertTrue(z["projektion"], "Stufe Hoch projiziert")
            self.assertGreater(z["pool"], 0.0, f"Gobo {rad}: {z}")
            self.assertEqual(z["maske"], 1, f"Gobo {rad}: Pool-Licht leuchtet unmaskiert {z}")
            self.assertTrue(z["muster"])
            # Kein Pool-Verlauf ueber dem Muster: die Teile am Kegelrand waeren
            # sonst halb so hell wie der Kern.
            self.assertEqual(z["alphaMap"], "null", z)
        self._push(_payload(gobo_wheel=0))
        self._bild()
        zurueck = self._json(_LICHT_JS % (_FID, _FID))
        self.assertEqual(zurueck, offen)

    def test_muster_bleibt_am_kegelrand(self):
        self._load_and_wait()
        r = self._json(_MUSTER_RADIUS_JS)
        # Zebra: die Balken enden knapp hinter dem Kegelrand (0,62 * 1,15),
        # nicht mehr bei 0,94 als Streifen neben dem Fleck.
        self.assertLessEqual(r["zebra"], 0.62 * 1.15 + 0.01, r)
        self.assertGreater(r["zebra"], 0.62, r)
        for stil, rmax in r.items():
            self.assertLessEqual(rmax, 0.9, f"{stil}: Motiv reicht bis {rmax}")

    def test_textur_fein_genug_und_gefiltert(self):
        self._load_and_wait()
        self._push(_payload(gobo_wheel=75))          # Zebra
        z = self._json(_TEXEL_JS % _FID)
        # Kopf 6 m hoch: Bodenscheibe ~3 m Halbachse. Ein Texel war bei
        # 128 px rund 5 cm — sichtbare Treppen an den Balkenkanten.
        self.assertGreater(z["halbachse"], 2.0, z)
        self.assertLess(z["texel"], 0.02, z)
        self.assertGreaterEqual(z["breite"], 512)
        self.assertTrue(z["mipmap"], z)
        self.assertGreaterEqual(z["aniso"], 1)
        self.assertGreaterEqual(z["strahlBreite"], 512)
        self.assertTrue(z["strahlMipmap"], z)


# ── 3 + 4: Glaettung je Renderbild ──────────────────────────────────────────

_TAKT = 1000.0 / 30


class Viz92GlaettungTest(_Basis):
    def _strom(self, schritte_fn, n=12):
        """n Updates im 30-Hz-Takt (Fake-Uhr), je zwei Bilder dazwischen."""
        bilder = []
        for i in range(n + 1):
            t = i * _TAKT
            self._uhr(t)
            self._push(schritte_fn(i))
            for versatz in (_TAKT / 4, 3 * _TAKT / 4):
                self._bild(t + versatz)
                bilder.append(self._json(_BILD_JS % _FID))
        return bilder

    def test_gobo_drehung_gleichmaessig_je_bild(self):
        self._load_and_wait()
        dmx = 2 * math.pi / 255
        bilder = self._strom(lambda i: _payload(gobo_wheel=25, gobo_rotation=100 + i))
        w = [b["gobo"] for b in bilder][2:]
        s = _schritte(w)
        # Jedes Bild dreht weiter, und zwar gleich weit (halber DMX-Schritt) —
        # ohne Glaettung stand jedes zweite Bild still.
        self.assertGreater(min(s), 0.4 * dmx, s)
        self.assertLess(max(s), 0.6 * dmx, s)
        # Das Bodenmuster dreht in JEDEM Bild mit (affine Bodenmatrix).
        d = [_kreis(x) for x in _schritte([b["disc"] for b in bilder][2:])]
        self.assertGreater(min(abs(x) for x in d), 0.3 * dmx, d)
        # Ende: exakt das Ziel, Glaettung aus.
        self._bild(13 * _TAKT + 100)
        ende = self._json(_BILD_JS % _FID)
        self.assertAlmostEqual(ende["gobo"], (112 / 255) * 2 * math.pi, places=9)
        self.assertFalse(ende["aktiv"])

    def test_gobo_wraparound_kurzer_weg(self):
        self._load_and_wait()
        bilder = self._strom(lambda i: _payload(gobo_wheel=25, gobo_rotation=(250 + i) % 255),
                             n=10)
        s = [_kreis(x) for x in _schritte([b["gobo"] for b in bilder][2:])]
        dmx = 2 * math.pi / 255
        # 254 -> 0: auf dem Kreis ein normaler Schritt, kein Umlauf rueckwaerts
        # (255 und 0 sind derselbe Winkel, deshalb % 255).
        self.assertGreater(min(s), 0.0, s)
        self.assertLess(max(s), 2.5 * dmx, s)

    def test_fleck_folgt_dem_angezeigten_kopf(self):
        from test_viz83_gobo_strahl_scene import _TREFFER_JS
        self._load_and_wait()
        bilder = []
        fehler = []
        for i in range(13):
            t = i * _TAKT
            self._uhr(t)
            self._push(_payload(gobo_wheel=25, pan=100 + i, tilt=150))
            for versatz in (_TAKT / 4, 3 * _TAKT / 4):
                self._bild(t + versatz)
                bilder.append(self._json(_BILD_JS % _FID))
                # Jeder Teilstrahl endet auch MITTEN in der Bewegung auf
                # hellem Bodenmuster (Muster sitzt unter dem angezeigten Kopf).
                for tr in json.loads(self._eval(_TREFFER_JS % _FID)):
                    if tr["hell"] <= 127:
                        fehler.append((i, versatz, tr))
        self.assertEqual(fehler[:4], [], f"{len(fehler)} Teilstrahlen im Dunkeln")
        pan = [b["pan"] for b in bilder][2:]
        s = _schritte(pan)
        schritt = math.pi / 128                      # 1 DMX Pan bei 360 Grad
        self.assertGreater(min(s), 0.4 * schritt, s)
        self.assertLess(max(s), 0.6 * schritt, s)
        # Pool-Ziel (= Mitte des Lichts) auf der Achse des angezeigten Kopfes.
        self.assertLess(max(b["zielAbw"] for b in bilder), 1e-6)

    def test_sprung_und_blackout_bleiben_sofort(self):
        self._load_and_wait()
        self._uhr(0)
        self._push(_payload(gobo_wheel=25, pan=100))
        self._uhr(_TAKT)
        self._push(_payload(gobo_wheel=25, pan=101))    # laufende Bewegung
        self._bild(_TAKT + 5)
        self.assertTrue(self._json(_BILD_JS % _FID)["aktiv"])
        # Blackout mitten in der Bewegung: im selben Update dunkel.
        self._uhr(2 * _TAKT)
        self._push(_payload(gobo_wheel=25, pan=102, intensity=0))
        self._bild(2 * _TAKT + 1)
        z = self._json(_BILD_JS % _FID)
        self.assertEqual(z["beamOpacity"], 0.0)
        self.assertFalse(z["fleck"])
        # Grosser Sprung (Cue): das naechste Bild steht am Ziel.
        self._uhr(3 * _TAKT)
        self._push(_payload(gobo_wheel=25, pan=200))
        self._bild(3 * _TAKT + 1)
        z = self._json(_BILD_JS % _FID)
        self.assertAlmostEqual(z["pan"], (200 - 128) / 128 * math.pi, places=9)
        self.assertFalse(z["aktiv"])

    def test_farb_update_mitten_in_der_bewegung_springt_nicht_vor(self):
        # Ein reines Farb-Update setzt im DMX-Pfad auch Pan neu (aufs Ziel);
        # das naechste Bild muss trotzdem den Zwischenstand zeigen.
        self._load_and_wait()
        self._uhr(0)
        self._push(_payload(gobo_wheel=25, pan=100))
        self._uhr(_TAKT)
        self._push(_payload(gobo_wheel=25, pan=101))
        self._bild(_TAKT + 8)
        vorher = self._json(_BILD_JS % _FID)["pan"]
        self._uhr(_TAKT + 10)
        self._push(_payload(gobo_wheel=25, pan=101, color_g=0))
        self._bild(_TAKT + 12)                       # nur 4 ms nach dem letzten Bild
        z = self._json(_BILD_JS % _FID)
        ziel = (101 - 128) / 128 * math.pi
        self.assertTrue(z["aktiv"])
        self.assertGreater(z["pan"], vorher - 1e-12)
        self.assertLess(z["pan"], ziel - 1e-6, "Bild zeigt schon das Ziel")

    def test_hoechstens_60_glaettungsbilder_je_sekunde(self):
        self._load_and_wait()
        self._uhr(0)
        self._push(_payload(gobo_wheel=25, pan=100))
        self._uhr(_TAKT)
        self._push(_payload(gobo_wheel=25, pan=101))
        self._bild(_TAKT + 8)
        a = self._json(_BILD_JS % _FID)["pan"]
        self._bild(_TAKT + 12)                       # 240-Hz-Takt: kein neuer Schritt
        b = self._json(_BILD_JS % _FID)["pan"]
        self._bild(_TAKT + 26)
        c = self._json(_BILD_JS % _FID)["pan"]
        self.assertEqual(a, b)
        self.assertGreater(c, b)


# ── 5: Eigenschatten ────────────────────────────────────────────────────────

_TYPEN = ["moving_head", "pixel_head", "scanner", "par", "led_bar", "strobe",
          "dimmer", "other"]
# Stellungen je Geraet: (fid, typ, Lage, Pan, Tilt)
_FAELLE = []
for _i, _typ in enumerate(_TYPEN):
    _FAELLE.append((921000 + _i, _typ, {"x": _i * 3 - 10, "z": -4}, 128, 128))
# Schwenkende Koepfe zusaetzlich schraeg (die "Fledermaus" aus Buegel/Kopf).
_FAELLE += [
    (921100, "moving_head", {"x": 2, "z": 4}, 128, 170),
    (921101, "moving_head", {"x": 6, "z": 4}, 90, 100),
    (921102, "moving_head", {"x": -6, "z": 4, "rotX": 180, "y": 7}, 128, 20),
    (921103, "scanner", {"x": 10, "z": 4}, 140, 160),
]


class Viz92EigenschattenTest(_Basis):
    GERAETE = [_geraet(fid, typ, **lage) for fid, typ, lage, _p, _t in _FAELLE]
    TIER = "max"            # 16 Pool-Lichter: jedes Geraet bekommt eins

    def test_kein_geraet_beschattet_sich_selbst(self):
        self._load_and_wait()
        self._push(*[_payload(fid, typ, pan=p, tilt=t) for fid, typ, _l, p, t in _FAELLE])
        self._bild()
        self._bild()
        geprueft = 0
        fehler = []
        for fid, typ, _l, p, t in _FAELLE:
            z = self._json(_EIGENSCHATTEN_JS % (fid, fid))
            self.assertNotIn("fehler", z, f"{typ}/{fid}: {z}")
            self.assertGreater(z["meshes"], 0, f"{typ}: keine Schattenwerfer gefunden")
            self.assertTrue(z["leuchtet"], f"{typ}: Pool-Licht dunkel {z}")
            # Das Pool-Licht sitzt an der Linse (lichtUrsprung) ...
            self.assertLess(z["abw"], 1e-9, f"{typ}: {z}")
            self.assertGreaterEqual(z["strahlen"], 9)
            geprueft += z["strahlen"]
            # ... und kein Strahl trifft das eigene Gehaeuse jenseits der
            # Nahgrenze der Schattenkamera.
            if z["treffer"]:
                fehler.append((typ, fid, p, t, z))
        self.assertEqual(fehler, [], f"Eigenschatten bei {len(fehler)} Geraeten")
        self.assertGreater(geprueft, 100)


if __name__ == "__main__":
    unittest.main()
