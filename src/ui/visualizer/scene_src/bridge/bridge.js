// VIZ-13 Schritt 3a-4: Qt WebChannel - Bridge-Vertrag (ehem.
// stage_scene.html:3317-3513 applySettings/jsAdd.../pushTransformsToPython/
// tryChannel). Reines Verschieben - ALLE 14 Signal-Connects + Slot-Aufrufe
// 1:1 erhalten (Design-Dokument Leitprinzip).
import * as THREE from '../three/three.js';
import { scene, gpuTier, setDeviceRatio } from '../scene/renderer.js';
import { applyBrightness } from '../scene/lights.js';
import { fixtures, settings, stageObjects, view } from '../state.js';
import { addFixture, removeFixture } from '../fixtures/fixtures.js';
import { applyDmx } from './dmx_apply.js';                                // VIZ-71
import { forgetDmx, pruneDmxCache } from '../fixtures/dmx_cache.js';      // VIZ-71
import { resyncBeamVisibility } from '../fixtures/builders.js';
import { setBeamsOff } from '../state.js';   // VIZ-15
import { setViewMode } from '../stage/view_mode.js';
import { setEditMode, setBrightnessManual, resetBrightnessAuto, updateOutlines, jsApplyExternalSelection } from '../interaction/tools.js';
import { setFpsVisible } from '../camera/presets.js';
import {
  loadStageJson, createStageObject, removeStageObject, updateStageObjectProps,
  setResizeModeEnabled, isUserRemoved,
} from '../stage/stage_objects.js';
import { hideTooltip } from '../interaction/pointer.js';
import { resetCameraView } from '../camera/cameras.js';
import { setCameraPreset, setNamedCameras } from '../camera/presets.js';
import { deg2rad, rad2deg } from '../scene/renderer.js';
import { clearDockHighlight } from '../stage/docking.js';
import { requestRender } from '../scene/render_loop.js';  // VIZ-13 3c-2
import { syncRoomShell } from '../scene/room_shell.js';
import { setPlaceableCount } from '../interaction/place_ghost.js';  // VIZ-14

// ============================================================================
// Python bridge actions used externally
// ============================================================================
export function jsAddStageObject(type) {
  return createStageObject(type, null, null, null, 0, null, null);
}

// QWebChannel kann denselben Direkt- und Poll-Event zustellen. Durch die
// Python-ID bleibt das inkrementelle Hinzufügen deshalb idempotent.
export function jsAddStageObjectData(json) {
  try {
    const d = typeof json === 'string' ? JSON.parse(json) : json;
    if (!d || !d.type) return null;
    // A3D-12/A3D-30: eine automatische Wiederherstellung (`reassert`) darf ein
    // vom Nutzer geloeschtes Element NICHT reanimieren. Der Repair-Loop in
    // loadStageJson respektierte den Tombstone schon immer, dieser
    // Inkremental-Kanal nicht — ein verspaetet zugestelltes addStageData baute
    // das Objekt neu auf UND hob per createStageObject seinen Tombstone auf.
    //
    // Nur `reassert` wird so behandelt: ein echtes Undo/Redo-Re-Add ist eine
    // bewusste Nutzergeste und MUSS den Tombstone aufheben duerfen.
    if (d.reassert && d.id && isUserRemoved(d.id)) return null;
    if (d.id && stageObjects[d.id]) {
      updateStageObjectProps(d.id, d);
      return d.id;
    }
    return createStageObject(
      d.type, d.position || null, d.size || null, d.color || null,
      d.rotation || 0, d.id || null, d.name || null,
    );
  } catch (e) {
    return null;
  }
}

export function jsRemoveStageObject(id) {
  removeStageObject(id);
}

export function jsSelectStageObject(id) {
  view.selectedStageId = id || null;
  updateOutlines();
}

export function jsApplyFixtureTransform(fid, x, y, z, rotX, rotY, rotZ, dock) {
  const f = fixtures[fid];
  if (!f) return;
  // A3D-10: `dock` reist optional in DERSELBEN Payload mit, damit Undo/Redo einer
  // Gestik den Andock-Zustand mitfuehrt. Fehlt das Feld (Alt-Payload), bleibt
  // `dockedTo` unangetastet — sonst wuerde jeder Alt-Aufrufer still entdocken.
  if (dock !== undefined && dock !== null) f.dockedTo = dock || null;
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

// VIZ-14 (Plan §3 "Arrangement-Tool"): die Auswahl in eine REIHE, ein RASTER
// oder einen KREIS legen — mit festem Abstand statt per Hand geschoben.
//
// Abgrenzung zu den beiden Nachbarn: `jsAlignSelected` legt alle auf EINE Linie
// (gleicher x bzw. z), `jsDistributeSelected` verteilt sie gleichmaessig
// ZWISCHEN den vorhandenen Aussenpunkten — beide aendern nur eine Achse und
// brauchen eine schon halbwegs passende Ausgangslage. Das Anordnen baut die
// Formation dagegen NEU auf, um den Schwerpunkt der Auswahl herum.
//
// ★ Sortiert wird nach der aktuellen Position, nicht nach fid: der Nutzer sieht
// links-nach-rechts, was er links-nach-rechts hingestellt hat. Nach fid zu
// ordnen wuerde die Reihenfolge beim Anordnen still umwerfen (und fids haengen
// an der Patch-Reihenfolge, nicht am Rig).
export function jsArrangeSelected(spec) {
  let cfg = spec;
  if (typeof cfg === 'string') {
    try { cfg = JSON.parse(cfg); } catch (e) { return; }
  }
  if (!cfg) return;
  const fs = view.selectedFids.map(fid => fixtures[fid]).filter(Boolean);
  if (fs.length < 2) return;              // eine Formation aus einem Geraet gibt es nicht

  const shape = String(cfg.shape || 'row');
  const gap = Math.max(0.05, Number(cfg.spacing) || 1.0);
  const achse = (cfg.axis === 'z') ? 'z' : 'x';
  // Schwerpunkt der aktuellen Auswahl = Anker. So bleibt die Formation dort,
  // wo der Nutzer sie hingestellt hat, statt in den Weltnullpunkt zu springen.
  const cx = fs.reduce((s, f) => s + f.group.position.x, 0) / fs.length;
  const cz = fs.reduce((s, f) => s + f.group.position.z, 0) / fs.length;
  const quer = (achse === 'x') ? 'z' : 'x';
  fs.sort((a, b) => (a.group.position[achse] - b.group.position[achse])
                 || (a.group.position[quer] - b.group.position[quer]));

  if (shape === 'row') {
    const start = -((fs.length - 1) * gap) / 2;
    fs.forEach((f, i) => {
      if (achse === 'x') { f.group.position.x = cx + start + i * gap; f.group.position.z = cz; }
      else               { f.group.position.z = cz + start + i * gap; f.group.position.x = cx; }
    });
  } else if (shape === 'grid') {
    const cols = Math.max(1, Math.floor(Number(cfg.cols) || Math.ceil(Math.sqrt(fs.length))));
    const rows = Math.ceil(fs.length / cols);
    const x0 = -((cols - 1) * gap) / 2;
    const z0 = -((rows - 1) * gap) / 2;
    fs.forEach((f, i) => {
      const r = Math.floor(i / cols), c = i % cols;
      f.group.position.x = cx + x0 + c * gap;
      f.group.position.z = cz + z0 + r * gap;
    });
  } else if (shape === 'circle') {
    // Radius: ausdruecklich gesetzt, sonst aus dem Abstand abgeleitet, damit
    // benachbarte Geraete wirklich `spacing` auseinander stehen (Umfang/Anzahl).
    const r = (Number(cfg.radius) > 0)
      ? Number(cfg.radius)
      : Math.max(gap, (gap * fs.length) / (2 * Math.PI));
    fs.forEach((f, i) => {
      const a = (2 * Math.PI * i) / fs.length;
      f.group.position.x = cx + Math.cos(a) * r;
      f.group.position.z = cz + Math.sin(a) * r;
    });
  } else {
    return;                                // unbekannte Form -> nichts anfassen
  }
  pushTransformsToPython();
  requestRender();  // 3c-2: Anordnen veraendert Fixture-Positionen
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
  // VIZ-LABELS: Fixture-Namens-Sprites global ein-/ausblenden. Reine Flag-
  // Mutation — die tatsaechliche Sichtbarkeit setzt der Per-Frame-Gate
  // (updateLabelZoomVisibility, app.js) im durch requestRender() unten
  // ohnehin ausgeloesten Frame. Additiv im settingsChanged-JSON (wie fpsVisible).
  if (typeof s.showLabels === 'boolean') settings.showLabels = s.showLabels;
  // VIZ-14: Raum-Huelle. syncRoomShell baut sie AUS DEM AKTUELLEN INHALT neu
  // auf — eine feste Groesse wuerde bei grossen Rigs mitten durchschneiden.
  if (typeof s.showRoom === 'boolean') { settings.showRoom = s.showRoom; syncRoomShell(); }
  for (const fid in fixtures) {
    const f = fixtures[fid];
    // A3D-05: Kegel-Sichtbarkeit (Einzelkopf + Laser-Faecher + Multi-Head-Pro-Kopf)
    // nach showCones-Toggle sofort neu setzen — vorher blieben die PAR-Bar-/Mover-Bar-/
    // Spider-Pro-Kopf-Kegel bis zum naechsten DMX-Update der Fixture stale.
    resyncBeamVisibility(f);
    if (f.floorSpot) f.floorSpot.visible = settings.showFloorSpots && f.floorSpot.material.opacity > 0.01;
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
        if (bridge.fixtureRemoved) bridge.fixtureRemoved.connect(fid => { removeFixture(fid); forgetDmx(fid); });
        // VIZ-71: KEIN dmxBatch-Handler mehr. Die DMX-Werte schiebt Python per
        // runJavaScript direkt an window.__lightos.applyDmx (visualizer/
        // dmx_push.py); der Rueckfall laeuft ueber den Poll unten. Ein hier
        // verbundenes Signal liesse den QWebChannel-Publisher jedes Senden
        // serialisieren — Arbeit fuer einen Weg, der nach dem Laden ohnehin
        // nicht zustellt (s. Poll-Kommentar).
        if (bridge.allFixtures)    bridge.allFixtures.connect(j => {
          const list = JSON.parse(j);
          pruneDmxCache(list.map(f => f.fid));
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
        if (bridge.addStageObjectData) bridge.addStageObjectData.connect(j => jsAddStageObjectData(j));
        if (bridge.removeStageObject) bridge.removeStageObject.connect(id => jsRemoveStageObject(id));
        if (bridge.selectStageObject) bridge.selectStageObject.connect(id => jsSelectStageObject(id));
        if (bridge.applyFixtureTransform) bridge.applyFixtureTransform.connect(j => {
          const d = JSON.parse(j);
          jsApplyFixtureTransform(d.fid, d.x, d.y, d.z, d.rotX, d.rotY, d.rotZ, d.dock);
        });
        if (bridge.alignSelected)   bridge.alignSelected.connect(m => jsAlignSelected(m));
        if (bridge.distributeSelected) bridge.distributeSelected.connect(a => jsDistributeSelected(a));
        if (bridge.arrangeSelected) bridge.arrangeSelected.connect(j => jsArrangeSelected(j));
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
          // (das feuert nicht garantiert bei jedem Monitorwechsel). VIZ-71:
          // ueber die EINE Quelle in renderer.js (Deckel der Stufe +
          // dynamische Aufloesung). Nach dem Laden kommt das Signal nicht an —
          // der Poll spiegelt es als Zustand 'pixelRatio' (unten).
          setDeviceRatio(r);
          requestRender();  // 3c-2 Dirty-Quelle 5 (PixelRatio-Wechsel)
        });
        // VIZ-15: aktive Qualitaetsstufe (Probe- oder ?gputier-Override-
        // Ergebnis) an Python melden — Slot-Aufrufe kommen zuverlaessig an.
        if (bridge.reportGpuTier) { try { bridge.reportGpuTier(gpuTier); } catch (e) {} }
        if (bridge.requestFixtures) bridge.requestFixtures();
        // VIZ-13 3c-2-Fix (2026-07-07, LIVE verifiziert): PULL statt PUSH.
        // QtWebEngine stellt Python->JS-SIGNALE (Push) an die eingebettete
        // Post-Load-Seite NICHT zu (auch fokussiert nicht) — SLOT-RUECKGABEN
        // (Callback-Antworten auf JS-initiierte Calls) schon. Ohne das war
        // 3D-Bearbeiten/Kamera/DMX tot (nur der Connect-Burst lud die Fixtures).
        // Darum pollt die Seite periodisch pollControl() MIT Callback und wendet
        // den zurueckgegebenen Steuer-Zustand + Einmal-Events an.
        if (bridge.pollControl) {
          let _pEM = null, _pVM = null, _pSet = null, _pStage = null, _pFix = null, _pSel = null;
          let _pPlace = null;   // VIZ-14: Zahl offener Platzierungen
          let _pBeamsOff = null;   // VIZ-15 (JSON-Signatur, s. Poll unten)
          let _pPR = null;         // VIZ-71: Pixeldichte des Bildschirms
          // VIZ-71 (S5): zuletzt gesehene Revisionen je Zustands-Schluessel.
          // Python antwortet nur mit Geaendertem (pollControlRev) — vorher ging
          // die volle Geraeteliste und die Buehne bei JEDEM Poll mit.
          const _revs = {};
          const _versuche = {};        // Review B2: Fehlschlaege je Schluessel
          const _MAX_VERSUCHE = 3;
          const _abfragen = (cb) => (bridge.pollControlRev
            ? bridge.pollControlRev(JSON.stringify(_revs), cb)
            : bridge.pollControl(cb));
          setInterval(function(){
            try {
              _abfragen(function(js){
                try {
                  const s = JSON.parse(js);
                  // Review B2: Revisionen erst NACH dem Anwenden uebernehmen und
                  // jeden Zustands-Block einzeln absichern. Vorher wurde _rev vor
                  // allen Handlern quittiert, und ein Wurf (z. B. defekte Buehne)
                  // liess alle spaeteren Schluessel derselben Antwort dauerhaft
                  // fallen — Python schickt sie erst bei geaendertem Wert wieder.
                  // Ein gescheiterter Schluessel bleibt unquittiert (kommt beim
                  // naechsten Poll erneut), nach _MAX_VERSUCHE Fehlschlaegen wird
                  // er aufgegeben (kein Dauer-Neubau 8x pro Sekunde).
                  const _fehl = {};
                  const _block = (key, fn) => {
                    try { fn(); }
                    catch (eB) {
                      _fehl[key] = true;
                      console.log('poll: Zustand ' + key + ' nicht angewandt', eB);
                    }
                  };
                  // Idempotente Zustaende: nur bei Aenderung anwenden. Der
                  // Vergleichswert (_pX) wird erst nach Erfolg gesetzt.
                  if (s.editMode !== undefined && s.editMode !== _pEM) {
                    _block('editMode', () => { setEditMode(s.editMode); _pEM = s.editMode; });
                  }
                  // VIZ-14: wie viele Geraete warten auf einen Platz? Steuert
                  // den Platzier-Geist (0 = kein Geist).
                  if (s.placeable !== undefined && s.placeable !== _pPlace) {
                    _block('placeable', () => { setPlaceableCount(s.placeable); _pPlace = s.placeable; });
                  }
                  // VIZ-15: welche Geraete haben ihren Lichtkegel ausgeblendet?
                  // Als JSON-String vergleichen, nicht als Array — ein Array ist
                  // bei jedem Poll ein NEUES Objekt und waere damit immer
                  // "geaendert" (der Rebuild liefe dann 8x pro Sekunde).
                  if (s.beamsOff !== undefined) {
                    const sig = JSON.stringify(s.beamsOff);
                    if (sig !== _pBeamsOff) {
                      _block('beamsOff', () => {
                        setBeamsOff(s.beamsOff);
                        for (const k in fixtures) resyncBeamVisibility(fixtures[k]);
                        requestRender();
                        _pBeamsOff = sig;
                      });
                    }
                  }
                  if (s.viewMode !== undefined && s.viewMode !== _pVM) {
                    _block('viewMode', () => { setViewMode(s.viewMode); _pVM = s.viewMode; });
                  }
                  // VIZ-71 (N3): Bildschirmwechsel kam bisher nur als Push-Signal —
                  // nach dem Laden also nie. Jetzt auch als Poll-Zustand.
                  if (typeof s.pixelRatio === 'number' && s.pixelRatio !== _pPR) {
                    _block('pixelRatio', () => { setDeviceRatio(s.pixelRatio); _pPR = s.pixelRatio; });
                  }
                  if (s.settings && s.settings !== _pSet) {
                    _block('settings', () => { applySettings(JSON.parse(s.settings)); _pSet = s.settings; });
                  }
                  if (s.stage && s.stage !== _pStage) {
                    _block('stage', () => { loadStageJson(s.stage); _pStage = s.stage; });
                  }
                  // Voll-Fixture-Rebuild (allFixtures): nur bei geaenderter Liste
                  // anwenden. addFixture ist idempotent (ersetzt vorhandene fid).
                  if (s.fixtures && s.fixtures !== _pFix) {
                    _block('fixtures', () => {
                      const list = JSON.parse(s.fixtures);
                      // VIZ-71: Reste alter Shows aus dem DMX-Cache raeumen.
                      // Review B3: fids, die DIESELBE Antwort per fixtureAdded
                      // baut, bleiben drin — sonst wirft eine noch alte Liste
                      // den DMX-Stand eines frisch platzierten Geraets weg, und
                      // es bliebe dunkel, bis sich sein DMX aendert.
                      const behalten = list.map(f => f.fid);
                      for (const ev of (s.events || [])) {
                        if (ev && ev.t === 'fixtureAdded') {
                          try { behalten.push(JSON.parse(ev.j).fid); } catch (eJ) {}
                        }
                      }
                      pruneDmxCache(behalten);
                      // Ein stolperndes Geraet darf die folgenden nicht kosten;
                      // es wird geloggt, nicht wiederholt (sonst Dauer-Neubau).
                      for (const f of list) {
                        try { addFixture(f); }
                        catch (eF) { console.log('poll: Geraet nicht gebaut', f && f.fid, eF); }
                      }
                      _pFix = s.fixtures;
                    });
                  }
                  // VIZ-14 (Slice 1b): globale/Programmer-Auswahl -> Outlines im
                  // 3D. Idempotent (nur bei geaenderter Liste), OHNE Echo zurueck
                  // (jsApplyExternalSelection ruft updateOutlines(false)).
                  if (s.selection !== undefined && s.selection !== _pSel) {
                    _block('selection', () => { jsApplyExternalSelection(s.selection); _pSel = s.selection; });
                  }
                  if (s._rev) {
                    for (const k in s._rev) {
                      if (_fehl[k]) {
                        const n = (_versuche[k] || 0) + 1;
                        _versuche[k] = n;
                        if (n < _MAX_VERSUCHE) continue;      // naechster Poll: erneut
                      }
                      delete _versuche[k];
                      _revs[k] = s._rev[k];
                    }
                  }
                  if (s.dmx) {
                    // A3D-04: eigenes try/catch. Ein Wurf hier (defektes JSON, ein
                    // Fixture-Handler, der stolpert) landete sonst im aeusseren catch
                    // und uebersprunge den DANACH folgenden events-Block - waehrend
                    // Python die Event-Queue beim Ausliefern schon geleert hat. Ein
                    // DMX-Problem darf keine Kamera-/Transform-/Stage-Events fressen.
                    // VIZ-71: derselbe Weg wie der Push (Sequenznummern je
                    // Eintrag in s.dmxSeq; unbekannte fids landen im Cache).
                    try {
                      applyDmx(JSON.parse(s.dmx), s.dmxSeq);
                    } catch (e) { console.log('poll dmx: Batch uebersprungen', e); }
                  }
                  // Einmal-Events: genau einmal ausfuehren (Python leert die Queue).
                  if (s.events) {
                    for (const ev of s.events) {
                      try {
                        if (ev.t === 'cameraReset') resetCameraView();
                        else if (ev.t === 'brightness') setBrightnessManual(ev.v);
                        else if (ev.t === 'brightnessAuto') resetBrightnessAuto();
                        else if (ev.t === 'transform') { const d = JSON.parse(ev.j); jsApplyFixtureTransform(d.fid, d.x, d.y, d.z, d.rotX, d.rotY, d.rotZ, d.dock); }
                        else if (ev.t === 'addStage') jsAddStageObject(ev.stype);
                        else if (ev.t === 'addStageData') jsAddStageObjectData(ev.j);
                        else if (ev.t === 'removeStage') jsRemoveStageObject(ev.id);
                        else if (ev.t === 'selectStage') jsSelectStageObject(ev.id);
                        else if (ev.t === 'updateStage') { const d = JSON.parse(ev.j); updateStageObjectProps(d.id, d); }
                        else if (ev.t === 'align') jsAlignSelected(ev.mode);
                        else if (ev.t === 'distribute') jsDistributeSelected(ev.axis);
                        else if (ev.t === 'arrange') jsArrangeSelected(ev.j);
                        else if (ev.t === 'resizeMode') setResizeModeEnabled(ev.on);
                        else if (ev.t === 'cameraPreset') setCameraPreset(ev.name);
                        else if (ev.t === 'namedCameras') setNamedCameras(JSON.parse(ev.j));
                        else if (ev.t === 'fixtureAdded') { try { addFixture(JSON.parse(ev.j)); } catch (eA) {} }
                        else if (ev.t === 'fixtureRemoved') { removeFixture(ev.fid); forgetDmx(ev.fid); }
                      } catch (e2) {}
                    }
                  }
                } catch (e) {}
              });
            } catch (e) {}
          }, 130);
        }
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
