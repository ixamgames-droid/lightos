// VIZ-14 (Plan §3 "Raum-Box statt Void"): eine neutrale, abschaltbare Raum-Huelle.
//
// ★ WARUM DAS EIN WIDERSPRUCH WAR — und wie er aufgeloest ist:
// Der Plan fuehrt "Raum-Box statt Void" als *Hoch* (MagicVis, Easy View), im
// Code stand aber ausdruecklich das Gegenteil: die vorgerenderten Kulissen
// (theatre/rock/box) wurden BEWUSST entfernt, der Visualizer startet leer und
// der Nutzer baut seine Buehne selbst. David hat 2026-07-31 entschieden:
// **neutrale Huelle, abschaltbar** — Waende und Decke als reine Orientierung,
// KEIN Buehnenbild, KEINE Deko, Default AUS. Damit kommt nichts von dem
// zurueck, was damals absichtlich rausflog.
//
// Drei Eigenschaften, die das von einer Kulisse unterscheiden:
//  1. Sie traegt keine Information — eine Flaeche, eine Farbe, kein Muster.
//  2. Sie faengt keine Eingabe (`raycast = noop`): weder Klick noch Marquee
//     noch das Zielen-Werkzeug duerfen an einer Wand haengen bleiben. Die
//     Boden-Ebene (`intersectGround`) bleibt die einzige Zielflaeche.
//  3. Sie waechst mit dem Inhalt statt eine Raumgroesse zu behaupten: die
//     Huelle wird aus der Ausdehnung von Fixtures + Buehnenobjekten abgeleitet
//     (mit Rand). Eine feste Groesse wuerde bei grossen Rigs mitten durch das
//     Rig schneiden — schlimmer als gar keine Huelle.
//
// In der 2D-Draufsicht bleibt sie aus: die Decke laege genau zwischen Kamera
// und Buehne.

import * as THREE from '../three/three.js';
import { scene } from './renderer.js';
import { fixtures, stageObjects, settings, view } from '../state.js';

const RAND_M = 4.0;       // Luft zwischen Rig und Wand
const MIN_BREITE = 12.0;  // auch eine leere Buehne bekommt einen sichtbaren Raum
const MAX_BREITE = 80.0;  // nicht groesser als der Referenz-Boden
const MIN_HOEHE = 5.0;
const MAX_HOEHE = 20.0;

let huelle = null;

function _noop() { /* faengt keine Eingabe — s. Kopfkommentar Punkt 2 */ }

/** Ausdehnung des tatsaechlichen Inhalts (Fixtures + Buehnenobjekte). */
function inhaltsMasse() {
  let minX = Infinity, maxX = -Infinity, minZ = Infinity, maxZ = -Infinity, maxY = 0;
  const merke = (p) => {
    if (!p) return;
    if (p.x < minX) minX = p.x;
    if (p.x > maxX) maxX = p.x;
    if (p.z < minZ) minZ = p.z;
    if (p.z > maxZ) maxZ = p.z;
    if (p.y > maxY) maxY = p.y;
  };
  for (const fid in fixtures) merke(fixtures[fid].group && fixtures[fid].group.position);
  for (const id in stageObjects) merke(stageObjects[id].mesh && stageObjects[id].mesh.position);
  if (!isFinite(minX)) { minX = maxX = minZ = maxZ = 0; }   // leere Szene

  const breite = Math.min(MAX_BREITE,
    Math.max(MIN_BREITE, (maxX - minX) + 2 * RAND_M));
  const tiefe = Math.min(MAX_BREITE,
    Math.max(MIN_BREITE, (maxZ - minZ) + 2 * RAND_M));
  const hoehe = Math.min(MAX_HOEHE, Math.max(MIN_HOEHE, maxY + RAND_M));
  return {
    breite, tiefe, hoehe,
    mitteX: (minX + maxX) / 2,
    mitteZ: (minZ + maxZ) / 2,
  };
}

function abbauen() {
  if (!huelle) return;
  scene.remove(huelle);
  if (huelle.geometry) huelle.geometry.dispose();
  if (huelle.material) huelle.material.dispose();
  huelle = null;
}

function aufbauen() {
  const m = inhaltsMasse();
  // Von INNEN sichtbar (BackSide) — sonst steht man vor einer schwarzen Kiste.
  const geo = new THREE.BoxGeometry(m.breite, m.hoehe, m.tiefe);
  const mat = new THREE.MeshStandardMaterial({
    color: 0x1e2128, roughness: 0.98, metalness: 0.0,
    side: THREE.BackSide, transparent: true, opacity: 0.55,
  });
  huelle = new THREE.Mesh(geo, mat);
  huelle.position.set(m.mitteX, m.hoehe / 2, m.mitteZ);
  huelle.raycast = _noop;
  huelle.renderOrder = -1;          // hinter allem anderen
  huelle.receiveShadow = false;     // eine Orientierungshilfe wirft/faengt kein Licht
  huelle.castShadow = false;
  huelle.userData.isRoomShell = true;
  scene.add(huelle);
}

/** Huelle an den aktuellen Zustand angleichen (Schalter UND Ansichtsmodus). */
export function syncRoomShell() {
  const gewuenscht = !!settings.showRoom && view.mode === '3D';
  if (!gewuenscht) { abbauen(); return; }
  abbauen();          // neu aufbauen: der Inhalt kann sich geaendert haben
  aufbauen();
}

/** Nur fuer Tests/Diagnose: liegt gerade eine Huelle in der Szene?
 *
 * ``raycastTreffer`` ist der ECHTE Gegenbeweis zu Punkt 2 im Kopfkommentar:
 * ein Strahl aus der Raummitte auf die Wand zu. Faengt die Huelle Eingaben,
 * steht hier >0 und Klicken/Zielen/Marquee waeren im Raum kaputt. Eine
 * Selbstauskunft ("raycast ist ein No-Op") waere kein Beleg — der Strahl ist
 * einer. -2 = die Messung selbst ist gescheitert (dann ist der Test rot, nicht
 * still gruen).
 */
export function roomShellInfo() {
  if (!huelle) return null;
  const p = (huelle.geometry && huelle.geometry.parameters) || {};
  let treffer = -2;
  try {
    const rc = new THREE.Raycaster();
    rc.set(new THREE.Vector3(huelle.position.x, 1.5, huelle.position.z),
           new THREE.Vector3(1, 0, 0));
    treffer = rc.intersectObject(huelle, true).length;
  } catch (e) { treffer = -2; }
  return {
    breite: p.width, hoehe: p.height, tiefe: p.depth,
    x: huelle.position.x, y: huelle.position.y, z: huelle.position.z,
    raycastTreffer: treffer,
  };
}
