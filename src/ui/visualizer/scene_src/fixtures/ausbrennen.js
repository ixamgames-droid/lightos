// VIZ-91: Ausbrennschutz — viele Kegel/Bodenflecken addieren sich nicht mehr
// zu reinem Weiss.
//
// Ist-Zustand: Kegel (createBeamCone) und Bodenflecken (createFloorSpot) sind
// MeshBasicMaterial mit AdditiveBlending, Deckkraft = Helligkeit * 0,85 bzw.
// * 0,55. Das ACES-Tone-Mapping des Renderers hilft dagegen NICHT: three
// wendet es je Fragment an, BEVOR geblendet wird — jeder Kegel fuer sich
// bleibt unter 1, ihre Summe im Bildpuffer klemmt trotzdem auf Weiss. Ein
// echtes Tone-Mapping der Summe braeuchte einen HDR-Zwischenpuffer plus
// Nachbearbeitung (r128 ohne EffectComposer, Fill-Rate auf schwachen GPUs).
//
// Ansatz: die Deckkraft ALLER Kegel (bzw. Flecken) wird mit EINEM gemeinsamen
// Faktor gedaempft, der aus der "Licht-Last" der Szene folgt — der Summe der
// leuchtenden Kegel (je Kegel 0..1: Deckkraft relativ zur vollen, mal hellster
// Farbkanal). Bis zur Schwelle bleibt alles wie bisher (kleine Shows sehen
// unveraendert aus); darueber faellt der Faktor mit (Schwelle/Last)^p (Kegel
// p = 1, Flecken 0,75 — Begruendung bei den Konstanten). Bei den Kegeln bleibt
// die Summe ueber der Schwelle damit konstant (ein festes Budget von etwa
// "Schwelle" vollen Kegeln, wie eine Belichtungsautomatik); nach unten
// begrenzt, damit einzelne Kegel sichtbar bleiben.
//
// Gezaehlt wird nur, was zu sehen ist (beamsOff, Kegel-/Fleck-Schalter, 2D,
// Kopf ohne Auftreffpunkt zaehlen nicht); Prisma-Nebenstrahlen zaehlen je als
// eigener Kegel. Laser (eigenes Material, laser.js) und die echten
// Pool-Lichter (scene/spot_pool.js) bleiben ungedaempft.
//
// Kosten: der Faktor ist EINE geteilte Uniform, per onBeforeCompile in den
// Shader gelegt (gl_FragColor.a *= Faktor) — keine Schleife ueber Geraete,
// kein Material-Schreiben, kein Shader-Neubau beim Aendern. Die Last wird
// inkrementell gefuehrt: updateFixture meldet nur den Anteil DIESES Geraets
// (alt raus, neu rein), removeFixture nimmt ihn heraus. Gemessen wird der
// Stand OHNE Strobe (vor _strobeZeigen) — sonst pumpte jede Blitzflanke die
// Helligkeit aller anderen Kegel.
//
// material.opacity bleibt unberuehrt: Sichtbarkeits-Schwellen (beamsSichtbar,
// fleckSichtbar), Strobe-Merker und Prisma-Faecher lesen weiter den
// ungedaempften Wert.
"use strict";

import { requestRender } from '../scene/render_loop.js';
// Zirkulaer mit builders.js (das ausbrennNachfuehren holt) — unbedenklich,
// beide Seiten lesen die Importe nur in Funktionsruempfen.
import { beamsSichtbar, fleckSichtbar } from './builders.js';

// Kegel ueberlagern sich von vorn gesehen fast vollstaendig (alle zeigen in
// den Raum) — deshalb strenger als die Bodenflecken, die nebeneinander liegen.
// Schwelle 8: ein Spider (8 Einzelstrahlen) bleibt fuer sich ungedaempft.
// Exponent: Kegel stapeln sich in der Frontansicht reihenweise HINTEREINANDER
// (Traversen-Raster) — die Ueberdeckung je Bildpunkt waechst fast linear mit
// der Geraetezahl. Gemessen (60 weisse Moving Heads, 10x6-Raster, Blick von
// vorn, 640x480, 27.10.2026): Weiss-Anteil des Bildes ohne Schutz 58 %; mit
// der Wurzel (p = 0,5) nur 51 %, mit p = 0,85 43 %, mit p = 1 35 % (bei 30
// Geraeten 36 -> 23 %). Mehr Daempfung liesse Einzelkegel verschwinden — der
// Rest ist echte Ueberdeckung (60 weisse Strahlen hintereinander) und waere
// nur mit einem HDR-Zwischenpuffer zu deckeln (s. Modulkopf).
export const KEGEL_SCHWELLE = 8;
export const KEGEL_EXPONENT = 1;
export const KEGEL_MINIMUM = 0.08;
export const FLECK_SCHWELLE = 10;
export const FLECK_EXPONENT = 0.75;
export const FLECK_MINIMUM = 0.25;

// Bezugsgroessen fuer "voll": Deckkraft eines Fleckes bei Helligkeit 1
// (createFloorSpot); beim Kegel die Einstellung beamOpacity (s. kegelLast).
const FLECK_VOLL = 0.55;

/** Daempfungsfaktor (0..1] fuer eine Licht-Last: bis `schwelle` 1, darueber
 *  (schwelle/last)^exponent, nie unter `minimum`. Rein. */
export function ausbrennDaempfung(last, schwelle, minimum, exponent = 0.5) {
  if (!(last > schwelle) || !(schwelle > 0)) return 1;
  const p = (exponent > 0) ? exponent : 0.5;
  return Math.max(minimum, Math.pow(schwelle / last, p));
}

// Geteilte Uniforms — jedes gepatchte Material bindet DIESES Objekt.
const _kegel = { value: 1 };
const _fleck = { value: 1 };
let _kegelLast = 0;
let _fleckLast = 0;
let _geraete = 0;
let _an = true;          // Test-/Diagnose-Schalter (ausbrennSchutz)

const ANKER = '#include <tonemapping_fragment>';
const ZEILE = 'gl_FragColor.a *= lightosAusbrennen;\n\t';
const KOPF = 'uniform float lightosAusbrennen;\n';

/** MeshBasic-Fragment-Shader patchen; null = Anker nicht genau einmal da
 *  (anderer three-Stand) — dann bleibt das Material ungedaempft. */
export function patchAusbrennShader(fs) {
  if (typeof fs !== 'string') return null;
  const i = fs.indexOf(ANKER);
  if (i < 0 || fs.indexOf(ANKER, i + ANKER.length) >= 0) return null;
  return KOPF + fs.slice(0, i) + ZEILE + fs.slice(i);
}

// Zwei GETRENNTE Funktionen (nicht eine Fabrik): three nimmt
// onBeforeCompile.toString() in den Programmschluessel.
function kegelAusbrennHook(shader) {
  const fs = patchAusbrennShader(shader.fragmentShader);
  if (fs === null) return;
  shader.fragmentShader = fs;
  shader.uniforms.lightosAusbrennen = _kegel;
}

function fleckAusbrennHook(shader) {
  const fs = patchAusbrennShader(shader.fragmentShader);
  if (fs === null) return;
  shader.fragmentShader = fs;
  shader.uniforms.lightosAusbrennen = _fleck;
}

export function kegelDaempfen(mat) { if (mat) mat.onBeforeCompile = kegelAusbrennHook; }
export function fleckDaempfen(mat) { if (mat) mat.onBeforeCompile = fleckAusbrennHook; }

function _anteil(m, voll) {
  const mat = m && m.material;
  if (!mat || !(mat.opacity > 0)) return 0;
  const c = mat.color;
  const farbe = c ? Math.max(c.r, c.g, c.b) : 1;
  return Math.min(1, mat.opacity / voll) * Math.min(1, Math.max(0, farbe));
}

/** Roh-Kegel-Last eines Geraets (ohne Sichtbarkeit): Summe ueber alle seine
 *  Kegel. Prisma-Nebenstrahlen teilen das Material des Hauptstrahls
 *  (prism.js) und tragen je eine volle Kegel-Menge bei. */
function _rohKegel(f, beamOpacity) {
  const voll = Math.max(0.05, beamOpacity || 0);
  let s = _anteil(f.beam, voll);
  if (s > 0 && f.prismCones) s *= 1 + f.prismCones.length;
  if (f.bars) for (const bar of f.bars) if (bar && bar.beams) for (const b of bar.beams) s += _anteil(b, voll);
  if (f.parHeads) for (const ph of f.parHeads) s += _anteil(ph && ph.beam, voll);
  if (f.moverHeads) for (const mh of f.moverHeads) s += _anteil(mh && mh.beam, voll);
  return s;
}

function _rohFleck(f) { return _anteil(f.floorSpot, FLECK_VOLL); }

// Zaehlt nur, was zu sehen ist. Gefragt wird ueber DIESELBEN Regeln wie im
// Handler (beamsSichtbar / fleckSichtbar: Kegel-Schalter, 2D/3D, beamsOff je
// Geraet, Fleck-Schalter, kein Auftreffpunkt) — nicht ueber `mesh.visible`:
// das schaltet der Strobe je Blitz um, und ein Nachmelden in der Dunkelphase
// liesse die Last des Geraets bis zum naechsten DMX-Update auf 0 stehen. Die
// Helligkeits-Schwelle der Regeln deckt die Roh-Last selbst ab (0 bei dunkel).
function _sichtbar(f, roh) {
  const k = (roh.kegel > 0 && beamsSichtbar(f, 1)) ? roh.kegel : 0;
  const d = f.floorSpot;
  // Gobo-Projektion voll: die flache Scheibe ist per Ebenen-Maske aus
  // (scene/spot_pool.js#_bodenmuster), `visible` bleibt dabei an.
  const b = (roh.fleck > 0 && d && fleckSichtbar(f, 1) && (d.layers.mask & 1)) ? roh.fleck : 0;
  return [k, b];
}

function _neuRechnen() {
  if (_geraete <= 0) { _kegelLast = 0; _fleckLast = 0; }   // Rundungsreste weg
  const k = _an ? ausbrennDaempfung(_kegelLast, KEGEL_SCHWELLE, KEGEL_MINIMUM, KEGEL_EXPONENT) : 1;
  const b = _an ? ausbrennDaempfung(_fleckLast, FLECK_SCHWELLE, FLECK_MINIMUM, FLECK_EXPONENT) : 1;
  if (Math.abs(k - _kegel.value) > 1e-4 || Math.abs(b - _fleck.value) > 1e-4) {
    _kegel.value = k;
    _fleck.value = b;
    requestRender();
  }
}

function _eintragen(f) {
  const [k, b] = _sichtbar(f, f._ausbrennRoh);
  const alt = f._ausbrennLast;
  if (alt) { _kegelLast -= alt[0]; _fleckLast -= alt[1]; } else _geraete += 1;
  f._ausbrennLast = [k, b];
  _kegelLast += k; _fleckLast += b;
  _neuRechnen();
}

/** Nach dem DMX-Anwenden eines Geraets: seinen Anteil neu melden (O(Kegel
 *  dieses Geraets), keine Schleife ueber die Szene). Die Roh-Last bezieht
 *  sich auf die Deckkraft, die DIESES Update geschrieben hat — eine spaeter
 *  verstellte beamOpacity wirkt (wie im Bild) erst mit dem naechsten Update. */
export function ausbrennMelden(f, beamOpacity) {
  if (!f) return;
  f._ausbrennRoh = { kegel: _rohKegel(f, beamOpacity), fleck: _rohFleck(f) };
  _eintragen(f);
}

/** Sichtbarkeit hat sich OHNE DMX-Update geaendert (beamsOff, Kegel-/Fleck-
 *  Schalter, 2D/3D, Auftreffpunkt aus der Glaettung, Gobo-Projektion):
 *  Anteil aus der gemerkten Roh-Last neu eintragen. `fleckNeu` liest die
 *  Fleck-Deckkraft frisch (der Spot-Pool fuehrt sie zwischen zwei Updates
 *  nach) — nur ausserhalb eines Blitzes, sonst laege der Strobe-Wert drin. */
export function ausbrennNachfuehren(f, fleckNeu = false) {
  if (!f || !f._ausbrennRoh) return;
  if (fleckNeu && (f._gezeigt === undefined || f._gezeigt === 1)) f._ausbrennRoh.fleck = _rohFleck(f);
  _eintragen(f);
}

/** Geraet entfernt: seinen Anteil herausnehmen. */
export function ausbrennAbmelden(f) {
  if (!f || !f._ausbrennLast) return;
  _kegelLast -= f._ausbrennLast[0];
  _fleckLast -= f._ausbrennLast[1];
  f._ausbrennLast = null;
  f._ausbrennRoh = null;
  _geraete -= 1;
  _neuRechnen();
}

/** Test-/Diagnose-Seam: Schutz an/aus (Vorher/Nachher-Vergleich im Bild). */
export function ausbrennSchutz(an) {
  _an = !!an;
  _neuRechnen();
  return _an;
}

/** Test-/Diagnose-Seam: Lasten und aktuelle Faktoren. */
export function ausbrennInfo() {
  return {
    an: _an, kegelLast: _kegelLast, fleckLast: _fleckLast, geraete: _geraete,
    kegelFaktor: _kegel.value, fleckFaktor: _fleck.value,
    kegelSchwelle: KEGEL_SCHWELLE, kegelMinimum: KEGEL_MINIMUM, kegelExponent: KEGEL_EXPONENT,
    fleckSchwelle: FLECK_SCHWELLE, fleckMinimum: FLECK_MINIMUM, fleckExponent: FLECK_EXPONENT,
  };
}
