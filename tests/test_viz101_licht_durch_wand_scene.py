"""VIZ-101: Licht geht nicht mehr durch die Rueckwand, keine Moire-Streifen.

Befund (Live-Gobo-Demo 10.10.2026), auf ``main`` nachgemessen (31.10.2026):

1. Trifft die Strahlmitte eine Wand (Buehnenobjekt ``wall``), lag der
   Bodenfleck WAAGERECHT in Trefferhoehe — zur Haelfte hinter der Wand, von
   hinten/oben als heller Halbkreis zu sehen. Ein Gobo-Kegel (seit VIZ-102 bis
   zum fernen Rand seines Musters verlaengert) schoss durch die Wand; hinter
   ihr lagen Kegelstuecke in der Luft.
2. Die Wand hat ``side: DoubleSide``; three zeichnete deshalb auch ihre
   beleuchtete Vorderseite in die Shadow-Map — Shadow-Acne, waagerechte
   Moire-Streifen im Lichtfleck (offenes Gobo wie mit Gobo).
3. Das Kegelende steht senkrecht zur Achse: bei schraegem Einfall blieb der
   obere Rand als runder Bogen VOR der Wand stehen, der untere ragte hindurch.

Jetzt (``fixtures/builders.js#applyFloorAim``): an einer senkrechten Flaeche
liegt der Fleck in der Wandebene (``floor_pool.js#fleckAufFlaeche``), der
Kegel reicht bis zu ihrem fernen Rand und wird an der Wandebene beschnitten
(``gobo_textures.js#kegelWandAbgleichen``, dieselben fuenf Clipping-Ebenen
wie VIZ-102 — kein Programmwechsel); die Wand wirft ihren Schatten mit der
Rueckseite (``shadowSide: BackSide``).

Review-Nachtrag: trifft die Strahlmitte den BODEN knapp vor der Wand, ragten
Fleck und Kegel ebenso hinter sie. Jetzt sucht ``_wandImFleck`` im
Fussabdruck nach einer Wand; Fleck (``fleckWandAbgleichen``) und Kegel enden
an ihrer Ebene. Beschnitten wird nur, wenn die Wand den Kegel auch in der
Hoehe ganz abdeckt (``_wandDeckt``) — ueber eine niedrige Wand geht das Licht
hinweg.

Bildpruefung ueber den echten GL-Kontext der Seite (offscreen, readPixels;
ohne Kontext wird uebersprungen), Geometrie ohne GL.
"""
import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest as _pytest_xplat15                      # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402  XPLAT-15

from test_viz92_gobo_feinschliff_scene import _Basis, _geraet, _payload  # noqa: E402


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    from PySide6.QtWidgets import QApplication as _QApp
    destroy_all_top_level_widgets(_QApp.instance())


_FID = 1010001
_RING = 45          # Gobo 1 (Ring-Spalte)
# Moving Head 4 m hoch, Tilt 192 = 45 Grad nach vorn (-z): die Strahlmitte
# trifft die Wand (Vorderseite z = -2,4) in rund 1,6 bis 2 m Hoehe.
_TILT = 192
_WAND_Z = -2.5
_WAND_VORN = _WAND_Z + 0.1

_GEOMETRIE_JS = """
(function(){
  const L = window.__lightos, T = window.THREE, f = L.fixtures['%d'];
  const s = f.floorSpot; s.updateMatrixWorld(true);
  const r = (s.geometry.parameters && s.geometry.parameters.radius) || 1;
  const rand = [];
  for (let k = 0; k < 16; k++) {
    const th = k * Math.PI / 8;
    rand.push(new T.Vector3(r * Math.cos(th), r * Math.sin(th), 0).applyMatrix4(s.matrixWorld).z);
  }
  const n = new T.Vector3(0, 0, 1).transformDirection(s.matrixWorld);
  // Kegel: Endpunkte der Mantellinien und die Clipping-Ebenen
  const b = f.beam, p = b.geometry.parameters; b.updateWorldMatrix(true, false);
  const kegelEnde = [];
  for (let k = 0; k < 16; k++) {
    const th = k * Math.PI / 8;
    const e = b.localToWorld(new T.Vector3(p.radius * Math.sin(th), -p.height / 2,
                                           p.radius * Math.cos(th)));
    kegelEnde.push([e.y, e.z]);
  }
  const eb = b.material.clippingPlanes.map(e => [e.normal.x, e.normal.y, e.normal.z, e.constant]);
  return JSON.stringify({ sichtbar: s.visible, mitte: [s.position.x, s.position.y, s.position.z],
    rand: rand, normale: [n.x, n.y, n.z], kegelEnde: kegelEnde, ebenen: eb,
    geschnitten: !!f._kegelSchnitt, rotX: s.rotation.x, auto: s.matrixAutoUpdate });
})()
"""

_BILD_JS = """
(function(){
  const L = window.__lightos, T = window.THREE;
  const cv = document.getElementsByTagName('canvas')[0];
  const gl = cv && (cv.getContext('webgl2') || cv.getContext('webgl'));
  if (!gl || gl.isContextLost()) return JSON.stringify({gl: false});
  Object.defineProperty(window, 'innerWidth', { value: 640, configurable: true });
  Object.defineProperty(window, 'innerHeight', { value: 480, configurable: true });
  window.dispatchEvent(new Event('resize'));
  const wand = L.stageObjects['wand1'].mesh;
  const cam = new T.PerspectiveCamera(50, 640 / 480, 0.1, 100);
  const k = %s;
  cam.position.set(k[0], k[1], k[2]); cam.lookAt(k[3], k[4], k[5]);
  cam.updateMatrixWorld(true);
  L.view.activeCam = cam;
  const W = gl.drawingBufferWidth, H = gl.drawingBufferHeight;
  const rc = new T.Raycaster();
  // Helligkeit an Weltpunkten; null = ausserhalb des Bildes oder von der
  // Wand verdeckt (gemessen wird nur, was man HINTER der Wand wirklich sieht).
  window.__v101 = function(punkte) {
    L.requestRender(); L.__renderTick();
    const buf = new Uint8Array(W * H * 4);
    gl.readPixels(0, 0, W, H, gl.RGBA, gl.UNSIGNED_BYTE, buf);
    const out = [];
    let summe = 0;
    for (let i = 0; i < buf.length; i += 4) summe += buf[i] + buf[i + 1] + buf[i + 2];
    for (const q of punkte) {
      const v = new T.Vector3(q[0], q[1], q[2]);
      const d = v.clone().sub(cam.position), weit = d.length();
      rc.set(cam.position, d.normalize()); rc.far = weit - 0.01;
      const n = v.clone().project(cam);
      const x = Math.round((n.x * 0.5 + 0.5) * W), y = Math.round((n.y * 0.5 + 0.5) * H);
      if (x < 1 || y < 1 || x >= W - 1 || y >= H - 1 || rc.intersectObject(wand, true).length) {
        out.push(null); continue;
      }
      const i = (y * W + x) * 4;
      out.push((buf[i] + buf[i + 1] + buf[i + 2]) / 3);
    }
    return JSON.stringify({ werte: out, mittel: summe / (W * H * 3), verloren: gl.isContextLost() });
  };
  return JSON.stringify({ gl: true, W: W, H: H });
})()
"""


def _hinter_der_wand():
    """Punkte hinter der Wand: Boden und Hoehe des alten waagerechten Flecks."""
    punkte = []
    for z in (-2.8, -3.2, -3.6, -4.0, -4.5, -5.0, -6.0):
        for x in (-2.0, -1.0, 0.0, 1.0, 2.0):
            punkte.append([x, 0.01, z])
            punkte.append([x, 1.6, z])
            punkte.append([x, 2.0, z])
    return punkte


def _wandlinie():
    """Senkrechte Linie mitten durch den Lichtfleck, knapp vor der Wand."""
    return [[0.0, 0.9 + 1.8 * k / 240, _WAND_VORN + 0.005] for k in range(241)]


def _zacken(werte, schwelle=3.0):
    """Moire-Mass: Zahl der Richtungswechsel mit mindestens `schwelle`
    Helligkeitsstufen Hub. Ein glatter Lichtfleck hat einen Gipfel (1-2
    Wechsel), Shadow-Acne Dutzende."""
    w = [v for v in werte if v is not None]
    if not w:
        return 0
    zahl, richtung, extrem = 0, 0, w[0]
    for v in w[1:]:
        if richtung == 0:
            if abs(v - extrem) >= schwelle:
                richtung, extrem = (1 if v > extrem else -1), v
        elif richtung > 0:
            if v > extrem:
                extrem = v
            elif v <= extrem - schwelle:
                zahl, richtung, extrem = zahl + 1, -1, v
        else:
            if v < extrem:
                extrem = v
            elif v >= extrem + schwelle:
                zahl, richtung, extrem = zahl + 1, 1, v
    return zahl


class _WandBasis(_Basis):
    __test__ = False
    GERAETE = [_geraet(_FID, x=0, y=4, z=0)]

    def _wand(self, typ="wall", groesse=(10, 6, 0.2)):
        self._bridge_obj.addStageObjectData.emit(json.dumps({
            "id": "wand1", "type": typ,
            "position": {"x": 0, "y": groesse[1] / 2, "z": _WAND_Z},
            "size": {"x": groesse[0], "y": groesse[1], "z": groesse[2]}}))
        self._poll_until_true("!!window.__lightos.stageObjects['wand1']")

    def _aufbau(self, tilt=_TILT, **attrs):
        self._load_and_wait()
        self._wand()
        self._push(_payload(_FID, tilt=tilt, **attrs))
        for _ in range(4):
            self._bild()

    def _geometrie(self):
        return self._json(_GEOMETRIE_JS % _FID)

    def _sicht(self, settings, tilt=_TILT, **attrs):
        js = ("(function(){const S=window.__lightos.settings; %s return 1;})()"
              % "".join(f"S.{k}={'true' if v else 'false'};" for k, v in settings.items()))
        self._eval(js)
        self._push(_payload(_FID, tilt=tilt, **attrs))
        self._bild()
        self._bild()

    def _kamera(self, kamera):
        a = self._json(_BILD_JS % json.dumps(kamera))
        if not a.get("gl"):
            self.skipTest("kein GL-Kontext (offscreen) — Bildpruefung nur mit Grafikkarte")
        if a["W"] < 320 or a["H"] < 240:
            self.skipTest(f"Zeichenflaeche zu klein: {a}")

    def _messen(self, punkte):
        z = self._json("window.__v101(%s)" % json.dumps(punkte))
        if z["verloren"]:
            self.skipTest("GL-Kontext waehrend der Messung verloren")
        if z["mittel"] < 1:
            self.skipTest("leeres Bild (kein Rendern offscreen)")
        return z["werte"]

    # ── Geometrie (ohne GL) ───────────────────────────────────────────────

    def _pruefe_geometrie(self, gobo):
        g = self._geometrie()
        # Fleck liegt IN der Wandebene, nicht waagerecht durch sie hindurch.
        self.assertGreater(abs(g["normale"][2]), 0.99, g)
        self.assertAlmostEqual(g["mitte"][2], _WAND_VORN + 0.01, delta=0.02)
        self.assertGreaterEqual(min(g["rand"]), _WAND_VORN - 0.005,
                                f"Fleck ragt hinter die Wand: {g['rand']}")
        # Kegel: jede Mantellinie erreicht die Wandebene oder den Boden davor
        # (kein runder Bogen in der Luft vor der Wand) ...
        luft = [e for e in g["kegelEnde"] if e[0] > 0.02 and e[1] > _WAND_VORN + 0.02]
        self.assertEqual(luft, [], f"Kegelrand endet vor der Wand (gobo={gobo})")
        # ... und hinter der Ebene wird nichts gezeichnet.
        self.assertTrue(g["geschnitten"], g)
        for e in g["ebenen"]:
            self.assertGreater(e[2], 0.99, e)
            self.assertAlmostEqual(-e[3] / e[2], _WAND_VORN, delta=0.02)

    def test_offen_fleck_und_kegel_an_der_wand(self):
        self._aufbau()
        self._pruefe_geometrie(False)

    def test_gobo_fleck_und_kegel_an_der_wand(self):
        self._aufbau(gobo_wheel=_RING)
        self._pruefe_geometrie(True)

    def test_zurueck_auf_den_boden_liegt_der_fleck_wieder_flach(self):
        self._aufbau()
        self._push(_payload(_FID, tilt=64))           # 45 Grad von der Wand weg
        for _ in range(3):
            self._bild()
        g = self._geometrie()
        self.assertAlmostEqual(g["rotX"], -3.14159265 / 2, places=4)
        self.assertGreater(abs(g["normale"][1]), 0.99, g)
        self.assertFalse(g["geschnitten"], "Kegel bleibt an der alten Wandebene beschnitten")

    def test_schmale_box_beschneidet_den_kegel_nicht(self):
        # Eine Box schmaler als der Kegel: das Licht geht seitlich weiter.
        self._load_and_wait()
        self._wand("speaker", (0.6, 4.5, 0.6))
        self._push(_payload(_FID, tilt=_TILT))
        for _ in range(3):
            self._bild()
        self.assertFalse(self._geometrie()["geschnitten"])

    def test_niedrige_wand_beschneidet_den_kegel_nicht(self):
        # 3 m hoch: die Mitte trifft die Wand (y ~ 2), die oberen Randstrahlen
        # des weiten Kegels (5,2 m Durchmesser) gehen in ~3,6 m ueber sie
        # hinweg — die unendliche Wandebene darf dort nicht schneiden.
        self._load_and_wait()
        self._wand(groesse=(10, 3, 0.2))
        self._push(_payload(_FID, tilt=_TILT))
        for _ in range(3):
            self._bild()
        g = self._geometrie()
        self.assertGreater(abs(g["normale"][2]), 0.99, "Mitte trifft die Wand nicht")
        self.assertFalse(g["geschnitten"])

    def test_wand_niedriger_als_kegelbreit_wird_beschnitten(self):
        # 10 m breit, 4,5 m hoch: niedriger als der Kegel breit ist, deckt ihn
        # aber ganz ab. Vorher galt sie als „schmal“ (mittlere Kante 4,5 m
        # < 5,2 m Kegel) und der Gobo-Kegel schoss ungeschnitten hindurch.
        self._load_and_wait()
        self._wand(groesse=(10, 4.5, 0.2))
        self._push(_payload(_FID, tilt=_TILT, gobo_wheel=_RING))
        for _ in range(3):
            self._bild()
        self.assertTrue(self._geometrie()["geschnitten"])

    # ── Bild (mit GL) ────────────────────────────────────────────────────

    def _hinten_dunkel(self, settings, tilt=_TILT, **attrs):
        self._aufbau(tilt=tilt, **attrs)
        self._kamera([0, 10, -11, 0, 0, -4])
        punkte = _hinter_der_wand()
        self._sicht(settings, tilt=tilt, **attrs)
        an = self._messen(punkte)
        self._sicht(settings, tilt=tilt, intensity=0, **attrs)
        aus = self._messen(punkte)
        paare = [(p, a - b) for p, a, b in zip(punkte, an, aus) if a is not None and b is not None]
        self.assertGreater(len(paare), 40, "zu wenige sichtbare Punkte hinter der Wand")
        hell = [(p, round(d, 1)) for p, d in paare if d > 6]
        self.assertEqual(hell, [], f"Licht hinter der Wand ({attrs}, {settings})")

    def test_bild_offen_kein_fleck_hinter_der_wand(self):
        self._hinten_dunkel({"showCones": True, "showFloorSpots": True})

    def test_bild_gobo_kein_kegel_hinter_der_wand(self):
        self._hinten_dunkel({"showCones": True, "showFloorSpots": True}, gobo_wheel=_RING)

    # Review: die Strahlmitte trifft den BODEN knapp vor der Wand (Tilt 150:
    # 1,2 m davor, Tilt 160: 0,6 m davor). Fleck (Rand bis z = -3,7, mit Gobo
    # -5,5) und Kegel ragten hinter die Wand — auf main bis +127 Stufen.
    def test_bild_boden_vor_der_wand_offen(self):
        self._hinten_dunkel({"showCones": True, "showFloorSpots": True}, tilt=150)

    def test_bild_boden_knapp_vor_der_wand_offen(self):
        self._hinten_dunkel({"showCones": True, "showFloorSpots": True}, tilt=160)

    def test_bild_boden_knapp_vor_der_wand_gobo(self):
        self._hinten_dunkel({"showCones": True, "showFloorSpots": True}, tilt=160,
                            gobo_wheel=_RING)

    def test_bild_keine_moire_streifen_auf_der_wand(self):
        # Offenes Gobo, nur das echte Licht (ohne Kegel und Fleck): dort sass
        # die Acne. Auf main (DoubleSide-Schatten) 40-55 Zacken, jetzt 0.
        self._aufbau()
        self._kamera([0, 2.5, 7, 0, 2, _WAND_VORN])
        self._sicht({"showCones": False, "showFloorSpots": False})
        werte = self._messen(_wandlinie())
        self.assertGreater(max(werte) - min(werte), 12, "kein Lichtfleck auf der Wand")
        self.assertLessEqual(_zacken(werte), 4, f"Moire-Streifen: {[round(v) for v in werte]}")


class Viz101WandHochTest(_WandBasis):
    __test__ = True
    TIER = "high"


class Viz101WandNiedrigTest(_WandBasis):
    __test__ = True
    TIER = "low"
