"""UI-113: Regler am Finger — nur der Griff zaehlt (Touch-Audit A-02/C-03/D-09).

Befund 11.11.2026: ein Tipp auf die Rille eines Reglers sprang um eine Seite
(Kanal 0 -> 10, Grand Master 100 -> 90 %), blieb der Finger 1,5 s liegen,
lief der Wert bis 185. Jetzt gilt am Finger (aus Touch erzeugte Maus): Tipp,
Halten und Ziehen ab der Rille aendern nichts, Ziehen am Griff bedient den
Regler, quer wischen scrollt die Seite. Die Maus bleibt wie bisher.

Geprueft mit echtem Touch-Ablauf ueber das Fenster (``QTest.touchEvent``):
Qt erzeugt daraus die Maus, wie auf dem Geraet.
"""
from __future__ import annotations

import os
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt                                # noqa: E402
from PySide6.QtTest import QTest                                     # noqa: E402
from PySide6.QtWidgets import (                                      # noqa: E402
    QApplication, QLabel, QScrollArea, QSlider, QVBoxLayout, QWidget,
)

from src.ui import touch_keyboard as tk                              # noqa: E402
from src.ui import ziehen_scrollen as zs                             # noqa: E402

_app = QApplication.instance() or QApplication([])


def _regler(wert=0, maximum=255):
    r = QSlider(Qt.Orientation.Horizontal)
    r.setRange(0, maximum)
    r.setValue(wert)
    r.setMinimumWidth(250)
    return r


def _ohne_scroll(regler):
    """Regler in einem einfachen Fenster ohne Scrollflaeche (wie GM)."""
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.addWidget(regler)
    w.resize(300, 80)
    w.show()
    QApplication.processEvents()
    return w


def _scrollseite(regler):
    area = QScrollArea()
    area.setWidgetResizable(True)
    inhalt = QWidget()
    lay = QVBoxLayout(inhalt)
    lay.addWidget(QLabel("\n".join(f"Zeile {i}" for i in range(120))))
    lay.addWidget(regler)
    area.setWidget(inhalt)
    area.resize(320, 220)
    area.show()
    QApplication.processEvents()
    bar = area.verticalScrollBar()
    bar.setValue(bar.maximum())
    QApplication.processEvents()
    return area


def _griff_mitte(regler) -> QPoint:
    return zs.griff_rechteck(regler).center()


def _rille(regler) -> QPoint:
    """Punkt auf der Rille, weit weg vom Griff."""
    g = zs.griff_rechteck(regler)
    x = regler.width() - 20 if g.center().x() < regler.width() // 2 else 20
    return QPoint(x, regler.height() // 2)


class _Finger:
    def __init__(self, widget):
        self.dev = QTest.createTouchDevice()
        self.win = widget.window()
        self.w = widget

    def _p(self, p: QPoint) -> QPoint:
        return self.w.mapTo(self.win, p)

    def druck(self, p):
        QTest.touchEvent(self.win, self.dev).press(0, self._p(p), self.win).commit()

    def zug(self, p):
        QTest.touchEvent(self.win, self.dev).move(0, self._p(p), self.win).commit()

    def los(self, p):
        QTest.touchEvent(self.win, self.dev).release(0, self._p(p), self.win).commit()

    def tipp(self, p):
        self.druck(p)
        self.los(p)

    def ziehen(self, start: QPoint, d: QPoint, schritte=6):
        self.druck(start)
        for i in range(1, schritte + 1):
            self.zug(start + d * (i / schritte))
        self.los(start + d)


class ReglerTouchTest(unittest.TestCase):

    def setUp(self):
        self.f = zs.einrichten(_app)
        self.f.aktiv = True
        self.addCleanup(self.f._abbrechen)
        self.addCleanup(self.f.schwung_stoppen)

    # ── Rille ────────────────────────────────────────────────────────────────

    def test_rillen_tipp_aendert_nichts(self):
        for bauen in (_scrollseite, _ohne_scroll):
            r = _regler(0)
            fenster = bauen(r)
            self.addCleanup(fenster.deleteLater)
            _Finger(r).tipp(_rille(r))
            QApplication.processEvents()
            self.assertEqual(r.value(), 0, f"{bauen.__name__}: Rillen-Tipp springt nicht")

    def test_rillen_doppeltipp_aendert_nichts(self):
        r = _regler(0)
        fenster = _ohne_scroll(r)
        self.addCleanup(fenster.deleteLater)
        f = _Finger(r)
        f.tipp(_rille(r))
        f.tipp(_rille(r))
        QApplication.processEvents()
        self.assertEqual(r.value(), 0)

    def test_rillen_halten_1_5_s_aendert_nichts(self):
        r = _regler(0)
        fenster = _ohne_scroll(r)
        self.addCleanup(fenster.deleteLater)
        f = _Finger(r)
        p = _rille(r)
        f.druck(p)
        ende = time.monotonic() + 1.5
        while time.monotonic() < ende:
            QApplication.processEvents()
            time.sleep(0.01)
        f.los(p)
        QApplication.processEvents()
        self.assertEqual(r.value(), 0, "Halten auf der Rille laeuft nicht weiter")

    def test_ziehen_ab_der_rille_bewegt_nichts(self):
        r = _regler(0)
        fenster = _ohne_scroll(r)
        self.addCleanup(fenster.deleteLater)
        p = QPoint(r.width() // 2, r.height() // 2)
        _Finger(r).ziehen(p, QPoint(80, 0))
        self.assertEqual(r.value(), 0)

    # ── Griff ────────────────────────────────────────────────────────────────

    def test_griff_ziehen_bewegt_ohne_sprung(self):
        for bauen in (_scrollseite, _ohne_scroll):
            r = _regler(128)
            fenster = bauen(r)
            self.addCleanup(fenster.deleteLater)
            vorher = _griff_mitte(r)
            # Finger knapp neben der Griffmitte (in der Trefferzone)
            start = vorher + QPoint(6, 3)
            _Finger(r).ziehen(start, QPoint(60, 0))
            self.assertGreater(r.value(), 128, f"{bauen.__name__}: Regler folgt dem Finger")
            nachher = _griff_mitte(r)
            self.assertLessEqual(abs((nachher.x() - vorher.x()) - 60), 3,
                                 "Griff wandert genau mit dem Finger (kein Sprung)")

    def test_griff_trefferzone(self):
        r = _regler(128)
        fenster = _ohne_scroll(r)
        self.addCleanup(fenster.deleteLater)
        g = zs.griff_rechteck(r)
        self.assertTrue(zs.am_griff(r, QPoint(g.right() + zs.GRIFF_ZONE, g.center().y())))
        self.assertFalse(zs.am_griff(r, QPoint(g.right() + zs.GRIFF_ZONE + 3, g.center().y())))

    def test_griff_tipp_aendert_nichts(self):
        r = _regler(128)
        fenster = _ohne_scroll(r)
        self.addCleanup(fenster.deleteLater)
        _Finger(r).tipp(_griff_mitte(r))
        self.assertEqual(r.value(), 128)
        self.assertFalse(r.isSliderDown())

    # ── Seite ────────────────────────────────────────────────────────────────

    def test_quer_wischen_in_scrollseite_scrollt_ohne_wert(self):
        for griff in (True, False):
            r = _regler(128 if griff else 0)
            area = _scrollseite(r)
            self.addCleanup(area.deleteLater)
            bar = area.verticalScrollBar()
            vorher = bar.value()
            start = _griff_mitte(r) if griff else _rille(r)
            _Finger(r).ziehen(start, QPoint(2, 90))
            self.f.schwung_stoppen()
            self.assertEqual(r.value(), 128 if griff else 0, "Wert unveraendert")
            self.assertLess(bar.value(), vorher, "Seite gescrollt")

    # ── Maus unveraendert ────────────────────────────────────────────────────

    def test_maus_tipp_auf_rille_springt_wie_bisher(self):
        for bauen in (_scrollseite, _ohne_scroll):
            r = _regler(0)
            fenster = bauen(r)
            self.addCleanup(fenster.deleteLater)
            QTest.mouseClick(r, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                             _rille(r))
            self.assertEqual(r.value(), r.pageStep(), f"{bauen.__name__}: Maus springt")

    def test_eigene_reglerklasse_unberuehrt(self):
        class Fader(QSlider):
            def mousePressEvent(self, ev):          # noqa: N802
                self.gedrueckt = True
                super().mousePressEvent(ev)
        r = Fader(Qt.Orientation.Horizontal)
        r.setRange(0, 255)
        r.setMinimumWidth(250)
        fenster = _ohne_scroll(r)
        self.addCleanup(fenster.deleteLater)
        _Finger(r).tipp(_rille(r))
        self.assertTrue(getattr(r, "gedrueckt", False), "Druck kommt beim eigenen Regler an")

    # ── Groessen im Touch-Modus ──────────────────────────────────────────────

    def _touch_qss(self, touch: bool) -> str:
        from src.ui.main_window import MainWindow

        class _Stub:
            _touch_mode = touch

            def setStyleSheet(self, qss):
                self.qss = qss
        s = _Stub()
        MainWindow._apply_theme(s)
        return s.qss

    def test_touch_qss_regler_groessen(self):
        for touch in (True, False):
            w = QWidget()
            w.setStyleSheet(self._touch_qss(touch))
            lay = QVBoxLayout(w)
            h = QSlider(Qt.Orientation.Horizontal)
            v = QSlider(Qt.Orientation.Vertical)
            lay.addWidget(h)
            lay.addWidget(v)
            w.resize(300, 300)
            w.show()
            QApplication.processEvents()
            self.addCleanup(w.deleteLater)
            if touch:
                self.assertGreaterEqual(h.height(), 40)
                self.assertGreaterEqual(v.width(), 40)
                for r in (h, v):
                    g = zs.griff_rechteck(r)
                    self.assertGreaterEqual(min(g.width(), g.height()), 34, g)
            else:
                self.assertLess(h.height(), 40, "ohne Touch unveraendert klein")

    def test_grand_master_touch(self):
        from src.ui.main_window import MainWindow
        alt = tk.is_touch_mode()
        self.addCleanup(tk.setze_touch_modus, alt)
        w = MainWindow(touch=True)
        self.addCleanup(w.deleteLater)
        w.show()
        QApplication.processEvents()
        gm = w._slider_gm
        self.assertEqual(gm.width(), 170, "GM breiter")
        self.assertGreaterEqual(gm.height(), 30, "GM hoeher")
        self.assertLessEqual(gm.height(), w._section_bar.height(), "GM passt in die Kopfleiste")
        self.assertLessEqual(w._section_bar.height(), 35, "Kopfleiste waechst nicht")
        g = zs.griff_rechteck(gm)
        self.assertGreaterEqual(min(g.width(), g.height()), 28)
        # ohne Scrollflaeche: Rillen-Tipp aendert den GM nicht, Griff ziehen schon
        self.assertEqual(gm.value(), 100)
        _Finger(gm).tipp(QPoint(15, gm.height() // 2))
        QApplication.processEvents()
        self.assertEqual(gm.value(), 100, "GM springt nicht")
        _Finger(gm).ziehen(_griff_mitte(gm), QPoint(-60, 0))
        self.assertLess(gm.value(), 100, "GM am Griff ziehen bedient ihn")
        gm.setValue(100)
        w.close()

    def test_zoom_knoepfe_im_touch_modus_44px(self):
        from src.ui.views.live_view import LiveView
        alt = tk.is_touch_mode()
        self.addCleanup(tk.setze_touch_modus, alt)
        for touch, groesse in ((True, 44), (False, 30)):
            tk.setze_touch_modus(touch)
            lv = LiveView()
            self.addCleanup(lv.deleteLater)
            for b in (lv._btn_zoom_out, lv._btn_zoom_in, lv._btn_fit):
                self.assertEqual((b.width(), b.height()), (groesse, groesse))
            if touch:
                self.assertGreaterEqual(lv._zoom_overlay.layout().spacing(), 8)


if __name__ == "__main__":
    unittest.main()
