"""UI-116: Umschalter „Mehrfach“ — Mehrfachauswahl am Finger.

Touch-Audit 11.11.2026, Befunde A-06 (Bibliothek, Programmer-Geraeteliste)
und C-05 (Editor-Listen). Am Finger gibt es kein Strg-/Umschalt-Klick: jeder
Tipp ersetzte die Auswahl, „Chase +“ aus mehreren Snaps oder Luecken wie
„Geraet 1, 3, 5“ waren nicht erreichbar.

Der Knopf steht neben der Liste und ist **nur im Touch-Modus sichtbar**
(``is_touch_mode()``) — mit der Maus bleibt alles wie bisher (Strg/Umschalt).
Eingeschaltet stellt er die Liste(n) auf ``MultiSelection``: jeder Tipp
schaltet genau die angetippte Zeile um, die uebrigen bleiben gewaehlt.
Ausgeschaltet gilt wieder der bisherige Auswahlmodus, die Auswahl bleibt
stehen. Wischen scrollt weiter (UI-110 haelt den Druck in Listen zurueck,
ein Tipp wird erst beim Loslassen nachgereicht); langes Druecken oeffnet wie
bisher das Kontextmenue (UI-114) und aendert die Auswahl nicht.
"""
from __future__ import annotations

from PySide6.QtWidgets import QAbstractItemView, QPushButton

#: Mindesthoehe am Finger (Richtwert des Touch-Audits, wie die Qt-Knoepfe mit --touch)
TOUCH_HOEHE = 44
TEXT_AUS = "Mehrfach"
TEXT_AN = "Mehrfach ✓"
_MEHRFACH = QAbstractItemView.SelectionMode.MultiSelection


def _touch() -> bool:
    try:
        from src.ui.touch_keyboard import is_touch_mode
        return bool(is_touch_mode())
    except Exception:
        return False


class MehrfachKnopf(QPushButton):
    """Umschalter fuer die Mehrfachauswahl am Finger in ``listen``."""

    def __init__(self, *listen: QAbstractItemView, parent=None, touch: bool | None = None):
        super().__init__(TEXT_AUS, parent)
        self.setObjectName("mehrfachKnopf")
        self.setCheckable(True)
        self.setToolTip(
            "Mehrfachauswahl am Finger: eingeschaltet wählt jeder Tipp eine "
            "Zeile dazu oder ab (statt die Auswahl zu ersetzen).")
        self._listen: list[QAbstractItemView] = []
        self._modus: dict[int, QAbstractItemView.SelectionMode] = {}
        for liste in listen:
            self.liste_dazu(liste)
        fm = self.fontMetrics()
        self.setMinimumHeight(max(TOUCH_HOEHE, fm.height() + 12))
        self.setMinimumWidth(max(TOUCH_HOEHE, fm.horizontalAdvance(TEXT_AN) + 28))
        self.toggled.connect(self._umschalten)
        if not (_touch() if touch is None else touch):
            # Maus: unsichtbar (vor dem Einhaengen versteckt — ein Layout
            # zeigt ein ausdruecklich verstecktes Widget nicht wieder).
            self.setHidden(True)

    def liste_dazu(self, liste: QAbstractItemView) -> None:
        self._listen.append(liste)
        self._modus[id(liste)] = liste.selectionMode()
        if self.isChecked():
            liste.setSelectionMode(_MEHRFACH)

    def _umschalten(self, an: bool) -> None:
        self.setText(TEXT_AN if an else TEXT_AUS)
        for liste in self._listen:
            try:
                liste.setSelectionMode(_MEHRFACH if an else self._modus[id(liste)])
            except RuntimeError:
                pass        # Liste schon zerstoert (Neuaufbau der Ansicht)
