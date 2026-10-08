// VIZ-72: Feste Umgebung im Ansehen-Modus als wenige Koerper zeichnen.
//
// Jedes Buehnenobjekt (Podest, Wand, Traverse, Moebel, ...) ist ein eigenes
// Mesh — also ein eigener Draw-Call im Hauptbild UND einer je schattenwerfendem
// Licht im Schatten-Durchlauf. Im Ansehen-Modus aendert sich daran nichts;
// dort fasst dieses Modul die Objekte JE MATERIAL-ART zu einem Mesh zusammen
// (14 graue Traversen -> 1 Koerper). Gemessen an der Buehnen-Show (23 Objekte):
// 23 -> 8 Draw-Calls im Hauptbild, je Schatten-Licht ebenso.
//
// Bauen-Modi ('edit' / 'stage'), die 2D-Draufsicht und ein ausgewaehltes
// Buehnenobjekt zeigen wieder die EINZELNEN Objekte — dort wird verschoben,
// eingefaerbt, gepulst und halbtransparent gezeichnet.
//
// ★ Picking, Andocken und Strahl-Verdeckung bleiben unberuehrt: sie werfen
// ihre Strahlen gegen `stageObjects[id].mesh`, nie gegen die Szene, und der
// Raycaster von three r128 prueft `visible` nicht. Die Originale bleiben in
// der Szene (nur unsichtbar) und werden weiter von scene.updateMatrixWorld()
// mitgefuehrt. Die zusammengefassten Koerper selbst sind nicht pickbar.
//
// ★ Wie in shadow_update.js eine SIGNATUR statt Dirty-Hooks: Objekte aendern
// sich ueber ein gutes Dutzend Pfade (Bridge-Update, Stage-Reload, Docking,
// Groesse, Farbe, Loeschen). Die Signatur liest genau das, was das Bild
// bestimmt (Objekt, Weltmatrix, Geometrie, Material-Werte) — ein vergessener
// Pfad kann so keinen veralteten Koerper stehen lassen.
import * as THREE from '../three/three.js';
import { stageObjects, view } from '../state.js';
import { scene } from '../scene/renderer.js';

let _koerper = [];         // zusammengefasste Meshes in der Szene
let _versteckt = [];       // Original-Objekte (so.mesh), die dafuer unsichtbar sind
let _sig = null;
let _neubauten = 0;

/** Soll gerade zusammengefasst gezeichnet werden? */
export function umgebungZusammenfassen() {
  return view.mode === '3D' && view.editMode === 'view' && !view.selectedStageId;
}

function _matSchluessel(m) {
  const hex = (c) => (c && c.getHexString) ? c.getHexString() : '-';
  return [m.type, hex(m.color), hex(m.emissive), m.emissiveIntensity, m.roughness,
          m.metalness, m.side, m.transparent ? 1 : 0, m.opacity, m.depthWrite ? 1 : 0,
          m.vertexColors ? 1 : 0, m.flatShading ? 1 : 0, m.fog ? 1 : 0, m.wireframe ? 1 : 0].join(',');
}

// Darf dieses Mesh in einen Sammelkoerper? Texturierte oder mehrteilige
// Materialien und nicht-dreieckige Geometrie bleiben einzeln.
function _tauglich(o) {
  if (!o.isMesh || o.isInstancedMesh || o.isSkinnedMesh) return false;
  const m = o.material, g = o.geometry;
  if (!m || Array.isArray(m) || m.map || m.alphaMap || m.emissiveMap || m.envMap) return false;
  if (!g || !g.isBufferGeometry || !g.attributes.position) return false;
  if (g.morphAttributes && Object.keys(g.morphAttributes).length) return false;
  return true;
}

function _sichtbarKette(o, wurzel) {
  for (let p = o; p; p = p.parent) {
    if (!p.visible && !(p === wurzel)) return false;
    if (p === wurzel) return true;
  }
  return true;
}

function _signatur() {
  const teile = [];
  const ids = Object.keys(stageObjects).sort();
  for (const id of ids) {
    const so = stageObjects[id];
    const w = so && so.mesh;
    if (!w) continue;
    w.updateMatrixWorld(true);
    teile.push(id, w.id);
    w.traverse(o => {
      if (!o.isMesh) return;
      teile.push(o.id, o.visible ? 1 : 0, o.geometry ? o.geometry.id : -1,
                 o.material && !Array.isArray(o.material) ? o.material.id : -1,
                 o.material && !Array.isArray(o.material) ? _matSchluessel(o.material) : '',
                 o.castShadow ? 1 : 0, o.receiveShadow ? 1 : 0);
      const e = o.matrixWorld.elements;
      for (let i = 0; i < 16; i++) teile.push(e[i]);
    });
  }
  return teile.join('|');
}

function _aufloesen() {
  for (const k of _koerper) {
    scene.remove(k);
    if (k.geometry) k.geometry.dispose();   // Material gehoert dem Original
  }
  _koerper = [];
  for (const w of _versteckt) w.visible = true;
  _versteckt = [];
}

const _n3 = new THREE.Matrix3();
const _v = new THREE.Vector3();

// Positionen/Normalen aller Teile in Weltkoordinaten in EINE Geometrie.
function _verschmelzen(meshes) {
  let n = 0;
  for (const o of meshes) {
    const g = o.geometry;
    n += g.index ? g.index.count : g.attributes.position.count;
  }
  const pos = new Float32Array(n * 3);
  const nor = new Float32Array(n * 3);
  let ohneNormalen = false;
  let k = 0;
  for (const o of meshes) {
    const g = o.geometry;
    const P = g.attributes.position;
    const N = g.attributes.normal;
    if (!N) ohneNormalen = true;
    const idx = g.index;
    const anzahl = idx ? idx.count : P.count;
    const m = o.matrixWorld;
    _n3.getNormalMatrix(m);
    // Gespiegelte Matrix dreht den Umlaufsinn — Dreieck umsortieren.
    const spiegel = m.determinant() < 0;
    for (let i = 0; i < anzahl; i++) {
      let j = i;
      if (spiegel) { const r = i % 3; if (r === 1) j = i + 1; else if (r === 2) j = i - 1; }
      const q = idx ? idx.getX(j) : j;
      _v.fromBufferAttribute(P, q).applyMatrix4(m);
      pos[k * 3] = _v.x; pos[k * 3 + 1] = _v.y; pos[k * 3 + 2] = _v.z;
      if (N) {
        _v.fromBufferAttribute(N, q).applyMatrix3(_n3).normalize();
        nor[k * 3] = _v.x; nor[k * 3 + 1] = _v.y; nor[k * 3 + 2] = _v.z;
      }
      k += 1;
    }
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  geo.setAttribute('normal', new THREE.Float32BufferAttribute(nor, 3));
  if (ohneNormalen) geo.computeVertexNormals();
  geo.computeBoundingBox();
  geo.computeBoundingSphere();
  return geo;
}

function _zusammenfassen() {
  // Ein Objekt wird nur zusammengefasst, wenn ALLE seine sichtbaren Meshes
  // tauglich sind — sonst bliebe ein halbes Objekt doppelt stehen.
  const gruppen = new Map();   // schluessel -> {material, cast, receive, meshes}
  for (const id of Object.keys(stageObjects).sort()) {
    const so = stageObjects[id];
    const w = so && so.mesh;
    if (!w || !w.visible) continue;
    const teile = [];
    let ok = true;
    w.traverse(o => {
      if (!ok || !o.isMesh || !_sichtbarKette(o, w)) return;
      if (!_tauglich(o)) ok = false; else teile.push(o);
    });
    if (!ok || !teile.length) continue;
    for (const o of teile) {
      const s = _matSchluessel(o.material) + '#' + (o.castShadow ? 1 : 0) + (o.receiveShadow ? 1 : 0);
      let gr = gruppen.get(s);
      if (!gr) {
        gr = { material: o.material, cast: o.castShadow, receive: o.receiveShadow, meshes: [] };
        gruppen.set(s, gr);
      }
      gr.meshes.push(o);
    }
    _versteckt.push(w);
  }
  for (const gr of gruppen.values()) {
    const k = new THREE.Mesh(_verschmelzen(gr.meshes), gr.material);
    k.castShadow = gr.cast;
    k.receiveShadow = gr.receive;
    k.matrixAutoUpdate = false;           // Welt-Koordinaten stehen in der Geometrie
    k.userData.umgebungKoerper = true;
    k.userData.excludeFromFit = true;     // Fit misst weiter die Originale
    k.raycast = () => {};                 // nie pickbar — die Originale sind es
    scene.add(k);
    _koerper.push(k);
  }
  for (const w of _versteckt) w.visible = false;
  _neubauten += 1;
}

/** Vor JEDEM Bild (app.js#renderFrame). Liefert true, wenn sich etwas tat. */
export function syncUmgebung() {
  if (!umgebungZusammenfassen()) {
    if (_koerper.length || _versteckt.length) { _aufloesen(); _sig = null; return true; }
    _sig = null;
    return false;
  }
  // Die Originale sind waehrend des Zusammenfassens unsichtbar; fuer die
  // Signatur zaehlt ihre Sichtbarkeit deshalb kurz wie vorher.
  for (const w of _versteckt) w.visible = true;
  const sig = _signatur();
  for (const w of _versteckt) w.visible = false;
  if (sig === _sig) return false;
  _aufloesen();
  _zusammenfassen();
  _sig = sig;
  return true;
}

/** Test-/Diagnose-Seam. */
export function umgebungInfo() {
  return {
    aktiv: _koerper.length > 0,
    koerper: _koerper.length,
    objekteZusammengefasst: _versteckt.length,
    objekteGesamt: Object.keys(stageObjects).length,
    neubauten: _neubauten,
  };
}
