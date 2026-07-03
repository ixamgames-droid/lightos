// VIZ-13 Schritt 3a-4: Picking (ehem. stage_scene.html:2335-2424).
// raycaster/mouse waren im Original modul-globaler Scope-State, von dem u.a.
// stage/stage_objects.js#pickResizeHandle und interaction/pointer.js lesen -
// hier als geteilte const-Objekte exportiert (Referenz bleibt stabil, wird
// wie im Original nur mutiert: raycaster.setFromCamera(...), mouse.x=...).
import * as THREE from '../three/three.js';
import { renderer } from '../scene/renderer.js';
import { fixtures, stageObjects, topDownIcons, settings, view } from '../state.js';

export const raycaster = new THREE.Raycaster();
export const mouse = new THREE.Vector2();

export function setMouseFromCoords(clientX, clientY) {
  const rect = renderer.domElement.getBoundingClientRect();
  mouse.x = ((clientX - rect.left) / rect.width) * 2 - 1;
  mouse.y = -((clientY - rect.top) / rect.height) * 2 + 1;
}

export function setMouseFromEvent(e) {
  setMouseFromCoords(e.clientX, e.clientY);
}

export function intersectGround() {
  raycaster.setFromCamera(mouse, view.activeCam);
  const plane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
  const out = new THREE.Vector3();
  raycaster.ray.intersectPlane(plane, out);
  return out;
}

export function pickFixture() {
  raycaster.setFromCamera(mouse, view.activeCam);
  // For 2D mode prefer the top-down icons (their body meshes are in fixtureMeshes? No, we rebuild only on add/remove - icons aren't in that list. Build dynamic list here.)
  const meshes = [];
  if (view.mode === '2D') {
    for (const fid in topDownIcons) {
      topDownIcons[fid].traverse(o => { if (o.isMesh) { o.userData.fid = Number(fid); meshes.push(o); } });
    }
  } else {
    for (const fid in fixtures) {
      fixtures[fid].group.traverse(o => { if (o.isMesh) { o.userData.fid = Number(fid); meshes.push(o); } });
    }
  }
  const hits = raycaster.intersectObjects(meshes, true);
  if (hits.length > 0) return hits[0].object.userData.fid;
  return null;
}

export function pickStageObject() {
  raycaster.setFromCamera(mouse, view.activeCam);
  const meshes = Object.values(stageObjects).map(s => s.mesh);
  // recursive=true: Truss-Gruppen tragen ihre Geometrie in Kind-Meshes.
  const hits = raycaster.intersectObjects(meshes, true);
  if (hits.length > 0) {
    const sid = _stageIdFromObject(hits[0].object);
    if (sid) return sid;
  }
  // Touch-Fallback: naechstes Element-Zentrum innerhalb Bildschirm-Toleranz,
  // damit duenne Trassen auch per Finger antippbar sind.
  return _pickStageObjectNear(48);
}

export function _pickStageObjectNear(tolPx) {
  const rect = renderer.domElement.getBoundingClientRect();
  const mx = (mouse.x + 1) / 2 * rect.width;
  const my = (1 - mouse.y) / 2 * rect.height;
  let best = null, bestD = tolPx;
  const v = new THREE.Vector3();
  for (const id in stageObjects) {
    const so = stageObjects[id];
    // Naehe-Fallback NUR fuer duenne Trassen (Finger treffen die Gitterstreben
    // schwer). Grossflaechige Elemente (Plattform/Boden/...) brauchen ihn nicht —
    // sonst zaehlen leere Taps daneben als Treffer und brechen den Doppeltipp-
    // Reset / das Deselektieren.
    if (so.data.type !== 'truss_h' && so.data.type !== 'truss_v') continue;
    v.set(so.data.position.x, so.data.position.y, so.data.position.z).project(view.activeCam);
    if (v.z > 1) continue;  // hinter der Kamera
    const sx = (v.x + 1) / 2 * rect.width;
    const sy = (1 - v.y) / 2 * rect.height;
    const d = Math.hypot(sx - mx, sy - my);
    if (d < bestD) { bestD = d; best = id; }
  }
  return best;
}

export function _stageIdFromObject(obj) {
  let o = obj;
  while (o) {
    if (o.userData && o.userData.stageId) return o.userData.stageId;
    o = o.parent;
  }
  return null;
}

export function snap(v) {
  if (!settings.snapToGrid) return v;
  return Math.round(v / settings.gridStep) * settings.gridStep;
}
