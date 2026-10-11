// VIZ-100: haengende Montage — ein an eine Traverse angedockter Moving Head
// haengt wirklich DARUNTER.
//
// Befund: Andocken setzt den Geraete-Ursprung 0,25 m unter die Unterkante der
// Traverse (DOCK_HANG_OFFSET, gespiegelt in stage_definition.py). Das Modell
// wurde aber vom Sockel nach OBEN gebaut (builders.js#buildMovingHead: Sockel
// bei 0, Kopf-Drehpunkt bei +0,375). Traverse 5,85-6,15 m, Ursprung 5,60 m ->
// Kopf-Drehpunkt 5,975 m: der Lichtaustritt sass mitten im Rohr.
//
// Loesung — nur die DARSTELLUNG aendert sich, keine gespeicherte Zahl:
//   * "Haengend" ist kein neues Feld. Es ist dasselbe Merkmal, das Python
//     schon fuehrt (scene_graph.MountType.HANG): an eine horizontale Traverse
//     angedockt. Hier abgeleitet aus f.dockedTo + Typ des Buehnen-Elements.
//   * Der Geraete-Ursprung bleibt, wo ihn das Andocken seit jeher hinsetzt
//     (Unterkante - DOCK_HANG_OFFSET). Bestehende Shows und Buehnen behalten
//     jede Position; es gibt nichts zu migrieren und nichts, was Python und
//     JS unterschiedlich rechnen koennten.
//   * Sockel, Hals und Buegel werden an der Ursprungs-Ebene gespiegelt, der
//     Kopf wandert mit nach unten, bleibt selbst aber UNGEDREHT: Pan dreht
//     weiter um +Y, Tilt um +X, der Lichtausgang bleibt -Y. Gleiche DMX-Werte
//     ergeben damit exakt dieselbe Strahlrichtung wie vorher — Zielen,
//     Einmessen und die Richtungsrechnung in aim.py bleiben gueltig.
//   * Danach rueckt das ganze Modell so weit hoch, dass seine Oberkante an der
//     Unterkante der Traverse anliegt. Der Betrag kommt aus der gemessenen
//     Hoehe der Teile (Bounding-Box), nicht aus einer zweiten festen Zahl.
//
// Bewusst NICHT haengend: Stuetzen (truss_v) — dort gibt es kein "darunter",
// und alle Geraete ohne Buegel (PAR, Leisten, Strobe ...), deren Modelle
// schon um den Ursprung herum bzw. nach unten gebaut sind.
//
// Blatt-Modul: nur three.js und state.js. Wer die Haltung umschaltet, zielt
// danach selbst neu (app.js#perFrameUpdate, fixtures.js#addFixture).
import * as THREE from '../three/three.js';
import { fixtures, stageObjects } from '../state.js';

// Abstand Geraete-Ursprung <-> Unterkante der Traverse beim Andocken.
// EINE Quelle fuer docking.js (dort re-exportiert); Python-Spiegel:
// stage_definition.DOCK_HANG_OFFSET.
export const DOCK_HANG_OFFSET = 0.25;
const HAENGE_TRAEGER = { truss_h: 1 };
const HAENGE_MODELLE = { moving_head: 1, pixel_head: 1 };

const _KOPFUEBER = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1, 0, 0), Math.PI);
const _box = new THREE.Box3();
const _m = new THREE.Matrix4();

/** Haengt dieses Geraet an einer horizontalen Traverse (und kann es haengen)? */
export function haengtAnTraverse(f) {
  if (!f || !f.dockedTo || !HAENGE_MODELLE[f.type] || !f.yoke || !f.head) return false;
  const so = stageObjects[f.dockedTo];
  return !!(so && so.data && HAENGE_TRAEGER[so.data.type]);
}

// Feste Teile: alles in der Modellgruppe ausser dem Pan-Gelenk, und alles am
// Pan-Gelenk ausser dem Kopf (Drehteller, Buegel-Arme, Motoren).
function _festeTeile(f) {
  const modell = f.yoke.parent;
  return modell.children.filter(c => c !== f.yoke)
    .concat(f.yoke.children.filter(c => c !== f.head));
}

// Stehende Lage einmal merken — jede Haltung wird daraus gesetzt, nie aus der
// vorigen (kein Aufsummieren ueber mehrfaches Umschalten).
function _stand(o) {
  if (!o.userData._stand) {
    o.userData._stand = { y: o.position.y, q: o.quaternion.clone() };
  }
  return o.userData._stand;
}

// Oberkante der festen Teile im Koordinatensystem der Modellgruppe. Pan dreht
// um Y und aendert keine Hoehe, deshalb zaehlt vom Gelenk nur die Position.
function _oberkante(f) {
  let top = -Infinity;
  for (const teil of _festeTeile(f)) {
    const y0 = (teil.parent === f.yoke) ? f.yoke.position.y : 0;
    teil.updateMatrix();
    teil.traverse(m => {
      if (!m.isMesh || !m.geometry) return;
      if (!m.geometry.boundingBox) m.geometry.computeBoundingBox();
      _m.identity();
      for (let o = m; o !== teil.parent; o = o.parent) { o.updateMatrix(); _m.premultiply(o.matrix); }
      _box.copy(m.geometry.boundingBox).applyMatrix4(_m);
      top = Math.max(top, y0 + _box.max.y);
    });
  }
  return isFinite(top) ? top : 0;
}

function _setze(f, haengt) {
  const modell = f.yoke.parent;
  for (const teil of _festeTeile(f)) {
    const s = _stand(teil);
    teil.position.y = haengt ? -s.y : s.y;
    // Halbe Drehung um X = Spiegelung an der Ursprungs-Ebene fuer diese
    // (um ihre Hochachse symmetrischen) Teile; der Kegelstumpf des Sockels
    // zeigt damit mit der breiten Seite zur Traverse.
    if (haengt) teil.quaternion.copy(_KOPFUEBER).multiply(s.q);
    else teil.quaternion.copy(s.q);
  }
  const g = _stand(f.yoke), k = _stand(f.head), mo = _stand(modell);
  f.yoke.position.y = haengt ? -g.y : g.y;
  f.head.position.y = haengt ? -k.y : k.y;     // Kopf selbst bleibt ungedreht
  modell.position.y = haengt ? mo.y + DOCK_HANG_OFFSET - _oberkante(f) : mo.y;
  f._haengt = haengt;
}

/** Haltung eines Geraets an seine Montage angleichen. true = umgeschaltet. */
export function syncMountPose(f) {
  if (!f || !f.yoke || !f.head || !HAENGE_MODELLE[f.type]) return false;
  const soll = haengtAnTraverse(f);
  if (!!f._haengt === soll) return false;
  _setze(f, soll);
  return true;
}

/** Alle Geraete angleichen; `nachher(f)` laeuft je umgeschaltetem Geraet. */
export function syncMountPoses(nachher) {
  let n = 0;
  for (const fid in fixtures) {
    const f = fixtures[fid];
    if (syncMountPose(f)) { n += 1; if (nachher) nachher(f); }
  }
  return n;
}
