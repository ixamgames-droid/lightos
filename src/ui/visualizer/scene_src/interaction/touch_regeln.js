// UI-115 (Touch-Audit D-03/D-06): reine Regeln fuer den Finger in der
// 3D-Ansicht — ohne Abhaengigkeiten, damit sie sich ohne GPU/Browser pruefen
// lassen (tests/test_ui115_flaechen_touch.py ueber node).

// D-03: Langes Druecken platziert ein Geraet nur im Modus „Bearbeiten“ und
// nur, wenn kein Geraet unter dem Finger liegt. Traversen und Podeste sind
// erlaubte Ziele — dort dockt das Geraet an (findDockTarget), genau wie beim
// Rechtsklick der Maus. Gesperrt bleibt der Griff eines Gizmos bzw. einer
// Groessen-Ecke (dragMode 'gizmoDrag' / 'stageResize'). Ein Element-Zug, der
// sich schon bewegt hat, kommt hier nie an: touchmove bricht den Timer ab.
// Im Modus „Ansehen“ (und „Bühne“) tut langes Druecken nichts.
const _GESPERRTE_ZUEGE = ['gizmoDrag', 'stageResize'];
export function langDruckPlatziert(editMode, keinGeraet, dragMode = 'none') {
  return editMode === 'edit' && !!keinGeraet &&
         !_GESPERRTE_ZUEGE.includes(dragMode);
}

// D-06: Ein Finger auf leerer Flaeche im Modus „Bearbeiten“ dreht (3D) bzw.
// verschiebt (2D) die Kamera — der Auswahlrahmen bleibt der Maus vorbehalten.
export function leerZiehenRahmen(touch) {
  return !touch;
}

// UI-123 (Touch-Audit D-13): Geraetename am Finger. Mit der Maus zeigt das
// Verweilen ueber einem Geraet Name und Position (Tooltip); am Finger gibt
// es kein Verweilen. Jetzt: ein Tipp (ein Finger, kaum bewegt, kein
// Platzieren per langem Druck) auf ein Geraet zeigt dasselbe Schild
// TIPP_NAME_MS lang ueber dem Finger. Ein neuer Tipp oder die Maus ersetzt es.
export const TIPP_NAME_MS = 2500;
export const TIPP_WEG_PX = 12;      // so weit darf der Finger beim Tipp wandern

export function tippZeigtName(wegPx, zweiFinger, platziert) {
  return !zweiFinger && !platziert && wegPx <= TIPP_WEG_PX;
}

// Derselbe Text wie beim Maus-Tooltip (eine Quelle fuer beide).
export function geraeteText(fid, label, typ, x, y, z) {
  return '[' + fid + '] ' + (label || '?') + ' - ' + typ +
    '  (X:' + x.toFixed(1) + ' Y:' + y.toFixed(1) + ' Z:' + z.toFixed(1) + ')';
}

// Lage des Schilds: mittig UEBER dem Finger (der verdeckt sonst den Text),
// am Fensterrand gehalten; oben kein Platz -> unter den Finger.
export function tippLage(fx, fy, breite, hoehe, fensterB, fensterH) {
  const abstand = 28;
  let x = fx - breite / 2;
  let y = fy - hoehe - abstand;
  if (y < 4) y = fy + abstand;
  x = Math.max(4, Math.min(x, fensterB - breite - 4));
  y = Math.max(4, Math.min(y, fensterH - hoehe - 4));
  return { x: Math.round(x), y: Math.round(y) };
}
