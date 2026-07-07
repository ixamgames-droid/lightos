// VIZ-13 Schritt 3a-4: Touch-Handler (Pinch-Zoom + Long-Press statt
// Rechtsklick + Drag) + FAB-Click-Handler + Keyboard
// (ehem. stage_scene.html:3062-3268). Reines Verschieben.
import { renderer } from '../scene/renderer.js';
import { rad2deg } from '../scene/renderer.js';
import { orthoCam, orthoState, resizeOrtho, panCamera3D, resetCameraView } from '../camera/cameras.js';
import { fitSelected } from '../camera/presets.js';
import { fixtures, stageObjects, settings, view } from '../state.js';
import { setMouseFromCoords, pickFixture, pickStageObject, snap } from './picking.js';
import { findDockTarget, moveDockedFixtures, _reportDockedFixturePositions } from '../stage/docking.js';
import { updateOutlines } from './tools.js';
import { removeStageObject, notifyStageListChanged } from '../stage/stage_objects.js';
import {
  handlePointerDown, handlePointerMove, handlePointerUp,
  getFabLastPlaceCoords, _placeFixtureAtMouse, pointerState,
} from './pointer.js';
import { requestRender } from '../scene/render_loop.js';  // VIZ-13 3c-2

let lastTouchDist = 0;
let lastTouchCx = 0, lastTouchCy = 0;   // Zwei-Finger-Centroid (fuer Pan)
let longPressTimer = null;
let _lpTouchX = 0, _lpTouchY = 0;
let _lastTapTime = 0, _lastTapX = 0, _lastTapY = 0;   // Doppel-Tipp-Erkennung

function _showLongPressRing(cx, cy) {
  const ring = document.getElementById('longpress-ring');
  if (!ring) return;
  ring.style.left = cx + 'px';
  ring.style.top = cy + 'px';
  ring.style.display = 'block';
  ring.style.animation = 'none';
  ring.offsetHeight; // trigger reflow
  ring.style.animation = 'lp-pulse 0.6s ease-out';
  setTimeout(function() { if (ring) ring.style.display = 'none'; }, 700);
}

renderer.domElement.addEventListener('touchstart', function(e) {
  e.preventDefault();
  document.getElementById('tooltip').style.display = 'none';
  if (e.touches.length === 1) {
    const t = e.touches[0];
    // Doppel-Tipp auf leere Flaeche -> Kamera-Reset (T-VIZ-14)
    const now = Date.now();
    setMouseFromCoords(t.clientX, t.clientY);
    const overEmpty = (pickFixture() == null && pickStageObject() == null);
    if (now - _lastTapTime < 300 &&
        Math.abs(t.clientX - _lastTapX) < 30 && Math.abs(t.clientY - _lastTapY) < 30 &&
        overEmpty) {
      resetCameraView();
      _lastTapTime = 0;
      pointerState.isLeftDragging = false;
      pointerState.dragMode = 'none';
      return;
    }
    _lastTapTime = now; _lastTapX = t.clientX; _lastTapY = t.clientY;
    _lpTouchX = t.clientX; _lpTouchY = t.clientY;
    // Long-Press (600ms) = Fixture platzieren (ersetzt Rechtsklick)
    longPressTimer = setTimeout(function() {
      longPressTimer = null;
      setMouseFromCoords(_lpTouchX, _lpTouchY);
      _placeFixtureAtMouse();
      _showLongPressRing(_lpTouchX, _lpTouchY);
      pointerState.isLeftDragging = false;
      pointerState.dragMode = 'none';
    }, 600);
    handlePointerDown(t.clientX, t.clientY, false);
  } else if (e.touches.length === 2) {
    if (longPressTimer) { clearTimeout(longPressTimer); longPressTimer = null; }
    pointerState.isLeftDragging = false;
    pointerState.dragMode = 'none';
    const dx = e.touches[0].clientX - e.touches[1].clientX;
    const dy = e.touches[0].clientY - e.touches[1].clientY;
    lastTouchDist = Math.sqrt(dx * dx + dy * dy);
    lastTouchCx = (e.touches[0].clientX + e.touches[1].clientX) / 2;
    lastTouchCy = (e.touches[0].clientY + e.touches[1].clientY) / 2;
  }
}, { passive: false });

renderer.domElement.addEventListener('touchmove', function(e) {
  e.preventDefault();
  if (longPressTimer) { clearTimeout(longPressTimer); longPressTimer = null; }
  if (e.touches.length === 1) {
    const t = e.touches[0];
    handlePointerMove(t.clientX, t.clientY);
  } else if (e.touches.length === 2) {
    // Zwei-Finger: Pinch-Zoom + Schwenk (Centroid-Verschiebung)
    pointerState.isLeftDragging = false;
    pointerState.dragMode = 'none';
    const dx = e.touches[0].clientX - e.touches[1].clientX;
    const dy = e.touches[0].clientY - e.touches[1].clientY;
    const dist = Math.sqrt(dx * dx + dy * dy);
    const delta = lastTouchDist - dist;
    const cx = (e.touches[0].clientX + e.touches[1].clientX) / 2;
    const cy = (e.touches[0].clientY + e.touches[1].clientY) / 2;
    const dcx = cx - lastTouchCx;
    const dcy = cy - lastTouchCy;
    if (view.mode === '3D') {
      view.radius = Math.max(4, Math.min(120, view.radius + delta * 0.06));
      panCamera3D(dcx, dcy);   // ruft updateCamera()
    } else {
      orthoState.size = Math.max(4, Math.min(80, orthoState.size + delta * 0.03));
      const a = window.innerWidth / window.innerHeight;
      orthoCam.position.x -= dcx * (2 * orthoState.size * a) / window.innerWidth;
      orthoCam.position.z -= dcy * (2 * orthoState.size) / window.innerHeight;
      resizeOrtho();
    }
    lastTouchDist = dist;
    lastTouchCx = cx; lastTouchCy = cy;
  }
}, { passive: false });

renderer.domElement.addEventListener('touchend', function(e) {
  if (longPressTimer) { clearTimeout(longPressTimer); longPressTimer = null; }
  if (e.touches.length === 0) {
    handlePointerUp(false);
  } else if (e.touches.length === 1) {
    const t = e.touches[0];
    pointerState.lastMouseX = t.clientX;
    pointerState.lastMouseY = t.clientY;
  }
}, { passive: false });

// ============================================================================
// Floating Action Buttons (FABs) – Klick-Handler (Sichtbarkeit updateFABs()
// liegt in interaction/tools.js, siehe Kommentar dort)
// ============================================================================
export function fabDelete() {
  if (view.editMode === 'edit' && view.selectedFids.length > 0) {
    const bridge = bridgeRef.get();
    for (const fid of view.selectedFids.slice()) {
      if (bridge && bridge.fixtureDeleted) {
        try { bridge.fixtureDeleted(String(fid)); } catch (err) {}
      }
      removeFixtureRef.get()(fid);
    }
    view.selectedFids = [];
    updateOutlines();
  } else if (view.editMode === 'stage' && view.selectedStageId) {
    removeStageObject(view.selectedStageId);
  }
}

export function fabRotate() {
  if (view.editMode === 'stage' && view.selectedStageId) {
    const so = stageObjects[view.selectedStageId];
    if (so) {
      so.mesh.rotation.y += Math.PI / 2;
      so.data.rotation = so.mesh.rotation.y;
      if (so._helper) so._helper.update();
      // Angedockte Strahler ggf. neu einhaengen (Footprint hat sich gedreht)
      moveDockedFixtures(view.selectedStageId, 0, 0);
      _reportDockedFixturePositions(view.selectedStageId);
      requestRender();  // 3c-2: Stage-Rotation direkt (kein verdrahteter Helfer)
    }
  } else if (view.editMode === 'edit' && view.selectedFids.length > 0) {
    // Touch-Schnellaktion: ausgewählte Strahler um 90° um die Hochachse drehen.
    const bridge = bridgeRef.get();
    for (const fid of view.selectedFids) {
      const f = fixtures[fid];
      if (!f) continue;
      f.group.rotation.y += Math.PI / 2;
      if (f.icon) f.icon.rotation.y = f.group.rotation.y + (f._lastPanRad || 0);
      if (bridge && bridge.fixtureRotationChanged) {
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
    requestRender();  // 3c-2: Fixture-Rotation direkt (kein verdrahteter Helfer)
  }
}

export function fabPlace() {
  const coords = getFabLastPlaceCoords();
  const px = snap(coords ? coords.x : 0);
  const pz = snap(coords ? coords.z : 0);
  const bridge = bridgeRef.get();
  if (bridge && bridge.placeFixture) {
    let y = 6.5, dock = '';
    if (settings.dockEnabled) {
      const dt = findDockTarget(px, pz);
      if (dt) { y = dt.y; dock = dt.stageId; }
    }
    bridge.placeFixture(JSON.stringify({ x: px, y: y, z: pz, dock: dock }));
  }
}

// Keyboard
window.addEventListener('keydown', function(e) {
  if (e.key === 'Delete') {
    if (view.editMode === 'edit' && view.selectedFids.length > 0) {
      const bridge = bridgeRef.get();
      for (const fid of view.selectedFids.slice()) {
        if (bridge && bridge.fixtureDeleted) {
          try { bridge.fixtureDeleted(String(fid)); } catch (err) {}
        }
        removeFixtureRef.get()(fid);
      }
      view.selectedFids = [];
      updateOutlines();
    } else if (view.editMode === 'stage' && view.selectedStageId) {
      removeStageObject(view.selectedStageId);
    }
  } else if ((e.key === 'r' || e.key === 'R') && view.editMode === 'stage' && view.selectedStageId) {
    const so = stageObjects[view.selectedStageId];
    if (so) {
      so.mesh.rotation.y += Math.PI / 2;
      so.data.rotation = so.mesh.rotation.y;
      if (so._helper) so._helper.update();
      requestRender();  // 3c-2: Stage-Rotation direkt (kein verdrahteter Helfer)
    }
  } else if (e.key === 'Escape') {
    view.selectedFids = [];
    view.selectedStageId = null;
    updateOutlines();
  } else if (e.key === 'f' || e.key === 'F') {
    // VIZ-13 Schritt 3b-K-1: F-Taste = Fit-Selected (leere Auswahl -> Fit-All)
    fitSelected();
  }
});

// ── Spaet-Bindung (bridge entsteht erst beim WebChannel-Connect;
// removeFixture liegt in fixtures/fixtures.js, das seinerseits ueber
// wireFixturesLateBindings von interaction/tools.js abhaengt - ein direkter
// Import fixtures.js->touch.js->tools.js->fixtures.js waere zirkulaer,
// siehe Design-Dokument "Kern-Gotcha") ──────────────────────────────────────
export const bridgeRef = { get: () => null };
export const removeFixtureRef = { get: () => () => {} };
export function wireTouchLateBindings({ getBridge, removeFixture }) {
  bridgeRef.get = getBridge;
  removeFixtureRef.get = () => removeFixture;
}
