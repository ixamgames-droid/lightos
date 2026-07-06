"""SelectAllSpinBox — QSpinBox, die beim Fokussieren den ganzen Inhalt markiert.

UXT-11a: In den Standard-QSpinBoxen setzt ein Klick/Tab den Cursor ans Ende,
ohne den Wert zu markieren. Tippt der Nutzer dann eine Zahl, hängt sie an den
alten Wert an (aus „1" + „2" wird „12") statt ihn zu ersetzen. Diese Variante
markiert bei Fokus den gesamten Inhalt, sodass das erste Eintippen den Wert
überschreibt — das erwartete Verhalten für kurze Zahlenfelder.
"""
from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QSpinBox


class SelectAllSpinBox(QSpinBox):
    def focusInEvent(self, event):  # noqa: N802 (Qt-API)
        super().focusInEvent(event)
        # Verzögert (0 ms): Qt positioniert den Cursor erst NACH focusInEvent,
        # ein direktes selectAll() würde sofort wieder aufgehoben. Der Timer ist
        # kurzlebig (feuert im nächsten Event-Loop-Durchlauf) → kein GC-Pin.
        QTimer.singleShot(0, self.selectAll)
