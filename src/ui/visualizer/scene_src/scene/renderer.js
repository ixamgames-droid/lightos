// VIZ-13 Schritt 3a-4: Renderer + Scene (ehem. stage_scene.html:180-196, 258-290).
// Reines Verschieben - Funktionssignaturen/Bodies unveraendert.
import * as THREE from '../three/three.js';
import { settings } from '../state.js';
import { requestRender } from './render_loop.js';  // VIZ-13 3c-2
import { tierProfile, pixelRatioCapFor } from './quality_tiers.js';         // VIZ-71
import { createDynamicResolution } from './dynamic_resolution.js';          // VIZ-71
import { decideTier, BENCH_HIGH_MS } from './gpu_tier.js';                                 // VIZ-84

export const scene = new THREE.Scene();
scene.background = new THREE.Color(0x080808);
scene.fog = new THREE.FogExp2(0x080808, 0.025);

// ── GPU-Tier (Low-Spec-Erkennung, 2026-07-11) ───────────────────────────────
// Davids Surface (Adreno, MAX_TEXTURE_IMAGE_UNITS=16) braucht andere Defaults
// als eine Desktop-GPU: Antialias ist eine KONSTRUKTOR-Entscheidung des
// Renderers, daher probt eine Wegwerf-Canvas VOR dem Bau die Limits.
// Override fuer Tests/Debug/Geraete-Praeferenz: ?gputier=low|high|max in der
// Page-URL. VIZ-71: 'max' gibt es NUR ueber diesen Weg — die Probe waehlt nie
// mehr als 'high'.
// VIZ-84: die Entscheidung selbst steht rein in gpu_tier.js (Renderer-Name,
// dann Frame-Zeit, dann Texture-Units). Test-Seams, nur ohne ?gputier
// wirksam: `window.__lightosGpuRendererStub` (Renderer-Name) und
// `window.__lightosGpuBenchStub` (Frame-Zeit in ms) — per DocumentCreation-
// Skript vor dem Modul gesetzt.
export const gpuProbeInfo = { tier: null, grund: '', chip: '', maxTex: null, benchMs: null };

// VIZ-84: Frame-Zeit-Rueckfall — ein paar bildschirmfuellende Draws mit einem
// rechenlastigen Fragment-Shader auf dem Probe-Kontext, `readPixels` erzwingt
// das Warten auf die GPU (dessen Rueckweg-Kosten werden abgezogen). Kostet auf einer diskreten Karte unter 1 ms, auf
// einem Software-Renderer deutlich mehr — deshalb bricht die Messung ab, sobald
// das Urteil feststeht. Liefert die Dauer der Mess-Draws in ms oder null.
function messeFuellrate(gl) {
  const vsQ = 'attribute vec2 p; void main() { gl_Position = vec4(p, 0.0, 1.0); }';
  const fsQ = 'precision mediump float; uniform float k;'
    + 'void main() { vec2 u = gl_FragCoord.xy * 0.013; float a = k;'
    + ' for (int i = 0; i < 128; i++) { a = sin(a + u.x) * cos(a - u.y) + a * 0.5; }'
    + ' gl_FragColor = vec4(a, a * 0.5, 0.25, 1.0); }';
  let vs = null, fs = null, prog = null, buf = null;
  try {
    gl.canvas.width = 512;
    gl.canvas.height = 512;
    gl.viewport(0, 0, 512, 512);
    vs = gl.createShader(gl.VERTEX_SHADER);
    gl.shaderSource(vs, vsQ); gl.compileShader(vs);
    fs = gl.createShader(gl.FRAGMENT_SHADER);
    gl.shaderSource(fs, fsQ); gl.compileShader(fs);
    prog = gl.createProgram();
    gl.attachShader(prog, vs); gl.attachShader(prog, fs);
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) return null;
    gl.useProgram(prog);
    buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    const loc = gl.getAttribLocation(prog, 'p');
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
    const kLoc = gl.getUniformLocation(prog, 'k');
    const px = new Uint8Array(4);
    // Aufwaermen: Shader-Kompilierung/erste Belegung nicht mitmessen.
    gl.uniform1f(kLoc, 0.1);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, px);
    // Befund nach Review: `readPixels` kostet je Draw einen vollen
    // GPU-Rueckweg (auf echter integrierter Grafik ~2 ms), der mit der
    // Fuellrate nichts zu tun hat. Deshalb zuerst dieselben Draws auf 1x1
    // Pixel (nur Rueckweg + Draw-Overhead), dann bildschirmfuellend; je Lauf
    // zaehlt das schnellste Einzelbild (Ausreisser/Scheduler raus), und das
    // Ergebnis ist die reine Fuell-Zeit fuer 6 Draws.
    const lauf = (w, h) => {
      gl.viewport(0, 0, w, h);
      let best = Infinity;
      const t0 = performance.now();
      for (let i = 0; i < 6; i++) {
        const t = performance.now();
        gl.uniform1f(kLoc, 0.2 + i * 0.1);
        gl.drawArrays(gl.TRIANGLES, 0, 3);
        gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, px);
        best = Math.min(best, performance.now() - t);
        if (performance.now() - t0 > 4 * BENCH_HIGH_MS) break;   // Urteil steht
      }
      return best;
    };
    const rueckweg = lauf(1, 1);
    const voll = lauf(512, 512);
    if (!isFinite(rueckweg) || !isFinite(voll)) return null;
    return Math.max(0, voll - rueckweg) * 6;
  } catch (e) {
    return null;
  } finally {
    try {
      if (buf) gl.deleteBuffer(buf);
      if (prog) gl.deleteProgram(prog);
      if (vs) gl.deleteShader(vs);
      if (fs) gl.deleteShader(fs);
    } catch (e) { /* best effort */ }
  }
}
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
    if (forced === 'low' || forced === 'high' || forced === 'max') {
      gpuProbeInfo.tier = forced;
      gpuProbeInfo.grund = 'manuell (?gputier)';
      return forced;
    }
    const cv = document.createElement('canvas');
    gl = cv.getContext('webgl') || cv.getContext('experimental-webgl');
    if (!gl) {
      gpuProbeInfo.tier = 'low';
      gpuProbeInfo.grund = 'kein WebGL-Kontext';
      return 'low';
    }
    const maxTex = gl.getParameter(gl.MAX_TEXTURE_IMAGE_UNITS);
    let chip = '';
    const stub = window.__lightosGpuRendererStub;
    if (typeof stub === 'string') {
      chip = stub;
    } else {
      const dbg = gl.getExtension('WEBGL_debug_renderer_info');
      if (dbg) chip = String(gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) || '');
    }
    const benchStub = window.__lightosGpuBenchStub;
    const urteil = decideTier({
      chip, maxTex,
      messen: () => (typeof benchStub === 'number' ? benchStub : messeFuellrate(gl)),
    });
    Object.assign(gpuProbeInfo, urteil, { chip, maxTex });
    return urteil.tier;
  } catch (e) {
    gpuProbeInfo.tier = 'high';
    gpuProbeInfo.grund = 'Probe-Fehler: ' + e;
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
// VIZ-71: alles, was die Stufe im Renderer bedeutet, aus EINER Tabelle.
export const tierSettings = tierProfile(gpuTier);

export const renderer = new THREE.WebGLRenderer({
  // Low-Spec: MSAA kostet auf fill-rate-limitierten Chips ueberproportional;
  // high-performance bittet Dual-GPU-Systeme um die dedizierte Karte.
  antialias: !isLowSpec,
  powerPreference: 'high-performance',
});
// Pixel-Ratio ist QUADRATISCHE Fragment-Last: 2.0 auf dem High-DPI-Surface
// hiess 4x so viele Pixel wie 1.0 — Low-Spec deckelt auf 1.25, Hoch auf 2,
// Maximal gar nicht (VIZ-71, Tabelle in quality_tiers.js).
export const PIXEL_RATIO_CAP = pixelRatioCapFor(gpuTier);

// ── Pixeldichte: EINE Quelle (VIZ-71 S6) ────────────────────────────────────
// Basis = min(Geraete-Pixeldichte, Deckel der Stufe); die dynamische
// Aufloesung multipliziert ihre Skala darauf. Resize, Bildschirmwechsel
// (pixelRatioSignal) und die Absenkung laufen ALLE ueber applyPixelRatio —
// sonst hoebe ein Resize waehrend der Kamerafahrt die Absenkung auf, oder ein
// Monitorwechsel den Low-Spec-Deckel (das war die Falle am pixelRatioSignal).
let _deviceRatioOverride = null;
export function setDeviceRatio(r) {
  _deviceRatioOverride = (typeof r === 'number' && r > 0) ? r : null;
  applyPixelRatio();
}
export function basePixelRatio() {
  return Math.min(_deviceRatioOverride || window.devicePixelRatio || 1, PIXEL_RATIO_CAP);
}
export const dynamicResolution = createDynamicResolution({
  now: () => performance.now(),
  setTimer: (fn, ms) => setTimeout(fn, ms),
  clearTimer: (h) => clearTimeout(h),
  applyScale: () => applyPixelRatio(),
  requestRender,
  mode: tierSettings.dynamicResolution,
});
export function applyPixelRatio() {
  const soll = basePixelRatio() * dynamicResolution.scale();
  // setPixelRatio legt den Canvas-Puffer neu an — nur beim WECHSEL.
  if (Math.abs(renderer.getPixelRatio() - soll) > 1e-6) {
    renderer.setPixelRatio(soll);
    requestRender();
  }
}
// Kamera-Hook (camera/cameras.js#updateCamera/resizeOrtho).
export function noteCameraMotion() { dynamicResolution.noteCameraMotion(); }

renderer.setSize(window.innerWidth, window.innerHeight);
renderer.setPixelRatio(basePixelRatio());
renderer.shadowMap.enabled = true;
// PCFSoft sampelt deutlich mehr Shadow-Taps pro Pixel als plain PCF.
renderer.shadowMap.type = tierSettings.softShadows ? THREE.PCFSoftShadowMap : THREE.PCFShadowMap;
// console.warn statt .log: Qt spiegelt nur Warning/Error-Konsolenzeilen ins
// crash.log — so ist die Tier-Entscheidung auch nachtraeglich diagnostizierbar.
console.warn('[viz] GPU-Tier: ' + gpuTier
  + ' (grund=' + gpuProbeInfo.grund
  + ', renderer=' + gpuProbeInfo.chip
  + ', maxTextures=' + renderer.capabilities.maxTextures
  + ', pixelRatioCap=' + PIXEL_RATIO_CAP
  + ', schattenDach=' + tierSettings.shadowCap
  + ', echteLichter=' + tierSettings.realLights
  + ', dynAufloesung=' + tierSettings.dynamicResolution
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
  // Bildschirm mit anderer Skalierung verschoben) - hier mitziehen. VIZ-71:
  // ueber die eine Quelle — eine laufende Absenkung bleibt, die Basis ist neu.
  applyPixelRatio();
  requestRender();  // 3c-2 Dirty-Quelle 5 (Fenster-Resize)
});
