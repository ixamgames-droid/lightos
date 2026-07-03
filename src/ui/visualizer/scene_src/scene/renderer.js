// VIZ-13 Schritt 3a-4: Renderer + Scene (ehem. stage_scene.html:180-196, 258-290).
// Reines Verschieben - Funktionssignaturen/Bodies unveraendert.
import * as THREE from '../three/three.js';
import { settings } from '../state.js';

export const scene = new THREE.Scene();
scene.background = new THREE.Color(0x080808);
scene.fog = new THREE.FogExp2(0x080808, 0.025);

export const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
// Bundle ist three.js r128 (siehe three_local.js REVISION) - dort heisst die
// Farbraum-API noch outputEncoding/sRGBEncoding, nicht outputColorSpace.
renderer.outputEncoding = THREE.sRGBEncoding;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
// >1.0, damit die Szene nach dem Tone-Mapping heller wirkt als vorher (ACES
// dunkelt sonst v.a. additive Beam-/Emissive-Materialien sichtbar ab).
renderer.toneMappingExposure = 1.2;
document.body.appendChild(renderer.domElement);

// Grad <-> Radiant (Bridge transportiert Rotationen in GRAD, Three.js nutzt
// Radiant). Eigene Helfer statt THREE.MathUtils - unabhaengig vom Build.
export function deg2rad(d) { return (Number(d) || 0) * Math.PI / 180; }
export function rad2deg(r) { return (Number(r) || 0) * 180 / Math.PI; }

// window 'resize'-Listener, Renderer-Teil (ehem. stage_scene.html:3304-3312,
// siehe Aufteilungs-Kommentar in camera/cameras.js).
window.addEventListener('resize', function() {
  renderer.setSize(window.innerWidth, window.innerHeight);
  // Monitor-Wechsel kann devicePixelRatio aendern (z.B. Fenster auf anderen
  // Bildschirm mit anderer Skalierung verschoben) - hier mitziehen.
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
});
