"""UI-110: Ziehen auf Text, Flaeche oder einfacher Liste scrollt den Bereich.

Geprueft mit echten Qt-Widgets (offscreen) und Maus-Ereignissen ueber den
Anwendungsfilter: Seite und nur lesbarer Text scrollen, einfache Liste auch,
ein Klick ohne Zug kommt unveraendert an, Regler/Knopf/Textfeld/Listen mit
Ziehen-und-Ablegen oder Mehrfachauswahl behalten den Zug, nicht scrollbarer
innerer Bereich gibt an den aeusseren weiter, Umschalt markiert weiter.
"""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt              # noqa: E402
from PySide6.QtGui import QMouseEvent                                # noqa: E402
from PySide6.QtWidgets import (                                      # noqa: E402
    QAbstractItemView, QApplication, QLabel, QLineEdit, QListWidget,
    QPushButton, QScrollArea, QSlider, QTextBrowser, QVBoxLayout, QWidget,
)

from src.ui import ziehen_scrollen as zs                             # noqa: E402

_app = QApplication.instance() or QApplication([])


class _Zeit:
    t = 1000


def _maus(w, typ, pos, knopf=Qt.MouseButton.LeftButton,
          knoepfe=Qt.MouseButton.LeftButton, mods=Qt.KeyboardModifier.NoModifier,
          glob=None):
    _Zeit.t += 10
    lokal = QPointF(pos)
    glob = QPointF(w.mapToGlobal(pos)) if glob is None else QPointF(glob)
    ev = QMouseEvent(typ, lokal, glob, knopf, knoepfe, mods)
    ev.setTimestamp(_Zeit.t)
    QApplication.sendEvent(w, ev)
    return ev


def _ziehen(w, start: QPoint, ende: QPoint, schritte: int = 5, mods=Qt.KeyboardModifier.NoModifier):
    """Druecken, in Schritten ziehen, loslassen. Gibt die Ereignisse zurueck."""
    # Bildschirmlage einmal festhalten: das Widget wandert beim Scrollen mit,
    # die echte Maus nicht.
    g0 = w.mapToGlobal(start)
    evs = [_maus(w, QEvent.Type.MouseButtonPress, start, mods=mods, glob=g0)]
    for i in range(1, schritte + 1):
        d = (ende - start) * (i / schritte)
        evs.append(_maus(w, QEvent.Type.MouseMove, start + d, knopf=Qt.MouseButton.NoButton,
                         mods=mods, glob=g0 + d))
    evs.append(_maus(w, QEvent.Type.MouseButtonRelease, ende,
                     knoepfe=Qt.MouseButton.NoButton, mods=mods, glob=g0 + (ende - start)))
    return evs


def _seite(*kinder):
    """Scrollbare Seite: langer Text oben, dann die Kinder."""
    area = QScrollArea()
    area.setWidgetResizable(True)
    inhalt = QWidget()
    lay = QVBoxLayout(inhalt)
    text = QLabel("\n".join(f"Zeile {i}" for i in range(120)))
    lay.addWidget(text)
    for k in kinder:
        lay.addWidget(k)
    area.setWidget(inhalt)
    area.resize(300, 200)
    area.show()
    QApplication.processEvents()
    return area, text


class ZiehenScrollenTest(unittest.TestCase):

    def setUp(self):
        self.f = zs.einrichten(_app)
        self.f.aktiv = True
        self.addCleanup(self.f._abbrechen)

    def test_einrichten_nur_einmal(self):
        self.assertIs(zs.einrichten(_app), self.f)

    def test_ziehen_auf_text_scrollt_die_seite(self):
        area, text = _seite()
        bar = area.verticalScrollBar()
        self.assertGreater(bar.maximum(), 0)
        self.assertIs(zs.ziel_bereich(text), area)
        _ziehen(text, QPoint(50, 150), QPoint(50, 30))
        self.assertEqual(bar.value(), 120, "Inhalt folgt der Maus")
        _ziehen(text, QPoint(50, 30), QPoint(50, 80))
        self.assertEqual(bar.value(), 70)

    def test_klick_ohne_zug_scrollt_nicht_und_kommt_an(self):
        area, text = _seite()
        evs = _ziehen(text, QPoint(50, 100), QPoint(51, 101), schritte=1)
        self.assertEqual(area.verticalScrollBar().value(), 0)
        self.assertFalse(QApplication.overrideCursor())

    def test_nach_zug_wird_loslassen_geschluckt(self):
        area, _ = _seite()
        browser = QTextBrowser()
        browser.setHtml("<br>".join(f"<a href='x{i}'>Link {i}</a>" for i in range(200)))
        browser.resize(300, 200)
        browser.show()
        QApplication.processEvents()
        geklickt = []
        browser.anchorClicked.connect(geklickt.append)
        bar = browser.verticalScrollBar()
        _ziehen(browser.viewport(), QPoint(20, 150), QPoint(20, 40))
        self.assertEqual(bar.value(), 110)
        self.assertEqual(geklickt, [], "kein Link nach dem Zug")
        self.assertFalse(QApplication.overrideCursor(), "Zeiger wieder normal")

    def test_einfache_liste_scrollt(self):
        liste = QListWidget()
        liste.addItems([f"Eintrag {i}" for i in range(200)])
        liste.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        liste.resize(200, 150)
        liste.show()
        QApplication.processEvents()
        self.assertIs(zs.ziel_bereich(liste.viewport()), liste)
        _ziehen(liste.viewport(), QPoint(20, 120), QPoint(20, 20))
        self.assertEqual(liste.verticalScrollBar().value(), 100)

    def test_liste_mit_ablegen_oder_mehrfachauswahl_behaelt_den_zug(self):
        a = QListWidget()
        a.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        b = QListWidget()
        b.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        for liste in (a, b):
            liste.addItems([f"E {i}" for i in range(200)])
            liste.resize(200, 150)
            liste.show()
        QApplication.processEvents()
        self.assertIsNone(zs.ziel_bereich(a.viewport()))
        self.assertIsNone(zs.ziel_bereich(b.viewport()))

    def test_bedienelemente_behalten_den_zug(self):
        regler = QSlider(Qt.Orientation.Horizontal)
        knopf = QPushButton("Los")
        feld = QLineEdit("Text")
        area, _ = _seite(regler, knopf, feld)
        for w in (regler, knopf, feld):
            self.assertIsNone(zs.ziel_bereich(w), type(w).__name__)
        regler.setRange(0, 100)
        regler.setValue(50)
        area.verticalScrollBar().setValue(area.verticalScrollBar().maximum())
        QApplication.processEvents()
        vorher = area.verticalScrollBar().value()
        _ziehen(regler, QPoint(5, 5), QPoint(5, -60))
        self.assertEqual(area.verticalScrollBar().value(), vorher)

    def test_eigene_klasse_mit_maus_behaelt_den_zug(self):
        class Fader(QWidget):
            def mousePressEvent(self, ev):
                ev.accept()

        fader = Fader()
        fader.setMinimumHeight(40)
        area, _ = _seite(fader)
        self.assertIsNone(zs.ziel_bereich(fader))

    def test_editierbarer_text_markiert_weiter(self):
        from PySide6.QtWidgets import QTextEdit
        t = QTextEdit()
        t.setPlainText("\n".join("x" * 10 for _ in range(200)))
        self.assertIsNone(zs.ziel_bereich(t.viewport()))
        t.setReadOnly(True)
        t.resize(200, 100)
        t.show()
        QApplication.processEvents()
        self.assertIs(zs.ziel_bereich(t.viewport()), t)

    def test_nicht_scrollbarer_innerer_bereich_gibt_nach_aussen(self):
        kurz = QListWidget()
        kurz.addItems(["eins", "zwei"])
        kurz.setFixedHeight(120)
        area, _ = _seite(kurz)
        self.assertEqual(kurz.verticalScrollBar().maximum(), 0)
        self.assertIs(zs.ziel_bereich(kurz.viewport()), area)

    def test_umschalt_markiert_statt_scrollen(self):
        area, text = _seite()
        _ziehen(text, QPoint(50, 150), QPoint(50, 30), mods=Qt.KeyboardModifier.ShiftModifier)
        self.assertEqual(area.verticalScrollBar().value(), 0)

    def test_abschaltbar_je_widget_und_gesamt(self):
        area, text = _seite()
        text.setProperty("ziehen_scrollen", False)
        self.assertIsNone(zs.ziel_bereich(text))
        text.setProperty("ziehen_scrollen", None)
        self.f.aktiv = False
        _ziehen(text, QPoint(50, 150), QPoint(50, 30))
        self.assertEqual(area.verticalScrollBar().value(), 0)

    def test_bereich_weg_waehrend_zug_bricht_nicht(self):
        area, text = _seite()
        _maus(text, QEvent.Type.MouseButtonPress, QPoint(50, 150))
        _maus(text, QEvent.Type.MouseMove, QPoint(50, 100), knopf=Qt.MouseButton.NoButton)
        area.deleteLater()
        QApplication.processEvents()
        ersatz = QWidget()
        _maus(ersatz, QEvent.Type.MouseMove, QPoint(50, 50), knopf=Qt.MouseButton.NoButton)
        _maus(ersatz, QEvent.Type.MouseButtonRelease, QPoint(50, 50), knoepfe=Qt.MouseButton.NoButton)
        self.assertIsNone(self.f._bereich)
        self.assertFalse(QApplication.overrideCursor())


if __name__ == "__main__":
    unittest.main()
