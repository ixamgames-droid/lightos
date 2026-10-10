// VIZ-72: Spot-Pool — eine FESTE Zahl echter SpotLights fuer die hellsten Strahlen.
//
// Bis VIZ-72 trug jedes Strahl-Geraet (PAR, Strobe, Moving Head, ...) sein
// eigenes THREE.SpotLight in der Szene. In three.js r128 rechnet JEDES
// beleuchtete Material in JEDEM Pixel alle sichtbaren Lichter durch (die
// Lichtschleife ist im Shader ausgerollt). Gemessen an der Buehnen-Show
// (80 Geraete, davon 68 mit Strahl; offscreen, Intel UHD 630, 1280x720,
// Stufe Hoch, Median je Bild):
//
//     68 SpotLights (main)                54,6 ms
//     nur 8 SpotLights (Rest entfernt)    19,8 ms   (-64 %)
//     0 SpotLights                        16,0 ms
//     ohne Kegel                          51,2 ms   (-6 %)
//     Buehne ausgeblendet                 38,4 ms   (Fuellrate x 68 Lichter)
//
// Der Lichterzahl-Posten ist also der Hebel, nicht Draw-Calls oder Kegel.
//
// Deshalb jetzt: jedes Geraet behaelt `f.spot` als PARAMETER-Traeger (Farbe,
// Intensitaet, Winkel, Halbschatten, Ziel — alle bisherigen Schreiber in
// builders.js/optics.js bleiben unveraendert), haengt ihn aber NICHT mehr in
// die Szene. Echte Lichter gibt es nur noch im Pool; `syncSpotPool()` vergibt
// sie vor jedem Bild an die hellsten sichtbaren Strahlen und kopiert deren
// Parameter hinein. Alle uebrigen Strahlen zeigen weiter Kegel, Bodenfleck und
// leuchtende Linse — sie beleuchten nur die Umgebung nicht mehr selbst.
//
// ★ VIZ-69-Lehre: die Zahl der Lichter und der Schatten-Lichter gehoert in r128
// zum Programmschluessel JEDES beleuchteten Materials. Der Pool aendert seine
// Groesse deshalb NUR beim Patchen (wie vorher das Hinzufuegen eines Geraets),
// nie wegen DMX: ein Pool-Licht wird nie unsichtbar geschaltet, ein
// unbenutztes leuchtet mit Intensitaet 0. Die Vergabe selbst aendert nur
// Uniforms (Farbe, Lage, Winkel) — keine Neukompilierung.
//
// Groesse: min(Stufe `realLights` aus quality_tiers.js, Zahl der Strahl-Geraete).
// Ein kleines Rig (<= Poolgroesse) hat damit genau so viele Lichter wie vorher,
// jedes Geraet bekommt sein Licht — Bild und Kosten wie bisher.
//
// Ruhe bei Wellen (Review M1): eine Hysterese gegen die AKTUELLE Helligkeit
// reicht nicht — bei einer Dimmer-Welle wird jeder Halter laufend dunkler,
// irgendwann ist ein anderer 1,25-mal so hell, und die Lichter sprangen
// gemessen 2-4-mal je Bild (68 PARs, Sinuswelle: 133 Wechsel und 53
// Schattendurchlaeufe in 60 Bildern). Jetzt drei Bremsen:
//   * Ein LEUCHTENDER Halter zaehlt mit seinem Spitzenwert, der nur langsam
//     abklingt (Halbwertszeit SPITZE_HALBWERT_MS). In einer Welle haben alle
//     Geraete denselben Spitzenwert — keiner ist 1,25-mal so hell wie ein
//     Halter im Wellental, die Vergabe bleibt stehen.
//   * Ein leuchtender Halter behaelt sein Licht mindestens MIN_HALT_MS.
//   * Verdraengt wird hoechstens alle WECHSEL_ABSTAND_MS, dann aber alles
//     Faellige im selben Bild: jeder Wechsel zeichnet ALLE Shadow-Maps neu
//     (ein Durchlauf je Bild, nicht je Licht) — gebuendelt kostet ein
//     Lauflicht-Schritt einen Durchlauf statt acht. Das deckelt die
//     Schattendurchlaeufe durch Wechsel bei 1000/WECHSEL_ABSTAND_MS je Sekunde.
// Ein Halter, der SCHLAGARTIG ausgeht (Lauflicht, Blackout), ist sofort frei
// und gibt sein Licht beim naechsten erlaubten Wechsel ab. Wer allmaehlich
// auf 0 sinkt (Wellental), zaehlt erst nach DUNKEL_GNADE_MS als dunkel.
// Gemessen (simulierte Uhr, 30 Bilder/s, 68 PARs, 10 s; Wechsel/Schatten-
// durchlaeufe vorher -> nachher): Welle 1 s 476/297 -> 1/1, Welle 2 s
// 260/143 -> 0/0, Welle 5 s 108/67 -> 24/20, Welle 10 s 54/34 -> 29/18;
// Lauflicht 250-1000 ms unveraendert (jeder Schritt bekommt seine Lichter).
// Preis: ein Lauflicht mit 150-ms-Schritten deckt nur noch ~40 %.
// Gleich hell (statisches Vollbild): die Lichter gehen raeumlich verteilt an
// die Geraete, die am weitesten von den schon beleuchtenden entfernt sind
// (Review M2) — vorher bekamen die kleinsten fids alle Lichter, also meist eine
// zusammenhaengende Gruppe auf einer Seite.
import * as THREE from '../three/three.js';
import { scene, isLowSpec, tierSettings } from './renderer.js';
import { requestShadowUpdate } from './shadow_update.js';
import { requestRender } from './render_loop.js';
// VIZ-96: Gobo-Projektion — reine Rechnung/Shader-Patch in gobo_projektion.js,
// Motive und Kegelrand aus gobo_textures.js.
import { goboTexture, GOBO_STILE, GOBO_RAND, GROESSE as GOBO_KACHEL_PX } from '../fixtures/gobo_textures.js';
import {
  installGoboProjektion, baueGoboAtlas, goboProjektionAktiv, goboKachel, goboLichtWinkel,
  goboDrehung, setzeGoboLicht, loescheGoboLicht, GOBO_HALBSCHATTEN, GOBO_MAX_LICHTER,
} from './gobo_projektion.js';

export const HYSTERESE = 1.25;
export const MIN_HALT_MS = 400;
export const WECHSEL_ABSTAND_MS = 200;
export const SPITZE_HALBWERT_MS = 8000;
export const DUNKEL_GNADE_MS = 250;
// "Schlagartig aus": im Bild davor noch mindestens so viel vom Spitzenwert.
const SCHLAGARTIG = 0.25;
// Ohne Stufen-Angabe (alte Tabelle) — der Wert der Stufe Hoch.
const POOL_STANDARD = 8;

// ── VIZ-92: das Licht kommt aus der LINSE, nicht aus dem Gehaeuse ──────────
// Bis VIZ-92 sass jedes Pool-Licht dort, wo frueher das Geraete-Licht hing:
// `spot.position` (r128-Vorgabe 0, 1, 0) im Koordinatensystem der Gruppe —
// also einen Meter UEBER dem Sockel, unabhaengig von Pan/Tilt. Der Strahl lief
// damit erst durch Sockel, Buegel und Kopf des eigenen Geraets: unter der Linse
// lag dessen Schatten (die "Fledermaus" aus Buegel und Kopf an der Rueckwand,
// dunkle Flecken neben den Spidern in der Buehnen-Show).
// Jetzt: Ursprung = Spitze des Kegels (dort sitzt die Linse bzw. der
// Lichtaustritt, s. fixtures.js#createBeamCone), ein Stueck in
// Strahlrichtung vorgeschoben; und die Schattenkamera beginnt erst nach
// SCHATTEN_NEAR — das eigene Gehaeuse (Kopf-Trommel ~0,1 m, PAR-Dose ~0,15 m,
// Sockel eines stehenden Kopfes ~0,35 m vor der Kopfmitte) landet nicht in der
// eigenen Shadow-Map. Fremde Koerper weiter weg werfen weiter Schatten.
export const LINSEN_VORSPRUNG = 0.02;
export const SCHATTEN_NEAR = 0.5;
const _apex = new THREE.Vector3(), _basis = new THREE.Vector3();

/** Lichtursprung eines Geraets (Welt) nach `out`; ohne Kegel wie bisher. */
export function lichtUrsprung(f, out) {
  const beam = f && f.beam;
  const p = beam && beam.geometry && beam.geometry.parameters;
  if (p && p.height > 0) {
    beam.updateWorldMatrix(true, false);
    beam.localToWorld(_apex.set(0, p.height / 2, 0));
    beam.localToWorld(_basis.set(0, -p.height / 2, 0));
    _basis.sub(_apex);
    const l = _basis.length();
    out.copy(_apex);
    if (l > 1e-9) out.addScaledVector(_basis, LINSEN_VORSPRUNG / l);
    return out;
  }
  f.group.updateWorldMatrix(true, false);
  return out.copy(f.spot.position).applyMatrix4(f.group.matrixWorld);
}

// ── VIZ-96: Gobo-Projektion an den Pool gekoppelt ──────────────────────────
// Ein Geraet, das gerade ein Pool-Licht MIT Schatten haelt und ein Gobo zeigt,
// projiziert echt: das Pool-Licht traegt das Motiv als Maske (Muster auf
// Hindernissen, Schatten dahinter), und die flache Bodenmuster-Scheibe des
// Geraets wird ausgeblendet. Alle anderen Gobo-Geraete behalten das
// Bodenmuster wie seit VIZ-83/VIZ-92.
//
// Installiert wird EINMAL beim Laden dieses Moduls, vor dem ersten Bild, und
// nur wenn die Stufe es will (quality_tiers.js `goboProjektion`: Niedrig aus).
// Scheitert etwas (kein Canvas, anderer three-Stand), bleibt alles beim
// Bodenmuster — goboProjektionAktiv() ist dann false.
function _starteGoboProjektion() {
  if (!(tierSettings && tierSettings.goboProjektion)) return false;
  try {
    const atlas = baueGoboAtlas(
      GOBO_STILE,
      (stil) => { const t = goboTexture(stil); return t ? t.image : null; },
      (b, h) => { const c = document.createElement('canvas'); c.width = b; c.height = h; return c; },
      GOBO_KACHEL_PX);
    if (!atlas) return false;
    // Ohne Mipmaps: projektive Koordinaten springen an Koerperkanten, die
    // kleinste Mip-Stufe zoege dort graue Saeume (und mischte Nachbar-Kacheln).
    const tex = new THREE.CanvasTexture(atlas.canvas);
    tex.generateMipmaps = false;
    tex.minFilter = THREE.LinearFilter;
    tex.magFilter = THREE.LinearFilter;
    tex.needsUpdate = true;
    return installGoboProjektion({
      materialKlassen: [THREE.MeshStandardMaterial],
      lichtChunk: THREE.ShaderChunk.lights_fragment_begin,
      Vector4: THREE.Vector4,
      atlas: tex,
      index: atlas.index,
    });
  } catch (e) {
    return false;
  }
}
_starteGoboProjektion();

const _projiziert = new Set();   // Geraete, deren Pool-Licht gerade das Gobo traegt
const _projNeu = new Set();
const _blick = new THREE.Matrix4();
const _hoch = new THREE.Vector3(0, 1, 0);

function _bodenmuster(f, zeigen) {
  f.goboProjiziert = !zeigen;
  // Ueber die Ebenen-Maske, nicht ueber `visible`/Deckkraft: die schreibt
  // builders.js#applyGenericColor bei jedem DMX-Update neu.
  if (f.floorSpot) {
    if (zeigen) f.floorSpot.layers.enable(0); else f.floorSpot.layers.disable(0);
  }
}

function _projektionAbgleichen() {
  for (const f of _projiziert) if (!_projNeu.has(f)) _bodenmuster(f, true);
  for (const f of _projNeu) if (!_projiziert.has(f)) _bodenmuster(f, false);
  _projiziert.clear();
  for (const f of _projNeu) _projiziert.add(f);
  _projNeu.clear();
}

// Pool-Licht `i` (Slot p) projiziert das Gobo von Geraet f. Liefert false,
// wenn es nicht geht (Licht ohne Schatten, kein Motiv, kein Kegel).
// Der Musterwinkel kommt aus der Welt-Matrix des Kegels — sie traegt die
// ANGEZEIGTE Kopfstellung und Gobo-Drehung (VIZ-92: geglaettet je Bild).
function _goboProjizieren(i, p, f) {
  const l = p.licht;
  if (i >= GOBO_MAX_LICHTER || !l.castShadow) return false;
  const kachel = goboKachel(f.lastGobo);
  const beam = f.beam;
  const gp = beam && beam.geometry && beam.geometry.parameters;
  if (kachel < 0 || !gp || !(gp.radius > 0) || !(gp.height > 0)) return false;
  const e = beam.matrixWorld.elements;     // von lichtUrsprung() gerade aktualisiert
  const lx = Math.hypot(e[0], e[1], e[2]);
  const ly = Math.hypot(e[4], e[5], e[6]);
  const lz = Math.hypot(e[8], e[9], e[10]);
  if (!(lx > 1e-9) || !(ly > 1e-9) || !(lz > 1e-9)) return false;
  // Rand des SICHTBAREN Kegels (Zoom/Iris in x/z, Kegellaenge in y) — derselbe
  // Rand, auf den alignGoboFloor das Bodenmuster legt: beim Wechsel zwischen
  // Scheibe und Projektion springt die Groesse des Musters nicht.
  const optik = goboLichtWinkel((gp.radius * lx) / (gp.height * ly), GOBO_RAND);
  if (!optik) return false;
  // Achsen der Schattenkamera, wie three sie baut (SpotLightShadow:
  // Position des Lichts, lookAt aufs Ziel, Welt-Up).
  _blick.lookAt(l.position, p.ziel.position, _hoch);
  const b = _blick.elements;               // Spalte 0 = rechts, Spalte 1 = hoch
  const d = goboDrehung(
    (e[0] * b[0] + e[1] * b[1] + e[2] * b[2]) / lx,
    (e[0] * b[4] + e[1] * b[5] + e[2] * b[6]) / lx,
    (e[8] * b[0] + e[9] * b[1] + e[10] * b[2]) / lz,
    (e[8] * b[4] + e[9] * b[5] + e[10] * b[6]) / lz);
  l.angle = optik.winkel;
  l.penumbra = GOBO_HALBSCHATTEN;
  setzeGoboLicht(i, 1, optik.skala * d[0], optik.skala * d[1], kachel);
  return true;
}

const _pool = [];          // [{ licht, ziel, fid }]
let _fixtures = null;      // state.fixtures (per initSpotPool gesetzt, kein Import-Zyklus)
let _vergaben = 0;         // Zaehler: wie oft wechselte ein Licht den Besitzer
let _schattenSoll = 0;

/** Poolgroesse der aktiven Qualitaetsstufe (echte Lichter hoechstens). */
export function poolDach() {
  const n = tierSettings && tierSettings.realLights;
  return (typeof n === 'number' && n > 0) ? n : POOL_STANDARD;
}

export function initSpotPool(fixtures) { _fixtures = fixtures; }

function _neuesLicht() {
  // Dieselben Grundwerte wie das Geraete-Licht in fixtures.js#addFixture; alles,
  // was je Geraet anders ist, kopiert syncSpotPool() ohnehin hinein.
  const licht = new THREE.SpotLight(0xffffff, 0, 25, Math.PI / 10 * 1.2, 0.6, 1.0);
  const res = isLowSpec ? 256 : 512;
  licht.shadow.mapSize.width = res;
  licht.shadow.mapSize.height = res;
  licht.castShadow = false;
  licht.shadow.camera.near = SCHATTEN_NEAR;   // VIZ-92: eigenes Gehaeuse ausblenden
  licht.userData.spotPool = true;
  const ziel = new THREE.Object3D();
  ziel.userData.spotPool = true;
  scene.add(ziel);
  licht.target = ziel;
  scene.add(licht);
  return { licht, ziel, fid: null, veraltet: false };
}

/**
 * Poolgroesse und Schatten-Vergabe setzen. NUR beim Patchen rufen
 * (fixtures.js#syncSpotShadowBudget) — jede Aenderung hier kompiliert die
 * beleuchteten Shader neu.
 *
 * @param strahlGeraete  Zahl der Geraete mit `f.spot`
 * @param schattenBudget wie viele Lichter hoechstens Schatten werfen duerfen
 * @returns true, wenn sich Zahl oder Schatten geaendert haben
 */
export function resizeSpotPool(strahlGeraete, schattenBudget) {
  const soll = Math.max(0, Math.min(poolDach(), strahlGeraete | 0));
  let geaendert = false;
  while (_pool.length < soll) { _pool.push(_neuesLicht()); geaendert = true; }
  while (_pool.length > soll) {
    const p = _pool.pop();
    scene.remove(p.licht);
    scene.remove(p.ziel);
    if (p.licht.shadow && typeof p.licht.shadow.dispose === 'function') p.licht.shadow.dispose();
    geaendert = true;
  }
  _schattenSoll = Math.min(_pool.length, Math.max(0, schattenBudget | 0));
  for (let i = 0; i < _pool.length; i++) {
    const will = i < _schattenSoll;
    if (_pool[i].licht.castShadow !== will) { _pool[i].licht.castShadow = will; geaendert = true; }
  }
  if (geaendert) requestShadowUpdate();
  return geaendert;
}

// Wie hell ist der Strahl dieses Geraets gerade (0 = traegt nichts bei)?
// Gleiches Mass wie builders.js#applyGenericColor (Intensitaet x hellster
// Farbkanal); ein ausgeblendetes Geraet (2D-Ansicht) zaehlt als dunkel —
// vorher hing sein Licht an der unsichtbaren Gruppe und leuchtete nicht.
export function strahlHelligkeit(f) {
  const s = f && f.spot;
  if (!s || !s.visible || !(s.intensity > 0)) return 0;
  if (f.group && !f.group.visible) return 0;
  const c = s.color;
  return s.intensity * Math.max(c.r, c.g, c.b);
}

const _kand = [];
const _belegt = new Set();
const _v = new THREE.Vector3();

function _abstand2(a, b) {
  const dx = a.x - b.x, dy = a.y - b.y, dz = a.z - b.z;
  return dx * dx + dy * dy + dz * dz;
}

// Aus _kand[k..] (absteigend sortiert) den naechsten Kandidaten waehlen: unter
// den GLEICH hellen den, der am weitesten von den schon vergebenen Lichtern
// entfernt ist (Review M2). Tauscht ihn an Stelle k. Ohne `lage` bleibt die
// Sortierung (gleich hell: kleinere fid).
function _waehle(k, neu, hell, lage) {
  if (!lage || k + 1 >= _kand.length) return;
  const h = hell.get(_kand[k]);
  let ende = k + 1;
  while (ende < _kand.length && hell.get(_kand[ende]) === h) ende += 1;
  if (ende - k < 2) return;
  let best = k, bestD = -1;
  for (let j = k; j < ende; j++) {
    const pj = lage(_kand[j]);
    if (!pj) continue;
    let d = Infinity;
    for (let i = 0; i < neu.length; i++) {
      if (neu[i] === null) continue;
      const pi = lage(neu[i]);
      if (pi) d = Math.min(d, _abstand2(pi, pj));
    }
    if (d > bestD) { bestD = d; best = j; }   // gleich weit: kleinere fid (Sortierung)
  }
  if (best !== k) { const t = _kand[k]; _kand[k] = _kand[best]; _kand[best] = t; }
}

/**
 * Vergabe nach Helligkeit, mit Hysterese. Rein ueber Zahlen (Test-Seam):
 * `halter` = aktuelle fid je Slot (null = frei), `hell` = Map fid -> Helligkeit.
 * Liefert die neue fid je Slot.
 *
 * `opt` (alles optional; ohne opt gilt die nackte Hysterese-Regel):
 *   spitze     Map fid -> Spitzenwert; damit zaehlt ein HALTER (nie
 *              ein Herausforderer) — Ruhe bei Wellen. 0 = dunkel/frei.
 *   seit, jetzt  Vergabezeit je Slot (ms) und jetzt; ein leuchtender Halter
 *              ist erst nach minHalt ms verdraengbar (ein dunkler sofort).
 *   minHalt    Mindesthaltezeit (ms), Standard MIN_HALT_MS (nur mit seit).
 *   wechselErlaubt  false = in diesem Bild nicht verdraengen (Abstand der
 *              Wechsel-Bilder); freie Slots fuellen sich trotzdem.
 *   lage       fid -> {x,y,z}: gleich helle Kandidaten raeumlich verteilen.
 *   info       Objekt; bekommt `ausstehend` = true, wenn ein Wechsel nur
 *              aufgeschoben ist (Haltezeit, Wechselabstand, abklingende
 *              Spitze) — der Aufrufer fordert dann spaeter ein Bild an.
 */
export function vergeben(halter, hell, hysterese = HYSTERESE, opt = null) {
  const o = opt || {};
  const spitze = o.spitze || null;
  const seit = o.seit || null;
  const jetzt = o.jetzt || 0;
  const minHalt = (typeof o.minHalt === 'number') ? o.minHalt : MIN_HALT_MS;
  const wechselErlaubt = o.wechselErlaubt !== false;
  const lage = o.lage || null;
  if (o.info) o.info.ausstehend = false;
  const staerke = (fid) => {
    const h = hell.get(fid) || 0;
    if (!spitze) return h;
    const s = spitze.get(fid) || 0;
    return s > h ? s : h;
  };
  const neu = halter.slice();
  const vergeben_ = _belegt;
  vergeben_.clear();
  // 1) Verschwundene Halter geben ab. Ein DUNKLER Halter behaelt seinen Slot
  //    vorerst — wird er wieder hell, steht sein Licht noch am selben Platz und
  //    die Shadow-Map muss nicht neu (Farb-/Dimmerwechsel kosten keinen
  //    Schattendurchlauf, VIZ-69). Gebraucht wird der Slot erst, wenn ein
  //    heller Strahl keinen freien mehr findet (Schritt 3).
  for (let i = 0; i < neu.length; i++) {
    const fid = neu[i];
    if (fid === null || !hell.has(fid) || vergeben_.has(fid)) neu[i] = null;
    else vergeben_.add(fid);
  }
  // 2) Leuchtende Kandidaten ohne Slot, hellste zuerst (gleich hell: kleinere fid).
  _kand.length = 0;
  for (const [fid, h] of hell) if (h > 0 && !vergeben_.has(fid)) _kand.push(fid);
  _kand.sort((a, b) => (hell.get(b) - hell.get(a)) || (a - b));
  let k = 0;
  // 2b) Freie Slots sofort fuellen (kein Halter verliert etwas).
  for (let i = 0; i < neu.length && k < _kand.length; i++) {
    if (neu[i] === null) { _waehle(k, neu, hell, lage); neu[i] = _kand[k++]; }
  }
  // 3) Verdraengen: der hellste Uebrige gegen den schwaechsten verdraengbaren
  //    Halter — nur mit Abstand (Hysterese gegen dessen Spitzenwert), ein
  //    leuchtender erst nach der Mindesthaltezeit. Ein dunkler Halter
  //    (Staerke 0) verliert gegen jeden leuchtenden Kandidaten.
  while (k < _kand.length) {
    let schwach = -1, schwachS = 0, gesperrt = false;
    for (let i = 0; i < neu.length; i++) {
      const si = staerke(neu[i]);
      if (si > 0 && seit && seit[i] != null && jetzt - seit[i] < minHalt) {
        gesperrt = true;
        continue;
      }
      if (schwach < 0 || si < schwachS) { schwach = i; schwachS = si; }
    }
    const herausforderer = hell.get(_kand[k]);
    if (schwach < 0 || !(herausforderer > schwachS * hysterese)) {
      // Kein Wechsel jetzt. Aufgeschoben (statt endgueltig abgelehnt), wenn
      // der Herausforderer einen Halter schon nach dessen AKTUELLER Helligkeit
      // schluege — Haltezeit oder abklingende Spitze geben ihm den Platz bald.
      if (o.info && (gesperrt || spitze)) {
        for (let i = 0; i < neu.length; i++) {
          if (herausforderer > (hell.get(neu[i]) || 0) * hysterese) { o.info.ausstehend = true; break; }
        }
      }
      break;   // _kand ist absteigend sortiert — kein Weiterer schafft es
    }
    if (!wechselErlaubt) { if (o.info) o.info.ausstehend = true; break; }
    neu[schwach] = null;               // der Verdraengte zaehlt fuer die Verteilung nicht
    _waehle(k, neu, hell, lage);
    neu[schwach] = _kand[k++];
    if (seit) seit[schwach] = jetzt;   // frisch vergeben: wieder gesperrt
  }
  return neu;
}

const _hell = new Map();
const _spitze = new Map();   // fid -> abklingender Spitzenwert (nur Pool-Bewertung)
const _seit = [];            // Vergabezeit je Slot (ms)
const _dunkelSeit = new Map();   // fid -> seit wann ganz dunkel (ms)
const _vorher = new Map();       // fid -> Helligkeit im Bild davor
let _letzterWechsel = -Infinity; // Zeit des letzten Bildes mit Verdraengung
const _info = { ausstehend: false };
let _uhr = null;                  // Test-Seam: simulierte Zeit statt performance.now()

/** Test-Seam: eigene Uhr (ms) fuer syncSpotPool; null = performance.now(). */
export function setSpotPoolUhr(fn) {
  _uhr = (typeof fn === 'function') ? fn : null;
  _letzteZeit = -1;
  _letzterWechsel = -Infinity;
  for (let i = 0; i < _seit.length; i++) _seit[i] = null;
}
let _letzteZeit = -1;
let _warteTimer = 0;
const WARTE_MS = 100;

function _lage(fid) {
  const f = _fixtures && _fixtures[fid];
  if (!f || !f.group) return null;
  return f.group.getWorldPosition(f._poolLage || (f._poolLage = new THREE.Vector3()));
}

/** Vor JEDEM Bild (app.js#renderFrame) — vor prepareShadowMap. */
export function syncSpotPool() {
  if (!_pool.length || !_fixtures) {
    if (_projiziert.size) _projektionAbgleichen();   // VIZ-96: Bodenmuster zurueck
    return;
  }
  const gobo = goboProjektionAktiv();
  _hell.clear();
  for (const fid in _fixtures) {
    const f = _fixtures[fid];
    if (f && f.spot) _hell.set(Number(fid), strahlHelligkeit(f));
  }
  // Spitzenwerte nachfuehren: steigen sofort, klingen mit der Zeit ab.
  // Schlagartig aus (Lauflicht, Blackout) -> sofort 0; allmaehlich auf 0
  // (Wellental) -> erst nach DUNKEL_GNADE_MS.
  const jetzt = _uhr ? _uhr() : performance.now();
  const dt = _letzteZeit < 0 ? 0 : Math.max(0, jetzt - _letzteZeit);
  _letzteZeit = jetzt;
  const abkling = Math.pow(0.5, dt / SPITZE_HALBWERT_MS);
  for (const [fid, h] of _hell) {
    const vorher = _vorher.get(fid) || 0;
    _vorher.set(fid, h);
    let sp = (_spitze.get(fid) || 0) * abkling;
    if (h > 0) {
      _dunkelSeit.delete(fid);
      if (h > sp) sp = h;
    } else if (sp > 0) {
      if (vorher >= sp * SCHLAGARTIG) sp = 0;
      else {
        const d = _dunkelSeit.get(fid);
        if (d === undefined) _dunkelSeit.set(fid, jetzt);
        else if (jetzt - d >= DUNKEL_GNADE_MS) sp = 0;
      }
    }
    _spitze.set(fid, sp);
  }
  if (_spitze.size > _hell.size) {
    for (const fid of _spitze.keys()) {
      if (!_hell.has(fid)) { _spitze.delete(fid); _dunkelSeit.delete(fid); _vorher.delete(fid); }
    }
  }
  const alt = _pool.map(p => p.fid);
  while (_seit.length < _pool.length) _seit.push(null);
  _seit.length = _pool.length;
  const neu = vergeben(alt, _hell, HYSTERESE, {
    spitze: _spitze, seit: _seit, jetzt, lage: _lage, info: _info,
    wechselErlaubt: jetzt - _letzterWechsel >= WECHSEL_ABSTAND_MS,
  });
  // Aufgeschobener Wechsel: spaeter noch ein Bild anfordern, auch wenn sonst
  // nichts passiert (Bilder entstehen nur auf Anforderung) — eins je WARTE_MS
  // reicht, kein Dauer-Rendern.
  if (_info.ausstehend && !_warteTimer) {
    _warteTimer = setTimeout(() => { _warteTimer = 0; requestRender(); }, WARTE_MS);
  }
  let verdraengt = false;
  for (let i = 0; i < _pool.length; i++) {
    const p = _pool[i];
    const fid = neu[i];
    if (fid !== p.fid) {
      if (p.fid !== null) verdraengt = true;
      p.fid = fid;
      _vergaben += 1;
      _seit[i] = jetzt;
    }
    const l = p.licht;
    const f = (fid !== null) ? _fixtures[fid] : null;
    const s = f && f.spot;
    // Ein dunkler Halter (Schritt 1 in vergeben) behaelt Lage und Winkel, nur
    // seine Intensitaet ist 0 — auch in der 2D-Ansicht (Gruppe unsichtbar).
    const leuchtet = !!s && _hell.get(fid) > 0;
    if (s) {
      // Ziel wie beim Geraete-Licht (f.spotTarget); der Ursprung sitzt seit
      // VIZ-92 an der Linse (lichtUrsprung, s. o.) statt 1 m ueber dem Sockel.
      lichtUrsprung(f, l.position);
      const t = s.target;
      if (t) {
        if (t.parent === scene || !t.parent) p.ziel.position.copy(t.position);
        else { t.getWorldPosition(_v); p.ziel.position.copy(_v); }
      }
      l.color.copy(s.color);
      l.intensity = leuchtet ? s.intensity : 0;
      l.angle = s.angle;
      l.penumbra = s.penumbra;
      l.distance = s.distance;
      l.decay = s.decay;
    } else {
      l.intensity = 0;
    }
    // VIZ-96: Gobo-Halter. Mit Schatten-Licht traegt das Licht das Muster als
    // Maske; ohne (Licht jenseits des Schatten-Budgets) laesst es sich nicht
    // maskieren — dann bleibt es dunkel wie seit VIZ-92 (sonst laege wieder der
    // volle runde Lichtkreis neben dem Bodenmuster).
    let projiziert = false;
    if (gobo && s && f.goboAktiv) {
      if (leuchtet && _goboProjizieren(i, p, f)) { projiziert = true; _projNeu.add(f); }
      else l.intensity = 0;
    }
    if (gobo && !projiziert) loescheGoboLicht(i);
    // Dunkles Pool-Licht: seine Shadow-Map nicht neu zeichnen (es traegt nichts
    // bei). Lief waehrenddessen ein Schattendurchlauf, ist seine Map veraltet
    // (noteShadowPass) — dann wird sie beim Wiederaufleuchten erneuert.
    const aktiv = leuchtet && l.intensity > 0;
    if (l.castShadow && l.shadow.autoUpdate !== aktiv) {
      l.shadow.autoUpdate = aktiv;
      if (aktiv && p.veraltet) { l.shadow.needsUpdate = true; requestShadowUpdate(); }
      p.veraltet = false;
    }
  }
  if (verdraengt) _letzterWechsel = jetzt;
  if (gobo) _projektionAbgleichen();
}

/** Nach prepareShadowMap: `neu` = in diesem Bild entstehen die Shadow-Maps neu.
 *  Dunkle Pool-Lichter zeichnen dabei nicht mit — ihre Map ist danach alt. */
export function noteShadowPass(neu) {
  if (!neu) return;
  for (const p of _pool) {
    if (p.licht.castShadow && p.licht.shadow.autoUpdate === false) p.veraltet = true;
  }
}

/** Test-/Diagnose-Seam: Zustand des Pools als Zahlen. */
export function spotPoolInfo() {
  let schatten = 0, hell = 0;
  for (const p of _pool) {
    if (p.licht.castShadow) schatten += 1;
    if (p.licht.intensity > 0) hell += 1;
  }
  return {
    dach: poolDach(),
    groesse: _pool.length,
    schatten,
    leuchtend: hell,
    vergaben: _vergaben,
    halter: _pool.map(p => p.fid),
    hysterese: HYSTERESE,
    minHaltMs: MIN_HALT_MS,
    wechselAbstandMs: WECHSEL_ABSTAND_MS,
    ausstehend: _info.ausstehend,
    // VIZ-96: fids, deren Pool-Licht gerade das Gobo projiziert.
    goboProjiziert: _pool.filter(p => p.fid !== null && _fixtures && _fixtures[p.fid]
      && _projiziert.has(_fixtures[p.fid])).map(p => p.fid),
  };
}

/** Test-/Benchmark-Seam: die echten Lichter selbst. */
export function spotPoolLights() {
  return _pool.map(p => p.licht);
}
