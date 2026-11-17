"""VIZ-93: DMX-Farben im 3D satt — sRGB statt linear, farbtonerhaltendes Tone-Mapping.

Befund (test_viz93_co9_farbe_payload): Abendrot 255/60/0 wirkte im 3D-Strahl
hellbeige, der Payload stimmt. Ursache in der Szene, fuer ALLE Geraete:

1. ``updateFixture`` nahm r/255 ungewandelt als LINEARE Farbe; die
   sRGB-Ausgabe (renderer.js) hob G 60 damit auf ~133 (Rot -> Orange).
2. ACES-Tone-Mapping mischt die Kanaele (reines Rot -> ~255/40/25, Abendrot
   voll ~245/170/46).

Jetzt (fixtures/lichtfarbe.js): die DMX-Farbe wird EINMAL sRGB -> linear
gewandelt, bevor sie in Material-/Lichtfarben geht (Kegel, Bodenfleck,
SpotLight/Pool-Licht, Linse/Lampe/Pixel, Laser), und Lichtmaterialien
bekommen ACES nur auf den hellsten Kanal (alle Kanaele gleich skaliert) —
Grau/Weiss bit-gleich wie vorher, Farben behalten ihren Ton. Helligkeits-
Masse (Sichtbarkeit, Ausbrenn-Last, Pool-Rangfolge) bleiben im sRGB-Mass.

Kerntests ohne WebGL (Szenenzustand, Shader-Quelltext). Mit GL-Kontext misst
ein Bildtest den Farbton im echten Bild. Mit ``LIGHTOS_VIZ93_BILDER=<ordner>``
(und optional ``LIGHTOS_VIZ93_PRAEFIX``) legt er je Farbe ein PNG ab
(Vorher/Nachher-Bilder fuer die Abnahme).
"""
import base64
import json
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest as _pytest_xplat15                      # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402  XPLAT-15

from test_viz92_gobo_feinschliff_scene import (        # noqa: E402
    _Basis, _geraet, _payload)


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    from PySide6.QtWidgets import QApplication as _QApp
    destroy_all_top_level_widgets(_QApp.instance())


_FID = 930301


def _lin(v):
    c = v / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


FARBEN = {
    "abendrot": (255, 60, 0),
    "rot": (255, 0, 0),
    "gruen": (0, 255, 0),
    "blau": (0, 0, 255),
    "amber": (255, 191, 0),       # color_utils: "amber" #ffbf00
    "uv_lila": (160, 64, 255),    # color_utils: "violett" #a040ff
    "weiss": (255, 255, 255),
}


def _farbe(r, g, b, intensity=255):
    return _payload(_FID, color_r=r, color_g=g, color_b=b, intensity=intensity)


_ZUSTAND_JS = """
(function(){
  const L = window.__lightos, f = L.fixtures['%d'];
  const c = o => o ? [o.r, o.g, o.b] : null;
  return JSON.stringify({
    kegel: c(f.beam.material.color), fleck: c(f.floorSpot.material.color),
    spot: c(f.spot.color), linse: c(f.lens && f.lens.material.emissive),
    sichtbar: f.beam.visible, spotInt: f.spot.intensity,
    fleckHell: f._fleckHell, last: L.ausbrennInfo().kegelLast,
  });
})()
""" % _FID


class Viz93FarbraumTest(_Basis):
    GERAETE = [_geraet(_FID)]

    def _zustand(self, r, g, b, intensity=255):
        self._push(_farbe(r, g, b, intensity))
        return json.loads(self._eval(_ZUSTAND_JS))

    def test_dmx_farbe_wird_als_srgb_gelesen(self):
        """Abendrot: G 60 kommt linear als ~0,045 an (vorher 60/255 = 0,235)."""
        self._load_and_wait()
        z = self._zustand(255, 60, 0)
        soll = [_lin(255), _lin(60), _lin(0)]
        for feld in ("kegel", "fleck", "spot", "linse"):
            for ist, s in zip(z[feld], soll):
                self.assertAlmostEqual(ist, s, places=4, msg=(feld, z))
        # Weiss und volle Kanaele bleiben 1 — die Wandlung dunkelt nichts ab.
        z = self._zustand(255, 255, 255)
        self.assertEqual(z["kegel"], [1, 1, 1], z)

    def test_kopf_farben_der_mehrkopf_geraete_auch(self):
        """PAR-Bar: Kopf-Farben laufen durch dieselbe Wandlung."""
        self._load_and_wait()
        r = json.loads(self._eval("""
        (function(){
          const L = window.__lightos, T = window.THREE;
          const f = { isParBar: true, lastHeads: [{r: 255, g: 60, b: 0}],
                      parHeads: [{ lens: new T.Mesh(new T.BoxGeometry(), new T.MeshStandardMaterial()),
                                   beam: new T.Mesh(new T.BoxGeometry(), new T.MeshBasicMaterial()) }],
                      icon: null };
          L.__updateParBarDmx(f, { r: 255, g: 60, b: 0, intNorm: 1 });
          const e = f.parHeads[0].lens.material.emissive, k = f.parHeads[0].beam.material.color;
          return JSON.stringify({ linse: [e.r, e.g, e.b], kegel: [k.r, k.g, k.b] });
        })()"""))
        for feld in ("linse", "kegel"):
            self.assertAlmostEqual(r[feld][1], _lin(60), places=4, msg=r)

    def test_helligkeits_masse_bleiben_im_srgb_mass(self):
        """Farbe und Dimmer getrennt: Sichtbarkeit, Ausbrenn-Last und Spot
        haengen weiter am hellsten sRGB-Kanal — Grau 128 zaehlt wie vorher."""
        self._load_and_wait()
        z = self._zustand(128, 128, 128)
        self.assertAlmostEqual(z["fleckHell"], 128 / 255, places=6, msg=z)
        self.assertAlmostEqual(z["last"], 128 / 255, places=4, msg=z)
        self.assertTrue(z["sichtbar"], z)
        hell = self._eval(
            "window.__lightos.__strahlHelligkeit(window.__lightos.fixtures['%d'])" % _FID)
        self.assertAlmostEqual(hell, z["spotInt"] * 128 / 255, places=4)
        # Ganz dunkle Farbe: Schwelle wie vorher (lum 3/255 > 0,01 -> sichtbar).
        z = self._zustand(3, 3, 3)
        self.assertTrue(z["sichtbar"], z)
        self.assertGreater(z["spotInt"], 0, z)

    def test_lichtmaterialien_farbtonerhaltend_getont(self):
        """Kegel und Fleck: ACES nur auf den hellsten Kanal (Ausbrennschutz
        bleibt). Beleuchtete Materialien (Koerper UND Linse) behalten ihren
        Prototyp-Hook (Gobo-Projektion, VIZ-96) und das normale ACES — die
        Linse bekommt nur die sRGB-Wandlung."""
        self._load_and_wait()
        r = json.loads(self._eval("""
        (function(){
          const L = window.__lightos, T = window.THREE, f = L.fixtures['%d'];
          const probe = (mat, lib) => {
            const sh = { fragmentShader: T.ShaderLib[lib].fragmentShader, uniforms: {} };
            mat.onBeforeCompile(sh);
            return { neu: sh.fragmentShader.indexOf('lightosHell') >= 0,
                     alt: sh.fragmentShader.indexOf('#include <tonemapping_fragment>') >= 0,
                     daempf: sh.fragmentShader.indexOf('gl_FragColor.a *= lightosAusbrennen') };
          };
          let koerper = null;
          f.group.traverse(o => { if (!koerper && o.isMesh && o.material && o.material.isMeshStandardMaterial
                                      && o !== f.lens) koerper = o.material; });
          return JSON.stringify({ kegel: probe(f.beam.material, 'basic'),
                                  fleck: probe(f.floorSpot.material, 'basic'),
                                  linse: probe(f.lens.material, 'physical'),
                                  koerper: probe(koerper, 'physical'),
                                  doppelt: L.__patchLichtTon('#include <tonemapping_fragment>\\n#include <tonemapping_fragment>') });
        })()""" % _FID))
        for feld in ("kegel", "fleck"):
            self.assertTrue(r[feld]["neu"] and not r[feld]["alt"], (feld, r))
        self.assertTrue(r["linse"]["alt"] and not r["linse"]["neu"], r)
        # Ausbrennschutz bleibt drin (VIZ-91).
        self.assertGreaterEqual(r["kegel"]["daempf"], 0, r)
        self.assertGreaterEqual(r["fleck"]["daempf"], 0, r)
        self.assertTrue(r["koerper"]["alt"] and not r["koerper"]["neu"], r)
        self.assertIsNone(r["doppelt"])


# ── Echtes Bild (nur mit GL-Kontext) ─────────────────────────────────────────
_BILD_JS = """
(function(dunkel, png){
  const L = window.__lightos, T = window.THREE;
  const cv = document.getElementsByTagName('canvas')[0];
  const gl = cv && (cv.getContext('webgl2') || cv.getContext('webgl'));
  if (!gl || gl.isContextLost()) return JSON.stringify({gl: false});
  if (!window.__v93cam) {
    Object.defineProperty(window, 'innerWidth', { value: 480, configurable: true });
    Object.defineProperty(window, 'innerHeight', { value: 360, configurable: true });
    window.dispatchEvent(new Event('resize'));
    const cam = new T.PerspectiveCamera(50, 480 / 360, 0.1, 100);
    cam.position.set(0, 3.2, 9); cam.lookAt(0, 2.8, 0); cam.updateMatrixWorld(true);
    L.view.activeCam = cam; window.__v93cam = cam;
  }
  L.requestRender(); L.__renderTick();
  const W = gl.drawingBufferWidth, H = gl.drawingBufferHeight;
  const buf = new Uint8Array(W * H * 4);
  gl.readPixels(0, 0, W, H, gl.RGBA, gl.UNSIGNED_BYTE, buf);
  if (dunkel) { window.__v93dunkel = buf; return JSON.stringify({gl: true}); }
  const d = window.__v93dunkel;
  // Lichtanteil = hell - dunkel; nur deutlich beleuchtete Bildpunkte.
  let sr = 0, sg = 0, sb = 0, n = 0;
  for (let i = 0; i < buf.length; i += 4) {
    const r = buf[i] - d[i], g = buf[i + 1] - d[i + 1], b = buf[i + 2] - d[i + 2];
    if (Math.max(r, g, b) < 30) continue;
    sr += Math.max(0, r); sg += Math.max(0, g); sb += Math.max(0, b); n += 1;
  }
  const out = {gl: true, n: n, r: sr / Math.max(1, n), g: sg / Math.max(1, n), b: sb / Math.max(1, n)};
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


class Viz93BildTest(_Basis):
    """Farbton im echten Bild (uebersprungen ohne GL-Kontext)."""
    GERAETE = [_geraet(_FID, y=5.5)]

    def _bild(self, r, g, b, name=None):
        self._push(_farbe(r, g, b, intensity=0))
        d = json.loads(self._eval(_BILD_JS % ("true", "false")))
        if not d.get("gl"):
            raise unittest.SkipTest("kein GL-Kontext offscreen")
        self._push(_farbe(r, g, b))
        ordner = os.environ.get("LIGHTOS_VIZ93_BILDER")
        m = json.loads(self._eval(_BILD_JS % ("false", "true" if (ordner and name) else "false")))
        if ordner and name and m.get("png"):
            os.makedirs(ordner, exist_ok=True)
            praefix = os.environ.get("LIGHTOS_VIZ93_PRAEFIX", "neu")
            pfad = os.path.join(ordner, f"{praefix}_{name}.png")
            with open(pfad, "wb") as fh:
                fh.write(base64.b64decode(m.pop("png").split(",", 1)[1]))
        m.pop("png", None)
        return m

    def test_bild_farbton_bleibt_satt(self):
        self._load_and_wait()
        werte = {name: self._bild(*rgb, name=name) for name, rgb in FARBEN.items()}
        print("VIZ93-BILD", json.dumps(werte))
        ab, rot, weiss = werte["abendrot"], werte["rot"], werte["weiss"]
        for w in werte.values():
            self.assertGreater(w["n"], 200, werte)
        # Abendrot: G/R wie im DMX-Wert (60/255 = 0,24), nicht beige (~0,7).
        self.assertLess(ab["g"] / ab["r"], 0.36, ab)
        self.assertLess(ab["b"] / ab["r"], 0.08, ab)
        # Reines Rot bleibt rot (vorher ~255/40/25 -> rosa Stich).
        self.assertLess(max(rot["g"], rot["b"]) / rot["r"], 0.08, rot)
        # Weiss bleibt neutral.
        self.assertLess(abs(weiss["r"] - weiss["b"]) / weiss["r"], 0.1, weiss)
