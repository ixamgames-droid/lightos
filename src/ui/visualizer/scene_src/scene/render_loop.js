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
// Von allen visuellen Mutationsquellen gerufen (dmxBatch, Kamera, Selektion/
// Outlines, Stage-CRUD, Settings/Brightness, Resize, Drags — vollstaendige
// Liste s. Design (e) "Dirty-Quellen" + Verdrahtungs-Kommentar in app.js).
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
    // Schritt 1 (3c-2): Render noch BEDINGUNGSLOS wie vor dem Umbau — das
    // Dirty-Gate wird in Schritt 2 scharf geschaltet. Zaehler-/Flag-
    // Bookkeeping laeuft schon identisch zur Gate-Version mit.
    _renderCount += 1;
    _dirty = false;
    if (_renderFn) _renderFn();
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
