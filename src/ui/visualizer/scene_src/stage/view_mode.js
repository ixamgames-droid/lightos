// VIZ-13 Schritt 3a-4: View mode 2D / 3D (ehem. stage_scene.html:2009-2043).
// Reines Verschieben.
import { view, fixtures, stageObjects, settings } from '../state.js';
import { presetObjects, floorMesh } from '../scene/grid_floor.js';
import { resizeOrtho, perspectiveCam, orthoCam } from '../camera/cameras.js';
import { applyStageObject2DStyle, updateResizeHandles } from './stage_objects.js';

export function setViewMode(mode) {
  view.mode = (mode === '2D') ? '2D' : '3D';
  view.activeCam = (view.mode === '2D') ? orthoCam : perspectiveCam;
  document.getElementById('mode-text').textContent = (view.mode === '2D') ? '2D Top View' : '3D View';
  document.getElementById('ruler-info').style.display = (view.mode === '2D') ? 'block' : 'none';
  // Toggle fixtures visibility
  for (const fid in fixtures) {
    const f = fixtures[fid];
    f.group.visible = (view.mode === '3D');
    if (f.icon) f.icon.visible = (view.mode === '2D');
    // Hide beam cones in 2D
    if (f.beam) f.beam.visible = (view.mode === '3D') && settings.showCones && f.beam.material.opacity > 0.01;
    // VIZ-03: Laser-Faecher-Sichtbarkeit am View-Wechsel ebenfalls neu setzen —
    // sonst bleibt sie auf dem letzten (2D-)Stand 'false' kleben, bis das naechste
    // DMX-Update updateFixture() erneut durchlaeuft.
    if (f.laserBeams) {
      for (const bm of f.laserBeams) {
        if (bm.material) bm.visible = (view.mode === '3D') && settings.showCones && bm.material.opacity > 0.01;
      }
    }
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
}
