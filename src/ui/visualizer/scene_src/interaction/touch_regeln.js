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
