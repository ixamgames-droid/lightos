// VIZ-13 Schritt 3a-4: geteilter globaler State als eigenes ES-Modul - JETZT
// tatsaechlich genutzt (Umzug aus stage_scene.html abgeschlossen).
//
// Warum kein `export let mode` fuer viewMode/activeCam: ein re-exportiertes
// `let` ist in ES-Modulen zwar live bindend fuer andere Module, aber NICHT
// von aussen zuweisbar (`import { x } from './state.js'; x = 1` ist ein
// SyntaxError - Import-Bindings sind read-only). viewMode/activeCam werden
// im bestehenden Code jedoch direkt neu zugewiesen (ehem. stage_scene.html
// 1995-96, `viewMode = ...; activeCam = ...`), nicht nur mutiert. Deshalb:
// Getter/Setter-Objekt `view` (siehe unten) statt re-exportierter `let`s.
// selectedFids/selectedStageId/editMode/editTool haben dasselbe Zuweisungs-
// muster (komplette Ersetzung, z.B. `selectedFids = [fid]`) - daher
// ebenfalls ueber `view`-Getter/Setter statt eigener re-exportierter `let`s.
//
// 3a-4-Erweiterung ggue. 3a-3: zusaetzlich zu mode/activeCam/selectedFids/
// selectedStageId haelt `view` jetzt auch editMode/editTool (ehem. globale
// `let`s bei stage_scene.html:214/219) sowie die Kamera-Sphaerik theta/phi/
// radius (ehem. stage_scene.html:3273) - alle werden von mehreren Modulen
// (interaction/*, camera/cameras.js, bridge/bridge.js) gelesen UND komplett
// neu zugewiesen, genau das Zuweisungsmuster, fuer das dieses Getter/Setter-
// Pattern gebaut wurde. Das haelt die Modul-Abhaengigkeiten sternfoermig auf
// state.js statt N-zu-N zwischen den Interaction-/Kamera-Modulen.
//
// fixtures/stageObjects/topDownIcons/settings bleiben dagegen `const`-Objekte:
// der bestehende Code mutiert nur ihren Inhalt (`fixtures[fid] = {...}`,
// `settings.brightness = b`, `stageObjects[id] = {...}`), reassigned nie die
// Bindings selbst - ein re-exportiertes `const`-Objekt ist dafuer ausreichend
// und bleibt referenzgleich fuer alle Module, die es importieren.

"use strict";

// ----------------------------------------------------------------------------
// Objekt-State (Referenzen bleiben stabil, nur Inhalt wird mutiert)
// ----------------------------------------------------------------------------

// fid -> {...} (stage_scene.html:1009)
export const fixtures = {};

// id -> { mesh, data } - custom editable objects (stage_scene.html:284)
export const stageObjects = {};

// fid -> sprite/mesh - Top-Down-Icon-Parallelwelt, bleibt in 3a intakt
// (stirbt erst in 3c, siehe Design-Dokument Abschnitt (d)) (stage_scene.html:1011)
export const topDownIcons = {};

// Renderer-/Interaktions-Einstellungen (stage_scene.html:227-240)
export const settings = {
  beamOpacity: 0.85,
  showCones: true,
  showFloorSpots: true,
  showFog: true,
  stagePreset: 'simple',
  snapToGrid: true,
  gridStep: 1.0,
  brightness: 0.20,        // 0.0 = pitch black, 1.0 = bright daylight
  autoBrightness: true,    // auto-bump brightness when in edit modes
  dockEnabled: false,      // opt-in: Strahler rasten an Trassen/Plattformen ein
};

// ----------------------------------------------------------------------------
// View-Accessor: primitive/reassignte Flags ueber Getter/Setter statt
// re-exportiertem `let` (Design-Risiko 1 - siehe Kommentar oben).
// ----------------------------------------------------------------------------

let _viewMode = '3D';        // '2D' | '3D' (ehem. stage_scene.html:213)
let _activeCam = null;       // perspectiveCam|orthoCam, von camera/cameras.js befuellt
let _selectedFids = [];      // fid numbers (ehem. stage_scene.html:2207)
let _selectedStageId = null; // ehem. stage_scene.html:2208
let _editMode = 'view';      // 'view' | 'edit' | 'stage' (ehem. stage_scene.html:214)
let _editTool = 'move_xz';   // 'move_xz'|'aim'|'trace' (VIZ-13 3b-G: move_y/rotate -> Gizmo)

// Kamera-Sphaerik (Eigenbau-Orbit, ehem. stage_scene.html:3273) - kommt erst
// in 3b durch OrbitControls-Objekt-State ab; in 3a bleibt es primitive State.
let _theta = 0.3, _phi = 1.1, _radius = 22;

export const view = {
  get mode() { return _viewMode; },
  set mode(v) { _viewMode = v; },

  get activeCam() { return _activeCam; },
  set activeCam(v) { _activeCam = v; },

  get selectedFids() { return _selectedFids; },
  set selectedFids(v) { _selectedFids = v; },

  get selectedStageId() { return _selectedStageId; },
  set selectedStageId(v) { _selectedStageId = v; },

  get editMode() { return _editMode; },
  set editMode(v) { _editMode = v; },

  get editTool() { return _editTool; },
  set editTool(v) { _editTool = v; },

  get theta() { return _theta; },
  set theta(v) { _theta = v; },

  get phi() { return _phi; },
  set phi(v) { _phi = v; },

  get radius() { return _radius; },
  set radius(v) { _radius = v; },
};
