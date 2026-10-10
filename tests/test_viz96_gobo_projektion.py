"""VIZ-96 (B1): Gobo-Projektion mit Verdeckung — Shader-Patch, Atlas, Abbildung.

Bis VIZ-96 lag das Gobo als flache Scheibe auf der Flaeche, die der
Zentralstrahl trifft. Eine Traverse im Strahl ignorierte das Muster: kein Muster
auf dem Hindernis, kein Schatten dahinter. three r128 kennt kein
``SpotLight.map`` — ``scene_src/scene/gobo_projektion.js`` haengt das Motiv
deshalb als Maske in den Licht-Loop der schattenwerfenden Spot-Lichter.

Das Modul ist rein (keine Imports). Dieser Test faehrt es unter Node gegen die
ECHTEN r128-Shader-Chunks aus ``three_local.js`` und prueft:

* der Anker steht genau einmal im Chunk; die Maske landet im Spot-Block,
  hinter dem Schattentest und vor ``RE_Direct`` — also innerhalb der
  Schatten-Bedingung (Verdeckung kommt aus der vorhandenen Shadow-Map);
* three rollt die Licht-Schleife per Textersatz aus: nach dem Ausrollen steht
  im Patch kein nacktes ``i`` mehr;
* genau EIN zusaetzlicher Sampler, unabhaengig von der Zahl der Lichter;
* EINE Hook-Funktion fuer alle Materialien -> der Programmschluessel-Zusatz
  (``onBeforeCompile.toString()``) ist fuer alle gleich und aendert sich bei
  Gobo-Wechsel/Drehung/an-aus nicht (nur Uniform-Werte);
* ohne Installation (Stufe Niedrig) bleibt die Materialklasse unberuehrt;
* die Abbildung Licht -> Motiv: ein Randstrahl des Kegels bei Umfangswinkel th
  landet im Motiv genau dort, wo das Bodenmotiv sein Teil th hat — gemessen
  mit der echten Schattenmatrix von three, auch senkrecht nach unten und mit
  Gobo-Drehung;
* der Atlas: jede Kachel an ihrem Platz, Zeile 0 unten.

Die Kopplung an den Spot-Pool in der echten Seite prueft
``test_viz96_gobo_projektion_scene.py``.
"""
import json
import os
import re
import subprocess
import tempfile
import unittest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_VIZ = os.path.join(_REPO, "src", "ui", "visualizer")
_MODUL = os.path.join(_VIZ, "scene_src", "scene", "gobo_projektion.js")
_THREE = os.path.join(_VIZ, "three_local.js")
_STUFEN = os.path.join(_VIZ, "scene_src", "scene", "quality_tiers.js")
_FIXTURES = os.path.join(_VIZ, "scene_src", "fixtures", "fixtures.js")

_KOPF = """
import { createRequire } from 'module';
import * as G from './gobo.mjs';
const require = createRequire(import.meta.url);
const THREE = require(%s);
const aus = {};
"""

_FUSS = "\nconsole.log(JSON.stringify(aus));\n"


def _node_verfuegbar() -> bool:
    try:
        subprocess.run(["node", "--version"], capture_output=True, timeout=10)
        return True
    except Exception:                       # pragma: no cover
        return False


def _fahre(rumpf: str):
    if not os.path.exists(_MODUL):
        raise AssertionError("scene/gobo_projektion.js fehlt (VIZ-96 B1)")
    with open(_MODUL, encoding="utf-8") as fh:
        quelle = fh.read()
    with tempfile.TemporaryDirectory() as verz:
        with open(os.path.join(verz, "gobo.mjs"), "w", encoding="utf-8") as fh:
            fh.write(quelle)
        with open(os.path.join(verz, "treiber.mjs"), "w", encoding="utf-8") as fh:
            fh.write(_KOPF % json.dumps(_THREE) + rumpf + _FUSS)
        out = subprocess.run(["node", os.path.join(verz, "treiber.mjs")],
                             capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        raise AssertionError(out.stderr)
    return json.loads(out.stdout)


# Fragment-Shader so zusammensetzen, wie three es nach onBeforeCompile tut:
# Includes aufloesen, dann die Licht-Schleife ausrollen (r128, WebGLProgram).
_AUFLOESEN = r"""
function aufloesen(s) {
  return s.replace(/^[ \t]*#include +<([\w\d./]+)>/gm,
    (m, name) => aufloesen(THREE.ShaderChunk[name]));
}
function ausrollen(s, zahlen) {
  for (const [k, v] of Object.entries(zahlen)) s = s.split(k).join(String(v));
  return s.replace(
    /#pragma unroll_loop_start\s+for\s*\(\s*int\s+i\s*=\s*(\d+)\s*;\s*i\s*<\s*(\d+)\s*;\s*i\s*\+\+\s*\)\s*{([\s\S]+?)}\s+#pragma unroll_loop_end/g,
    (m, a, b, rumpf) => {
      let t = '';
      for (let i = parseInt(a); i < parseInt(b); i++) {
        t += rumpf.replace(/\[\s*i\s*\]/g, '[ ' + i + ' ]').replace(/UNROLLED_LOOP_INDEX/g, i);
      }
      return t;
    });
}
"""


@unittest.skipUnless(_node_verfuegbar(), "node nicht installiert")
class ShaderPatchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = _fahre(_AUFLOESEN + r"""
const chunk = THREE.ShaderChunk.lights_fragment_begin;
const std = THREE.ShaderLib.standard.fragmentShader;
aus.revision = THREE.REVISION;
aus.ankerZahl = chunk.split(G.GOBO_ANKER).length - 1;
aus.includeZahl = std.split(G.GOBO_INCLUDE).length - 1;
const gepatcht = G.patchFragmentShader(std, chunk);
aus.gepatcht = typeof gepatcht === 'string';
const voll = aufloesen(gepatcht), ohne = aufloesen(std);
aus.samplerMit = (voll.match(/uniform\s+sampler2D\s+\w+/g) || []).length;
aus.samplerOhne = (ohne.match(/uniform\s+sampler2D\s+\w+/g) || []).length;
aus.kopfZahl = voll.split('uniform sampler2D lightosGoboMap;').length - 1;
// Lage der Maske im aufgeloesten Quelltext
const spot = voll.indexOf('#if ( NUM_SPOT_LIGHTS > 0 ) && defined( RE_Direct )');
const dir = voll.indexOf('#if ( NUM_DIR_LIGHTS > 0 ) && defined( RE_Direct )');
const anker = voll.indexOf(G.GOBO_ANKER);
const maske = voll.indexOf('lightosGoboParam[ i ]');
const maskeEnde = voll.indexOf('directLight.color *= mix( 1.0, lightosGm, lightosGp.x );');
const bedingung = voll.lastIndexOf('#if defined( USE_SHADOWMAP ) && ( UNROLLED_LOOP_INDEX < NUM_SPOT_LIGHT_SHADOWS )', anker);
const endif = voll.indexOf('#endif', anker);
const reDirect = voll.indexOf('RE_Direct( directLight, geometry, material, reflectedLight );', anker);
aus.lage = { spot, dir, anker, maske, maskeEnde, bedingung, endif, reDirect };
aus.maskeZahl = voll.split('lightosGoboParam[ i ]').length - 1;
// Ausgerollt: 3 Spot-Lichter, 2 davon mit Schatten.
const roll = ausrollen(voll, { NUM_SPOT_LIGHT_SHADOWS: 2, NUM_SPOT_LIGHTS: 3,
  NUM_DIR_LIGHT_SHADOWS: 0, NUM_DIR_LIGHTS: 0, NUM_POINT_LIGHT_SHADOWS: 0,
  NUM_POINT_LIGHTS: 0, NUM_RECT_AREA_LIGHTS: 0, NUM_HEMI_LIGHTS: 0 });
const teile = roll.split('vec4 lightosGp = ');
const bloecke = teile.slice(1).map(t => t.split('\n\t\t}')[0]);
// Die Praeprozessor-Bedingung direkt vor jedem Block (three laesst sie stehen).
aus.rollBedingung = teile.slice(0, -1).map(t => {
  const m = t.match(/#if defined\( USE_SHADOWMAP \) && \( (\d+) < (\d+) \)/g);
  return m[m.length - 1].replace(/.*\( (\d+) < (\d+) \)/, '$1<$2');
});
aus.rollBloecke = bloecke.length;
aus.rollIndizes = bloecke.map(t => (t.match(/lightosGoboParam\[ (\d+) \]/) || [])[1]);
aus.rollKoord = bloecke.map(t => (t.match(/vSpotShadowCoord\[ (\d+) \]/g) || []).join('|'));
aus.nacktesI = bloecke.some(t => /\bi\b/.test(t));
aus.kopfRoll = roll.includes('uniform vec4 lightosGoboParam[ 2 ];');
// Nicht patchbar -> null (kein halber Patch)
aus.ohneAnker = G.patchLichtChunk(chunk.replace(G.GOBO_ANKER, 'x'));
aus.doppelAnker = G.patchLichtChunk(chunk + chunk);
aus.basic = G.patchFragmentShader(THREE.ShaderLib.basic.fragmentShader, chunk);
aus.ohneChunk = G.patchFragmentShader(std, 'void main() {}');
""")

    def test_anker_steht_genau_einmal_im_r128_chunk(self):
        r = self.r
        self.assertEqual(r["revision"], "128")
        self.assertEqual(r["ankerZahl"], 1, "Anker im Spot-Block von lights_fragment_begin")
        self.assertEqual(r["includeZahl"], 1)
        self.assertTrue(r["gepatcht"])
        self.assertEqual(r["maskeZahl"], 1, "die Maske steht genau einmal (im Spot-Block)")

    def test_maske_liegt_im_schattenzweig_des_spot_blocks(self):
        g = self.r["lage"]
        for name, wert in g.items():
            self.assertGreaterEqual(wert, 0, name)
        self.assertLess(g["spot"], g["bedingung"])
        self.assertLess(g["bedingung"], g["anker"], "hinter der Schatten-Bedingung")
        self.assertLess(g["anker"], g["maske"], "Maske NACH dem Schattentest")
        self.assertLess(g["maskeEnde"], g["endif"],
                        "Maske innerhalb der Schatten-Bedingung (nur Lichter mit Shadow-Map)")
        self.assertLess(g["endif"], g["reDirect"], "vor RE_Direct: sie wirkt auf den Lichtbeitrag")
        self.assertLess(g["reDirect"], g["dir"], "im Spot-Block, nicht bei Richtungslichtern")

    def test_ausgerollte_schleife_hat_kein_nacktes_i(self):
        r = self.r
        # Drei Spot-Lichter, zwei mit Schatten: der dritte Block steht hinter
        # `2 < 2` — der Praeprozessor wirft ihn weg (kein Zugriff ausserhalb des Felds).
        self.assertEqual(r["rollBloecke"], 3)
        self.assertEqual(r["rollBedingung"], ["0<2", "1<2", "2<2"])
        self.assertEqual(r["rollIndizes"], ["0", "1", "2"])
        self.assertEqual(r["rollKoord"], ["|".join(["vSpotShadowCoord[ %d ]" % n] * 2)
                                          for n in range(3)])
        self.assertFalse(r["nacktesI"], "nach dem Ausrollen darf kein `i` stehen bleiben")
        self.assertTrue(r["kopfRoll"], "Feldgroesse = Zahl der Schatten-Lichter")

    def test_genau_ein_zusaetzlicher_sampler(self):
        r = self.r
        self.assertEqual(r["samplerMit"] - r["samplerOhne"], 1,
                         "EIN Atlas fuer alle Motive und alle Lichter")
        self.assertEqual(r["kopfZahl"], 1)

    def test_nicht_patchbar_liefert_null(self):
        r = self.r
        self.assertIsNone(r["ohneAnker"])
        self.assertIsNone(r["doppelAnker"])
        self.assertIsNone(r["basic"], "unbeleuchtete Materialien bleiben unberuehrt")
        self.assertIsNone(r["ohneChunk"])


@unittest.skipUnless(_node_verfuegbar(), "node nicht installiert")
class HookTest(unittest.TestCase):
    def test_ein_hook_fuer_alle_und_nur_uniforms_aendern_sich(self):
        r = _fahre(r"""
const Std = THREE.MeshStandardMaterial;
aus.vorherEigen = Object.prototype.hasOwnProperty.call(Std.prototype, 'onBeforeCompile');
aus.schluesselOhne = new Std().customProgramCacheKey();
aus.aktivVorher = G.goboProjektionAktiv();
aus.slotsVorher = G.goboProjektionInfo().slots;
aus.kachelVorher = G.goboKachel('zebra');
const atlas = { istAtlas: true };
aus.ohneAtlas = G.installGoboProjektion({ materialKlassen: [Std], Vector4: THREE.Vector4,
  lichtChunk: THREE.ShaderChunk.lights_fragment_begin, index: {} });
aus.falscherChunk = G.installGoboProjektion({ materialKlassen: [Std], Vector4: THREE.Vector4,
  lichtChunk: 'kein Anker', atlas, index: {} });
aus.eigenNachFehlversuch = Object.prototype.hasOwnProperty.call(Std.prototype, 'onBeforeCompile');
aus.installiert = G.installGoboProjektion({ materialKlassen: [Std], Vector4: THREE.Vector4,
  lichtChunk: THREE.ShaderChunk.lights_fragment_begin, atlas, index: { ring_slits: 0, zebra: 6 } });
const a = new Std(), b = new THREE.MeshPhysicalMaterial(), basic = new THREE.MeshBasicMaterial();
aus.gleicheFunktion = a.onBeforeCompile === b.onBeforeCompile;
aus.basicUnberuehrt = basic.onBeforeCompile === THREE.Material.prototype.onBeforeCompile;
const k1 = a.customProgramCacheKey();
aus.schluesselGleich = k1 === b.customProgramCacheKey();
aus.schluesselAndersAlsOhne = k1 !== aus.schluesselOhne;
const s1 = { fragmentShader: THREE.ShaderLib.standard.fragmentShader, uniforms: {} };
const s2 = { fragmentShader: THREE.ShaderLib.physical.fragmentShader, uniforms: {} };
a.onBeforeCompile(s1); b.onBeforeCompile(s2);
aus.geteilteUniforms = s1.uniforms.lightosGoboMap === s2.uniforms.lightosGoboMap
  && s1.uniforms.lightosGoboParam === s2.uniforms.lightosGoboParam;
aus.atlasDrin = s1.uniforms.lightosGoboMap.value === atlas;
aus.feld = s1.uniforms.lightosGoboParam.value.length;
aus.max = G.GOBO_MAX_LICHTER;
aus.quelleGleich = s1.fragmentShader === s2.fragmentShader;
const quelle1 = s1.fragmentShader;
// Gobo an, drehen, wechseln, aus: nur Werte.
G.setzeGoboLicht(0, 1, 0.5, -0.25, G.goboKachel('zebra'));
aus.nachSetzen = G.goboProjektionInfo().param[0];
G.setzeGoboLicht(0, 1, 0.1, 0.9, G.goboKachel('ring_slits'));
G.loescheGoboLicht(0);
aus.nachLoeschen = G.goboProjektionInfo().param[0];
const s3 = { fragmentShader: THREE.ShaderLib.standard.fragmentShader, uniforms: {} };
a.onBeforeCompile(s3);
aus.quelleStabil = s3.fragmentShader === quelle1;
aus.schluesselStabil = a.customProgramCacheKey() === k1;
aus.ausserhalb = G.setzeGoboLicht(99, 1, 1, 0, 0);
aus.kachelUnbekannt = G.goboKachel('open');
aus.kachelLeer = G.goboKachel('');
aus.info = G.goboProjektionInfo();
// Basic-Shader durch den Hook: unveraendert, keine Uniforms.
const s4 = { fragmentShader: THREE.ShaderLib.basic.fragmentShader, uniforms: {} };
a.onBeforeCompile(s4);
aus.basicQuelle = s4.fragmentShader === THREE.ShaderLib.basic.fragmentShader
  && Object.keys(s4.uniforms).length === 0;
""")
        # Stufe Niedrig = nichts installiert: Klasse und Schluessel wie three sie liefert.
        self.assertFalse(r["vorherEigen"])
        self.assertFalse(r["aktivVorher"])
        self.assertEqual(r["slotsVorher"], 0)
        self.assertEqual(r["kachelVorher"], -1)
        # Fehlversuche lassen alles unberuehrt.
        self.assertFalse(r["ohneAtlas"])
        self.assertFalse(r["falscherChunk"])
        self.assertFalse(r["eigenNachFehlversuch"])
        self.assertTrue(r["installiert"])
        self.assertTrue(r["gleicheFunktion"])
        self.assertTrue(r["basicUnberuehrt"])
        self.assertTrue(r["schluesselGleich"], "ein Programmschluessel-Zusatz fuer alle Materialien")
        self.assertTrue(r["schluesselAndersAlsOhne"])
        self.assertTrue(r["geteilteUniforms"], "alle Programme lesen dieselben Uniform-Objekte")
        self.assertTrue(r["atlasDrin"])
        self.assertEqual(r["feld"], r["max"])
        self.assertTrue(r["quelleGleich"])
        self.assertEqual(r["nachSetzen"], [1, 0.5, -0.25, 6])
        self.assertEqual(r["nachLoeschen"], [0, 1, 0, 0])
        self.assertTrue(r["quelleStabil"], "Gobo-Wechsel aendert den Shader-Quelltext nicht")
        self.assertTrue(r["schluesselStabil"], "Gobo-Wechsel aendert den Programmschluessel nicht")
        self.assertFalse(r["ausserhalb"])
        self.assertEqual(r["kachelUnbekannt"], -1)
        self.assertEqual(r["kachelLeer"], -1)
        self.assertEqual(r["info"]["slots"], 1)
        self.assertTrue(r["basicQuelle"])

    def test_feld_reicht_fuer_das_schatten_dach_der_stufe_maximal(self):
        with open(_FIXTURES, encoding="utf-8") as fh:
            dach = int(re.search(r"(?m)^const SHADOW_SPOT_HARD_CAP_MAX = (\d+);", fh.read()).group(1))
        r = _fahre("aus.max = G.GOBO_MAX_LICHTER;")
        self.assertGreaterEqual(r["max"], dach,
                                "lightosGoboParam muss jedes Schatten-Licht bedienen koennen")


@unittest.skipUnless(_node_verfuegbar(), "node nicht installiert")
class AbbildungTest(unittest.TestCase):
    """Randstrahl th des Kegels -> Motiv-Koordinate, mit der echten Schattenmatrix."""

    _RUMPF = r"""
const RAND = 0.62;
function fall(pos, ziel, goboWinkel, halbwinkel) {
  const licht = new THREE.SpotLight(0xffffff, 1, 25, 0.3, 0.5, 1);
  licht.position.set(...pos);
  licht.target.position.set(...ziel);
  licht.updateMatrixWorld(true); licht.target.updateMatrixWorld(true);
  // Kegel: -y zeigt vom Licht zum Ziel, dazu die Gobo-Drehung um die Achse.
  const kopf = new THREE.Object3D();
  kopf.position.set(...pos);
  const achse = new THREE.Vector3(...ziel).sub(new THREE.Vector3(...pos)).normalize();
  kopf.quaternion.setFromUnitVectors(new THREE.Vector3(0, -1, 0), achse);
  const kegel = new THREE.Object3D();
  kegel.rotation.y = goboWinkel;
  kopf.add(kegel);
  kopf.updateMatrixWorld(true);
  const e = kegel.matrixWorld.elements;
  const tanK = Math.tan(halbwinkel);
  const optik = G.goboLichtWinkel(tanK, RAND);
  licht.angle = optik.winkel;
  licht.shadow.updateMatrices(licht);
  const blick = new THREE.Matrix4().lookAt(licht.position, licht.target.position, new THREE.Vector3(0, 1, 0));
  const b = blick.elements;
  const d = G.goboDrehung(
    e[0]*b[0] + e[1]*b[1] + e[2]*b[2], e[0]*b[4] + e[1]*b[5] + e[2]*b[6],
    e[8]*b[0] + e[9]*b[1] + e[10]*b[2], e[8]*b[4] + e[9]*b[5] + e[10]*b[6]);
  const cs = optik.skala * d[0], sn = optik.skala * d[1];
  let fehler = 0;
  for (let k = 0; k < 16; k++) {
    const th = 2 * Math.PI * k / 16;
    // Punkt auf der Mantellinie th, 5 m vor dem Licht
    const p = new THREE.Vector3(5 * tanK * Math.sin(th), -5, 5 * tanK * Math.cos(th))
      .applyMatrix4(kegel.matrixWorld);
    const c = new THREE.Vector4(p.x, p.y, p.z, 1).applyMatrix4(licht.shadow.matrix);
    const dx = c.x / c.w - 0.5, dy = c.y / c.w - 0.5;
    const u = cs * dx - sn * dy, v = sn * dx + cs * dy;       // wie im Shader
    fehler = Math.max(fehler, Math.abs(u - 0.5 * RAND * Math.sin(th)),
                      Math.abs(v + 0.5 * RAND * Math.cos(th)));
  }
  return { fehler, skala: optik.skala, winkel: optik.winkel };
}
aus.schraeg = fall([2, 6, 1], [5, 0, -2], 0, 0.25);
aus.schraegGedreht = fall([2, 6, 1], [5, 0, -2], 1.1, 0.25);
aus.senkrecht = fall([0, 6, 0], [0, 0, 0], 0, 0.2);
aus.senkrechtGedreht = fall([0, 6, 0], [0, 0, 0], 2.4, 0.2);
aus.nachHinten = fall([-3, 4, 2], [-6, 0, 6], 4.0, 0.35);
aus.weit = fall([0, 6, 0], [1, 0, 2], 0.7, 1.3);
aus.deckel = G.GOBO_MAX_LICHTWINKEL;
aus.ungueltig = [G.goboLichtWinkel(0, RAND), G.goboLichtWinkel(0.3, 0), G.goboLichtWinkel(NaN, RAND)];
aus.entartet = G.goboDrehung(0, 0, 0, 0);
"""

    @classmethod
    def setUpClass(cls):
        cls.r = _fahre(cls._RUMPF)

    def test_randstrahl_trifft_sein_motivteil(self):
        for name in ("schraeg", "schraegGedreht", "senkrecht", "senkrechtGedreht", "nachHinten"):
            self.assertLess(self.r[name]["fehler"], 2e-3,
                            f"{name}: Kegelrand muss im Motiv bei GOBO_RAND unter Winkel th liegen")

    def test_ganze_kachel_passt_ins_licht_bis_zum_deckel(self):
        r = self.r
        self.assertAlmostEqual(r["schraeg"]["skala"], 1.0, places=9,
                               msg="unter dem Deckel fuellt die Kachel genau den Lichtkegel")
        self.assertGreater(r["schraeg"]["winkel"], 0.25, "das Licht oeffnet weiter als der Kegel")
        # Sehr weiter Kegel: Winkel am Deckel, der Massstab gleicht aus.
        self.assertAlmostEqual(r["weit"]["winkel"], r["deckel"], places=9)
        self.assertLess(r["weit"]["skala"], 1.0)
        self.assertLess(r["weit"]["fehler"], 2e-3, "auch am Deckel bleibt der Kegelrand auf GOBO_RAND")

    def test_ungueltige_eingaben(self):
        self.assertEqual(self.r["ungueltig"], [None, None, None])
        self.assertEqual(self.r["entartet"], [1, 0])


@unittest.skipUnless(_node_verfuegbar(), "node nicht installiert")
class AtlasTest(unittest.TestCase):
    def test_kacheln_liegen_an_ihrem_platz(self):
        r = _fahre(r"""
const rufe = [];
function neuesCanvas(b, h) {
  return { width: b, height: h, getContext: () => ({
    fillRect: (...a) => rufe.push(['fill', ...a]),
    drawImage: (bild, ...a) => rufe.push(['bild', bild.stil, ...a]),
  }) };
}
const stile = ['a', 'b', 'c', 'd', 'e', 'f', 'g'];
const atlas = G.baueGoboAtlas(stile, s => ({ stil: s }), neuesCanvas, 512);
aus.groesse = [atlas.canvas.width, atlas.canvas.height];
aus.index = atlas.index;
aus.rufe = rufe;
aus.raster = [G.GOBO_ATLAS_SPALTEN, G.GOBO_ATLAS_ZEILEN];
aus.zuViele = G.baueGoboAtlas(['1','2','3','4','5','6','7','8','9'], s => ({ stil: s }), neuesCanvas, 512);
aus.motivFehlt = G.baueGoboAtlas(['a', 'b'], s => (s === 'b' ? null : { stil: s }), neuesCanvas, 512);
aus.leer = G.baueGoboAtlas([], s => ({ stil: s }), neuesCanvas, 512);
""")
        self.assertEqual(r["raster"], [4, 2])
        self.assertEqual(r["groesse"], [2048, 1024], "EINE Textur fuer alle Motive")
        self.assertEqual(r["index"], {s: i for i, s in enumerate("abcdefg")})
        self.assertEqual(r["rufe"][0], ["fill", 0, 0, 2048, 1024], "Grund schwarz = kein Licht")
        bilder = [x for x in r["rufe"] if x[0] == "bild"]
        # Zeile 0 liegt UNTEN im Canvas (flipY der Textur): y = 512; Zeile 1 oben: y = 0.
        self.assertEqual(bilder[0], ["bild", "a", 0, 512, 512, 512])
        self.assertEqual(bilder[3], ["bild", "d", 1536, 512, 512, 512])
        self.assertEqual(bilder[4], ["bild", "e", 0, 0, 512, 512])
        self.assertEqual(bilder[6], ["bild", "g", 1024, 0, 512, 512])
        self.assertIsNone(r["zuViele"])
        self.assertIsNone(r["motivFehlt"])
        self.assertIsNone(r["leer"])


class StufenSchalterTest(unittest.TestCase):
    def test_gobo_projektion_je_stufe(self):
        with open(_STUFEN, encoding="utf-8") as fh:
            quelle = fh.read()
        werte = {}
        for stufe in ("low", "high", "max"):
            block = re.search(stufe + r": Object\.freeze\(\{(.*?)\}\)", quelle, re.S).group(1)
            werte[stufe] = dict(re.findall(r"(\w+): ([^,\n]+)", block)).get("goboProjektion")
        self.assertEqual(werte, {"low": "false", "high": "true", "max": "true"},
                         "Niedrig bleibt beim Bodenmuster, Hoch/Maximal projizieren")

    def test_anleitung_nennt_das_gobo_je_stufe(self):
        pfad = os.path.join(_REPO, "docs", "anleitung_3d_visualizer_2026",
                            "ANLEITUNG_3D_BUEHNE.md")
        with open(pfad, encoding="utf-8") as fh:
            text = fh.read()
        for name, wort in (("Niedrig", "flacher Fleck"), ("Hoch", "projiziert"),
                           ("Maximal", "projiziert")):
            zeile = re.search(r"(?m)^\| \*\*%s\*\*.*$" % name, text)
            self.assertIsNotNone(zeile, f"Tabellenzeile {name} fehlt")
            self.assertIn(wort, zeile.group(0))


if __name__ == "__main__":
    unittest.main()
