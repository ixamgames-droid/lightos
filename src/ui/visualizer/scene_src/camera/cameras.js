// VIZ-13 Schritt 3a-4: Kameras (perspectiveCam/orthoCam) + Kamera-Sphaerik
// (ehem. stage_scene.html:198-213, 2210-2217, 3273-3312). Reines Verschieben.
//
// orthoSize/camTarget bleiben modul-lokale `let`/const, weil sie NUR hier
// gelesen/geschrieben werden (ausser orthoSize, das von interaction/pointer.js
// + interaction/touch.js beim Wheel-/Pinch-Zoom mutiert wird - siehe Export
// unten als Objekt-Wrapper, gleiches Getter/Setter-Muster wie state.view).
import * as THREE from '../three/three.js';
import { view } from '../state.js';
// VIZ-13 3c-2: On-Demand-Rendering — updateCamera()/resizeOrtho() sind die
// Flaschenhaelse, durch die (fast) jede Kamera-Mutation laeuft (Orbit/Zoom/
// Pinch/Presets/Fit/benannte Kameras/Reset) -> EIN requestRender je Funktion
// deckt sie alle ab. (Der direkte 2D-Pan in pointer.js/touch.js mutiert
// orthoCam.position OHNE diese Helfer — dort ist die Quelle separat
// verdrahtet.)
import { requestRender } from '../scene/render_loop.js';

// A3D-41: Seitenverhaeltnis des Viewports, NIE nicht-endlich.
//
// `window.innerWidth / window.innerHeight` ist bei einem noch nicht
// gelayouteten View `0/0 === NaN` — und eine Kamera, die einmal mit
// `aspect = NaN` gebaut wurde, hat eine vollstaendig nicht-endliche
// Projektionsmatrix. Ab da liefert JEDER Raycast NaN, voellig unabhaengig von
// der Zeigerposition, und die erste Gestik danach schreibt NaN-Positionen in
// den SceneGraph (von dort als `"x": null` in die Bridge-Payload — genau der
// A3D-41-Crash). Nachgemessen in der offscreen-Page: `aspect` NaN,
// `projectionMatrix.elements` komplett nicht-endlich.
//
// Der Fallback 1 (quadratisch) haelt die Kamera in einem gueltigen Zustand,
// bis ein echter Resize kommt — `onWindowResize` unten laeuft durch dieselbe
// Funktion und korrigiert das Bild dann von selbst.
export function viewportAspect() {
  const w = window.innerWidth, h = window.innerHeight;
  return (w > 0 && h > 0) ? w / h : 1;
}

export const perspectiveCam = new THREE.PerspectiveCamera(60, viewportAspect(), 0.1, 500);
perspectiveCam.position.set(0, 12, 18);
perspectiveCam.lookAt(0, 0, 0);

let _orthoSize = 18; // half-height in world units
const aspect = viewportAspect();
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
  const a = viewportAspect();
  orthoCam.left = -_orthoSize * a;
  orthoCam.right = _orthoSize * a;
  orthoCam.top = _orthoSize;
  orthoCam.bottom = -_orthoSize;
  orthoCam.updateProjectionMatrix();
  requestRender();  // 3c-2 Dirty-Quelle 2 (Kamera: Ortho-Zoom/Fit/Resize)
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
  requestRender();  // 3c-2 Dirty-Quelle 2 (Kamera: Orbit/Pan/Zoom/Preset/Fit)
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
  // A3D-41: ueber viewportAspect() — ein Resize auf 0 (Tab weggeschaltet,
  // Splitter zugezogen) darf die Projektionsmatrix nicht mit NaN fuellen.
  // Genau dieser Listener heilt sie umgekehrt beim naechsten echten Resize.
  perspectiveCam.aspect = viewportAspect();
  perspectiveCam.updateProjectionMatrix();
  resizeOrtho();
});
