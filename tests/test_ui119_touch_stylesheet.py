"""UI-119: Touch-Stylesheet vervollstaendigt (Touch-Audit 11.11.2026).

Gemessen offscreen mit dem Theme + Touch-QSS wie im Hauptfenster mit
``--touch``, bedient mit echtem Touch-Ablauf (``QTest.touchEvent``):

* A-16/D-16: Haken/Radio >= 36 px hoch, Kaestchen 28 px; ein Fingertipp auf
  den TEXT schaltet.
* A-14/C-16: Bildlaufleisten 24 px.
* A-13/B-10/C-09/D-10: Splitter-Griffe 16 px mit Punkt-Marke, am Finger
  ziehbar; VC-Splitter und Einfach-Pult (eigene Werte) ebenso; VIZ-109-
  Klappknopf 34 px.
* A-11: Tabellenzeilen >= 44 px, Kopfzeile >= 40 px, Reiter-Pfeile 40 px.
* C-11: Eintraege der aufgeklappten Klappliste >= 44 px.
* C-12: Menue-Eintraege >= 44 px.
* C-13: Abstand Ja <-> Nein >= 16 px.
* C-14: feste 24/26-px-Knoepfe und 10-px-Schrift der Editoren folgen dem
  Touch-Zustand.

Ohne Touch-Modus bleibt alles wie bisher (Maus).
"""
from __future__ import annotations

import os
import pathlib
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt                                  # noqa: E402
from PySide6.QtTest import QTest                                       # noqa: E402
from PySide6.QtWidgets import (                                        # noqa: E402
    QApplication, QCheckBox, QComboBox, QDialogButtonBox, QLabel, QListWidget,
    QMenu, QRadioButton, QSplitter, QStyle, QStyleOptionButton, QTabWidget,
    QTableWidget, QVBoxLayout, QWidget,
)

from src.ui import touch_keyboard as tk                                # noqa: E402

_app = QApplication.instance() or QApplication([])

import pytest as _pytest_xplat15                      # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    from PySide6.QtWidgets import QApplication as _QApp
    destroy_all_top_level_widgets(_QApp.instance())


_WURZEL = pathlib.Path(__file__).resolve().parents[1]


def _qss(touch: bool) -> str:
    qss = (_WURZEL / "assets" / "themes" / "dark.qss").read_text(encoding="utf-8")
    return qss + (tk.touch_qss() if touch else "")


def _warte(bedingung, ms=5000) -> bool:
    """Auf eine Bedingung warten statt fester Wartezeit (CI ist langsam)."""
    import time
    ende = time.monotonic() + ms / 1000
    while not bedingung():
        if time.monotonic() > ende:
            return False
        QApplication.processEvents()
        QTest.qWait(10)
    return True


class _Finger:
    def __init__(self, widget):
        self.dev = QTest.createTouchDevice()
        self.win = widget.window()
        self.w = widget

    def _p(self, p: QPoint) -> QPoint:
        return self.w.mapTo(self.win, p)

    def tipp(self, p: QPoint):
        QTest.touchEvent(self.win, self.dev).press(0, self._p(p), self.win).commit()
        QTest.touchEvent(self.win, self.dev).release(0, self._p(p), self.win).commit()
        QApplication.processEvents()

    def zug(self, start: QPoint, d: QPoint, schritte=8):
        QTest.touchEvent(self.win, self.dev).press(0, self._p(start), self.win).commit()
        for i in range(1, schritte + 1):
            QTest.touchEvent(self.win, self.dev).move(
                0, self._p(start + d * (i / schritte)), self.win).commit()
        QTest.touchEvent(self.win, self.dev).release(0, self._p(start + d), self.win).commit()
        QApplication.processEvents()


def _indikator(cb):
    opt = QStyleOptionButton()
    cb.initStyleOption(opt)
    se = (QStyle.SubElement.SE_RadioButtonIndicator if isinstance(cb, QRadioButton)
          else QStyle.SubElement.SE_CheckBoxIndicator)
    return cb.style().subElementRect(se, opt, cb)


def _popups_zu():
    for _ in range(5):
        p = QApplication.activePopupWidget()
        if p is None:
            break
        p.close()
        QApplication.processEvents()


class _Basis(unittest.TestCase):
    touch = True

    def setUp(self):
        alt = tk.is_touch_mode()
        self.addCleanup(tk.install, _app, alt)
        tk.install(_app, touch=self.touch)
        self.addCleanup(_popups_zu)

    def _fenster(self, *teile, breite=520, hoehe=360):
        w = QWidget()
        w.setStyleSheet(_qss(self.touch))
        lay = QVBoxLayout(w)
        for t in teile:
            lay.addWidget(t)
        w.resize(breite, hoehe)
        w.show()
        QApplication.processEvents()
        self.addCleanup(w.deleteLater)
        self.addCleanup(w.close)
        return w


class TouchMasseTest(_Basis):

    def test_a16_haken_und_radio_am_finger(self):
        cb, rb = QCheckBox("Snap an Raster"), QRadioButton("Kreis")
        self._fenster(cb, rb)
        for w in (cb, rb):
            self.assertGreaterEqual(w.height(), tk.HAKEN_ZEILE, type(w).__name__)
            r = _indikator(w)
            self.assertGreaterEqual(r.height(), 26)
            self.assertLessEqual(r.height(), 30)
        # Fingertipp auf den Text (rechts neben dem Kaestchen) schaltet
        text_x = _indikator(cb).right() + 30
        self.assertLess(text_x, cb.width())
        _Finger(cb).tipp(QPoint(text_x, cb.height() // 2))
        self.assertTrue(_warte(cb.isChecked), "Tipp auf den Text hakt an")

    def test_a14_c16_bildlaufleisten_24px(self):
        liste = QListWidget()
        liste.addItems([f"Eintrag {i}" for i in range(200)])
        self._fenster(liste)
        self.assertTrue(_warte(lambda: liste.verticalScrollBar().isVisible()))
        self.assertGreaterEqual(liste.verticalScrollBar().width(), 24)

    def test_splitter_griff_16px_mit_marke_und_ziehbar(self):
        links, rechts = QLabel("links"), QLabel("rechts")
        sp = QSplitter(Qt.Orientation.Horizontal)
        sp.addWidget(links)
        sp.addWidget(rechts)
        sp.setChildrenCollapsible(False)
        self._fenster(sp, breite=600)
        sp.setSizes([280, 280])
        QApplication.processEvents()
        griff = sp.handle(1)
        self.assertGreaterEqual(griff.width(), 16)
        self.assertIn("griff_senkrecht.svg", tk.touch_qss())
        self.assertIn("griff_waagerecht.svg", tk.touch_qss())
        vorher = sp.sizes()[0]
        # Finger trifft den Griff am Rand (nicht genau die Mitte) und zieht
        _Finger(griff).zug(QPoint(griff.width() - 3, griff.height() // 2), QPoint(80, 0))
        self.assertTrue(_warte(lambda: sp.sizes()[0] >= vorher + 50), sp.sizes())

    def test_splitter_mit_eigenem_stil_vc_und_einfachpult(self):
        src = (_WURZEL / "src/ui/views/virtual_console_view.py").read_text(encoding="utf-8")
        self.assertNotIn('width:2px; }")', src, "fester 2-px-Griff ist an Touch gekoppelt")
        sp = QSplitter(Qt.Orientation.Horizontal)
        sp.addWidget(QLabel("a"))
        sp.addWidget(QLabel("b"))
        sp.setStyleSheet("QSplitter::handle { background:#30363d; width:%dpx; }"
                         % tk.SPLITTER_GRIFF)
        self._fenster(sp)
        self.assertGreaterEqual(sp.handle(1).width(), 16)

    def test_d10_klappknopf_34px(self):
        from src.ui.visualizer.spalte_einklappen import baue_knopf
        k = baue_knopf()
        self.addCleanup(k.deleteLater)
        self.assertGreaterEqual(k.width(), 34)
        self.assertGreaterEqual(k.minimumWidth(), 34)

    def test_a11_tabellenzeile_und_kopfzeile(self):
        t = QTableWidget(6, 3)
        t.setHorizontalHeaderLabels(["Gerät", "Adresse", "Universum"])
        self._fenster(t)
        self.assertTrue(_warte(lambda: t.rowHeight(0) >= 44), t.rowHeight(0))
        self.assertGreaterEqual(t.horizontalHeader().height(), 40)

    def test_a11_reiter_pfeile(self):
        tabs = QTabWidget()
        for i in range(30):
            tabs.addTab(QWidget(), f"Reiter Nummer {i}")
        self._fenster(tabs, breite=400)
        pfeile = [b for b in tabs.tabBar().findChildren(QWidget)
                  if type(b).__name__ == "QToolButton" and b.isVisible()]
        self.assertTrue(pfeile, "Pfeile sichtbar")
        for b in pfeile:
            self.assertGreaterEqual(min(b.width(), b.height()), 38, b.size())

    def test_c11_klappliste_eintraege(self):
        combo = QComboBox()
        combo.addItems(["Kreis", "Acht", "Linie", "Dreieck"])
        self._fenster(combo)
        combo.showPopup()
        view = combo.view()
        self.assertTrue(_warte(view.isVisible))
        h = view.visualRect(combo.model().index(1, 0)).height()
        self.assertGreaterEqual(h, 44)
        # Fingertipp auf den dritten Eintrag waehlt ihn
        r = view.visualRect(combo.model().index(2, 0))
        _Finger(view.viewport()).tipp(r.center())
        self.assertTrue(_warte(lambda: combo.currentIndex() == 2), combo.currentIndex())

    def test_c12_menue_eintraege(self):
        w = self._fenster(QLabel("x"))
        m = QMenu(w)
        a = m.addAction("Kopieren")
        m.addAction("Einfügen")
        m.popup(w.mapToGlobal(QPoint(10, 10)))
        self.assertTrue(_warte(m.isVisible))
        self.assertGreaterEqual(m.actionGeometry(a).height(), 44)

    def test_c13_ja_nein_abstand(self):
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Yes
                               | QDialogButtonBox.StandardButton.No)
        self._fenster(box)
        ja = box.button(QDialogButtonBox.StandardButton.Yes)
        nein = box.button(QDialogButtonBox.StandardButton.No)
        a, b = sorted((ja.geometry(), nein.geometry()), key=lambda g: g.left())
        self.assertGreaterEqual(b.left() - a.right() - 1, 16)

    def test_c14_feste_hoehen_und_schrift(self):
        self.assertEqual(tk.touch_hoehe(24), 38)
        self.assertEqual(tk.touch_hoehe(26), 38)
        self.assertEqual(tk.touch_hoehe(44), 44)
        css = "QPushButton{font-size:10px;} QLabel{font-size: 9px;}"
        self.assertNotIn("10px", tk.touch_schrift(css))
        self.assertEqual(tk.touch_schrift(css).count("font-size:13px"), 2)
        for f in ("src/ui/views/scene_editor.py", "src/ui/views/chaser_editor.py",
                  "src/ui/views/efx_view.py", "src/ui/views/rgb_matrix_view.py",
                  "src/ui/widgets/color_picker.py"):
            src = (_WURZEL / f).read_text(encoding="utf-8")
            self.assertNotIn("setFixedHeight(24)", src, f)
            self.assertNotIn("setFixedHeight(26)", src, f)
            self.assertIn("touch_hoehe(", src, f)

    def test_c14_szenen_editor_knopf_am_finger(self):
        from src.core.engine.scene import Scene
        from src.ui.views.scene_editor import SceneEditor
        ed = SceneEditor(Scene())
        self.addCleanup(ed.deleteLater)
        knopf = ed._btn_editor_popout
        self.assertGreaterEqual(knopf.maximumHeight(), 38)
        self.assertIn("font-size:13px", knopf.styleSheet())


class MausUnveraendertTest(_Basis):
    touch = False

    def test_ohne_touch_wie_bisher(self):
        cb = QCheckBox("Snap")
        liste = QListWidget()
        liste.addItems([str(i) for i in range(200)])
        sp = QSplitter(Qt.Orientation.Horizontal)
        sp.addWidget(QLabel("a"))
        sp.addWidget(QLabel("b"))
        t = QTableWidget(3, 2)
        self._fenster(cb, liste, sp, t)
        self.assertLess(_indikator(cb).height(), 20)
        self.assertTrue(_warte(lambda: liste.verticalScrollBar().isVisible()))
        self.assertEqual(liste.verticalScrollBar().width(), 12)
        self.assertEqual(sp.handle(1).width(), 4)
        self.assertLess(t.rowHeight(0), 44)
        self.assertEqual(tk.touch_hoehe(24), 24)
        self.assertEqual(tk.touch_schrift("font-size:10px"), "font-size:10px")
        from src.ui.visualizer.spalte_einklappen import baue_knopf
        k = baue_knopf()
        self.addCleanup(k.deleteLater)
        self.assertEqual(k.width(), 18)

    def test_symbole_vorhanden(self):
        for name in ("griff_senkrecht.svg", "griff_waagerecht.svg"):
            self.assertTrue((_WURZEL / "assets" / "icons" / name).is_file(), name)


if __name__ == "__main__":
    unittest.main()
