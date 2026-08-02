// VIZ-14 (Plan §4/Phase 4, Punkt 2): das GEZOGENE Geraet landet dort, wo man
// es fallen laesst — die Drag-Haelfte zur schon gebauten Ghost-Vorschau.
//
// Bisher ging Platzieren nur per Rechtsklick, und der setzte „das naechste noch
// unplatzierte Geraet". Welches das ist, stand nirgends — man platzierte blind
// und sortierte hinterher. Der Plan verlangt ausdruecklich: „Klick-Platzierung
// nur fuer das in der Liste selektierte Geraet (nie blind das naechste)".
//
// ★ WARUM HTML5-DRAG UND NICHT DIE BRUECKE: gemessen, bevor gebaut wurde — ein
//   Qt-Drag auf die QWebEngineView kommt in der Seite als ECHTES
//   dragenter/dragover/drop an, samt `text/plain`-Nutzlast. Damit folgt der
//   Geist im vollen Ereignistakt des Zeigers. Haette man die Koordinaten
//   stattdessen ueber den Poll der Bruecke geschickt, ruckelte die Vorschau im
//   Poll-Intervall — sichtbar genau bei der Bewegung, um die es geht.
//
// ★ NUR IM BAUEN-MODUS: ausserhalb wird `preventDefault` NICHT gerufen. Dann
//   zeigt der Zeiger von selbst „hier kann man nicht ablegen" — ehrlicher als
//   ein Drop, der still nichts tut, und ehrlicher als heimlich in den
//   Bauen-Modus zu schalten (der Modus gehoert dem Nutzer, s. VIZ-14-Maschine).

import { view } from '../state.js';
import { updatePlaceGhost, hidePlaceGhost, setDragArmed } from './place_ghost.js';

// Nutzlast-Format der Qt-Liste. Bewusst `text/plain` mit Praefix: das ist der
// einzige Typ, den die Bruecke Qt->Seite verlaesslich durchreicht, und das
// Praefix trennt unseren Drag von beliebigem Text, den jemand hineinzieht.
const PRAEFIX = 'lightos-fixture:';

let _haenger = null;      // { intersectGround, snap, findDockTarget, settings, bridge }
let _letzteFid = null;    // fid des laufenden Drags (fuer den Drop)

/** Rechen-Haenger nachreichen (Spaet-Bindung wie bei den anderen Interaktionen).
 *
 * Dieses Modul rechnet NICHTS selbst: Bodenpunkt, Raster und Andock-Ziel kommen
 * aus `pointer.js`, das sie ohnehin schon bestimmt. Eine zweite Rechnung hier
 * waere die Drift-Quelle aus FM16E.
 */
export function setDragHelpers(h) { _haenger = h; }

export function parseFixturePayload(text) {
  if (typeof text !== 'string' || !text.startsWith(PRAEFIX)) return null;
  const roh = text.slice(PRAEFIX.length).trim();
  if (!/^\d+$/.test(roh)) return null;
  return parseInt(roh, 10);
}

/** Darf hier ueberhaupt abgelegt werden? */
export function dropAllowed() {
  return view.editMode === 'edit' && view.mode === '3D';
}

/** Zielpose unter dem Zeiger — oder null, wenn dort kein Boden ist. */
function _pose(clientX, clientY) {
  if (!_haenger) return null;
  _haenger.setMouseFromCoords(clientX, clientY);
  const treffer = _haenger.intersectGround();
  if (!treffer) return null;
  const x = _haenger.snap(treffer.x);
  const z = _haenger.snap(treffer.z);
  let y = 6.5, dock = '';
  if (_haenger.settings && _haenger.settings.dockEnabled) {
    const ziel = _haenger.findDockTarget(x, z);
    if (ziel) { y = ziel.y; dock = ziel.stageId || ''; }
  }
  return { x, y, z, dock };
}

function _onDragOver(e) {
  const fid = parseFixturePayload(
    (e.dataTransfer && e.dataTransfer.getData('text/plain')) || '');
  // Waehrend des Ziehens liefern manche Browser die Nutzlast aus Datenschutz-
  // gruenden NICHT (nur beim Drop). Der Geist soll trotzdem laufen — deshalb
  // reicht hier, DASS gezogen wird; die fid entscheidet erst der Drop.
  if (!dropAllowed()) return;          // kein preventDefault -> Zeiger sagt nein
  e.preventDefault();
  setDragArmed(true);                  // auch ein Verschieben zeigt den Geist
  if (fid !== null) _letzteFid = fid;
  const p = _pose(e.clientX, e.clientY);
  if (p) updatePlaceGhost(p.x, p.y, p.z, !!p.dock);
  else hidePlaceGhost();
}

function _onDragLeave() { setDragArmed(false); hidePlaceGhost(); }

function _onDrop(e) {
  setDragArmed(false);
  hidePlaceGhost();
  if (!dropAllowed()) return;
  e.preventDefault();
  const text = (e.dataTransfer && e.dataTransfer.getData('text/plain')) || '';
  const fid = parseFixturePayload(text);
  const ziel = (fid !== null) ? fid : _letzteFid;
  _letzteFid = null;
  if (ziel === null || ziel === undefined) return;
  const p = _pose(e.clientX, e.clientY);
  if (!p) return;
  const bridge = _haenger && _haenger.bridge && _haenger.bridge();
  if (bridge && bridge.placeFixture) {
    bridge.placeFixture(JSON.stringify(
      { x: p.x, y: p.y, z: p.z, dock: p.dock, fid: ziel }));
  }
}

export function installDragDrop(target) {
  const t = target || window;
  t.addEventListener('dragenter', e => { if (dropAllowed()) e.preventDefault(); });
  t.addEventListener('dragover', _onDragOver);
  t.addEventListener('dragleave', _onDragLeave);
  t.addEventListener('drop', _onDrop);
}

/** Test-Seam: welches Geraet wuerde ein Drop gerade platzieren? */
export function pendingDragFid() { return _letzteFid; }
