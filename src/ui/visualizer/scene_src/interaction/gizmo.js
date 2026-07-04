// VIZ-13 Schritt 3b-G: Eigenbau Move/Rotate-Gizmo (OHNE externe Controls,
// Davids Entscheidung). Selbstgebautes Transform-Gizmo am Auswahl-Schwerpunkt:
// 3 Achsen-Pfeile (X/Y/Z, eingefaerbt) fuer Translation + 3 Ringe fuer Rotation.
//
// KERNPUNKT: strukturell zoom-korrekt. Translation projiziert den Pointer-Strahl
// auf die Welt-Achse (closest-point-on-line) und misst ein WELT-Delta; Rotation
// schneidet den Strahl mit der Achsen-Ebene und misst einen WELT-Winkel. Das
// ersetzt die alten move_y/rotate-Werkzeuge mit ihren fixen Pixel-Faktoren
// (dY*0.02, dYaw*0.5 = die zoom-abhaengigen "25-m-Sprung"-Bugs).
//
// Das Gizmo ist ACHSEN-ausgerichtet (Welt-Achsen, nicht objekt-lokal) — wie
// grandMA3/Blender im World-Modus: vorhersehbare Bewegung. Sichtbarkeit/Position/
// Skala werden pro Frame in app.js#animate ueber attachGizmoToSelection() gesetzt
// (kein Wiring in tools.js noetig -> kein Import-Zyklus).
//
// Siehe docs/VIZ13_JS_NEUAUFBAU_DESIGN.md 3b-G.
import * as THREE from '../three/three.js';
import { scene } from '../scene/renderer.js';
import { view, fixtures } from '../state.js';
import { raycaster, mouse } from './picking.js';
import { perspectiveCam } from '../camera/cameras.js';

// Feste Welt-Achsen-Einheitsvektoren (Translation projiziert hierauf).
export const GIZMO_AXES = {
  x: new THREE.Vector3(1, 0, 0),
  y: new THREE.Vector3(0, 1, 0),
  z: new THREE.Vector3(0, 0, 1),
};

// Orthonormale In-Ebenen-Basis je Rotationsachse (right-hand: a × ref = bit).
// atan2(v·bit, v·ref) = Winkel um die Achse. Hartkodiert (nur 3 Welt-Achsen).
const ROT_BASIS = {
  x: { ref: new THREE.Vector3(0, 1, 0), bit: new THREE.Vector3(0, 0, 1) },
  y: { ref: new THREE.Vector3(0, 0, 1), bit: new THREE.Vector3(1, 0, 0) },
  z: { ref: new THREE.Vector3(1, 0, 0), bit: new THREE.Vector3(0, 1, 0) },
};

const AXIS_COLOR = { x: 0xff5555, y: 0x66dd66, z: 0x5599ff };

// Basis-Groessen in Gizmo-Einheiten (vor der Kamera-Distanz-Skalierung).
const SHAFT_LEN = 1.5, SHAFT_R = 0.045, HEAD_LEN = 0.42, HEAD_R = 0.13;
// Rotations-Ringe bewusst AUSSERHALB der Translations-Pfeile (die bis ~1.92
// reichen): sonst ueberlappen Ring und Schaft raeumlich -> mehrdeutiges Picking
// (der Raycast trifft den falschen Handle). Ringe umschliessen die Pfeile
// (grandMA3/Blender-Muster).
const RING_INNER = 2.05, RING_OUTER = 2.25;

export const gizmoRoot = new THREE.Group();
gizmoRoot.visible = false;
scene.add(gizmoRoot);

// Pickbare Handle-Meshes (userData.gizmoMode + userData.axis).
const _handles = [];

function _handleMat(color, opacity) {
  // depthTest:false -> Handles zeichnen/picken IMMER ueber den Fixtures (nie
  // verdeckt), renderOrder hoch. transparent fuer weiches Ueberzeichnen.
  return new THREE.MeshBasicMaterial({
    color, side: THREE.DoubleSide, depthTest: false,
    transparent: true, opacity: opacity,
  });
}

function _buildTranslateHandle(axisKey) {
  const g = new THREE.Group();
  const col = AXIS_COLOR[axisKey];
  const shaft = new THREE.Mesh(
    new THREE.CylinderGeometry(SHAFT_R, SHAFT_R, SHAFT_LEN, 12), _handleMat(col, 0.9));
  shaft.position.y = SHAFT_LEN / 2;
  const head = new THREE.Mesh(
    new THREE.ConeGeometry(HEAD_R, HEAD_LEN, 16), _handleMat(col, 0.9));
  head.position.y = SHAFT_LEN + HEAD_LEN / 2;
  g.add(shaft); g.add(head);
  // Zylinder/Kegel zeigen entlang +Y -> auf die Zielachse drehen.
  if (axisKey === 'x') g.rotation.z = -Math.PI / 2;   // +Y -> +X
  else if (axisKey === 'z') g.rotation.x = Math.PI / 2; // +Y -> +Z
  g.traverse(o => {
    if (o.isMesh) {
      o.userData.gizmoMode = 'translate';
      o.userData.axis = axisKey;
      o.renderOrder = 999;
    }
  });
  g.children.forEach(m => m.traverse(o => { if (o.isMesh) _handles.push(o); }));
  return g;
}

function _buildRotateHandle(axisKey) {
  const col = AXIS_COLOR[axisKey];
  const ring = new THREE.Mesh(
    new THREE.RingGeometry(RING_INNER, RING_OUTER, 48), _handleMat(col, 0.7));
  // RingGeometry-Normale = +Z. Fuer Rotation UM die Achse a muss die Ring-Ebene
  // senkrecht zu a stehen -> Ring-Normale = a.
  if (axisKey === 'x') ring.rotation.y = Math.PI / 2;      // Normale +Z -> +X
  else if (axisKey === 'y') ring.rotation.x = -Math.PI / 2; // Normale +Z -> +Y
  ring.userData.gizmoMode = 'rotate';
  ring.userData.axis = axisKey;
  ring.renderOrder = 998;
  _handles.push(ring);
  return ring;
}

for (const ax of ['x', 'y', 'z']) {
  gizmoRoot.add(_buildTranslateHandle(ax));
  gizmoRoot.add(_buildRotateHandle(ax));
}

// ── Sichtbarkeit / Position / Skala (pro Frame aus animate aufgerufen) ───────
const _c = new THREE.Vector3();

function _selectionCentroid(out) {
  out.set(0, 0, 0);
  let n = 0;
  for (const fid of view.selectedFids) {
    const f = fixtures[fid];
    if (f && f.group) { out.add(f.group.position); n++; }
  }
  if (n) out.divideScalar(n);
  return n;
}

// Konstante Bildschirmgroesse: Skala an die Kamera-Distanz zum Gizmo koppeln
// (perspektivisch). view.radius taugt NICHT (nur Kamera<->camTarget); das Gizmo
// steht i.d.R. abseits des Targets -> echte Distanz messen.
const _SCREEN_SCALE = 0.11;

export function attachGizmoToSelection() {
  // Gizmo nur im 3D-Bau-Modus, im "Bewegen"-Werkzeug (move_xz), mit Auswahl.
  // In aim/trace ist das Gizmo AUS (sonst schluckt es Ziel-/Nachfahr-Klicks nahe
  // dem Schwerpunkt). Waehrend eines Gizmo-Drags bleibt die Bedingung erfuellt
  // -> das Gizmo folgt dem live wandernden Schwerpunkt.
  const gate = (view.mode === '3D' && view.editMode === 'edit'
                && view.editTool === 'move_xz' && view.selectedFids.length > 0);
  if (!gate) { gizmoRoot.visible = false; return; }
  const n = _selectionCentroid(_c);
  if (!n) { gizmoRoot.visible = false; return; }
  gizmoRoot.position.copy(_c);
  const dist = perspectiveCam.position.distanceTo(gizmoRoot.position);
  const s = Math.max(0.001, dist * _SCREEN_SCALE);
  gizmoRoot.scale.set(s, s, s);
  gizmoRoot.visible = true;
}

// ── Picking ──────────────────────────────────────────────────────────────────
export function pickGizmoHandle() {
  if (!gizmoRoot.visible) return null;
  // Handle-Welt-Matrizen sicher aktuell (Position/Skala werden in attachGizmoTo-
  // Selection gesetzt; ein Raycast VOR dem naechsten Render saehe sonst veraltete
  // Handle-Positionen -> Fehlgriff).
  gizmoRoot.updateMatrixWorld(true);
  raycaster.setFromCamera(mouse, view.activeCam);
  const hits = raycaster.intersectObjects(_handles, false);
  if (!hits.length) return null;
  const h = hits[0].object;
  return { mode: h.userData.gizmoMode, axis: h.userData.axis };
}

// ── Drag-Mathematik (zoom/perspektiv-korrekt — nutzt den Pointer-Strahl) ─────
const _w0 = new THREE.Vector3();

// Parametrischer Wert t (Welt-Einheiten) auf der Achse a durch A, der dem
// aktuellen Pointer-Strahl am naechsten liegt (closest point between two lines).
// mouse muss vorher via setMouseFromCoords gesetzt sein (Aufrufer tut das).
export function axisParamUnderPointer(A, a) {
  raycaster.setFromCamera(mouse, view.activeCam);
  const P = raycaster.ray.origin, d = raycaster.ray.direction; // d normalisiert
  _w0.subVectors(P, A);                          // w0 = P - A (Vorzeichen kritisch:
  // A-P wuerde den Parameter negieren -> Handle liefe der Maus entgegen)
  const b = d.dot(a), dd = d.dot(_w0), ae = a.dot(_w0);
  const denom = 1 - b * b;                       // 0 nur wenn Strahl ∥ Achse
  return Math.abs(denom) < 1e-6 ? ae : (ae - b * dd) / denom;
}

// Winkel (rad) des Pointer-Treffers in der Ebene mit Normale = Achse a durch C.
// Rueckgabe null, wenn der Strahl parallel zur Ebene liegt.
const _plane = new THREE.Plane();
const _hit = new THREE.Vector3();
const _v = new THREE.Vector3();
export function rotationAngleUnderPointer(C, axisKey) {
  const a = GIZMO_AXES[axisKey];
  raycaster.setFromCamera(mouse, view.activeCam);
  _plane.setFromNormalAndCoplanarPoint(a, C);
  if (!raycaster.ray.intersectPlane(_plane, _hit)) return null;
  _v.subVectors(_hit, C);
  const basis = ROT_BASIS[axisKey];
  return Math.atan2(_v.dot(basis.bit), _v.dot(basis.ref));
}
