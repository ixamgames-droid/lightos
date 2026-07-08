"""LocaleTolerantDoubleSpinBox — QDoubleSpinBox, das Punkt UND Komma als
Dezimaltrenner akzeptiert.

VIZ-FIX-DECIMAL: In den 3D-Panel-Zahlenfeldern („Position & Ausrichtung",
Stage-Größe, Raster) ist eine Standard-`QDoubleSpinBox` an das System-Locale
gebunden. Auf deutschem Locale erwartet sie das Komma als Dezimaltrenner; tippt
der Nutzer „5.7" mit Punkt, ist die Eingabe ungültig und wird verworfen/geklemmt
(z. B. auf den Minimalwert oder den Ganzzahl-Anteil) — stiller Datenverlust.

Diese Variante läuft intern auf C-Locale (Punkt = Dezimaltrenner, kein Punkt als
Tausender-Gruppierung) und normalisiert Komma→Punkt beim Validieren und beim
Auslesen. Damit werden BEIDE Schreibweisen (`5.7` und `5,7`) korrekt als 5.7
übernommen. Der getippte Text bleibt in der Anzeige unverändert (die Validierung
bewertet nur eine normalisierte Kopie), erst beim Commit wird der Wert geparst.
"""
from __future__ import annotations

from PySide6.QtCore import QLocale
from PySide6.QtWidgets import QDoubleSpinBox


class LocaleTolerantDoubleSpinBox(QDoubleSpinBox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # C-Locale: '.' ist Dezimaltrenner und wird NICHT als Tausender-Gruppierung
        # gedeutet. Komma fangen validate()/valueFromText() zusätzlich ab.
        self.setLocale(QLocale(QLocale.Language.C))

    def validate(self, text: str, pos: int):  # noqa: N802 (Qt-API)
        # Akzeptanz aus der normalisierten Kopie bestimmen (damit ein getipptes
        # Komma als gültig gilt), aber den ORIGINAL-Text/-Cursor zurückgeben, damit
        # die Anzeige nicht mitten im Tippen umspringt.
        state, _norm, _p = super().validate(text.replace(",", "."), pos)
        return state, text, pos

    def valueFromText(self, text: str) -> float:  # noqa: N802 (Qt-API)
        return super().valueFromText(text.replace(",", "."))
