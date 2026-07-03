// VIZ-13 Schritt 3a-3: geteilter globaler State als eigenes ES-Modul.
//
// WICHTIG (Design-Dokument Abschnitt (a), "Kern-Gotcha beim Split" + Risiko 1
// aus dem Auftrag): dieses Modul wird in 3a-3 NUR angelegt und 1:1 spiegel-
// gleich zum bestehenden State-Block in stage_scene.html befuellt - es wird
// hier noch NICHT importiert/genutzt. stage_scene.html bleibt in diesem
// Schritt der EINE <script>-Block mit ihren eigenen `let`/`const`-Bindings.
// Der eigentliche Umzug (stage_scene.html importiert von hier, eigene
// Bindings werden entfernt) passiert in 3a-4, damit dieser Diff klein und
// pruefbar bleibt und 3a-3 allein gruen ist (keine Verhaltensaenderung).
//
// Warum kein `export let mode` fuer viewMode/activeCam: ein re-exportiertes
// `let` ist in ES-Modulen zwar live bindend fuer andere Module, aber NICHT
// von aussen zuweisbar (`import { x } from './state.js'; x = 1` ist ein
// SyntaxError - Import-Bindings sind read-only). viewMode/activeCam werden
// im bestehenden Code jedoch direkt neu zugewiesen (stage_scene.html:1995-96,
// `viewMode = ...; activeCam = ...`), nicht nur mutiert. Deshalb: Getter/
// Setter-Objekt `view` (siehe unten) statt zweier re-exportierter `let`.
// selectedFids/selectedStageId haben dasselbe Zuweisungsmuster (komplette
// Ersetzung, z.B. `selectedFids = [fid]`, `selectedStageId = null`) - daher
// ebenfalls ueber `view`-Getter/Setter statt eigener re-exportierter `let`.
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

let _viewMode = '3D';        // '2D' | '3D' (stage_scene.html:213)
let _activeCam = null;       // wird von aussen mit perspectiveCam/orthoCam
                              // befuellt, sobald die Kamera-Objekte existieren
                              // (Kamera-Erzeugung wandert erst in einem
                              // spaeteren 3a-Schritt hierher - state.js kennt
                              // in 3a-3 noch keine THREE-Objekte).
let _selectedFids = [];      // fid numbers (stage_scene.html:2207)
let _selectedStageId = null; // stage_scene.html:2208

export const view = {
  get mode() { return _viewMode; },
  set mode(v) { _viewMode = v; },

  get activeCam() { return _activeCam; },
  set activeCam(v) { _activeCam = v; },

  get selectedFids() { return _selectedFids; },
  set selectedFids(v) { _selectedFids = v; },

  get selectedStageId() { return _selectedStageId; },
  set selectedStageId(v) { _selectedStageId = v; },
};
