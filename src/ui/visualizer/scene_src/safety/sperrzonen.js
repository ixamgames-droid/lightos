// LAS-32 (Slice S1): Sperrzonen und Laser-Maximalfeld im 3D — NUR ANZEIGE.
//
// Dieses Modul ZEIGT, was Python eingetragen und gerechnet hat:
//   * Sperrzonen als rote, halbtransparente Quader,
//   * je Laser das Maximalfeld (vier Randwinkel + Sicherheitszuschlag) als
//     duenne Pyramide vom Geraet aus.
// Es schaltet nichts ab und entscheidet nichts — ob ein Laser eine Zone
// erreichen kann, rechnet ausschliesslich src/core/laser/sperrzonen.py.
//
// Bewusst ein eigenes Blatt-Modul (haengt nur an three, Szene, state und dem
// Render-Gate): keine Eingriffe in Geraetebau, Spot-Pool oder app.js. Die Daten
// kommen als EIN JSON-Text ueber den Poll (bridge.js, Schluessel `sperrzonen`).
//
// Drei Eigenschaften, die es von einem Buehnen-Element unterscheiden:
//   1. Faengt keine Eingabe (raycast = No-Op) — Klick, Marquee und Zielen
//      gehen durch eine Zone hindurch.
//   2. Zaehlt nicht zur Szenen-Ausdehnung (excludeFromFit) und wirft/faengt
//      keinen Schatten.
//   3. Das Feld haengt NICHT am Geraete-Objekt, sondern steht daneben in der
//      Szene und uebernimmt dessen Lage (sperrzonenAbgleich). So aendert sich
//      am Geraet nichts (Auswahl-Rahmen, Aufraeumen, Picking).
//
// Spitze der Pyramide = AUSTRITTSFENSTER des Modells (dort haengt das
// Strahlen-Rig, f.laserRig.pivot), nicht der Geraete-Ursprung — dieselbe Stelle
// wie feld_spitze() in Python.
//
// Achse: die Pyramide folgt der GERAETEACHSE (von ihr aus werden die Randwinkel
// gemessen). Das Strahlen-Schema des Lasers (laser.js) ist dagegen fest um
// LASER_PITCH (~3,4 Grad) nach unten geneigt, damit die Strahlen im Bild ueber
// die Koepfe laufen. Beide Bilder liegen also bewusst nicht auf einer Achse;
// gerechnet wird mit der Pyramide (Python: STRAHLBILD_NEIGUNG_GRAD).
import * as THREE from '../three/three.js';
import { scene, deg2rad } from '../scene/renderer.js';
import { fixtures } from '../state.js';
import { requestRender } from '../scene/render_loop.js';

export const ZONEN_FARBE = 0xff2020;
export const ZONEN_DECKKRAFT = 0.22;
export const FELD_FARBE = 0xffb000;
export const FELD_DECKKRAFT = 0.07;
export const FELD_LAENGE_STANDARD = 25.0;   // wie LASER_BEAM_LENGTH (laser.js)
const WINKEL_GESAMT_MAX = 89.0;

const _noop = () => {};
const _zonen = {};      // id -> { gruppe, daten }
const _felder = {};     // fid -> { gruppe, daten, ecken, lage }
let _laenge = FELD_LAENGE_STANDARD;
const _spitze = new THREE.Vector3();

function zahl(v, def) {
  const n = Number(v);
  return isFinite(n) ? n : def;
}

function nurAnzeige(obj) {
  obj.raycast = _noop;
  obj.castShadow = false;
  obj.receiveShadow = false;
  obj.userData.excludeFromFit = true;
  obj.userData.sperrzonenAnzeige = true;
}

function entsorge(gruppe) {
  if (!gruppe) return;
  scene.remove(gruppe);
  gruppe.traverse(o => {
    if (o.geometry) o.geometry.dispose();
    if (o.material) {
      if (o.material.map) o.material.map.dispose();
      o.material.dispose();
    }
  });
}

function schild(text) {
  const c = document.createElement('canvas');
  c.width = 512; c.height = 96;
  const g = c.getContext('2d');
  g.fillStyle = 'rgba(60,0,0,0.78)';
  g.fillRect(0, 0, c.width, c.height);
  g.strokeStyle = '#ff4040';
  g.lineWidth = 4;
  g.strokeRect(2, 2, c.width - 4, c.height - 4);
  g.fillStyle = '#ffd0d0';
  g.font = 'bold 40px sans-serif';
  g.textAlign = 'center';
  g.textBaseline = 'middle';
  g.fillText(String(text).slice(0, 24), c.width / 2, c.height / 2, c.width - 24);
  const mat = new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(c),
                                         transparent: true, depthTest: false });
  const s = new THREE.Sprite(mat);
  s.scale.set(2.4, 0.45, 1);
  nurAnzeige(s);
  return s;
}

function baueZone(d) {
  const b = Math.max(0.05, zahl(d.breite, 4));
  const h = Math.max(0.05, zahl(d.hoehe, 3));
  const t = Math.max(0.05, zahl(d.tiefe, 4));
  const gruppe = new THREE.Group();
  gruppe.position.set(zahl(d.x, 0), zahl(d.y, 0) + h / 2, zahl(d.z, 0));
  gruppe.rotation.y = deg2rad(zahl(d.dreh_y, 0));
  const geo = new THREE.BoxGeometry(b, h, t);
  const koerper = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({
    color: ZONEN_FARBE, transparent: true, opacity: ZONEN_DECKKRAFT,
    depthWrite: false, side: THREE.DoubleSide, fog: false,
  }));
  koerper.userData.teil = 'koerper';
  nurAnzeige(koerper);
  const kanten = new THREE.LineSegments(
    new THREE.EdgesGeometry(geo),
    new THREE.LineBasicMaterial({ color: ZONEN_FARBE, transparent: true, opacity: 0.9, fog: false }));
  nurAnzeige(kanten);
  const s = schild(d.name || 'Sperrzone');
  s.position.set(0, h / 2 + 0.35, 0);
  gruppe.add(koerper, kanten, s);
  nurAnzeige(gruppe);
  gruppe.userData.koerper = koerper;
  scene.add(gruppe);
  return gruppe;
}

// Ecken der Feld-Pyramide im Geraete-Koordinatensystem. Das Geraet strahlt
// nach lokal +Z; „rechts" aus Sicht des Geraets in Strahlrichtung ist lokal -X
// (dieselbe Festlegung wie geraete_achsen() in Python).
export function feldEcken(d, laenge) {
  const z = Math.max(2, zahl(d.zuschlag, 5));
  const tan = w => Math.tan(Math.min(WINKEL_GESAMT_MAX, zahl(w, 0) + z) * Math.PI / 180);
  const L = laenge;
  const xl = L * tan(d.links), xr = -L * tan(d.rechts);
  const yo = L * tan(d.oben), yu = -L * tan(d.unten);
  return [[xl, yo, L], [xr, yo, L], [xr, yu, L], [xl, yu, L]];
}

function baueFeld(d) {
  const e = feldEcken(d, _laenge);
  const pos = [0, 0, 0];
  for (const p of e) pos.push(p[0], p[1], p[2]);
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  geo.setIndex([0, 1, 2, 0, 2, 3, 0, 3, 4, 0, 4, 1]);
  const flaeche = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({
    color: FELD_FARBE, transparent: true, opacity: FELD_DECKKRAFT,
    depthWrite: false, side: THREE.DoubleSide, fog: false,
  }));
  nurAnzeige(flaeche);
  const lin = [];
  const strecke = (a, b) => lin.push(a[0], a[1], a[2], b[0], b[1], b[2]);
  for (let i = 0; i < 4; i++) {
    strecke([0, 0, 0], e[i]);
    strecke(e[i], e[(i + 1) % 4]);
  }
  const lgeo = new THREE.BufferGeometry();
  lgeo.setAttribute('position', new THREE.Float32BufferAttribute(lin, 3));
  const linien = new THREE.LineSegments(lgeo, new THREE.LineBasicMaterial({
    color: FELD_FARBE, transparent: true, opacity: 0.55, fog: false }));
  nurAnzeige(linien);
  const gruppe = new THREE.Group();
  gruppe.add(flaeche, linien);
  nurAnzeige(gruppe);
  gruppe.visible = false;      // erst sichtbar, wenn das Geraet in der Szene steht
  scene.add(gruppe);
  return { gruppe, ecken: e };
}

function vollstaendig(d) {
  return ['links', 'rechts', 'oben', 'unten'].every(
    k => typeof d[k] === 'number' && isFinite(d[k]) && d[k] >= 0);
}

/** Bestand ersetzen. `json` = Text oder Objekt {zonen:[...], felder:[...], laenge}. */
export function setSperrzonen(json) {
  const d = (typeof json === 'string') ? JSON.parse(json || '{}') : (json || {});
  for (const id in _zonen) { entsorge(_zonen[id].gruppe); delete _zonen[id]; }
  for (const fid in _felder) { entsorge(_felder[fid].gruppe); delete _felder[fid]; }
  _laenge = Math.max(1, zahl(d.laenge, FELD_LAENGE_STANDARD));
  for (const z of (d.zonen || [])) {
    if (!z || z.id === undefined || z.id === null) continue;
    _zonen[String(z.id)] = { gruppe: baueZone(z), daten: z };
  }
  for (const f of (d.felder || [])) {
    if (!f || !vollstaendig(f)) continue;       // ohne Randwinkel kein Feld
    const fid = Number(f.fid);
    if (!isFinite(fid)) continue;
    const gebaut = baueFeld(f);
    _felder[fid] = { gruppe: gebaut.gruppe, ecken: gebaut.ecken, daten: f, lage: '' };
  }
  sperrzonenAbgleich();
  requestRender();
  return Object.keys(_zonen).length;
}

/** Felder an die Lage ihrer Geraete heften. Billig (ein Vergleich je Laser),
 *  laeuft bei jedem Poll — so folgt das Feld einem verschobenen, gedrehten
 *  oder neu gebauten Geraet, ohne dass der Geraetebau davon wissen muss. */
export function sperrzonenAbgleich() {
  let geaendert = false;
  for (const fid in _felder) {
    const e = _felder[fid];
    const f = fixtures[fid];
    const g = f && f.group;
    if (!g) {
      if (e.gruppe.visible) { e.gruppe.visible = false; e.lage = ''; geaendert = true; }
      continue;
    }
    const q = g.quaternion;
    // Austrittsfenster: Lage des Strahlen-Rigs im Geraet (lokal), in die Welt
    // gedreht. Modell ohne Rig -> Geraete-Ursprung.
    const rig = f.laserRig && f.laserRig.pivot;
    _spitze.set(0, 0, 0);
    if (rig) _spitze.copy(rig.position).multiply(g.scale).applyQuaternion(q);
    _spitze.add(g.position);
    const p = _spitze;
    const lage = [p.x, p.y, p.z, q.x, q.y, q.z, q.w].map(v => v.toFixed(5)).join('|');
    if (lage !== e.lage || !e.gruppe.visible) {
      e.gruppe.position.copy(p);
      e.gruppe.quaternion.copy(q);
      e.gruppe.visible = true;
      e.lage = lage;
      geaendert = true;
    }
  }
  if (geaendert) requestRender();
  return geaendert;
}

/** Test-/Diagnose-Seam: was liegt wirklich in der Szene? */
export function sperrzonenInfo() {
  const zonen = [];
  for (const id in _zonen) {
    const g = _zonen[id].gruppe;
    const k = g.userData.koerper;
    const par = k.geometry.parameters || {};
    let treffer = -2;
    try {
      const rc = new THREE.Raycaster();
      scene.updateMatrixWorld();
      rc.set(new THREE.Vector3(g.position.x, g.position.y + 500, g.position.z),
             new THREE.Vector3(0, -1, 0));
      treffer = rc.intersectObject(g, true).length;
    } catch (err) { treffer = -2; }
    // Ecken in Weltkoordinaten, Reihenfolge wie zonen_ecken() in Python
    // (Bit 0 = x, Bit 1 = y, Bit 2 = z).
    const weltEcken = [];
    for (let i = 0; i < 8; i++) {
      const v = new THREE.Vector3((i & 1 ? 1 : -1) * par.width / 2,
                                  (i & 2 ? 1 : -1) * par.height / 2,
                                  (i & 4 ? 1 : -1) * par.depth / 2);
      k.localToWorld(v);
      weltEcken.push([v.x, v.y, v.z]);
    }
    zonen.push({
      id, name: _zonen[id].daten.name, weltEcken,
      x: g.position.x, y: g.position.y, z: g.position.z,
      breite: par.width, hoehe: par.height, tiefe: par.depth,
      drehY: g.rotation.y * 180 / Math.PI,
      farbe: k.material.color.getHex(), deckkraft: k.material.opacity,
      transparent: !!k.material.transparent,
      inSzene: g.parent === scene, sichtbar: g.visible,
      raycastTreffer: treffer,
    });
  }
  const felder = [];
  for (const fid in _felder) {
    const e = _felder[fid];
    const g = e.gruppe;
    g.updateMatrixWorld(true);
    const welt = e.ecken.map(p => {
      const v = new THREE.Vector3(p[0], p[1], p[2]).applyMatrix4(g.matrixWorld);
      return [v.x, v.y, v.z];
    });
    felder.push({
      fid: Number(fid), sichtbar: g.visible, inSzene: g.parent === scene,
      x: g.position.x, y: g.position.y, z: g.position.z,
      ecken: e.ecken, weltEcken: welt,
    });
  }
  return { zonen, felder, laenge: _laenge };
}

// Zugang fuer Tests und Diagnose, ohne app.js anzufassen.
window.__lightosSperrzonen = {
  setzen: setSperrzonen, abgleich: sperrzonenAbgleich, info: sperrzonenInfo, feldEcken,
};
