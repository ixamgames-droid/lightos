// VIZ-13 Schritt 3a-4: Andocken (opt-in) - Strahler rasten an Buehnen-
// Elemente ein (ehem. stage_scene.html:2432-2533). Reines Verschieben.
//   Trasse  -> Strahler haengt unten dran ('hang')
//   Boden/Plattform/... -> Strahler steht oben drauf ('top')
// Spiegelt StageDefinition.dock_target_for() in stage_definition.py.
import * as THREE from '../three/three.js';
import { fixtures, stageObjects, view } from '../state.js';
import { applyStageEmissive } from '../interaction/tools.js';
import { _stageIdFromObject } from '../interaction/picking.js';

export const DOCK_HANG_TYPES = { truss_h: 1, truss_v: 1 };
export const DOCK_TOP_TYPES  = { platform: 1, floor: 1, dj_booth: 1, speaker: 1, audience: 1 };
export const DOCK_HANG_OFFSET = 0.25;
export const DOCK_TOP_OFFSET  = 0.30;
const _dockRay = new THREE.Raycaster();
let _dockHighlightId = null;

export const dockHighlight = {
  get: () => _dockHighlightId,
  set: (v) => { _dockHighlightId = v; },
};

// Liefert {stageId, y, kind} fuer das oberste andockbare Element ueber (x,z) oder null.
export function findDockTarget(x, z) {
  const meshes = [];
  for (const id in stageObjects) meshes.push(stageObjects[id].mesh);
  if (meshes.length === 0) return null;
  _dockRay.set(new THREE.Vector3(x, 200, z), new THREE.Vector3(0, -1, 0));
  _dockRay.near = 0; _dockRay.far = 500;
  const hits = _dockRay.intersectObjects(meshes, true);
  for (const h of hits) {
    const sid = _stageIdFromObject(h.object);
    if (!sid) continue;
    const so = stageObjects[sid];
    if (!so) continue;
    const t = so.data.type;
    const sy = so.data.size.y || 0.1;
    if (DOCK_HANG_TYPES[t]) {
      return { stageId: sid, y: so.data.position.y - sy / 2 - DOCK_HANG_OFFSET, kind: 'hang' };
    }
    if (DOCK_TOP_TYPES[t]) {
      return { stageId: sid, y: so.data.position.y + sy / 2 + DOCK_TOP_OFFSET, kind: 'top' };
    }
    // wall / led_wall: ignorieren, naechsten (tieferen) Treffer pruefen
  }
  return null;
}

export function applyDockHighlight(sid) {
  if (_dockHighlightId === sid) return;
  clearDockHighlight();
  const so = stageObjects[sid];
  if (so) { applyStageEmissive(so.mesh, 0.0, 0.55, 0.18); _dockHighlightId = sid; }
}

export function clearDockHighlight() {
  if (_dockHighlightId && stageObjects[_dockHighlightId] &&
      _dockHighlightId !== view.selectedStageId) {
    applyStageEmissive(stageObjects[_dockHighlightId].mesh, 0, 0, 0);
  }
  _dockHighlightId = null;
}

export function showDockBadge(text) {
  const b = document.getElementById('dock-badge');
  const t = document.getElementById('dock-badge-text');
  if (b && t) { t.textContent = text; b.style.display = 'block'; }
}
export function hideDockBadge() {
  const b = document.getElementById('dock-badge');
  if (b) b.style.display = 'none';
}

export function _dockNameFor(sid) {
  const so = stageObjects[sid];
  if (!so) return sid;
  return so.data.name || so.data.type || sid;
}

// Verschiebt alle an `sid` angedockten Strahler mit (XZ-Delta) und setzt ihre
// Hoehe neu. Wird aufgerufen, wenn ein Buehnen-Element bewegt/skaliert wird.
export function moveDockedFixtures(sid, dxw, dzw) {
  for (const fid in fixtures) {
    const f = fixtures[fid];
    if (!f || f.dockedTo !== sid) continue;
    f.group.position.x += dxw;
    f.group.position.z += dzw;
    const dock = findDockTarget(f.group.position.x, f.group.position.z);
    if (dock && dock.stageId === sid) {
      f.group.position.y = dock.y;
    }
    if (f.icon) f.icon.position.set(f.group.position.x, 0.05, f.group.position.z);
    if (f.spotTarget) f.spotTarget.position.set(f.group.position.x, 0.0, f.group.position.z);
  }
}

export function _reportDockedFixturePositions(sid) {
  for (const fid in fixtures) {
    const f = fixtures[fid];
    if (!f || f.dockedTo !== sid) continue;
    const bridge = bridgeRef.get();
    if (bridge && bridge.fixturePositionChanged) {
      try {
        bridge.fixturePositionChanged(String(fid),
          f.group.position.x, f.group.position.y, f.group.position.z);
      } catch (e) {}
    }
  }
}

// ── Spaet-Bindung (bridge entsteht erst beim WebChannel-Connect) ───────────
export const bridgeRef = { get: () => null };
export function wireDockingLateBindings({ getBridge }) {
  bridgeRef.get = getBridge;
}

// stage/stage_objects.js#removeStageObject braucht Zugriff auf
// _dockHighlightId (Design-Dokument "Kern-Gotcha") - ueber wireStageObjects-
// LateBindings verdrahtet, siehe app.js.
