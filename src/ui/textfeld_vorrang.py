"""UI-146: Tippen in ein Textfeld loest nie ein Fenster-Kuerzel aus.

Das Hauptfenster legt einzelne Buchstaben und Zeichen als Kuerzel an
(H = Highlight, Umschalt+H = Lowlight, R, ":" = Befehlszeile, Leertaste = GO).
Solange ein bearbeitbares Texteingabefeld (Zeile, Textfeld, Zahlenfeld,
bearbeitbare Auswahlliste) den Fokus hat, gehoeren Tasten, die ein Zeichen
erzeugen, diesem Feld — mit oder ohne Umschalt. Qt erledigt das fuer die
meisten Felder schon selbst; diese Regel macht es zentral und unabhaengig
von der Feldklasse fest (``MainWindow.event`` fragt sie beim
``ShortcutOverride`` ab).

Nicht betroffen: Tasten mit Strg/Alt/Meta (Strg+S, Strg+Z, ...), Escape und
Funktionstasten (F5, F12) — sie erzeugen kein Zeichen und bleiben Kuerzel.
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import (QAbstractSpinBox, QApplication, QComboBox,
                               QLineEdit, QPlainTextEdit, QTextEdit)

_KUERZEL_MODS = (Qt.KeyboardModifier.ControlModifier
                 | Qt.KeyboardModifier.AltModifier
                 | Qt.KeyboardModifier.MetaModifier)


def ist_textfeld(w) -> bool:
    """True fuer ein bearbeitbares Texteingabefeld."""
    try:
        if isinstance(w, QLineEdit):
            return not w.isReadOnly() and w.isEnabled()
        if isinstance(w, (QTextEdit, QPlainTextEdit)):
            return not w.isReadOnly() and w.isEnabled()
        if isinstance(w, QAbstractSpinBox):
            return not w.isReadOnly() and w.isEnabled()
        if isinstance(w, QComboBox):
            return w.isEditable() and w.isEnabled()
    except RuntimeError:        # Widget schon abgebaut
        return False
    return False


def hat_vorrang(ev) -> bool:
    """True (Ereignis angenommen), wenn dieser ``ShortcutOverride`` ein
    Zeichen fuer das fokussierte Textfeld ist und kein Kuerzel ausloesen
    darf."""
    if ev.type() != QEvent.Type.ShortcutOverride:
        return False
    try:
        if ev.modifiers() & _KUERZEL_MODS:
            return False
        text = ev.text()
        if not text or not text.isprintable():
            return False
        if not ist_textfeld(QApplication.focusWidget()):
            return False
    except RuntimeError:
        return False
    ev.accept()
    return True
