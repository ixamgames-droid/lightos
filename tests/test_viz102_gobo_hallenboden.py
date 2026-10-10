"""VIZ-102: Gobo-Muster ueber die Buehnenkante — reine Rechnung unter Node.

Rueckmeldung des Projektinhabers nach der Live-Demo von VIZ-96:

1. Die Projektion endete an der Buehnenkante (Grenzebene aus B3). Sie soll auf
   dem Hallenboden weiterlaufen. Die frueher gesehene "Streckung" dort war
   echte Geometrie des Motivs — das aber ueber den Kegel hinausreichte (Licht
   ohne Strahl). Jetzt liegt das Motiv im Kegel, die Projektion laeuft ueber
   die Kante weiter und gehoert zur Reichweite des Kegels: bis zum fernen
   Kegelrand auf der getroffenen Flaeche volle Staerke, tiefer mit dem
   Abstandsquadrat, jenseits der Kegel-Reichweite weich aus
   (``goboFern``/``goboFernFaktor``, dieselbe Rechnung wie im Shader).
2. Teile des flachen Musters hingen vor der Buehne in der Luft: die Scheibe
   ragte ueber die Kante der getroffenen Oberseite. Die Kante ist ein gedrehtes
   Rechteck (``kantenAbstand``); der Ueberhang (``goboUeberhang``) verlaengert
   den Kegel stufenlos, und der Rest des Musters liegt auf der Flaeche darunter
   — ausserhalb des Schattens der Oberseite (``schattenRechteck``).

Der Ablauf in der Seite: ``test_viz102_gobo_hallenboden_scene.py``.
"""
import math
import unittest

from test_viz96_gobo_projektion import _fahre, _node_verfuegbar

_RUMPF = r"""
// ── Reichweite ──
aus.ausblende = G.GOBO_AUSBLENDE;
const F = G.goboFern(6, 8);
aus.fern = F;
aus.fernKlein = G.goboFern(6, 4);          // Kegel kuerzer als das Muster auf seiner Flaeche
aus.fernKein = [G.goboFern(Infinity, 8), G.goboFern(0, 8), G.goboFern(NaN, 8), G.goboFern(null, null)]
  .map(v => v[0] === G.GOBO_FERN_AUS && v[1] === G.GOBO_FERN_AUS);
aus.fernOhneReich = G.goboFern(6, null);
aus.faktor = [3, 6, 7, 8, 8.6, 9.2, 12].map(w => G.goboFernFaktor(F, w));
aus.faktorAus = G.goboFernFaktor(G.goboFern(null, null), 80);
let fv = 2, mono = true;
for (let w = 1; w < 12; w += 0.05) { const x = G.goboFernFaktor(F, w); if (x > fv + 1e-12) mono = false; fv = x; }
aus.faktorMonoton = mono;
// Shader: dieselbe Rechnung, auf die Maske, mit dem Achsabstand w.
const fs = G.patchFragmentShader(THREE.ShaderLib.standard.fragmentShader,
                                 THREE.ShaderChunk.lights_fragment_begin);
aus.glsl = fs.indexOf('uniform vec2 lightosGoboFern[ NUM_SPOT_LIGHT_SHADOWS ];') >= 0
  && fs.indexOf('float lightosGw = max( vSpotShadowCoord[ i ].w, 0.0001 );') >= 0
  && fs.indexOf('float lightosGf = lightosGoboFern[ i ].x / lightosGw;') >= 0
  && fs.indexOf('min( 1.0, lightosGf * lightosGf ) * ( 1.0 - smoothstep( lightosGoboFern[ i ].y, lightosGoboFern[ i ].y * 1.15, lightosGw ) )') >= 0;
aus.keineEbene = fs.indexOf('lightosGoboEbene') < 0;
// w der Schattenkoordinate IST der Abstand entlang der Lichtachse.
const l = new THREE.SpotLight(0xffffff, 1, 25, 0.5, 0.05, 1);
l.castShadow = true; l.position.set(1, 5, -2); l.target.position.set(2.5, 1, 1.2);
l.shadow.camera.near = 0.5;
l.updateMatrixWorld(true); l.target.updateMatrixWorld(true); l.shadow.updateMatrices(l);
const achse = l.target.position.clone().sub(l.position).normalize();
aus.wFehler = 0;
for (const P of [[2.5, 1, 1.2], [0, 0, 6], [4, 1, 3], [1, 2, 0]]) {
  const v = new THREE.Vector3(P[0], P[1], P[2]);
  const c = new THREE.Vector4(v.x, v.y, v.z, 1).applyMatrix4(l.shadow.matrix);
  aus.wFehler = Math.max(aus.wFehler, Math.abs(c.w - v.sub(l.position).dot(achse)));
}

// ── Kante ──
const K = { cx: 1, cz: 2, hx: 4, hz: 2.5, c: 1, s: 0, y: 1 };
aus.kante = [G.kantenAbstand(K, 1, 2), G.kantenAbstand(K, 4.5, 2), G.kantenAbstand(K, 1, 4.2),
             G.kantenAbstand(K, 1, 5), G.kantenAbstand(K, -3.5, 4.4)];
// um 90 Grad gedreht: die lange Seite liegt jetzt in z.
const w = Math.PI / 2;
const KD = { cx: 1, cz: 2, hx: 4, hz: 2.5, c: Math.cos(w), s: Math.sin(w), y: 1 };
aus.gedreht = [G.kantenAbstand(KD, 1, 5.5), G.kantenAbstand(KD, 3, 2), G.kantenAbstand(KD, 4, 2)];
// gegen three: Punkt in lokale Koordinaten eines um y gedrehten Objekts.
const o = new THREE.Object3D(); o.position.set(1, 0, 2); o.rotation.y = 0.7; o.updateMatrixWorld(true);
const KS = { cx: 1, cz: 2, hx: 4, hz: 2.5, c: Math.cos(0.7), s: Math.sin(0.7), y: 1 };
aus.dreiFehler = 0;
for (const P of [[3, 1], [-2, 4], [0.5, 0.2], [5, 5]]) {
  const lok = o.worldToLocal(new THREE.Vector3(P[0], 0, P[1]));
  const soll = Math.min(4 - Math.abs(lok.x), 2.5 - Math.abs(lok.z));
  aus.dreiFehler = Math.max(aus.dreiFehler, Math.abs(soll - G.kantenAbstand(KS, P[0], P[1])));
}

// ── Ueberhang ──
aus.ueber = [3, 2, 1.5, 1, 0.5, 0, -1].map(d => G.goboUeberhang(d, 2));
aus.ueberKaputt = [G.goboUeberhang(1, 0), G.goboUeberhang(NaN, 2), G.goboUeberhang(1, NaN)];
let vor = 0, sprung = 0, monoton = true;
for (let d = 2; d >= 0; d -= 0.02) {
  const u = G.goboUeberhang(d, 2);
  if (u < vor - 1e-12) monoton = false;
  sprung = Math.max(sprung, u - vor); vor = u;
}
aus.ueberMonoton = monoton; aus.ueberSprung = sprung;

// ── Schatten der Oberseite ──
const A = [0, 5, -3];
const S = G.schattenRechteck(K, A[0], A[1], A[2], 0);
aus.schatten = S;
// Strahl vom Licht durch jede Ecke der Oberseite trifft den Boden in der
// entsprechenden Ecke des Schattenrechtecks.
aus.eckFehler = 0;
for (const [ex, ez] of [[1, 1], [1, -1], [-1, 1], [-1, -1]]) {
  const oben = [K.cx + ex * K.hx, K.y, K.cz + ez * K.hz];
  const t = A[1] / (A[1] - oben[1]);
  const bx = A[0] + (oben[0] - A[0]) * t, bz = A[2] + (oben[2] - A[2]) * t;
  aus.eckFehler = Math.max(aus.eckFehler, Math.abs(bx - (S.cx + ex * S.hx)),
                           Math.abs(bz - (S.cz + ez * S.hz)));
}
aus.schattenNull = [G.schattenRechteck(K, 0, 1, 0, 0), G.schattenRechteck(K, 0, 0.5, 0, 0),
                    G.schattenRechteck(K, 0, 5, 0, 1), G.schattenRechteck(K, 0, 5, 0, 2)];

// ── Fussabdruck des geneigten Kegels ──
const senk = G.strahlFussabdruck(0, -1, 0, 5, 0.4);
aus.senkrecht = senk.map(r => r.weit);
const th = 42 * Math.PI / 180, tA = Math.tan(23.7 * Math.PI / 180);
const gen = G.strahlFussabdruck(0, -Math.cos(th), Math.sin(th), 5.8, tA);   // geneigt nach +z
aus.geneigt = gen.slice(0, 4).map(r => [r.dx, r.dz, r.weit]);
// Gegenprobe vor/zurueck: Randstrahlen in der Neigungsebene auf die Flaeche.
const H = 5.8 * Math.cos(th), aW = Math.atan(tA);
aus.vorSoll = H * (Math.tan(th + aW) - Math.tan(th));
aus.zurueckSoll = H * (Math.tan(th) - Math.tan(th - aW));
aus.fussLeer = [G.strahlFussabdruck(0, 1, 0, 5, 0.4).length, G.strahlFussabdruck(0, -1, 0, Infinity, 0.4).length,
                G.strahlFussabdruck(1, 0, 0, 5, 0.4).length];
// Ueberhang: senkrecht = wie der einfache Radius-Vergleich zur naechsten Kante.
const KB = { cx: 0, cz: 0, hx: 5.5, hz: 3.5, c: 1, s: 0, y: 1 };
aus.gleich = [];
for (const z of [0, 1.0, 2.0, 2.8, 3.2, 3.49]) {
  aus.gleich.push([G.goboUeberhangGerichtet(KB, 0, z, G.strahlFussabdruck(0, -1, 0, 5, 0.4)),
                   G.goboUeberhang(G.kantenAbstand(KB, 0, z), 2)]);
}
// Geneigt nach vorn, Mitte 2,7 m vor der Kante: ein Radius (2,5 m) saehe
// keinen Ueberhang, der Fussabdruck (5,7 m nach vorn) schon.
aus.geneigtUeber = G.goboUeberhangGerichtet(KB, 0, 0.8, gen);
// Tiefe Platte, Mitte 4 m vor der vorderen Kante: nach vorn geneigt ragt der
// Fussabdruck darueber, nach hinten geneigt nicht.
const KT = { cx: 0, cz: 0, hx: 5.5, hz: 10, c: 1, s: 0, y: 1 };
aus.tiefVor = G.goboUeberhangGerichtet(KT, 0, 6, gen);
aus.geneigtWeg = G.goboUeberhangGerichtet(KT, 0, 6,
  G.strahlFussabdruck(0, -Math.cos(th), -Math.sin(th), 5.8, tA));
aus.radiusSaehe = G.goboUeberhang(G.kantenAbstand(KB, 0, 0.8), 5.8 * tA);
aus.ausserhalb = G.goboUeberhangGerichtet(KB, 0, 4, gen);
aus.ohneFuss = G.goboUeberhangGerichtet(KB, 0, 0, []);
// Kegellaenge bis der FERNE Rand unten ankommt.
aus.fernSenk = G.kegelFernLaenge(-1, 0.4, 6);
const Lf = G.kegelFernLaenge(-Math.cos(th), tA, 7.2);
aus.fernGeneigt = Lf;
// Punkt auf dem fernen Rand bei Achstiefe Lf: seine Hoehe unter der Spitze
// muss die Hoehe der unteren Flaeche sein (7,2 m Achse -> H = 7,2 cos th).
aus.fernHoehe = [Lf / Math.cos(aW) * Math.cos(th + aW), 7.2 * Math.cos(th)];
aus.fernFlach = G.kegelFernLaenge(-Math.cos(1.5), 0.4, 6);
"""


@unittest.skipUnless(_node_verfuegbar(), "node nicht installiert")
class Viz102LogikTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = _fahre(_RUMPF)

    # ── Punkt 1: Reichweite statt Grenze ─────────────────────────────────────
    def test_projektion_gehoert_zur_reichweite_des_kegels(self):
        r = self.r
        self.assertEqual(r["fern"], [6, 8])
        self.assertEqual(r["fernKlein"], [6, 6], "das Muster auf SEINER Flaeche bleibt immer ganz")
        self.assertEqual(r["fernKein"], [True, True, True, True], "kein Auftreffpunkt: keine Grenze")
        self.assertEqual(r["fernOhneReich"][0], 6)
        f = r["faktor"]
        self.assertEqual(f[:2], [1, 1], "bis zum fernen Kegelrand auf der Flaeche volle Staerke")
        self.assertAlmostEqual(f[2], (6 / 7) ** 2, places=9, msg="tiefer: Abstandsquadrat")
        self.assertAlmostEqual(f[3], (6 / 8) ** 2, places=9)
        self.assertTrue(0 < f[4] < f[3], "jenseits der Kegel-Reichweite blendet es aus")
        self.assertEqual(f[5], 0, "bei 1,15 x Reichweite ist nichts mehr da: kein Muster ohne Strahl")
        self.assertEqual(f[6], 0)
        self.assertTrue(r["faktorMonoton"], "nirgends heller als naeher am Licht")
        self.assertEqual(r["faktorAus"], 1)
        self.assertAlmostEqual(r["ausblende"], 1.15, places=9)

    def test_shader_rechnet_dasselbe_und_kennt_keine_grenzebene_mehr(self):
        self.assertTrue(self.r["glsl"])
        self.assertTrue(self.r["keineEbene"], "die Projektion endet nicht mehr an der Kante")
        self.assertLess(self.r["wFehler"], 1e-9, "w = Abstand entlang der Lichtachse")

    # ── Punkt 2: Kante, Ueberhang, Schatten ──────────────────────────────────
    def test_kantenabstand_auch_gedreht(self):
        r = self.r
        for ist, soll in zip(r["kante"], [2.5, 0.5, 0.3, -0.5, -0.5]):
            self.assertAlmostEqual(ist, soll, places=9)
        for ist, soll in zip(r["gedreht"], [0.5, 0.5, -0.5]):
            self.assertAlmostEqual(ist, soll, places=9)
        self.assertLess(r["dreiFehler"], 1e-9, "gleiche Drehrichtung wie three (rotation.y)")

    def test_ueberhang_weich_von_null_bis_eins(self):
        r = self.r
        u = r["ueber"]
        self.assertEqual(u[0], 0)
        self.assertEqual(u[1], 0, "Rand beruehrt die Kante gerade: noch kein Ueberhang")
        self.assertAlmostEqual(u[3], 0.5, places=9)
        self.assertEqual(u[5], 1, "Mitte auf der Kante")
        self.assertEqual(u[6], 1)
        self.assertTrue(0 < u[2] < u[3] < u[4] < 1)
        self.assertEqual(r["ueberKaputt"], [0, 0, 0])
        self.assertTrue(r["ueberMonoton"])
        self.assertLess(r["ueberSprung"], 0.02, "die Kegellaenge haengt daran — kein Sprung")

    def test_fussabdruck_des_geneigten_kegels(self):
        r = self.r
        for w in r["senkrecht"]:
            self.assertAlmostEqual(w, 2.0, places=9, msg="senkrecht: ein Kreis")
        vor, zurueck, quer1, quer2 = r["geneigt"]
        self.assertAlmostEqual(vor[2], r["vorSoll"], places=9)
        self.assertAlmostEqual(zurueck[2], r["zurueckSoll"], places=9)
        self.assertGreater(vor[2], 2 * zurueck[2], "nach vorn viel weiter als zurueck")
        self.assertAlmostEqual(vor[1], 1.0, places=9)
        self.assertAlmostEqual(zurueck[1], -1.0, places=9)
        self.assertAlmostEqual(quer1[2], quer2[2], places=9)
        self.assertEqual(r["fussLeer"], [0, 0, 0], "nach oben / waagerecht / kein Abstand")

    def test_ueberhang_folgt_der_richtung(self):
        r = self.r
        for gerichtet, radius in r["gleich"]:
            self.assertAlmostEqual(gerichtet, radius, places=9)
        self.assertEqual(r["radiusSaehe"], 0)
        self.assertGreater(r["geneigtUeber"], 0.3, "ferner Rand ragt ueber die vordere Kante")
        self.assertGreater(r["tiefVor"], 0)
        self.assertEqual(r["geneigtWeg"], 0, "von der Kante weg geneigt: kein Ueberhang")
        self.assertEqual(r["ausserhalb"], 1)
        self.assertEqual(r["ohneFuss"], 0)

    def test_kegel_reicht_mit_dem_fernen_rand_bis_unten(self):
        r = self.r
        self.assertAlmostEqual(r["fernSenk"], 6, places=9)
        self.assertGreater(r["fernGeneigt"], 7.2)
        self.assertAlmostEqual(r["fernHoehe"][0], r["fernHoehe"][1], places=9)
        self.assertTrue(math.isfinite(r["fernFlach"]))
        self.assertEqual(r["fernFlach"], 6, "zu flach: Achslaenge")

    def test_schatten_der_oberseite_ist_das_gestreckte_rechteck(self):
        r = self.r
        s = r["schatten"]
        self.assertAlmostEqual(s["hx"], 4 * 5 / 4, places=9)
        self.assertAlmostEqual(s["hz"], 2.5 * 5 / 4, places=9)
        self.assertEqual(s["y"], 0)
        self.assertLess(r["eckFehler"], 1e-9)
        self.assertEqual(r["schattenNull"], [None, None, None, None],
                         "Licht nicht ueber der Oberseite / Flaeche nicht darunter")
        self.assertTrue(math.isfinite(s["cx"]) and math.isfinite(s["cz"]))


if __name__ == "__main__":
    unittest.main()
