// VIZ-14 (Plan §3 "Drag&Drop + Ghost-Preview, Auto-Hang auf Truss"): der
// Platzier-Geist.
//
// Bisher war das Platzieren blind: Rechtsklick in die Szene setzt das naechste
// noch unplatzierte Geraet an diese Stelle — man sah WEDER wo es landet, NOCH
// ob es an einer Traverse haengen wird, NOCH ueberhaupt, dass gerade etwas zu
// platzieren ist. Der Geist zeigt alle drei Dinge, bevor geklickt wird.
//
// Bewusst ein Leaf-Modul: es kennt weder Docking noch Raycasting. Der Aufrufer
// (pointer.js) rechnet Bodenpunkt und Andock-Ziel ohnehin schon aus — haette
// dieses Modul sie selbst geholt, waere daraus ein Import-Zyklus geworden UND
// eine zweite Quelle fuer dieselbe Rechnung (die Drift-Falle aus FM16E).

import * as THREE from '../three/three.js';
import { scene } from '../scene/renderer.js';
import { requestRender } from '../scene/render_loop.js';

let geist = null;
let offen = 0;          // wie viele Geraete warten auf einen Platz?
// VIZ-14 Drag-Haelfte: waehrend eines laufenden Drags soll der Geist AUCH dann
// erscheinen, wenn nichts mehr „offen" ist — wer ein bereits platziertes Geraet
// zieht, verschiebt es, und auch dafuer will man vorher sehen, wo es landet.
let ziehen = false;
let zuletzt = null;     // letzte Pose — spart Render-Anstoesse bei Stillstand

function _noop() { /* faengt keine Eingabe: der Geist darf den Klick nicht schlucken */ }

function bauen() {
  if (geist) return;
  const g = new THREE.Group();
  // Koerper: schlichter Quader in der Groessenordnung eines Scheinwerfers.
  const koerper = new THREE.Mesh(
    new THREE.BoxGeometry(0.35, 0.45, 0.35),
    new THREE.MeshBasicMaterial({ color: 0x66ccff, transparent: true, opacity: 0.45 }));
  g.add(koerper);
  // Lotlinie zum Boden: ohne sie ist im 3D nicht zu sehen, WO unten ist.
  const lot = new THREE.Line(
    new THREE.BufferGeometry().setFromPoints(
      [new THREE.Vector3(0, 0, 0), new THREE.Vector3(0, -20, 0)]),
    new THREE.LineBasicMaterial({ color: 0x66ccff, transparent: true, opacity: 0.35 }));
  lot.raycast = _noop;          // dekorative Linie, s. VIZ-13-Regel
  g.add(lot);
  // Bodenmarke: der Fussabdruck, auf den geklickt wird.
  const marke = new THREE.Mesh(
    new THREE.RingGeometry(0.28, 0.38, 24),
    new THREE.MeshBasicMaterial({ color: 0x66ccff, transparent: true, opacity: 0.5,
                                  side: THREE.DoubleSide }));
  marke.rotation.x = -Math.PI / 2;
  marke.name = 'ghost-marke';
  g.add(marke);
  g.traverse(o => { o.raycast = _noop; });
  g.userData.isPlaceGhost = true;
  g.visible = false;
  geist = g;
  scene.add(g);
}

/** Wie viele Geraete warten auf einen Platz? 0 = kein Geist. */
export function setPlaceableCount(n) {
  const neu = Math.max(0, parseInt(n, 10) || 0);
  if (neu === offen) return;
  offen = neu;
  if (!offen) hidePlaceGhost();
}

export function placeGhostArmed() { return offen > 0; }

/** Drag laeuft (an) / ist vorbei (aus). Scharf ist der Geist bei OFFEN oder ZIEHEN. */
export function setDragArmed(an) {
  const neu = !!an;
  if (neu === ziehen) return;
  ziehen = neu;
  if (!ziehen && !offen) hidePlaceGhost();
}

/** Geist an Position setzen. ``angedockt`` faerbt ihn um (Auto-Hang sichtbar). */
export function updatePlaceGhost(x, y, z, angedockt) {
  if (!offen && !ziehen) { hidePlaceGhost(); return; }
  bauen();
  const schluessel = `${x.toFixed(2)}|${y.toFixed(2)}|${z.toFixed(2)}|${!!angedockt}`;
  const sichtbarVorher = geist.visible;
  geist.position.set(x, y, z);
  geist.visible = true;
  // Andock-Farbe: gruen = haengt gleich an der Traverse, blau = freier Platz.
  const farbe = angedockt ? 0x66ff99 : 0x66ccff;
  geist.traverse(o => { if (o.material && o.material.color) o.material.color.setHex(farbe); });
  const marke = geist.getObjectByName('ghost-marke');
  if (marke) marke.position.y = -y;      // Marke bleibt am Boden
  if (schluessel !== zuletzt || !sichtbarVorher) {
    zuletzt = schluessel;
    requestRender();                     // nur bei echter Aenderung
  }
}

export function hidePlaceGhost() {
  if (!geist || !geist.visible) return;
  geist.visible = false;
  zuletzt = null;
  requestRender();
}

/** Test-Seam: Zustand des Geistes ohne Pixel zu deuten.
 *
 * ``raycastTreffer`` ist der ECHTE Beleg dafuer, dass der Geist keine Eingabe
 * faengt: ein Strahl von schraeg oben mitten durch ihn. Steht hier >0, schluckt
 * ausgerechnet die Vorschau den Klick, der platzieren soll. Eine Selbstauskunft
 * ("raycast ist ein No-Op") waere kein Beleg — der Strahl ist einer.
 */
export function placeGhostInfo() {
  if (!geist) return { vorhanden: false, sichtbar: false, offen, ziehen,
                       raycastTreffer: -1 };
  const m = geist.children[0] && geist.children[0].material;
  let treffer = -2;
  try {
    const rc = new THREE.Raycaster();
    rc.set(new THREE.Vector3(geist.position.x, geist.position.y + 5, geist.position.z),
           new THREE.Vector3(0, -1, 0));
    treffer = rc.intersectObject(geist, true).length;
  } catch (e) { treffer = -2; }
  return {
    vorhanden: true, sichtbar: !!geist.visible, offen, ziehen,
    x: geist.position.x, y: geist.position.y, z: geist.position.z,
    farbe: m && m.color ? m.color.getHex() : null,
    raycastTreffer: treffer,
  };
}
