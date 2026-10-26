"""Spaltenbreiten fuer Tabellen mit Auswahl- und Eingabefeldern in den Zellen.

``QHeaderView.ResizeToContents`` misst nur Kopftext und Items; per
``setCellWidget`` gesetzte Felder zaehlen nicht verlaesslich mit (NET-15/#1138:
„Art-N", „E:"; OSC-07: „E"/„Ex" statt „Executor-Fader"). Die Hilfen hier messen
ein Probe-Feld als Kind der Tabelle — damit gelten dieselbe Schrift und
dasselbe Stylesheet wie in den Zellen — und setzen die Spalte fest.
"""
from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QHeaderView, QLineEdit, QTableWidget


def combo_breite(tabelle: QTableWidget, texte) -> int:
    """sizeHint-Breite einer Combo mit diesen Eintraegen (laengster samt Pfeil).

    ``texte``: Folge von ``(schluessel, text)``."""
    probe = QComboBox(tabelle)
    probe.setVisible(False)
    for _key, text in texte:
        probe.addItem(text)
    probe.ensurePolished()
    breite = probe.sizeHint().width()
    probe.setParent(None)
    probe.deleteLater()
    return breite


def lineedit_breite(tabelle: QTableWidget, platzhalter: str) -> int:
    """Breite, in der ein QLineEdit seinen Platzhalter ungekuerzt zeigt.

    ``QLineEdit.sizeHint`` rechnet mit 17 × „x" plus Rand/Polster; der Rand ist
    also ``sizeHint - 17 × x`` — dazu kommt die Laenge des Platzhalters. Nie
    schmaler als der sizeHint selbst."""
    probe = QLineEdit(tabelle)
    probe.setVisible(False)
    probe.setPlaceholderText(platzhalter)
    probe.ensurePolished()
    fm = probe.fontMetrics()
    hint = probe.sizeHint().width()
    rand = hint - 17 * fm.horizontalAdvance("x")
    breite = max(hint, fm.horizontalAdvance(platzhalter) + rand)
    probe.setParent(None)
    probe.deleteLater()
    return breite


def spalte_fest(tabelle: QTableWidget, spalte: int, mindest: int) -> None:
    """Spalte fest so breit wie ``mindest``, Kopftext und die Felder ihrer Zellen.

    Die Zelle ist um die Gitterlinie schmaler als die Spalte."""
    kopf = tabelle.horizontalHeader()
    if kopf.sectionResizeMode(spalte) != QHeaderView.ResizeMode.Fixed:
        kopf.setSectionResizeMode(spalte, QHeaderView.ResizeMode.Fixed)
    breite = max(int(mindest), kopf.sectionSizeHint(spalte))
    for r in range(tabelle.rowCount()):
        w = tabelle.cellWidget(r, spalte)
        if w is not None:
            breite = max(breite, w.sizeHint().width())
    kopf.resizeSection(spalte, breite + (1 if tabelle.showGrid() else 0))
