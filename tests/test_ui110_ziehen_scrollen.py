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
        alt_uhr = self.f._uhr
        self.f._uhr = lambda: _Zeit.t / 1000.0    # Ereignis-Takt = Uhr
        self.addCleanup(setattr, self.f, "_uhr", alt_uhr)
        self.addCleanup(self.f._abbrechen)
        self.addCleanup(self.f.schwung_stoppen)
        alt_touch = zs.ist_touch
        self.addCleanup(setattr, zs, "ist_touch", alt_touch)

    def _finger(self):
        zs.ist_touch = lambda ev: True

    def _ablege_liste(self):
        liste = QListWidget()
        liste.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        liste.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        liste.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        liste.addItems([f"E {i}" for i in range(200)])
        liste.resize(200, 150)
        liste.show()
        QApplication.processEvents()
        return liste

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


    # ── Touch ────────────────────────────────────────────────────────────────

    def test_touch_wischen_scrollt_auch_liste_mit_ablegen(self):
        liste = self._ablege_liste()
        self.assertIsNone(zs.ziel_bereich(liste.viewport()))
        self._finger()
        _ziehen(liste.viewport(), QPoint(20, 130), QPoint(20, 30))
        self.f.schwung_stoppen()
        self.assertEqual(liste.verticalScrollBar().value(), 100)
        self.assertFalse(QApplication.overrideCursor(), "am Finger kein Hand-Zeiger")

    def test_touch_langes_druecken_gibt_den_zug_an_die_liste(self):
        liste = self._ablege_liste()
        self._finger()
        v = liste.viewport()
        g0 = v.mapToGlobal(QPoint(20, 130))
        _maus(v, QEvent.Type.MouseButtonPress, QPoint(20, 130), glob=g0)
        _Zeit.t += int(zs.LANG_DRUCK_S * 1000) + 50          # Finger liegt still
        ev = _maus(v, QEvent.Type.MouseMove, QPoint(20, 80), knopf=Qt.MouseButton.NoButton,
                   glob=g0 + QPoint(0, -50))
        self.assertIsNone(self.f._bereich, "Zug gehoert jetzt der Liste")
        self.assertEqual(liste.verticalScrollBar().value(), 0)
        _maus(v, QEvent.Type.MouseButtonRelease, QPoint(20, 80), knoepfe=Qt.MouseButton.NoButton)

    def test_touch_braucht_groesseren_weg(self):
        area, text = _seite()
        self._finger()
        schwelle = QApplication.startDragDistance()
        _ziehen(text, QPoint(50, 150), QPoint(50, 150 - int(schwelle * 1.5)), schritte=1)
        self.assertEqual(area.verticalScrollBar().value(), 0, "Tippen mit Wackeln scrollt nicht")

    def test_touch_regler_bleibt_regler(self):
        regler = QSlider(Qt.Orientation.Horizontal)
        area, _ = _seite(regler)
        self.assertIsNone(zs.ziel_bereich(regler, touch=True))

    def test_schwung_nach_schnellem_wischen_und_finger_haelt_an(self):
        area, text = _seite()
        bar = area.verticalScrollBar()
        _ziehen(text, QPoint(50, 150), QPoint(50, 50))      # 100 px in 50 ms
        self.assertTrue(self.f.schwingt)
        nach_zug = bar.value()
        self.f.schwung_schritt(0.05)
        self.assertGreater(bar.value(), nach_zug, "laeuft in Wischrichtung weiter")
        weiter = bar.value()
        self.f.schwung_schritt(0.05)
        self.assertLess(bar.value() - weiter, weiter - nach_zug, "bremst ab")
        _maus(text, QEvent.Type.MouseButtonPress, QPoint(50, 50))
        self.assertFalse(self.f.schwingt, "Finger drauf haelt an")
        _maus(text, QEvent.Type.MouseButtonRelease, QPoint(50, 50), knoepfe=Qt.MouseButton.NoButton)

    def test_langsam_losgelassen_kein_schwung_und_auslauf_endet(self):
        area, text = _seite()
        g0 = text.mapToGlobal(QPoint(50, 150))
        _maus(text, QEvent.Type.MouseButtonPress, QPoint(50, 150), glob=g0)
        _maus(text, QEvent.Type.MouseMove, QPoint(50, 100), knopf=Qt.MouseButton.NoButton,
              glob=g0 + QPoint(0, -50))
        _Zeit.t += 300                                        # stehen geblieben
        _maus(text, QEvent.Type.MouseMove, QPoint(50, 100), knopf=Qt.MouseButton.NoButton,
              glob=g0 + QPoint(0, -50))
        _maus(text, QEvent.Type.MouseButtonRelease, QPoint(50, 100),
              knoepfe=Qt.MouseButton.NoButton, glob=g0 + QPoint(0, -50))
        self.assertFalse(self.f.schwingt)
        _ziehen(text, QPoint(50, 150), QPoint(50, 50))
        for _ in range(400):
            if not self.f.schwingt:
                break
            self.f.schwung_schritt(0.016)
        self.assertFalse(self.f.schwingt, "Auslauf endet von selbst")

    def test_echter_touch_ueber_das_fenster_eintragsweise_liste(self):
        """Echter Ablauf: Touch an das Fenster, Qt erzeugt die Maus daraus
        (zuerst an das QWindow, dann an das Widget). Liste scrollt
        eintragsweise: 100 px Fingerweg = sichtbare Eintraege, nicht 100."""
        from PySide6.QtTest import QTest
        dev = QTest.createTouchDevice()
        liste = QListWidget()
        liste.addItems([f"E {i}" for i in range(300)])
        liste.resize(200, 150)
        liste.show()
        QApplication.processEvents()
        bar = liste.verticalScrollBar()
        self.assertEqual(liste.verticalScrollMode(), QAbstractItemView.ScrollMode.ScrollPerItem)
        v = liste.viewport()
        QTest.touchEvent(v, dev).press(0, QPoint(20, 120), v).commit()
        for y in range(110, 15, -15):
            QTest.touchEvent(v, dev).move(0, QPoint(20, max(y, 20)), v).commit()
        QTest.touchEvent(v, dev).release(0, QPoint(20, 20), v).commit()
        self.f.schwung_stoppen()
        erwartet = round(100 * bar.pageStep() / v.height())
        self.assertGreater(bar.value(), 0, "Finger scrollt")
        self.assertLessEqual(abs(bar.value() - erwartet), 1)

    def test_touch_wischen_ueber_knopf_scrollt_ohne_klick_tippen_klickt(self):
        from PySide6.QtTest import QTest
        dev = QTest.createTouchDevice()
        knoepfe = [QPushButton(f"Knopf {i}") for i in range(40)]
        area, _ = _seite(*knoepfe)
        area.verticalScrollBar().setValue(area.verticalScrollBar().maximum())
        QApplication.processEvents()
        vp = area.viewport()

        def ganz_sichtbar(b):
            y = b.mapTo(vp, QPoint(0, 0)).y()
            return 0 <= y <= vp.height() - b.height()
        k = next(b for b in knoepfe if ganz_sichtbar(b))
        geklickt = []
        k.clicked.connect(lambda: geklickt.append(1))
        self.assertIsNone(zs.ziel_bereich(k), "Maus: Knopf bleibt Knopf")
        self.assertIs(zs.ziel_bereich(k, touch=True), area)
        bar = area.verticalScrollBar()
        mitte = QPoint(k.width() // 2, k.height() // 2)
        QTest.touchEvent(k, dev).press(0, mitte, k).commit()
        QTest.touchEvent(k, dev).release(0, mitte, k).commit()
        self.assertEqual(geklickt, [1], "Tippen klickt")
        geklickt.clear()
        vorher = bar.value()
        QTest.touchEvent(k, dev).press(0, mitte, k).commit()
        for dy in range(10, 90, 10):
            QTest.touchEvent(k, dev).move(0, mitte + QPoint(0, dy), k).commit()
        self.assertFalse(k.isDown(), "Knopf steht beim Wischen nicht gedrueckt")
        QTest.touchEvent(k, dev).release(0, mitte + QPoint(0, 80), k).commit()
        self.f.schwung_stoppen()
        self.assertLess(bar.value(), vorher, "Seite folgt dem Finger")
        self.assertEqual(geklickt, [], "Wischen loest den Knopf nicht aus")

    def test_echte_maus_ueber_das_fenster(self):
        """Mausweg ueber QTest (Druck, Bewegung mit gehaltener Taste,
        Loslassen). Den Fenster-Weg (Druck zuerst ans QWindow) decken die
        beiden Tests mit echtem Touch-Ablauf ab — nur sie werden ohne den
        Fix rot."""
        from PySide6.QtTest import QTest
        area, text = _seite()
        bar = area.verticalScrollBar()
        vp = area.viewport()
        QTest.mousePress(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(50, 150))
        for y in range(140, 40, -20):
            QTest.mouseMove(vp, QPoint(50, y))
        QTest.mouseRelease(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(50, 50))
        self.f.schwung_stoppen()
        self.assertGreater(bar.value(), 50, "Maus zieht die Seite")

    def test_ist_touch_erkennt_erzeugte_maus(self):
        ev = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(1, 1), QPointF(1, 1),
                         Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.NoModifier)
        self.assertFalse(zs.ist_touch(ev))


if __name__ == "__main__":
    unittest.main()
