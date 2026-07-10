// VIZ-13 Schritt 3a-4: Custom stage object builders + CRUD
// (ehem. stage_scene.html:431-810, 869-935). Reines Verschieben.
import * as THREE from '../three/three.js';
import { scene } from '../scene/renderer.js';
import { disposeObj } from '../scene/grid_floor.js';
import { loadModel, fitModelToSize } from '../scene/model_loader.js';
import { fixtures, stageObjects, view } from '../state.js';
import { raycaster, mouse } from '../interaction/picking.js';
import { requestRender } from '../scene/render_loop.js';  // VIZ-13 3c-2

// stageObjIdCounter bleibt hier (kein geteilter Modul-State laut Design-
// Dokument "Kern-Gotcha" - nur von createStageObject genutzt).
let stageObjIdCounter = 1;

export const STAGE_BLUEPRINTS = {
  floor: {
    label: 'Boden / Floor',
    defaultSize: { x: 14, y: 0.1, z: 10 },
    defaultColor: '#1c1c1c',
    build: (size, color) => {
      const m = new THREE.Mesh(
        new THREE.BoxGeometry(size.x, size.y, size.z),
        new THREE.MeshStandardMaterial({ color: color, roughness: 0.95, metalness: 0.0 })
      );
      m.receiveShadow = true;
      return m;
    },
  },
  platform: {
    label: 'Stage Platform',
    defaultSize: { x: 6, y: 0.4, z: 4 },
    defaultColor: '#332520',
    build: (size, color) => new THREE.Mesh(
      new THREE.BoxGeometry(size.x, size.y, size.z),
      new THREE.MeshStandardMaterial({ color: color, roughness: 0.9 })
    ),
  },
  truss_h: {
    label: 'Truss horizontal',
    defaultSize: { x: 4, y: 0.3, z: 0.3 },
    defaultColor: '#999999',
    build: (size, color) => {
      const group = new THREE.Group();
      const placeholder = new THREE.Mesh(
        new THREE.BoxGeometry(size.x, size.y, size.z),
        new THREE.MeshStandardMaterial({ color: color, metalness: 0.7, roughness: 0.4 })
      );
      placeholder.castShadow = true;
      placeholder.receiveShadow = true;
      group.add(placeholder);
      group.userData.isTrussGroup = true;
      group.userData.color = color;
      group.userData.size = { x: size.x, y: size.y, z: size.z };
      loadModel('assets/models/stage/truss_square_2m.obj', (model) => {
        if (!model) return;
        fitModelToSize(model, size);
        model.traverse(c => {
          if (c.isMesh) {
            c.material = new THREE.MeshStandardMaterial({ color: color, metalness: 0.7, roughness: 0.4 });
            c.castShadow = true;
            c.receiveShadow = true;
          }
        });
        group.remove(placeholder);
        if (placeholder.geometry) placeholder.geometry.dispose();
        if (placeholder.material) placeholder.material.dispose();
        group.add(model);
        // 3c-2: ASYNCHRONER Modell-Tausch (Platzhalter -> OBJ) kommt NACH dem
        // createStageObject-Frame an — ohne eigenen requestRender bliebe der
        // Platzhalter-Quader bis zum naechsten fremden Render sichtbar.
        requestRender();
      });
      return group;
    },
  },
  truss_v: {
    label: 'Truss vertical',
    defaultSize: { x: 0.3, y: 4, z: 0.3 },
    defaultColor: '#999999',
    build: (size, color) => {
      const group = new THREE.Group();
      const placeholder = new THREE.Mesh(
        new THREE.BoxGeometry(size.x, size.y, size.z),
        new THREE.MeshStandardMaterial({ color: color, metalness: 0.7, roughness: 0.4 })
      );
      placeholder.castShadow = true;
      placeholder.receiveShadow = true;
      group.add(placeholder);
      group.userData.isTrussGroup = true;
      group.userData.color = color;
      group.userData.size = { x: size.x, y: size.y, z: size.z };
      loadModel('assets/models/stage/truss_square_2m.obj', (model) => {
        if (!model) return;
        // truss_square_2m.obj has its long axis along X. Rotate 90deg around Z so it becomes Y-vertical.
        model.rotation.z = Math.PI / 2;
        // After rotation, X<->Y swap for sizing; pass swapped target.
        fitModelToSize(model, { x: size.y, y: size.x, z: size.z });
        model.traverse(c => {
          if (c.isMesh) {
            c.material = new THREE.MeshStandardMaterial({ color: color, metalness: 0.7, roughness: 0.4 });
            c.castShadow = true;
            c.receiveShadow = true;
          }
        });
        group.remove(placeholder);
        if (placeholder.geometry) placeholder.geometry.dispose();
        if (placeholder.material) placeholder.material.dispose();
        group.add(model);
        requestRender();  // 3c-2: asynchroner Modell-Tausch (s. truss_h)
      });
      return group;
    },
  },
  wall: {
    label: 'Wall / Backdrop',
    defaultSize: { x: 10, y: 6, z: 0.2 },
    defaultColor: '#222230',
    build: (size, color) => new THREE.Mesh(
      new THREE.BoxGeometry(size.x, size.y, size.z),
      new THREE.MeshStandardMaterial({ color: color, roughness: 1.0, side: THREE.DoubleSide })
    ),
  },
  led_wall: {
    label: 'LED Wall',
    defaultSize: { x: 8, y: 4.5, z: 0.15 },
    defaultColor: '#080820',
    build: (size, color) => new THREE.Mesh(
      new THREE.BoxGeometry(size.x, size.y, size.z),
      new THREE.MeshBasicMaterial({ color: color })
    ),
  },
  speaker: {
    label: 'Speaker Stack',
    defaultSize: { x: 1.4, y: 4.5, z: 1.4 },
    defaultColor: '#111111',
    build: (size, color) => new THREE.Mesh(
      new THREE.BoxGeometry(size.x, size.y, size.z),
      new THREE.MeshStandardMaterial({ color: color, roughness: 0.9 })
    ),
  },
  audience: {
    label: 'Audience Area',
    defaultSize: { x: 12, y: 0.05, z: 8 },
    defaultColor: '#0c0c10',
    build: (size, color) => new THREE.Mesh(
      new THREE.BoxGeometry(size.x, size.y, size.z),
      new THREE.MeshStandardMaterial({ color: color, roughness: 1.0 })
    ),
  },
  dj_booth: {
    label: 'DJ Booth',
    defaultSize: { x: 2.4, y: 1.2, z: 1.0 },
    defaultColor: '#1a1a25',
    build: (size, color) => new THREE.Mesh(
      new THREE.BoxGeometry(size.x, size.y, size.z),
      new THREE.MeshStandardMaterial({ color: color, roughness: 0.7, metalness: 0.3 })
    ),
  },
};

export function createStageObject(type, position, size, color, rotation, providedId, name) {
  const bp = STAGE_BLUEPRINTS[type];
  if (!bp) return null;
  const sz = size || { ...bp.defaultSize };
  const cl = color || bp.defaultColor;
  const mesh = bp.build(sz, cl);
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  if (position) mesh.position.set(
    (position.x != null) ? position.x : 0,
    (position.y != null) ? position.y : (sz.y / 2),
    (position.z != null) ? position.z : 0
  );
  else mesh.position.set(0, sz.y / 2, 0);
  mesh.rotation.y = rotation || 0;
  // ID-FIX: Python-seitige IDs respektieren (sonst stimmen select/update nicht ueberein)
  let id = (providedId && typeof providedId === 'string') ? providedId : ('stage-' + (stageObjIdCounter++));
  // Falls Kollision (sehr unwahrscheinlich): Suffix dranhaengen
  if (stageObjects[id]) id = id + '_' + (stageObjIdCounter++);
  mesh.userData.stageId = id;
  mesh.userData.isStageObject = true;
  mesh.userData.stageType = type;
  scene.add(mesh);
  stageObjects[id] = {
    mesh,
    data: {
      id, type,
      position: { x: mesh.position.x, y: mesh.position.y, z: mesh.position.z },
      size: { ...sz },
      rotation: mesh.rotation.y,
      color: cl,
      name: name || '',
    }
  };
  // Falls aktuell 2D-Ansicht: frisch erzeugtes Objekt sofort 2D-stylen.
  applyStageObject2DStyle(id, view.mode === '2D');
  notifyStageListChanged();
  requestRender();  // 3c-2 Dirty-Quelle 4 (Stage-CRUD: Objekt hinzugefuegt)
  return id;
}

// Update existing stage object in-place (geometry, color, position, rotation)
// Returns true if updated, false if not found
export function updateStageObjectProps(id, props) {
  const so = stageObjects[id];
  if (!so) return false;
  const data = so.data;

  // Size: replace geometry (Mesh) or rebuild scale (Group with loaded model / truss)
  if (props.size) {
    const sz = props.size;
    if (sz.x != null) data.size.x = sz.x;
    if (sz.y != null) data.size.y = sz.y;
    if (sz.z != null) data.size.z = sz.z;
    if (so.mesh.isMesh && so.mesh.geometry) {
      so.mesh.geometry.dispose();
      so.mesh.geometry = new THREE.BoxGeometry(data.size.x, data.size.y, data.size.z);
    } else if (so.mesh.isGroup) {
      // Rebuild the group entirely (cheap - blueprint creates placeholder + reloads cached model)
      const type = data.type;
      const bp = STAGE_BLUEPRINTS[type];
      if (bp) {
        const newGroup = bp.build({ x: data.size.x, y: data.size.y, z: data.size.z }, data.color);
        newGroup.position.copy(so.mesh.position);
        newGroup.rotation.copy(so.mesh.rotation);
        newGroup.userData.stageId = data.id;
        newGroup.userData.isStageObject = true;
        newGroup.userData.stageType = type;
        scene.remove(so.mesh);
        so.mesh.traverse(disposeObj);
        scene.add(newGroup);
        so.mesh = newGroup;
        // Auswahl-BoxHelper zeigte noch auf das alte (entfernte/disposte) Mesh ->
        // INLINE fuer newGroup neu aufbauen, sonst friert der gelbe Auswahlrahmen
        // auf der alten Geometrie ein. (Bewusst NICHT updateOutlines() — das wuerde
        // pro Rasterschritt Selektions-Signale an Python feuern + den Banner-DOM neu
        // bauen.) Sichtbarkeit des alten Helpers uebernehmen (selektiert vs. nicht).
        if (so._helper) {
          const wasVisible = so._helper.visible;
          scene.remove(so._helper);
          if (so._helper.geometry) so._helper.geometry.dispose();
          if (so._helper.material) so._helper.material.dispose();
          so._helper = new THREE.BoxHelper(so.mesh, 0xffd700);
          if (so._helper.material) {
            so._helper.material.depthTest = false;
            so._helper.material.transparent = true;
            so._helper.material.opacity = 1.0;
          }
          so._helper.visible = wasVisible;
          scene.add(so._helper);
          so._helper.update();
        }
      }
    }
  }

  // Color: update material (works on Mesh or recursively on Group)
  if (props.color) {
    data.color = props.color;
    const col = new THREE.Color(props.color);
    if (so.mesh.isMesh && so.mesh.material) {
      so.mesh.material.color = col;
    } else if (so.mesh.isGroup) {
      so.mesh.traverse(c => {
        if (c.isMesh && c.material && c.material.color) {
          c.material.color = col.clone();
        }
      });
      so.mesh.userData.color = props.color;
    }
  }

  // Position
  if (props.position) {
    const p = props.position;
    if (p.x != null) { data.position.x = p.x; so.mesh.position.x = p.x; }
    if (p.y != null) { data.position.y = p.y; so.mesh.position.y = p.y; }
    if (p.z != null) { data.position.z = p.z; so.mesh.position.z = p.z; }
  }

  // Rotation
  if (props.rotation != null) {
    data.rotation = props.rotation;
    so.mesh.rotation.y = props.rotation;
  }

  // Name
  if (props.name != null) data.name = props.name;

  // 2D-View Top-Color update
  updateStageObject2D(id);
  requestRender();  // 3c-2 Dirty-Quelle 4 (Stage-CRUD: Groesse/Farbe/Transform)
  return true;
}

// In 2D-View: render stage objects with distinct top-down colors per type
export const STAGE_2D_COLORS = {
  floor:     { fill: 0x2a2a2a, edge: 0x6a6a6a, label: 'BODEN' },
  platform:  { fill: 0x6b4a3a, edge: 0xc7906a, label: 'PLATFORM' },
  truss_h:   { fill: 0x999999, edge: 0xcccccc, label: 'TRUSS H' },
  truss_v:   { fill: 0x999999, edge: 0xcccccc, label: 'TRUSS V' },
  wall:      { fill: 0x3a3a55, edge: 0x6a6a8a, label: 'WALL' },
  led_wall:  { fill: 0x202060, edge: 0x4080ff, label: 'LED' },
  speaker:   { fill: 0x1a1a1a, edge: 0xff8800, label: 'SPK' },
  audience:  { fill: 0x4a3a2a, edge: 0xb89060, label: 'AUDIENCE' },
  dj_booth:  { fill: 0x2a2a4a, edge: 0x60a0ff, label: 'DJ' },
};

export function updateStageObject2D(id) {
  // Buehnen-Objekt an den aktuellen View-Modus anpassen (siehe 2D-Style unten).
  applyStageObject2DStyle(id, view.mode === '2D');
}

// ── 2D-OCCLUSION-FIX ─────────────────────────────────────────────────────────
// Im 2D-Top-Down rendern wir User-Buehnenobjekte (Boden/Plattform/Truss/…) NICHT
// mehr als solide Boxen — sonst verdecken sie die flachen Fixture-Icons. Statt-
// dessen: halbtransparent + depthWrite aus, so dass die Grundflaeche als dezenter
// Umriss sichtbar bleibt, die Strahler darunter aber durchscheinen. Im 3D wird
// der Originalzustand des Materials wiederhergestellt.
export function _setMeshMat2D(m, is2D) {
  if (!m || !m.isMesh || !m.material) return;
  const mats = Array.isArray(m.material) ? m.material : [m.material];
  for (const mat of mats) {
    if (!mat) continue;
    if (mat.userData.__orig2d === undefined) {
      mat.userData.__orig2d = {
        transparent: mat.transparent,
        opacity: mat.opacity,
        depthWrite: mat.depthWrite,
      };
    }
    if (is2D) {
      mat.transparent = true;
      mat.opacity = 0.22;
      mat.depthWrite = false;
    } else {
      const o = mat.userData.__orig2d;
      mat.transparent = o.transparent;
      mat.opacity = o.opacity;
      mat.depthWrite = o.depthWrite;
    }
    mat.needsUpdate = true;
  }
  m.renderOrder = is2D ? 1 : 0;
}

export function applyStageObject2DStyle(id, is2D) {
  const so = stageObjects[id];
  if (!so || !so.mesh) return;
  if (so.mesh.isMesh) _setMeshMat2D(so.mesh, is2D);
  else so.mesh.traverse(c => { if (c.isMesh) _setMeshMat2D(c, is2D); });
  _syncFootprintOutline(so, is2D);
  requestRender();  // 3c-2: Material-Styles/Footprint-Umriss geaendert
}

// 3c-1: Grundriss-Umriss — im 2D-Plan bekommt jedes Buehnenobjekt eine klare
// Aussenkante in seiner Typ-Farbe (STAGE_2D_COLORS.edge, vorher ungenutzt).
// Der 0.22-Opacity-Fill allein war auf dem dunklen Boden kaum lesbar. Als
// Kind von so.mesh folgt der Umriss Position/Rotation live; bei Groessen-/
// Group-Rebuilds wird er hier idempotent neu erzeugt (applyStageObject2DStyle
// laeuft nach jedem createStageObject/updateStageObjectProps/Modus-Wechsel).
function _syncFootprintOutline(so, is2D) {
  if (so._outline2d) {
    if (so._outline2d.parent) so._outline2d.parent.remove(so._outline2d);
    if (so._outline2d.geometry) so._outline2d.geometry.dispose();
    if (so._outline2d.material) so._outline2d.material.dispose();
    so._outline2d = null;
  }
  if (!is2D) return;
  const sz = (so.data && so.data.size) || {};
  const hx = (sz.x || 1) / 2, hz = (sz.z || 1) / 2;
  const y = (sz.y || 0) / 2 + 0.02;   // knapp ueber der Oberkante (depthTest ist eh aus)
  const pts = [
    new THREE.Vector3(-hx, y, -hz), new THREE.Vector3(hx, y, -hz),
    new THREE.Vector3(hx, y, hz), new THREE.Vector3(-hx, y, hz),
  ];
  const colors = STAGE_2D_COLORS[so.data && so.data.type];
  const line = new THREE.LineLoop(
    new THREE.BufferGeometry().setFromPoints(pts),
    new THREE.LineBasicMaterial({
      color: (colors && colors.edge) || 0x8a8fa0,
      transparent: true, opacity: 0.95, depthTest: false,
    })
  );
  line.renderOrder = 2;   // ueber den 2D-Fills (1), unter den Fixture-Icons (3)
  line.userData.isFootprintOutline = true;
  // Vom Raycast ausnehmen: pickStageObject/findDockTarget/Zielen laufen
  // rekursiv ueber so.mesh, und three.js raycastet Lines mit ~1 m Threshold —
  // der Umriss wuerde Picking/Docking sonst unpraezise machen.
  line.raycast = function () {};
  so.mesh.add(line);
  so._outline2d = line;
}

export function removeStageObject(id) {
  const so = stageObjects[id];
  if (!so) return;
  // BoxHelper + Label entfernen
  if (so._helper) {
    scene.remove(so._helper);
    if (so._helper.geometry) so._helper.geometry.dispose();
    if (so._helper.material) so._helper.material.dispose();
    so._helper = null;
  }
  if (so._label) {
    scene.remove(so._label);
    if (so._label.material && so._label.material.map) so._label.material.map.dispose();
    if (so._label.material) so._label.material.dispose();
    so._label = null;
  }
  // 3c-1: Grundriss-Umriss mit-disposen (disposeObj traversiert nicht)
  _syncFootprintOutline(so, false);
  scene.remove(so.mesh);
  disposeObj(so.mesh);
  delete stageObjects[id];
  if (view.selectedStageId === id) {
    view.selectedStageId = null;
    clearResizeHandles();
  }
  if (dockHighlightRef.get() === id) dockHighlightRef.set(null);
  // Angedockte Strahler loesen (bleiben an letzter Position)
  for (const fid in fixtures) {
    const f = fixtures[fid];
    if (f && f.dockedTo === id) {
      f.dockedTo = null;
      const bridge = bridgeRef.get();
      if (bridge && bridge.fixtureDockChanged) {
        try { bridge.fixtureDockChanged(String(fid), ''); } catch (e) {}
      }
    }
  }
  updateOutlinesRef.get()();
  notifyStageListChanged();
  requestRender();  // 3c-2 Dirty-Quelle 4 (Stage-CRUD: Objekt entfernt)
}

export function clearStageObjects() {
  // Snapshot der IDs - sonst mutieren wir waehrend Iteration
  const ids = Object.keys(stageObjects).slice();
  for (const id of ids) removeStageObject(id);
  // Defensiv: Falls etwas haengt
  for (const id in stageObjects) delete stageObjects[id];
  clearResizeHandles();
  clearStageLabels();
}

// ============================================================================
// Resize-Handles (4 gelbe Wuerfel an den Box-Ecken, 2D-Editmodus)
// ============================================================================
export let resizeHandles = [];          // Array von Mesh-Handles (in scene)
export let resizeModeEnabled = false;   // Toggle: nur wenn aktiv erscheinen Resize-Handles

export function setResizeModeEnabled(on) {
  resizeModeEnabled = !!on;
  updateResizeHandles();
}

export function clearResizeHandles() {
  if (resizeHandles.length) requestRender();  // 3c-2: Handles verschwinden
  for (const h of resizeHandles) {
    scene.remove(h);
    if (h.geometry) h.geometry.dispose();
    if (h.material) h.material.dispose();
  }
  resizeHandles.length = 0;
}

export function updateResizeHandles() {
  clearResizeHandles();
  // Resize-Handles nur wenn explizit aktiviert (Toggle "Groesse anpassen")
  if (!resizeModeEnabled) return;
  if (view.editMode !== 'stage' || !view.selectedStageId) return;
  const so = stageObjects[view.selectedStageId];
  if (!so) return;
  const pos = so.mesh.position;
  const halfX = so.data.size.x / 2;
  const halfZ = so.data.size.z / 2;
  const handleY = pos.y + so.data.size.y / 2 + 0.4;
  const handleSize = (view.mode === '2D') ? 0.7 : 0.45;
  const corners = [
    {name: 'nw', x: pos.x - halfX, z: pos.z - halfZ},
    {name: 'ne', x: pos.x + halfX, z: pos.z - halfZ},
    {name: 'sw', x: pos.x - halfX, z: pos.z + halfZ},
    {name: 'se', x: pos.x + halfX, z: pos.z + halfZ},
  ];
  for (const c of corners) {
    const geo = new THREE.BoxGeometry(handleSize, handleSize, handleSize);
    const mat = new THREE.MeshBasicMaterial({color: 0xffd700, transparent: true, opacity: 0.95});
    const m = new THREE.Mesh(geo, mat);
    m.position.set(c.x, handleY, c.z);
    m.userData = {isResizeHandle: true, corner: c.name, stageId: view.selectedStageId};
    scene.add(m);
    resizeHandles.push(m);
  }
  requestRender();  // 3c-2: Handles neu aufgebaut
}

export function pickResizeHandle() {
  raycaster.setFromCamera(mouse, view.activeCam);
  const hits = raycaster.intersectObjects(resizeHandles, false);
  if (hits.length > 0) return hits[0].object;
  return null;
}

// ============================================================================
// 3D-Text-Labels (Sprite mit Canvas-Texture) ueber jedem Stage-Element
// ============================================================================
export function makeLabelSprite(text, color) {
  const canvas = document.createElement('canvas');
  canvas.width = 256;
  canvas.height = 64;
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, 256, 64);
  // Hintergrund halbtransparent
  ctx.fillStyle = 'rgba(20, 20, 30, 0.78)';
  ctx.fillRect(0, 0, 256, 64);
  ctx.strokeStyle = color || '#ffd700';
  ctx.lineWidth = 3;
  ctx.strokeRect(2, 2, 252, 60);
  ctx.fillStyle = color || '#ffd700';
  ctx.font = 'bold 30px Segoe UI, Tahoma, sans-serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(String(text).toUpperCase(), 128, 32);
  const tex = new THREE.CanvasTexture(canvas);
  tex.needsUpdate = true;
  const mat = new THREE.SpriteMaterial({map: tex, transparent: true, depthTest: false});
  const sprite = new THREE.Sprite(mat);
  sprite.scale.set(3.0, 0.75, 1);
  return sprite;
}

export function clearStageLabels() {
  for (const id in stageObjects) {
    const so = stageObjects[id];
    if (so._label) {
      scene.remove(so._label);
      if (so._label.material && so._label.material.map) so._label.material.map.dispose();
      if (so._label.material) so._label.material.dispose();
      so._label = null;
    }
  }
}

export function ensureLabel(id) {
  const so = stageObjects[id];
  if (!so) return;
  const typeLabel = (STAGE_2D_COLORS[so.data.type] && STAGE_2D_COLORS[so.data.type].label) || so.data.type;
  const text = so.data.name ? (so.data.name + ' [' + typeLabel + ']') : typeLabel;
  if (so._label) {
    // Update vorhandenes Label
    scene.remove(so._label);
    if (so._label.material && so._label.material.map) so._label.material.map.dispose();
    if (so._label.material) so._label.material.dispose();
  }
  so._label = makeLabelSprite(text, '#ffd700');
  scene.add(so._label);
}

export function updateStageLabelPositions() {
  for (const id in stageObjects) {
    const so = stageObjects[id];
    if (!so._label) continue;
    so._label.position.set(
      so.mesh.position.x,
      so.mesh.position.y + so.data.size.y / 2 + 1.2,
      so.mesh.position.z
    );
  }
}

export function getStageJson() {
  return {
    name: 'CustomStage',
    objects: Object.values(stageObjects).map(s => ({
      id: s.data.id,
      type: s.data.type,
      name: s.data.name || '',
      position: { ...s.data.position },
      size: { ...s.data.size },
      rotation: s.data.rotation,
      color: s.data.color,
    })),
    fixtures: Object.entries(fixtures).map(([fid, f]) => ({
      fid: Number(fid),
      x: f.group.position.x,
      y: f.group.position.y,
      z: f.group.position.z,
      // Rotationen hier in Radiant (interner JS-Roundtrip, kein Bridge-Grad).
      rotationX: f.group.rotation.x,
      rotationY: f.group.rotation.y,
      rotationZ: f.group.rotation.z,
    })),
  };
}

// FLICKER-FIX: Während eines kompletten Stage-Loads dürfen die
// einzelnen create/remove-Operationen NICHT jeweils zurück an Python
// melden – das löst sonst N×Tree-Rebuilds aus.
let _isLoadingStage = false;

// Review-Fix (Stage-Echo-Race): Sequenz-Token aus der zuletzt per
// loadStageJson() empfangenen Buehnen-Definition ("_reloadToken", von
// push_stage_definition() vergeben). JEDES notifyStageListChanged()-Echo
// traegt diesen Token zurueck an Python, damit ein spaet eintreffendes Echo
// aus einem inzwischen ueberholten Reload dort als STALE erkannt und dessen
// destruktiver Loesch-Abgleich uebersprungen werden kann.
let _currentStageReloadToken = null;

export function loadStageJson(json) {
  const incoming = typeof json === 'string' ? JSON.parse(json) : json;
  const incomingToken = incoming && incoming._reloadToken;
  // Die QtWebChannel-Signale werden zusätzlich über pollControl zugestellt.
  // Sobald die direkte Zustellung doch greift, erreicht derselbe Bulk-Push
  // den View somit zweimal. Ein zweiter clear/create-Durchlauf während/kurz
  // nach dem ersten machte sich bei komplexen Bühnen als partiell geleerte
  // Elementliste bemerkbar. Ein Reload-Token ist pro Python-Push eindeutig;
  // identische, bereits vollständig vorhandene Tokens sind daher strikt
  // idempotent und brauchen keinen erneuten Szenenaufbau.
  const incomingIds = (incoming && Array.isArray(incoming.objects))
    ? incoming.objects.map(o => o && o.id).filter(Boolean).sort()
    : [];
  const currentIds = Object.keys(stageObjects).sort();
  const isAlreadyComplete = incomingIds.length === currentIds.length
    && incomingIds.every((id, index) => id === currentIds[index]);
  if (typeof incomingToken === 'number'
      && incomingToken === _currentStageReloadToken
      && isAlreadyComplete) {
    return;
  }
  _isLoadingStage = true;
  try {
    const data = incoming;
    if (typeof data._reloadToken === 'number') _currentStageReloadToken = data._reloadToken;
    clearStageObjects();
    view.selectedStageId = null;
    clearResizeHandles();
    clearStageLabels();
    if (data.objects && Array.isArray(data.objects)) {
      data.objects.forEach(o => {
        createStageObject(o.type, o.position, o.size, o.color, o.rotation, o.id, o.name);
      });
    }
    if (data.fixtures && Array.isArray(data.fixtures)) {
      data.fixtures.forEach(fp => {
        const f = fixtures[fp.fid];
        if (f) {
          f.group.position.set(fp.x || 0, fp.y || 6.5, fp.z || 0);
          if (typeof fp.rotationX === 'number') f.group.rotation.x = fp.rotationX;
          if (typeof fp.rotationY === 'number') f.group.rotation.y = fp.rotationY;
          if (typeof fp.rotationZ === 'number') f.group.rotation.z = fp.rotationZ;
        }
      });
    }
    updateOutlinesRef.get()();
  } catch (e) {
    console.log('loadStageJson error:', e);
  } finally {
    _isLoadingStage = false;
    // EINE einzige finale Sync ans Python schicken (statt N×)
    notifyStageListChanged();
    // 3c-2: Bulk-Load deckt auch den direkten Fixture-Transform-Zweig oben
    // (f.group.position/rotation OHNE verdrahteten Helfer) + den Fehlerfall ab.
    requestRender();
  }
}

export function notifyStageListChanged() {
  if (_isLoadingStage) return;  // unterdrücken während Bulk-Load
  const bridge = bridgeRef.get();
  if (bridge && bridge.stageListChanged) {
    const payload = {
      objects: Object.values(stageObjects).map(s => s.data),
      _reloadToken: _currentStageReloadToken,
    };
    try { bridge.stageListChanged(JSON.stringify(payload)); } catch (e) {}
  }
}

// ── Spaet-Bindung (zirkulaere Abhaengigkeiten aufloesen, wie im Design-
// Dokument Abschnitt (a) "Kern-Gotcha" vorgeschrieben) ──────────────────────
// stage_objects.js <-> bridge/bridge.js (bridge-Objekt entsteht erst beim
// WebChannel-Connect) und stage_objects.js <-> interaction/tools.js
// (updateOutlines rundet Selektions-UI ab, die wiederum Stage-Objekte kennt)
// sind gegenseitig abhaengig. Statt echtem zirkulaeren Modul-Import (der bei
// ES-Modulen mit Top-Level-Werten Probleme macht, weil einer der beiden zum
// Import-Zeitpunkt noch nicht fertig ausgewertet ist) registriert app.js
// beim Bootstrap schmale Getter-Referenzen. Das entspricht dem im Original
// impliziten "alle Funktionen sehen sich gegenseitig im selben Scope"-
// Verhalten 1:1, nur explizit gemacht. _dockHighlightId selbst lebt in
// interaction/docking.js (dort auch gelesen/geschrieben ausserhalb dieses
// Moduls) - hier nur ueber den Getter/Setter erreichbar.
export const bridgeRef = { get: () => null };
export const updateOutlinesRef = { get: () => () => {} };
export const dockHighlightRef = { get: () => null, set: () => {} };

export function wireStageObjectsLateBindings({ getBridge, updateOutlines, dockHighlight }) {
  bridgeRef.get = getBridge;
  updateOutlinesRef.get = () => updateOutlines;
  dockHighlightRef.get = dockHighlight.get;
  dockHighlightRef.set = dockHighlight.set;
}
