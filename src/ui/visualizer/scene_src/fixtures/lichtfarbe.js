// VIZ-93: DMX-Farben im 3D als sRGB lesen und satt halten.
//
// Befund (gemessen): Abendrot 255/60/0 wirkte im Strahl hellbeige, obwohl der
// Payload stimmt. Zwei Ursachen, beide fuer ALLE Geraete:
//
//  1. Farbraum. three r128 nimmt Material- und Lichtfarben als LINEAR, die
//     Ausgabe (renderer.outputEncoding = sRGBEncoding) kodiert danach nach
//     sRGB. DMX-Werte SIND aber schon sRGB-Werte (so mischt sie das Pult und
//     so zeigt sie jedes Farbfeld der Oberflaeche). r/255 ungewandelt hob G 60
//     damit auf ~133 — aus Rot wurde Orange, aus Orange Beige.
//     -> `lichtfarbe()` wandelt EINMAL sRGB -> linear, dort wo die Farbe aus dem
//     Payload in Material-/Lichtfarben geht (updateFixture, Kopf-Farben der
//     Mehrkopf-Geraete, Laser-Profilfarbe).
//
//  2. Tone-Mapping. ACES (renderer.js) mischt die Kanaele ueber seine
//     Eingangs-/Ausgangsmatrix — helle gesaettigte Farben laufen Richtung
//     Weiss (reines Rot -> 255/40/25). Fuer die unbeleuchteten Lichtmaterialien
//     (Kegel, Bodenflecken, Laserstrahlen) ersetzt `patchLichtTon` die
//     Tone-Mapping-Zeile durch die farbtonerhaltende Form: dieselbe ACES-Kurve
//     (inkl. Belichtung) auf den hellsten Kanal, alle Kanaele mit demselben
//     Faktor skaliert. Grau/Weiss sind damit BIT-gleich wie bisher (ACES bildet
//     Grau auf Grau ab: die Zeilensummen beider Matrizen sind 1), also bleiben
//     Weiss und die Dimmer-Kennlinie unveraendert; Farben behalten ihren Ton.
//     Koerper, Raum und Buehnenobjekte behalten das normale ACES.
//     Linsen/Pixel (MeshStandard) bekommen nur die sRGB-Wandlung, NICHT diesen
//     Patch: beleuchtete Materialien tragen den Gobo-Projektions-Hook am
//     PROTOTYP (scene/gobo_projektion.js) — ein eigener Hook je Linse wuerde
//     ihn verdecken und einen zweiten Programmschluessel bringen.
//
// Helligkeits-Masse (Sichtbarkeits-Schwellen, Licht-Last des Ausbrennschutzes,
// Pool-Rangfolge) rechnen weiter im sRGB-Mass von vorher: `srgbKanal` bildet
// den hellsten linearen Kanal zurueck (monoton je Kanal, also identisch zum
// hellsten sRGB-Kanal) — Farbe und Dimmer bleiben getrennt, keine Schwelle
// verschiebt sich.
"use strict";

import * as THREE from '../three/three.js';

/** DMX-Farbe 0..255 (sRGB) -> lineare THREE.Color fuer Materialien/Lichter.
 *  `ziel` (optional) wird wiederverwendet statt neu angelegt. */
export function lichtfarbe(r, g, b, ziel) {
  const c = ziel || new THREE.Color();
  c.setRGB((Number(r) || 0) / 255, (Number(g) || 0) / 255, (Number(b) || 0) / 255);
  return c.convertSRGBToLinear();
}

/** Ein linearer Kanalwert 0..1 -> sRGB 0..1 (dieselbe Kurve wie three). */
export function srgbKanal(v) {
  if (!(v > 0)) return 0;
  return (v < 0.0031308) ? v * 12.92 : 1.055 * Math.pow(v, 1 / 2.4) - 0.055;
}

const TON_ANKER = '#include <tonemapping_fragment>';
// Farbtonerhaltendes Tone-Mapping: `toneMapping()` ist die vom Renderer
// gewaehlte Funktion (ACES mit toneMappingExposure), nur auf Grau angewandt.
const TON_NEU = [
  '#if defined( TONE_MAPPING )',
  '\t{',
  '\t\tfloat lightosHell = max( max( gl_FragColor.r, gl_FragColor.g ), gl_FragColor.b );',
  '\t\tif ( lightosHell > 0.0 ) gl_FragColor.rgb *= toneMapping( vec3( lightosHell ) ).g / lightosHell;',
  '\t}',
  '#endif',
].join('\n');

/** Fragment-Shader eines Lichtmaterials patchen; null = Anker nicht genau
 *  einmal da (anderer three-Stand) — dann bleibt das normale ACES. */
export function patchLichtTon(fs) {
  if (typeof fs !== 'string') return null;
  const i = fs.indexOf(TON_ANKER);
  if (i < 0 || fs.indexOf(TON_ANKER, i + TON_ANKER.length) >= 0) return null;
  return fs.slice(0, i) + TON_NEU + fs.slice(i + TON_ANKER.length);
}

/** Fuer onBeforeCompile-Hooks (auch die des Ausbrennschutzes). */
export function lichtTonAnwenden(shader) {
  const fs = patchLichtTon(shader.fragmentShader);
  if (fs !== null) shader.fragmentShader = fs;
}

// Eigene, benannte Funktion: three nimmt onBeforeCompile.toString() in den
// Programmschluessel — alle Laserstrahlen teilen sich damit ihr Programm.
function lichtTonHook(shader) { lichtTonAnwenden(shader); }

/** Unbeleuchtetes Lichtmaterial (MeshBasic) markieren. Beleuchtete
 *  Materialien bleiben aussen vor (Gobo-Hook am Prototyp, s. Modulkopf);
 *  ein schon gesetzter eigener Hook bleibt unangetastet. */
export function lichtMaterial(mat) {
  if (!mat || !mat.isMeshBasicMaterial) return;
  if (Object.prototype.hasOwnProperty.call(mat, 'onBeforeCompile')) return;
  mat.onBeforeCompile = lichtTonHook;
}

/** Laserstrahlen eines Geraets markieren (einmal beim Bau, vor dem ersten
 *  Kompilieren). Kegel und Bodenflecken laufen ueber die Hooks des
 *  Ausbrennschutzes (ausbrennen.js), die dieselbe Funktion anwenden. */
export function lichtMaterialienMarkieren(f) {
  if (!f || !f.laserBeams) return;
  for (const bm of f.laserBeams) if (bm) lichtMaterial(bm.material);
}
