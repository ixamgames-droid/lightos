// VIZ-13 Schritt 3a-4: View mode 2D / 3D (ehem. stage_scene.html:2009-2043).
// Reines Verschieben.
import { view, fixtures, stageObjects } from '../state.js';
import { presetObjects, floorMesh } from '../scene/grid_floor.js';
import { resizeOrtho, perspectiveCam, orthoCam } from '../camera/cameras.js';
import { applyStageObject2DStyle, updateResizeHandles } from './stage_objects.js';
import { requestRender } from '../scene/render_loop.js';  // VIZ-13 3c-2
import { resyncBeamVisibility } from '../fixtures/builders.js';

// 3c-1: Gesten-Hint unten rechts pro Modus — vorher stand DAUERHAFT der
// 3D-Text da, auch im 2D-Plan (stale Footer-Hint, Reframe-Befund 3).
// Drag-Verhalten haengt am editMode (pointer.js): Geraet ziehen verschiebt
// NUR im Bau-Modus, im Ansehen-Modus schwenkt jeder Drag — der Text nennt
// deshalb den Modus explizit. Zoom/Doppel-Tipp gelten modusunabhaengig
// (pointer.js#wheel, touch.js Doppel-Tipp -> resetCameraView inkl. Ortho).
export const HINT_3D = '3D: 1-Finger drehen · 2-Finger Pinch/Schwenk · Doppel-Tipp = Kamera-Reset · Lang drücken = Fixture platzieren';
export const HINT_2D = '2D-Plan: Mausrad/Pinch = Zoom · Doppel-Tipp = Ansicht zurücksetzen · Ansehen: Ziehen = schwenken · Bauen: Gerät ziehen = verschieben';

export function setViewMode(mode) {
  view.mode = (mode === '2D') ? '2D' : '3D';
  view.activeCam = (view.mode === '2D') ? orthoCam : perspectiveCam;
  document.getElementById('mode-text').textContent = (view.mode === '2D') ? '2D Top View' : '3D View';
  document.getElementById('ruler-info').style.display = (view.mode === '2D') ? 'block' : 'none';
  const hintEl = document.getElementById('controls');
  if (hintEl) hintEl.textContent = (view.mode === '2D') ? HINT_2D : HINT_3D;
  // Toggle fixtures visibility
  for (const fid in fixtures) {
    const f = fixtures[fid];
    f.group.visible = (view.mode === '3D');
    if (f.icon) f.icon.visible = (view.mode === '2D');
    // A3D-24: Kegel-Sichtbarkeit (Einzelkopf + Laser-Faecher + Multi-Head-Pro-Kopf)
    // am View-Wechsel neu setzen — sonst kleben sie auf dem letzten (2D-)Stand 'false',
    // bis das naechste DMX-Update der Fixture updateFixture() durchlaeuft. Deckt jetzt
    // auch PAR-Bar/Mover-Bar/Spider-Pro-Kopf-Kegel ab (vorher nur f.beam/f.laserBeams).
    resyncBeamVisibility(f);
  }
  // Hide preset 3D scenery in 2D top-down to reduce clutter
  presetObjects.forEach(o => {
    if (o.userData && o.userData.isFloor) return;
    o.visible = (view.mode === '3D');
  });
  if (floorMesh) floorMesh.visible = true;
  // 2D-OCCLUSION-FIX: User-Buehnenobjekte im 2D halbtransparent (durchscheinend),
  // im 3D wieder voll — sonst verdecken Boden/Plattformen die Fixture-Icons.
  for (const id in stageObjects) applyStageObject2DStyle(id, view.mode === '2D');
  // Resize ortho on mode switch (preserve aspect)
  resizeOrtho();
  // Resize-Handles neu generieren (Groesse haengt vom Viewmode ab)
  updateResizeHandles();
  // 3c-2: Modus-Wechsel schaltet Kamera + Sichtbarkeit ALLER Objekte um
  // (redundant zu resizeOrtho — explizit fuer den Fall, dass sich die
  // Aufruf-Kette oben aendert).
  requestRender();
}
