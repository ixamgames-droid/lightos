// VIZ-79: Laser im 3D — Strahlen-Rig, DMX-Abbildung und langsame Bewegung.
//
// Ein Laser zeichnet keinen Lichtkegel, sondern einzelne duenne Strahlen bzw.
// eine Lichtflaeche, die ueber die Buehne bis ins Publikum reichen. Was die
// Profile an Laser-Kanaelen haben, rechnet Python in einen kleinen, bereits
// normierten Block ``payload.laser`` um (visualizer_service._laser_payload):
//
//   x, y     Position/Schwenk -1..1 (laser_x/laser_y, sonst pan/tilt)
//   sx, sy   Groesse 0..1      (laser_zoom_x/laser_zoom_y, sonst zoom)
//   rot      Winkel 0..1       (gobo_rotation)
//   form     0 Faecher · 1 Einzelstrahl · 2 Strahlenkranz · 3 Flaeche
//            (grob aus Musterbank/Musterauswahl — die echten Muster der
//            Geraete sind Vektorgrafiken, die der Viewer nicht nachzeichnet)
//   dx, dy, dz, dr   Bewegung laeuft im Geraet selbst (dynamische Bereiche
//            der Kanaele bzw. Auto-Programm mit Geschwindigkeit > 0)
//   tempo    0..1 (speed) — Tempo dieser Eigenbewegung
//
// Leistung: das Rig wird EINMAL je Geraet gebaut (8 Strahlen + 1 Flaeche, eine
// geteilte Zylinder-Geometrie). Ein DMX-Update setzt nur Drehung, Skalierung
// und Sichtbarkeit — keine neuen Geometrien, keine neuen Materialien, keine
// Vektor-Allokationen (Modul-Temporaere).
import * as THREE from '../three/three.js';
import { fixtures, settings, view, beamsOff } from '../state.js';
import { geteilteGeometrie } from '../scene/geteilte_geometrie.js';   // VIZ-66

// 25 m reichen von einer Rueckwand-Traverse ueber Buehne und Publikum; 1,5 cm
// Radius sind auf ~20 m Kameraabstand etwa ein bis zwei Pixel breit (WebGL-
// Linien waeren fest 1 px und skalierten nicht). Die Deckkraft ist eine EIGENE
// Konstante: Laser haengen bewusst NICHT an „Beam Opacity".
export const LASER_BEAM_LENGTH = 25.0;
export const LASER_BEAM_RADIUS = 0.015;
export const LASER_BEAM_OPACITY = 0.9;
// Eine Flaeche deckt viel mehr Pixel als ein Strahl — sonst ueberstrahlt sie.
export const LASER_SHEET_OPACITY = 0.3;
export const LASER_MAX_BEAMS = 8;

const LASER_PITCH = 0.06;        // rad (~3,5°) nach unten — ueber den Koepfen
const FAN_HALF = 0.35;           // halbe Faecherbreite bei voller Groesse (rad)
const RING_HALF = 0.18;          // halber Oeffnungswinkel des Strahlenkranzes
const POS_YAW = 0.6;             // x = ±1 -> ±34° Schwenk
const POS_PITCH = 0.35;          // y = ±1 -> ±20° Neigung
const MIN_SIZE = 0.15;           // Groesse 0 ist ein schmaler, kein unsichtbarer Faecher

export const LASER_FORMEN = ['faecher', 'einzel', 'kranz', 'flaeche'];

const _AUF = new THREE.Vector3(0, 1, 0);
const _dir = new THREE.Vector3();

// Geteilt von allen Lasern (VIZ-66-Cache): die Geometrie ist bei allen gleich,
// disposeObj gibt sie beim Entfernen eines Geraets nicht frei.
function beamGeo() {
  return geteilteGeometrie(`laser-strahl|${LASER_BEAM_LENGTH}|${LASER_BEAM_RADIUS}`, () => {
    const g = new THREE.CylinderGeometry(LASER_BEAM_RADIUS, LASER_BEAM_RADIUS,
                                         LASER_BEAM_LENGTH, 4, 1, true);
    g.translate(0, LASER_BEAM_LENGTH / 2, 0);   // Fuss am Ursprung
    return g;
  });
}
function sheetGeo() {
  // Dreieck vom Austrittsfenster nach vorn (+Z); die Breite setzt scale.x
  // (x = ±1 je Meter Laenge -> scale.x = tan(halbe Breite)).
  return geteilteGeometrie(`laser-flaeche|${LASER_BEAM_LENGTH}`, () => {
    const L = LASER_BEAM_LENGTH;
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(
      [0, 0, 0, -L, 0, L, L, 0, L], 3));
    return g;
  });
}

// Strahlen und Flaeche sind reines Licht, kein Koerper:
//  * raycast = No-Op — three r128 prueft `visible` beim Raycast NICHT. Ohne das
//    fing ein unsichtbarer (dunkler oder vom Muster abgeschalteter) 25-m-Strahl
//    jeden Klick, Hover und Zug ab, der irgendwo vor dem Laser landete: ein
//    Bodenklick waehlte den Laser aus, ein Zug verschob ihn (Review VIZ-79, H1).
//    Dieselbe Regel wie bei der Lotlinie des Platzier-Geists (place_ghost.js).
//  * excludeFromFit — „Auswahl einpassen" rahmt das Geraet, nicht 25 m Strahl
//    (camera/presets.js, wie bei den Lichtkegeln).
const _keinTreffer = () => {};
function nurLicht(mesh) {
  mesh.raycast = _keinTreffer;
  mesh.userData.excludeFromFit = true;
}

// Rig an das Geraete-Modell haengen. `fensterZ` = Austrittsfenster (lokal).
export function buildLaserRig(group, fensterZ) {
  const mat = new THREE.MeshBasicMaterial({
    color: 0x00ff00,
    transparent: true,
    opacity: LASER_BEAM_OPACITY,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    // Der Distanznebel der Szene wuerde die Strahlen zum Hintergrund hin
    // wegmischen; real sind Laser im Dunst eher heller als dunkler.
    fog: false,
  });
  const pivot = new THREE.Object3D();
  pivot.position.set(0, 0, fensterZ);
  pivot.rotation.order = 'YXZ';   // Schwenk, dann Neigung, dann Rollen um die Strahlachse
  group.add(pivot);
  const laserBeams = [];
  for (let i = 0; i < LASER_MAX_BEAMS; i++) {
    const bm = new THREE.Mesh(beamGeo(), mat.clone());
    bm.userData.deckkraft = LASER_BEAM_OPACITY;
    nurLicht(bm);
    pivot.add(bm);
    laserBeams.push(bm);
  }
  const sheetMat = mat.clone();
  sheetMat.side = THREE.DoubleSide;
  const sheet = new THREE.Mesh(sheetGeo(), sheetMat);
  sheet.userData.deckkraft = LASER_SHEET_OPACITY;
  sheet.userData.flaeche = true;
  nurLicht(sheet);
  pivot.add(sheet);
  laserBeams.push(sheet);
  const rig = { pivot, beams: laserBeams.slice(0, LASER_MAX_BEAMS), sheet,
                state: defaultState(), key: '' };
  poseLaser(rig, 0);
  return { rig, laserBeams };
}

function defaultState() {
  return { x: 0, y: 0, sx: 1, sy: 1, rot: 0, form: 0,
           dx: false, dy: false, dz: false, dr: false, tempo: 0 };
}

function zahl(v, lo, hi, def) {
  return (typeof v === 'number' && isFinite(v)) ? Math.max(lo, Math.min(hi, v)) : def;
}

function bewegt(s) { return s.dx || s.dy || s.dz || s.dr; }

// Strahlen eines Rigs aus Zustand + Zeit (s) setzen. Reine Transformation.
function poseLaser(rig, t) {
  const s = rig.state;
  const ph = t * (0.3 + 1.2 * s.tempo);   // langsam: ~0,05-0,24 Umlaeufe/s
  const yaw = s.x * POS_YAW + (s.dx ? 0.5 * Math.sin(ph) : 0);
  const pitch = LASER_PITCH + s.y * POS_PITCH + (s.dy ? 0.2 * Math.sin(0.7 * ph) : 0);
  const roll = s.rot * 2 * Math.PI + (s.dr ? ph : 0);
  const puls = s.dz ? (0.6 + 0.4 * Math.sin(1.3 * ph)) : 1;
  const gx = Math.max(MIN_SIZE, s.sx) * puls;
  const gy = Math.max(MIN_SIZE, s.sy) * puls;
  rig.pivot.rotation.set(pitch, yaw, roll);

  const form = LASER_FORMEN[s.form] || 'faecher';
  let n = 0;
  for (let i = 0; i < rig.beams.length; i++) {
    const bm = rig.beams[i];
    if (form === 'faecher' && i < 5) {
      const a = FAN_HALF * gx * (i / 2 - 1);
      _dir.set(Math.sin(a), 0, Math.cos(a));
    } else if (form === 'einzel' && i === 0) {
      _dir.set(0, 0, 1);
    } else if (form === 'kranz') {
      const phi = (i / rig.beams.length) * 2 * Math.PI;
      _dir.set(Math.sin(RING_HALF * gx) * Math.cos(phi),
               Math.sin(RING_HALF * gy) * Math.sin(phi), 1).normalize();
    } else {
      bm.userData.aktiv = false;
      continue;
    }
    bm.quaternion.setFromUnitVectors(_AUF, _dir);
    bm.userData.aktiv = true;
    n += 1;
  }
  rig.sheet.userData.aktiv = (form === 'flaeche');
  rig.sheet.scale.set(Math.tan(FAN_HALF * gx), 1, 1);
  rig.aktiveStrahlen = n;
}

// DMX-Teil des Lasers: Zustand aus payload.laser uebernehmen und Strahlen
// setzen. Fehlt der Block (aeltere Payloads, Profil ohne Laser-Kanaele), gilt
// der Grundzustand — ein statischer Faecher geradeaus.
export function applyLaser(f, dmx) {
  const rig = f && f.laserRig;
  if (!rig) return;
  const L = (dmx && dmx.laser) || null;
  const s = rig.state;
  if (L) {
    s.x = zahl(L.x, -1, 1, 0);
    s.y = zahl(L.y, -1, 1, 0);
    s.sx = zahl(L.sx, 0, 1, 1);
    s.sy = zahl(L.sy, 0, 1, s.sx);
    s.rot = zahl(L.rot, 0, 1, 0);
    s.form = Math.round(zahl(L.form, 0, LASER_FORMEN.length - 1, 0));
    s.dx = !!L.dx; s.dy = !!L.dy; s.dz = !!L.dz; s.dr = !!L.dr;
    s.tempo = zahl(L.tempo, 0, 1, 0);
  } else {
    Object.assign(s, defaultState());
  }
  // Nur neu setzen, wenn sich etwas geaendert hat (DMX kommt im Takt, auch
  // wenn der Laser steht); bewegte Laser setzt der Frame-Takt.
  const key = `${s.x}|${s.y}|${s.sx}|${s.sy}|${s.rot}|${s.form}`;
  if (key !== rig.key || bewegt(s)) {
    rig.key = key;
    poseLaser(rig, bewegt(s) ? jetzt() : 0);
  }
}

// ── Eigenbewegung ───────────────────────────────────────────────────────────
// Bewegte Laser (dx/dy/dz/dr) laufen zeitgesteuert weiter, solange sie
// leuchten — ohne dass Python jeden Frame neu schickt. Nur solange so ein
// Laser sichtbar ist, haelt die Live-Probe den Render-Loop wach.
const _bewegt = new Set();

function jetzt() { return performance.now() / 1000; }

// Nach applyGenericColor aufrufen: erst dann steht die Sichtbarkeit fest.
export function noteLaserAnimation(f) {
  const rig = f && f.laserRig;
  if (!rig) return;
  const leuchtet = f.laserBeams.some(bm => bm.visible);
  if (leuchtet && bewegt(rig.state)) _bewegt.add(f.fid);
  else _bewegt.delete(f.fid);
}

// Pro-Geraet-Veto (beamsOff, VIZ-15) gilt auch hier: ein ausgeblendeter Laser
// haelt den Render-Loop nicht wach und wird nicht weitergedreht.
export function laserAnimationAktiv() {
  if (!(_bewegt.size > 0 && view.mode === '3D' && settings.showCones)) return false;
  for (const fid of _bewegt) if (!beamsOff.has(fid)) return true;
  return false;
}

export function tickLaserAnimation(t) {
  if (!_bewegt.size) return;
  const zeit = (t === undefined) ? jetzt() : t;
  for (const fid of _bewegt) {
    const f = fixtures[fid];
    if (!f || !f.laserRig) { _bewegt.delete(fid); continue; }
    if (beamsOff.has(fid)) continue;
    poseLaser(f.laserRig, zeit);
  }
}

// Test-/Diagnose-Seam: Zustand und Pose eines Lasers als reine Zahlen.
export function laserInfo(fid, t) {
  const f = fixtures[fid];
  if (!f || !f.laserRig) return null;
  const rig = f.laserRig;
  if (t !== undefined) poseLaser(rig, t);
  return {
    state: { ...rig.state },
    form: LASER_FORMEN[rig.state.form],
    aktiv: rig.aktiveStrahlen,
    flaeche: !!rig.sheet.userData.aktiv,
    yaw: rig.pivot.rotation.y, pitch: rig.pivot.rotation.x, roll: rig.pivot.rotation.z,
    bewegt: _bewegt.has(Number(fid)),
    animationAktiv: laserAnimationAktiv(),
  };
}
