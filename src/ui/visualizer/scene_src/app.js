// VIZ-13 Schritt 3a-4: Entry-Modul - ersetzt den EINEN <script>-Block in
// stage_scene.html. Importiert alle Teilmodule (das loest ihre Top-Level-
// Effekte aus - Scene/Renderer/Kameras/Grid/Lichter werden beim Import
// instanziiert, exakt wie vorher beim sequentiellen Durchlauf des einen
// Skripts), verdrahtet die Spaet-Bindungen fuer zirkulaere Abhaengigkeiten
// (Design-Dokument Abschnitt (a) "Kern-Gotcha"), haengt die globalen
// onclick/oninput-Handler-Namen aus stage_scene.html an `window` (die HTML
// blieb unveraendert - Buttons rufen weiterhin z.B. `setEditTool(...)` als
// globale Funktion auf) und startet den Render-Loop + Bridge-Poll wie im
// Original.
import { scene, renderer } from './scene/renderer.js';
import { applyBrightness } from './scene/lights.js';
import './scene/grid_floor.js';
import { view, fixtures, stageObjects, settings } from './state.js';

import './camera/cameras.js';
import { setViewMode } from './stage/view_mode.js';
import {
  setCameraPreset, fitAll, fitSelected, setFpsVisible, fpsTick,
  wirePresetsLateBindings, saveNamedCamera, applyNamedCamera, getNamedCameras,
} from './camera/presets.js';

import {
  updateResizeHandles, resizeHandles, getStageJson, loadStageJson,
  clearStageObjects, wireStageObjectsLateBindings,
} from './stage/stage_objects.js';
import { dockHighlight, wireDockingLateBindings } from './stage/docking.js';

import {
  setEditMode, setEditTool, setTraceShape, onTraceRadius, onTraceSpeed,
  saveTraceSeq, setBrightnessManual, resetBrightnessAuto, updateOutlines,
  applyStageEmissive, wireToolsLateBindings,
} from './interaction/tools.js';
import { wirePointerLateBindings } from './interaction/pointer.js';
import { attachGizmoToSelection } from './interaction/gizmo.js';  // VIZ-13 3b-G
import { fabDelete, fabRotate, fabPlace, wireTouchLateBindings } from './interaction/touch.js';

import { getBridge, tryChannel, jsAddStageObject } from './bridge/bridge.js';
import { removeFixture as _removeFixtureForTouch } from './fixtures/fixtures.js';
import {
  startRenderLoop, requestRender, registerLiveAnimation, renderStats, renderTick,
} from './scene/render_loop.js';

// ── Spaet-Bindungen verdrahten (Design-Dokument "Kern-Gotcha") ─────────────
// interaction/tools.js hat wireFixturesLateBindings({updateOutlines}) bereits
// selbst beim eigenen Modul-Load aufgerufen (siehe Ende von
// interaction/tools.js), weil das ohne Zyklus direkt dort verdrahtbar ist -
// hier nur noch die Bindungen, die `bridge` bzw. `removeFixture` betreffen
// (die erst nach dem Import ALLER beteiligten Module verdrahtet werden
// koennen, da ein direkter Import sonst einen echten ES-Modul-Zyklus waere).
wireToolsLateBindings({ getBridge });
wirePointerLateBindings({ getBridge });
wireTouchLateBindings({ getBridge, removeFixture: _removeFixtureForTouch });
wireDockingLateBindings({ getBridge });
wireStageObjectsLateBindings({ getBridge, updateOutlines, dockHighlight });
wirePresetsLateBindings({ getBridge });

// ============================================================================
// Render loop (3c-2: On-Demand — Loop-Mechanik lebt in scene/render_loop.js)
// ============================================================================
// perFrameUpdate laeuft bei JEDEM rAF-Tick, auch wenn NICHT gerendert wird:
// (a) der Selektions-Puls mutiert Emissive/Handle-Skala zeitbasiert (die
//     zugehoerige Live-Animation-Probe unten haelt den Loop solange am
//     Rendern, wie ein Stage-Element selektiert ist),
// (b) attachGizmoToSelection() MUSS vor jedem Render die Gizmo-Transform
//     aktuell halten (folgt dem Auswahl-Schwerpunkt live, auch im Drag),
// (c) fpsTick() misst die Frame-Zeiten (No-Op solange Overlay aus).
function perFrameUpdate() {
  // Pulsierende Emissive-Farbe fuer das selektierte Stage-Element (sehr sichtbar)
  if (view.selectedStageId && stageObjects[view.selectedStageId]) {
    const so = stageObjects[view.selectedStageId];
    const t = Date.now() * 0.005;
    const pulse = 0.5 + 0.5 * Math.sin(t);
    applyStageEmissive(so.mesh, pulse * 0.7, pulse * 0.45, 0.0);
    // Resize-Handles pulsen ebenfalls (Skala leicht moduliert)
    const handleScale = 1.0 + 0.15 * Math.sin(t * 1.4);
    for (const h of resizeHandles) {
      h.scale.set(handleScale, handleScale, handleScale);
    }
    if (so._helper) so._helper.update();
  }
  // VIZ-13 3b-G: Move/Rotate-Gizmo an die aktuelle Auswahl heften (Sichtbarkeit/
  // Position/Skala pro Frame — folgt so live dem Schwerpunkt, auch waehrend des
  // Drags, und haelt konstante Bildschirmgroesse).
  attachGizmoToSelection();
  fpsTick();
}

// Kontinuierliche Animation (Design (e) Punkt 7): solange ein Stage-Element
// selektiert ist, pulsiert seine Emissive -> der Loop muss jeden Frame
// rendern. Nach dem Deselektieren faellt der Loop automatisch in Idle zurueck.
// (Wirkung erst mit dem Dirty-Gate in render_loop.js Schritt 2.)
registerLiveAnimation(() => !!(view.selectedStageId && stageObjects[view.selectedStageId]));

startRenderLoop({
  render: () => renderer.render(scene, view.activeCam),
  perFrame: perFrameUpdate,
});

// Initial Brightness anwenden (Default = dunkel fuer Beam-Wiedergabe)
applyBrightness(settings.brightness);

// ============================================================================
// Globale onclick/oninput-Handler (stage_scene.html-Buttons rufen diese als
// freistehende globale Funktionen auf, z.B. onclick="setEditTool('move_xz')")
// ============================================================================
window.setEditTool = setEditTool;
window.setTraceShape = setTraceShape;
window.onTraceRadius = onTraceRadius;
window.onTraceSpeed = onTraceSpeed;
window.saveTraceSeq = saveTraceSeq;
window.fabRotate = fabRotate;
window.fabDelete = fabDelete;
window.fabPlace = fabPlace;

// ============================================================================
// Qt WebChannel starten (ehem. stage_scene.html:3513 `setTimeout(tryChannel, 200)`)
// ============================================================================
setTimeout(tryChannel, 200);

// ============================================================================
// Expose for debug (ehem. stage_scene.html:3555-3559 `window.__lightos`)
// ============================================================================
window.__lightos = {
  fixtures, stageObjects, settings,
  setViewMode, setEditMode, getStageJson, loadStageJson,
  addStageObject: jsAddStageObject,
  clearStageObjects, updateResizeHandles, resizeHandles: () => resizeHandles,
  setBrightnessManual, resetBrightnessAuto, applyBrightness,
  // VIZ-13 Schritt 3b-K-1: Kamera-Presets + Fit/Fit-Selected + FPS-Overlay
  setCameraPreset, fitAll, fitSelected, setFpsVisible,
  // VIZ-13 Schritt 3b-K-2: benannte Kameras (Speichern/Anwenden/Auflisten)
  saveNamedCamera, applyNamedCamera, getNamedCameras,
  // VIZ-13 Schritt 3c-2: On-Demand-Render-API. requestRender = reiner
  // Flag-Setter (Parity-Kernannahme); renderStats + __renderTick sind die
  // deterministischen Test-Hooks (offscreen drosselt rAF + Post-Load-Signale,
  // s. render_loop.js — Tests treiben die Ticks selbst per runJavaScript).
  requestRender, renderStats, __renderTick: renderTick,
};

// Init-Flag fuer den Smoke-Test (VIZ-13 3a-4): belegt, dass app.js komplett
// durchgelaufen ist (alle Module importiert, Bridge-Poll gestartet, Render-
// Loop laeuft). Zusaetzlich zum bereits bestehenden window.__lightos-Vertrag
// (der unveraendert bleibt, siehe Design-Dokument Leitprinzip Punkt 3).
window.__lightosAppReady = true;
