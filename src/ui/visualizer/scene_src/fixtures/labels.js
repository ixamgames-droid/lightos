// VIZ-14: persistente Fixture-Labels im 3D-Visualizer ("#<fid> <Kurzname>").
//
// Ansatz Sprite (three.js), NICHT CSS2D: das Label ist ein Kind der Fixture-
// root-Gruppe -> es folgt Position/Rotation und versteckt sich in 2D (root.visible)
// OHNE Extra-Verdrahtung, und es wird im GL-Pass gezeichnet + faced automatisch die
// Kamera. Es gibt KEINE Per-Frame-DOM-Projektion (der CSS2D-Kostentreiber, den der
// Plan nennt) und KEIN requestRender/Live-Probe von hier (Endlos-Render-Falle,
// s. render_loop.js). Sprite-`sizeAttenuation` (Default true) = feste Weltgroesse ->
// Labels schrumpfen beim Rauszoomen = Auto-Declutter (die "ab Zoomstufe"-Vorgabe).
import * as THREE from '../three/three.js';
import { settings } from '../state.js';  // VIZ-LABELS: globaler showLabels-Toggle

const _LABEL_COLOR = '#cfe3ff';
const _CANVAS_W = 256, _CANVAS_H = 64;
// Ab dieser Kamera-Distanz (Weltmeter) zur Fixture wird das Label ausgeblendet
// (zusaetzlich zur Groessen-Attenuation) — haelt dichte, weit entfernte Rigs sauber.
const _LABEL_MAX_DIST = 28;

// Ein Label-Sprite aus einer Canvas-Textur bauen. Schrift auto-fit (schrumpft, bis
// der Text in die Box passt) — laengere Namen ("#12 MH LINKS") bleiben lesbar.
export function makeFixtureLabel(text) {
  const canvas = document.createElement('canvas');
  canvas.width = _CANVAS_W; canvas.height = _CANVAS_H;
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, _CANVAS_W, _CANVAS_H);
  ctx.fillStyle = 'rgba(16,18,26,0.80)';
  ctx.fillRect(0, 0, _CANVAS_W, _CANVAS_H);
  ctx.strokeStyle = _LABEL_COLOR; ctx.lineWidth = 2;
  ctx.strokeRect(2, 2, _CANVAS_W - 4, _CANVAS_H - 4);
  ctx.fillStyle = _LABEL_COLOR;
  ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  const s = String(text);
  let font = 30;
  do {
    ctx.font = 'bold ' + font + 'px Segoe UI, Tahoma, sans-serif';
    if (ctx.measureText(s).width <= _CANVAS_W - 18) break;
    font -= 2;
  } while (font > 12);
  ctx.fillText(s, _CANVAS_W / 2, _CANVAS_H / 2 + 1);
  const tex = new THREE.CanvasTexture(canvas);
  tex.needsUpdate = true;
  const mat = new THREE.SpriteMaterial({ map: tex, transparent: true, depthTest: false });
  const sprite = new THREE.Sprite(mat);
  sprite.scale.set(2.6, 0.65, 1);   // Weltgroesse (sizeAttenuation Default true)
  sprite.renderOrder = 999;         // ueber den Fixture-Meshes
  sprite.userData.text = s;         // Test/Debug-Hook (Canvas-Text ist sonst nicht lesbar)
  return sprite;
}

// Textur-Map explizit freigeben: disposeObj (grid_floor.js) disposed Geometry +
// Material, aber NICHT material.map — ohne dies leckt jede Fixture-Entfernung /
// jeder allFixtures-Resync eine CanvasTexture (Trap, vgl. stage_objects.js#Labels).
export function disposeFixtureLabel(sprite) {
  if (!sprite) return;
  if (sprite.material) {
    if (sprite.material.map) sprite.material.map.dispose();
    sprite.material.dispose();
  }
  if (sprite.parent) sprite.parent.remove(sprite);
}

function _visibleFor(f, camPos, show3d) {
  // VIZ-LABELS: globaler Toggle hat Vorrang — aus = alle Labels aus (ohne dass
  // die Sprites disposed werden; ein Re-Toggle blendet sie sofort wieder ein).
  return show3d && settings.showLabels && camPos.distanceTo(f.group.position) < _LABEL_MAX_DIST;
}

// Zoom-/Distanz-Gate, aus app.js#perFrameUpdate JEDEN rAF-Tick gerufen. Setzt die
// Label-Sichtbarkeit nach Kamera-Distanz. BEWUSST OHNE Kamera-Early-Out: die Distanz
// haengt an Kamera- UND Fixture-Position, also muss auch eine bewegte FIXTURE (Drag/
// Dock/Gizmo bei stehender Kamera) die Sichtbarkeit nachziehen — ein reiner Kamera-
// Cache liesse das Label sonst stale (Review-Fund). Die Kosten sind vernachlaessigbar
// (<=48 distanceTo/Frame, reine CPU) und es entsteht KEIN Render-Load: der Gate ruft
// NIE requestRender und registriert keine Live-Probe — eine reine, idempotente
// Sichtbarkeits-Zuweisung, die nur bei einem ohnehin dirty-en Frame (Kamera- ODER
// Fixture-Bewegung -> requestRender an der Quelle) tatsaechlich gerendert wird. Ein
// neu hinzugekommenes Label bekommt so im ersten gerenderten Frame (addFixture ->
// updateFixture -> requestRender; perFrame laeuft VOR dem Dirty-Gate) korrekt gesetzt.
export function updateLabelZoomVisibility(fixtures, cam, viewMode) {
  if (!cam) return;
  const p = cam.position;
  const show3d = (viewMode === '3D');
  for (const fid in fixtures) {
    const f = fixtures[fid];
    if (!f || !f.label) continue;
    f.label.visible = _visibleFor(f, p, show3d);
  }
}
