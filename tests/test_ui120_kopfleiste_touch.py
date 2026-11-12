"""UI-120: Kopfleiste (Sektionsleiste) am Finger (Touch-Audit A-04/A-12/A-17/A-19).

Befund 11.11.2026: die Leiste war fest 35 px hoch. Mit ``--touch`` waren
STOP ALL und BLACKOUT 44 px hoch und wurden unten abgeschnitten, die
Sektionsknoepfe (36 px) verloren auch ohne Touch 1 px. Die Page-Pfeile ‹ ›
waren fest 22 px breit, „✖ Clear“ 24 px hoch. Zwischen LASER NOT-AUS (Ecke der
Menueleiste) und STOP ALL/BLACKOUT darunter lagen nur 4 px.

Gemessen wird am gebauten Hauptfenster (Wegwerf-Daten aus conftest), der
Finger laeuft ueber ``QTest.touchEvent`` — Qt erzeugt daraus die Maus wie auf
dem Geraet.
"""
from __future__ import annotations

import os
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint                                    # noqa: E402
from PySide6.QtTest import QTest                                     # noqa: E402
from PySide6.QtWidgets import QApplication, QPushButton              # noqa: E402

from src.ui import touch_keyboard as tk                              # noqa: E402

_app = QApplication.instance() or QApplication([])


def _warte(bedingung, sekunden=5.0) -> bool:
    ende = time.monotonic() + sekunden
    while time.monotonic() < ende:
        QApplication.processEvents()
        if bedingung():
            return True
        time.sleep(0.01)
    QApplication.processEvents()
    return bool(bedingung())


class _Finger:
    def __init__(self, fenster):
        self.dev = QTest.createTouchDevice()
        self.win = fenster

    def tipp(self, widget, p: QPoint):
        q = widget.mapTo(self.win, p)
        QTest.touchEvent(self.win, self.dev).press(0, q, self.win).commit()
        QTest.touchEvent(self.win, self.dev).release(0, q, self.win).commit()
        QApplication.processEvents()


def _fenster(touch: bool, kiosk: bool = False, breite: int = 1440):
    from src.ui.main_window import MainWindow
    w = MainWindow(touch=touch, kiosk=kiosk)
    w._hw_timer.stop()
    w.resize(breite, 900)
    w.show()
    for _ in range(5):
        QApplication.processEvents()
    return w


def _oben(widget, fenster) -> int:
    return widget.mapTo(fenster, QPoint(0, 0)).y()


class _Basis(unittest.TestCase):
    TOUCH = False

    @classmethod
    def setUpClass(cls):
        cls._alt = tk.is_touch_mode()
        cls.w = _fenster(cls.TOUCH)

    @classmethod
    def tearDownClass(cls):
        cls.w.hide()
        cls.w.deleteLater()
        QApplication.processEvents()
        tk.setze_touch_modus(cls._alt)

    def _knoepfe(self):
        bar = self.w._section_bar
        return [b for b in bar.findChildren(QPushButton) if b.isVisible()]

    def _pfeile(self):
        return [b for b in self._knoepfe()
                if b.toolTip().startswith(("Vorherige Page", "Nächste Page"))]

    # A-04 / A-19: nichts wird unten abgeschnitten
    def test_alle_knoepfe_ganz_in_der_leiste(self):
        bar = self.w._section_bar
        for b in self._knoepfe():
            oben = b.mapTo(bar, QPoint(0, 0)).y()
            self.assertGreaterEqual(oben, 0, b.text())
            self.assertLessEqual(oben + b.height(), bar.height(),
                                 f"{b.text()!r}: {b.height()} px ab y={oben} in {bar.height()} px")
            self.assertGreaterEqual(b.height(), b.sizeHint().height(), b.text())

    # A-17: Abstand LASER NOT-AUS -> STOP ALL/BLACKOUT
    def test_abstand_notaus_zu_stop_und_blackout(self):
        w = self.w
        n = w._btn_laser_notaus
        unten = _oben(n, w) + n.height()
        for b in (w._btn_stop_all, w._btn_blackout):
            self.assertGreaterEqual(_oben(b, w) - unten, 8, b.text())

    # A-17 am Finger: ein Tipp in die Luecke loest keins der beiden aus
    def test_tipp_in_die_luecke_loest_nichts_aus(self):
        w = self.w
        n = w._btn_laser_notaus
        bo = w._btn_blackout
        luecke_y = _oben(n, w) + n.height() + 4
        p = QPoint(bo.mapTo(w, QPoint(bo.width() // 2, 0)).x(), luecke_y)
        blackout_vorher = bo.isChecked()
        _Finger(w).tipp(w, p)
        self.assertEqual(bo.isChecked(), blackout_vorher, "BLACKOUT nicht umgeschaltet")
        self.assertFalse(bool(getattr(w._state, "laser_estop_active", False)),
                         "Laser-NOT-AUS nicht ausgeloest")
        self.assertNotIn(w.childAt(p), (bo, n, w._btn_stop_all))


class KopfleisteMausTest(_Basis):
    TOUCH = False

    def test_hoehen_ohne_touch(self):
        self.assertGreaterEqual(self.w._section_bar.height(), 36)
        self.assertLessEqual(self.w._section_bar.height(), 40, "Maus-Leiste bleibt schmal")
        for b in self._pfeile():
            self.assertGreaterEqual(b.height(), 28, b.text())
            self.assertGreaterEqual(b.width(), b.sizeHint().width(), b.text())

    def test_sektionen_bei_1440_voll_lesbar(self):
        texte = [b.text() for b in self.w._section_btns]
        self.assertFalse([t for t in texte if "…" in t], texte)


class KopfleisteTouchTest(_Basis):
    TOUCH = True

    def test_hoehen_mit_touch(self):
        w = self.w
        self.assertGreaterEqual(w._section_bar.height(), 48)
        for b in (w._btn_stop_all, w._btn_blackout, w._btn_tap, w._btn_clear_nonvc):
            self.assertGreaterEqual(b.height(), 44, b.text())
        for b in self._pfeile():
            self.assertGreaterEqual(min(b.width(), b.height()), 44, b.text())
        for b in w._section_btns:
            self.assertGreaterEqual(b.height(), 48, b.text())

    def test_page_pfeil_am_finger(self):
        pe = self.w._state.playback_engine
        if pe is None:
            self.skipTest("keine PlaybackEngine")
        pe.set_page(0)
        QApplication.processEvents()
        vor = next(b for b in self._pfeile() if b.text() == ">")
        zur = next(b for b in self._pfeile() if b.text() == "<")
        f = _Finger(self.w)
        # Rand des Pfeils: frueher ausserhalb der 22 px
        f.tipp(vor, QPoint(vor.width() - 4, vor.height() - 4))
        self.assertTrue(_warte(lambda: pe.current_page == 1), pe.current_page)
        f.tipp(zur, QPoint(3, 3))
        self.assertTrue(_warte(lambda: pe.current_page == 0), pe.current_page)

    def test_sektionsknopf_unterer_rand_am_finger(self):
        w = self.w
        ziel = w._section_btns[1]
        start = w._stack.currentIndex()
        if start == 1:
            ziel = w._section_btns[2]
        idx = w._section_btns.index(ziel)
        _Finger(w).tipp(ziel, QPoint(ziel.width() // 2, ziel.height() - 3))
        self.assertTrue(_warte(lambda: w._stack.currentIndex() == idx), w._stack.currentIndex())
        w._section_btns[start].click()


class KioskTest(unittest.TestCase):

    def test_kiosk_abstand_blackout_notaus(self):
        alt = tk.is_touch_mode()
        self.addCleanup(tk.setze_touch_modus, alt)
        for touch in (False, True):
            w = _fenster(touch, kiosk=True)
            try:
                bo, n = w._btn_blackout_kiosk, w._btn_laser_notaus
                self.assertGreaterEqual(n.x() - (bo.x() + bo.width()), 8, f"touch={touch}")
            finally:
                w.hide()
                w.deleteLater()
                QApplication.processEvents()


if __name__ == "__main__":
    unittest.main()
