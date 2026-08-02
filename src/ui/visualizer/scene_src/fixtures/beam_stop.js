// VIZ-BEAM-OCCLUSION Teil 2: der Strahl endet am ERSTEN getroffenen Koerper,
// nicht erst am Boden.
//
// Teil 1 (schon drin) laesst den Kegel an der Bodenebene enden — gerechnet aus
// dem Schnittpunkt der Strahlrichtung mit y=0. Das ist richtig, solange nichts
// dazwischensteht. Steht es doch — Podest, DJ-Pult, Boxenstapel, Traverse —
// schiesst der sichtbare Kegel mitten hindurch und endet erst am Boden
// dahinter. Am Rig ist das genau der haeufige Fall: Scheinwerfer stehen ueber
// Buehnenelementen, nicht ueber leerem Boden.
//
// Dieses Modul ist bewusst **importfrei** (kein THREE, kein state) und rechnet
// nur mit Zahlen. Die Strahlenverfolgung selbst bleibt beim Aufrufer, der die
// Szene ohnehin schon hat; hier liegt die Entscheidung, WELCHER Abstand gilt —
// und genau die ist die fehleranfaellige Stelle: `Infinity` bedeutet „nichts
// getroffen" und darf nicht mit „Abstand 0" verwechselt werden.
//
// Dieselbe Bauart wie `optics.js`: ohne Importe ist die Funktion in einem
// Unit-Test direkt aufrufbar, ohne eine 3D-Szene hochzuziehen.

/** Ist das ein brauchbarer, positiver Abstand? */
function gueltig(d) {
  return typeof d === 'number' && isFinite(d) && d > 0;
}

/**
 * Naechster Auftreffpunkt entlang des Strahls.
 *
 * @param {number} bodenAbstand   Abstand bis zur Bodenebene, `Infinity` = nie
 * @param {number} objektAbstand  Abstand bis zum naechsten Buehnenkoerper,
 *                                `Infinity`/`null` = keiner getroffen
 * @returns {number} der kleinere gueltige Abstand, sonst `Infinity`
 *
 * `Infinity` heisst „kein Auftreffpunkt" und wird vom Aufrufer als „behalte die
 * Grundlaenge" gelesen — NICHT als Laenge 0. Ein nach oben gerichteter Kopf
 * trifft weder Boden noch Koerper und muss seinen vollen Kegel behalten.
 */
export function naechsterAuftreffpunkt(bodenAbstand, objektAbstand) {
  const b = gueltig(bodenAbstand) ? bodenAbstand : Infinity;
  const o = gueltig(objektAbstand) ? objektAbstand : Infinity;
  return Math.min(b, o);
}

/**
 * Trifft der Strahl zuerst einen Koerper — und wenn ja, wie weit ueber dem
 * Boden liegt dieser Auftreffpunkt?
 *
 * Der Lichtfleck gehoert auf die Flaeche, die das Licht wirklich abbekommt.
 * Liegt sie auf einem Podest, muss der Fleck dort liegen und nicht auf dem
 * Boden darunter — sonst zeigt die Ansicht Licht an einer Stelle, die im
 * Schatten des Podests liegt.
 *
 * @param {number} bodenAbstand
 * @param {?{abstand:number, y:number}} treffer  naechster Koerper-Treffer
 * @returns {{abstand:number, y:number}} Abstand und Hoehe des Auftreffpunkts
 */
export function auftreffFlaeche(bodenAbstand, treffer) {
  const b = gueltig(bodenAbstand) ? bodenAbstand : Infinity;
  if (treffer && gueltig(treffer.abstand) && treffer.abstand < b) {
    const y = (typeof treffer.y === 'number' && isFinite(treffer.y))
      ? treffer.y : 0;
    return { abstand: treffer.abstand, y: y };
  }
  return { abstand: b, y: 0 };
}
