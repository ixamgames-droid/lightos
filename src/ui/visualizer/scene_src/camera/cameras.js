// VIZ-13 Schritt 3a-4: Kameras (perspectiveCam/orthoCam) + Kamera-Sphaerik
// (ehem. stage_scene.html:198-213, 2210-2217, 3273-3312). Reines Verschieben.
//
// orthoSize/camTarget bleiben modul-lokale `let`/const, weil sie NUR hier
// gelesen/geschrieben werden (ausser orthoSize, das von interaction/pointer.js
// + interaction/touch.js beim Wheel-/Pinch-Zoom mutiert wird - siehe Export
// unten als Objekt-Wrapper, gleiches Getter/Setter-Muster wie state.view).
import * as THREE from '../three/three.js';
import { view } from '../state.js';

export const perspectiveCam = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 0.1, 500);
perspectiveCam.position.set(0, 12, 18);
perspectiveCam.lookAt(0, 0, 0);

let _orthoSize = 18; // half-height in world units
const aspect = window.innerWidth / window.innerHeight;
export const orthoCam = new THREE.OrthographicCamera(
  -_orthoSize * aspect, _orthoSize * aspect, _orthoSize, -_orthoSize, 0.1, 500
);
orthoCam.position.set(0, 60, 0.001);
orthoCam.lookAt(0, 0, 0);
orthoCam.up.set(0, 0, -1); // so +Z points down on screen, +X right

// orthoSize wird von aussen (interaction/pointer.js Wheel-Zoom,
// interaction/touch.js Pinch-Zoom) gelesen UND neu zugewiesen - Getter/
// Setter-Objekt statt re-exportiertem `let` (gleiches Muster wie state.view).
export const orthoState = {
  get size() { return _orthoSize; },
  set size(v) { _orthoSize = v; },
};

view.activeCam = perspectiveCam;

export function resizeOrtho() {
  const a = window.innerWidth / window.innerHeight;
  orthoCam.left = -_orthoSize * a;
  orthoCam.right = _orthoSize * a;
  orthoCam.top = _orthoSize;
  orthoCam.bottom = -_orthoSize;
  orthoCam.updateProjectionMatrix();
}

// ============================================================================
// Camera (Eigenbau-Orbit - theta/phi/radius liegen in state.view, siehe
// Design-Dokument "Kern-Gotcha", damit interaction/pointer.js + touch.js sie
// ohne zirkulaeren Import gegen camera/cameras.js lesen/schreiben koennen)
// ============================================================================
export const camTarget = new THREE.Vector3(0, 2, 0);

export function updateCamera() {
  perspectiveCam.position.x = camTarget.x + view.radius * Math.sin(view.phi) * Math.sin(view.theta);
  perspectiveCam.position.y = camTarget.y + view.radius * Math.cos(view.phi);
  perspectiveCam.position.z = camTarget.z + view.radius * Math.sin(view.phi) * Math.cos(view.theta);
  perspectiveCam.lookAt(camTarget);
}
updateCamera();

// Schwenkt das 3D-Kamera-Ziel in der Bildebene (Zwei-Finger-Pan).
export function panCamera3D(dScreenX, dScreenY) {
  const k = view.radius * 0.0016;
  const rx = Math.cos(view.theta), rz = -Math.sin(view.theta);   // Bildschirm-rechts in Welt-XZ
  const fx = Math.sin(view.theta), fz = Math.cos(view.theta);    // Bildschirm-hoch in Welt-XZ
  camTarget.x -= dScreenX * k * rx + dScreenY * k * fx;
  camTarget.z -= dScreenX * k * rz + dScreenY * k * fz;
  updateCamera();
}

// Gemeinsamer Kamera-Reset (Toolbar-Button UND Doppel-Tipp).
export function resetCameraView() {
  view.theta = 0.3; view.phi = 1.1; view.radius = 22;
  camTarget.set(0, 2, 0);
  updateCamera();
  _orthoSize = 18;
  orthoCam.position.set(0, 60, 0.001);
  orthoCam.lookAt(0, 0, 0);
  resizeOrtho();
}

// window 'resize'-Listener: ehem. stage_scene.html:3304-3312 kombinierte
// Kamera-Aspect-Update UND renderer.setSize/setPixelRatio in einem Listener.
// Reine Modul-Aufteilung erfordert den Renderer-Teil in scene/renderer.js
// (zirkulaerer Import sonst: cameras.js<->renderer.js) - hier bewusst NUR
// der Kamera-Teil, der Renderer-Teil ist als eigener Listener in
// scene/renderer.js registriert. Beide Listener feuern beim selben Event,
// Ausfuehrungsreihenfolge = Registrierungsreihenfolge (Renderer-Modul wird
// von app.js VOR cameras.js importiert) - identisch zum Ist-Verhalten, da
// die beiden Anweisungsbloecke im Original nicht voneinander abhingen.
window.addEventListener('resize', function() {
  perspectiveCam.aspect = window.innerWidth / window.innerHeight;
  perspectiveCam.updateProjectionMatrix();
  resizeOrtho();
});
