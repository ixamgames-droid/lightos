// VIZ-15: aus dem Bodenfleck wird ein Licht-POOL.
//
// Was er vorher war: eine `CircleGeometry` mit gleichmaessiger Deckkraft und
// FESTEM Radius (1,2 m) — also eine Scheibe mit harter Kante, die immer gleich
// gross blieb, egal wie weit der Scheinwerfer weg stand oder wie eng der Zoom
// war. Echtes Licht macht beides nicht: es laeuft am Rand weich aus, und der
// Fleck waechst mit dem Abstand.
//
// Zwei Ergaenzungen, beide billig:
//
// 1. **Weicher Rand** ueber EINE gemeinsame Falloff-Textur als `alphaMap`.
//    Eine Textur fuer alle Fixtures, einmal gezeichnet — kein Aufwand pro
//    Geraet und keiner pro Frame.
//
//    ⚠️ DIE FALLE DABEI: `alphaMap` liest in three.js den **GRUENKANAL** der
//    Textur, nicht deren Alphakanal. Ein Verlauf aus "weiss, Alpha 1" nach
//    "weiss, Alpha 0" — der naheliegende Einfall — ergibt einen konstanten
//    Gruenwert und damit gar keinen Verlauf: der Rand bliebe hart. Gezeichnet
//    wird deshalb ein GRAUVERLAUF mit voller Deckkraft (weiss = innen,
//    schwarz = aussen).
//
// 2. **Groesse folgt Abstand und Zoom.** Der Auftreffabstand wird in
//    `applyFloorAim` ohnehin gerechnet (seit VIZ-BEAM-OCCLUSION Teil 1), und
//    der SpotLight-Winkel folgt seit VIZ-MH-OPTICS dem Zoom — der Radius faellt
//    damit als reine Multiplikation ab, ohne neue Geometrie und ohne
//    zusaetzlichen Strahl.
import * as THREE from '../three/three.js';

// Aus createFloorSpot: mit diesem Radius wird die Scheibe gebaut. Der Faktor
// unten ist relativ dazu — steht die Zahl dort einmal anders, muss sie hier
// mitwandern, deshalb der Name statt einer nackten 1.2 an zwei Stellen.
export const POOL_BASIS_RADIUS = 1.2;
// Grenzen gegen Entartung: ein Scheinwerfer direkt ueber dem Boden ergaebe
// sonst einen Punkt, einer quer durch die Halle eine Flaeche, die die halbe
// Szene ueberdeckt.
export const POOL_MIN_RADIUS = 0.25;
export const POOL_MAX_RADIUS = 12.0;

let _falloff = null;

/** Die gemeinsame Falloff-Textur (Grauverlauf, s. Fallenhinweis oben). */
export function poolFalloffTexture() {
  if (_falloff) return _falloff;
  try {
    const S = 128;
    const cv = document.createElement('canvas');
    cv.width = S; cv.height = S;
    const ctx = cv.getContext('2d');
    const g = ctx.createRadialGradient(S / 2, S / 2, 0, S / 2, S / 2, S / 2);
    // Innen voll, ein gutes Stueck flach halten, dann weich auf null. Ein
    // linearer Verlauf ab der Mitte sieht aus wie ein Farbverlauf, nicht wie
    // ein Lichtfleck — echtes Licht hat einen hellen Kern.
    g.addColorStop(0.00, '#ffffff');
    g.addColorStop(0.45, '#ededed');
    g.addColorStop(0.75, '#8a8a8a');
    g.addColorStop(1.00, '#000000');
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, S, S);
    _falloff = new THREE.CanvasTexture(cv);
  } catch (e) {
    _falloff = null;    // ohne Canvas (Testumgebung) bleibt es die harte Scheibe
  }
  return _falloff;
}

/** Skalierungsfaktor der Boden-Scheibe — rein, damit die Rechnung pruefbar ist.
 *
 *  ``dist`` ist der Abstand zum Auftreffpunkt (``Infinity`` = trifft nie),
 *  ``spotAngle`` der halbe Oeffnungswinkel des SpotLights in Radiant (er folgt
 *  seit VIZ-MH-OPTICS dem Zoom). Ohne brauchbare Eingaben bleibt es beim
 *  Grundradius — ein Fleck, der bei einem NaN auf null zusammenfaellt, waere
 *  schlimmer als einer in der falschen Groesse.
 */
export function floorPoolScale(dist, spotAngle) {
  if (typeof dist !== 'number' || !isFinite(dist) || dist <= 0) return 1;
  if (typeof spotAngle !== 'number' || !isFinite(spotAngle) || spotAngle <= 0) return 1;
  const r = Math.tan(Math.min(spotAngle, Math.PI / 2 - 0.01)) * dist;
  if (!isFinite(r) || r <= 0) return 1;
  const geklemmt = Math.max(POOL_MIN_RADIUS, Math.min(POOL_MAX_RADIUS, r));
  return geklemmt / POOL_BASIS_RADIUS;
}

/** Weichen Rand auf einen frisch gebauten Bodenfleck legen. */
export function applyPoolFalloff(disc) {
  if (!disc || !disc.material) return;
  const tex = poolFalloffTexture();
  if (!tex) return;
  disc.material.alphaMap = tex;
  disc.material.needsUpdate = true;
}

/** Groesse des Bodenflecks an Auftreffabstand und Zoom angleichen.
 *
 *  Bewusst mit Totzone: der Abstand kommt aus einer Pan/Tilt-Rechnung und
 *  schwankt minimal — ohne sie schriebe der 44-Hz-Pfad jeden Frame eine neue
 *  Skalierung (dieselbe Ueberlegung wie bei der Kegellaenge).
 */
export function syncPoolSize(f, dist) {
  const disc = f && f.floorSpot;
  if (!disc) return;
  const k = floorPoolScale(dist, f.spot ? f.spot.angle : 0);
  if (Math.abs((disc.scale.x || 1) - k) < 0.01) return;
  // Die Scheibe liegt flach (rotation.x = -PI/2), ihre lokale Z-Achse zeigt
  // also nach oben — skaliert wird in X und Y, nicht in X und Z.
  disc.scale.set(k, k, 1);
}
