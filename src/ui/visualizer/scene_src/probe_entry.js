// VIZ-13 Schritt 3a-1..3a-3: TEST-ONLY Entry-Modul fuer die ESM-Machbarkeits-
// Probe-Page (stage_scene_esm_probe.html). Importiert NUR das Blatt-Modul
// probe_util.js und exponiert dessen Ergebnis als `window.__lightosEsmOk` -
// das ist der Vertrag, den tests/test_viz13_esm_smoke.py per QWebEngineView
// abfragt.
//
// WICHTIG (seit Schritt 3a-4): dieses Modul ist NICHT mehr identisch mit
// scene_src/app.js - seit 3a-4 ist app.js das ECHTE Produktiv-Entry-Modul
// (instanziiert THREE.WebGLRenderer, was offscreen ohne GL fehlschlaegt).
// probe_entry.js bleibt bewusst minimal (kein Renderer, kein Modul-Split-
// Umfang) fuer den reinen ESM-Ladereihenfolge-/three-Wrapper-/state.js-Beleg
// aus 3a-1..3a-3 - der VOLLE Modul-Split wird stattdessen ueber die echte
// stage_scene.html + tests/test_viz13_scene_modules_smoke.py (3a-4) belegt.
import { probeThreeNamespace, probeThreeWrapper, probeState } from './probe_util.js';

const probe = { ...probeThreeNamespace(), ...probeThreeWrapper(), ...probeState() };
window.__lightosEsmOk = true;
window.__lightosEsmProbe = probe;
