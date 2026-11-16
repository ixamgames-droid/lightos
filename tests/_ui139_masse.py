"""UI-139: gemeinsame Messhilfen fuer die Klick-Test-Funde.

* ``fenster_qss(touch)`` = Theme + das Touch-Stylesheet, das das Hauptfenster
  mit ``--touch`` setzt (``MainWindow._apply_theme``). Der Override-Text wird
  per ``ast`` aus ``main_window.py`` gelesen — so laufen Test und App nicht
  auseinander, und der Test muss kein Hauptfenster bauen.
* ``Rahmen`` ist ein Host-Widget mit diesem Stylesheet in der Groesse, die
  eine Ansicht bei kleiner Aufloesung bekommt.
* ``text_passt(knopf)`` prueft, dass die Beschriftung in die Innenflaeche des
  Knopfs passt (Innenabstand des Stylesheets eingerechnet).
"""
from __future__ import annotations

import ast
import pathlib

from PySide6.QtWidgets import (
    QApplication, QPushButton, QStyle, QStyleOptionButton, QVBoxLayout, QWidget,
)

from src.ui import touch_keyboard as tk

WURZEL = pathlib.Path(__file__).resolve().parents[1]

#: Platz, den eine Ansicht im Hauptfenster bekommt (Fenster minus Menue,
#: Kopfleiste, Unterreiter, Befehlszeile, Statusleiste; gemessen an den
#: Klick-Test-Bildern vom 16.11.2026).
KLEIN = {"1280x800": (1280, 590), "1366x768": (1366, 560)}


def _override_text() -> str:
    quelle = (WURZEL / "src" / "ui" / "main_window.py").read_text(encoding="utf-8")
    baum = ast.parse(quelle)
    for knoten in ast.walk(baum):
        if isinstance(knoten, ast.FunctionDef) and knoten.name == "_apply_theme":
            for k in ast.walk(knoten):
                if (isinstance(k, ast.AugAssign) and isinstance(k.value, ast.Constant)
                        and isinstance(k.value.value, str)
                        and "QPushButton { min-height" in k.value.value):
                    return k.value.value
    raise AssertionError("Touch-Override in main_window._apply_theme nicht gefunden")


def fenster_qss(touch: bool) -> str:
    qss = (WURZEL / "assets" / "themes" / "dark.qss").read_text(encoding="utf-8")
    if touch:
        qss += "\n" + _override_text() + tk.touch_qss()
    return qss


class Rahmen(QWidget):
    """Host mit Fenster-Stylesheet; nimmt die Ansicht als einziges Kind auf."""

    def __init__(self, touch: bool, groesse=(1280, 590)):
        super().__init__()
        self.setStyleSheet(fenster_qss(touch))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        # Wie das Hauptfenster (``setMinimumSize(900, 600)``): eine eigene
        # Mindestgroesse verhindert, dass die Mindesthoehe der Ansicht das
        # Fenster groesser macht — die Ansicht wird wie in der App gequetscht.
        self.setMinimumSize(200, 200)
        self.resize(*groesse)

    def zeige(self, ansicht: QWidget) -> QWidget:
        self.layout().addWidget(ansicht)
        self.show()
        for _ in range(4):
            QApplication.processEvents()
        return ansicht


def touch_setzen(testfall, touch: bool) -> None:
    alt = tk.is_touch_mode()
    testfall.addCleanup(tk.setze_touch_modus, alt)
    tk.setze_touch_modus(touch)


def innen(knopf: QPushButton):
    opt = QStyleOptionButton()
    knopf.initStyleOption(opt)
    opt.rect = knopf.rect()
    return knopf.style().subElementRect(
        QStyle.SubElement.SE_PushButtonContents, opt, knopf)


def text_passt(knopf: QPushButton) -> bool:
    knopf.ensurePolished()
    fm = knopf.fontMetrics()
    r = innen(knopf)
    return (fm.horizontalAdvance(knopf.text()) <= r.width()
            and fm.height() <= r.height() + 1)


def sichtbar_in(widget: QWidget, oben: QWidget) -> bool:
    """Liegt ``widget`` vollstaendig innerhalb von ``oben``?"""
    tl = widget.mapTo(oben, widget.rect().topLeft())
    br = widget.mapTo(oben, widget.rect().bottomRight())
    return oben.rect().contains(tl) and oben.rect().contains(br)
