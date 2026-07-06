// VIZ-13 Schritt 3a-4: Qt WebChannel - Bridge-Vertrag (ehem.
// stage_scene.html:3317-3513 applySettings/jsAdd.../pushTransformsToPython/
// tryChannel). Reines Verschieben - ALLE 14 Signal-Connects + Slot-Aufrufe
// 1:1 erhalten (Design-Dokument Leitprinzip).
import * as THREE from '../three/three.js';
import { renderer, scene } from '../scene/renderer.js';
import { applyBrightness } from '../scene/lights.js';
import { fixtures, settings, view } from '../state.js';
import { addFixture, removeFixture, updateFixture } from '../fixtures/fixtures.js';
import { setViewMode } from '../stage/view_mode.js';
import { setEditMode, setBrightnessManual, resetBrightnessAuto, updateOutlines } from '../interaction/tools.js';
import { setFpsVisible } from '../camera/presets.js';
import {
  loadStageJson, createStageObject, removeStageObject, updateStageObjectProps,
  setResizeModeEnabled,
} from '../stage/stage_objects.js';
import { hideTooltip } from '../interaction/pointer.js';
import { resetCameraView } from '../camera/cameras.js';
import { setCameraPreset, setNamedCameras } from '../camera/presets.js';
import { deg2rad, rad2deg } from '../scene/renderer.js';
import { clearDockHighlight } from '../stage/docking.js';
import { requestRender } from '../scene/render_loop.js';  // VIZ-13 3c-2

// ============================================================================
// Python bridge actions used externally
// ============================================================================
export function jsAddStageObject(type) {
  return createStageObject(type, null, null, null, 0, null, null);
}

export function jsRemoveStageObject(id) {
  removeStageObject(id);
}

export function jsSelectStageObject(id) {
  view.selectedStageId = id || null;
  updateOutlines();
}

export function jsApplyFixtureTransform(fid, x, y, z, rotX, rotY, rotZ) {
  const f = fixtures[fid];
  if (!f) return;
  hideTooltip();   // VIZ-10: Panel-Eingabe darf keinen veralteten Tooltip stehen lassen
  if (x != null) f.group.position.x = x;
  if (y != null) f.group.position.y = y;
  if (z != null) f.group.position.z = z;
  // Rotationen kommen in GRAD über die Bridge -> hier in Radiant wandeln.
  // (Behebt den Alt-Bug, bei dem Grad direkt als Radiant gesetzt wurden.)
  if (rotX != null) f.group.rotation.x = deg2rad(rotX);
  if (rotY != null) f.group.rotation.y = deg2rad(rotY);
  if (rotZ != null) f.group.rotation.z = deg2rad(rotZ);
  if (f.icon) {
    f.icon.position.set(f.group.position.x, 0.05, f.group.position.z);
    if (rotY != null) f.icon.rotation.y = f.group.rotation.y + (f._lastPanRad || 0);  // Top-Down: Yaw + Pan
  }
  requestRender();  // 3c-2: Transform aus dem Python-Properties-Panel
}

export function jsAlignSelected(mode) {
  if (view.selectedFids.length < 2) return;
  const fs = view.selectedFids.map(fid => fixtures[fid]).filter(Boolean);
  if (fs.length < 2) return;
  let val;
  if (mode === 'left') {
    val = Math.min(...fs.map(f => f.group.position.x));
    fs.forEach(f => f.group.position.x = val);
  } else if (mode === 'right') {
    val = Math.max(...fs.map(f => f.group.position.x));
    fs.forEach(f => f.group.position.x = val);
  } else if (mode === 'front') {
    val = Math.max(...fs.map(f => f.group.position.z));
    fs.forEach(f => f.group.position.z = val);
  } else if (mode === 'back') {
    val = Math.min(...fs.map(f => f.group.position.z));
    fs.forEach(f => f.group.position.z = val);
  } else if (mode === 'center_x') {
    val = fs.reduce((s, f) => s + f.group.position.x, 0) / fs.length;
    fs.forEach(f => f.group.position.x = val);
  } else if (mode === 'center_z') {
    val = fs.reduce((s, f) => s + f.group.position.z, 0) / fs.length;
    fs.forEach(f => f.group.position.z = val);
  }
  pushTransformsToPython();
  requestRender();  // 3c-2: Ausrichten veraendert Fixture-Positionen
}

export function jsDistributeSelected(axis) {
  if (view.selectedFids.length < 3) return;
  const fs = view.selectedFids.map(fid => fixtures[fid]).filter(Boolean);
  if (fs.length < 3) return;
  const key = (axis === 'x') ? 'x' : 'z';
  fs.sort((a, b) => a.group.position[key] - b.group.position[key]);
  const min = fs[0].group.position[key];
  const max = fs[fs.length - 1].group.position[key];
  const step = (max - min) / (fs.length - 1);
  fs.forEach((f, i) => f.group.position[key] = min + step * i);
  pushTransformsToPython();
  requestRender();  // 3c-2: Verteilen veraendert Fixture-Positionen
}

export function pushTransformsToPython() {
  for (const fid of view.selectedFids) {
    const f = fixtures[fid];
    if (!f) continue;
    if (f.icon) f.icon.position.set(f.group.position.x, 0.05, f.group.position.z);
    // VIZ-02: Ausrichten/Verteilen positioniert das Geraet FREI um. Eine noch
    // bestehende Andock-Bindung wuerde es beim naechsten Bewegen des
    // Buehnenelements zurueckspringen lassen -> Dock loesen (wie am Drag-Ende).
    if (f.dockedTo) {
      f.dockedTo = null;
      if (bridge && bridge.fixtureDockChanged) {
        try { bridge.fixtureDockChanged(String(fid), ''); } catch (err) {}
      }
    }
    if (bridge && bridge.fixturePositionChanged) {
      try {
        bridge.fixturePositionChanged(String(fid), f.group.position.x, f.group.position.y, f.group.position.z);
      } catch (err) {}
    }
  }
}

// ============================================================================
// Settings
// ============================================================================
export function applySettings(s) {
  if (typeof s.beamOpacity === 'number') settings.beamOpacity = s.beamOpacity;
  if (typeof s.showCones === 'boolean') settings.showCones = s.showCones;
  if (typeof s.showFloorSpots === 'boolean') settings.showFloorSpots = s.showFloorSpots;
  if (typeof s.showFog === 'boolean') {
    settings.showFog = s.showFog;
    if (s.showFog && view.mode === '3D') {
      const bg = scene.background ? scene.background.getHex() : 0x080808;
      scene.fog = new THREE.FogExp2(bg, Math.max(0.005, 0.025 * (1 - settings.brightness)));
    } else {
      scene.fog = null;
    }
  }
  if (typeof s.snapToGrid === 'boolean') settings.snapToGrid = s.snapToGrid;
  if (typeof s.gridStep === 'number') settings.gridStep = s.gridStep;
  if (typeof s.brightness === 'number') applyBrightness(s.brightness);
  if (typeof s.autoBrightness === 'boolean') settings.autoBrightness = s.autoBrightness;
  if (typeof s.dockEnabled === 'boolean') {
    settings.dockEnabled = s.dockEnabled;
    if (!s.dockEnabled) clearDockHighlight();
  }
  // VIZ-13 Schritt 3b-K-2: FPS-Debug-Overlay-Toggle (Einstellungen-Tab).
  // Kein eigener Bridge-Vertrag noetig (Design-Dokument (c) "FPS-Debug-
  // Toggle") - reist additiv im bestehenden settingsChanged-JSON mit.
  if (typeof s.fpsVisible === 'boolean') setFpsVisible(s.fpsVisible);
  for (const fid in fixtures) {
    const f = fixtures[fid];
    if (f.beam) f.beam.visible = settings.showCones && (view.mode === '3D') && f.beam.material.opacity > 0.01;
    if (f.floorSpot) f.floorSpot.visible = settings.showFloorSpots && f.floorSpot.material.opacity > 0.01;
    // VIZ-03: Laser-Faecher analog zu beam/floorSpot neu setzen (z. B. nach
    // showCones-Toggle), nicht erst beim naechsten DMX-Update.
    if (f.laserBeams) for (const bm of f.laserBeams) { if (bm.material) bm.visible = settings.showCones && (view.mode === '3D') && bm.material.opacity > 0.01; }
  }
  requestRender();  // 3c-2 Dirty-Quelle 6 (Settings: Fog/Beam-Sichtbarkeiten)
}

// ============================================================================
// Qt WebChannel
// ============================================================================
export let bridge = null;

export function tryChannel() {
  if (typeof QWebChannel !== 'undefined' && typeof qt !== 'undefined') {
    new QWebChannel(qt.webChannelTransport, function(channel) {
      bridge = channel.objects.bridge;
      if (bridge) {
        if (bridge.fixtureAdded)   bridge.fixtureAdded.connect(j => { addFixture(JSON.parse(j)); });
        if (bridge.fixtureRemoved) bridge.fixtureRemoved.connect(fid => { removeFixture(fid); });
        // VIZ-13 3c-4: Legacy-Einzel-Handler bridge.dmxUpdated ENTFERNT — der
        // Service pusht ausschliesslich als Batch-Array ueber dmxBatch (der Body
        // ruft dasselbe updateFixture pro Element auf).
        if (bridge.dmxBatch)       bridge.dmxBatch.connect(j => {
          const arr = JSON.parse(j);
          for (const d of arr) {
            updateFixture(d.fid, d.r, d.g, d.b, d.intensity, d.pan||128, d.tilt||128, d.heads||null);
          }
        });
        if (bridge.allFixtures)    bridge.allFixtures.connect(j => {
          const list = JSON.parse(j);
          list.forEach(f => addFixture(f));
          // VIZ-12: JETZT sind die Fixture-Objekte gebaut — Service um den
          // vollen DMX-Bestand bitten. Ein zeitgesteuerter Push von Python
          // aus kann VOR diesem Punkt eintreffen und verpufft dann (kein
          // Fixture-Objekt -> updateFixture no-op, Dirty-Cache haelt die
          // Werte trotzdem fuer zugestellt). Ereignisgesteuert statt Timing.
          if (bridge.requestFullResync) {
            try { bridge.requestFullResync(); } catch (e) {}
          }
        });
        if (bridge.settingsChanged) bridge.settingsChanged.connect(j => applySettings(JSON.parse(j)));
        if (bridge.viewModeChanged) bridge.viewModeChanged.connect(name => setViewMode(name));
        if (bridge.editModeChanged) bridge.editModeChanged.connect(name => setEditMode(name));
        if (bridge.stageLoaded)    bridge.stageLoaded.connect(j => loadStageJson(j));
        if (bridge.addStageObject) bridge.addStageObject.connect(t => jsAddStageObject(t));
        if (bridge.removeStageObject) bridge.removeStageObject.connect(id => jsRemoveStageObject(id));
        if (bridge.selectStageObject) bridge.selectStageObject.connect(id => jsSelectStageObject(id));
        if (bridge.applyFixtureTransform) bridge.applyFixtureTransform.connect(j => {
          const d = JSON.parse(j);
          jsApplyFixtureTransform(d.fid, d.x, d.y, d.z, d.rotX, d.rotY, d.rotZ);
        });
        if (bridge.alignSelected)   bridge.alignSelected.connect(m => jsAlignSelected(m));
        if (bridge.distributeSelected) bridge.distributeSelected.connect(a => jsDistributeSelected(a));
        if (bridge.cameraReset)    bridge.cameraReset.connect(() => resetCameraView());
        // VIZ-13 Schritt 3b-K-2: Kamera-Preset-Auswahl aus der Toolbar +
        // gespeicherte-Kameras-Liste (additiv zu cameraReset).
        if (bridge.cameraPreset)  bridge.cameraPreset.connect(name => setCameraPreset(name));
        // Python-Signal heisst namedCamerasChanged (NICHT "setX" — QWebChannel
        // exponiert "set"-praefigierte Signale nicht). Der JS-Handler ist die
        // importierte presets.js-Funktion setNamedCameras (lokal, kein Signal).
        if (bridge.namedCamerasChanged) bridge.namedCamerasChanged.connect(j => {
          try { setNamedCameras(JSON.parse(j)); } catch (e) {}
        });
        if (bridge.brightnessSignal) bridge.brightnessSignal.connect(v => setBrightnessManual(v));
        if (bridge.brightnessAutoSignal) bridge.brightnessAutoSignal.connect(() => resetBrightnessAuto());
        if (bridge.updateStageObject) bridge.updateStageObject.connect(j => {
          try {
            const d = JSON.parse(j);
            updateStageObjectProps(d.id, d);
          } catch (err) { console.log('updateStageObject err:', err); }
        });
        if (bridge.resizeModeSignal) bridge.resizeModeSignal.connect(on => setResizeModeEnabled(on));
        if (bridge.pixelRatioSignal) bridge.pixelRatioSignal.connect(r => {
          // VIZ-12 Schritt 5: expliziter Bildschirmwechsel (Qt screenChanged)
          // -> Renderer-Pixelratio neu setzen, unabhaengig vom 'resize'-Event
          // (das feuert nicht garantiert bei jedem Monitorwechsel).
          renderer.setPixelRatio(Math.min(r || window.devicePixelRatio || 1, 2));
          requestRender();  // 3c-2 Dirty-Quelle 5 (PixelRatio-Wechsel)
        });
        if (bridge.requestFixtures) bridge.requestFixtures();
      }
    });
  } else {
    setTimeout(tryChannel, 200);
  }
}

// getBridge(): schmaler Zugriffspunkt fuer alle Module, die `bridge` per
// Late-Binding brauchen (interaction/pointer.js, interaction/touch.js,
// interaction/tools.js, stage/docking.js, stage/stage_objects.js - siehe
// jeweiliges "Kern-Gotcha"-Kommentar dort). `bridge` ist hier ein
// modul-lokales `let`, das erst beim WebChannel-Connect gesetzt wird -
// getBridge() liest es lazy zum Aufrufzeitpunkt, nicht beim Import.
export function getBridge() { return bridge; }
