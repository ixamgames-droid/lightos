"""UI-139 (Klick-Test 16.11.2026): Programmer bei kleiner Aufloesung.

* Fund 15: der Hilfeknopf „?“ war im Touch-Modus leer — 30 px fest breit,
  das Touch-Padding (14 px je Seite) frass das Zeichen. Jetzt am Finger
  44 x 44 px mit eigenem Innenabstand; mit der Maus wie bisher.
* Fund 6: der eingebettete Matrix-Editor bekam bei 1280 x 800 (Touch) nur
  rund 180 px; „+ Neu“, „Löschen“, „Start“, „Stop“ lagen uebereinander, die
  Liste war 23 px hoch. Jetzt: auf dem Matrix-Reiter klappt die Lampen-
  Vorschau bei knapper Hoehe von selbst zu (nicht gemerkt, beim Verlassen
  wieder wie vorher), die vier Knoepfe stehen im Touch-Modus 2 x 2, und die
  linke Spalte scrollt statt sich zu ueberlappen.
"""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                                        # noqa: E402
from PySide6.QtCore import QPoint                                    # noqa: E402
from PySide6.QtTest import QTest                                     # noqa: E402
from PySide6.QtWidgets import QApplication, QPushButton, QWhatsThis  # noqa: E402

import _ui139_masse as m                                             # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets              # noqa: E402

_app = QApplication.instance() or QApplication([])
_DEV = QTest.createTouchDevice()


@pytest.fixture(autouse=True)
def _aufraeumen():
    yield
    QWhatsThis.leaveWhatsThisMode()
    destroy_all_top_level_widgets(_app)


class _Basis(unittest.TestCase):
    def _ansicht(self, touch, groesse):
        m.touch_setzen(self, touch)
        from src.ui.views import programmer_view as pv
        gespeichert = []
        alt = pv._save_prefs
        pv._save_prefs = lambda d: gespeichert.append(dict(d))
        self.addCleanup(setattr, pv, "_save_prefs", alt)
        self.gespeichert = gespeichert
        r = m.Rahmen(touch, groesse)
        v = r.zeige(pv.ProgrammerView())
        self._r = r
        return r, v


class HilfeknopfTest(_Basis):
    def test_fragezeichen_sichtbar(self):
        for touch in (False, True):
            for name, groesse in m.KLEIN.items():
                r, v = self._ansicht(touch, groesse)
                b = v._btn_help
                with self.subTest(touch=touch, aufl=name):
                    self.assertEqual(b.text(), "?")
                    self.assertTrue(m.text_passt(b), f"„?“ passt nicht in {b.size()}")
                    if touch:
                        self.assertGreaterEqual(b.width(), 44)
                        self.assertGreaterEqual(b.height(), 44)
                    else:
                        self.assertEqual(b.width(), 30)
                r.close()

    def test_fingertipp_startet_hilfemodus(self):
        r, v = self._ansicht(True, m.KLEIN["1280x800"])
        b = v._btn_help
        p = b.mapTo(r, QPoint(b.width() // 2, b.height() // 2))
        QTest.touchEvent(r, _DEV).press(0, p, r).commit()
        QTest.touchEvent(r, _DEV).release(0, p, r).commit()
        QApplication.processEvents()
        self.assertTrue(QWhatsThis.inWhatsThisMode())


class MatrixReiterTest(_Basis):
    def _matrix(self, v):
        v._main_tabs.setCurrentIndex(v._matrix_tab_index)
        for _ in range(6):
            QApplication.processEvents()
        return v._embedded_rgb

    def _knoepfe(self, rgb):
        return [b for b in rgb.findChildren(QPushButton)
                if b.text() in ("+ Neu", "Löschen", "▶ Start", "■ Stop")]

    def test_knoepfe_ueberlappen_nicht_und_liste_ist_bedienbar(self):
        for touch in (False, True):
            for name, groesse in m.KLEIN.items():
                r, v = self._ansicht(touch, groesse)
                rgb = self._matrix(v)
                knoepfe = self._knoepfe(rgb)
                self.assertEqual(len(knoepfe), 4)
                rects = [b.geometry().translated(b.parentWidget().mapTo(rgb, QPoint(0, 0)))
                         for b in knoepfe]
                with self.subTest(touch=touch, aufl=name):
                    for i, a in enumerate(rects):
                        for b in rects[i + 1:]:
                            self.assertFalse(a.intersects(b), f"{a} ueberlappt {b}")
                    for k in knoepfe:
                        self.assertTrue(m.text_passt(k), k.text())
                        if touch:
                            self.assertGreaterEqual(k.height(), 44)
                    self.assertGreaterEqual(rgb._list.height(), 60,
                                            "Matrix-Liste zu niedrig")
                r.close()

    def test_vorschau_klappt_bei_knapper_hoehe_zu_und_wieder_auf(self):
        r, v = self._ansicht(True, m.KLEIN["1280x800"])
        tp = v._tile_preview
        tp.set_collapsed(False)
        vorher = v._rgb_page.height()
        self._matrix(v)
        self.assertTrue(tp.is_collapsed(), "Vorschau blieb auf dem Matrix-Reiter offen")
        for _ in range(4):
            QApplication.processEvents()
        self.assertGreater(v._rgb_page.height(), 179)
        v._main_tabs.setCurrentIndex(0)
        QApplication.processEvents()
        self.assertFalse(tp.is_collapsed(), "Vorschau kam nicht zurueck")
        self.assertEqual(self.gespeichert, [], "automatisches Zuklappen wurde gemerkt")
        del vorher

    def test_viel_platz_laesst_die_vorschau_offen(self):
        r, v = self._ansicht(False, (1920, 950))
        tp = v._tile_preview
        tp.set_collapsed(False)
        self._matrix(v)
        self.assertFalse(tp.is_collapsed())

    def test_von_hand_zugeklappt_bleibt_zu(self):
        r, v = self._ansicht(True, m.KLEIN["1280x800"])
        tp = v._tile_preview
        tp.set_collapsed(True)
        self._matrix(v)
        v._main_tabs.setCurrentIndex(0)
        QApplication.processEvents()
        self.assertTrue(tp.is_collapsed())


if __name__ == "__main__":
    unittest.main()
