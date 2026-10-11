// LAS-32 (Slice S1): Sperrzonen und Laser-Maximalfeld im 3D — NUR ANZEIGE.
//
// Dieses Modul ZEIGT, was Python eingetragen und gerechnet hat:
//   * Sperrzonen als rote, halbtransparente Quader,
//   * je Laser das Maximalfeld (vier Randwinkel + Sicherheitszuschlag) als
//     FUSSABDRUCK: kurzer Ansatz am Geraet, gelber Umriss dort, wo das Feld
//     auf Flaechen trifft, und der erreichte Teil einer Zone rot schraffiert,
//   * dazu das Fenster „Sicht des Lasers" (sperrzonen_lasersicht.js).
// (Beschreibung und Grenzen der Darstellung: Block „Darstellung des Feldes"
// weiter unten.)
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
// Spitze des Feldes = AUSTRITTSFENSTER des Modells (dort haengt das
// Strahlen-Rig, f.laserRig.pivot), nicht der Geraete-Ursprung — dieselbe Stelle
// wie feld_spitze() in Python.
//
// Achse: das Feld (eine nach vorn offene Pyramide) folgt der GERAETEACHSE (von ihr aus werden die Randwinkel
// gemessen). Das Strahlen-Schema des Lasers (laser.js) ist dagegen fest um
// LASER_PITCH (~3,4 Grad) nach unten geneigt, damit die Strahlen im Bild ueber
// die Koepfe laufen. Beide Bilder liegen also bewusst nicht auf einer Achse;
// gerechnet wird mit dem Feld (Python: STRAHLBILD_NEIGUNG_GRAD).
import * as THREE from '../three/three.js';
import { scene, deg2rad } from '../scene/renderer.js';
import { fixtures, stageObjects, view } from '../state.js';
import { requestRender } from '../scene/render_loop.js';
import * as G from './sperrzonen_geo.js';
import { zeichneLasersicht, lasersichtInfo, lasersichtBedienung } from './sperrzonen_lasersicht.js';

export const ZONEN_FARBE = 0xff2020;
export const ZONEN_DECKKRAFT = 0.22;
export const FELD_FARBE = 0xffb000;
export const FELD_LAENGE_STANDARD = 25.0;   // wie LASER_BEAM_LENGTH (laser.js)
const WINKEL_GESAMT_MAX = 89.0;

const _noop = () => {};
const _zonen = {};      // id -> { gruppe, daten, zustand, laser }
const _felder = {};     // fid -> { gruppe, daten, ecken, lage, extra, erreicht, teile }
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
  if (gruppe.parent) gruppe.parent.remove(gruppe);
  gruppe.traverse(o => {
    if (o.geometry) o.geometry.dispose();
    if (o.material) {
      if (o.material.map) o.material.map.dispose();
      o.material.dispose();
    }
  });
}

// Namensschild einer Zone. Es soll in JEDER Ansicht lesbar sein — in der
// Totale, von der Seite und im 2D-Plan. Ein Schild fester Groesse in Metern
// ist aus 25 m Abstand ein paar Pixel hoch. Darum haelt es einen festen Anteil
// der Bildhoehe (SCHILD_ANTEIL) und wird nur aus der Naehe nicht kleiner als
// SCHILD_MIN_M. Gesetzt wird das unmittelbar vor dem Zeichnen (onBeforeRender)
// aus der Kamera, mit der gerade gezeichnet wird.
export const SCHILD_ANTEIL = 0.036;
export const SCHILD_MIN_M = 0.45;
/** Das Schild steht mit seiner UNTERKANTE so weit ueber der Zone (Meter). */
export const SCHILD_ABSTAND_M = 0.30;

/** Hoehe des Schilds in Metern fuer eine Bildhoehe von `weltHoehe` Metern
 *  (in der Entfernung des Schilds). */
export function schildHoehe(weltHoehe) {
  const h = SCHILD_ANTEIL * zahl(weltHoehe, 0);
  return Math.max(SCHILD_MIN_M, h);
}

const _kamPos = new THREE.Vector3();
const _schildPos = new THREE.Vector3();

function schildAnpassen(_renderer, _scene, camera) {
  let weltHoehe = 0;
  if (camera.isOrthographicCamera) {
    weltHoehe = (camera.top - camera.bottom) / (camera.zoom || 1);
  } else if (camera.isPerspectiveCamera) {
    camera.getWorldPosition(_kamPos);
    this.getWorldPosition(_schildPos);
    weltHoehe = 2 * _kamPos.distanceTo(_schildPos) * Math.tan(camera.fov * Math.PI / 360);
  }
  const u = this.userData;
  // Zweizeilige Schilder und der Hinweis am Feld-Ansatz nutzen dieselbe Regel
  // (dieser mit eigenem Anteil); ohne Angabe gilt das Mass des Namensschilds.
  const h = (u.anteil ? Math.max(u.minM, u.anteil * weltHoehe) : schildHoehe(weltHoehe))
            * (u.hoehenFaktor || 1);
  const b = h * u.seitenverhaeltnis;
  if (Math.abs(this.scale.y - h) > 1e-4) {
    this.scale.set(b, h, 1);
    this.updateMatrixWorld(true);     // gilt noch fuer DIESES Bild
  }
}

function schild(text, zusatz) {
  const beschriftung = String(text).slice(0, 24);
  const zeile2 = zusatz ? String(zusatz).slice(0, 48) : '';
  const c = document.createElement('canvas');
  const ZEILE2 = 54;
  c.height = 96 + (zeile2 ? ZEILE2 : 0);
  let g = c.getContext('2d');
  g.font = 'bold 52px sans-serif';
  // So breit wie der Text: ein kurzer Name gibt ein kurzes Schild.
  let breite = g.measureText(beschriftung).width;
  if (zeile2) {
    g.font = 'bold 30px sans-serif';
    breite = Math.max(breite, g.measureText(zeile2).width);
  }
  c.width = Math.max(160, Math.min(1024, Math.ceil(breite) + 56));
  g = c.getContext('2d');
  g.fillStyle = zeile2 ? 'rgba(120,0,0,0.95)' : 'rgba(70,0,0,0.92)';
  g.fillRect(0, 0, c.width, c.height);
  if (zeile2) {
    g.fillStyle = 'rgba(40,0,0,0.95)';
    g.fillRect(0, 96, c.width, ZEILE2);
  }
  g.strokeStyle = zeile2 ? '#ffd0d0' : '#ff5050';
  g.lineWidth = 5;
  g.strokeRect(2.5, 2.5, c.width - 5, c.height - 5);
  g.fillStyle = '#ffffff';
  g.font = 'bold 52px sans-serif';
  g.textAlign = 'center';
  g.textBaseline = 'middle';
  g.fillText(beschriftung, c.width / 2, 96 / 2 + 2, c.width - 24);
  if (zeile2) {
    g.fillStyle = '#ffcc00';
    g.font = 'bold 30px sans-serif';
    g.fillText(zeile2, c.width / 2, 96 + ZEILE2 / 2 - 2, c.width - 24);
  }
  const mat = new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(c),
                                         transparent: true, depthTest: false,
                                         depthWrite: false, fog: false });
  const s = new THREE.Sprite(mat);
  s.userData.seitenverhaeltnis = c.width / c.height;
  s.userData.hoehenFaktor = c.height / 96;      // die Namenszeile bleibt gleich gross
  s.userData.text = beschriftung;
  s.userData.zusatz = zeile2;
  s.scale.set(SCHILD_MIN_M * c.width / 96, SCHILD_MIN_M * c.height / 96, 1);
  s.center.set(0.5, 0);               // waechst von der Unterkante nach oben
  s.renderOrder = 20;                 // ueber Zonen und Feld
  s.onBeforeRender = schildAnpassen;
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
  s.position.set(0, h / 2 + SCHILD_ABSTAND_M, 0);
  gruppe.add(koerper, kanten, s);
  nurAnzeige(gruppe);
  gruppe.userData.koerper = koerper;
  gruppe.userData.kanten = kanten;
  gruppe.userData.schild = s;
  scene.add(gruppe);
  return gruppe;
}

// Ecken des Feldes in `laenge` Metern Abstand, im Geraete-Koordinatensystem.
// Das Geraet strahlt nach lokal +Z; „rechts" aus Sicht des Geraets in
// Strahlrichtung ist lokal -X (dieselbe Festlegung wie geraete_achsen() in
// Python). Gezeichnet wird diese lange Pyramide NICHT mehr (s. u.) — die Ecken
// bleiben als Pruefgroesse: an ihnen bindet der Szenen-Test die Lage des
// Feldes an feld_ebenen() in Python.
export function feldEcken(d, laenge) {
  const z = Math.max(2, zahl(d.zuschlag, 5));
  const tan = w => Math.tan(Math.min(WINKEL_GESAMT_MAX, zahl(w, 0) + z) * Math.PI / 180);
  const L = laenge;
  const xl = L * tan(d.links), xr = -L * tan(d.rechts);
  const yo = L * tan(d.oben), yu = -L * tan(d.unten);
  return [[xl, yo, L], [xr, yo, L], [xr, yu, L], [xl, yu, L]];
}

/** Anker eines Feldes: eine leere Gruppe, die die Lage des Austrittsfensters
 *  uebernimmt. Alles Sichtbare haengt aufbau() darunter. */
function baueFeld(d) {
  const gruppe = new THREE.Group();
  nurAnzeige(gruppe);
  gruppe.visible = false;      // erst sichtbar, wenn das Geraet in der Szene steht
  scene.add(gruppe);
  return { gruppe, ecken: feldEcken(d, _laenge) };
}

function vollstaendig(d) {
  return ['links', 'rechts', 'oben', 'unten'].every(
    k => typeof d[k] === 'number' && isFinite(d[k]) && d[k] >= 0);
}

/** Bestand ersetzen. `json` = Text oder Objekt
 *  {zonen:[...], felder:[...], laenge, lasersicht}. */
export function setSperrzonen(json) {
  const d = (typeof json === 'string') ? JSON.parse(json || '{}') : (json || {});
  for (const id in _zonen) { entsorge(_zonen[id].gruppe); delete _zonen[id]; }
  for (const fid in _felder) { entsorge(_felder[fid].gruppe); delete _felder[fid]; }
  _laenge = Math.max(1, zahl(d.laenge, FELD_LAENGE_STANDARD));
  // Fenster „Sicht des Lasers": der gemerkte Zustand kommt aus Python.
  if (typeof d.lasersicht === 'boolean') _lasersichtAn = d.lasersicht;
  for (const z of (d.zonen || [])) {
    if (!z || z.id === undefined || z.id === null) continue;
    _zonen[String(z.id)] = { gruppe: baueZone(z), daten: z, zustand: '', laser: [] };
  }
  for (const f of (d.felder || [])) {
    if (!f || !vollstaendig(f)) continue;       // ohne Randwinkel kein Feld
    const fid = Number(f.fid);
    if (!isFinite(fid)) continue;
    const gebaut = baueFeld(f);
    _felder[fid] = { gruppe: gebaut.gruppe, ecken: gebaut.ecken, daten: f, lage: '',
                     extra: null, erreicht: [], teile: {} };
  }
  lagenAbgleich();
  aufbauSicher();
  requestRender();
  return Object.keys(_zonen).length;
}

/** Felder an die Lage ihrer Geraete heften. Billig (ein Vergleich je Laser),
 *  laeuft bei jedem Poll — so folgt das Feld einem verschobenen, gedrehten
 *  oder neu gebauten Geraet, ohne dass der Geraetebau davon wissen muss. */
export function sperrzonenAbgleich() {
  let geaendert = lagenAbgleich();
  // Fussabdruck und die Sicht des Lasers haengen auch an den Buehnenkoerpern
  // — verschobene Plattform, neues Bild.
  const sig = buehnenSignatur();
  if (sig !== _buehneSig) { _buehneSig = sig; geaendert = true; }
  if (auswahlFolgen()) geaendert = true;
  if (geaendert) { aufbauSicher(); requestRender(); }
  return geaendert;
}

function lagenAbgleich() {
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
  return geaendert;
}

/** Das Fenster „Sicht des Lasers" folgt dem im 3D gewaehlten Laser — nur in
 *  dem Moment, in dem sich die Auswahl aendert (die Umschalter im Fenster
 *  bleiben sonst wirksam). */
function auswahlFolgen() {
  const sel = view.selectedFids || [];
  const sig = sel.join(',');
  if (sig === _auswahlSig) return false;
  _auswahlSig = sig;
  for (let i = sel.length - 1; i >= 0; i--) {
    const fid = Number(sel[i]);
    if (_felder[fid]) {
      if (fid === Number(_lasersichtFid)) return false;
      _lasersichtFid = fid;
      return true;
    }
  }
  return false;
}

// ════════════════════════════════════════════════════════════════════════════
// Darstellung des Feldes (eine, vom Projektinhaber aus drei Varianten gewaehlt)
//
//   FUSSABDRUCK  kein Volumen quer durchs Bild. Am Geraet ein kurzer Ansatz,
//                der die Oeffnung zeigt; dort, wo das moegliche Strahlfeld auf
//                Flaechen trifft (Boden, quaderfoermige Buehnenkoerper), ein
//                gelber Umriss mit zarter Fuellung — begrenzt auf eine
//                Reichweite und zum Rand hin ausgeblendet.
//   SCHRAFFUR    der Teil einer Sperrzone, den das Feld erreicht, kraeftig rot
//                schraffiert. Ihr Schild sitzt UEBER der Zone, neben der
//                Schraffur, und traegt „⚠ Laser N erreicht diese Zone".
//                Nicht erreichte Zonen sind etwas blasser.
//   OHNE TREFFER die Feldkanten laufen ein Stueck ausblendend weiter (wohin
//                zeigt das Feld?), am Ansatz steht „Laser N: erreicht keine
//                Zone".
//   FENSTER      „Sicht des Lasers" (sperrzonen_lasersicht.js): Bild-im-Bild
//                aus dem Austrittsfenster, ein-/ausblendbar.
//
// GRENZEN DES FUSSABDRUCKS (bewusst, nur Darstellung): er faellt auf den Boden
// (y = 0) und auf die zugewandten Seiten QUADERFOERMIGER Buehnenkoerper —
// nicht auf Traversen, runde oder schraege Koerper, nicht auf Geraete. Und er
// kennt keine Verdeckung: was hinter einer Plattform im Schatten laege, wird
// trotzdem umrandet. Fuer „erreicht / erreicht nicht" spielt er keine Rolle.
//
// Alles ist NUR ANZEIGE und teilt die Regeln von oben: faengt keine Eingabe,
// zaehlt nicht zur Szenen-Ausdehnung, haengt nicht am Geraet. Der
// Strahlenfaecher des Lasers selbst (laser.js) bleibt unberuehrt.
//
// „Erreicht" wird hier fuer das BILD nachgerechnet — mit derselben Vorschrift
// wie kann_erreichen()/pruefe_laser() in Python (sperrzonen_geo.js) und per
// Test daran gebunden. Die Meldungen im Programm kommen weiter aus Python.
// ════════════════════════════════════════════════════════════════════════════
export const TREFFER_FARBE = 0xff2a2a;
export const ZONE_BLASS_DECKKRAFT = 0.12;
export const ANSATZ_LAENGE = 1.5;
/** Ohne Treffer laufen die Feldkanten so weit ausblendend weiter (Meter). */
export const FREI_LAENGE = 4.5;
/** Reichweite des Fussabdrucks ab Geraet (Meter, entlang der Achse) … */
export const FUSS_REICHWEITE = 12.0;
/** … mindestens aber so weit hinter der ersten getroffenen Flaeche. */
export const FUSS_NACHLAUF = 5.0;
const FUSS_LAENGE_MAX = 25.0;
const RAND_BILD_M = 0.02;          // Schnittflaechen knapp VOR der Zonenwand
const RAND_FUSS_M = 0.012;

let _buehneSig = '';
let _fehler = '';
let _lasersichtAn = true;
let _lasersichtFid = null;
let _auswahlSig = '';
let _melder = null;                // meldet Ein/Aus des Fensters an Python
const _mat = new THREE.Matrix4();
const _mat2 = new THREE.Matrix4();
const _vek = new THREE.Vector3();
const _vek2 = new THREE.Vector3();

function wandle(punkte, matrix) {
  return punkte.map(p => {
    _vek.set(p[0], p[1], p[2]).applyMatrix4(matrix);
    return [_vek.x, _vek.y, _vek.z];
  });
}

/** Konvexe Polygone -> ein Netz; `alpha(p)` je Ecke (Vorgabe 1). */
function flaechenNetz(polygone, material, alpha) {
  const pos = [], farbe = [];
  for (const p of polygone) {
    for (let i = 1; i + 1 < p.length; i++) {
      for (const q of [p[0], p[i], p[i + 1]]) {
        pos.push(q[0], q[1], q[2]);
        farbe.push(1, 1, 1, alpha ? alpha(q) : 1);
      }
    }
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  geo.setAttribute('color', new THREE.Float32BufferAttribute(farbe, 4));
  const m = new THREE.Mesh(geo, material);
  nurAnzeige(m);
  return m;
}

/** Strecken [[a, b], …] -> Linien; `alpha(p)` je Endpunkt (Vorgabe 1). */
function linienNetz(strecken, material, alpha) {
  const pos = [], farbe = [];
  for (const s of strecken) {
    for (const q of s) {
      pos.push(q[0], q[1], q[2]);
      farbe.push(1, 1, 1, alpha ? alpha(q) : 1);
    }
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  geo.setAttribute('color', new THREE.Float32BufferAttribute(farbe, 4));
  const l = new THREE.LineSegments(geo, material);
  nurAnzeige(l);
  return l;
}

function fuellMaterial(farbe, deckkraft) {
  return new THREE.MeshBasicMaterial({
    color: farbe, vertexColors: true, transparent: true, opacity: deckkraft,
    depthWrite: false, side: THREE.DoubleSide, fog: false,
    polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2,
  });
}

function linienMaterial(farbe, deckkraft) {
  return new THREE.LineBasicMaterial({
    color: farbe, vertexColors: true, transparent: true, opacity: deckkraft, fog: false });
}

/** Schraffur in Bildschirm-Pixeln: liest sich aus jeder Entfernung gleich. */
function schraffurMaterial(farbe, stark, schwach) {
  return new THREE.ShaderMaterial({
    uniforms: { farbe: { value: new THREE.Color(farbe) },
                stark: { value: stark }, schwach: { value: schwach } },
    vertexShader:
      'void main(){ gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }',
    fragmentShader:
      'uniform vec3 farbe; uniform float stark; uniform float schwach;' +
      'void main(){ float s = mod(gl_FragCoord.x + gl_FragCoord.y, 12.0);' +
      ' gl_FragColor = vec4(farbe, s < 5.0 ? stark : schwach); }',
    transparent: true, depthWrite: false, side: THREE.DoubleSide, fog: false,
  });
}

function umriss(polygon) {
  return polygon.map((p, i) => [p, polygon[(i + 1) % polygon.length]]);
}

/** Kleines, sachliches Schild am Feld-Ansatz („… erreicht keine Zone"). */
function hinweisSchild(text) {
  const c = document.createElement('canvas');
  c.height = 64;
  let g = c.getContext('2d');
  g.font = 'bold 30px sans-serif';
  c.width = Math.max(120, Math.min(1024, Math.ceil(g.measureText(text).width) + 40));
  g = c.getContext('2d');
  g.fillStyle = 'rgba(18,20,26,0.90)';
  g.fillRect(0, 0, c.width, c.height);
  g.strokeStyle = 'rgba(255,176,0,0.85)';
  g.lineWidth = 3;
  g.strokeRect(1.5, 1.5, c.width - 3, c.height - 3);
  g.fillStyle = '#ffd98a';
  g.font = 'bold 30px sans-serif';
  g.textAlign = 'center';
  g.textBaseline = 'middle';
  g.fillText(text, c.width / 2, c.height / 2 + 1);
  const s = new THREE.Sprite(new THREE.SpriteMaterial({
    map: new THREE.CanvasTexture(c), transparent: true, depthTest: false,
    depthWrite: false, fog: false }));
  s.userData.seitenverhaeltnis = c.width / c.height;
  s.userData.anteil = 0.024;
  s.userData.minM = 0.30;
  s.userData.text = text;
  s.center.set(0.5, 0);
  s.renderOrder = 19;
  s.onBeforeRender = schildAnpassen;
  nurAnzeige(s);
  return s;
}

// ── Rechen-Kontexte ─────────────────────────────────────────────────────────

/** Feld eines Lasers: Tangens-Werte und die Matrizen Laser <-> Welt. */
function feldKontext(fid, e) {
  e.gruppe.updateMatrixWorld(true);
  const welt = e.gruppe.matrixWorld.clone();
  const f = fixtures[fid];
  return {
    fid: Number(fid), t: G.tanWerte(e.daten), tOhne: G.tanWerte(e.daten, false),
    welt, zuLaser: new THREE.Matrix4().copy(welt).invert(),
    spitze: new THREE.Vector3().setFromMatrixPosition(welt),
    geraet: (f && f.group) ? f.group.position.clone() : null,
  };
}

/** Zone als Quader um den eigenen Ursprung, plus Matrizen Zone <-> Laser. */
function zonenKontext(k, z, rand) {
  const g = z.gruppe;
  g.updateMatrixWorld(true);
  const par = g.userData.koerper.geometry.parameters;
  const zuLaser = new THREE.Matrix4().multiplyMatrices(k.zuLaser, g.matrixWorld);
  return {
    hb: par.width / 2 + rand, hh: par.height / 2 + rand, ht: par.depth / 2 + rand,
    zuLaser, zuZone: new THREE.Matrix4().copy(zuLaser).invert(),
    weltZuZone: new THREE.Matrix4().copy(g.matrixWorld).invert(),
  };
}

/** Dieselbe Vorschrift wie pruefe_laser() in Python. */
function erreicht(k, z) {
  const q = zonenKontext(k, z, G.ZONEN_RAND_M);
  const inZone = v => {
    _vek2.copy(v).applyMatrix4(q.weltZuZone);
    return G.punktImQuader([_vek2.x, _vek2.y, _vek2.z], q.hb, q.hh, q.ht);
  };
  if (inZone(k.spitze) || (k.geraet && inZone(k.geraet))) return true;
  const ecken = wandle(G.quaderEcken(q.hb, q.hh, q.ht), q.zuLaser);
  for (const fl of G.FLAECHEN) {
    if (G.schneideFeld(fl.map(i => ecken[i]), k.t).length) return true;
  }
  return false;
}

/** Oberflaeche des Koerpers „Zone ∩ Feld" (Laser-Koordinaten):
 *  `aussen` = Anteile der Zonenwaende, `innen` = Anteile der Feldwaende;
 *  `q` = der Zonen-Kontext dazu. */
function schnittKoerper(k, z, rand) {
  const q = zonenKontext(k, z, rand);
  const ecken = wandle(G.quaderEcken(q.hb, q.hh, q.ht), q.zuLaser);
  const aussen = [], innen = [];
  for (const fl of G.FLAECHEN) {
    const p = G.schneideFeld(fl.map(i => ecken[i]), k.t);
    if (p.length >= 3) aussen.push(p);
  }
  for (const d of G.seitenDreiecke(k.t, 400)) {
    const p = G.schneideQuader(wandle(d, q.zuZone), q.hb, q.hh, q.ht);
    if (p.length >= 3) innen.push(wandle(p, q.zuLaser));
  }
  return { aussen, innen, q };
}

function buehnenKoerper() {
  const liste = [];
  for (const id in stageObjects) {
    const so = stageObjects[id];
    const m = so && so.mesh;
    if (!m || !m.visible) continue;
    const s = (so.data && so.data.size) || {};
    const par = (m.isMesh && m.geometry && m.geometry.parameters) || {};
    const quader = isFinite(par.width) && isFinite(par.height) && isFinite(par.depth);
    const hb = (quader ? par.width : zahl(s.x, 0)) / 2;
    const hh = (quader ? par.height : zahl(s.y, 0)) / 2;
    const ht = (quader ? par.depth : zahl(s.z, 0)) / 2;
    if (!(hb > 0 && hh > 0 && ht > 0)) continue;
    m.updateMatrixWorld(true);
    liste.push({ mesh: m, quader, hb, hh, ht });
  }
  return liste;
}

function buehnenSignatur() {
  const teile = [];
  for (const id in stageObjects) {
    const so = stageObjects[id];
    const m = so && so.mesh;
    if (!m) continue;
    const s = (so.data && so.data.size) || {};
    teile.push([id, m.visible ? 1 : 0, m.position.x, m.position.y, m.position.z,
                m.rotation.y, s.x, s.y, s.z].join(','));
  }
  return teile.join(';');
}

// ── Bausteine ───────────────────────────────────────────────────────────────

/** Kurzer Ansatz am Geraet: zeigt die Oeffnung des Feldes. Mit `weiter`
 *  laufen die vier Kanten bis dorthin ausblendend weiter. */
function baueAnsatz(k, laenge, weiter) {
  const richtungen = G.kantenRichtungen(k.t);
  const ecken = richtungen.map(r => [r[0] * laenge, r[1] * laenge, laenge]);
  const s = [0, 0, 0];
  const gruppe = new THREE.Group();
  const seiten = ecken.map((p, i) => [s, p, ecken[(i + 1) % 4]]);
  gruppe.add(flaechenNetz(seiten, fuellMaterial(FELD_FARBE, 0.10)));
  const strecken = ecken.map(p => [s, p]);
  for (const u of umriss(ecken)) strecken.push(u);
  gruppe.add(linienNetz(strecken, linienMaterial(FELD_FARBE, 0.95)));
  if (weiter > laenge) {
    const fern = richtungen.map(r => [r[0] * weiter, r[1] * weiter, weiter]);
    gruppe.add(linienNetz(ecken.map((p, i) => [p, fern[i]]),
                          linienMaterial(FELD_FARBE, 0.8),
                          p => Math.max(0, (weiter - p[2]) / (weiter - laenge))));
  }
  nurAnzeige(gruppe);
  return gruppe;
}

/** Wo trifft das Feld auf Boden und (quaderfoermige) Buehnenkoerper? */
function baueFussabdruck(k, koerper) {
  const roh = [];
  // Boden (y = 0) — nur, wenn das Geraet darueber haengt.
  if (k.spitze.y > RAND_FUSS_M) {
    const R = 4 * FUSS_LAENGE_MAX, x = k.spitze.x, z = k.spitze.z;
    roh.push(wandle([[x - R, RAND_FUSS_M, z - R], [x - R, RAND_FUSS_M, z + R],
                     [x + R, RAND_FUSS_M, z + R], [x + R, RAND_FUSS_M, z - R]], k.zuLaser));
  }
  // Quader der Buehne: nur die Seiten, die dem Geraet zugewandt sind.
  for (const b of koerper) {
    if (!b.quader) continue;
    const zuK = _mat.copy(b.mesh.matrixWorld).invert();
    _vek2.copy(k.spitze).applyMatrix4(zuK);
    const sp = [_vek2.x, _vek2.y, _vek2.z], h = [b.hb, b.hh, b.ht];
    const zuLaser = _mat2.multiplyMatrices(k.zuLaser, b.mesh.matrixWorld);
    const ecken = wandle(G.quaderEcken(b.hb + RAND_FUSS_M, b.hh + RAND_FUSS_M,
                                       b.ht + RAND_FUSS_M), zuLaser);
    G.FLAECHEN.forEach((fl, i) => {
      const n = G.NORMALEN[i];
      const a = n[0] ? 0 : (n[1] ? 1 : 2);
      if (sp[a] * n[a] <= h[a]) return;              // abgewandt
      roh.push(fl.map(j => ecken[j]));
    });
  }
  const getroffen = [];
  let nah = Infinity;
  for (const p of roh) {
    const c = G.schneideFeld(p, k.t, FUSS_LAENGE_MAX);
    if (c.length < 3) continue;
    getroffen.push(c);
    for (const q of c) if (q[2] < nah) nah = q[2];
  }
  const gruppe = new THREE.Group();
  nurAnzeige(gruppe);
  if (!getroffen.length) return { gruppe, anzahl: 0, reichweite: 0 };
  // Reichweite: FUSS_REICHWEITE ab Geraet — haengt der Laser so hoch, dass
  // das Feld erst dahinter aufsetzt, noch FUSS_NACHLAUF Meter ab dort. Die
  // letzten Meter blenden aus: das Feld hoert dort nicht auf, nur das Bild.
  const L = Math.min(FUSS_LAENGE_MAX, _laenge, Math.max(FUSS_REICHWEITE, nah + FUSS_NACHLAUF));
  const grenze = Math.max(nah + 1.0, L - FUSS_NACHLAUF);
  const polygone = [];
  for (const c of getroffen) {
    // an der Ausblend-Grenze teilen: so ist der Verlauf auf jeder Teilflaeche linear
    const vorn = G.schneide(c, q => q[2] - grenze);
    const fern = G.schneide(G.schneide(c, q => grenze - q[2]), q => q[2] - L);
    if (vorn.length >= 3) polygone.push(vorn);
    if (fern.length >= 3) polygone.push(fern);
  }
  if (!polygone.length) return { gruppe, anzahl: 0, reichweite: L };
  const alpha = p => (p[2] <= grenze) ? 1 : Math.max(0, (L - p[2]) / (L - grenze));
  gruppe.add(flaechenNetz(polygone, fuellMaterial(FELD_FARBE, 0.09), alpha));
  const strecken = [];
  for (const p of polygone) {
    for (const s of umriss(p)) {
      const [a, b] = s;
      const aufGrenze = v => Math.abs(a[2] - v) < 1e-6 && Math.abs(b[2] - v) < 1e-6;
      if (aufGrenze(grenze) || aufGrenze(L)) continue;    // Teilungs- und Endkante
      strecken.push(s);
    }
  }
  gruppe.add(linienNetz(strecken, linienMaterial(FELD_FARBE, 0.95), alpha));
  return { gruppe, anzahl: polygone.length, reichweite: L };
}

/** Der erreichte Teil einer Zone, rot schraffiert. `mitte` = Schwerpunkt der
 *  getroffenen Zonenwaende in ZONEN-Koordinaten (das Schild weicht ihm aus). */
function baueSchnitt(k, z) {
  let s = schnittKoerper(k, z, RAND_BILD_M);
  if (!s.aussen.length) s = schnittKoerper(k, z, G.ZONEN_RAND_M);   // nur der Rand beruehrt
  const gruppe = new THREE.Group();
  if (s.aussen.length) {
    const a = flaechenNetz(s.aussen, schraffurMaterial(TREFFER_FARBE, 0.92, 0.34));
    a.renderOrder = 6;
    gruppe.add(a);
  }
  if (s.innen.length) {
    const i = flaechenNetz(s.innen, schraffurMaterial(TREFFER_FARBE, 0.42, 0.10));
    i.renderOrder = 5;
    gruppe.add(i);
  }
  const strecken = [];
  for (const p of s.aussen.concat(s.innen)) for (const u of umriss(p)) strecken.push(u);
  if (strecken.length) {
    const l = linienNetz(strecken, linienMaterial(0xffe0e0, 0.95));
    l.renderOrder = 7;
    gruppe.add(l);
  }
  const summe = [0, 0, 0];
  let n = 0;
  for (const p of s.aussen) {
    for (const q of wandle(p, s.q.zuZone)) { summe[0] += q[0]; summe[1] += q[1]; summe[2] += q[2]; n++; }
  }
  nurAnzeige(gruppe);
  return { gruppe, anzahl: s.aussen.length + s.innen.length, summe, n };
}

/** Zustand einer Zone ins Bild setzen: Schild (mit Treffer-Zeile), Blaesse.
 *  `aktiv` = es steht ueberhaupt ein pruefbares Feld in der Szene. */
function zonenZustand(z, laser, aktiv, mitte) {
  const u = z.gruppe.userData;
  const par = u.koerper.geometry.parameters;
  z.laser = laser.slice();
  z.zustand = !aktiv ? '' : (laser.length ? 'erreicht' : 'frei');
  const blass = z.zustand === 'frei';
  u.koerper.material.opacity = blass ? ZONE_BLASS_DECKKRAFT : ZONEN_DECKKRAFT;
  u.kanten.material.opacity = blass ? 0.5 : 0.9;
  const wort = laser.length === 1 ? 'erreicht' : 'erreichen';
  const zusatz = laser.length ? '⚠ Laser ' + laser.join(', ') + ' ' + wort + ' diese Zone' : '';
  if (u.schild.userData.zusatz !== zusatz) {
    entsorge(u.schild);
    u.schild = schild(z.daten.name || 'Sperrzone', zusatz);
    z.gruppe.add(u.schild);
  }
  u.schild.material.opacity = blass ? 0.72 : 1;
  // Das Schild steht UEBER der Zone und rueckt von der Schraffur weg — so
  // verdeckt es sie auch im 2D-Plan (Blick von oben) nicht.
  let x = 0, t = 0;
  if (mitte) {
    if (Math.abs(mitte[0]) > 0.15 * par.width) x = -Math.sign(mitte[0]) * 0.25 * par.width;
    if (Math.abs(mitte[2]) > 0.15 * par.depth) t = -Math.sign(mitte[2]) * 0.25 * par.depth;
  }
  u.schild.position.set(x, par.height / 2 + SCHILD_ABSTAND_M, t);
}

/** Daten fuer das Fenster „Sicht des Lasers". */
function lasersichtDaten(fid, k, koerper, alle) {
  const e = _felder[fid];
  const zonen = [];
  for (const id in _zonen) {
    const q = zonenKontext(k, _zonen[id], 0);
    const ecken = wandle(G.quaderEcken(q.hb, q.hh, q.ht), q.zuLaser);
    zonen.push({ name: _zonen[id].daten.name || 'Sperrzone',
                 erreicht: e.erreicht.indexOf(id) >= 0,
                 flaechen: G.FLAECHEN.map(fl => fl.map(i => ecken[i])) });
  }
  const linien = [];
  const R = 40, x0 = Math.round(k.spitze.x / 2) * 2, z0 = Math.round(k.spitze.z / 2) * 2;
  for (let i = -R; i <= R; i += 2) {
    linien.push(wandle([[x0 + i, 0, z0 - R], [x0 + i, 0, z0 + R]], k.zuLaser));
    linien.push(wandle([[x0 - R, 0, z0 + i], [x0 + R, 0, z0 + i]], k.zuLaser));
  }
  const kanten = [];
  for (const b of koerper) {
    const zuLaser = _mat2.multiplyMatrices(k.zuLaser, b.mesh.matrixWorld);
    const ecken = wandle(G.quaderEcken(b.hb, b.hh, b.ht), zuLaser);
    for (const [a, c] of G.KANTEN) kanten.push([ecken[a], ecken[c]]);
  }
  return { fid: Number(fid), laser: alle, titel: 'Sicht von Laser ' + fid,
           tan: k.t, tanOhne: k.tOhne,
           winkel: e.daten, zonen, linien, koerper: kanten };
}

// ── Aufbau ──────────────────────────────────────────────────────────────────

function aufbau() {
  const jeZone = {}, mitten = {}, kontexte = {};
  for (const fid in _felder) {
    const e = _felder[fid];
    if (e.extra) { entsorge(e.extra); e.extra = null; }
    e.erreicht = [];
    e.teile = {};
    if (!e.gruppe.visible) continue;
    const k = kontexte[fid] = feldKontext(fid, e);
    for (const id in _zonen) {
      if (erreicht(k, _zonen[id])) {
        e.erreicht.push(id);
        (jeZone[id] = jeZone[id] || []).push(Number(fid));
      }
    }
  }
  const koerper = buehnenKoerper();
  for (const fid in kontexte) {
    const e = _felder[fid], k = kontexte[fid];
    const frei = !e.erreicht.length;
    const extra = new THREE.Group();
    nurAnzeige(extra);
    extra.add(baueAnsatz(k, ANSATZ_LAENGE, frei ? FREI_LAENGE : 0));
    const fuss = baueFussabdruck(k, koerper);
    extra.add(fuss.gruppe);
    let schnitt = 0;
    for (const id of e.erreicht) {
      const s = baueSchnitt(k, _zonen[id]);
      extra.add(s.gruppe);
      schnitt += s.anzahl;
      const m = mitten[id] = mitten[id] || { summe: [0, 0, 0], n: 0 };
      for (let i = 0; i < 3; i++) m.summe[i] += s.summe[i];
      m.n += s.n;
    }
    let hinweis = '';
    if (frei && Object.keys(_zonen).length) {
      hinweis = 'Laser ' + Number(fid) + ': erreicht keine Zone';
      const h = hinweisSchild(hinweis);
      // ueber der Oberkante des Ansatzes, damit es ihn nicht verdeckt
      h.position.set(0, k.t.o * ANSATZ_LAENGE + 0.25, ANSATZ_LAENGE);
      extra.add(h);
    }
    e.teile = { ansatz: ANSATZ_LAENGE, weiter: frei ? FREI_LAENGE : 0, fuss: fuss.anzahl,
                reichweite: fuss.reichweite, schnitt, hinweis };
    e.gruppe.add(extra);
    e.extra = extra;
  }
  const fids = Object.keys(kontexte).map(Number).sort((a, b) => a - b);
  for (const id in _zonen) {
    const m = mitten[id];
    zonenZustand(_zonen[id], (jeZone[id] || []).sort((a, b) => a - b), fids.length > 0,
                 (m && m.n) ? m.summe.map(v => v / m.n) : null);
  }
  // Fenster „Sicht des Lasers": nur mit pruefbarem Laser UND Zone.
  const moeglich = fids.length > 0 && Object.keys(_zonen).length > 0;
  let sicht = null;
  if (moeglich && _lasersichtAn) {
    const fid = (fids.indexOf(Number(_lasersichtFid)) >= 0) ? Number(_lasersichtFid) : fids[0];
    sicht = lasersichtDaten(fid, kontexte[fid], koerper, fids);
  }
  _buehneSig = buehnenSignatur();
  zeichneLasersicht(sicht, moeglich);
}

/** Die Darstellung darf den Poll (und damit die uebrige Szene) nie mitreissen. */
function aufbauSicher() {
  try {
    aufbau();
    _fehler = '';
  } catch (err) {
    _fehler = String((err && err.stack) || err);
    console.log('sperrzonen: Darstellung', err);
  }
}

/** Fenster „Sicht des Lasers" ein-/ausblenden; `fid` waehlt den Laser.
 *  Ohne Argumente: Zustand lesen. */
export function lasersicht(an, fid) {
  if (an !== undefined && an !== null) _lasersichtAn = !!an;
  if (fid !== undefined && fid !== null) _lasersichtFid = Number(fid);
  aufbauSicher();
  requestRender();
  return _lasersichtAn;
}

/** Wer erfaehrt, dass das Fenster IM 3D ein-/ausgeblendet wurde (Python
 *  merkt es sich). Gesetzt von bridge.js — dieses Modul kennt die Bruecke nicht. */
export function setLasersichtMelder(fn) {
  _melder = (typeof fn === 'function') ? fn : null;
}

lasersichtBedienung({
  an: an => {
    lasersicht(!!an);
    if (_melder) { try { _melder(!!an); } catch (err) { console.log('sperrzonen: Melder', err); } }
  },
  waehle: fid => { lasersicht(undefined, fid); },
});

/** Test-/Diagnose-Seam der Darstellung. */
export function sperrzonenDarstellungInfo() {
  const felder = [];
  for (const fid in _felder) {
    const e = _felder[fid];
    let fremd = 0;
    if (e.extra) e.extra.traverse(o => { if (!o.userData.sperrzonenAnzeige) fremd++; });
    felder.push({ fid: Number(fid), erreicht: e.erreicht.slice(), teile: e.teile,
                  extra: !!e.extra, ohneKennung: fremd });
  }
  const zonen = [];
  for (const id in _zonen) {
    const z = _zonen[id], u = z.gruppe.userData;
    const par = u.koerper.geometry.parameters;
    zonen.push({ id, zustand: z.zustand || '', laser: (z.laser || []).slice(),
                 deckkraft: u.koerper.material.opacity,
                 farbe: u.koerper.material.color.getHex(),
                 zusatz: u.schild.userData.zusatz || '',
                 schildOrt: [u.schild.position.x, u.schild.position.y, u.schild.position.z],
                 schildUeberZone: u.schild.position.y >= par.height / 2
                                  && u.schild.center.y === 0 });
  }
  return { fehler: _fehler, felder, zonen, lasersicht: lasersichtInfo(),
           lasersichtAn: _lasersichtAn };
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
      schild: { text: g.userData.schild.userData.text,
                breite: g.userData.schild.scale.x, hoehe: g.userData.schild.scale.y,
                seitenverhaeltnis: g.userData.schild.userData.seitenverhaeltnis },
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
  schildHoehe, darstellung: sperrzonenDarstellungInfo, lasersicht,
};
