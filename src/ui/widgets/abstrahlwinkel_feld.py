"""FM-64: Eingabefeld „Abstrahlwinkel“ fuer Fixture-Editor und -Generator.

Zwei Zahlen: der Abstrahlwinkel (fester Winkel bzw. bei Zoom der engste)
und optional „bis“ (der weiteste Winkel bei Zoom). Beide 0 = keine Angabe —
dann leitet der 3D-Visualizer den Kegel wie bisher aus Geraetetyp und Zoom
ab. Die Regeln (Klemmen, Tauschen, fest/Spanne) stehen in
``src/core/abstrahlwinkel.py``; dieses Widget zeigt nur an.
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QDoubleSpinBox, QHBoxLayout, QLabel, QWidget

from src.core import abstrahlwinkel as AW

TOOLTIP = (
    "Abstrahlwinkel laut Datenblatt (voller Winkel des Lichtkegels in Grad). "
    "Der 3D-Visualizer zeichnet den Kegel dann in dieser Breite.\n"
    "Hat das Gerät Zoom: links den engsten, rechts („bis“) den weitesten "
    "Winkel eintragen — der Kegel folgt dann dem Zoom-Kanal zwischen beiden.\n"
    "„keine Angabe“ = wie bisher: der Kegel ergibt sich aus Gerätetyp und Zoom.")


class AbstrahlwinkelFeld(QWidget):
    """``[ 25,0° ] bis [ 40,0° ] (Zoom)`` — ``werte()`` = ``(eng, weit)``."""

    geaendert = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.spin_eng = QDoubleSpinBox()
        self.spin_weit = QDoubleSpinBox()
        for sp, leer in ((self.spin_eng, "keine Angabe"),
                         (self.spin_weit, "ohne Zoom")):
            sp.setDecimals(1)
            sp.setRange(0.0, AW.WINKEL_MAX)
            sp.setSingleStep(1.0)
            sp.setSuffix("°")
            # 0 = keine Angabe; unter WINKEL_MIN gibt es keinen Kegel.
            sp.setSpecialValueText(leer)
            sp.setToolTip(TOOLTIP)
            sp.valueChanged.connect(lambda *_: self.geaendert.emit())
        self.spin_eng.setAccessibleName("Abstrahlwinkel")
        self.spin_weit.setAccessibleName("Abstrahlwinkel bis (Zoom)")
        lbl = QLabel("bis")
        lbl.setToolTip(TOOLTIP)
        lay.addWidget(self.spin_eng, 1)
        lay.addWidget(lbl)
        lay.addWidget(self.spin_weit, 1)
        self.setToolTip(TOOLTIP)

    def werte(self) -> tuple[float, float]:
        """``(eng, weit)`` bereinigt; ``(0.0, 0.0)`` = keine Angabe."""
        return AW.normalisiere(self.spin_eng.value(), self.spin_weit.value())

    def setze(self, eng, weit=None) -> None:
        a, b = AW.normalisiere(eng, weit)
        self.spin_eng.setValue(a)
        self.spin_weit.setValue(b if b != a else 0.0)

    def nur_ansehen(self) -> None:
        for sp in (self.spin_eng, self.spin_weit):
            sp.setReadOnly(True)
