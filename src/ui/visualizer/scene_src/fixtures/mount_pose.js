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
// VIZ-103: „Unterkante der Traverse“ ist die WIRKLICHE Unterkante des
// Traegers (position.y - size.y / 2), nicht „Ursprung + DOCK_HANG_OFFSET“.
// Beides ist nur gleich, wenn die Hoehe frisch vom Andocken stammt. In der
// Buehnen-Show 2026 liegt der Ursprung 0,20 m statt 0,25 m unter der
// Unterkante (0,4 m dicke Traversen) — der Sockel ragte 5 cm in die Traverse.
// Dasselbe passiert, wenn jemand die Hoehe von Hand eintraegt oder die
// Traverse nachtraeglich dicker bzw. hoeher macht. Die gespeicherte Position
// bleibt auch hier unangetastet; nur das Modell rueckt an die Kante.
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

// VIZ-103: so weit unter der Unterkante darf der Ursprung liegen, damit das
// Modell an die Kante rueckt. Darueber hinaus (und wenn der Ursprung UEBER der
// Traverse liegt) hat jemand das Geraet bewusst woanders hingesetzt, die
// Bindung aber stehen lassen: dann bleibt das Modell im festen Abstand bei
// seiner gespeicherten Position, statt meterweit davon entfernt zu erscheinen.
const HAENGE_NAH = 2 * DOCK_HANG_OFFSET;
const _EPS = 1e-6;

// Abstand Geraete-Ursprung -> Unterkante des Traegers, an dem das Geraet haengt
// (positiv = Ursprung liegt darunter). Fehlen Masse, gilt der feste Abstand.
function _haengeAbstand(f) {
  const so = stageObjects[f.dockedTo];
  const d = so && so.data;
  const py = d && d.position ? +d.position.y : NaN;
  const sy = d && d.size ? +d.size.y : NaN;
  if (!isFinite(py) || !isFinite(sy) || sy < 0) return DOCK_HANG_OFFSET;
  const abstand = (py - sy / 2) - f.group.position.y;
  if (!isFinite(abstand) || abstand > HAENGE_NAH + _EPS || abstand < -sy - _EPS) {
    return DOCK_HANG_OFFSET;
  }
  return abstand;
}

function _setze(f, haengt, abstand) {
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
  modell.position.y = haengt ? mo.y + abstand - _oberkante(f) : mo.y;
  f._haengt = haengt;
  f._haengeAbstand = haengt ? abstand : 0;
}

/** Haltung eines Geraets an seine Montage angleichen. true = umgeschaltet
 *  ODER nachgezogen (VIZ-103: Traverse oder Geraetehoehe haben sich geaendert,
 *  waehrend es haengt) — der Aufrufer zielt in beiden Faellen neu. */
export function syncMountPose(f) {
  if (!f || !f.yoke || !f.head || !HAENGE_MODELLE[f.type]) return false;
  const soll = haengtAnTraverse(f);
  const abstand = soll ? _haengeAbstand(f) : 0;
  if (!!f._haengt === soll
      && (!soll || Math.abs((f._haengeAbstand || 0) - abstand) < _EPS)) return false;
  _setze(f, soll, abstand);
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
