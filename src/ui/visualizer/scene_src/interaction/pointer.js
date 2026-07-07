// VIZ-13 Schritt 3a-4: Pointer-State-Machine (ehem. stage_scene.html:2338-
// 3057 handlePointerDown/Move/Up + Maus-Listener + Wheel + hideTooltip +
// _placeFixtureAtMouse + contextmenu). Reines Verschieben.
import * as THREE from '../three/three.js';
import { renderer } from '../scene/renderer.js';
import { rad2deg, deg2rad } from '../scene/renderer.js';
import { orthoCam, orthoState, updateCamera } from '../camera/cameras.js';
import { fixtures, stageObjects, settings, view } from '../state.js';
import {
  raycaster, mouse, setMouseFromCoords, setMouseFromEvent, intersectGround,
  pickFixture, pickStageObject, snap,
} from './picking.js';
import {
  applyDockHighlight, clearDockHighlight, showDockBadge, hideDockBadge,
  _dockNameFor, findDockTarget, moveDockedFixtures, _reportDockedFixturePositions,
} from '../stage/docking.js';
import {
  updateOutlines, showEditReadout, hideEditReadout, updateMeasureReadout,
  _traceSpec, setLastTraceTarget, traceShape, traceRadius, updateFABs,
} from './tools.js';
import {
  pickGizmoHandle, axisParamUnderPointer, rotationAngleUnderPointer, GIZMO_AXES,
} from './gizmo.js';
import {
  pickResizeHandle, updateResizeHandles, notifyStageListChanged,
  updateStageObjectProps, resizeHandles,
} from '../stage/stage_objects.js';
import { floorMesh } from '../scene/grid_floor.js';
import { resizeOrtho } from '../camera/cameras.js';
import { requestRender } from '../scene/render_loop.js';  // VIZ-13 3c-2

export let isLeftDragging = false;
export let dragMode = 'none';  // 'rotate' | 'pan' | 'fixtureDrag' | 'stageDrag' | 'marquee' | 'none'
let lastMouseX = 0, lastMouseY = 0;
let downMouseX = 0, downMouseY = 0;
let mouseMovedDuringClick = false;

let dragStartPositions = {}; // fid -> {x, z}
let dragStartStagePos = null; // for stage drag
let dragGroundOffset = { x: 0, y: 0, z: 0, userData: undefined };
let dragResizeCorner = null;     // 'nw' | 'ne' | 'sw' | 'se'
let dragResizeStart = null;      // {startCenterX,Z, startSizeX,Z, fixedCornerX,Z}
let _fabLastPlaceCoords = null;
// VIZ-13 3b-G: aktive Gizmo-Gestik. { mode:'translate'|'rotate', axis, axisVec,
// pivot(Vector3), startParam | startAngle }. dragStartPositions[fid] traegt bei
// Gizmo-Drags zusaetzlich .quat (Start-Quaternion) fuer die Welt-Achsen-Rotation.
let dragGizmo = null;
const _gizmoDeltaQuat = new THREE.Quaternion();
const _gizmoPivot = new THREE.Vector3();
const _gizmoOffset = new THREE.Vector3();

export function getFabLastPlaceCoords() { return _fabLastPlaceCoords; }

// interaction/touch.js braucht Lese- UND Schreibzugriff auf isLeftDragging/
// dragMode/lastMouseX/lastMouseY (Original: gemeinsamer Scope, die Touch-
// Handler setzen sie direkt). Re-exportierte `let`s sind fuer Importeure
// read-only (Design-Dokument Risiko 1) - deshalb Getter/Setter-Wrapper wie
// state.js#view, hier lokal fuer den Pointer-Modul-State.
export const pointerState = {
  get isLeftDragging() { return isLeftDragging; },
  set isLeftDragging(v) { isLeftDragging = v; },
  get dragMode() { return dragMode; },
  set dragMode(v) { dragMode = v; },
  get lastMouseX() { return lastMouseX; },
  set lastMouseX(v) { lastMouseX = v; },
  get lastMouseY() { return lastMouseY; },
  set lastMouseY(v) { lastMouseY = v; },
};

export function _placeFixtureAtMouse() {
  raycaster.setFromCamera(mouse, view.activeCam);
  const target = new THREE.Vector3();
  raycaster.ray.intersectPlane(new THREE.Plane(new THREE.Vector3(0,1,0), -0.4), target);
  const bridge = bridgeRef.get();
  if (bridge && target && bridge.placeFixture) {
    const px = snap(target.x), pz = snap(target.z);
    _fabLastPlaceCoords = { x: target.x, z: target.z };
    let y = 6.5, dock = '';
    if (settings.dockEnabled) {
      const dt = findDockTarget(px, pz);
      if (dt) { y = dt.y; dock = dt.stageId; }
    }
    bridge.placeFixture(JSON.stringify({ x: px, y: y, z: pz, dock: dock }));
  }
}

renderer.domElement.addEventListener('contextmenu', function(e) {
  e.preventDefault();
  setMouseFromEvent(e);
  _placeFixtureAtMouse();
}, false);

// Shared pointer logic (called by both mouse and touch handlers)
export function handlePointerDown(clientX, clientY, shiftKey) {
  setMouseFromCoords(clientX, clientY);
  isLeftDragging = true;
  downMouseX = clientX; downMouseY = clientY;
  lastMouseX = clientX; lastMouseY = clientY;
  mouseMovedDuringClick = false;

  if (view.editMode === 'edit') {
    // VIZ-13 3b-G: Gizmo-Handles zuerst (schlagen Fixture-Pick/Marquee — wie das
    // Stage-Resize-Handle im Stage-Modus). Nur wenn das Gizmo sichtbar ist, d.h.
    // im 3D-Bau-Modus mit Auswahl. Startet die Gizmo-Gestik; Kamera bleibt gesperrt
    // (eigener dragMode, keine 'rotate'/'pan'-Zweige).
    const ghandle = pickGizmoHandle();
    if (ghandle) {
      const axisVec = GIZMO_AXES[ghandle.axis];
      dragStartPositions = {};
      _gizmoPivot.set(0, 0, 0);
      let n = 0;
      for (const sf of view.selectedFids) {
        const f = fixtures[sf];
        if (f) {
          const g = f.group;
          dragStartPositions[sf] = {
            x: g.position.x, y: g.position.y, z: g.position.z,
            rotXDeg: rad2deg(g.rotation.x), rotYDeg: rad2deg(g.rotation.y),
            quat: g.quaternion.clone(),
          };
          _gizmoPivot.add(g.position); n++;
        }
      }
      if (n) _gizmoPivot.divideScalar(n);
      dragGizmo = { mode: ghandle.mode, axis: ghandle.axis, axisVec, pivot: _gizmoPivot.clone() };
      if (ghandle.mode === 'translate') {
        dragGizmo.startParam = axisParamUnderPointer(dragGizmo.pivot, axisVec);
      } else {
        dragGizmo.startAngle = rotationAngleUnderPointer(dragGizmo.pivot, ghandle.axis);
      }
      dragMode = 'gizmoDrag';
      return;
    }
    if (view.editTool === 'aim' || view.editTool === 'trace') {
      // 1-Finger-Drag = Kamera drehen/schwenken; ein Tipp (ohne Bewegung) zielt
      // bzw. startet das Nachfahren (in handlePointerUp). Kein Fixture-Drag/Marquee.
      dragMode = (view.mode === '3D') ? 'rotate' : 'pan';
      return;
    }
    const fid = pickFixture();
    if (fid != null) {
      const additive = shiftKey;
      if (!additive && !view.selectedFids.includes(fid)) {
        view.selectedFids = [fid];
      } else if (additive) {
        if (!view.selectedFids.includes(fid)) view.selectedFids.push(fid);
      }
      dragStartPositions = {};
      for (const sf of view.selectedFids) {
        if (fixtures[sf]) {
          const g = fixtures[sf].group;
          dragStartPositions[sf] = {
            x: g.position.x,
            y: g.position.y,
            z: g.position.z,
            rotXDeg: rad2deg(g.rotation.x),
            rotYDeg: rad2deg(g.rotation.y),
          };
        }
      }
      const groundHit = intersectGround();
      const refF = fixtures[fid];
      if (groundHit && refF) {
        dragGroundOffset.x = groundHit.x - refF.group.position.x;
        dragGroundOffset.y = 0;
        dragGroundOffset.z = groundHit.z - refF.group.position.z;
        dragGroundOffset.userData = { refFid: fid };
      }
      dragMode = 'fixtureDrag';
      updateOutlines();
      return;
    } else {
      // Marquee-Selektion (nur mit Maus; Touch springt direkt zu Kamera-Pan)
      dragMode = 'marquee';
      const m = document.getElementById('marquee');
      m.style.display = 'block';
      m.style.left = clientX + 'px';
      m.style.top = clientY + 'px';
      m.style.width = '0px';
      m.style.height = '0px';
      if (!shiftKey) { view.selectedFids = []; updateOutlines(); }
      return;
    }
  }

  if (view.editMode === 'stage') {
    if (view.selectedStageId && resizeHandles.length > 0) {
      const handle = pickResizeHandle();
      if (handle) {
        const so = stageObjects[view.selectedStageId];
        if (so) {
          dragResizeCorner = handle.userData.corner;
          const halfX = so.data.size.x / 2;
          const halfZ = so.data.size.z / 2;
          const cx = so.mesh.position.x;
          const cz = so.mesh.position.z;
          let fixedX, fixedZ;
          if (dragResizeCorner === 'nw') { fixedX = cx + halfX; fixedZ = cz + halfZ; }
          else if (dragResizeCorner === 'ne') { fixedX = cx - halfX; fixedZ = cz + halfZ; }
          else if (dragResizeCorner === 'sw') { fixedX = cx + halfX; fixedZ = cz - halfZ; }
          else                                { fixedX = cx - halfX; fixedZ = cz - halfZ; }
          dragResizeStart = {
            fixedX, fixedZ,
            startSizeX: so.data.size.x,
            startSizeZ: so.data.size.z,
          };
          dragMode = 'stageResize';
          return;
        }
      }
    }
    const sid = pickStageObject();
    if (sid != null) {
      view.selectedStageId = sid;
      const so = stageObjects[sid];
      const groundHit = intersectGround();
      if (groundHit) {
        dragStartStagePos = {
          startX: so.mesh.position.x,
          startZ: so.mesh.position.z,
          offsetX: groundHit.x - so.mesh.position.x,
          offsetZ: groundHit.z - so.mesh.position.z,
        };
      }
      dragMode = 'stageDrag';
      updateOutlines();
      return;
    } else {
      view.selectedStageId = null;
      updateOutlines();
    }
  }

  if (view.mode === '3D') {
    dragMode = 'rotate';
  } else {
    dragMode = 'pan';
  }
}

export function handlePointerMove(clientX, clientY, ctrlKey) {
  if (Math.abs(clientX - downMouseX) > 3 || Math.abs(clientY - downMouseY) > 3) {
    mouseMovedDuringClick = true;
  }
  if (view.mode === '2D') {
    setMouseFromCoords(clientX, clientY);
    const gh = intersectGround();
    if (gh) {
      document.getElementById('ruler-info').textContent =
        'X: ' + gh.x.toFixed(2) + ' m | Z: ' + gh.z.toFixed(2) + ' m | Grid: ' + (settings.snapToGrid ? 'ON' : 'OFF');
    }
  }
  if (!isLeftDragging) return;
  setMouseFromCoords(clientX, clientY);
  const dx = clientX - lastMouseX;
  const dy = clientY - lastMouseY;

  if (dragMode === 'rotate') {
    view.theta -= dx * 0.008;
    view.phi = Math.max(0.2, Math.min(Math.PI * 0.49, view.phi + dy * 0.008));
    updateCamera();
  } else if (dragMode === 'pan') {
    const a = window.innerWidth / window.innerHeight;
    const wPerPxX = (2 * orthoState.size * a) / window.innerWidth;
    const wPerPxZ = (2 * orthoState.size) / window.innerHeight;
    orthoCam.position.x -= dx * wPerPxX;
    orthoCam.position.z -= dy * wPerPxZ;
  } else if (dragMode === 'fixtureDrag') {
    // Fixture-Koerper ziehen = XZ-Verschieben am Boden (via Raycast -> schon
    // zoom-korrekt). Y/Rotation laufen ueber das Gizmo (3b-G), nicht mehr ueber
    // eigene Werkzeuge/Pixel-Faktoren.
    const gh = intersectGround();
    if (gh && dragGroundOffset.userData) {
      const refFid = dragGroundOffset.userData.refFid;
      const newX = gh.x - dragGroundOffset.x;
      const newZ = gh.z - dragGroundOffset.z;
      const refStart = dragStartPositions[refFid];
      if (refStart) {
        const dxw = snap(newX) - refStart.x;
        const dzw = snap(newZ) - refStart.z;
        let refDock = null;
        for (const fid of view.selectedFids) {
          const start = dragStartPositions[fid];
          const f = fixtures[fid];
          if (start && f) {
            f.group.position.x = start.x + dxw;
            f.group.position.z = start.z + dzw;
            if (settings.dockEnabled) {
              const dt = findDockTarget(f.group.position.x, f.group.position.z);
              f._pendingDock = dt ? dt.stageId : null;
              if (dt) f.group.position.y = dt.y;
              if (Number(fid) === Number(refFid)) refDock = dt;
            }
            if (f.icon) f.icon.position.set(f.group.position.x, 0.05, f.group.position.z);
          }
        }
        if (settings.dockEnabled) {
          if (refDock) {
            applyDockHighlight(refDock.stageId);
            showDockBadge((refDock.kind === 'hang' ? 'haengt an ' : 'steht auf ') + _dockNameFor(refDock.stageId));
          } else {
            clearDockHighlight();
            hideDockBadge();
          }
        }
      }
    }
  } else if (dragMode === 'gizmoDrag' && dragGizmo) {
    // VIZ-13 3b-G: Gizmo-Gestik. Strukturell zoom-korrekt (Welt-Delta aus dem
    // Pointer-Strahl, KEINE Pixel-Faktoren). Snap an/aus ueber snapToGrid + Strg
    // (Strg = frei, "Snap-Escape"). KEIN Bridge-Call — Commit erst am Drag-Ende.
    const snapActive = settings.snapToGrid && !ctrlKey;
    if (dragGizmo.mode === 'translate') {
      const cur = axisParamUnderPointer(dragGizmo.pivot, dragGizmo.axisVec);
      let delta = cur - dragGizmo.startParam;
      if (snapActive) delta = Math.round(delta / settings.gridStep) * settings.gridStep;
      const ax = dragGizmo.axis;
      const isVertical = (ax === 'y');
      let refDock = null;
      for (const fid of view.selectedFids) {
        const start = dragStartPositions[fid];
        const f = fixtures[fid];
        if (!start || !f) continue;
        f.group.position.x = start.x + (ax === 'x' ? delta : 0);
        f.group.position.y = start.y + (ax === 'y' ? delta : 0);
        f.group.position.z = start.z + (ax === 'z' ? delta : 0);
        if (isVertical) {
          // Explizite Hoehe -> Andocken loesen (wie das alte move_y).
          f._pendingDock = null;
          f.group.position.y = Math.max(0, Math.min(30, f.group.position.y));
        } else if (settings.dockEnabled) {
          const dt = findDockTarget(f.group.position.x, f.group.position.z);
          f._pendingDock = dt ? dt.stageId : null;
          if (dt) f.group.position.y = dt.y;
          if (!refDock && dt) refDock = dt;
        }
        if (f.icon) f.icon.position.set(f.group.position.x, 0.05, f.group.position.z);
      }
      if (!isVertical && settings.dockEnabled) {
        if (refDock) {
          applyDockHighlight(refDock.stageId);
          showDockBadge((refDock.kind === 'hang' ? 'haengt an ' : 'steht auf ') + _dockNameFor(refDock.stageId));
        } else { clearDockHighlight(); hideDockBadge(); }
      }
      showEditReadout(ax.toUpperCase() + ': ' + (delta >= 0 ? '+' : '') + delta.toFixed(2) + ' m');
    } else {
      // Rotation UM die Welt-Achse a: delta-Quaternion mit dem Start-Quaternion
      // je Fixture komponieren (f.group.rotation folgt automatisch -> die
      // Gestik-Ende-Payload liest korrekte rx/ry/rz in Grad).
      const cur = rotationAngleUnderPointer(dragGizmo.pivot, dragGizmo.axis);
      if (cur != null) {
        // Kanten-Guard: war der Ring beim Pointer-Down exakt kantenparallel,
        // blieb startAngle null -> sonst 'cur - null' = grosser Fehlsprung.
        if (dragGizmo.startAngle == null) dragGizmo.startAngle = cur;
        let delta = cur - dragGizmo.startAngle;
        if (snapActive) { const step = deg2rad(15); delta = Math.round(delta / step) * step; }
        _gizmoDeltaQuat.setFromAxisAngle(dragGizmo.axisVec, delta);
        for (const fid of view.selectedFids) {
          const start = dragStartPositions[fid];
          const f = fixtures[fid];
          if (!start || !f || !start.quat) continue;
          f.group.quaternion.multiplyQuaternions(_gizmoDeltaQuat, start.quat);
          // Multi-Select: die Position um den GEMEINSAMEN Pivot mitdrehen (die
          // Gruppe orbitet ihren Schwerpunkt — wie grandMA3/Blender-World-Pivot;
          // der Ring sitzt am Schwerpunkt und hielt das bisher nicht ein). Einzel-
          // Fixture: start == pivot -> Offset 0 -> keine Positionsaenderung.
          _gizmoOffset.set(start.x - dragGizmo.pivot.x, start.y - dragGizmo.pivot.y, start.z - dragGizmo.pivot.z);
          _gizmoOffset.applyQuaternion(_gizmoDeltaQuat);
          f.group.position.set(
            dragGizmo.pivot.x + _gizmoOffset.x,
            dragGizmo.pivot.y + _gizmoOffset.y,
            dragGizmo.pivot.z + _gizmoOffset.z);
          if (f.icon) {
            f.icon.position.set(f.group.position.x, 0.05, f.group.position.z);
            f.icon.rotation.y = f.group.rotation.y + (f._lastPanRad || 0);
          }
        }
        showEditReadout('Drehen ' + dragGizmo.axis.toUpperCase() + ': ' +
                        (delta >= 0 ? '+' : '') + Math.round(rad2deg(delta)) + '°');
      }
    }
  } else if (dragMode === 'stageDrag' && view.selectedStageId) {
    const so = stageObjects[view.selectedStageId];
    const gh = intersectGround();
    if (gh && so && dragStartStagePos) {
      const nx = snap(gh.x - dragStartStagePos.offsetX);
      const nz = snap(gh.z - dragStartStagePos.offsetZ);
      const dxw = nx - so.mesh.position.x;
      const dzw = nz - so.mesh.position.z;
      so.mesh.position.x = nx;
      so.mesh.position.z = nz;
      so.data.position.x = nx;
      so.data.position.z = nz;
      if (dxw || dzw) moveDockedFixtures(view.selectedStageId, dxw, dzw);
      if (so._helper) so._helper.update();
      updateResizeHandles();
    }
  } else if (dragMode === 'stageResize' && view.selectedStageId && dragResizeStart) {
    const so = stageObjects[view.selectedStageId];
    const gh = intersectGround();
    if (gh && so) {
      const fx = dragResizeStart.fixedX;
      const fz = dragResizeStart.fixedZ;
      const newGripX = snap(gh.x);
      const newGripZ = snap(gh.z);
      const newSizeX = Math.max(0.2, Math.abs(newGripX - fx));
      const newSizeZ = Math.max(0.2, Math.abs(newGripZ - fz));
      const newCX = (fx + newGripX) / 2;
      const newCZ = (fz + newGripZ) / 2;
      // Truss/Platform-Groups werden in updateStageObjectProps komplett neu
      // gebaut (dispose + Modell-Clone). Die GESNAPPTEN Werte aendern sich nur
      // beim Ueberqueren einer Rasterlinie -> nur dann neu aufbauen, statt pro
      // Mausbewegung (verhindert den GC-/Perf-Churn beim Resizen).
      if (newSizeX !== dragResizeStart.lastSizeX || newSizeZ !== dragResizeStart.lastSizeZ
          || newCX !== dragResizeStart.lastCX || newCZ !== dragResizeStart.lastCZ) {
        dragResizeStart.lastSizeX = newSizeX;
        dragResizeStart.lastSizeZ = newSizeZ;
        dragResizeStart.lastCX = newCX;
        dragResizeStart.lastCZ = newCZ;
        updateStageObjectProps(view.selectedStageId, {
          size: {x: newSizeX, z: newSizeZ},
          position: {x: newCX, z: newCZ},
        });
        moveDockedFixtures(view.selectedStageId, 0, 0);
        updateResizeHandles();
      }
      if (so._helper) so._helper.update();
    }
  } else if (dragMode === 'marquee') {
    const m = document.getElementById('marquee');
    const x1 = Math.min(downMouseX, clientX);
    const y1 = Math.min(downMouseY, clientY);
    const x2 = Math.max(downMouseX, clientX);
    const y2 = Math.max(downMouseY, clientY);
    m.style.left = x1 + 'px';
    m.style.top = y1 + 'px';
    m.style.width = (x2 - x1) + 'px';
    m.style.height = (y2 - y1) + 'px';
  }
  // 3c-2 Dirty-Quellen (aktive Drag-Gestik): EIN Sammelpunkt fuer alle
  // Szenen-Drags — 'rotate' (redundant zu updateCamera), 'pan' (mutiert
  // orthoCam.position DIREKT und laeuft an updateCamera/resizeOrtho vorbei!),
  // 'fixtureDrag'/'gizmoDrag' (Fixture-Transforms + Dock-Preview),
  // 'stageDrag'/'stageResize' (Stage-Transforms). 'marquee' ist reine
  // DOM-Mutation -> kein Render noetig.
  if (dragMode !== 'none' && dragMode !== 'marquee') requestRender();
  lastMouseX = clientX; lastMouseY = clientY;
}

export function handlePointerUp(shiftKey) {
  if (!isLeftDragging) return;
  isLeftDragging = false;
  // ── Aim-Werkzeug: sauberer Tipp (kein Drag) ─────────────────────────────────
  if (view.editMode === 'edit' && (view.editTool === 'aim' || view.editTool === 'trace') && !mouseMovedDuringClick) {
    const fid = pickFixture();
    const bridge = bridgeRef.get();
    if (fid != null) {
      // Gerät antippen = auswählen (Mehrfach mit Shift)
      if (shiftKey) { if (!view.selectedFids.includes(fid)) view.selectedFids.push(fid); }
      else { view.selectedFids = [fid]; }
      updateOutlines();
      updateFABs();
      updateMeasureReadout();
      if (bridge && bridge.fixtureSelectionChanged) {
        try { bridge.fixtureSelectionChanged(JSON.stringify(view.selectedFids)); } catch (e) {}
      }
      dragMode = 'none';
      return;
    }
    // Keine Fixture getroffen -> Fläche (Boden/Wand/Plattform) anpeilen
    const pickable = floorMesh
      ? [floorMesh, ...Object.values(stageObjects).map(s => s.mesh)]
      : Object.values(stageObjects).map(s => s.mesh);
    raycaster.setFromCamera(mouse, view.activeCam);
    const hits = raycaster.intersectObjects(pickable, true);
    if (hits.length > 0 && view.selectedFids.length > 0) {
      const point = hits[0].point;
      let nx = 0, ny = 1, nz = 0;   // Welt-Normale (Default = nach oben)
      if (hits[0].face) {
        const ln = hits[0].face.normal;
        const obj = hits[0].object; obj.updateMatrixWorld(true);
        const e = obj.matrixWorld.elements;
        const wx = e[0]*ln.x + e[4]*ln.y + e[8]*ln.z;
        const wy = e[1]*ln.x + e[5]*ln.y + e[9]*ln.z;
        const wz = e[2]*ln.x + e[6]*ln.y + e[10]*ln.z;
        const L = Math.sqrt(wx*wx + wy*wy + wz*wz) || 1;
        nx = wx/L; ny = wy/L; nz = wz/L;
      }
      if (view.editTool === 'trace') {
        setLastTraceTarget({ x: point.x, y: point.y, z: point.z, nx, ny, nz });
        if (bridge && bridge.startTrace) {
          try { bridge.startTrace(JSON.stringify(_traceSpec())); } catch (e) {}
        }
        const shp = traceShape === 'line' ? 'Linie' : (traceShape === 'rect' ? 'Rechteck' : 'Kreis');
        showEditReadout('○ Nachfahren: ' + shp + ' (' + traceRadius.toFixed(1) + ' m) um ' +
                        point.x.toFixed(1) + ' / ' + point.y.toFixed(1) + ' / ' + point.z.toFixed(1) + ' m');
      } else {
        if (bridge && bridge.aimFixturesAt) {
          try {
            bridge.aimFixturesAt(JSON.stringify({
              x: point.x, y: point.y, z: point.z, nx, ny, nz,
              fids: view.selectedFids.slice(),
            }));
          } catch (e) {}
        }
        showEditReadout('⌖ Ziel: ' + point.x.toFixed(2) + ' / ' +
                        point.y.toFixed(2) + ' / ' + point.z.toFixed(2) + ' m');
      }
    }
    dragMode = 'none';
    return;
  }
  if (dragMode === 'fixtureDrag' || dragMode === 'gizmoDrag') {
    // VIZ-13 3b-G: Gizmo-Gestik nutzt EXAKT denselben Commit wie der Koerper-Drag
    // -> ein fixtureGestureEnd je Fixture, Python buendelt zu EINEM Undo-Command.
    const gizmoRotate = (dragMode === 'gizmoDrag' && dragGizmo && dragGizmo.mode === 'rotate');
    const bridge = bridgeRef.get();
    for (const fid of view.selectedFids) {
      const f = fixtures[fid];
      if (!f) continue;
      // Andock-Beziehung festschreiben: bei aktivem Andocken aus der Vorschau,
      // bei freiem Ziehen (Andocken AUS) loest ein Drag eine bestehende Bindung.
      let newDock;
      if (settings.dockEnabled) {
        newDock = (f._pendingDock !== undefined) ? f._pendingDock : (f.dockedTo || null);
      } else {
        newDock = null;
      }
      const hasDockChange = (newDock || null) !== (f.dockedTo || null);
      if (hasDockChange) f.dockedTo = newDock || null;
      delete f._pendingDock;
      const hasRotation = gizmoRotate;
      // Review-Fix (Undo-Gestik-Buendelung): EIN kombiniertes Event fuer das
      // Drag-Ende statt 2-3 einzelner Bridge-Aufrufe (Position/Dock/Rotation)
      // -- Python buendelt sie zu GENAU EINEM Undo-Command (Design (e): "EIN
      // Command pro Gestik"). Faellt auf die alten Einzel-Slots zurueck, falls
      // eine aeltere Bridge (ohne fixtureGestureEnd) im WebChannel haengt.
      if (bridge && bridge.fixtureGestureEnd) {
        const payload = {
          fid: Number(fid),
          x: f.group.position.x, y: f.group.position.y, z: f.group.position.z,
          hasRotation,
          hasDockChange,
          dock: f.dockedTo || '',
        };
        if (hasRotation) {
          payload.rx = rad2deg(f.group.rotation.x);
          payload.ry = rad2deg(f.group.rotation.y);
          payload.rz = rad2deg(f.group.rotation.z);
        }
        try { bridge.fixtureGestureEnd(JSON.stringify(payload)); } catch (e) {}
      } else {
        if (hasDockChange && bridge && bridge.fixtureDockChanged) {
          try { bridge.fixtureDockChanged(String(fid), f.dockedTo || ''); } catch (e) {}
        }
        if (bridge && bridge.fixturePositionChanged) {
          try {
            bridge.fixturePositionChanged(
              String(fid),
              f.group.position.x,
              f.group.position.y,
              f.group.position.z
            );
          } catch (err) {}
        }
        // Beim Drehen-Werkzeug zusätzlich die neue Ausrichtung (GRAD) melden.
        if (hasRotation && bridge && bridge.fixtureRotationChanged) {
          try {
            bridge.fixtureRotationChanged(
              String(fid),
              rad2deg(f.group.rotation.x),
              rad2deg(f.group.rotation.y),
              rad2deg(f.group.rotation.z)
            );
          } catch (err) {}
        }
      }
    }
    clearDockHighlight();
    hideDockBadge();
    hideEditReadout();
  }
  if (dragMode === 'stageDrag' && view.selectedStageId) {
    const so = stageObjects[view.selectedStageId];
    if (so) {
      so.data.position.x = so.mesh.position.x;
      so.data.position.y = so.mesh.position.y;
      so.data.position.z = so.mesh.position.z;
    }
    _reportDockedFixturePositions(view.selectedStageId);
    notifyStageListChanged();
  }
  if (dragMode === 'stageResize' && view.selectedStageId) {
    _reportDockedFixturePositions(view.selectedStageId);
    notifyStageListChanged();
    updateResizeHandles();
    dragResizeCorner = null;
    dragResizeStart = null;
  }
  if (dragMode === 'marquee') {
    const m = document.getElementById('marquee');
    const rect = renderer.domElement.getBoundingClientRect();
    const x1 = parseInt(m.style.left, 10);
    const y1 = parseInt(m.style.top, 10);
    const w = parseInt(m.style.width, 10);
    const h = parseInt(m.style.height, 10);
    m.style.display = 'none';
    const newlySelected = [];
    for (const fid in fixtures) {
      const f = fixtures[fid];
      const pos = (view.mode === '2D' && f.icon) ? f.icon.position.clone() : f.group.position.clone();
      const screen = pos.project(view.activeCam);
      const sx = ((screen.x + 1) / 2) * rect.width + rect.left;
      const sy = ((1 - screen.y) / 2) * rect.height + rect.top;
      if (sx >= x1 && sx <= x1 + w && sy >= y1 && sy <= y1 + h) {
        newlySelected.push(Number(fid));
      }
    }
    if (shiftKey) {
      for (const fid of newlySelected) if (!view.selectedFids.includes(fid)) view.selectedFids.push(fid);
    } else {
      view.selectedFids = newlySelected;
    }
    updateOutlines();
  }
  dragMode = 'none';
  dragGizmo = null;         // VIZ-13 3b-G: Gizmo-Gestik beendet
  updateMeasureReadout();   // Abstand zeigen, wenn jetzt genau 2 ausgewählt sind
}

// VIZ-10: Fixture-Tooltip ausblenden - bei Drag-Start, bei jeder programmatischen
// Transform-Aenderung (jsApplyFixtureTransform-Pfad) und beim Mausverlassen des
// Canvas. Ohne das blieb der zuletzt gezeigte Text (inkl. veralteter Koordinaten)
// stehen, solange sich die Maus nicht bewegt - auch nach einer Verschiebung ueber
// das Properties-Panel.
export function hideTooltip() {
  const tt = document.getElementById('tooltip');
  if (tt) tt.style.display = 'none';
}

// Mouse listeners (thin wrappers)
renderer.domElement.addEventListener('mousedown', function(e) {
  if (e.button !== 0) return;
  hideTooltip();
  handlePointerDown(e.clientX, e.clientY, e.shiftKey);
}, false);

window.addEventListener('mouseup', function(e) {
  handlePointerUp(e.shiftKey);
});

window.addEventListener('mousemove', function(e) {
  handlePointerMove(e.clientX, e.clientY, e.ctrlKey);
  // Tooltip (Maus-only, bei Touch irrelevant)
  if (!isLeftDragging) {
    setMouseFromCoords(e.clientX, e.clientY);
    const fid = pickFixture();
    const tt = document.getElementById('tooltip');
    if (fid != null && fixtures[fid]) {
      const f = fixtures[fid];
      tt.style.display = 'block';
      tt.style.left = (e.clientX + 12) + 'px';
      tt.style.top = (e.clientY - 8) + 'px';
      const pos = f.group.position;
      tt.textContent = '[' + fid + '] ' + (f.data.label || '?') + ' - ' + f.type +
        '  (X:' + pos.x.toFixed(1) + ' Y:' + pos.y.toFixed(1) + ' Z:' + pos.z.toFixed(1) + ')';
    } else {
      tt.style.display = 'none';
    }
  }
});

renderer.domElement.addEventListener('mouseleave', hideTooltip);

renderer.domElement.addEventListener('wheel', function(e) {
  if (view.mode === '3D') {
    view.radius = Math.max(4, Math.min(120, view.radius + e.deltaY * 0.04));
    updateCamera();
  } else {
    orthoState.size = Math.max(4, Math.min(80, orthoState.size + e.deltaY * 0.02));
    resizeOrtho();
  }
}, { passive: true });

// ── Spaet-Bindung (zirkulaere Abhaengigkeit: bridge/bridge.js ruft
// handlePointerDown/Up etc. NICHT direkt auf, aber `bridge` selbst entsteht
// erst beim WebChannel-Connect - siehe Design-Dokument "Kern-Gotcha") ──────
export const bridgeRef = { get: () => null };

export function wirePointerLateBindings({ getBridge }) {
  bridgeRef.get = getBridge;
}
