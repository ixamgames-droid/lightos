// VIZ-13 Schritt 3c-2: On-Demand-Rendering — Dirty-Flag-Render-Loop
// (Design: docs/VIZ13_JS_NEUAUFBAU_DESIGN.md Abschnitt (e) "On-Demand-
// Rendering (dirty-flag statt bedingungslosem rAF)").
//
// Kernidee: `animate()` rendert nicht mehr jeden Frame bedingungslos,
// sondern nur wenn "dirty" (requestRender() wurde seit dem letzten Render
// gerufen) ODER eine kontinuierliche Animation laeuft (hasLiveAnimation()).
// Die rAF-Kette selbst laeuft IMMER weiter (nie abreissen, VIZ-10-Vertrag) —
// nur der render()-Aufruf ist bedingt. Konsequenz (Design (e) Punkt 7):
// statische Szene ohne Selektion/DMX-Aenderung = ~0 Render-Last (spiegelt
// VIZ-12s "statische Szene = 0 Push-Last" auf der JS-Render-Seite).
//
// BEWUSST NULL Imports: dieses Modul ist ein reines Blatt, damit JEDES
// scene_src-Modul (state.js, bridge.js, cameras.js, tools.js, ...)
// requestRender() ohne Zyklus-Risiko importieren kann (die Modul-
// Abhaengigkeiten bleiben sternfoermig, s. state.js-Kommentar). Den
// eigentlichen render()-Aufruf + den Pro-Frame-Hook liefert app.js beim
// startRenderLoop() als Closures an.
//
// requestRender() ist ein REINER Flag-Setter (Parity-Kernannahme 3c-2):
// keine Material-/DOM-/Szenen-Seiteneffekte — die bestehenden Golden-/
// Polish-Tests lesen Objekt-/Material-Zustaende render-unabhaengig und
// bleiben dadurch byte-identisch gruen.
"use strict";

let _dirty = true;          // Start dirty: der erste Frame rendert IMMER
let _renderCount = 0;       // zaehlt Gate-Oeffnungen (= renderer.render-Aufrufe)
let _renderFn = null;       // von app.js geliefert: () => renderer.render(...)
let _perFrameFn = null;     // von app.js geliefert: Puls + Gizmo + FPS (laeuft JEDEN Tick)
const _liveAnimProbes = [];

// Dedup-Set fuer Frame-Fehler: verhindert 60x/s-Spam im DevTools-Log, wenn
// ein Frame wiederholt am selben Fehler scheitert (ehem. app.js#animate).
const _loggedTickErrors = new Set();

// ── Dirty-Flag-API ───────────────────────────────────────────────────────────
// Verdrahtungs-Karte (Design (e) "Dirty-Quellen", Stand 3c-2 Schritt 3):
//   1. dmxBatch          -> fixtures.js#updateFixture (deckt Batch-Handler +
//                           addFixture) und #removeFixture
//   2. Kamera            -> cameras.js#updateCamera + #resizeOrtho (alle
//                           Orbit/Zoom/Preset/Fit/Named-Pfade) + pointer.js#
//                           handlePointerMove-Sammelpunkt (direkter 2D-Pan!)
//   3. Selektion/Outline -> tools.js#updateOutlines (+ view-Setter-Netz)
//   4. Stage-CRUD/Resize -> stage_objects.js (create/update/remove/Handles/
//                           2D-Style/loadStageJson) + docking.js (Highlight/
//                           moveDockedFixtures) + touch.js (fabRotate/'R')
//   5. Resize/PixelRatio -> renderer.js window-resize + bridge.js
//                           pixelRatioSignal
//   6. Brightness/Settings -> lights.js#applyBrightness + bridge.js#
//                           applySettings
//   7. Kontinuierlich    -> Live-Probes (unten) statt Flag
//   +  Async-Nachlader   -> model_loader.js#onLoaded (DAE/OBJ-Callbacks)
//   +  Bridge-Direktpfade-> bridge.js jsApplyFixtureTransform/jsAlign/
//                           jsDistribute; tools.js#setEditTool (Gizmo-Gate)
//   +  Sicherheitsnetz   -> state.js view-Setter (Neuzuweisungen; In-Place-
//                           push/splice laufen ueber updateOutlines)
// BEWUSST NICHT verdrahtet: gizmo.js#attachGizmoToSelection (laeuft in
// perFrame JEDEN Tick — ein requestRender dort waere Endlos-Rendering; seine
// Eingangsgroessen sind alle quellseitig verdrahtet).
//
// ⚠️ FRAGILE DECKUNGEN (adversarialer Vollcheck 3c-2: 0 harte Findings, 3
// Hinweise — heute korrekt, bei Refactorings NICHT aufweichen):
//   D1 fixtures.js#removeFixture: der selectedFids-splice ist nur durch das
//      explizite requestRender() am Funktionsende gedeckt — nie entfernen.
//   D2 pointer.js: die drei selectedFids.push()-Stellen (Down/Aim/Marquee)
//      deckt jeweils NUR das updateOutlines() wenige Zeilen tiefer im SELBEN
//      Funktionslauf — keinen early-return dazwischen einbauen.
//   D3 app.js#wire*LateBindings: die Default-Getter der Late-Binding-Refs
//      sind stille No-Ops — eine Bootstrap-Reihenfolge-Aenderung wuerde
//      Fehler maskieren statt werfen.
export function requestRender() { _dirty = true; }

// ── Kontinuierliche Animationen (Design (e) Punkt 7) ─────────────────────────
// Eine Probe ist ein () => bool: true = "Animation laeuft gerade" -> der Loop
// rendert weiter jeden Frame, das Dirty-Flag wird dadurch effektiv nicht
// geloescht. Registriert werden: der Selektions-Puls des Stage-Elements
// (app.js) und das FPS-Overlay (camera/presets.js). Trace/Nachfahren braucht
// KEINE Probe: die Bewegung rechnet Python und trifft als dmxBatch ein
// (-> requestRender via Quelle 1); Laser-Faecher/Beams aendern sich ebenfalls
// nur durch DMX-Updates, nicht zeitgesteuert.
export function registerLiveAnimation(probeFn) { _liveAnimProbes.push(probeFn); }

export function hasLiveAnimation() {
  for (const fn of _liveAnimProbes) {
    try {
      if (fn()) return true;
    } catch (e) { /* defekte Probe darf den Loop nie stoppen */ }
  }
  return false;
}

// ── Messbarkeit (Tests/Abnahme) ──────────────────────────────────────────────
// count zaehlt die GATE-OEFFNUNGEN (Entscheidungen "jetzt rendern"), nicht den
// GL-Erfolg: schlaegt renderer.render() fehl (z.B. kein WebGL offscreen), ist
// die Entscheidung trotzdem gezaehlt und das Flag konsistent geloescht — so
// bleibt die Dirty-Logik auch im offscreen-Testlauf deterministisch messbar.
export function renderStats() {
  return { count: _renderCount, dirty: _dirty, live: hasLiveAnimation() };
}

// ── Ein Tick-Body ────────────────────────────────────────────────────────────
// Vom rAF-Loop gerufen UND (fuer deterministische Tests) direkt via
// window.__lightos.__renderTick() aufrufbar: eine offscreen/inaktive
// QtWebEngine-Seite drosselt rAF und Post-Load-Signale (Messartefakt-Falle,
// s. Second-Brain reference_qwebchannel_headless_delivery) — Tests treiben
// die Ticks deshalb selbst per runJavaScript statt auf Timing zu warten.
export function renderTick() {
  try {
    if (_perFrameFn) _perFrameFn();
    // Dirty-Gate (Design (e)): rendern NUR, wenn seit dem letzten Render
    // requestRender() gerufen wurde ODER eine kontinuierliche Animation
    // laeuft (Puls/FPS-Overlay — deren Probes halten das Gate offen, das
    // Flag wird dadurch effektiv nicht geloescht). Die rAF-Kette selbst
    // laeuft ungegated weiter (VIZ-10-Vertrag).
    if (_dirty || hasLiveAnimation()) {
      _renderCount += 1;
      _dirty = false;
      if (_renderFn) _renderFn();
    }
  } catch (err) {
    const msg = String(err && err.message || err);
    if (!_loggedTickErrors.has(msg)) {
      _loggedTickErrors.add(msg);
      console.error('renderTick() frame error (weitere gleiche Fehler werden unterdrueckt):', err);
    }
    // Frame ueberspringen — naechster Tick versucht es erneut.
  }
}

// ── Loop-Start (einmal aus app.js) ───────────────────────────────────────────
export function startRenderLoop({ render, perFrame }) {
  _renderFn = render || null;
  _perFrameFn = perFrame || null;
  function animate() {
    // rAF-Aufruf bewusst VOR dem Tick-Body: die Kette darf auch bei einem
    // Fehler im Frame niemals abreissen (VIZ-10-Vertrag, ehem. app.js).
    requestAnimationFrame(animate);
    renderTick();
  }
  animate();
}
