// VIZ-13 Schritt 3a-4: Async model loader (OBJ/DAE) + Cache
// (ehem. stage_scene.html:356-426). Reines Verschieben.
import * as THREE from '../three/three.js';
import { requestRender } from './render_loop.js';  // VIZ-13 3c-2

const modelCache = {};           // path -> THREE.Object3D (cloned per use)
const modelLoadCallbacks = {};   // path -> [callbacks waiting]

export function loadModel(path, callback) {
  if (modelCache[path]) {
    try { callback(modelCache[path].clone(true)); } catch (e) { console.log('loadModel cb err:', e); }
    return;
  }
  if (modelLoadCallbacks[path]) {
    modelLoadCallbacks[path].push(callback);
    return;
  }
  modelLoadCallbacks[path] = [callback];

  const isObj = path.toLowerCase().endsWith('.obj');
  const isDae = path.toLowerCase().endsWith('.dae');

  const onLoaded = (obj) => {
    if (obj) {
      obj.traverse(c => {
        if (c.isMesh && !c.material) {
          c.material = new THREE.MeshStandardMaterial({ color: 0x888888, roughness: 0.7 });
        }
      });
      modelCache[path] = obj;
    }
    const cbs = modelLoadCallbacks[path] || [];
    delete modelLoadCallbacks[path];
    for (const cb of cbs) {
      try { cb(obj ? obj.clone(true) : null); } catch (e) { console.log('model cb err:', e); }
    }
    // 3c-2: ZENTRALER Async-Nachlade-Frame — die Callbacks haengen frisch
    // geladene Modelle in die Szene (builders.js: par/strobe/smoke/hazer.dae;
    // stage_objects.js: Truss-OBJ). Sie kommen NACH dem Frame des ausloesenden
    // addFixture/createStageObject an; ohne requestRender bliebe bis zum
    // naechsten fremden Render der Platzhalter/das nackte Prozedural-Modell
    // sichtbar.
    requestRender();
  };

  const onError = (err) => {
    console.log('model load FAILED:', path, err);
    const cbs = modelLoadCallbacks[path] || [];
    delete modelLoadCallbacks[path];
    for (const cb of cbs) {
      try { cb(null); } catch (e) {}
    }
  };

  try {
    if (isObj && typeof THREE.OBJLoader === 'function') {
      new THREE.OBJLoader().load(path, obj => onLoaded(obj), undefined, onError);
    } else if (isDae && typeof THREE.ColladaLoader === 'function') {
      new THREE.ColladaLoader().load(path, result => onLoaded(result.scene || result), undefined, onError);
    } else {
      onError(new Error('no loader available for ' + path));
    }
  } catch (err) {
    onError(err);
  }
}

// Helper: scale a loaded model into a target bounding box (size.x/y/z in world units)
//
// ★ MODELLOADER (2026-08-05): entartete Modelle konnten das Modell aus der Welt
// schieben. Die Rechnung nahm frueher IMMER den Faktor `size/max(ms, 1e-6)` fuer
// den Versatz — auch dann, wenn die Skalierung wegen einer Achse ohne
// Ausdehnung gar nicht gesetzt worden war. Gemessen: eine in x flache Geometrie
// (Plane statt Koerper) mit Mitte bei x = 5 landete danach bei
// **x = -10.000.000**. Unsichtbar, ohne Fehlermeldung, und die Ursache liegt in
// einer fremden Datei — genau die Sorte Fehler, die man am Rig sucht.
//
// Und ein Modell ganz OHNE Geometrie (leere/kaputte Datei) liefert eine leere
// Bounding-Box: `getSize` gibt -Infinity, `getCenter` NaN. Das lief bis hierhin
// ungebremst in `position` — NaN wandert von dort in die Matrix, in die
// Bounding-Sphere und in den Frustum-Cull.
//
// Deshalb: der Versatz benutzt **denselben Faktor wie die Skalierung**, und wo
// keine skaliert wurde, ist er 1. Nicht-endliche Werte fuehren zu gar keiner
// Verschiebung — ein Modell an der falschen Stelle ist reparierbar, eines mit
// NaN-Matrix nicht.
export function fitModelToSize(model, size) {
  const bbox = new THREE.Box3().setFromObject(model);
  const ms = bbox.getSize(new THREE.Vector3());
  const brauchbar = (v) => Number.isFinite(v) && v > 0;
  const fx = brauchbar(ms.x) ? size.x / ms.x : 1;
  const fy = brauchbar(ms.y) ? size.y / ms.y : 1;
  const fz = brauchbar(ms.z) ? size.z / ms.z : 1;
  if (brauchbar(ms.x) && brauchbar(ms.y) && brauchbar(ms.z)) {
    model.scale.set(fx, fy, fz);
  }
  // Re-center on origin — mit denselben Faktoren, mit denen wirklich skaliert
  // wurde (siehe oben). Eine leere Bounding-Box liefert NaN/Infinity: dann gar
  // nicht verschieben.
  const center = bbox.getCenter(new THREE.Vector3());
  const dx = center.x * fx, dy = center.y * fy, dz = center.z * fz;
  if (Number.isFinite(dx) && Number.isFinite(dy) && Number.isFinite(dz)) {
    model.position.sub(new THREE.Vector3(dx, dy, dz));
  }
}
