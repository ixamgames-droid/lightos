// VIZ-66: Geteilte, im Code erzeugte Geometrie fuer Geraete- und Buehnenmodelle.
//
// LightOS liefert keine fremden 3D-Modelldateien mehr mit (bis VIZ-66 lagen hier
// 19 Dateien aus QLC+). Die Koerper entstehen stattdessen aus three.js-
// Grundkoerpern. Damit das nicht je Geraet neu gerechnet wird, legt dieses Modul
// jede Form EINMAL an und gibt danach dieselbe BufferGeometry heraus — zwanzig
// PARs teilen sich ein Gehaeuse, nur das Material (Farbe/Emissive) bleibt je
// Geraet eigen.
//
// ★ Die Falle dabei: `disposeObj` (grid_floor.js) gibt beim Entfernen eines
// Geraets bzw. beim Groessenwechsel eines Buehnenobjekts die Geometrie frei. Bei
// geteilter Geometrie traefe das alle anderen Nutzer mit — three laedt die
// Puffer dann beim naechsten Bild zwar neu hoch, aber jedes Loeschen kostete
// einen Upload fuer alle. Deshalb traegt jede Geometrie von hier die Marke
// `userData.geteilt`, und `disposeObj` laesst sie in Ruhe.
import * as THREE from '../three/three.js';

const _cache = new Map();

/**
 * Geometrie unter `schluessel` aus dem Cache, sonst einmal mit `bauen()` anlegen.
 * Der Schluessel muss alles enthalten, was die Form aendert (Masse, Segmente).
 */
export function geteilteGeometrie(schluessel, bauen) {
  let g = _cache.get(schluessel);
  if (!g) {
    g = bauen();
    g.userData.geteilt = true;
    g.userData.schluessel = schluessel;
    g.computeBoundingBox();
    g.computeBoundingSphere();
    _cache.set(schluessel, g);
  }
  return g;
}

/** Anzahl gecachter Formen (Test-Seam: Teilen statt Neubauen ist pruefbar). */
export function geteilteGeometrieAnzahl() {
  return _cache.size;
}

const _m = new THREE.Matrix4();
const _q = new THREE.Quaternion();
const _s = new THREE.Vector3(1, 1, 1);
const _p = new THREE.Vector3();
const _e = new THREE.Euler();

/**
 * Teil-Geometrie an Ort und Stelle verschieben/drehen/strecken.
 * `pos` [x,y,z], `rot` [x,y,z] in Radiant, `skal` [x,y,z] — alles optional.
 */
export function platziere(geo, pos, rot, skal) {
  _p.set(...(pos || [0, 0, 0]));
  _e.set(...(rot || [0, 0, 0]));
  _q.setFromEuler(_e);
  _s.set(...(skal || [1, 1, 1]));
  _m.compose(_p, _q, _s);
  geo.applyMatrix4(_m);
  return geo;
}

const _oben = new THREE.Vector3(0, 1, 0);
const _a = new THREE.Vector3();
const _b = new THREE.Vector3();
const _d = new THREE.Vector3();

/**
 * Rohr (Zylinder) von Punkt `a` nach Punkt `b`. Fuer Traversen-Gurte und
 * -Streben; `offen` spart die Deckel, wo sie ohnehin im Gurt stecken.
 */
export function rohr(a, b, radius, radial, offen) {
  _a.set(...a); _b.set(...b);
  _d.subVectors(_b, _a);
  const laenge = _d.length();
  const geo = new THREE.CylinderGeometry(radius, radius, laenge, radial, 1, !!offen);
  _q.setFromUnitVectors(_oben, _d.normalize());
  _p.addVectors(_a, _b).multiplyScalar(0.5);
  _m.compose(_p, _q, _s.set(1, 1, 1));
  geo.applyMatrix4(_m);
  return geo;
}

/**
 * Mehrere Teil-Geometrien zu EINER zusammenfuegen (ein Drawcall, ein Material).
 * Nur Position + Normale — die Modelle sind untexturiert. Indizierte Teile
 * werden vorher entfaltet; die Teile selbst werden danach freigegeben.
 */
export function verschmelzen(teile) {
  let n = 0;
  const flach = teile.map((t) => {
    const f = t.index ? t.toNonIndexed() : t;
    if (f !== t) t.dispose();
    n += f.attributes.position.count;
    return f;
  });
  const pos = new Float32Array(n * 3);
  const nor = new Float32Array(n * 3);
  let o = 0;
  for (const f of flach) {
    pos.set(f.attributes.position.array, o * 3);
    if (f.attributes.normal) nor.set(f.attributes.normal.array, o * 3);
    o += f.attributes.position.count;
    f.dispose();
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute('normal', new THREE.Float32BufferAttribute(nor, 3));
  return g;
}
