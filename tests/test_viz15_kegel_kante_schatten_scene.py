"""VIZ-15 Schritt 2 + VIZ-BEAM-OCCLUSION Teil 3 — in echter QWebEngine.

(A) Weicher Kegelrand (Fresnel): der Kegel laeuft zur Silhouette hin aus,
    blickwinkelabhaengig (laengs hineingeschaut bleibt er hell). Ab Stufe
    "Hoch"; auf "Niedrig" ist der Kegel-Shader Zeichen fuer Zeichen der
    bisherige (also auch pixelgleich).
(B) Volumen-Schatten im Strahl: ein Koerper, der nur TEILWEISE im Kegel
    steht, verdunkelt den sichtbaren Strahl dahinter. Nur auf "Maximal"
    (hoechstens 8 Kegel, je Kegel 4 Koerper; fixtures/strahl_optik.js).

Bildtests laufen nur mit GL-Kontext (sonst uebersprungen). Mit
``LIGHTOS_VIZ15_BILDER=<ordner>`` legen sie Vorher/Nachher-PNGs ab, mit
``LIGHTOS_VIZ15_MESSUNG=1`` misst ein Lauf die Bildzeit mit und ohne
Volumen-Schatten (Ausgabe ``VIZ15-MESSUNG``).
"""
import base64
import json
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest as _pytest_xplat15                      # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402  XPLAT-15

from test_viz92_gobo_feinschliff_scene import (        # noqa: E402
    _Basis, _FID, _geraet, _payload, _pump)


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    from PySide6.QtWidgets import QApplication as _QApp
    destroy_all_top_level_widgets(_QApp.instance())


# Kegel-Material einmal durch seinen Hook schicken (wie three beim Kompilieren).
_SHADER_JS = """
(function(){
  const L = window.__lightos, T = window.THREE, f = L.fixtures['%d'];
  const sh = { vertexShader: T.ShaderLib.basic.vertexShader,
               fragmentShader: T.ShaderLib.basic.fragmentShader, uniforms: {} };
  f.beam.material.onBeforeCompile.call(f.beam.material, sh);
  const alt = L.__patchLichtTon(L.__patchAusbrennShader(T.ShaderLib.basic.fragmentShader));
  return JSON.stringify({
    info: L.strahlOptikInfo(),
    vsGleich: sh.vertexShader === T.ShaderLib.basic.vertexShader,
    fsGleich: sh.fragmentShader === alt,
    kante: sh.fragmentShader.indexOf('lightosKantenFaktor()') >= 0,
    schatten: sh.fragmentShader.indexOf('lightosSchatten()') >= 0,
    uniforms: Object.keys(sh.uniforms).sort(),
    daempf: sh.fragmentShader.indexOf('gl_FragColor.a *= lightosAusbrennen') >= 0,
  });
})()
""" % _FID

# Bild von vorn; liefert mittlere Helligkeit (max-Kanal) an projizierten
# Weltpunkten je Gruppe und optional ein PNG.
_BILD_JS = """
(function(gruppen, png){
  const L = window.__lightos, T = window.THREE;
  const cv = document.getElementsByTagName('canvas')[0];
  const gl = cv && (cv.getContext('webgl2') || cv.getContext('webgl'));
  if (!gl || gl.isContextLost()) return JSON.stringify({gl: false});
  if (!window.__v15cam) {
    Object.defineProperty(window, 'innerWidth', { value: 480, configurable: true });
    Object.defineProperty(window, 'innerHeight', { value: 360, configurable: true });
    window.dispatchEvent(new Event('resize'));
    const cam = new T.PerspectiveCamera(50, 480 / 360, 0.1, 100);
    cam.position.set(0, 3.0, 9); cam.lookAt(0, 3.0, 0); cam.updateMatrixWorld(true);
    L.view.activeCam = cam; window.__v15cam = cam;
  }
  L.requestRender(); L.__renderTick();
  const W = gl.drawingBufferWidth, H = gl.drawingBufferHeight;
  const buf = new Uint8Array(W * H * 4);
  gl.readPixels(0, 0, W, H, gl.RGBA, gl.UNSIGNED_BYTE, buf);
  const cam = window.__v15cam, v = new T.Vector3();
  const hell = (x, y, z) => {
    v.set(x, y, z).project(cam);
    const px = Math.round((v.x * 0.5 + 0.5) * (W - 1));
    const py = Math.round((v.y * 0.5 + 0.5) * (H - 1));   // GL: Zeile 0 unten
    if (px < 0 || py < 0 || px >= W || py >= H) return 0;
    const i = (py * W + px) * 4;
    return Math.max(buf[i], buf[i + 1], buf[i + 2]);
  };
  const out = {gl: true};
  for (const name in gruppen) {
    let s = 0, n = 0;
    for (const p of gruppen[name]) { s += hell(p[0], p[1], p[2]); n += 1; }
    out[name] = s / Math.max(1, n);
  }
  if (png) {
    const c2 = document.createElement('canvas'); c2.width = W; c2.height = H;
    const ctx = c2.getContext('2d'), img = ctx.createImageData(W, H);
    for (let y = 0; y < H; y++) {
      img.data.set(buf.subarray((H - 1 - y) * W * 4, (H - y) * W * 4), y * W * 4);
    }
    ctx.putImageData(img, 0, 0);
    out.png = c2.toDataURL('image/png');
  }
  return JSON.stringify(out);
})(%s, %s)
"""


def _punkte(x0, x1, y0, y1, schritte=6):
    pts = []
    for i in range(schritte + 1):
        for j in range(schritte + 1):
            pts.append([x0 + (x1 - x0) * i / schritte, y0 + (y1 - y0) * j / schritte, 0.0])
    return pts


class _Bild(_Basis):
    def _bild(self, gruppen, name=None):
        ordner = os.environ.get("LIGHTOS_VIZ15_BILDER")
        m = json.loads(self._eval(_BILD_JS % (json.dumps(gruppen),
                                              "true" if (ordner and name) else "false")))
        if not m.get("gl"):
            raise unittest.SkipTest("kein GL-Kontext offscreen")
        if ordner and name and m.get("png"):
            os.makedirs(ordner, exist_ok=True)
            with open(os.path.join(ordner, name + ".png"), "wb") as fh:
                fh.write(base64.b64decode(m["png"].split(",", 1)[1]))
        m.pop("png", None)
        return m

    def _licht(self, gruppen, name=None, intensity=60):
        """Lichtanteil je Gruppe: Bild mit Strahl minus Bild ohne (Dimmer 0) —
        Raum und Koerper fallen heraus. Gedimmt, damit nichts auf 255 klemmt."""
        self._push(_payload(_FID, intensity=0))
        dunkel = self._bild(gruppen)
        self._push(_payload(_FID, intensity=intensity))
        hell = self._bild(gruppen, name)
        return {k: max(0.0, hell[k] - dunkel[k]) for k in gruppen}

    def _schalter(self, **o):
        self._eval("window.__lightos.__strahlOptikSchalter(%s)" % json.dumps(o))

    def _kegel_info(self):
        return json.loads(self._eval(
            "(function(){const f=window.__lightos.fixtures['%d'];"
            "const g=f.beam.geometry.parameters;"
            "return JSON.stringify({r:g.radius*f.beam.scale.x, h:g.height*f.beam.scale.y,"
            " sy:f.beam.scale.y});})()" % _FID))


class NiedrigTest(_Basis):
    TIER = "low"

    def test_niedrig_kegel_shader_unveraendert(self):
        """Stufe Niedrig: weder Rand noch Schatten — Vertex-Shader bit-gleich,
        Fragment-Shader genau der bisherige (Ausbrennschutz + Farbton)."""
        self._load_and_wait()
        r = json.loads(self._eval(_SHADER_JS))
        self.assertFalse(r["info"]["kante"], r)
        self.assertEqual(r["info"]["schattenMax"], 0, r)
        self.assertTrue(r["vsGleich"], "Vertex-Shader auf Niedrig veraendert")
        self.assertTrue(r["fsGleich"], "Fragment-Shader auf Niedrig veraendert")
        self.assertEqual(r["uniforms"], ["lightosAusbrennen"], r)


class HochTest(_Bild):
    TIER = "high"

    def test_hoch_rand_an_schatten_aus(self):
        self._load_and_wait()
        r = json.loads(self._eval(_SHADER_JS))
        self.assertTrue(r["info"]["kante"], r)
        self.assertEqual(r["info"]["schattenMax"], 0, "Volumen-Schatten nur auf Maximal")
        self.assertTrue(r["kante"] and not r["schatten"], r)
        self.assertFalse(r["vsGleich"], r)
        self.assertTrue(r["daempf"], "Ausbrennschutz muss bleiben (VIZ-91)")
        self.assertIn("lightosKante", r["uniforms"])

    def test_patch_ist_rein_und_vorsichtig(self):
        self._load_and_wait()
        r = json.loads(self._eval("""
        (function(){
          const L = window.__lightos, T = window.THREE;
          const vs = T.ShaderLib.basic.vertexShader, fs = T.ShaderLib.basic.fragmentShader;
          return JSON.stringify({
            nichts: L.__patchStrahlOptik(vs, fs, false, false),
            doppelt: L.__patchStrahlOptik(vs + '\\n#include <project_vertex>', fs, true, false),
            beide: !!L.__patchStrahlOptik(vs, fs, true, true),
          });
        })()"""))
        self.assertIsNone(r["nichts"])
        self.assertIsNone(r["doppelt"], "Anker doppelt -> unveraendert lassen")
        self.assertTrue(r["beide"])

    def test_bild_rand_weicher_als_mitte(self):
        """Seitenansicht eines senkrechten Strahls: am Rand (aussen 25 % der
        Breite) dunkler relativ zur Mitte als ohne Fresnel."""
        self._load_and_wait()
        self._push(_payload(_FID))
        _pump(0.3)
        k = self._kegel_info()
        y_mitte = 6.0 - 0.5 * k["h"]
        r_hier = 0.5 * k["r"]          # Radius in halber Kegellaenge
        gruppen = {
            "mitte": _punkte(-0.2 * r_hier, 0.2 * r_hier, y_mitte - 0.2, y_mitte + 0.2),
            "rand": _punkte(0.75 * r_hier, 0.92 * r_hier, y_mitte - 0.2, y_mitte + 0.2),
        }
        self._schalter(kante=False)
        ohne = self._licht(gruppen, "vorher_kante")
        self._schalter(kante=True)
        mit = self._licht(gruppen, "nachher_kante")
        print("VIZ15-KANTE", json.dumps({"ohne": ohne, "mit": mit, "kegel": k}))
        self.assertGreater(ohne["mitte"], 20, ohne)
        q_ohne = ohne["rand"] / max(1.0, ohne["mitte"])
        q_mit = mit["rand"] / max(1.0, mit["mitte"])
        self.assertLess(q_mit, q_ohne * 0.85,
                        f"Rand nicht weicher: ohne {q_ohne:.2f}, mit {q_mit:.2f}")
        self.assertGreater(mit["mitte"], 0.6 * ohne["mitte"], "Mitte darf hell bleiben")


class MaximalTest(_Bild):
    TIER = "max"

    def _platte(self, sid="platte1", x=1.75, y=3.0, breite=3.0):
        """Duenne Platte, die nur die +x-Haelfte des Kegels abdeckt."""
        self._bridge_obj.addStageObjectData.emit(json.dumps({
            "id": sid, "type": "platform",
            "position": {"x": x, "y": y, "z": 0.0},
            "size": {"x": breite, "y": 0.2, "z": 3.0},
        }))
        self._poll_until_true(f"!!window.__lightos.stageObjects['{sid}']")

    def test_maximal_rand_und_schatten_im_shader(self):
        self._load_and_wait()
        r = json.loads(self._eval(_SHADER_JS))
        self.assertTrue(r["kante"] and r["schatten"], r)
        self.assertEqual(r["info"]["schattenMax"], 8, r)
        self.assertEqual(r["info"]["koerperMax"], 4, r)
        for u in ("lightosSchattenAn", "lightosSchattenN", "lightosQuelle", "lightosKoerper"):
            self.assertIn(u, r["uniforms"])

    def test_koerper_im_kegel_wird_zugeteilt(self):
        self._load_and_wait()
        self._platte()
        self._push(_payload(_FID))
        _pump(0.3)
        # Zwei Bilder: das erste nach dem DMX-Schritt ordnet Kegel/Koerper erst ein.
        for _ in range(2):
            self._eval("(function(){const L=window.__lightos; L.requestRender(); L.__renderTick(); return 1;})()")
        r = json.loads(self._eval(
            "(function(){const L=window.__lightos,f=L.fixtures['%d'];"
            "const u=f.beam.material.userData.lightosSchatten;"
            "return JSON.stringify({n:u?u.n.value:-1, q:u?u.quelle.value.toArray():null,"
            " info:L.strahlOptikInfo()});})()" % _FID))
        self.assertEqual(r["n"], 1, r)
        self.assertEqual(r["info"]["zuteilung"]["kegel"], 1, r)
        self.assertGreater(r["q"][1], 4.0, "Quelle = Linse oben am Geraet")

    def test_bild_strahl_hinter_koerper_dunkler(self):
        """Platte deckt die +x-Haelfte des Kegels: darunter ist der Strahl
        mit Volumen-Schatten deutlich dunkler, die freie -x-Haelfte nicht."""
        self._load_and_wait()
        self._platte()
        self._push(_payload(_FID))
        _pump(0.3)
        k = self._kegel_info()
        self.assertLess(6.0 - k["h"], 2.0, f"Kegel endet an der Platte? {k}")
        r_bei_2 = k["r"] * (6.0 - 2.0) / k["h"]     # Radius 2 m ueber dem Boden
        gruppen = {
            "schattenseite": _punkte(0.35 * r_bei_2, 0.7 * r_bei_2, 1.2, 2.4),
            "freie_seite": _punkte(-0.7 * r_bei_2, -0.35 * r_bei_2, 1.2, 2.4),
        }
        self._schalter(schatten=False)
        ohne = self._licht(gruppen, "vorher_schatten")
        self._schalter(schatten=True)
        mit = self._licht(gruppen, "nachher_schatten")
        print("VIZ15-SCHATTEN", json.dumps({"ohne": ohne, "mit": mit, "kegel": k}))
        self.assertGreater(ohne["schattenseite"], 15, ohne)
        self.assertLess(mit["schattenseite"], 0.6 * ohne["schattenseite"],
                        f"Strahl hinter der Platte nicht dunkler: {ohne} -> {mit}")
        self.assertGreater(mit["freie_seite"], 0.85 * ohne["freie_seite"],
                           f"freie Seite darf nicht dunkler werden: {ohne} -> {mit}")

_MESS_FIDS = [_FID + 100 + i for i in range(8)]


@unittest.skipUnless(os.environ.get("LIGHTOS_VIZ15_MESSUNG"), "nur auf Wunsch")
class MessungTest(_Bild):
    """Bildzeit: 8 Moving Heads, 4 Platten im Kegel, 1280x720 — Volumen-
    Schatten + Rand aus/an im Wechsel (gleiche Seite, gleiche Szene)."""
    TIER = "max"
    GERAETE = [_geraet(fid, x=-3.5 + i, y=6) for i, fid in enumerate(_MESS_FIDS)]

    def test_messung_bildzeit(self):
        self._load_and_wait()
        for i in range(4):
            self._bridge_obj.addStageObjectData.emit(json.dumps({
                "id": f"m{i}", "type": "platform",
                "position": {"x": -3.0 + 2.0 * i + 0.6, "y": 2.5 + 0.3 * i, "z": 0.0},
                "size": {"x": 1.5, "y": 0.2, "z": 3.0}}))
            self._poll_until_true(f"!!window.__lightos.stageObjects['m{i}']")
        self._push(*[_payload(fid, intensity=120) for fid in _MESS_FIDS])
        _pump(0.3)
        mess = """
        (function(an){
          const L = window.__lightos, T = window.THREE;
          const cv = document.getElementsByTagName('canvas')[0];
          const gl = cv && (cv.getContext('webgl2') || cv.getContext('webgl'));
          if (!window.__v15mess) {
            Object.defineProperty(window, 'innerWidth', { value: 1280, configurable: true });
            Object.defineProperty(window, 'innerHeight', { value: 720, configurable: true });
            window.dispatchEvent(new Event('resize'));
            const cam = new T.PerspectiveCamera(50, 1280 / 720, 0.1, 100);
            cam.position.set(0, 3.0, 9); cam.lookAt(0, 3.0, 0); cam.updateMatrixWorld(true);
            L.view.activeCam = cam; window.__v15mess = cam;
          }
          L.__strahlOptikSchalter({schatten: an, kante: an});
          const px = new Uint8Array(4);
          for (let i = 0; i < 5; i++) { L.requestRender(); L.__renderTick(); }
          if (gl) gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, px);
          const t0 = performance.now();
          for (let i = 0; i < 60; i++) {
            L.requestRender(); L.__renderTick();
            if (gl) gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, px);
          }
          return JSON.stringify({ms: (performance.now() - t0) / 60,
                                 z: L.strahlOptikInfo().zuteilung});
        })(%s)"""
        ergebnis = {"aus": [], "an": []}
        for _runde in range(3):
            for an in (False, True):
                ergebnis["an" if an else "aus"].append(
                    json.loads(self._eval(mess % ("true" if an else "false"))))
        print("VIZ15-MESSUNG", json.dumps(ergebnis))
        self.assertGreaterEqual(ergebnis["an"][-1]["z"]["kegel"], 4, ergebnis)


if __name__ == "__main__":
    unittest.main()
