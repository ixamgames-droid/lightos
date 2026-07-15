// VIZ-13 Schritt 3a-4: Werkzeug-State + Selektions-/Outline-Verwaltung
// (ehem. stage_scene.html:2047-2204 setEditMode/setEditTool/Trace-Cluster/
// Readouts/Brightness-Setter, 2226-2330 applyStageEmissive/updateOutlines).
// Reines Verschieben.
import * as THREE from '../three/three.js';
import { scene } from '../scene/renderer.js';
import { applyBrightness } from '../scene/lights.js';
import { fixtures, stageObjects, settings, view } from '../state.js';
import { updateResizeHandles } from '../stage/stage_objects.js';
import { wireFixturesLateBindings } from '../fixtures/fixtures.js';
import { requestRender } from '../scene/render_loop.js';  // VIZ-13 3c-2

let _userBrightnessOverride = null;  // wenn Slider manuell gesetzt

export function setEditMode(mode) {
  view.editMode = mode || 'view';
  const banner = document.getElementById('mode-banner');
  if (view.editMode === 'edit') {
    banner.textContent = 'FIXTURE EDIT – Ziehen=Bewegen | Rechtsklick/Lang-Drücken=Platzieren | 📌 Taste unten rechts';
    banner.style.display = 'block';
  } else if (view.editMode === 'stage') {
    banner.textContent = 'BÜHNE BEARBEITEN – Tippen=Auswählen | Ziehen=Verschieben | ↻ / 🗑 unten rechts';
    banner.style.display = 'block';
  } else {
    banner.style.display = 'none';
  }
  updateFABs();
  // Edit-Werkzeug-Leiste nur im Fixture-Edit-Modus zeigen.
  const etb = document.getElementById('edit-toolbar');
  if (etb) etb.style.display = (view.editMode === 'edit') ? 'flex' : 'none';
  if (view.editMode === 'edit') {
    setEditTool(view.editTool);
  } else if (bridgeRef.get() && bridgeRef.get().stopTrace) {
    try { bridgeRef.get().stopTrace(); } catch (e) {}   // Nachfahren beim Modus-Verlassen stoppen
  }
  // Auto-Brightness: edit/stage modes brighten the scene for visibility
  if (settings.autoBrightness && _userBrightnessOverride === null) {
    if (view.editMode === 'edit' || view.editMode === 'stage') {
      applyBrightness(0.65);
    } else {
      applyBrightness(0.20);
    }
    // Inform Python so UI slider reflects current value
    const bridge = bridgeRef.get();
    if (typeof bridge !== 'undefined' && bridge && bridge.brightnessChanged) {
      try { bridge.brightnessChanged(settings.brightness); } catch (e) {}
    }
  }
  // Clear selection on mode change
  view.selectedFids = [];
  view.selectedStageId = null;
  updateOutlines();
}

// Edit-Werkzeug umschalten (von den Buttons oben). Aktualisiert Highlight +
// Hinweis-Banner. Wirkt nur im Fixture-Edit-Modus.
export function setEditTool(tool) {
  // VIZ-13 3b-G: move_y/rotate entfallen — das Move/Rotate-Gizmo (interaction/
  // gizmo.js) uebernimmt Hoehe + Rotation zoom-korrekt am selektierten Fixture.
  // 'move_xz' bleibt der Standard: Auswaehlen + XZ-Ziehen am Boden; das Gizmo
  // erscheint automatisch bei Auswahl im 3D-Bau-Modus.
  view.editTool = ['move_xz', 'aim', 'trace'].includes(tool) ? tool : 'move_xz';
  // Beim Wechsel WEG vom Trace-Werkzeug ein laufendes Nachfahren stoppen.
  const bridge0 = bridgeRef.get();
  if (view.editTool !== 'trace' && bridge0 && bridge0.stopTrace) {
    try { bridge0.stopTrace(); } catch (e) {}
  }
  const map = [['tool-move-xz','move_xz'], ['tool-aim','aim'], ['tool-trace','trace']];
  for (const [id, t] of map) {
    const b = document.getElementById(id);
    if (b) b.classList.toggle('active', t === view.editTool);
  }
  const tp = document.getElementById('trace-panel');
  if (tp) tp.style.display = (view.editMode === 'edit' && view.editTool === 'trace') ? 'flex' : 'none';
  const banner = document.getElementById('mode-banner');
  if (view.editMode === 'edit' && banner) {
    banner.style.display = 'block';
    banner.textContent =
      view.editTool === 'move_xz' ? 'BEWEGEN – Gerät antippen = auswählen · am Boden ziehen (X/Z) · Gizmo-Pfeile: Achse/Höhe · Ringe: drehen (Strg = frei)'
      : view.editTool === 'aim' ? 'ZIELEN – Gerät antippen = auswählen · Boden/Wand antippen → ausrichten (MH fahren Pan/Tilt)'
      : 'NACHFAHREN – Moving Heads auswählen, dann Boden/Wand antippen → fahren dort eine Form ab (Tool wechseln = Stopp)';
  }
  // 3c-2: das Gizmo-Gate (attachGizmoToSelection, laeuft pro Frame) haengt am
  // editTool — der Werkzeugwechsel laesst das Gizmo erscheinen/verschwinden
  // und braucht dafuer einen Frame.
  requestRender();
}

// ── Trace-Einstellungen (Form / Größe / Tempo / Speichern) ───────────────────
export let traceShape = 'circle';      // 'circle' | 'line' | 'rect'
export let traceRadius = 1.0;          // Meter
export let traceIntervalMs = 60;       // Tempo (ms je Punkt)
export let lastTraceTarget = null;     // {x,y,z,nx,ny,nz} vom letzten Tipp

export function setTraceShape(s) {
  traceShape = (s === 'line' || s === 'rect') ? s : 'circle';
  for (const [id, sh] of [['tp-circle','circle'], ['tp-line','line'], ['tp-rect','rect']]) {
    const b = document.getElementById(id);
    if (b) b.classList.toggle('active', sh === traceShape);
  }
  restartTraceIfActive();
}
export function onTraceRadius(v) {
  traceRadius = Math.max(0.2, Number(v) / 10);
  const el = document.getElementById('trace-radius-val');
  if (el) el.textContent = traceRadius.toFixed(1) + ' m';
  restartTraceIfActive();
}
export function onTraceSpeed(v) {
  traceIntervalMs = Math.max(20, parseInt(v, 10));
  const el = document.getElementById('trace-speed-val');
  if (el) el.textContent = traceIntervalMs + ' ms';
  restartTraceIfActive();
}
export function _traceSpec() {
  if (!lastTraceTarget) return null;
  return Object.assign({
    shape: traceShape, radius: traceRadius, count: 48,
    intervalMs: traceIntervalMs, fids: view.selectedFids.slice(),
  }, lastTraceTarget);
}
export function setLastTraceTarget(t) { lastTraceTarget = t; }
export function restartTraceIfActive() {
  const bridge = bridgeRef.get();
  if (view.editTool === 'trace' && lastTraceTarget && view.selectedFids.length > 0 &&
      bridge && bridge.startTrace) {
    try { bridge.startTrace(JSON.stringify(_traceSpec())); } catch (e) {}
  }
}
export function saveTraceSeq() {
  const spec = _traceSpec();
  if (!spec || view.selectedFids.length === 0) {
    showEditReadout('Erst Moving Heads wählen + eine Fläche antippen, dann speichern.');
    return;
  }
  const bridge = bridgeRef.get();
  if (bridge && bridge.saveTraceSequence) {
    try { bridge.saveTraceSequence(JSON.stringify(spec)); } catch (e) {}
  }
}

// Transientes Mess-/Wert-Readout während eines Edit-Drags (oben rechts).
export function showEditReadout(text) {
  const ri = document.getElementById('ruler-info');
  if (!ri) return;
  ri.textContent = text;
  ri.style.display = 'block';
}
export function hideEditReadout() {
  if (view.mode === '3D') {
    const ri = document.getElementById('ruler-info');
    if (ri) ri.style.display = 'none';
  }
}

// Mess-Anzeige: bei genau ZWEI ausgewaehlten Fixtures den Abstand (Meter) zeigen.
// (Grundlage fuers exakte Ausmessen — z.B. wie weit zwei Moving Heads stehen.)
export function updateMeasureReadout() {
  const ri = document.getElementById('ruler-info');
  if (!ri) return;
  if (view.editMode === 'edit' && view.selectedFids.length === 2 &&
      fixtures[view.selectedFids[0]] && fixtures[view.selectedFids[1]]) {
    const a = fixtures[view.selectedFids[0]].group.position;
    const b = fixtures[view.selectedFids[1]].group.position;
    const dx = a.x - b.x, dy = a.y - b.y, dz = a.z - b.z;
    const d = Math.sqrt(dx*dx + dy*dy + dz*dz);
    ri.textContent = '📏 Abstand: ' + d.toFixed(2) + ' m  (Δx ' + Math.abs(dx).toFixed(2) +
                     ' · Δy ' + Math.abs(dy).toFixed(2) + ' · Δz ' + Math.abs(dz).toFixed(2) + ')';
    ri.style.display = 'block';
  } else if (view.mode === '3D') {
    ri.style.display = 'none';
  }
}

// Direkter Slider-Setter (von Python aufgerufen) - markiert User-Override
export function setBrightnessManual(b) {
  _userBrightnessOverride = b;
  applyBrightness(b);
}

// Reset auto-brightness (User klickt "Auto")
export function resetBrightnessAuto() {
  _userBrightnessOverride = null;
  // Trigger current edit mode brightness
  setEditMode(view.editMode);
}

// ============================================================================
// Selection / outlines
// ============================================================================
// Apply an emissive RGB (0..1) to a mesh or all child meshes of a Group.
export function applyStageEmissive(target, r, g, b) {
  if (!target) return;
  if (target.isMesh) {
    if (target.material && target.material.emissive) {
      target.material.emissive.setRGB(r, g, b);
    }
  } else if (target.isGroup || target.children) {
    target.traverse(c => {
      if (c.isMesh && c.material && c.material.emissive) {
        c.material.emissive.setRGB(r, g, b);
      }
    });
  }
}

export function updateOutlines(notify = true) {
  // notify=false: NUR die Visuals aktualisieren, OHNE die Auswahl an Python
  // zurueckzumelden (VIZ-14 Slice 1b). Wird von jsApplyExternalSelection genutzt,
  // wenn die Auswahl GERADE VON Python kam — sonst liefe sie via
  // fixtureSelectionChanged sofort wieder nach Python zurueck (Echo/Loop).
  // Fixture outlines: tint icon ring in 2D, otherwise fall back to a wireframe-like hue
  for (const fid in fixtures) {
    const f = fixtures[fid];
    const sel = view.selectedFids.includes(Number(fid));
    if (f.icon && f.icon.userData.ring && f.icon.userData.ring.material) {
      f.icon.userData.ring.material.opacity = sel ? 1.0 : 0.0;
    }
    // 3D selection: brighten lens emissive a bit when no DMX intensity
    if (f.lens && f.lens.material) {
      if (sel) {
        // ensure visible cue
        if (!f._selBorder) {
          const geo = new THREE.RingGeometry(0.4, 0.55, 24);
          const mat = new THREE.MeshBasicMaterial({ color: 0x66ccff, transparent: true, opacity: 0.85, side: THREE.DoubleSide });
          const ring = new THREE.Mesh(geo, mat);
          ring.rotation.x = -Math.PI / 2;
          ring.position.y = -0.5;
          f.group.add(ring);
          f._selBorder = ring;
        }
        f._selBorder.visible = true;
      } else if (f._selBorder) {
        f._selBorder.visible = false;
      }
    }
  }
  // Stage object highlight: selektiertes Element gelb (sehr auffaellig), andere unmarkiert
  for (const id in stageObjects) {
    const so = stageObjects[id];
    if (id === view.selectedStageId) {
      // BoxHelper in hellgelb mit dicker Linie
      if (!so._helper) {
        so._helper = new THREE.BoxHelper(so.mesh, 0xffd700);
        if (so._helper.material) {
          so._helper.material.linewidth = 4;
          so._helper.material.depthTest = false;
          so._helper.material.transparent = true;
          so._helper.material.opacity = 1.0;
        }
        scene.add(so._helper);
      } else {
        so._helper.material.color.setHex(0xffd700);
        so._helper.material.opacity = 1.0;
      }
      so._helper.update();
      so._helper.visible = true;
      // Labels ueber Elementen wurden auf Wunsch entfernt (stoeren) - nichts tun
      // Emissive-Boost als Start-Wert (animate() pulsiert weiter)
      applyStageEmissive(so.mesh, 0.4, 0.25, 0.0);
    } else {
      if (so._helper) so._helper.visible = false;
      // Emissive zuruecksetzen
      applyStageEmissive(so.mesh, 0, 0, 0);
    }
  }
  // Resize-Handles neu aufbauen (nur sichtbar wenn editMode == 'stage' + Selektion)
  updateResizeHandles();
  // Top-Banner: zeige welche Art von Element selektiert ist
  const sb = document.getElementById('selection-banner');
  const sbt = document.getElementById('selection-banner-text');
  if (sb && sbt) {
    if (view.selectedStageId && stageObjects[view.selectedStageId]) {
      const so = stageObjects[view.selectedStageId];
      const typeLabels = {
        floor: 'BODEN',
        platform: 'PLATTFORM', truss_h: 'TRASSE (horizontal)', truss_v: 'TRASSE (vertikal)',
        wall: 'WAND', led_wall: 'LED-WAND', speaker: 'LAUTSPRECHER',
        audience: 'PUBLIKUM', dj_booth: 'DJ-BOOTH'
      };
      const nm = so.data.name || '';
      const tp = typeLabels[so.data.type] || String(so.data.type || '').toUpperCase();
      sbt.textContent = nm ? (tp + ' - ' + nm) : tp;
      sb.style.display = 'block';
    } else if (view.selectedFids.length > 0) {
      sbt.textContent = 'FIXTURE x' + view.selectedFids.length;
      sb.style.display = 'block';
    } else {
      sb.style.display = 'none';
    }
  }
  // Notify python of selection — uebersprungen bei notify=false (die Auswahl kam
  // gerade VON Python; ein Rueckruf waere ein Echo/Loop, VIZ-14 Slice 1b).
  if (notify) {
    const bridge = bridgeRef.get();
    if (bridge && bridge.fixtureSelectionChanged) {
      try { bridge.fixtureSelectionChanged(JSON.stringify(view.selectedFids)); } catch (e) {}
    }
    if (bridge && bridge.stageSelectionChanged) {
      try { bridge.stageSelectionChanged(view.selectedStageId || ''); } catch (e) {}
    }
  }
  updateFABs();
  // 3c-2 Dirty-Quelle 3 (Selektion/Outlines): Ring-Opacities, Sel-Border,
  // BoxHelper, Emissive-Reset — alle Selektionswechsel laufen hier durch.
  requestRender();
}

// VIZ-14 (Slice 1b): globale/Programmer-Auswahl (aus Python via Poll) auf die
// 3D-Szene anwenden. Setzt view.selectedFids und aktualisiert die Outlines OHNE
// Echo an Python (updateOutlines(false)) — der Loop-Brecher der Rueckrichtung.
// Defensiv: ungueltiges JSON / Nicht-Array wird ignoriert (leert die Auswahl NUR
// bei explizit leerem Array, nicht bei Parse-Fehlern).
export function jsApplyExternalSelection(json) {
  let fids;
  try {
    fids = JSON.parse(json);
  } catch (e) {
    return;
  }
  if (!Array.isArray(fids)) return;
  view.selectedFids = fids.map(Number).filter(n => !Number.isNaN(n));
  updateOutlines(false);
}

// ============================================================================
// Floating Action Buttons (FABs) – Sichtbarkeit (ehem. stage_scene.html:3230-3239)
// Hierher gezogen statt nach interaction/touch.js, weil updateOutlines()
// (oben in diesem Modul) sie am Ende jedes Aufrufs mit-aktualisiert - die
// fab*()-Handlerfunktionen selbst (Klick-Aktionen) bleiben in
// interaction/touch.js (Design-Dokument nennt touch.js fuer den
// Touch-/FAB-Cluster).
export function updateFABs() {
  const btnDelete = document.getElementById('fab-delete');
  const btnRotate = document.getElementById('fab-rotate');
  const btnPlace  = document.getElementById('fab-place');
  const hasFixtureSel = view.editMode === 'edit' && view.selectedFids.length > 0;
  const hasStageSel   = view.editMode === 'stage' && !!view.selectedStageId;
  if (btnDelete) btnDelete.style.display = (hasFixtureSel || hasStageSel) ? 'flex' : 'none';
  if (btnRotate) btnRotate.style.display = (hasFixtureSel || hasStageSel) ? 'flex' : 'none';
  if (btnPlace)  btnPlace.style.display  = (view.editMode === 'edit') ? 'flex' : 'none';
}

// ── Spaet-Bindung (bridge entsteht erst beim WebChannel-Connect,
// siehe Design-Dokument "Kern-Gotcha") ──────────────────────────────────────
export const bridgeRef = { get: () => null };
export function wireToolsLateBindings({ getBridge }) {
  bridgeRef.get = getBridge;
}

// removeFixture() in fixtures/fixtures.js ruft updateOutlines() ueber diese
// Spaet-Bindung auf (Design-Dokument "Kern-Gotcha" - Aufloesung des
// zirkulaeren Imports fixtures.js<->tools.js).
wireFixturesLateBindings({ updateOutlines });
