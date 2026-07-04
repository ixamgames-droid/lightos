// VIZ-13 Schritt 3b-K-1: Kamera-Presets + Fit/Fit-Selected + FPS-Overlay.
// Siehe docs/VIZ13_JS_NEUAUFBAU_DESIGN.md "3b-Nachtrag" - Eigenbau auf der
// vorhandenen theta/phi/radius-Orbit-Kamera (camera/cameras.js), KEINE
// externen Controls. Additiv: bestehendes Orbit/Zoom/Pan-Verhalten bleibt
// unveraendert, dieses Modul fuegt nur neue Funktionen hinzu.
import * as THREE from '../three/three.js';
import { view, fixtures } from '../state.js';
import {
  camTarget, updateCamera, resizeOrtho,
  orthoCam, orthoState, perspectiveCam,
} from './cameras.js';
import { fixtureMeshes } from '../fixtures/fixtures.js';
import { setViewMode } from '../stage/view_mode.js';

// ============================================================================
// Kamera-Presets (Top/Front/Seite/Perspektive/Frei)
// ============================================================================
// Feste theta/phi-Werte je Preset. "persp" = heutige Default-Schraegansicht
// (siehe resetCameraView in cameras.js: theta=0.3, phi=1.1). "free" ist ein
// No-Op fuer die Perspektiv-Kamera - laesst die aktuelle freie Orbit-Stellung
// unangetastet (Design-Dokument 3b-K: "Frei = aktuelle freie Orbit-Steuerung").
const PRESETS = {
  top:   { theta: 0.3, phi: 0.01 },
  front: { theta: 0.0, phi: Math.PI / 2 },
  side:  { theta: Math.PI / 2, phi: Math.PI / 2 },
  persp: { theta: 0.3, phi: 1.1 },
};

// Radius bleibt beim Preset-Wechsel unangetastet (nur Blickrichtung aendert
// sich) - der User kann danach weiter zoomen wie gewohnt.
//
// Sonder-Namen 'fit'/'fit_selected' (VIZ-13 3b-K-2): die Toolbar hat KEINEN
// eigenen Bridge-Kanal fuer Fit/Fit-Auswahl - sie reisen ueber dasselbe
// additive cameraPreset-Signal wie die Achsen-Presets (haelt den Bridge-
// Vertrag bei den 3 im Auftrag genannten Signalen: cameraPreset/
// setNamedCameras/cameraSaved). fitAll/fitSelected sind bereits vorhanden
// (Schritt 3b-K-1) und werden hier nur zusaetzlich verdrahtet.
export function setCameraPreset(name) {
  if (name === 'free') return; // No-Op: aktuelle Orbit-Stellung bleibt stehen
  if (name === 'fit') { fitAll(); return; }
  if (name === 'fit_selected') { fitSelected(); return; }
  // "save:<name>"/"apply:<name>" (Toolbar "Kamera speichern..."/gespeicherte
  // Kamera anwenden) - reisen ueber denselben additiven cameraPreset-Kanal,
  // s. visualizer_window.py#_on_save_named_camera/_on_apply_named_camera.
  if (typeof name === 'string' && name.indexOf('save:') === 0) {
    saveNamedCamera(name.slice(5));
    return;
  }
  if (typeof name === 'string' && name.indexOf('apply:') === 0) {
    applyNamedCamera(name.slice(6));
    return;
  }
  // "applycam:<json>": Python schickt den VOLLEN Kamera-Dict aus dem
  // autoritativen AppState.visualizer_named_cameras mit. Bewusste Design-
  // Entscheidung (Single Source of Truth): das Anwenden haengt NICHT von der
  // JS-lokalen _namedCameras-Liste und deren Push-Reihenfolge/-Zeitpunkt ab,
  // sondern nutzt direkt den Python-Bestand. applyNamedCamera nimmt ein dict
  // direkt.
  if (typeof name === 'string' && name.indexOf('applycam:') === 0) {
    try { applyNamedCamera(JSON.parse(name.slice(9))); } catch (e) {}
    return;
  }
  const p = PRESETS[name];
  if (!p) return;

  if (view.mode === '2D') {
    // Sinngemaess fuer den Ortho-2D-Modus: nur "top" ist eine echte Ansicht
    // (senkrecht von oben ist bereits der Standard-Ortho-Blick). Andere
    // Presets ergeben in der reinen Top-Down-Kamera keinen Sinn - No-Op.
    if (name === 'top' || name === 'persp') {
      orthoCam.position.set(camTarget.x, 60, camTarget.z + 0.001);
      orthoCam.lookAt(camTarget.x, 0, camTarget.z);
      resizeOrtho();
    }
    return;
  }

  view.theta = p.theta;
  view.phi = p.phi;
  updateCamera();
}

// ============================================================================
// Fit / Fit-Selected
// ============================================================================
// Bounding-Box ueber die gecachte Fixture-Mesh-Liste (fixtureMeshes,
// fixtures/fixtures.js#rebuildFixtureMeshList) - dieselbe Liste, die auch
// Picking nutzt (Design-Dokument Abschnitt (d) "Picking ueber gecachte
// Mesh-Listen"). Kein Extra-Traverse noetig.
const MARGIN = 1.35; // etwas Luft um die Bounding-Box, damit nichts am Rand klebt
const MIN_RADIUS = 3;
const MAX_RADIUS = 200;

function _boundsFromMeshes(meshes) {
  if (!meshes || meshes.length === 0) return null;
  const box = new THREE.Box3();
  let any = false;
  for (const m of meshes) {
    if (!m || !m.visible) continue;
    // Beam-Kegel (bis 8 m) nicht ins Fit einrechnen - sonst rahmt Fit die
    // Lichtstrahlen statt der Fixtures (fixtures.js#createBeamCone taggt sie).
    if (m.userData && m.userData.excludeFromFit) continue;
    box.expandByObject(m);
    any = true;
  }
  if (!any || box.isEmpty()) return null;
  return box;
}

function _meshesForFids(fids) {
  const out = [];
  for (const fid of fids) {
    const f = fixtures[fid];
    if (!f || !f.group) continue;
    f.group.traverse(o => { if (o.isMesh) out.push(o); });
  }
  return out;
}

// Zentriert target + setzt radius so, dass die Box komplett ins Bild passt
// (Perspektiv: radius aus Bounding-Sphere + FOV; Ortho: orthoSize aus BBox).
function _fitToBox(box) {
  if (!box) return;
  const center = new THREE.Vector3();
  const size = new THREE.Vector3();
  box.getCenter(center);
  box.getSize(size);
  const sphereRadius = Math.max(0.5, box.getBoundingSphere(new THREE.Sphere()).radius);

  if (view.mode === '2D') {
    const halfExtent = Math.max(size.x, size.z) * 0.5;
    orthoState.size = Math.max(4, Math.min(150, halfExtent * MARGIN));
    orthoCam.position.set(center.x, 60, center.z + 0.001);
    orthoCam.lookAt(center.x, 0, center.z);
    resizeOrtho();
    return;
  }

  camTarget.copy(center);
  const fovRad = (perspectiveCam.fov * Math.PI) / 180;
  const distForFov = (sphereRadius * MARGIN) / Math.sin(fovRad / 2);
  view.radius = Math.max(MIN_RADIUS, Math.min(MAX_RADIUS, distForFov));
  updateCamera();
}

export function fitCameraToObjects(meshes) {
  const box = _boundsFromMeshes(meshes);
  if (!box) return;
  _fitToBox(box);
}

export function fitAll() {
  fitCameraToObjects(fixtureMeshes);
}

export function fitSelected() {
  const sel = view.selectedFids;
  if (!sel || sel.length === 0) {
    fitAll();
    return;
  }
  fitCameraToObjects(_meshesForFids(sel));
}

// ============================================================================
// FPS-Overlay (rAF-Delta, gemittelt) - rein visuelles Debug-Hilfsmittel,
// standardmaessig aus. Kein Bridge-/Persistenz-Vertrag noetig.
// ============================================================================
let _fpsEl = null;
let _fpsVisible = false;
let _fpsLastT = 0;
let _fpsAccum = 0;
let _fpsFrames = 0;
let _fpsLastDisplay = 0;

function _ensureFpsEl() {
  if (_fpsEl) return _fpsEl;
  const el = document.createElement('div');
  el.id = 'fps-overlay';
  el.style.cssText =
    'position:absolute; top:8px; right:8px; z-index:5; ' +
    'color:#7f7; font-size:11px; font-family:monospace; ' +
    'background:rgba(0,0,0,0.55); padding:3px 8px; border-radius:4px; ' +
    'pointer-events:none; display:none;';
  el.textContent = 'FPS: --';
  document.body.appendChild(el);
  _fpsEl = el;
  return el;
}

export function setFpsVisible(vis) {
  _fpsVisible = !!vis;
  const el = _ensureFpsEl();
  el.style.display = _fpsVisible ? 'block' : 'none';
  if (_fpsVisible) { _fpsAccum = 0; _fpsFrames = 0; _fpsLastT = 0; }
}

// Wird pro Frame aus app.js#animate() aufgerufen (kein eigener rAF-Zweig,
// haengt sich in die bestehende Kette). No-Op solange nicht sichtbar.
export function fpsTick() {
  if (!_fpsVisible) return;
  const now = performance.now();
  if (_fpsLastT === 0) { _fpsLastT = now; return; }
  const dt = now - _fpsLastT;
  _fpsLastT = now;
  if (dt <= 0) return;
  _fpsAccum += dt;
  _fpsFrames += 1;
  // Anzeige alle ~250ms aktualisieren (nicht jeden Frame - flackert sonst)
  if (now - _fpsLastDisplay > 250 && _fpsFrames > 0) {
    const avgMs = _fpsAccum / _fpsFrames;
    const fps = avgMs > 0 ? 1000 / avgMs : 0;
    if (_fpsEl) _fpsEl.textContent = 'FPS: ' + fps.toFixed(1);
    _fpsLastDisplay = now;
    _fpsAccum = 0;
    _fpsFrames = 0;
  }
}

// ============================================================================
// Benannte Kameras (VIZ-13 Schritt 3b-K-2) - Persistenz laeuft ueber Python
// (additiver Show-Block visualizer.named_cameras, s. show_file.py). JS haelt
// nur die aktuell vom Service gepushte Liste + baut/liest das Speicher-JSON
// ({name, mode, theta, phi, radius, target:[x,y,z], orthoSize, orthoPan:[x,z]}
// - s. Design-Dokument (c)). `bridgeRef` = Late-Binding wie in
// interaction/tools.js (verhindert zirkulaeren Import presets.js<->bridge.js).
// ============================================================================
export const bridgeRef = { get: () => null };

export function wirePresetsLateBindings({ getBridge }) {
  bridgeRef.get = getBridge;
}

let _namedCameras = [];

// Vom Bridge-Connect (setNamedCameras-Signal) aufgerufen, wenn Python nach
// Show-Laden bzw. nach einem cameraSaved-Echo die volle Liste pusht.
export function setNamedCameras(list) {
  _namedCameras = Array.isArray(list) ? list : [];
}

export function getNamedCameras() {
  return _namedCameras;
}

// Baut das Speicher-JSON aus dem aktuellen Kamerastatus (3D: theta/phi/radius
// + camTarget; 2D: orthoSize + Ortho-Kameraposition als "Pan") und meldet es
// via bridge.cameraSaved(json) an Python zurueck (Persistenz + Broadcast an
// den Rest der Bridge-Liste laeuft dort, s. VisualizerBridge.cameraSaved).
export function saveNamedCamera(name) {
  const n = String(name || '').trim();
  if (!n) return;
  const payload = {
    name: n,
    mode: view.mode,
    theta: view.theta,
    phi: view.phi,
    radius: view.radius,
    target: [camTarget.x, camTarget.y, camTarget.z],
    orthoSize: orthoState.size,
    orthoPan: [orthoCam.position.x, orthoCam.position.z],
  };
  const bridge = bridgeRef.get && bridgeRef.get();
  if (bridge && bridge.cameraSaved) {
    try { bridge.cameraSaved(JSON.stringify(payload)); } catch (e) {}
  }
}

// Springt (ohne Animation - Lerp ist ein spaeteres Komfort-Extra, kein
// Vertragsbestandteil) auf eine zuvor gespeicherte Kamera. Akzeptiert
// entweder einen Namen (Lookup in _namedCameras) oder direkt ein Kamera-dict.
export function applyNamedCamera(nameOrCam) {
  const cam = (typeof nameOrCam === 'string')
    ? _namedCameras.find(c => c && c.name === nameOrCam)
    : nameOrCam;
  if (!cam) return;
  // Zuerst den gespeicherten View-Modus wiederherstellen: sonst mutiert das
  // Anwenden nur die INAKTIVE Kamera (z.B. orthoCam waehrend perspektivisch
  // gerendert wird) und die Ansicht aendert sich sichtbar nicht. setViewMode
  // schaltet die aktive Kamera + view.mode um, laesst aber theta/phi/radius
  // bzw. orthoSize/-Position unangetastet (die wir gleich setzen).
  const targetMode = (cam.mode === '2D') ? '2D' : '3D';
  if (view.mode !== targetMode) setViewMode(targetMode);
  if (cam.mode === '2D') {
    if (typeof cam.orthoSize === 'number') orthoState.size = cam.orthoSize;
    const pan = Array.isArray(cam.orthoPan) ? cam.orthoPan : [0, 0];
    orthoCam.position.set(pan[0] || 0, 60, (pan[1] || 0) + 0.001);
    orthoCam.lookAt(pan[0] || 0, 0, pan[1] || 0);
    resizeOrtho();
  } else {
    if (typeof cam.theta === 'number') view.theta = cam.theta;
    if (typeof cam.phi === 'number') view.phi = cam.phi;
    if (typeof cam.radius === 'number') view.radius = cam.radius;
    if (Array.isArray(cam.target)) camTarget.set(cam.target[0] || 0, cam.target[1] || 0, cam.target[2] || 0);
    updateCamera();
  }
}
