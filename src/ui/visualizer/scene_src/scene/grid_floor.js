// VIZ-13 Schritt 3a-4: Stage (preset + custom objects) - Grid/Floor-Teil
// (ehem. stage_scene.html:298-351). Reines Verschieben.
import * as THREE from '../three/three.js';
import { scene } from './renderer.js';

// presetObjects/stageObjIdCounter bleiben hier (kein geteilter Modul-State
// laut Design-Dokument "Kern-Gotcha") - stageObjIdCounter wandert in
// stage/stage_objects.js (dort gebraucht), presetObjects bleibt hier.
export const presetObjects = [];   // built from "preset" templates - cleared on switch

export let gridHelper = null;
export let gridLabelsGroup = null;
export let floorMesh = null;

export function disposeObj(o) {
  if (!o) return;
  if (o.geometry) o.geometry.dispose();
  if (o.material) {
    if (Array.isArray(o.material)) o.material.forEach(m => m.dispose());
    else o.material.dispose();
  }
  // A3D-07: Licht-Shadow-Map (WebGLRenderTarget) freigeben. disposeObj wird pro
  // entferntem Fixture ueber f.group.traverse gerufen; der Per-Fixture-SpotLight
  // (fixtures.js: root.add(spot), shadow.mapSize gesetzt) haengt als Kind an root.
  // three r128s disposeObj-Aequivalent gibt aber NUR geometry+material frei, NICHT
  // spot.shadow -> das GPU-RenderTarget der Shadow-Map leckt sonst pro Show-Reload
  // (waechst bis Context-Loss auf schwachen GPUs). Sicher hier: disposeObj laeuft
  // ausschliesslich ueber Fixture-/Stage-/Grid-Objekte, NIE ueber die persistenten
  // Szenen-Lichter (die werden nie getraversed/disposed).
  if (o.isLight && o.shadow && typeof o.shadow.dispose === 'function') o.shadow.dispose();
}

export function clearPreset() {
  for (const obj of presetObjects) {
    scene.remove(obj);
    obj.traverse(c => disposeObj(c));
  }
  presetObjects.length = 0;
  if (gridHelper) { scene.remove(gridHelper); disposeObj(gridHelper); gridHelper = null; }
  if (gridLabelsGroup) { scene.remove(gridLabelsGroup); gridLabelsGroup.traverse(disposeObj); gridLabelsGroup = null; }
  if (floorMesh) { scene.remove(floorMesh); disposeObj(floorMesh); floorMesh = null; }
}

export function trackPreset(obj) {
  scene.add(obj);
  presetObjects.push(obj);
  return obj;
}

export function buildGridAndFloor() {
  // Grid-Kontrast angehoben (VIZ-10): vorher auf dunklem Boden kaum sichtbar.
  gridHelper = new THREE.GridHelper(60, 60, 0x686870, 0x303038);
  scene.add(gridHelper);
  // Floor
  floorMesh = new THREE.Mesh(
    new THREE.PlaneGeometry(80, 80),
    new THREE.MeshStandardMaterial({ color: 0x282828, roughness: 0.95, metalness: 0.0 })
  );
  floorMesh.rotation.x = -Math.PI / 2;
  floorMesh.position.y = -0.002;
  floorMesh.receiveShadow = true;
  floorMesh.userData.isFloor = true;
  scene.add(floorMesh);
}

// Vorgerenderte Kulissen (theatre/rock/box) wurden bewusst entfernt: der
// Visualizer startet mit einer LEEREN Buehne. Es bleibt nur das Welt-Grid +
// ein dezenter Referenz-Boden als Orientierung. Der User baut seine eigene
// Buehne/Trassen als editierbare stageObjects selbst auf.
buildGridAndFloor();
