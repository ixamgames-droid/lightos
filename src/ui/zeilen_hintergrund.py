"""UI-144: Zeilenfarbe einer Liste auch unter dem App-Stylesheet zeigen.

Gestaltet ein Stylesheet das Unterelement ``QListWidget::item`` (das dunkle
Theme ``assets/themes/dark.qss`` tut das fuer jede Liste), malt Qt den
Pinsel aus ``QListWidgetItem.setBackground`` (BackgroundRole) nicht mehr.
Eine Zeilenfarbe, die dem Bediener etwas zeigt — die laufende Cue, die Farbe
eines Sequenz-Schritts —, kam dann nicht mehr an. Tabellen und Baeume sind
nicht betroffen (dort gestaltet das Theme nur ``::item:selected``).

``hintergrund_sichtbar(liste)`` setzt einen kleinen Delegaten: er fuellt fuer
Zeilen mit eigenem Hintergrund das Rechteck selbst und laesst danach den Stil
Text, Schrift und Symbol wie gewohnt zeichnen. Ausgewaehlte Zeilen behalten die
Auswahlfarbe des Themes; Zeilen ohne eigenen Hintergrund bleiben unveraendert.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QAbstractItemView, QStyle, QStyledItemDelegate,
                               QStyleOptionViewItem)


def _pinsel(wert) -> QBrush | None:
    if isinstance(wert, QColor):
        wert = QBrush(wert)
    if not isinstance(wert, QBrush):
        return None
    if wert.style() == Qt.BrushStyle.NoBrush or wert.color().alpha() == 0:
        return None
    return wert


class HintergrundDelegate(QStyledItemDelegate):
    """Zeichnet die BackgroundRole einer Zeile auch mit Stylesheet."""

    def paint(self, painter, option, index):
        pinsel = _pinsel(index.data(Qt.ItemDataRole.BackgroundRole))
        if pinsel is None or option.state & QStyle.StateFlag.State_Selected:
            super().paint(painter, option, index)
            return
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        painter.save()
        painter.fillRect(opt.rect, pinsel)
        painter.restore()
        # Kein Hover-Grau ueber der Markierung, keinen zweiten Hintergrund.
        opt.state &= ~QStyle.StateFlag.State_MouseOver
        opt.backgroundBrush = QBrush()
        widget = opt.widget
        style = widget.style() if widget is not None else None
        if style is None:
            super().paint(painter, opt, index)
            return
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, widget)


def hintergrund_sichtbar(liste: QAbstractItemView) -> HintergrundDelegate:
    """Setzt den Delegaten auf ``liste`` (Elternteil = Liste) und gibt ihn zurueck."""
    d = HintergrundDelegate(liste)
    liste.setItemDelegate(d)
    return d
