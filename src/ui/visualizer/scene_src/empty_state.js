// VIZ-14: Empty-State — eine leere Buehne soll wie ein Anfang aussehen,
// nicht wie ein Fehler.
//
// Bisher zeigte der Visualizer bei einer neuen Show nur Grid und Boden. Das ist
// der NORMALZUSTAND, sieht aber aus wie „da fehlt was" — und es sagt nirgends,
// was der naechste Schritt waere. Der Hinweis verschwindet, sobald das erste
// Geraet ODER das erste Buehnenobjekt da ist.
//
// Bewusst ein LEAF-MODUL: es importiert nur `state.js`. `tools.js` importiert
// aus `fixtures.js` und `stage/stage_objects.js`, die beiden also nicht aus
// `tools.js` — genau der Zyklus, den die bestehende Spaet-Bindung
// (`wireFixturesLateBindings`) umschifft. Ein eigenes Leaf-Modul braucht diesen
// Umweg gar nicht erst.
//
// Reines DOM, kein `requestRender`: der Hinweis haengt an keinem Frame und darf
// den On-Demand-Render-Loop nicht wecken (F1-Regel wie beim Modus-Rahmen).

import { fixtures, stageObjects } from './state.js';

/** Ist die Szene inhaltlich leer? (Grid/Boden zaehlen nicht — die sind Kulisse.) */
export function sceneIsEmpty() {
  for (const _ in fixtures) return false;
  for (const _ in stageObjects) return false;
  return true;
}

/** Blendet den Hinweis passend zum Inhalt ein/aus. Idempotent und billig. */
export function updateEmptyState() {
  const el = (typeof document !== 'undefined')
    ? document.getElementById('empty-state') : null;
  if (!el) return;
  const leer = sceneIsEmpty();
  if (el.hidden === !leer) return;      // nichts zu tun -> kein DOM-Schreiben
  el.hidden = !leer;
}
