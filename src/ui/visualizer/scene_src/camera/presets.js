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
export function setCameraPreset(name) {
  if (name === 'free') return; // No-Op: aktuelle Orbit-Stellung bleibt stehen
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
