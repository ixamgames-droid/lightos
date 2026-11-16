"""UI-140: Klick-Test Hauptfenster — Kontrollkaestchen ohne Haken, Menue
„Command“ doppelt.

Fund 1: Das dunkle Theme zeichnete eine angehakte QCheckBox blau, eine nicht
angehakte grau, beide ohne Haken; ankreuzbare Menue-Eintraege zeigten AUS gar
nichts. Geprueft wird per Pixelprobe mit dem ECHTEN Stylesheet des
Hauptfensters (``MainWindow._apply_theme`` an einem Stellvertreter-Widget),
Maus und Touch:

* AN: blaues Feld MIT hellem Haken darin.
* AUS: leerer Rahmen — heller Rand, dunkles Inneres, kein Blau.
* Menue: AUS-Eintrag hat ein sichtbares Kaestchen, ein normaler Eintrag nicht;
  Touch-Zeile bleibt >= 44 px, Maus-Zeile waechst nicht.
* Ein Fingertipp auf die Kaestchen-Zeile schaltet weiter.

Fund 2: Menue „Befehl“ mit EINEM Eintrag fuer ``:`` und F12; der umbenannte
Simulations-Schalter verspricht nicht „kein DMX-Ausgang“ (er schaltet nichts ab).
"""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QRect                                # noqa: E402
from PySide6.QtGui import QAction, QColor, QImage, QKeySequence        # noqa: E402
from PySide6.QtTest import QTest                                        # noqa: E402
from PySide6.QtWidgets import (                                         # noqa: E402
    QApplication, QCheckBox, QMenu, QStyle, QStyleOptionButton, QVBoxLayout,
    QWidget,
)

from _qt_lifecycle import destroy_all_top_level_widgets                # noqa: E402

_app = QApplication.instance() or QApplication([])

def _warte(bedingung, ms=5000) -> bool:
    import time
    ende = time.monotonic() + ms / 1000
    while not bedingung():
        if time.monotonic() > ende:
            return False
        QApplication.processEvents()
        QTest.qWait(10)
    return True


class _Stellvertreter(QWidget):
    """Traegt nur, was ``MainWindow._apply_theme`` liest/schreibt."""

    def __init__(self, touch: bool):
        super().__init__()
        self._touch_mode = touch


def _fenster(touch: bool) -> QWidget:
    from src.ui.main_window import MainWindow
    w = _Stellvertreter(touch)
    MainWindow._apply_theme(w)
    w.setStyleSheet(w.styleSheet())
    return w


def _hell(c: QColor) -> int:
    return (c.red() * 299 + c.green() * 587 + c.blue() * 114) // 1000


def _blau(c: QColor) -> bool:
    return c.blue() > 180 and c.red() < 80 and c.green() < 160


def _weiss(c: QColor) -> bool:
    return c.red() > 200 and c.green() > 200 and c.blue() > 200


def _pixel(img: QImage, r: QRect):
    return [img.pixelColor(x, y) for y in range(r.top(), r.bottom() + 1)
            for x in range(r.left(), r.right() + 1)]


def _indikator(cb: QCheckBox) -> QRect:
    opt = QStyleOptionButton()
    cb.initStyleOption(opt)
    return cb.style().subElementRect(QStyle.SubElement.SE_CheckBoxIndicator, opt, cb)


class KontrollkaestchenTest(unittest.TestCase):

    def tearDown(self):
        destroy_all_top_level_widgets(QApplication.instance())

    def _bau(self, touch: bool):
        w = _fenster(touch)
        lay = QVBoxLayout(w)
        an, aus = QCheckBox("Snap"), QCheckBox("Raster zeigen")
        an.setChecked(True)
        lay.addWidget(an)
        lay.addWidget(aus)
        w.resize(320, 160)
        w.show()
        self.assertTrue(_warte(lambda: w.isVisible()))
        QApplication.processEvents()
        return w, an, aus

    def _pruefe(self, touch: bool):
        w, an, aus = self._bau(touch)
        for cb, ist_an in ((an, True), (aus, False)):
            img = cb.grab().toImage()
            r = _indikator(cb)
            px = _pixel(img, r)
            if ist_an:
                self.assertTrue(any(_blau(c) for c in px), "AN ohne blaues Feld")
                self.assertGreater(sum(_weiss(c) for c in px), 4,
                                   f"AN ohne Haken (touch={touch})")
            else:
                self.assertFalse(any(_blau(c) for c in px), "AUS ist blau")
                rand = _pixel(img, QRect(r.left(), r.center().y(), 1, 1))
                rand += _pixel(img, QRect(r.center().x(), r.top(), 1, 1))
                self.assertTrue(all(_hell(c) > 140 for c in rand),
                                f"AUS ohne hellen Rahmen (touch={touch}): "
                                f"{[c.name() for c in rand]}")
                innen = _pixel(img, r.adjusted(3, 3, -3, -3))
                self.assertTrue(all(_hell(c) < 60 for c in innen),
                                f"AUS-Kaestchen nicht leer (touch={touch})")
        if touch:
            self.assertGreaterEqual(_indikator(an).height(), 26)
            self.assertGreaterEqual(an.height(), 36)
        else:
            self.assertEqual(_indikator(an).height(), 16, "Maus-Kaestchen veraendert")
        return w, an, aus

    def test_maus_an_und_aus_eindeutig(self):
        self._pruefe(False)

    def test_touch_an_und_aus_eindeutig(self):
        self._pruefe(True)

    def test_touch_fingertipp_schaltet_weiter(self):
        from src.ui import touch_keyboard as tk
        alt = tk.is_touch_mode()
        self.addCleanup(tk.install, _app, alt)
        tk.install(_app, touch=True)
        w, an, aus = self._pruefe(True)
        dev = QTest.createTouchDevice()
        # auf das Kaestchen selbst und auf den Text
        p = aus.mapTo(w, _indikator(aus).center())
        QTest.touchEvent(w, dev).press(0, p, w).commit()
        QTest.touchEvent(w, dev).release(0, p, w).commit()
        QApplication.processEvents()
        self.assertTrue(_warte(aus.isChecked), "Fingertipp aufs Kaestchen schaltet nicht")
        p = an.mapTo(w, QPoint(_indikator(an).right() + 30, an.height() // 2))
        QTest.touchEvent(w, dev).press(0, p, w).commit()
        QTest.touchEvent(w, dev).release(0, p, w).commit()
        QApplication.processEvents()
        self.assertTrue(_warte(lambda: not an.isChecked()), "Fingertipp auf den Text schaltet nicht")


class MenueKaestchenTest(unittest.TestCase):

    def tearDown(self):
        destroy_all_top_level_widgets(QApplication.instance())

    def _menue(self, touch: bool):
        w = self._w = _fenster(touch)   # Referenz halten: traegt das Menue
        w.resize(300, 200)
        w.show()
        m = QMenu(w)
        normal = m.addAction("Konfigurieren...")
        an = m.addAction("Hinweis bei neuem DMX-Interface")
        an.setCheckable(True)
        an.setChecked(True)
        aus = m.addAction("Simulations-Hinweis")
        aus.setCheckable(True)
        m.popup(w.mapToGlobal(QPoint(10, 10)))
        self.assertTrue(_warte(m.isVisible))
        QApplication.processEvents()
        img = m.grab().toImage()
        return m, img, normal, an, aus

    def _links(self, m, img, act, touch):
        g = m.actionGeometry(act)
        # Kaestchen-Spalte links vom Text (Text beginnt erst dahinter):
        # Abstand links + Kaestchen + Rand.
        breite = 32 if touch else 22
        return _pixel(img, QRect(g.left(), g.top(), breite, g.height()))

    def _pruefe(self, touch: bool):
        m, img, normal, an, aus = self._menue(touch)
        self.assertFalse(any(_hell(c) > 140 for c in self._links(m, img, normal, touch)),
                         "normaler Eintrag hat ploetzlich ein Kaestchen")
        px_aus = self._links(m, img, aus, touch)
        self.assertGreater(sum(_hell(c) > 140 for c in px_aus), 20,
                           f"AUS-Eintrag ohne sichtbares Kaestchen (touch={touch})")
        self.assertFalse(any(_blau(c) for c in px_aus))
        px_an = self._links(m, img, an, touch)
        self.assertTrue(any(_blau(c) for c in px_an))
        self.assertGreater(sum(_weiss(c) for c in px_an), 4, "AN ohne Haken")
        return m, normal, an, aus

    def test_maus_menue(self):
        m, normal, an, aus = self._pruefe(False)
        h = m.actionGeometry(aus).height()
        self.assertEqual(h, m.actionGeometry(normal).height())
        self.assertLessEqual(h, 30, "Maus-Menuezeile ist gewachsen")

    def test_touch_menue_zeile_bleibt_gross(self):
        m, normal, an, aus = self._pruefe(True)
        for a in (normal, an, aus):
            self.assertGreaterEqual(m.actionGeometry(a).height(), 44)


class HauptfensterMenueTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from src.core.show import show_file as SF
        from src.ui import main_window as mw
        cls.tmp = tempfile.mkdtemp(prefix="lightos_ui140_")
        SF.reset_show()
        cls.win = mw.MainWindow()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.win.deleteLater()
        except Exception:
            pass
        destroy_all_top_level_widgets()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _menues(self):
        return {m.title().replace("&", ""): m
                for m in self.win.menuBar().findChildren(QMenu) if m.title()}

    def test_befehl_menue_ein_eintrag_beide_kuerzel(self):
        menues = self._menues()
        self.assertNotIn("Command", menues)
        self.assertIn("Befehl", menues)
        acts = [a for a in menues["Befehl"].actions() if not a.isSeparator()]
        self.assertEqual([a.text() for a in acts], ["Befehlszeile fokussieren"])
        kuerzel = {s.toString() for s in acts[0].shortcuts()}
        self.assertEqual(kuerzel, {":", "F12"})

    def test_kuerzel_eindeutig_in_der_menueleiste(self):
        gesehen = {}
        for a in self.win.menuBar().findChildren(QAction):
            for s in a.shortcuts():
                t = s.toString()
                if t in (":", "F12"):
                    gesehen.setdefault(t, []).append(a.text())
        self.assertEqual(gesehen, {":": ["Befehlszeile fokussieren"],
                                   "F12": ["Befehlszeile fokussieren"]})

    def test_menue_mnemonics_befehl_kollidiert_nicht_mit_bearbeiten(self):
        titel = [m.title() for m in self._menues().values()]
        befehl = next(t for t in titel if t.replace("&", "") == "Befehl")
        buchstabe = befehl[befehl.index("&") + 1].lower()
        self.assertNotEqual(buchstabe, "b")

    def test_simulation_verspricht_keine_abschaltung(self):
        act = self.win._act_mock
        self.assertNotIn("Mock Mode", act.text())
        self.assertNotIn("kein DMX", act.text())
        self.assertIn("läuft", act.toolTip())
        self.assertTrue(self._menues()["Ausgabe"].toolTipsVisible())
        # Verhalten unveraendert: zeigt MOCK, schaltet nichts ab.
        act.setChecked(False)

    def test_hauptfenster_stylesheet_hat_haken(self):
        self.assertIn("haken.svg", self.win.styleSheet())
        from src.ui.haken_stil import haken_url
        self.assertTrue(os.path.isfile(haken_url()))
        self.assertTrue(os.path.isabs(haken_url()))
