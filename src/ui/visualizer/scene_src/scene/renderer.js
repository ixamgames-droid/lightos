// VIZ-13 Schritt 3a-4: Renderer + Scene (ehem. stage_scene.html:180-196, 258-290).
// Reines Verschieben - Funktionssignaturen/Bodies unveraendert.
import * as THREE from '../three/three.js';
import { settings } from '../state.js';
import { requestRender } from './render_loop.js';  // VIZ-13 3c-2

export const scene = new THREE.Scene();
scene.background = new THREE.Color(0x080808);
scene.fog = new THREE.FogExp2(0x080808, 0.025);

// ── GPU-Tier (Low-Spec-Erkennung, 2026-07-11) ───────────────────────────────
// Davids Surface (Adreno, MAX_TEXTURE_IMAGE_UNITS=16) braucht andere Defaults
// als eine Desktop-GPU: Antialias ist eine KONSTRUKTOR-Entscheidung des
// Renderers, daher probt eine Wegwerf-Canvas VOR dem Bau die Limits.
// Override fuer Tests/Debug: ?gputier=low|high in der Page-URL.
function probeGpuTier() {
  // ⚠️ Der Probe-Kontext MUSS wieder freigegeben werden.
  //
  // Diese Funktion holt einen ECHTEN WebGL-Kontext, nur um zwei Limits
  // abzufragen. Ohne Freigabe haengt er bis zur Garbage Collection am
  // Kontext-Budget des GPU-Prozesses — und der Renderer darunter holt sofort
  // den zweiten. Macht ZWEI Kontexte je Seitenladung, von denen einer nie
  // wieder benutzt wird.
  //
  // Das ist kein theoretisches Leck: das Kontext-Budget dieser Umgebung ist
  // klein genug, dass es erreicht wird (in `tests/test_viz14_drag_scene.py`
  // gemessen festgehalten — drei sichtbare Views nacheinander erschoepfen es
  // reproduzierbar, „Error creating WebGL context"). Und es trifft nicht nur
  // Tests: jedes Oeffnen des 3D-Fensters laedt die Seite neu.
  //
  // `WEBGL_lose_context` ist der einzige Weg, einen Kontext aktiv aufzugeben —
  // Canvas wegwerfen und auf die GC hoffen reicht nicht.
  let gl = null;
  try {
    const forced = new URLSearchParams(window.location.search).get('gputier');
    if (forced === 'low' || forced === 'high') return forced;
    const cv = document.createElement('canvas');
    gl = cv.getContext('webgl') || cv.getContext('experimental-webgl');
    if (!gl) return 'low';
    const maxTex = gl.getParameter(gl.MAX_TEXTURE_IMAGE_UNITS);
    let chip = '';
    const dbg = gl.getExtension('WEBGL_debug_renderer_info');
    if (dbg) chip = String(gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) || '');
    // Mobile-/Emulations-Chips: fill-rate-limitiert, wenige Texture-Units.
    const weakChip = /adreno|mali|powervr|videocore|swiftshader|basic render/i.test(chip);
    return (maxTex <= 16 || weakChip) ? 'low' : 'high';
  } catch (e) {
    return 'high';
  } finally {
    // `finally`, nicht am Ende des try-Blocks: die Funktion hat vier
    // Ausstiege (Override, kein Kontext, Ergebnis, Wurf). Drei davon wuerden
    // eine Freigabe am Blockende ueberspringen — und ausgerechnet der
    // Fehlerpfad haelt den Kontext dann am laengsten.
    try {
      const verlust = gl && gl.getExtension('WEBGL_lose_context');
      if (verlust) verlust.loseContext();
    } catch (e) { /* Freigabe ist best effort — nie den Start daran haengen */ }
  }
}
export const gpuTier = probeGpuTier();
export const isLowSpec = gpuTier === 'low';

export const renderer = new THREE.WebGLRenderer({
  // Low-Spec: MSAA kostet auf fill-rate-limitierten Chips ueberproportional;
  // high-performance bittet Dual-GPU-Systeme um die dedizierte Karte.
  antialias: !isLowSpec,
  powerPreference: 'high-performance',
});
// Pixel-Ratio ist QUADRATISCHE Fragment-Last: 2.0 auf dem High-DPI-Surface
// hiess 4x so viele Pixel wie 1.0 — Low-Spec deckelt auf 1.25.
// Exportiert: der pixelRatioSignal-Handler (bridge.js, screenChanged) MUSS
// denselben Deckel nutzen, sonst hebt ein Monitor-Wechsel ihn wieder auf.
export const PIXEL_RATIO_CAP = isLowSpec ? 1.25 : 2;
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, PIXEL_RATIO_CAP));
renderer.shadowMap.enabled = true;
// PCFSoft sampelt deutlich mehr Shadow-Taps pro Pixel als plain PCF.
renderer.shadowMap.type = isLowSpec ? THREE.PCFShadowMap : THREE.PCFSoftShadowMap;
// console.warn statt .log: Qt spiegelt nur Warning/Error-Konsolenzeilen ins
// crash.log — so ist die Tier-Entscheidung auch nachtraeglich diagnostizierbar.
console.warn('[viz] GPU-Tier: ' + gpuTier
  + ' (maxTextures=' + renderer.capabilities.maxTextures
  + ', pixelRatioCap=' + PIXEL_RATIO_CAP
  + ', antialias=' + String(!isLowSpec) + ')');
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
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, PIXEL_RATIO_CAP));
  requestRender();  // 3c-2 Dirty-Quelle 5 (Fenster-Resize)
});
