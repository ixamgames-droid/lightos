"""UI-94: Wann geht die Leertaste an ein Bedienelement statt an GO?

Das Hauptfenster bindet die Leertaste als Fenster-Kuerzel an GO. Knoepfe
(``QAbstractButton``) und nicht editierbare Auswahllisten nehmen den
``ShortcutOverride`` fuer die Leertaste nicht an — ohne diese Regel loeste
die Leertaste deshalb GO aus, auch wenn man per Tabulator auf einen Knopf
gegangen war (Befund am Menueknopf „Tabellen-Import“).

Regel (``hat_vorrang``): Die Leertaste geht an das Element mit Fokus, wenn

* es ein Knopf, Haken, Optionsfeld oder eine Auswahlliste ist,
* es bedienbar (sichtbar, nicht gesperrt) ist und im Fenster liegt und
* der Fokus per TASTATUR dorthin kam (Tabulator). Qt merkt sich das am
  Fenster als ``WA_KeyboardFocusChange`` — dasselbe Merkmal, an dem der Stil
  den Fokusrahmen zeichnet. Ein Mausklick loescht es wieder.

Sonst bleibt die Leertaste GO. Wichtig fuer den Show-Betrieb: ein Knopf, der
nur durch einen Mausklick den Fokus hat, bekommt die Leertaste NICHT —
sonst loeste der zuletzt geklickte Knopf ein zweites Mal aus statt GO.
Umschalt+Leertaste (BACK) ist nicht betroffen. Textfelder nehmen die
Leertaste von sich aus an (Qt), dafuer braucht es hier nichts.
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QAbstractButton, QApplication, QComboBox

_MODS = (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier
         | Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.MetaModifier)


def _bedienelement(w) -> bool:
    if isinstance(w, QAbstractButton):
        return True
    return isinstance(w, QComboBox) and not w.isEditable()


def hat_vorrang(fenster, ev) -> bool:
    """True, wenn die Leertaste dieses ``ShortcutOverride`` an das fokussierte
    Bedienelement gehen soll (das Ereignis ist dann angenommen)."""
    if ev.type() != QEvent.Type.ShortcutOverride:
        return False
    try:
        if ev.key() != Qt.Key.Key_Space or (ev.modifiers() & _MODS):
            return False
        fokus = QApplication.focusWidget()
        if (fokus is None or not _bedienelement(fokus)
                or fokus.window() is not fenster
                or not fokus.isVisible() or not fokus.isEnabled()
                or not fenster.testAttribute(Qt.WidgetAttribute.WA_KeyboardFocusChange)):
            return False
    except RuntimeError:        # Widget schon abgebaut
        return False
    ev.accept()
    return True
