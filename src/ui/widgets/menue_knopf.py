"""STAB-33: ``QPushButton``, der ein Menue aufklappt — ohne Qts eingebauten Pfeil.

Warum nicht ``QPushButton.setMenu``: sobald ein ``QPushButton`` ein Menue traegt,
fragt Qt den Stil nach der Breite des Menue-Pfeils (``PM_MenuButtonIndicator``).
Das Theme setzt Schriften in Pixeln (``font-size: 12px``), der Knopf hat dann
``font().pointSize() == -1`` — und Qts Windows-11-Stil rechnet die Pfeilbreite
genau daraus (``setPointSize(qRound(pointSize * 0.9))``). Folge auf jedem
Windows-Rechner beim Start::

    QFont::setPointSize: Point size <= 0 (-1), must be greater than 0

Eine feste Pfeilgroesse im Stylesheet stillt nur die Groessenberechnung; beim
Zeichnen fragt ``QStyleSheetStyle`` den Basis-Stil trotzdem. Unsere Knoepfe
tragen den Pfeil ohnehin als "▾" im Text — der eingebaute war doppelt.

Dieser Knopf merkt sich das Menue selbst und klappt es beim Klick unter sich
auf. ``menu()``/``setMenu()``/``showMenu()`` bleiben als Schnittstelle erhalten.
"""
from __future__ import annotations

from PySide6.QtWidgets import QMenu, QPushButton


class MenueKnopf(QPushButton):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._menue: QMenu | None = None
        self.clicked.connect(self.showMenu)

    def setMenu(self, menu: QMenu | None) -> None:   # noqa: N802 — Qt-Name
        """Bewusst NICHT an Qt weitergereicht (kein eingebauter Pfeil)."""
        self._menue = menu

    def menu(self) -> QMenu | None:
        return self._menue

    def showMenu(self, *_args) -> None:              # noqa: N802 — Qt-Name
        menu = self._menue
        if menu is None or not self.isEnabled():
            return
        menu.popup(self.mapToGlobal(self.rect().bottomLeft()))
