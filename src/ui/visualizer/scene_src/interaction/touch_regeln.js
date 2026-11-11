// UI-115 (Touch-Audit D-03/D-06): reine Regeln fuer den Finger in der
// 3D-Ansicht — ohne Abhaengigkeiten, damit sie sich ohne GPU/Browser pruefen
// lassen (tests/test_ui115_flaechen_touch.py ueber node).

// D-03: Langes Druecken platziert ein Geraet nur im Modus „Bearbeiten“ und
// nur auf freier Flaeche (kein Geraet, kein Buehnenelement unter dem Finger).
// Im Modus „Ansehen“ (und „Bühne“) tut langes Druecken nichts.
export function langDruckPlatziert(editMode, ueberLeer) {
  return editMode === 'edit' && !!ueberLeer;
}

// D-06: Ein Finger auf leerer Flaeche im Modus „Bearbeiten“ dreht (3D) bzw.
// verschiebt (2D) die Kamera — der Auswahlrahmen bleibt der Maus vorbehalten.
export function leerZiehenRahmen(touch) {
  return !touch;
}
