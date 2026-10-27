"""VIZ-91: grosse Shows brennen im 3D nicht mehr weiss aus.

Befund (Projektinhaber 08.10.2026): bei 40-80 leuchtenden Geraeten addierten
sich die Kegel (MeshBasicMaterial, AdditiveBlending, Deckkraft 0,85 je Kegel)
und die Bodenflecken zu reinem Weiss — Buehne und Gobo-Muster waren kaum noch
zu erkennen. Das ACES-Tone-Mapping hilft dabei nicht, three wendet es je
Fragment VOR dem Blenden an.

Jetzt (fixtures/ausbrennen.js): ein gemeinsamer Daempfungsfaktor fuer alle
Kegel bzw. Flecken, als Uniform im Shader (gl_FragColor.a *= Faktor). Er folgt
der Licht-Last der Szene: bis zur Schwelle 1 (kleine Shows unveraendert),
darueber (Schwelle/Last)^p mit Untergrenze — Kegel p = 1 (Schwelle 8,
Untergrenze 0,08: ein festes Budget von ~8 vollen Kegeln), Flecken p = 0,75
(Schwelle 10, Untergrenze 0,25). Gezaehlt wird nur, was zu sehen ist
(beamsOff, Fleck-Schalter), Prisma-Nebenstrahlen je als eigener Kegel.

Geprueft ueber die ECHTE Seite mit Produktiv-Push (60 Moving Heads):

* 1-3 leuchtende Geraete -> Faktor 1, effektive Deckkraft wie bisher;
* 60 leuchtende Geraete -> Summe der effektiven Kegel-Deckkraft deutlich unter
  der alten (60 * 0,85 = 51), Faktor nicht unter der Untergrenze;
* die Last wird inkrementell gefuehrt (wieder abdimmen, Geraete entfernen);
* material.opacity bleibt unberuehrt (Sichtbarkeits-Schwellen lesen sie);
* Kegel- und Fleck-Materialien binden wirklich die gemeinsame Uniform, und
  der Patch greift im MeshBasic-Shader des mitgelieferten three-Stands —
  auch WIRKSAM: im aufgeloesten Shader ueberschreibt danach nichts mehr das
  Alpha mit einem Wert, der nicht aus gl_FragColor selbst stammt.

Die Kerntests brauchen kein WebGL (Szenenzustand und Shader-Quelltext). Hat
die Seite offscreen einen echten GL-Kontext, misst ein Zusatztest das BILD:
Anteil reinweisser Bildpunkte mit und ohne Schutz (Seam ``__ausbrennSchutz``),
Blick von vorn auf das Raster. Ohne GL-Kontext wird er uebersprungen.
"""
import json
import math
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest as _pytest_xplat15                      # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402  XPLAT-15
from PySide6.QtCore import Slot                       # noqa: E402

import test_viz92_gobo_feinschliff_scene as _v92      # noqa: E402
from test_viz92_gobo_feinschliff_scene import (        # noqa: E402
    _Basis, _geraet, _payload)


class _PollBridge(_v92._MockBridge):
    """Wie die viz92-Attrappe, aber der Test kann Poll-Zustaende (beamsOff)
    vorgeben (wie test_viz79_laser_strahlen_scene)."""

    @Slot(result=str)
    def pollControl(self):
        return getattr(self, "_poll", "{}")


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    from PySide6.QtWidgets import QApplication as _QApp
    destroy_all_top_level_widgets(_QApp.instance())


_ANZAHL = 60
_FIDS = [930001 + i for i in range(_ANZAHL)]
# 10 x 6 Raster ueber die Buehne, alle senkrecht nach unten.
_GERAETE = [_geraet(fid, x=-9 + 2 * (i % 10), z=-5 + 2 * (i // 10))
            for i, fid in enumerate(_FIDS)]

_ZUSTAND_JS = """
(function(){
  const L = window.__lightos, info = L.ausbrennInfo();
  let roh = 0, eff = 0, fleckRoh = 0, fleckEff = 0, leuchtend = 0;
  for (const fid of %s) {
    const f = L.fixtures[String(fid)];
    if (!f) continue;
    const k = f.beam.material.opacity, b = f.floorSpot.material.opacity;
    if (k > 0) leuchtend += 1;
    roh += k; eff += k * info.kegelFaktor;
    fleckRoh += b; fleckEff += b * info.fleckFaktor;
  }
  return JSON.stringify({ info: info, roh: roh, eff: eff, fleckRoh: fleckRoh,
                          fleckEff: fleckEff, leuchtend: leuchtend });
})()
""" % json.dumps(_FIDS)


def _an(fid):
    return _payload(fid)


def _aus(fid):
    return _payload(fid, intensity=0)


class Viz91AusbrennenTest(_Basis):
    GERAETE = _GERAETE

    def setUp(self):
        alt = _v92._MockBridge
        _v92._MockBridge = _PollBridge
        try:
            super().setUp()
        finally:
            _v92._MockBridge = alt

    def _info(self):
        return json.loads(self._eval("JSON.stringify(window.__lightos.ausbrennInfo())"))

    def _licht(self, n_an):
        self._push(*[_an(f) if i < n_an else _aus(f) for i, f in enumerate(_FIDS)])
        return json.loads(self._eval(_ZUSTAND_JS))

    def test_wenige_geraete_bleiben_unveraendert(self):
        self._load_and_wait()
        for n in (1, 2, 3):
            z = self._licht(n)
            self.assertEqual(z["leuchtend"], n, z)
            self.assertEqual(z["info"]["kegelFaktor"], 1, z)
            self.assertEqual(z["info"]["fleckFaktor"], 1, z)
            self.assertAlmostEqual(z["eff"], z["roh"], places=6)
            self.assertAlmostEqual(z["fleckEff"], z["fleckRoh"], places=6)

    def test_sechzig_geraete_brennen_nicht_aus(self):
        self._load_and_wait()
        z = self._licht(_ANZAHL)
        self.assertEqual(z["leuchtend"], _ANZAHL)
        info = z["info"]
        # Rohsumme wie vor VIZ-91: 60 * 0,85 — material.opacity bleibt unberuehrt.
        self.assertAlmostEqual(z["roh"], _ANZAHL * 0.85, delta=0.5)
        self.assertAlmostEqual(info["kegelLast"], _ANZAHL, delta=0.5)
        # Feste Zahlen statt aus ausbrennInfo() nachgerechnet: Kegel 8/60,
        # Flecken (10/60)^0,75 — eine weichere Kurve (z. B. die Wurzel,
        # 0,365) faellt hier auf.
        self.assertAlmostEqual(info["kegelFaktor"], 8 / 60, places=3)
        self.assertAlmostEqual(info["fleckFaktor"], (10 / 60) ** 0.75, places=3)
        # Effektiv: ein Budget von ~8 vollen Kegeln (8 * 0,85 = 6,8) statt 51.
        self.assertLess(z["eff"], 7.5, z)
        self.assertLess(z["fleckEff"], 0.3 * z["fleckRoh"], z)
        # Mehr Geraete heisst nie WENIGER Licht (bei Exponent 1 bleibt die Summe
        # ueber der Schwelle konstant: ein festes Budget von ~Schwelle Kegeln).
        z30 = self._licht(30)
        self.assertGreaterEqual(z["eff"], z30["eff"] - 1e-6)
        self.assertLess(z30["info"]["kegelFaktor"], 1)

    def test_last_wird_inkrementell_gefuehrt(self):
        self._load_and_wait()
        self._licht(_ANZAHL)
        z = self._licht(2)                     # wieder abdimmen
        self.assertAlmostEqual(z["info"]["kegelLast"], 2.0, delta=0.05)
        self.assertEqual(z["info"]["kegelFaktor"], 1)
        self.assertEqual(z["info"]["geraete"], _ANZAHL)
        self._licht(_ANZAHL)
        # Geraete entfernen (fixtureRemoved) -> nur die zwei Restlichen tragen Last.
        for fid in _FIDS[2:]:
            self._bridge_obj.fixtureRemoved.emit(fid)
        self._poll_until_true("window.__lightos.ausbrennInfo().geraete === 2")
        info = json.loads(self._eval("JSON.stringify(window.__lightos.ausbrennInfo())"))
        self.assertLessEqual(info["kegelLast"], 2.0 + 0.05, info)
        self.assertEqual(info["kegelFaktor"], 1, info)

    def test_kurve_ist_rein_und_stetig(self):
        self._load_and_wait()
        werte = json.loads(self._eval(
            "JSON.stringify([0, 4, 8, 8.001, 16, 32, 80, 1000, NaN, -1]"
            ".map(n => window.__lightos.ausbrennDaempfung(n, 8, 0.3)))"))
        self.assertEqual(werte[:3], [1, 1, 1])
        self.assertAlmostEqual(werte[3], 1.0, places=3)        # stetig an der Schwelle
        self.assertAlmostEqual(werte[4], math.sqrt(0.5), places=6)
        self.assertAlmostEqual(werte[5], 0.5, places=6)
        self.assertAlmostEqual(werte[6], max(0.3, math.sqrt(0.1)), places=6)
        self.assertEqual(werte[7], 0.3)                         # Untergrenze
        self.assertEqual(werte[8:], [1, 1])                     # Unsinn -> neutral

    def test_eingestellte_kurven_mit_festen_werten(self):
        """Die im Betrieb benutzten Kurven (nicht der Standard-Exponent)."""
        self._load_and_wait()
        r = json.loads(self._eval("""
        (function(){
          const L = window.__lightos, i = L.ausbrennInfo();
          const k = n => L.ausbrennDaempfung(n, i.kegelSchwelle, i.kegelMinimum, i.kegelExponent);
          const b = n => L.ausbrennDaempfung(n, i.fleckSchwelle, i.fleckMinimum, i.fleckExponent);
          return JSON.stringify({i: i, k: [8, 8.001, 16, 60, 80, 100, 1000].map(k),
                                 b: [10, 20, 40, 100, 1000].map(b)});
        })()"""))
        i = r["i"]
        self.assertEqual((i["kegelSchwelle"], i["kegelExponent"], i["kegelMinimum"]),
                         (8, 1, 0.08))
        self.assertEqual((i["fleckSchwelle"], i["fleckExponent"], i["fleckMinimum"]),
                         (10, 0.75, 0.25))
        for ist, soll in zip(r["k"], [1, 1, 0.5, 8 / 60, 0.1, 0.08, 0.08]):
            self.assertAlmostEqual(ist, soll, places=3)
        for ist, soll in zip(r["b"], [1, 0.5 ** 0.75, 0.25 ** 0.75, 0.25, 0.25]):
            self.assertAlmostEqual(ist, soll, places=4)

    def test_unsichtbares_zaehlt_nicht(self):
        """beamsOff und Fleck-Schalter: nur sichtbare Kegel/Flecken tragen Last,
        und der Wechsel greift OHNE neues DMX-Update."""
        self._load_and_wait()
        self._licht(_ANZAHL)
        self.assertAlmostEqual(self._info()["kegelLast"], _ANZAHL, delta=0.5)
        self._bridge_obj._poll = json.dumps({"beamsOff": _FIDS[:30]})
        self._poll_until_true(
            "Math.abs(window.__lightos.ausbrennInfo().kegelLast - 30) < 0.5")
        info = self._info()
        self.assertAlmostEqual(info["kegelFaktor"], 8 / 30, places=3)
        self.assertAlmostEqual(info["fleckLast"], _ANZAHL, delta=0.5)   # Flecken bleiben
        # Ein DMX-Update haelt den Stand (beamsOff gilt weiter).
        z = self._licht(_ANZAHL)
        self.assertAlmostEqual(z["info"]["kegelLast"], 30, delta=0.5)
        self._bridge_obj._poll = json.dumps({"beamsOff": []})
        self._poll_until_true(
            "Math.abs(window.__lightos.ausbrennInfo().kegelLast - %d) < 0.5" % _ANZAHL)
        # Fleck-Schalter aus -> keine Fleck-Last, Faktor neutral; wieder an.
        self._bridge_obj.settingsChanged.emit(json.dumps({"showFloorSpots": False}))
        self._poll_until_true("window.__lightos.ausbrennInfo().fleckLast < 1e-6")
        self.assertEqual(self._info()["fleckFaktor"], 1)
        self._bridge_obj.settingsChanged.emit(json.dumps({"showFloorSpots": True}))
        self._poll_until_true(
            "Math.abs(window.__lightos.ausbrennInfo().fleckLast - %d) < 0.5" % _ANZAHL)

    def test_prisma_zaehlt_je_strahl(self):
        """Ein 3er-Prisma wirft drei Strahlen aus EINEM Material — drei Kegel Last."""
        self._load_and_wait()
        self._licht(2)
        self.assertAlmostEqual(self._info()["kegelLast"], 2, delta=0.05)
        mit = dict(_an(_FIDS[0]), prism=3)     # Facettenzahl wie vom Service
        self._push(mit)
        z = json.loads(self._eval(_ZUSTAND_JS))
        self.assertEqual(self._eval(
            "window.__lightos.fixtures['%d'].prismCones.length" % _FIDS[0]), 2)
        self.assertAlmostEqual(z["info"]["kegelLast"], 4, delta=0.05)
        z = self._licht(2)                     # Profil ohne Prisma -> wieder einer
        self.assertAlmostEqual(z["info"]["kegelLast"], 2, delta=0.05)

    def test_shader_bindet_gemeinsame_uniform(self):
        self._load_and_wait()
        self._licht(_ANZAHL)
        r = json.loads(self._eval("""
        (function(){
          const L = window.__lightos, T = window.THREE, info = L.ausbrennInfo();
          const basis = T.ShaderLib.basic.fragmentShader;
          const roh = L.__patchAusbrennShader(basis);
          const probe = (mat) => {
            const sh = { fragmentShader: basis, uniforms: {} };
            mat.onBeforeCompile(sh);
            const u = sh.uniforms.lightosAusbrennen;
            return { wert: u ? u.value : null, gepatcht: sh.fragmentShader !== basis,
                     schluessel: mat.customProgramCacheKey() };
          };
          const a = L.fixtures['%d'], b = L.fixtures['%d'];
          return JSON.stringify({
            patch: roh !== null,
            zeile: roh ? roh.indexOf('gl_FragColor.a *= lightosAusbrennen') : -1,
            tone: roh ? roh.indexOf('#include <tonemapping_fragment>') : -1,
            kopf: roh ? roh.indexOf('uniform float lightosAusbrennen;') : -1,
            doppelt: L.__patchAusbrennShader(basis + '\\n#include <tonemapping_fragment>'),
            kegelA: probe(a.beam.material), kegelB: probe(b.beam.material),
            fleck: probe(a.floorSpot.material), info: info,
            aufgeloest: (function(){
              const sh = { fragmentShader: basis, uniforms: {} };
              a.beam.material.onBeforeCompile(sh);
              let src = sh.fragmentShader;
              for (let n = 0; n < 5; n++) src = src.replace(
                /#include <([\\w]+)>/g, (m, k) => (T.ShaderChunk[k] !== undefined) ? T.ShaderChunk[k] : m);
              const main = src.slice(src.indexOf('void main'));
              const z = main.indexOf('gl_FragColor.a *= lightosAusbrennen');
              const rest = main.slice(z + 1);
              const fehler = [];
              const re = /gl_FragColor(\\.a)?\\s*=([^;]*);/g;
              let m, danach = 0;
              while ((m = re.exec(rest)) !== null) {
                danach += 1;
                if (m[2].indexOf('gl_FragColor') < 0) fehler.push(m[0]);
              }
              return { danach: danach, fehler: fehler, gefunden: z >= 0 };
            })(),
          });
        })()
        """ % (_FIDS[0], _FIDS[1])))
        self.assertTrue(r["patch"], "Anker fehlt im MeshBasic-Shader des three-Stands")
        self.assertGreaterEqual(r["kopf"], 0)
        self.assertGreater(r["tone"], r["zeile"], "Daempfung muss VOR dem Tone-Mapping stehen")
        self.assertGreater(r["zeile"], 0)
        self.assertIsNone(r["doppelt"], "zweideutiger Anker -> kein Patch")
        info = r["info"]
        self.assertTrue(r["kegelA"]["gepatcht"] and r["fleck"]["gepatcht"])
        self.assertAlmostEqual(r["kegelA"]["wert"], info["kegelFaktor"], places=6)
        self.assertAlmostEqual(r["kegelB"]["wert"], info["kegelFaktor"], places=6)
        self.assertAlmostEqual(r["fleck"]["wert"], info["fleckFaktor"], places=6)
        self.assertLess(info["kegelFaktor"], 1)
        # WIRKUNG ohne GL: Shader mit allen Includes aufloesen; nach unserer
        # Zeile darf kein Schreiben auf gl_FragColor / gl_FragColor.a mehr
        # kommen, dessen rechte Seite nicht aus gl_FragColor selbst stammt
        # (sonst waere die Daempfung wieder ueberschrieben).
        self.assertEqual(r["aufgeloest"]["fehler"], [], r["aufgeloest"])
        self.assertTrue(r["aufgeloest"]["gefunden"], r["aufgeloest"])
        self.assertGreater(r["aufgeloest"]["danach"], 0)
        # Gleiche Funktion je Art -> gleiches Programm fuer alle Kegel.
        self.assertEqual(r["kegelA"]["schluessel"], r["kegelB"]["schluessel"])
        self.assertNotEqual(r["kegelA"]["schluessel"], r["fleck"]["schluessel"])


# ── Echtes Bild (nur mit GL-Kontext) ─────────────────────────────────────────
# Gemessen 2026-10-27 (Linux, offscreen): 60 weisse Kegel -> Weiss-Anteil
# 58 %% ohne, 35 %% mit Schutz; 3 Kegel -> identisch (6 %%).
_BILD_JS = """
(function(){
  const L = window.__lightos, T = window.THREE;
  const cv = document.getElementsByTagName('canvas')[0];
  const gl = cv && (cv.getContext('webgl2') || cv.getContext('webgl'));
  if (!gl || gl.isContextLost()) return JSON.stringify({gl: false});
  if (!window.__v91cam) {
    Object.defineProperty(window, 'innerWidth', { value: 640, configurable: true });
    Object.defineProperty(window, 'innerHeight', { value: 480, configurable: true });
    window.dispatchEvent(new Event('resize'));
    const cam = new T.PerspectiveCamera(50, 640 / 480, 0.1, 100);
    cam.position.set(0, 3.5, 16); cam.lookAt(0, 3, 0); cam.updateMatrixWorld(true);
    L.view.activeCam = cam; window.__v91cam = cam;
  }
  L.__ausbrennSchutz(%s);
  L.requestRender(); L.__renderTick();
  const W = gl.drawingBufferWidth, H = gl.drawingBufferHeight;
  const buf = new Uint8Array(W * H * 4);
  gl.readPixels(0, 0, W, H, gl.RGBA, gl.UNSIGNED_BYTE, buf);
  let weiss = 0, summe = 0;
  for (let i = 0; i < buf.length; i += 4) {
    if (Math.min(buf[i], buf[i + 1], buf[i + 2]) >= 250) weiss += 1;
    summe += buf[i] + buf[i + 1] + buf[i + 2];
  }
  return JSON.stringify({gl: true, weiss: weiss / (W * H), mittel: summe / (W * H * 3)});
})()
"""


class Viz91BildTest(Viz91AusbrennenTest):
    """Vorher/Nachher im echten Bild (uebersprungen ohne GL-Kontext)."""

    def _paar(self, n):
        self._licht(n)
        an = json.loads(self._eval(_BILD_JS % "true"))
        if not an.get("gl"):
            raise unittest.SkipTest("kein GL-Kontext offscreen")
        aus = json.loads(self._eval(_BILD_JS % "false"))
        self._eval(_BILD_JS % "true")
        return an, aus

    def test_bild_sechzig_kegel_weniger_weiss(self):
        self._load_and_wait()
        an, aus = self._paar(_ANZAHL)
        # Der Befund: ausgebrannt. Absolutwert bewusst weit (gemessen 0,58 auf
        # Linux/llvmpipe; anderes GL/Pixeldichte darf abweichen) — die Aussage
        # tragen die relativen Vergleiche darunter.
        self.assertGreater(aus["weiss"], 0.25, aus)
        self.assertLess(an["weiss"], 0.7 * aus["weiss"], (an, aus))
        self.assertLess(an["mittel"], aus["mittel"], (an, aus))

    def test_bild_wenige_kegel_unveraendert(self):
        self._load_and_wait()
        an, aus = self._paar(3)
        self.assertAlmostEqual(an["weiss"], aus["weiss"], places=6)
        self.assertAlmostEqual(an["mittel"], aus["mittel"], places=6)


# Die Kerntests nicht doppelt laufen lassen.
for _name in [n for n in vars(Viz91AusbrennenTest) if n.startswith("test_")]:
    setattr(Viz91BildTest, _name, None)
