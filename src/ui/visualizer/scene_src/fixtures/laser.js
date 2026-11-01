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
//   muster   VIZ-95: echtes Muster aus den Profilangaben (LAS-33) —
//            {id, name, kontur: [[u,v,u,v…]…], punkte: [u,v…], unbekannt?}
//            in normierten Koordinaten (-1..1, x rechts, y oben). Ist es da,
//            gilt es statt `form`: Linienzuege werden ein Strahlenkegel
//            (Mantel vom Austrittsfenster bis zur Kontur), Einzelpunkte je ein
//            Strahl; `unbekannt` = neutraler Einzelstrahl.
//   farbe    VIZ-95: [r,g,b] aus den Farb-Bereichen des Profils — NUR der
//            Farbton der Strahlen, die Helligkeit bleibt beim Dimmer.
//   dx, dy, dz, dr   Bewegung laeuft im Geraet selbst (dynamische Bereiche
//            der Kanaele bzw. Auto-Programm mit Geschwindigkeit > 0)
//   tempo    0..1 (speed) — Tempo dieser Eigenbewegung
//
// Leistung: das Rig wird EINMAL je Geraet gebaut (32 Strahlen + 1 Flaeche, eine
// geteilte Zylinder-Geometrie, dazu ein Kegelmantel mit fester Kapazitaet —
// ein Musterwechsel schreibt dessen Punkte nur um, VIZ-95). Ein DMX-Update setzt nur Drehung, Skalierung
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
export const LASER_MAX_BEAMS = 32;      // VIZ-95: Pool fuer gepunktete Muster
const KRANZ_STRAHLEN = 8;               // Grobform „Strahlenkranz" (VIZ-79)
// VIZ-95: Kegelmantel eines Musters. Kapazitaet = visualizer_service.
// LASER_MUSTER_MAX_KONTUR; deckt weniger als eine Flaeche (ein Kreis-Kegel
// ueberlagert sich vorn und hinten).
export const LASER_MUSTER_MAX_KONTUR = 192;
export const LASER_KEGEL_OPACITY = 0.22;
const MUSTER_TAN = Math.tan(0.3);      // halber Oeffnungswinkel bei voller Groesse

const LASER_PITCH = 0.06;        // rad (~3,5°) nach unten — ueber den Koepfen
const FAN_HALF = 0.35;           // halbe Faecherbreite bei voller Groesse (rad)
const RING_HALF = 0.18;          // halber Oeffnungswinkel des Strahlenkranzes
const POS_YAW = 0.6;             // x = ±1 -> ±34° Schwenk
const POS_PITCH = 0.35;          // y = ±1 -> ±20° Neigung
const MIN_SIZE = 0.15;           // Groesse 0 ist ein schmaler, kein unsichtbarer Faecher

export const LASER_FORMEN = ['faecher', 'einzel', 'kranz', 'flaeche'];

const _AUF = new THREE.Vector3(0, 1, 0);
const _dir = new THREE.Vector3();
const _UNBEKANNT = { id: 'unbekannt', name: '', kontur: [], punkte: [], unbekannt: true };

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

// VIZ-95: Kegelmantel JE GERAET (die Kontur ist je Laser verschieden) mit
// fester Kapazitaet; ein Musterwechsel schreibt nur das Positions-Attribut um
// und setzt den Zeichenbereich. Die Kontur steht in Einheiten je Meter Laenge
// (u, v, 1) * L — die Groesse setzt scale.x/scale.y.
function kegelGeo() {
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(
    new Float32Array(LASER_MUSTER_MAX_KONTUR * 9), 3));
  g.setDrawRange(0, 0);
  // Feste Huelle statt computeBoundingSphere je Musterwechsel.
  g.boundingSphere = new THREE.Sphere(new THREE.Vector3(0, 0, LASER_BEAM_LENGTH / 2),
                                      LASER_BEAM_LENGTH);
  return g;
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
  const kegelMat = sheetMat.clone();
  const kegel = new THREE.Mesh(kegelGeo(), kegelMat);
  kegel.userData.deckkraft = LASER_KEGEL_OPACITY;
  kegel.userData.kegel = true;
  nurLicht(kegel);
  pivot.add(kegel);
  laserBeams.push(kegel);
  const rig = { pivot, beams: laserBeams.slice(0, LASER_MAX_BEAMS), sheet, kegel,
                state: defaultState(), key: '',
                muster: null, musterId: '', kegelSegmente: 0,
                punkte: new Float32Array(LASER_MAX_BEAMS * 2), punktN: 0,
                farbe: null, farbeObj: new THREE.Color() };
  poseLaser(rig, 0);
  return { rig, laserBeams };
}

function defaultState() {
  return { x: 0, y: 0, sx: 1, sy: 1, rot: 0, form: 0,
           dx: false, dy: false, dz: false, dr: false, tempo: 0,
           farbe: '' };
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

  if (rig.muster) { poseMuster(rig, gx, gy); return; }
  rig.kegel.userData.aktiv = false;
  const form = LASER_FORMEN[s.form] || 'faecher';
  let n = 0;
  for (let i = 0; i < rig.beams.length; i++) {
    const bm = rig.beams[i];
    if (form === 'faecher' && i < 5) {
      const a = FAN_HALF * gx * (i / 2 - 1);
      _dir.set(Math.sin(a), 0, Math.cos(a));
    } else if (form === 'einzel' && i === 0) {
      _dir.set(0, 0, 1);
    } else if (form === 'kranz' && i < KRANZ_STRAHLEN) {
      const phi = (i / KRANZ_STRAHLEN) * 2 * Math.PI;
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

// VIZ-95: echtes Muster — Kegelmantel (Groesse ueber die Skalierung) plus je
// Einzelpunkt ein Strahl; ein unbekanntes Muster ist ein Strahl geradeaus.
function poseMuster(rig, gx, gy) {
  const kx = MUSTER_TAN * gx, ky = MUSTER_TAN * gy;
  rig.kegel.scale.set(kx, ky, 1);
  rig.kegel.userData.aktiv = rig.kegelSegmente > 0;
  rig.sheet.userData.aktiv = false;
  const unbekannt = !!rig.muster.unbekannt;
  let n = 0;
  for (let i = 0; i < rig.beams.length; i++) {
    const bm = rig.beams[i];
    if (unbekannt && i === 0) {
      _dir.set(0, 0, 1);
    } else if (!unbekannt && i < rig.punktN) {
      _dir.set(rig.punkte[2 * i] * kx, rig.punkte[2 * i + 1] * ky, 1).normalize();
    } else {
      bm.userData.aktiv = false;
      continue;
    }
    bm.quaternion.setFromUnitVectors(_AUF, _dir);
    bm.userData.aktiv = true;
    n += 1;
  }
  rig.aktiveStrahlen = n;
}

// Muster in das Rig schreiben — nur wenn es ein ANDERES ist (id). Keine neuen
// Geometrien: das Positions-Attribut des Kegels wird ueberschrieben.
function setzeMuster(rig, m) {
  if (!m) {
    rig.muster = null; rig.musterId = ''; rig.kegelSegmente = 0; rig.punktN = 0;
    rig.kegel.geometry.setDrawRange(0, 0);
    return;
  }
  const id = String(m.id || m.name || '');
  if (rig.muster && id === rig.musterId) return;
  rig.muster = m.unbekannt ? _UNBEKANNT : m;
  rig.musterId = id;
  const L = LASER_BEAM_LENGTH;
  const attr = rig.kegel.geometry.getAttribute('position');
  const a = attr.array;
  let seg = 0;
  for (const linie of (m.unbekannt ? [] : (m.kontur || []))) {
    for (let j = 0; j + 3 < linie.length && seg < LASER_MUSTER_MAX_KONTUR; j += 2) {
      const o = seg * 9;
      a[o] = 0; a[o + 1] = 0; a[o + 2] = 0;
      a[o + 3] = linie[j] * L; a[o + 4] = linie[j + 1] * L; a[o + 5] = L;
      a[o + 6] = linie[j + 2] * L; a[o + 7] = linie[j + 3] * L; a[o + 8] = L;
      seg += 1;
    }
  }
  rig.kegelSegmente = seg;
  rig.kegel.geometry.setDrawRange(0, seg * 3);
  attr.needsUpdate = true;
  const p = m.unbekannt ? [] : (m.punkte || []);
  const n = Math.min(LASER_MAX_BEAMS, Math.floor(p.length / 2));
  for (let i = 0; i < 2 * n; i++) rig.punkte[i] = zahl(p[i], -1, 1, 0);
  rig.punktN = n;
}

function setzeFarbe(rig, farbe) {
  const ok = Array.isArray(farbe) && farbe.length === 3;
  if (!ok) { rig.farbe = null; rig.state.farbe = ''; return; }
  const r = zahl(farbe[0], 0, 255, 255), g = zahl(farbe[1], 0, 255, 255),
        b = zahl(farbe[2], 0, 255, 255);
  rig.farbeObj.setRGB(r / 255, g / 255, b / 255);
  rig.farbe = rig.farbeObj;
  rig.state.farbe = `${r},${g},${b}`;
}

// VIZ-95: Farbe der Laserstrahlen fuer applyGenericColor — die Profilfarbe,
// sonst die allgemeine Geraetefarbe. Nur der Farbton: Deckkraft und
// Sichtbarkeit rechnet der Aufrufer weiter aus der Helligkeit.
export function laserFarbe(f, allgemein) {
  return (f && f.laserRig && f.laserRig.farbe) || allgemein;
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
    setzeMuster(rig, (L.muster && typeof L.muster === 'object') ? L.muster : null);
    setzeFarbe(rig, L.farbe);
  } else {
    Object.assign(s, defaultState());
    setzeMuster(rig, null);
    setzeFarbe(rig, null);
  }
  // Nur neu setzen, wenn sich etwas geaendert hat (DMX kommt im Takt, auch
  // wenn der Laser steht); bewegte Laser setzt der Frame-Takt.
  const key = `${s.x}|${s.y}|${s.sx}|${s.sy}|${s.rot}|${s.form}|${rig.musterId}`;
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

// VIZ-110: removeFixture meldet das Geraet hier ab. Ohne das bliebe der
// Eintrag bis zum naechsten Bild stehen (tickLaserAnimation raeumt ihn dort
// auch ab) — so lange meldete die Live-Probe einen Laser, den es nicht mehr
// gibt. Ein Neubau mit gleicher fid setzt den Eintrag ueber
// noteLaserAnimation ohnehin neu nach seinem eigenen Stand.
export function vergissLaserAnimation(fid) {
  _bewegt.delete(Number(fid));
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
    muster: rig.muster ? (rig.muster.unbekannt ? 'unbekannt' : (rig.muster.name || rig.musterId)) : null,
    kegel: rig.kegel.userData.aktiv ? rig.kegelSegmente : 0,
    punkte: rig.muster && !rig.muster.unbekannt ? rig.punktN : 0,
    kegelSkala: [rig.kegel.scale.x, rig.kegel.scale.y],
    farbe: rig.state.farbe,
    yaw: rig.pivot.rotation.y, pitch: rig.pivot.rotation.x, roll: rig.pivot.rotation.z,
    bewegt: _bewegt.has(Number(fid)),
    animationAktiv: laserAnimationAktiv(),
  };
}
