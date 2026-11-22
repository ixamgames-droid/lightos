// VIZ-114: LED-Matrizen in mehreren BAUFORMEN, parametrisch aus dem Profil.
//
// Bis hierher kannte das 3D genau eine Matrix: die Kachel aus `buildMatrixPanel`
// (builders.js), deren Groesse aus dem Seitenverhaeltnis des Rasters folgt (die
// laengere Kante 0,5 m). Ein LED-Vorhang von 4 x 8 m, eine Pixel-Leiste oder
// ein Ring standen damit alle als dieselbe halbe Meter grosse Kachel da.
//
// Seit FM-80 traegt ein Profil aus dem Matrix-Assistenten, was man dafuer
// braucht: Pixel B x H, Flaeche in cm (daraus der Pixelabstand) und die
// Bauform. Python reicht das als `matrixForm` in der Nutzlast mit
// (`led_matrix.viz_form`):
//
//   { bauform, pitchW, pitchH (mm), breiteM, hoeheM, spalten, zeilen,
//     teilZeile, geschaetzt }
//
// ★ Wann dieser Weg greift — und wann NICHT:
//   * Bauform `panel` OHNE Flaechenangabe (jedes Bestandsgeraet) baut weiter
//     `buildMatrixPanel`, Zeile fuer Zeile unveraendert. Das ist die Zusage
//     „Bestandsgeraete pixelgleich“ (tests/test_viz114_*_scene.py misst sie).
//   * Alles andere (eine andere Bauform, oder ein Panel mit echten Massen)
//     baut hier.
//
// ★★ EIN Teil = EIN gepatchtes Geraet. Eine Matrix ueber mehrere Universen
// besteht seit FM-80 aus Zeilen-Streifen, je einer ein eigenes Geraet. Jeder
// Teil zeichnet seine Pixel an IHRER Stelle in der ganzen Matrix — der
// Ursprung des Modells ist die Mitte der GANZEN Matrix (beim Ring dessen
// Mittelpunkt). Stehen alle Teile auf derselben Position, setzt sich die
// Matrix im 3D von selbst zusammen.
//
// ★★ Nummerierung: ausschliesslich ueber `placeElement` (pixel_order.js) —
// dieselbe Funktion wie das Bestands-Panel und das 2D-Icon, Zwilling von
// `core/pixel_order.place_element`. Global gilt: Anzeige-Zeile = `teilZeile`
// + lokale Zeile; das ist genau `led_matrix.pixel_platz` und das Raster der
// Gesamt-Gruppe (`gesamt_raster`). Eine zweite Formel gibt es hier nicht.
//
// ★ Viele Pixel: ALLE Pixel eines Teils sind EIN `InstancedMesh` (ein
// Zeichenaufruf), ihre Farbe ist die Instanzfarbe. Die Helligkeit (Master,
// Strobe) steht als EINE Zahl im Material (`color` als Skalar) — so faerbt
// ein DMX-Stand nur einen Float-Puffer um, statt hunderte Materialien.
// Auf Stufe Niedrig haben runde Pixel weniger Ecken (`matrixPunktEcken`
// aus quality_tiers.js).
//
// Masse je Bauform (Python-Seite und Anleitung sagen dasselbe):
//   panel   Breite x Hoehe = Flaeche; Gehaeuse 5 cm tief, Pixel 85 % der Zelle.
//   leiste  wie panel, aber flaches 2,5-cm-Profil ohne Rand — fuer Stab/Leiste.
//   vorhang keine Flaeche, sondern je Spalte eine senkrechte Bahn; Pixel als
//           runde Punkte; oben eine Haengeschiene (nur am obersten Teil).
//   ring    Breite = Aussendurchmesser, Hoehe = Breite des Pixel-Bands;
//           Spalten laufen im Uhrzeigersinn von oben, Zeile 0 = aussen.
//   saeule  Breite = Durchmesser, Hoehe = Hoehe; Spalten rundum (von vorn
//           nach rechts), Zeile 0 = oben. Pixel schauen nach aussen.
import * as THREE from '../three/three.js';
import { placeElement, panelGrid } from './pixel_order.js';
import { isLowSpec, tierSettings } from '../scene/renderer.js';

export const MATRIX_BAUFORMEN = ['panel', 'vorhang', 'leiste', 'ring', 'saeule'];

// Ohne Flaechenangabe (Bauform im Profil, Assistenten-Daten aber geloescht)
// braucht eine Nicht-Panel-Form trotzdem einen Abstand: 3 cm, ein ueblicher
// Wert fuer Pixel-Leisten. Die Nutzlast markiert das als `geschaetzt`.
const PITCH_ERSATZ_MM = 30;

function _zahl(v, ersatz) {
  const x = Number(v);
  return Number.isFinite(x) ? x : ersatz;
}

/** Normalisiert die `matrixForm`-Angabe der Nutzlast (nie werfen). */
export function matrixFormNormal(mf) {
  const m = mf || {};
  const b = String(m.bauform || '').trim().toLowerCase();
  const bauform = MATRIX_BAUFORMEN.indexOf(b) >= 0 ? b : 'panel';
  const pitchW = Math.max(0, _zahl(m.pitchW, 0));
  const pitchH = Math.max(0, _zahl(m.pitchH, 0));
  return {
    bauform,
    pitchW, pitchH,
    spalten: Math.max(0, Math.floor(_zahl(m.spalten, 0))),
    zeilen: Math.max(0, Math.floor(_zahl(m.zeilen, 0))),
    teilZeile: Math.max(0, Math.floor(_zahl(m.teilZeile, 0))),
    breiteM: Math.max(0, _zahl(m.breiteM, 0)),
    hoeheM: Math.max(0, _zahl(m.hoeheM, 0)),
  };
}

/** Baut diese Angabe ein eigenes Modell? (sonst: Bestands-Panel) */
export function matrixFormAktiv(mf) {
  if (!mf) return false;
  const m = matrixFormNormal(mf);
  if (m.bauform !== 'panel') return true;
  return m.pitchW > 0 && m.pitchH > 0;
}

// Ecken eines runden Pixels — Stufe Niedrig spart hier (VIZ-71-Tabelle).
function _punktEcken() {
  const e = tierSettings && tierSettings.matrixPunktEcken;
  if (typeof e === 'number' && e >= 3) return e;
  return isLowSpec ? 6 : 12;
}

const _m4 = new THREE.Matrix4();
const _q = new THREE.Quaternion();
const _p = new THREE.Vector3();
const _s = new THREE.Vector3();
const _ACHSE_Y = new THREE.Vector3(0, 1, 0);

/**
 * VIZ-114: Matrix-Teil in seiner Bauform. Vertrag wie `buildMatrixPanel`
 * ({ group, pixels, whites, isMatrix, rows, cols }) plus
 *   pixels[i]     = { r, c, R, x, y, z } — r/c lokal (wie Bestand), R = globale
 *                   Anzeige-Zeile, x/y/z = Mitte im Modell (Meter)
 *   matrixInstanz = { mesh, farben, hell, bauform, masse }
 *   bauform, masse = { breite, hoehe, tiefe } der GANZEN Matrix in Metern.
 */
export function buildMatrixForm(n, pixelOrder, elementRotation, elementFlip,
                                gridCols, gridRows, matrixForm) {
  const mf = matrixFormNormal(matrixForm);
  const { count, cols: srcCols, rows: srcRows } = panelGrid(n, gridCols, gridRows);
  const plaetze = [];
  for (let i = 0; i < count; i++)
    plaetze.push(placeElement(i, srcCols, srcRows, pixelOrder,
                              elementRotation, elementFlip));
  const rows = plaetze[0].rows, cols = plaetze[0].cols;

  // Ganze Matrix: Spalten/Zeilen aus dem Profil, sonst dieser Teil allein.
  const spalten = mf.spalten > 0 ? mf.spalten : cols;
  const zeilen = Math.max(mf.zeilen > 0 ? mf.zeilen : rows, mf.teilZeile + rows);
  const pw = (mf.pitchW > 0 ? mf.pitchW : PITCH_ERSATZ_MM) / 1000;
  const ph = (mf.pitchH > 0 ? mf.pitchH : PITCH_ERSATZ_MM) / 1000;
  const z0 = mf.teilZeile;

  const group = new THREE.Group();
  const bauform = mf.bauform;
  const lagen = [];          // je Pixel {x,y,z, sx,sy, ry}
  let rund = false;          // runde Punkte statt Quads
  let masse;

  if (bauform === 'panel' || bauform === 'leiste') {
    const W = spalten * pw, H = zeilen * ph;
    const tiefe = bauform === 'leiste' ? 0.025 : 0.05;
    const anteil = bauform === 'leiste' ? 0.8 : 0.85;
    // Gehaeuse NUR dieses Teils (seine Zeilen), an seiner Stelle.
    const yOben = H / 2 - z0 * ph, hoeheTeil = rows * ph;
    const body = new THREE.Mesh(
      new THREE.BoxGeometry(W, hoeheTeil, tiefe),
      new THREE.MeshStandardMaterial({
        color: bauform === 'leiste' ? 0x2a2a2e : 0x141414,
        metalness: 0.4, roughness: 0.6 }));
    body.position.set(0, yOben - hoeheTeil / 2, 0);
    body.castShadow = true;
    body.userData.matrixKoerper = true;
    group.add(body);
    for (let i = 0; i < count; i++) {
      const { r, c } = plaetze[i];
      lagen.push({ x: -W / 2 + (c + 0.5) * pw, y: H / 2 - (z0 + r + 0.5) * ph,
                   z: tiefe / 2 + 0.002, sx: pw * anteil, sy: ph * anteil, ry: 0 });
    }
    masse = { breite: W, hoehe: H, tiefe };
  } else if (bauform === 'vorhang') {
    const W = spalten * pw, H = zeilen * ph;
    rund = true;
    const d = Math.max(0.006, Math.min(0.04, 0.45 * Math.min(pw, ph)));
    // Je Spalte eine Bahn ueber die Zeilen dieses Teils (bis zur Zellkante,
    // damit die Bahnen der Teile ohne Luecke aneinander anschliessen).
    const yOben = H / 2 - z0 * ph, yUnten = yOben - rows * ph;
    const pos = [];
    for (let c = 0; c < cols; c++) {
      const x = -W / 2 + (c + 0.5) * pw;
      pos.push(x, yOben, 0, x, yUnten, 0);
    }
    const bg = new THREE.BufferGeometry();
    bg.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
    const bahnen = new THREE.LineSegments(
      bg, new THREE.LineBasicMaterial({ color: 0x3a3a3a }));
    bahnen.userData.matrixBahnen = true;
    group.add(bahnen);
    if (z0 === 0) {
      // Haengeschiene ueber der ganzen Breite — nur am obersten Teil.
      const schiene = new THREE.Mesh(
        new THREE.BoxGeometry(W + pw, 0.04, 0.04),
        new THREE.MeshStandardMaterial({ color: 0x222222, metalness: 0.6, roughness: 0.5 }));
      schiene.position.set(0, H / 2 + 0.02, 0);
      schiene.userData.matrixKoerper = true;
      group.add(schiene);
    }
    for (let i = 0; i < count; i++) {
      const { r, c } = plaetze[i];
      lagen.push({ x: -W / 2 + (c + 0.5) * pw, y: H / 2 - (z0 + r + 0.5) * ph,
                   z: 0.003, sx: d, sy: d, ry: 0 });
    }
    masse = { breite: W, hoehe: H, tiefe: 0.04 };
  } else if (bauform === 'ring') {
    rund = true;
    // Breite = Aussendurchmesser, Hoehe = Bandbreite (aussen -> innen).
    const D = mf.breiteM > 0 ? mf.breiteM : spalten * pw / Math.PI;
    const band = Math.min(D / 2, mf.hoeheM > 0 ? mf.hoeheM : zeilen * ph);
    const pr = band / zeilen;
    const rAussenTeil = D / 2 - z0 * pr;
    const rInnenTeil = Math.max(0, rAussenTeil - rows * pr);
    const koerper = new THREE.Mesh(
      new THREE.RingGeometry(rInnenTeil, rAussenTeil, Math.max(24, Math.min(128, spalten)), 1),
      new THREE.MeshStandardMaterial({ color: 0x141414, metalness: 0.4,
                                       roughness: 0.6, side: THREE.DoubleSide }));
    koerper.position.z = -0.005;
    koerper.userData.matrixKoerper = true;
    group.add(koerper);
    for (let i = 0; i < count; i++) {
      const { r, c } = plaetze[i];
      const rad = Math.max(pr / 2, D / 2 - (z0 + r + 0.5) * pr);
      const th = Math.PI / 2 - 2 * Math.PI * (c + 0.5) / spalten;
      const bogen = 2 * Math.PI * rad / spalten;
      const d = Math.max(0.004, 0.8 * Math.min(pr, bogen));
      lagen.push({ x: rad * Math.cos(th), y: rad * Math.sin(th), z: 0.002,
                   sx: d, sy: d, ry: 0 });
    }
    masse = { breite: D, hoehe: D, tiefe: 0.01, band };
  } else {   // saeule
    const D = mf.breiteM > 0 ? mf.breiteM : spalten * pw / Math.PI;
    const H = mf.hoeheM > 0 ? mf.hoeheM : zeilen * ph;
    const phs = H / zeilen;
    const rad = D / 2;
    const yOben = H / 2 - z0 * phs, hoeheTeil = rows * phs;
    const koerper = new THREE.Mesh(
      new THREE.CylinderGeometry(rad * 0.97, rad * 0.97, hoeheTeil,
                                 Math.max(12, Math.min(isLowSpec ? 32 : 64, spalten))),
      new THREE.MeshStandardMaterial({ color: 0x141414, metalness: 0.4, roughness: 0.6 }));
    koerper.position.y = yOben - hoeheTeil / 2;
    koerper.castShadow = true;
    koerper.userData.matrixKoerper = true;
    group.add(koerper);
    const bogen = Math.PI * D / spalten;
    for (let i = 0; i < count; i++) {
      const { r, c } = plaetze[i];
      const th = 2 * Math.PI * (c + 0.5) / spalten;   // 0 = vorn (+Z), dann nach rechts (+X)
      lagen.push({ x: rad * Math.sin(th), y: H / 2 - (z0 + r + 0.5) * phs,
                   z: rad * Math.cos(th), sx: bogen * 0.85, sy: phs * 0.85, ry: th });
    }
    masse = { breite: D, hoehe: H, tiefe: D };
  }

  // ── Alle Pixel als EIN InstancedMesh ──────────────────────────────────────
  const geo = rund ? new THREE.CircleGeometry(0.5, _punktEcken())
                   : new THREE.PlaneGeometry(1, 1);
  // Unbeleuchtet: ein Pixel ist ein Strahler, keine Oberflaeche. `color` ist
  // die gemeinsame Helligkeit (Master/Strobe), die Instanzfarbe die Pixelfarbe.
  const mat = new THREE.MeshBasicMaterial({ color: 0x000000, side: THREE.DoubleSide,
                                            toneMapped: true });
  const mesh = new THREE.InstancedMesh(geo, mat, count);
  const farben = new Float32Array(count * 3);
  mesh.instanceColor = new THREE.InstancedBufferAttribute(farben, 3);
  const pixels = [];
  for (let i = 0; i < count; i++) {
    const l = lagen[i];
    _p.set(l.x, l.y, l.z);
    _q.setFromAxisAngle(_ACHSE_Y, l.ry);
    _s.set(l.sx, l.sy, 1);
    _m4.compose(_p, _q, _s);
    mesh.setMatrixAt(i, _m4);
    const { r, c } = plaetze[i];
    pixels.push({ r, c, R: z0 + r, x: l.x, y: l.y, z: l.z });
  }
  mesh.instanceMatrix.needsUpdate = true;
  mesh.instanceColor.needsUpdate = true;
  mesh.userData.matrixPixel = true;
  // Die Bounding-Sphere des Grundquads waere fuer das Culling zu klein —
  // ohne Neuberechnung fiele das Modell am Bildrand weg.
  mesh.frustumCulled = false;
  group.add(mesh);

  // Strobe/Helligkeit ueber dieselbe Schnittstelle wie die Bestands-Pixel
  // (strobe_hell.js liest und schreibt `o.material.emissiveIntensity`).
  const hell = {
    material: {
      _v: 0,
      get emissiveIntensity() { return this._v; },
      set emissiveIntensity(v) {
        this._v = v;
        mat.color.setScalar(Math.max(0, v));
      },
    },
  };
  return {
    group, pixels, whites: [], isMatrix: true, rows, cols,
    bauform, masse,
    matrixInstanz: { mesh, farben, hell, bauform, masse, anzahl: count },
  };
}

/**
 * DMX -> Instanzfarben. Dieselbe Regel wie `updateMatrixPanelDmx`: Pixel i
 * haengt an heads[i]; ohne Kopf-Daten Pixel 0 = Basisfarbe, Rest aus. Der
 * Master-Dimmer (intNorm * 1.6, wie beim Bestands-Panel) ist EIN Skalar.
 * `lichtfarbe` wird hereingereicht (sRGB -> linear, VIZ-93).
 */
export function updateMatrixFormDmx(f, dmx, lichtfarbe) {
  const mi = f.matrixInstanz;
  const { r, g, b, intNorm } = dmx;
  const hs = f.lastHeads || [];
  const fa = mi.farben;
  for (let i = 0; i < mi.anzahl; i++) {
    const h = hs[i] || {};
    const hr = (h.r != null) ? h.r : (i === 0 ? r : 0);
    const hg = (h.g != null) ? h.g : (i === 0 ? g : 0);
    const hb = (h.b != null) ? h.b : (i === 0 ? b : 0);
    const col = lichtfarbe(hr, hg, hb);
    fa[3 * i] = col.r; fa[3 * i + 1] = col.g; fa[3 * i + 2] = col.b;
  }
  mi.mesh.instanceColor.needsUpdate = true;
  mi.hell.material.emissiveIntensity = intNorm * 1.6;
}

/** Test-/Debug-Seam: Kennzahlen eines Matrix-Teils als Zahlen. */
export function matrixFormInfo(f) {
  if (!f || !f.matrixInstanz) return null;
  const mi = f.matrixInstanz;
  return {
    bauform: mi.bauform, anzahl: mi.anzahl,
    breite: mi.masse.breite, hoehe: mi.masse.hoehe, tiefe: mi.masse.tiefe,
    band: mi.masse.band || 0,
    hell: mi.hell.material.emissiveIntensity,
    ecken: mi.mesh.geometry.type === 'CircleGeometry'
      ? mi.mesh.geometry.parameters.segments : 0,
    zeichnungen: 1,
  };
}
