"""UI-139 (Klick-Test 16.11.2026, Fund 5): Simple-Desk-Fader am Finger.

Jeder Kanalstreifen war fest 36 x 124 px, der Griff 12 px, die Beschriftung
7-8 px — auch im Touch-Modus; darunter blieben rund 350 px leer. Jetzt im
Touch-Modus: Streifen >= 48 px breit, Griff >= 36 px, Schrift >= 11 px, die
Hoehe waechst mit dem Platz; das Geraete-Band ueber den Fadern bleibt
deckungsgleich. Mit der Maus bleibt alles wie bisher (36 x 124 px).
"""
from __future__ import annotations

import os
import re
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                                        # noqa: E402
from PySide6.QtCore import QPoint                                    # noqa: E402
from PySide6.QtTest import QTest                                     # noqa: E402
from PySide6.QtWidgets import QApplication, QStyle, QStyleOptionSlider  # noqa: E402

import _ui139_masse as m                                             # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets              # noqa: E402

_app = QApplication.instance() or QApplication([])
_DEV = QTest.createTouchDevice()


@pytest.fixture(autouse=True)
def _aufraeumen():
    yield
    destroy_all_top_level_widgets(_app)


def _griff(slider):
    opt = QStyleOptionSlider()
    slider.initStyleOption(opt)
    return slider.style().subControlRect(
        QStyle.ComplexControl.CC_Slider, opt, QStyle.SubControl.SC_SliderHandle, slider)


def _schrift_px(label) -> int:
    t = re.search(r"font-size\s*:\s*(\d+)px", label.styleSheet())
    return int(t.group(1)) if t else label.font().pixelSize()


class _Basis(unittest.TestCase):
    def _ansicht(self, touch, groesse=(1920, 870)):
        m.touch_setzen(self, touch)
        from src.ui.views.simple_desk import SimpleDeskView
        r = m.Rahmen(touch, groesse)
        return r, r.zeige(SimpleDeskView())


class FaderTouchTest(_Basis):
    def test_touch_streifen_griff_schrift(self):
        for name, groesse in list(m.KLEIN.items()) + [("1920x1080", (1920, 870))]:
            r, v = self._ansicht(True, groesse)
            f = v._faders[0]
            with self.subTest(aufl=name):
                self.assertGreaterEqual(f.width(), 48)
                g = _griff(f._slider)
                self.assertGreaterEqual(min(g.width(), g.height()), 36, g)
                for lbl in (f._val_lbl, f._attr_lbl, f._ch_lbl):
                    self.assertGreaterEqual(_schrift_px(lbl), 11, lbl.styleSheet())
                self.assertTrue(m.sichtbar_in(f, v), "Fader ragt aus der Ansicht")
            r.close()

    def test_touch_hoehe_waechst_mit_dem_platz(self):
        r, v = self._ansicht(True, (1920, 870))
        f = v._faders[0]
        flaeche = v._scroll.viewport().height()
        self.assertGreater(f.height(), 124)
        self.assertGreaterEqual(f.height(), flaeche - v._header_band.height() - 40,
                                "unter den Fadern bleibt die Flaeche leer")

    def test_band_deckt_die_fader(self):
        r, v = self._ansicht(True)
        band = v._header_band
        for kanal in (1, 2, 9, 40):
            f = v._faders[kanal - 1]
            x = f.mapTo(band.parentWidget(), QPoint(0, 0)).x()
            self.assertEqual(band._x_for(kanal), x - band.x(), kanal)

    def test_fingerzug_stellt_den_fader(self):
        r, v = self._ansicht(True, m.KLEIN["1280x800"])
        v._override_cb.setChecked(True)             # sonst reine Anzeige
        s = v._faders[0]._slider
        try:
            self.assertTrue(s.isEnabled())
            g = _griff(s)
            start = s.mapTo(r, g.center())
            ziel = s.mapTo(r, QPoint(g.center().x(), 4))
            QTest.touchEvent(r, _DEV).press(0, start, r).commit()
            for i in range(1, 7):
                QTest.touchEvent(r, _DEV).move(
                    0, start + (ziel - start) * (i / 6), r).commit()
            QTest.touchEvent(r, _DEV).release(0, ziel, r).commit()
            QApplication.processEvents()
            self.assertGreater(s.value(), 200)
        finally:
            s.setValue(0)
            v._override_cb.setChecked(False)


class FaderMausTest(_Basis):
    def test_maus_wie_bisher(self):
        r, v = self._ansicht(False, m.KLEIN["1366x768"])
        f = v._faders[0]
        self.assertEqual((f.width(), f.height()), (36, 124))
        band = v._header_band
        x = v._faders[4].mapTo(band.parentWidget(), QPoint(0, 0)).x()
        self.assertEqual(band._x_for(5), x - band.x())


if __name__ == "__main__":
    unittest.main()
