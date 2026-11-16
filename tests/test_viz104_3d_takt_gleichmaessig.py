"""VIZ-104 (3D-Takt): der Strobe im 3D-Visualizer blitzt gleichmaessig.

Befund der zweiten Sichtprobe (Windows x64, RX 580, 60-Hz-Bildschirm, 12 PAR +
4 Strobe): 53-59 Bilder/s beim Blitzen, dazu 1-4 einzelne lange Bilder
(33-83 ms) je 8 s. Das gleitende Mittel ``fpsNachfuehren`` machte aus EINEM
66-ms-Bild 46 statt 55 Bilder/s — mehr als die Traegheit von 12 %. Die Periode
sprang (bei 5 Hz 20 Wechsel in 10 s zwischen 8 und 12 Bildern), und weil die
Phase ``bild % periode`` war, sprang der Blitz mit.

Hier wird die reine Rechnung (``scene_src/fixtures/strobe.js``, unter Node)
mit SIMULIERTEN Bildfolgen gefahren — genau der Betriebsweg von
``fixtures.js#tickStrobe``: je Tick ein Bild, Bildabstand in ``taktMessen``,
Faktor aus ``taktFaktor``. Gemessen wird in ZEIT: wann beginnt ein Blitz,
wie weit liegen die Blitze auseinander, wie oft wechselt der Takt.

(a) 60 Bilder/s mit einzelnen 66-ms-Bildern alle 2-4 s, 2/5/10/20 Hz
(b) 30-Hz-Bildschirm mit einzelnen 67-ms-Bildern
(c) echter Wechsel 60 -> 30 Bilder/s (und zurueck)
(d) leicht schwankende Bildrate 53-59 Bilder/s
(e) 'weich' ohne Phasensprung, 'aus' unveraendert
(f) Pause / Tab im Hintergrund
(4) verlorenes Bild: Zaehler je Tick gegen Zaehler aus der Uhr

Das alte Verfahren laeuft im selben Treiber mit und belegt den Befund (ohne
Fix waeren (a) bis (d) rot). Die Verdrahtung in der echten Seite prueft
``test_viz104_3d_takt_gleichmaessig_scene.py``.
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MODUL = os.path.join(_REPO, "src", "ui", "visualizer", "scene_src", "fixtures",
                      "strobe.js")

_TREIBER = r"""
import * as S from './strobe.mjs';

// Bildfolge: Liste der Bildabstaende in ms. Ein Bild i erscheint zur Zeit t_i.
function lcg(seed) { let x = seed >>> 0; return () => ((x = (x * 1664525 + 1013904223) >>> 0) / 4294967296); }

function folge(dauerMs, normal, lang, lange) {
  // `lange` = Zeitpunkte (ms), an denen EIN langes Bild kommt.
  const dts = []; let t = 0, k = 0;
  while (t < dauerMs) {
    let dt = normal;
    if (k < lange.length && t >= lange[k]) { dt = lang; k += 1; }
    dts.push(dt); t += dt;
  }
  return dts;
}

// variante: 'neu' (taktMessen + taktFaktor, Zaehler je Tick),
//           'uhr' (wie neu, aber Bild aus der Uhr: runde(t * takt / 1000)),
//           'alt' (fpsNachfuehren + taktFps + strobeFaktor, Stand vor dem Fix).
function lauf(dts, hzListe, modus, variante, startFps) {
  const z = S.taktZustand(startFps || S.FPS_VORGABE);
  let fps = startFps || S.FPS_VORGABE, takt = fps, altPeriode = null, altWechsel = 0;
  let bild = 0, t = 0;
  const zeiten = [], fak = hzListe.map(() => []), taktZeiten = [], bildEff = hzListe.map(() => []);
  for (const dt of dts) {
    t += dt; bild += 1;
    if (variante === 'alt') {
      fps = S.fpsNachfuehren(fps, dt);
      const neu = S.taktFps(takt, fps);
      if (neu !== takt) { taktZeiten.push(t); takt = neu; }
    } else if (S.taktMessen(z, dt, bild)) {
      taktZeiten.push(t);
    }
    const b = (variante === 'uhr') ? Math.round(t * z.takt / 1000) : bild;
    zeiten.push(t);
    hzListe.forEach((hz, k) => {
      if (variante === 'ohnePhase') {          // robuster Takt, aber 'bild % periode'
        fak[k].push(S.strobeFaktor(b, hz, modus, z.takt));
        bildEff[k].push(b);
      } else if (variante === 'alt') {
        fak[k].push(S.strobeFaktor(b, hz, modus, takt));
        bildEff[k].push(b);
      } else {
        fak[k].push(S.taktFaktor(z, b, hz, modus));
        bildEff[k].push(S.taktBild(z, b, hz, modus));
      }
    });
  }
  const takte = (variante === 'alt') ? takt : z.takt;
  return { zeiten, fak, taktZeiten, takt: takte, fps: (variante === 'alt') ? fps : z.fps,
           bildEff, z };
}

function blitze(zeiten, f, abMs) {
  const an = [];
  for (let i = 0; i < f.length; i++) {
    if (f[i] === 1 && (i === 0 || f[i - 1] !== 1) && zeiten[i] >= (abMs || 0)) an.push(zeiten[i]);
  }
  const abst = [];
  for (let i = 1; i < an.length; i++) abst.push(an[i] - an[i - 1]);
  return { an, abst, min: Math.min(...abst), max: Math.max(...abst), n: an.length };
}

function muster(f, von, bis) { return f.slice(von, bis).map(v => v === 1 ? '#' : '.').join(''); }

const aus = {};
const LANGE_60 = [2100, 5300, 7400, 9600];          // alle 2-4 s ein langes Bild
const LANGE_30 = [1700, 4500, 6600, 9300];

// (a) 60 Bilder/s, einzelne 66-ms-Bilder.
aus.a = {};
const dtsA = folge(10000, 1000 / 60, 66, LANGE_60);
for (const v of ['neu', 'alt', 'uhr']) {
  aus.a[v] = {};
  const r = lauf(dtsA, [2, 5, 10, 20], 'flash', v, 60);
  [2, 5, 10, 20].forEach((hz, k) => {
    const b = blitze(r.zeiten, r.fak[k], 500);     // erster Blitz: Anlauf
    aus.a[v][hz] = { wechsel: r.taktZeiten.length, min: b.min, max: b.max, n: b.n,
                     periode: S.strobeBilder(hz, 60).periode,
                     muster: muster(r.fak[k], 0, 120) };
  });
}

// (b) 30-Hz-Bildschirm, einzelne 67-ms-Bilder; Start mit der Vorgabe 60.
aus.b = {};
const dtsB = folge(10000, 1000 / 30, 67, LANGE_30);
for (const v of ['neu', 'alt', 'uhr']) {
  aus.b[v] = {};
  const r = lauf(dtsB, [2, 5, 10, 20], 'flash', v, 60);
  [2, 5, 10, 20].forEach((hz, k) => {
    const b = blitze(r.zeiten, r.fak[k], 1500);
    aus.b[v][hz] = { wechsel: r.taktZeiten.length, wechselZeiten: r.taktZeiten,
                     takt: r.takt, min: b.min, max: b.max, n: b.n,
                     periode: S.strobeBilder(hz, 30).periode };
  });
}

// (c) echter Wechsel: 3 s 60 Bilder/s, dann 5 s 30 Bilder/s, dann 3 s 60.
aus.c = {};
const dtsC = [];
{ let t = 0; while (t < 3000) { dtsC.push(1000 / 60); t += 1000 / 60; }
  while (t < 8000) { dtsC.push(1000 / 30); t += 1000 / 30; }
  while (t < 11000) { dtsC.push(1000 / 60); t += 1000 / 60; } }
const WECHSEL_C = [[3000, 60, 30], [8000, 30, 60]];
for (const v of ['neu', 'alt', 'ohnePhase']) {
  aus.c[v] = {};
  const r = lauf(dtsC, [2, 3, 5, 7, 10, 20], 'flash', v, 60);
  [2, 3, 5, 7, 10, 20].forEach((hz, k) => {
    const b = blitze(r.zeiten, r.fak[k], 500);
    // Der Blitzabstand, in den der Takt-Wechsel faellt, gegen die Abstaende
    // davor und danach. Erlaubt ist nur, was die Erkennungszeit selbst
    // ausmacht (bis zur Uebernahme laeuft die alte Periode im neuen
    // Bildtempo) plus ein Bild — kein Sprung der Phase.
    const ueber = r.taktZeiten.map((ts, w) => {
      const [tWechsel, vor, nach] = WECHSEL_C[Math.min(w, 1)];
      const i = b.an.findIndex(x => x >= ts);
      if (i < 2 || i + 1 >= b.an.length) return null;
      const vorher = b.an[i - 1] - b.an[i - 2], spann = b.an[i] - b.an[i - 1],
            danach = b.an[i + 1] - b.an[i];
      const erlaubt = (ts - tWechsel) * Math.abs(1 - nach / vor) + 1000 / Math.min(vor, nach) + 0.01;
      return { vorher, spann, danach, erlaubt,
               ok: spann >= Math.min(vorher, danach) - erlaubt && spann <= Math.max(vorher, danach) + erlaubt };
    });
    // Blitzlaengen in ms (an-Strecken).
    const laengen = []; let start = null;
    r.fak[k].forEach((f, i) => {
      if (f === 1 && start === null) start = r.zeiten[i];
      if (f !== 1 && start !== null) { laengen.push(r.zeiten[i] - start); start = null; }
    });
    aus.c[v][hz] = { wechselZeiten: r.taktZeiten, takt: r.takt, min: b.min, max: b.max,
                     pAlt: 1000 * S.strobeBilder(hz, 60).periode / 60,
                     pNeu: 1000 * S.strobeBilder(hz, 30).periode / 30,
                     laengeMax: Math.max(...laengen), ueber };
  });
}
// Phase beim Wechsel, ohne Messung: Takt von Hand gestellt, jeder Wechselpunkt
// 0..119, je Frequenz. Der Anteil der Periode im ersten Bild mit neuem Takt
// muss dort weitergehen, wo die alte Periode im Bild davor stand (+ ein Bild).
{
  const paare = [[60, 30], [30, 60], [60, 50], [57, 40], [30, 144]];
  const ergebnis = { neu: 0, ohnePhase: 0, faelle: 0, doppel: 0, luecke: 0 };
  for (const [alt, neu] of paare) for (const hz of [1, 2, 3, 5, 7, 10, 20]) for (let s = 1; s < 120; s++) {
    const z = S.taktZustand(alt);
    for (let b = 0; b < s; b++) S.taktBild(z, b, hz, 'flash');
    const pA = S.strobeBilder(hz, alt).periode, pN = S.strobeBilder(hz, neu).periode;
    const anteilVor = (((S.taktBild(z, s - 1, hz, 'flash') % pA) + pA) % pA + 1) / pA % 1;
    const folgeVor = [];
    for (let b = s - pA; b < s; b++) folgeVor.push(S.taktFaktor(z, b, hz, 'flash'));
    z.takt = neu; z.wechsel += 1; z.wechselBild = s;
    const rN = ((S.taktBild(z, s, hz, 'flash') % pN) + pN) % pN;
    const rOhne = ((s % pN) + pN) % pN;
    const abstand = (x) => { const d = Math.abs(x / pN - anteilVor); return Math.min(d, 1 - d); };
    ergebnis.faelle += 1;
    if (abstand(rN) > 1 / pN + 1e-9) ergebnis.neu += 1;
    if (abstand(rOhne) > 1 / pN + 1e-9) ergebnis.ohnePhase += 1;
    // Folge um den Wechsel: Abstand der Blitzbeginne (in Bildern) liegt
    // zwischen der kuerzeren und der laengeren Periode (+-1 Bild).
    const folge = folgeVor.slice();
    for (let b = s; b < s + 2 * pN + 1; b++) folge.push(S.taktFaktor(z, b, hz, 'flash'));
    const beginne = [];
    folge.forEach((f, i) => { if (f === 1 && i > 0 && folge[i - 1] !== 1) beginne.push(i); });
    for (let i = 1; i < beginne.length; i++) {
      const d = beginne[i] - beginne[i - 1];
      if (d < Math.min(pA, pN) - 1) ergebnis.doppel += 1;
      if (d > Math.max(pA, pN) + 1) ergebnis.luecke += 1;
    }
  }
  aus.phase = ergebnis;
}

// Gleiche Frequenz bleibt gemeinsam in Phase — auch ein Geraet, das erst
// NACH dem Wechsel zu blitzen beginnt.
{
  const z = S.taktZustand(60);
  let bild = 0, gleich = true, verglichen = 0;
  dtsC.forEach((dt, i) => {
    bild += 1; S.taktMessen(z, dt, bild);
    const a = S.taktFaktor(z, bild, 5, 'flash');
    if (i > 300) {                         // Geraet B: ab Bild 300 (nach dem Wechsel)
      verglichen += 1;
      if (S.taktFaktor(z, bild, 5.0, 'flash') !== a) gleich = false;
    }
  });
  aus.c.gemeinsam = { gleich, verglichen };
}

// (d) schwankende Bildrate 53-59 Bilder/s (Zufall je Bild, dazu langsame Welle).
{
  const r1 = lcg(104);
  const dts = [];
  let t = 0;
  while (t < 20000) {
    const mitte = 56 + 2.5 * Math.sin(t / 1500);
    const fps = Math.max(53, Math.min(59, mitte + (r1() - 0.5) * 3));
    dts.push(1000 / fps); t += 1000 / fps;
  }
  aus.d = {};
  for (const v of ['neu', 'alt']) {
    const r = lauf(dts, [5], 'flash', v, 60);
    aus.d[v] = { wechsel: r.taktZeiten.length, takt: r.takt };
  }
  // Dazu die langen Bilder der Sichtprobe in derselben Folge.
  const mitLangen = dts.slice();
  [400, 800, 1100, 1500].forEach((i, k) => { mitLangen[i] = [33, 50, 66, 83][k]; });
  aus.d.neuLang = lauf(mitLangen, [5], 'flash', 'neu', 60).taktZeiten.length;
  aus.d.altLang = lauf(mitLangen, [5], 'flash', 'alt', 60).taktZeiten.length;
}

// (e) 'weich' und 'aus'.
aus.e = {};
{
  const r = lauf(dtsA, [2, 20], 'soft', 'neu', 60);
  const p = S.weichBilder(2, 60);
  let abweichend = 0;
  r.fak[0].forEach((f, i) => { if (f !== S.strobeFaktor(i + 1, 2, 'soft', 60)) abweichend += 1; });
  aus.e.weichA = { wechsel: r.taktZeiten.length, abweichend, periode: p };
  const rAlt = lauf(dtsA, [2], 'soft', 'alt', 60);
  aus.e.weichAltWechsel = rAlt.taktZeiten.length;
  // Echter Wechsel im weichen Modus: Phase geht in Stufen weiter, springt nicht.
  const rc = lauf(dtsC, [2], 'soft', 'neu', 60);
  let groessterSprung = 0;
  const w = rc.fak[0];
  for (let i = 1; i < w.length; i++) groessterSprung = Math.max(groessterSprung, Math.abs(w[i] - w[i - 1]));
  aus.e.weichC = { wechsel: rc.taktZeiten.length, groessterSprung,
                   stufe: Math.max(...Array.from({length: 8}, (_, s) =>
                     Math.abs(S.strobeFaktor(s * p / 8, 2, 'soft', 60) -
                              S.strobeFaktor((s + 1) * p / 8, 2, 'soft', 60)))) };
  const ro = lauf(dtsC, [2, 5, 20], 'off', 'neu', 60);
  aus.e.aus = ro.fak.every(f => f.every(v => v === 1));
}

// (f) Pause: 2 s nichts (Tab im Hintergrund), sonst 60 Bilder/s.
{
  const dts = folge(4000, 1000 / 60, 66, []);
  dts.splice(120, 0, 2000);
  dts.splice(200, 0, 600);
  const r = lauf(dts, [5], 'flash', 'neu', 60);
  // Nach der Pause: Folge bleibt im Bildraster periodisch (Zaehler +1 je Tick).
  const p = S.strobeBilder(5, 60).periode;
  let periodisch = true;
  for (let i = 0; i + p < r.fak[0].length; i++) if (r.fak[0][i] !== r.fak[0][i + p]) periodisch = false;
  aus.f = { wechsel: r.taktZeiten.length, fps: r.fps, takt: r.takt, periodisch,
            unsinn: [S.taktMessen(S.taktZustand(60), NaN, 1), S.taktMessen(S.taktZustand(60), 0, 1),
                     S.taktMessen(S.taktZustand(60), 5000, 1)] };
}

// Zufaellig gemischte kurze und lange Bilder (erste Sichtprobe, 34-52 Bilder/s):
// Takt-Wechsel in 20 s, neu gegen alt, je Anteil langer Bilder.
aus.mix = {};
for (const anteil of [0.1, 0.3, 0.5, 0.7]) {
  let neu = 0, alt = 0;
  for (let l = 0; l < 20; l++) {
    const r = lcg(l + 5), dts = [];
    let t = 0;
    while (t < 20000) { const dt = r() < anteil ? 33.3 : 16.7; dts.push(dt); t += dt; }
    neu += lauf(dts, [5], 'flash', 'neu', 60).taktZeiten.length;
    alt += lauf(dts, [5], 'flash', 'alt', 60).taktZeiten.length;
  }
  aus.mix[anteil] = { neu: neu / 20, alt: alt / 20 };
}
// Andere Spruenge: genau ein Wechsel, auf den neuen Wert.
aus.spruenge = {};
for (const [a, b] of [[60, 30], [30, 60], [60, 45], [60, 50], [144, 60], [60, 144]]) {
  const dts = [];
  let t = 0;
  while (t < 3000) { dts.push(1000 / a); t += 1000 / a; }
  while (t < 6000) { dts.push(1000 / b); t += 1000 / b; }
  const r = lauf(dts, [5], 'flash', 'neu', a);
  aus.spruenge[a + '>' + b] = { wechsel: r.taktZeiten.map(x => x - 3000), takt: r.takt };
}

// Robuste Messung im Einzelnen.
{
  const z = S.taktZustand(60);
  for (let i = 0; i < 40; i++) S.taktMessen(z, 1000 / 60, i);
  const vor = z.fps;
  S.taktMessen(z, 66, 41);
  const nachEinem = z.fps;
  const gemischt = [];
  for (let i = 0; i < 40; i++) gemischt.push(i % 4 < 2 ? 33.3 : 16.7);
  aus.mess = { vor, nachEinem, zuWenig: S.fpsRobust([16, 17]), gemischt: S.fpsRobust(gemischt),
               altNachEinem: S.fpsNachfuehren(55, 66),
               konst: [S.MESS_FENSTER, S.MESS_KAPPEN, S.TAKT_GEDULD, S.PAUSE_MS, S.TAKT_TRAEGHEIT] };
}

// Ohne Takt-Wechsel ist taktFaktor genau strobeFaktor (alte Folgen unveraendert).
{
  const z = S.taktZustand(60);
  let gleich = true;
  for (const hz of [0, 0.5, 2, 5, 12, 20]) for (const m of ['flash', 'soft', 'off'])
    for (let b = -5; b < 400; b++) if (S.taktFaktor(z, b, hz, m) !== S.strobeFaktor(b, hz, m, 60)) gleich = false;
  aus.ohneWechselGleich = gleich;
}

// (4) Verlorenes Bild: Zaehler je Tick ('neu') gegen Zaehler aus der Uhr
// ('uhr'). 80 Laeufe je Fall zu 20 s, alle 2-4 s ein langes Bild von 33-83 ms
// an zufaelliger Stelle. Gemessen: Abweichung jedes Blitzabstands von der
// Periode (ms) und ausgefallene Blitze (Abstand >= 1,75 Perioden).
aus.verloren = {};
for (const [schirm, normal] of [[60, 1000 / 60], [30, 1000 / 30]]) for (const hz of [2, 5, 10]) for (const v of ['neu', 'uhr']) {
  let summe = 0, n = 0, groesste = 0, ausfall = 0, ueberlang = 0;
  for (let lauf = 0; lauf < 80; lauf++) {
    const r = lcg(lauf * 7 + 1), z = S.taktZustand(schirm);
    const P = S.strobeBilder(hz, schirm).periode * normal;
    let t = 0, bild = 0, vor = 0, letzt = null, naechst = 1500 + r() * 2000;
    while (t < 20000) {
      let dt = normal;
      if (t >= naechst) { dt = 33 + r() * 50; naechst = t + 2000 + r() * 2000; ueberlang = Math.max(ueberlang, dt - normal); }
      t += dt; bild += 1;
      S.taktMessen(z, dt, bild);
      const b = (v === 'uhr') ? Math.round(t * z.takt / 1000) : bild;
      const f = S.taktFaktor(z, b, hz, 'flash');
      if (f === 1 && vor !== 1 && t > 1000) {
        if (letzt !== null) {
          const d = Math.abs(t - letzt - P);
          summe += d; n += 1; groesste = Math.max(groesste, d);
          if (t - letzt >= 1.75 * P) ausfall += 1;
        }
        letzt = t;
      }
      vor = f;
    }
  }
  aus.verloren[schirm + '/' + hz + '/' + v] = { mittel: summe / n, groesste, ausfall, n, ueberlang };
}

console.log(JSON.stringify(aus));
"""

_ERGEBNIS = None


def _node_verfuegbar():
    return shutil.which("node") is not None


def _js():
    global _ERGEBNIS
    if _ERGEBNIS is None:
        with open(_MODUL, encoding="utf-8") as fh:
            quelle = fh.read()
        with tempfile.TemporaryDirectory() as verz:
            with open(os.path.join(verz, "strobe.mjs"), "w", encoding="utf-8") as fh:
                fh.write(quelle)
            with open(os.path.join(verz, "treiber.mjs"), "w", encoding="utf-8") as fh:
                fh.write(_TREIBER)
            out = subprocess.run(["node", os.path.join(verz, "treiber.mjs")],
                                 capture_output=True, text=True, encoding="utf-8",
                                 errors="replace", timeout=120)
        if out.returncode != 0:
            raise AssertionError(out.stderr)
        _ERGEBNIS = json.loads(out.stdout)
    return _ERGEBNIS


_LANG_60 = 66 - 1000 / 60          # Ueberlaenge eines 66-ms-Bildes bei 60 Bildern/s
_LANG_30 = 67 - 1000 / 30


@unittest.skipUnless(_node_verfuegbar(), "node nicht installiert")
class EinzelneLangeBilderTest(unittest.TestCase):
    """(a)/(b): ein einzelnes langes Bild verstellt weder Takt noch Phase."""

    def test_a_60_bilder_kein_periodenwechsel_gleiche_abstaende(self):
        for hz, r in _js()["a"]["neu"].items():
            with self.subTest(hz=hz):
                self.assertEqual(r["wechsel"], 0, r)
                soll = r["periode"] * 1000 / 60
                self.assertAlmostEqual(r["min"], soll, delta=0.01)
                # Gleich bis auf hoechstens die Laenge des einen langen Bildes.
                self.assertLessEqual(r["max"] - r["min"], _LANG_60 + 0.01, r)
                self.assertGreaterEqual(r["n"], 9.5 * 60 / r["periode"] - 2)   # ab 0,5 s

    def test_b_30_hz_bildschirm_ein_wechsel_am_anfang_dann_ruhe(self):
        for hz, r in _js()["b"]["neu"].items():
            with self.subTest(hz=hz):
                # Vorgabe 60 -> gemessene 30: genau ein Wechsel, nach hoechstens 1 s.
                self.assertEqual(r["wechsel"], 1, r)
                self.assertLessEqual(r["wechselZeiten"][0], 1000, r)
                self.assertAlmostEqual(r["takt"], 30, delta=0.01)
                soll = r["periode"] * 1000 / 30
                self.assertAlmostEqual(r["min"], soll, delta=0.01)
                self.assertLessEqual(r["max"] - r["min"], _LANG_30 + 0.01, r)

    def test_befund_ohne_fix_springt_die_periode(self):
        """Das alte Verfahren in derselben Folge: die Periode wechselt bei
        jedem langen Bild hin und zurueck, die Abstaende springen weit mehr
        als ein Bild — das war das Muster der Sichtprobe."""
        alt = _js()["a"]["alt"]
        self.assertGreaterEqual(alt["5"]["wechsel"], 4, alt["5"])
        self.assertGreater(alt["5"]["max"] - alt["5"]["min"], _LANG_60 + 1, alt["5"])
        self.assertGreater(_js()["b"]["alt"]["5"]["wechsel"], 1)


@unittest.skipUnless(_node_verfuegbar(), "node nicht installiert")
class EchterWechselTest(unittest.TestCase):
    """(c): 60 -> 30 -> 60 Bilder/s. Der Takt folgt je Wechsel genau einmal,
    die Phase geht mit — kein Doppelblitz, keine lange Luecke."""

    def test_takt_folgt_genau_einmal_je_wechsel_und_schnell(self):
        for hz, r in _js()["c"]["neu"].items():
            if hz == "gemeinsam":
                continue
            with self.subTest(hz=hz):
                w = r["wechselZeiten"]
                self.assertEqual(len(w), 2, r)
                self.assertTrue(3000 < w[0] <= 3000 + 1000, w)       # 60 -> 30 nach <= 1 s
                self.assertTrue(8000 < w[1] <= 8000 + 500, w)        # 30 -> 60 nach <= 0,5 s
                self.assertAlmostEqual(r["takt"], 60, delta=0.01)

    def test_andere_spruenge_genau_einmal_auf_den_neuen_wert(self):
        for name, r in _js()["spruenge"].items():
            with self.subTest(sprung=name):
                neu = float(name.split(">")[1])
                self.assertEqual(len(r["wechsel"]), 1, r)
                self.assertLessEqual(r["wechsel"][0], 1300, r)
                self.assertAlmostEqual(r["takt"], neu, delta=0.01)

    def test_phase_geht_beim_wechsel_mit(self):
        """Jeder Wechselpunkt, sieben Frequenzen, fuenf Bildraten-Paare: die
        Phase geht weiter, wo sie stand (+ ein Bild) — kein Doppelblitz, keine
        Luecke laenger als die laengere der beiden Perioden. Ohne die
        Mitnahme ('bild % periode') springt sie in den meisten Faellen."""
        p = _js()["phase"]
        self.assertEqual(p["faelle"], 5 * 7 * 119)
        self.assertEqual(p["neu"], 0, p)
        self.assertEqual(p["doppel"], 0, p)
        self.assertEqual(p["luecke"], 0, p)
        self.assertGreater(p["ohnePhase"], p["faelle"] // 2, p)

    def test_kein_doppelblitz_keine_lange_luecke_in_zeit(self):
        """Gemessen in Zeit. Bis zur Uebernahme (0,4 bzw. 0,25 s) laeuft die
        alte Periode im neuen Bildtempo weiter — laenger oder kuerzer wird
        ein Abstand nie als diese oder die neue Periode (+ ein Bild)."""
        for hz, r in _js()["c"]["neu"].items():
            if hz == "gemeinsam":
                continue
            with self.subTest(hz=hz):
                alt60 = r["pAlt"]                 # Periode bei 60 in ms
                neu30 = r["pNeu"]                 # Periode bei 30 in ms
                p60 = alt60 * 60 / 1000           # in Bildern
                p30 = neu30 * 30 / 1000
                kuerzest = min(p30 * 1000 / 60, alt60, neu30)   # 30er-Periode im 60er-Tempo
                laengst = max(p60 * 1000 / 30, alt60, neu30)    # 60er-Periode im 30er-Tempo
                self.assertGreaterEqual(r["min"], kuerzest - 1000 / 60 - 0.01, r)
                self.assertLessEqual(r["max"], laengst + 1000 / 30 + 0.01, r)
                # Ein Blitz bleibt kurz (nicht zwei aneinander geklebt): hoechstens
                # ein gutes Viertel der laengsten Periode, + ein Bild Rundung.
                self.assertLessEqual(r["laengeMax"], 0.34 * laengst + 1000 / 30 + 0.01, r)
                for u in r["ueber"]:
                    self.assertTrue(u is None or u["ok"], u)

    def test_gleiche_frequenz_bleibt_gemeinsam_in_phase(self):
        g = _js()["c"]["gemeinsam"]
        self.assertTrue(g["gleich"])
        self.assertGreater(g["verglichen"], 100)


@unittest.skipUnless(_node_verfuegbar(), "node nicht installiert")
class SchwankendeBildrateTest(unittest.TestCase):
    def test_gemischte_bilder_schalten_selten(self):
        for anteil, m in _js()["mix"].items():
            with self.subTest(anteil=anteil):
                self.assertLessEqual(m["neu"], 6, m)            # in 20 s
                self.assertLess(m["neu"] * 4, m["alt"] + 1, m)

    def test_d_53_bis_59_bilder_periode_steht(self):
        d = _js()["d"]
        self.assertEqual(d["neu"]["wechsel"], 0, d)
        self.assertEqual(d["neu"]["takt"], 60)
        self.assertEqual(d["neuLang"], 0, d)
        # Ohne Fix: dieselbe Folge mit den langen Bildern der Sichtprobe schaltet.
        self.assertGreater(d["altLang"], 0, d)


@unittest.skipUnless(_node_verfuegbar(), "node nicht installiert")
class ModiUndPauseTest(unittest.TestCase):
    def test_e_weich_ohne_phasensprung(self):
        e = _js()["e"]
        self.assertEqual(e["weichA"]["wechsel"], 0)
        self.assertEqual(e["weichA"]["abweichend"], 0, "weiches Pulsieren ist gesprungen")
        self.assertGreater(e["weichAltWechsel"], 0, "Befund: alt sprang auch im weichen Modus")
        # Beim echten Wechsel: nie mehr als eine Stufe auf einmal.
        self.assertEqual(e["weichC"]["wechsel"], 2)
        self.assertLessEqual(e["weichC"]["groessterSprung"], e["weichC"]["stufe"] + 1e-9, e)

    def test_e_aus_bleibt_dauerlicht(self):
        self.assertTrue(_js()["e"]["aus"])

    def test_f_pause_verstellt_nichts(self):
        f = _js()["f"]
        self.assertEqual(f["wechsel"], 0)
        self.assertAlmostEqual(f["fps"], 60, delta=0.01)
        self.assertEqual(f["takt"], 60)
        self.assertTrue(f["periodisch"])
        self.assertEqual(f["unsinn"], [False, False, False])


@unittest.skipUnless(_node_verfuegbar(), "node nicht installiert")
class MessungTest(unittest.TestCase):
    def test_ein_langes_bild_zaehlt_nicht(self):
        m = _js()["mess"]
        self.assertAlmostEqual(m["vor"], 60, delta=0.01)
        self.assertAlmostEqual(m["nachEinem"], 60, delta=0.01)
        # Zum Vergleich der Befund: das alte Mittel faellt unter die Traegheit.
        self.assertLess(m["altNachEinem"], 55 * (1 - m["konst"][4]))
        self.assertEqual(m["zuWenig"], 0)
        # Gleichmaessig gemischte Bilder bleiben im Mittel (wie bisher: 40, nicht 45).
        self.assertAlmostEqual(m["gemischt"], 40, delta=1.5)

    def test_ohne_takt_wechsel_dieselbe_folge_wie_bisher(self):
        self.assertTrue(_js()["ohneWechselGleich"])


@unittest.skipUnless(_node_verfuegbar(), "node nicht installiert")
class VerlorenesBildTest(unittest.TestCase):
    """(4) Entscheidung: der Zaehler laeuft je Tick weiter (Blitz kommt um die
    Ueberlaenge des langen Bildes spaeter), statt aus der Uhr nachgefuehrt zu
    werden (dann faellt ein Blitz aus, wenn ein An-Bild uebersprungen wird).
    Gemessen an denselben Folgen wie (a) und (b)."""

    def test_je_tick_faellt_kein_blitz_aus(self):
        v = _js()["verloren"]
        for schirm in ("60", "30"):
            for hz in ("2", "5", "10"):
                tick, uhr = v[schirm + "/" + hz + "/neu"], v[schirm + "/" + hz + "/uhr"]
                with self.subTest(schirm=schirm, hz=hz):
                    self.assertEqual(tick["ausfall"], 0, tick)
                    # Abweichung je Abstand hoechstens die Ueberlaenge des einen langen Bildes.
                    self.assertLessEqual(tick["groesste"], tick["ueberlang"] + 0.01, tick)
                    self.assertGreater(tick["n"], 1000)
        # Aus der Uhr fallen Blitze aus, sobald ein An-Bild uebersprungen wird
        # (5 und 10 Hz) — eine Luecke von zwei Perioden ist sichtbarer als ein
        # um ein Bild spaeterer Blitz.
        for fall in ("60/5/uhr", "60/10/uhr", "30/10/uhr"):
            self.assertGreater(v[fall]["ausfall"], 0, (fall, v[fall]))
            self.assertGreater(v[fall]["groesste"], v[fall.replace("uhr", "neu")]["groesste"])


if __name__ == "__main__":
    unittest.main()
