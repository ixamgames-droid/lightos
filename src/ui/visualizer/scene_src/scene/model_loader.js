// VIZ-13 Schritt 3a-4: Async model loader (OBJ/DAE) + Cache
// (ehem. stage_scene.html:356-426). Reines Verschieben.
import * as THREE from '../three/three.js';

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
export function fitModelToSize(model, size) {
  const bbox = new THREE.Box3().setFromObject(model);
  const ms = bbox.getSize(new THREE.Vector3());
  if (ms.x > 0 && ms.y > 0 && ms.z > 0) {
    model.scale.set(size.x / ms.x, size.y / ms.y, size.z / ms.z);
  }
  // Re-center on origin
  const center = bbox.getCenter(new THREE.Vector3());
  // After we scaled, offset by the (scaled) center
  model.position.sub(new THREE.Vector3(
    center.x * (size.x / Math.max(ms.x, 1e-6)),
    center.y * (size.y / Math.max(ms.y, 1e-6)),
    center.z * (size.z / Math.max(ms.z, 1e-6))
  ));
}
