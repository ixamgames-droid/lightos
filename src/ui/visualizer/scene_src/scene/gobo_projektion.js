// VIZ-96: Gobo-Projektion mit Verdeckung (Weg B — eigener Shader in r128).
//
// Bis VIZ-96 lag das Gobo-Muster als flache Scheibe auf der Flaeche, die der
// ZENTRALSTRAHL trifft (fixtures/gobo_textures.js). Steht eine Traverse oder
// ein Buehnenkoerper nur teilweise im Strahl, ignorierte das Muster ihn: kein
// Muster auf dem Hindernis, kein Schatten dahinter.
//
// three.js r128 kennt kein `SpotLight.map`. Es rechnet aber fuer jedes
// SCHATTENWERFENDE Spot-Licht schon die projektive Koordinate aus Lichtsicht
// (`vSpotShadowCoord[ i ]`) und multipliziert im Licht-Loop die Verdeckung
// (`getShadow`) auf den Lichtbeitrag. Genau dort haengt dieses Modul EINE
// weitere Multiplikation an: das Gobo-Motiv als Maske. Das Muster faellt damit
// auf alles, was das Licht trifft, und was im Schatten liegt, bleibt dunkel —
// die Verdeckung kommt aus der vorhandenen Shadow-Map, ohne neuen Durchlauf.
//
// Regeln (VIZ-69 / VIZ-PERF):
//   * KEINE Shader-Variante je Gobo. Der Patch ist fuer alle beleuchteten
//     Materialien derselbe (eine Funktion -> ein Programmschluessel-Zusatz);
//     Gobo-Wechsel, Drehung und an/aus schreiben nur `lightosGoboParam`.
//   * Genau EIN zusaetzlicher Sampler (`lightosGoboMap`): ein Atlas mit allen
//     Motiven, unabhaengig von der Zahl der Lichter.
//   * Auf der Stufe Niedrig wird nichts installiert — Shader und Verhalten
//     sind dort exakt wie vor VIZ-96 (flaches Bodenmuster).
//
// Rein (keine Imports): three-Klassen, Chunk-Text und Atlas-Textur reicht der
// Aufrufer herein (scene/spot_pool.js). Node-Tests laden das Modul direkt
// (tests/test_viz96_gobo_projektion.py) und pruefen den Patch gegen die
// echten r128-Chunks aus three_local.js.
"use strict";

/** Raster des Motiv-Atlas (Kacheln). 4 x 2 = 8 Plaetze fuer 7 Motive. */
export const GOBO_ATLAS_SPALTEN = 4;
export const GOBO_ATLAS_ZEILEN = 2;
/** So viele Schatten-Lichter kann `lightosGoboParam` hoechstens bedienen
 *  (= Schatten-Dach der Stufe Maximal, fixtures.js SHADOW_SPOT_HARD_CAP_MAX). */
export const GOBO_MAX_LICHTER = 16;
/** Zusaetzliche Textur-Slots je beleuchtetem Material (der Atlas). */
export const GOBO_SLOTS = 1;
/** Groesster Oeffnungswinkel (rad) eines projizierenden Lichts. */
export const GOBO_MAX_LICHTWINKEL = 1.35;
/** Halbschatten eines projizierenden Lichts: die Blende hat selbst einen
 *  runden Rand (gobo_textures.js#zeichne), der weiche Pool-Verlauf dunkelte
 *  die Motiv-Teile am Rand ab (VIZ-92). */
export const GOBO_HALBSCHATTEN = 0.05;

// ── Shader-Patch ────────────────────────────────────────────────────────────
// Anker: die Schatten-Zeile des SPOT-Blocks in `lights_fragment_begin` (r128).
// Sie steht innerhalb von
//   #if defined( USE_SHADOWMAP ) && ( UNROLLED_LOOP_INDEX < NUM_SPOT_LIGHT_SHADOWS )
// — die Maske erbt diese Bedingung und liegt damit nur auf Lichtern, die eine
// Shadow-Map (und damit `vSpotShadowCoord[ i ]`) haben.
export const GOBO_INCLUDE = '#include <lights_fragment_begin>';
export const GOBO_ANKER =
  'spotLightShadow.shadowRadius, vSpotShadowCoord[ i ] ) : 1.0;';

// ⚠️ `[ i ]` genau so schreiben: three rollt die Licht-Schleife per Textersatz
// aus (/\[\s*i\s*\]/ -> `[ 0 ]`, `[ 1 ]`, ...). Ein nacktes `i` bliebe stehen.
// `w` wird nach unten begrenzt: hinter dem Licht waere die Division sonst
// 0/0 -> NaN, und NaN * 0 (Licht dort ohnehin aus) bliebe NaN.
export const GOBO_GLSL_MASKE = [
  '',
  '\t\t{',
  '\t\t\tvec4 lightosGp = lightosGoboParam[ i ];',
  '\t\t\tvec2 lightosGd = vSpotShadowCoord[ i ].xy / max( vSpotShadowCoord[ i ].w, 0.0001 ) - 0.5;',
  '\t\t\tlightosGd = vec2( lightosGp.y * lightosGd.x - lightosGp.z * lightosGd.y, lightosGp.z * lightosGd.x + lightosGp.y * lightosGd.y ) + 0.5;',
  '\t\t\tfloat lightosGin = step( 0.0, lightosGd.x ) * step( lightosGd.x, 1.0 ) * step( 0.0, lightosGd.y ) * step( lightosGd.y, 1.0 );',
  '\t\t\tfloat lightosGnr = floor( lightosGp.w + 0.5 );',
  '\t\t\tvec2 lightosGk = vec2( mod( lightosGnr, ' + GOBO_ATLAS_SPALTEN + '.0 ), floor( lightosGnr / ' + GOBO_ATLAS_SPALTEN + '.0 ) );',
  '\t\t\tfloat lightosGm = texture2D( lightosGoboMap, ( lightosGk + clamp( lightosGd, 0.002, 0.998 ) ) / vec2( ' + GOBO_ATLAS_SPALTEN + '.0, ' + GOBO_ATLAS_ZEILEN + '.0 ) ).r * lightosGin;',
  '\t\t\tdirectLight.color *= mix( 1.0, lightosGm, lightosGp.x );',
  '\t\t}',
].join('\n');

export const GOBO_GLSL_KOPF = [
  '#if defined( USE_SHADOWMAP ) && NUM_SPOT_LIGHT_SHADOWS > 0',
  'uniform sampler2D lightosGoboMap;',
  'uniform vec4 lightosGoboParam[ NUM_SPOT_LIGHT_SHADOWS ];',
  '#endif',
  '',
].join('\n');

function _genauEinmal(text, teil) {
  const i = text.indexOf(teil);
  return i >= 0 && text.indexOf(teil, i + teil.length) < 0;
}

/** `lights_fragment_begin` um die Gobo-Maske erweitern. Liefert null, wenn der
 *  Anker nicht GENAU einmal vorkommt (anderer three-Stand) — dann wird nichts
 *  gepatcht, und die Szene bleibt beim flachen Bodenmuster. */
export function patchLichtChunk(chunk) {
  if (typeof chunk !== 'string' || !_genauEinmal(chunk, GOBO_ANKER)) return null;
  return chunk.replace(GOBO_ANKER, GOBO_ANKER + GOBO_GLSL_MASKE);
}

/** Fragment-Shader eines beleuchteten Materials (noch mit `#include`-Zeilen,
 *  so wie `onBeforeCompile` ihn bekommt) patchen. null = nicht patchbar. */
export function patchFragmentShader(fragmentShader, chunk) {
  if (typeof fragmentShader !== 'string' || !_genauEinmal(fragmentShader, GOBO_INCLUDE)) return null;
  const gepatcht = patchLichtChunk(chunk);
  if (gepatcht === null) return null;
  return GOBO_GLSL_KOPF + fragmentShader.replace(GOBO_INCLUDE, gepatcht);
}

// ── Atlas ───────────────────────────────────────────────────────────────────
/** Platz (Spalte, Zeile ab UNTEN) der Kachel `nr`. */
export function goboKachelPlatz(nr) {
  return [nr % GOBO_ATLAS_SPALTEN, Math.floor(nr / GOBO_ATLAS_SPALTEN)];
}

/** Alle Motive auf EIN Canvas zeichnen.
 *
 *  @param stile        Stil-Namen in Kachel-Reihenfolge
 *  @param canvasFuer   stil -> Canvas des Motivs (oder null)
 *  @param neuesCanvas  (breite, hoehe) -> leeres Canvas
 *  @param kachelPx     Kantenlaenge einer Kachel
 *  @returns { canvas, index: { stil: kachelNr } } oder null
 *
 *  Zeile 0 liegt UNTEN im Bild: eine CanvasTexture wird mit flipY geladen,
 *  v = 0 ist also die Unterkante — und innerhalb der Kachel steht das Motiv
 *  damit genauso wie in seiner Einzeltextur am Bodenfleck. */
export function baueGoboAtlas(stile, canvasFuer, neuesCanvas, kachelPx) {
  const plaetze = GOBO_ATLAS_SPALTEN * GOBO_ATLAS_ZEILEN;
  if (!stile || !stile.length || stile.length > plaetze || !(kachelPx > 0)) return null;
  const canvas = neuesCanvas(GOBO_ATLAS_SPALTEN * kachelPx, GOBO_ATLAS_ZEILEN * kachelPx);
  const g = canvas && canvas.getContext && canvas.getContext('2d');
  if (!g) return null;
  g.fillStyle = '#000';                       // schwarz = kein Licht
  g.fillRect(0, 0, canvas.width, canvas.height);
  const index = {};
  for (let nr = 0; nr < stile.length; nr++) {
    const motiv = canvasFuer(stile[nr]);
    if (!motiv) return null;
    const [spalte, zeile] = goboKachelPlatz(nr);
    g.drawImage(motiv, spalte * kachelPx, (GOBO_ATLAS_ZEILEN - 1 - zeile) * kachelPx,
                kachelPx, kachelPx);
    index[stile[nr]] = nr;
  }
  return { canvas, index };
}

// ── Abbildung Licht -> Motiv (reine Zahlen) ─────────────────────────────────
/** Oeffnungswinkel des projizierenden Lichts und Massstab des Motivs.
 *
 *  Das Motiv traegt den Kegelrand bei `rand` (GOBO_RAND) seines Radius, die
 *  Motiv-Teile reichen darueber hinaus. Das Licht oeffnet deshalb so weit,
 *  dass die GANZE Kachel in seinen Kegel passt: tan(winkel) = tanKegel / rand
 *  (Massstab 1). Erst am Deckel `maxWinkel` schrumpft stattdessen der
 *  Massstab — der Kegelrand bleibt in jedem Fall auf `rand`.
 *
 *  @param tanKegel  Tangens des halben Oeffnungswinkels des SICHTBAREN Kegels
 */
export function goboLichtWinkel(tanKegel, rand, maxWinkel = GOBO_MAX_LICHTWINKEL) {
  if (!(tanKegel > 0) || !(rand > 0)) return null;
  const winkel = Math.min(maxWinkel, Math.atan(tanKegel / rand));
  return { winkel, skala: rand * Math.tan(winkel) / tanKegel };
}

/** Drehung Schatten-Kamera -> Motiv als [cos, sin].
 *
 *  Die Schattenkamera von three blickt per lookAt mit Welt-Up auf das Ziel —
 *  Pan und Gobo-Drehung des Kopfes stecken NICHT in ihrer Matrix. Hier wird
 *  die fehlende Drehung aus den Achsen berechnet: `ex`/`ez` sind die lokalen
 *  x-/z-Achsen des Kegels (Welt, normiert; sie tragen Kopfstellung UND
 *  Gobo-Winkel `beam.rotation.y`), `R`/`U` Rechts- und Hoch-Achse der
 *  Schattenkamera. Uebergeben werden die vier Skalarprodukte.
 *
 *  Herleitung: ein Randstrahl bei Umfangswinkel th liegt im Kamerabild bei
 *  d ~ B * (sin th, cos th) mit B = [[ex.R, ez.R], [ex.U, ez.U]]; im Motiv
 *  gehoert er nach (sin th, -cos th) (gobo_textures.js: Canvas-Winkel
 *  pi/2 - th, v nach oben). Also Motiv = diag(1,-1) * B^T * d — eine reine
 *  Drehung, weil (ex, ez) und (R, U) entgegengesetzt orientiert sind. Beide
 *  Schaetzungen je Eintrag werden gemittelt (Kegelachse und Blickrichtung
 *  weichen um den Linsen-Vorsprung minimal ab).
 */
export function goboDrehung(exR, exU, ezR, ezU) {
  const c = (exR - ezU) / 2, s = -(exU + ezR) / 2;
  const l = Math.hypot(c, s);
  if (!(l > 1e-9)) return [1, 0];
  return [c / l, s / l];
}

// ── Zustand + Installation ──────────────────────────────────────────────────
let _aktiv = false;
let _index = {};
let _gepatcht = 0;          // wie oft lief der Hook (Diagnose)
let _chunk = null;
const _uniforms = {
  lightosGoboMap: { value: null },
  lightosGoboParam: { value: [] },
};

// EINE Funktion fuer alle Materialien: three nimmt `onBeforeCompile.toString()`
// in den Programmschluessel — gleiche Funktion, gleiche Programme wie vorher.
function lightosGoboHook(shader) {
  const fs = patchFragmentShader(shader.fragmentShader, _chunk);
  if (fs === null) return;
  shader.fragmentShader = fs;
  shader.uniforms.lightosGoboMap = _uniforms.lightosGoboMap;
  shader.uniforms.lightosGoboParam = _uniforms.lightosGoboParam;
  _gepatcht += 1;
}

/** Projektion einschalten — EINMAL beim Start, vor dem ersten Bild.
 *
 *  @param opt.materialKlassen  beleuchtete Materialklassen (MeshStandardMaterial)
 *  @param opt.lichtChunk       THREE.ShaderChunk.lights_fragment_begin
 *  @param opt.Vector4          THREE.Vector4
 *  @param opt.atlas            Textur des Motiv-Atlas
 *  @param opt.index            { stil: kachelNr }
 *  @returns true, wenn installiert. false laesst alles wie vor VIZ-96.
 */
export function installGoboProjektion(opt) {
  if (_aktiv) return true;
  const o = opt || {};
  if (!o.atlas || !o.Vector4 || !o.materialKlassen || !o.materialKlassen.length) return false;
  if (patchLichtChunk(o.lichtChunk) === null) return false;
  _chunk = o.lichtChunk;
  _index = Object.assign({}, o.index);
  _uniforms.lightosGoboMap.value = o.atlas;
  const werte = [];
  for (let i = 0; i < GOBO_MAX_LICHTER; i++) werte.push(new o.Vector4(0, 1, 0, 0));
  _uniforms.lightosGoboParam.value = werte;
  for (const klasse of o.materialKlassen) klasse.prototype.onBeforeCompile = lightosGoboHook;
  _aktiv = true;
  return true;
}

export function goboProjektionAktiv() { return _aktiv; }

/** Kachel-Nummer eines Stils, -1 = kein Motiv (offen/unbekannt). */
export function goboKachel(stil) {
  const nr = _index[String(stil || '')];
  return (typeof nr === 'number') ? nr : -1;
}

/** Maske des Schatten-Lichts `i` setzen (nur Uniform-Werte).
 *  @param an     0..1 — Anteil der Maske (0 = Licht unveraendert)
 *  @param cs,sn  cos/sin der Drehung, bereits mit dem Massstab multipliziert
 */
export function setzeGoboLicht(i, an, cs, sn, kachel) {
  const v = _uniforms.lightosGoboParam.value[i];
  if (!v) return false;
  v.set(an, cs, sn, kachel);
  return true;
}

export function loescheGoboLicht(i) {
  const v = _uniforms.lightosGoboParam.value[i];
  if (v && v.x !== 0) v.set(0, 1, 0, 0);
}

/** Test-/Diagnose-Seam. */
export function goboProjektionInfo() {
  return {
    aktiv: _aktiv,
    slots: _aktiv ? GOBO_SLOTS : 0,
    hookLaeufe: _gepatcht,
    spalten: GOBO_ATLAS_SPALTEN,
    zeilen: GOBO_ATLAS_ZEILEN,
    index: Object.assign({}, _index),
    param: _uniforms.lightosGoboParam.value.map(v => [v.x, v.y, v.z, v.w]),
  };
}
