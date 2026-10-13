"""VIZ-96 (B3): Uebergaenge der Gobo-Projektion — reine Logik unter Node.

Sichtpruefung von B1/B2 am Bildschirm (12 Moving Heads, Stufe Hoch) ergab vier
offene Punkte. Die reine Rechnung dazu liegt in
``scene_src/scene/gobo_projektion.js`` und wird hier ohne Seite geprueft:

* **Blende** (``goboBlendeSchritt``): wechselt ein Pool-Licht den Besitzer,
  verschwand die Projektion in EINEM Bild. Jetzt laeuft der Anteil linear ueber
  ``GOBO_BLENDE_MS``; ein Bild nach langer Pause ueberspringt die Blende nicht.
* **Helligkeit** (``goboFlachDeckkraft``): das flache Rueckfall-Muster ist an
  die Projektion angeglichen und traegt waehrend der Blende seinen Anteil.
* **Schmale Buehnen-Elemente** (``goboSchmal``): Traverse/Stuetze tragen kein
  mehrere Meter grosses Muster; Wand und Buehnenplatte bleiben Ziel.
* der Shader bekommt EIN weiteres Uniform-Feld (seit VIZ-102 die Reichweite
  ``lightosGoboFern`` statt der Grenzebene aus B3 — die Projektion laeuft jetzt
  ueber Kanten weiter, s. ``test_viz102_gobo_hallenboden.py``), keinen Sampler.

Vergabe-Hysterese und der Ablauf im Spot-Pool: ``test_viz96_b3_uebergaenge_scene.py``.
"""
import unittest

from test_viz96_gobo_projektion import _fahre, _node_verfuegbar

_RUMPF = r"""
// ── Blende mit Fake-Uhr (16-ms-Bilder) ──
function lauf(von, ziel, dt) {
  let a = von; const reihe = [];
  for (let n = 0; n < 200; n++) {
    a = G.goboBlendeSchritt(a, ziel, dt);
    reihe.push(a);
    if (a === ziel) break;
  }
  let sprung = 0, monoton = true, vor = von;
  for (const v of reihe) {
    sprung = Math.max(sprung, Math.abs(v - vor));
    if (ziel < von ? v > vor : v < vor) monoton = false;
    vor = v;
  }
  return { ms: reihe.length * dt, sprung, monoton, ende: reihe[reihe.length - 1] };
}
aus.dauer = G.GOBO_BLENDE_MS;
aus.aus16 = lauf(1, 0, 16);
aus.ein16 = lauf(0, 1, 16);
aus.aus60 = lauf(1, 0, 60);
aus.pause = G.goboBlendeSchritt(1, 0, 5000);
aus.pauseEin = G.goboBlendeSchritt(0, 1, 5000);
aus.steht = [G.goboBlendeSchritt(1, 1, 16), G.goboBlendeSchritt(0, 0, 16),
             G.goboBlendeSchritt(0.4, 1, 0), G.goboBlendeSchritt(undefined, 0, 16)];
aus.umkehr = G.goboBlendeSchritt(G.goboBlendeSchritt(1, 0, 36), 1, 18);

// ── Helligkeit des flachen Musters ──
aus.hell = G.GOBO_FLACH_HELL;
aus.flach = [G.goboFlachDeckkraft(0.8, 1), G.goboFlachDeckkraft(0.8, 0.5),
             G.goboFlachDeckkraft(0.8, 0), G.goboFlachDeckkraft(0.8, undefined)];
aus.bonus = G.GOBO_HALTE_BONUS;

// ── schmale Buehnen-Elemente ──
const T = { x: 2.4, y: 0.3, z: 0.3 };
aus.schmal = {
  traverse: G.goboSchmal(T, 2.5),
  stuetze: G.goboSchmal({ x: 0.3, y: 4, z: 0.3 }, 2.5),
  wand: G.goboSchmal({ x: 10, y: 6, z: 0.2 }, 2.5),
  platte: G.goboSchmal({ x: 8, y: 1, z: 5 }, 2.5),
  platteWeit: G.goboSchmal({ x: 8, y: 1, z: 5 }, 11),
  podestKlein: G.goboSchmal({ x: 0.9, y: 0.8, z: 0.9 }, 2.5),
  podestEngerStrahl: G.goboSchmal({ x: 0.9, y: 0.8, z: 0.9 }, 0.5),
  ohneMasse: G.goboSchmal(null, 2.5),
  ohneGobo: G.goboSchmal(T, 0),
  kaputt: G.goboSchmal({ x: NaN, y: 1, z: 1 }, 2.5),
};

// ── Shader + Uniforms ──
const chunk = THREE.ShaderChunk.lights_fragment_begin;
const fs = G.patchFragmentShader(THREE.ShaderLib.standard.fragmentShader, chunk);
aus.sampler = (fs.match(/uniform\s+sampler2D\s+lightos\w+/g) || []).length;
aus.feld = fs.indexOf('uniform vec2 lightosGoboFern[ NUM_SPOT_LIGHT_SHADOWS ];') >= 0;
const iEbene = fs.indexOf('lightosGoboFern[ i ].x / lightosGw');
const iMix = fs.indexOf('directLight.color *= mix( 1.0, lightosGm, lightosGp.x );');
const iMaske = fs.indexOf('float lightosGm = texture2D( lightosGoboMap');
aus.lage = iMaske >= 0 && iEbene > iMaske && iMix > iEbene;
aus.einmal = fs.split('lightosGoboFern[ i ]').length - 1;   // x einmal, y zweimal

class Mat {}
aus.installiert = G.installGoboProjektion({
  materialKlassen: [Mat], lichtChunk: chunk, Vector4: THREE.Vector4,
  atlas: { atlas: true }, index: { zebra: 0 },
});
const hook = Mat.prototype.onBeforeCompile;
const vorher = hook.toString();
const sh = { fragmentShader: THREE.ShaderLib.standard.fragmentShader, uniforms: {} };
hook.call(new Mat(), sh);
aus.uniformDa = !!sh.uniforms.lightosGoboFern
  && sh.uniforms.lightosGoboFern.value.length === 2 * G.GOBO_MAX_LICHTER;
aus.grund = G.goboProjektionInfo().fern.every(v => v[0] === G.GOBO_FERN_AUS && v[1] === G.GOBO_FERN_AUS);
const feld = sh.uniforms.lightosGoboFern.value;
G.setzeGoboLicht(2, 1, 1, 0, 0);
G.setzeGoboFern(2, [6, 7.5]);
aus.gesetzt = G.goboProjektionInfo().fern[2];
aus.gleichesFeld = sh.uniforms.lightosGoboFern.value === feld;
G.loescheGoboLicht(2);
aus.geloescht = G.goboProjektionInfo().fern[2][0] === G.GOBO_FERN_AUS
  && G.goboProjektionInfo().fern[2][1] === G.GOBO_FERN_AUS;
aus.ausserhalb = G.setzeGoboFern(99, [6, 7.5]);
aus.hookGleich = Mat.prototype.onBeforeCompile === hook && hook.toString() === vorher;
"""


@unittest.skipUnless(_node_verfuegbar(), "node nicht installiert")
class Viz96B3LogikTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = _fahre(_RUMPF)

    # ── Punkt 1: Blende ──────────────────────────────────────────────────────
    def test_blende_laeuft_150_bis_250_ms_ohne_sprung(self):
        r = self.r
        self.assertGreaterEqual(r["dauer"], 150)
        self.assertLessEqual(r["dauer"], 250)
        for name in ("aus16", "ein16", "aus60"):
            lauf = r[name]
            self.assertTrue(lauf["monoton"], name)
            self.assertGreaterEqual(lauf["ms"], 150, name)
            self.assertLessEqual(lauf["ms"], 250, name)
        self.assertEqual(r["aus16"]["ende"], 0)
        self.assertEqual(r["ein16"]["ende"], 1)
        # 60-Hz-Bilder: kein Schritt groesser als ein Zehntel.
        self.assertLess(r["aus16"]["sprung"], 0.1)
        self.assertLess(r["ein16"]["sprung"], 0.1)

    def test_bild_nach_langer_pause_ueberspringt_die_blende_nicht(self):
        # Bilder entstehen nur auf Anforderung — 5 s Abstand sind normal.
        self.assertGreater(self.r["pause"], 0.3)
        self.assertLess(self.r["pause"], 1.0)
        self.assertLess(self.r["pauseEin"], 0.7)
        self.assertGreater(self.r["pauseEin"], 0.0)

    def test_blende_steht_am_ziel_und_kehrt_um(self):
        self.assertEqual(self.r["steht"], [1, 0, 0.4, 0])
        self.assertAlmostEqual(self.r["umkehr"], 1 - 36 / self.r["dauer"] + 18 / self.r["dauer"],
                               places=9)

    # ── Punkt 2: Helligkeit ──────────────────────────────────────────────────
    def test_flaches_muster_ist_abgedunkelt_und_traegt_seinen_anteil(self):
        r = self.r
        self.assertLess(r["hell"], 1.0, "flach war am Bildschirm heller als die Projektion")
        self.assertGreater(r["hell"], 0.6)
        voll, halb, null, ohne = r["flach"]
        self.assertAlmostEqual(voll, 0.8 * r["hell"], places=9)
        self.assertAlmostEqual(halb, 0.4 * r["hell"], places=9)
        # Anteil 0: Scheibe ist ueber die Ebenen-Maske aus, Deckkraft bleibt Mass
        # fuer "leuchtet" (bridge.js#applySettings).
        self.assertAlmostEqual(null, voll, places=9)
        self.assertAlmostEqual(ohne, voll, places=9)

    def test_haltebonus_ist_massvoll(self):
        self.assertGreater(self.r["bonus"], 1.0)
        self.assertLessEqual(self.r["bonus"], 1.5)

    # ── Punkt 3: schmale Buehnen-Elemente ────────────────────────────────────
    def test_traverse_und_stuetze_sind_schmal_platte_und_wand_nicht(self):
        s = self.r["schmal"]
        self.assertTrue(s["traverse"])
        self.assertTrue(s["stuetze"])
        self.assertFalse(s["wand"])
        self.assertFalse(s["platte"])
        self.assertFalse(s["platteWeit"], "auch ein sehr weiter Strahl bleibt auf der Buehnenplatte")
        self.assertTrue(s["podestKlein"])
        self.assertFalse(s["podestEngerStrahl"], "passt das Muster darauf, bleibt das Podest Ziel")
        self.assertFalse(s["ohneMasse"])
        self.assertFalse(s["ohneGobo"])
        self.assertFalse(s["kaputt"])

    # ── Shader ───────────────────────────────────────────────────────────────
    def test_shader_ein_feld_eine_multiplikation_kein_sampler(self):
        r = self.r
        self.assertEqual(r["sampler"], 1, "weiter genau EIN zusaetzlicher Sampler")
        self.assertTrue(r["feld"])
        self.assertTrue(r["lage"], "Reichweite wirkt auf die Maske, vor der Multiplikation aufs Licht")
        self.assertEqual(r["einmal"], 3)

    def test_reichweite_setzen_und_loeschen_aendert_nur_werte(self):
        r = self.r
        self.assertTrue(r["installiert"])
        self.assertTrue(r["uniformDa"])
        self.assertTrue(r["grund"], "Grundstellung = keine Abschwaechung")
        self.assertEqual(r["gesetzt"], [6, 7.5])
        self.assertTrue(r["gleichesFeld"])
        self.assertTrue(r["geloescht"], "loescheGoboLicht nimmt die Reichweite mit")
        self.assertFalse(r["ausserhalb"])
        self.assertTrue(r["hookGleich"], "Programmschluessel-Zusatz unveraendert (VIZ-69)")


if __name__ == "__main__":
    unittest.main()
