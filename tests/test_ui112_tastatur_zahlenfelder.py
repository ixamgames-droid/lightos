"""UI-112: Texteingabe und Zahlenfelder am Finger (Touch-Audit C-01/C-02/D-16).

Geprueft mit echtem Touch-Ablauf ueber das Fenster (``QTest.touchEvent``,
Qt erzeugt daraus die Maus wie am Geraet) und offscreen gemessenen Groessen:

* C-01: Fingertipp in ein Textfeld oeffnet (Linux) die app-eigene
  Bildschirmtastatur; sie tippt live ins Feld, Abbruch stellt den alten Text
  her, ↵ schickt die Eingabetaste. Maus, Wisch und Feld ohne Touch-Modus:
  nichts. ``is_touch_mode()`` folgt ``install()``.
* C-02: Fingertipp in die Zahl oeffnet den Ziffernblock (OK/Abbruch, Min/Max,
  Bereich wird eingehalten); −/+ liegen links/rechts, je >= 36 px, mit
  Abstand; der Tipp auf + zaehlt weiter und oeffnet nichts.
* D-16: Haken in den Seitenspalten (``#touchSpalte``) >= 26 px, die
  Zahlenfelder der Live-Spalte tragen die Touch-Knoepfe trotz eigenem Stil.
"""
from __future__ import annotations

import os
import pathlib
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt                                  # noqa: E402
from PySide6.QtTest import QTest                                       # noqa: E402
from PySide6.QtWidgets import (                                        # noqa: E402
    QApplication, QCheckBox, QDialog, QDoubleSpinBox, QLineEdit, QSpinBox, QStyle,
    QStyleOptionButton, QStyleOptionSpinBox, QVBoxLayout, QWidget,
)

from src.ui import bildschirm_tastatur as bt                           # noqa: E402
from src.ui import touch_keyboard as tk                                # noqa: E402

_app = QApplication.instance() or QApplication([])

# XPLAT-15: keine Fenster in die naechste Datei mitnehmen (Muster test_live_view_fit).
import pytest as _pytest_xplat15                      # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    from PySide6.QtWidgets import QApplication as _QApp
    destroy_all_top_level_widgets(_QApp.instance())
_WURZEL = pathlib.Path(__file__).resolve().parents[1]


def _dark_qss(touch: bool) -> str:
    qss = (_WURZEL / "assets" / "themes" / "dark.qss").read_text(encoding="utf-8")
    return qss + (tk.touch_qss() if touch else "")


def _zu(popup) -> bool:
    """Popup geschlossen (es loescht sich dabei selbst)?"""
    from shiboken6 import isValid
    return not isValid(popup) or not popup.isVisible()


def _popups_zu():
    for _ in range(5):
        p = QApplication.activePopupWidget()
        if p is None:
            break
        p.close()
        QApplication.processEvents()


class _Finger:
    def __init__(self, widget):
        self.dev = QTest.createTouchDevice()
        self.win = widget.window()
        self.w = widget

    def _p(self, p: QPoint) -> QPoint:
        return self.w.mapTo(self.win, p)

    def tipp(self, p):
        QTest.touchEvent(self.win, self.dev).press(0, self._p(p), self.win).commit()
        QTest.touchEvent(self.win, self.dev).release(0, self._p(p), self.win).commit()
        QApplication.processEvents()

    def wisch(self, start: QPoint, d: QPoint, schritte=6):
        QTest.touchEvent(self.win, self.dev).press(0, self._p(start), self.win).commit()
        for i in range(1, schritte + 1):
            QTest.touchEvent(self.win, self.dev).move(
                0, self._p(start + d * (i / schritte)), self.win).commit()
        QTest.touchEvent(self.win, self.dev).release(0, self._p(start + d), self.win).commit()
        QApplication.processEvents()


def _knoepfe(spin):
    opt = QStyleOptionSpinBox()
    spin.initStyleOption(opt)
    st = spin.style()
    up = st.subControlRect(QStyle.ComplexControl.CC_SpinBox, opt,
                           QStyle.SubControl.SC_SpinBoxUp, spin)
    dn = st.subControlRect(QStyle.ComplexControl.CC_SpinBox, opt,
                           QStyle.SubControl.SC_SpinBoxDown, spin)
    return up, dn


class _Basis(unittest.TestCase):
    touch = True

    def setUp(self):
        alt = tk.is_touch_mode()
        self.addCleanup(tk.setze_touch_modus, alt)
        tk.install(_app, touch=self.touch)
        self.addCleanup(_popups_zu)
        self.alt_text = bt.APP_TEXT_TASTATUR
        bt.APP_TEXT_TASTATUR = True          # Linux-Weg (auch wenn hier Windows waere)
        self.addCleanup(setattr, bt, "APP_TEXT_TASTATUR", self.alt_text)

    def _fenster(self, *felder, touch_qss=None):
        w = QWidget()
        w.setStyleSheet(_dark_qss(self.touch if touch_qss is None else touch_qss))
        lay = QVBoxLayout(w)
        for f in felder:
            lay.addWidget(f)
        w.resize(420, 300)
        w.show()
        QApplication.processEvents()
        self.addCleanup(w.deleteLater)
        self.addCleanup(w.close)
        return w

    def _tipp_in_zahl(self, spin):
        le = spin.lineEdit()
        _Finger(le).tipp(le.rect().center())
        QApplication.processEvents()
        return getattr(le, "_bildschirm_popup", None)


class ZiffernblockTest(_Basis):

    def test_install_setzt_touch_zustand(self):
        self.assertTrue(tk.is_touch_mode())

    def test_fingertipp_in_zahl_oeffnet_ziffernblock(self):
        spin = QSpinBox()
        spin.setRange(1, 512)
        spin.setValue(1)
        self._fenster(spin)
        block = self._tipp_in_zahl(spin)
        self.assertIsInstance(block, bt.Ziffernblock)
        self.assertTrue(block.isVisible())
        for z in "300":
            block.tasten[z].click()
        self.assertEqual(block.anzeige.text(), "300")
        block.btn_ok.click()
        QApplication.processEvents()
        self.assertEqual(spin.value(), 300, "Adresse 300 mit drei Tipps + OK")
        self.assertTrue(_zu(block))

    def test_bereich_wird_eingehalten_min_max_abbruch(self):
        spin = QSpinBox()
        spin.setRange(0, 255)
        spin.setValue(10)
        self._fenster(spin)
        block = bt.oeffnen(spin.lineEdit())
        self.assertIn("0 … 255", block.bereich.text())
        for z in "999":
            block.tippe(z)
        self.assertEqual(block.wert(), 255)
        block.tasten["Min"].click()
        self.assertEqual(block.wert(), 0)
        block.tasten["Max"].click()
        self.assertEqual(block.wert(), 255)
        block.btn_abbruch.click()
        QApplication.processEvents()
        self.assertEqual(spin.value(), 10, "Abbruch laesst den Wert")
        self.assertNotIn("±", block.tasten, "kein Vorzeichen ohne negative Werte")

    def test_tipp_daneben_ist_abbruch(self):
        spin = QSpinBox()
        spin.setRange(0, 255)
        spin.setValue(7)
        self._fenster(spin)
        block = bt.oeffnen(spin.lineEdit())
        block.tippe("2")
        block.close()            # Qt schliesst ein Popup beim Tipp daneben
        QApplication.processEvents()
        self.assertEqual(spin.value(), 7)

    def test_echter_tipp_daneben_schliesst_ohne_knopf_dahinter(self):
        # Pruefung: ein Tipp neben den Block ist nur Abbruch. Qt reicht den
        # schliessenden Druck sonst (X11/Windows, wo das Popup die Maus
        # greift) an das Widget dahinter weiter — dort liegen GO/BLACKOUT.
        from PySide6.QtWidgets import QPushButton
        spin = QSpinBox()
        spin.setRange(0, 255)
        spin.setValue(7)
        knopf = QPushButton("BLACKOUT")
        gedrueckt = []
        knopf.pressed.connect(lambda: gedrueckt.append("pressed"))
        knopf.clicked.connect(lambda: gedrueckt.append("clicked"))
        w = self._fenster(knopf, spin)
        w.layout().insertStretch(1, 1)       # Knopf oben, Feld unten
        w.resize(420, 760)
        QApplication.processEvents()
        block = self._tipp_in_zahl(spin)
        self.assertIsInstance(block, bt.Ziffernblock)
        self.assertTrue(block.testAttribute(Qt.WidgetAttribute.WA_NoMouseReplay))
        self.assertFalse(block.geometry().contains(knopf.mapToGlobal(knopf.rect().center())))
        block.tippe("2")
        _Finger(knopf).tipp(knopf.rect().center())
        QApplication.processEvents()
        self.assertTrue(_zu(block))
        self.assertEqual(spin.value(), 7, "Tipp daneben = Abbruch")
        self.assertEqual(gedrueckt, [], "der Knopf dahinter loest nicht aus")

    def test_tastatur_reicht_tipp_daneben_nicht_weiter(self):
        kb = bt.oeffnen(self._fenster(QLineEdit()).findChild(QLineEdit))
        self.assertTrue(kb.testAttribute(Qt.WidgetAttribute.WA_NoMouseReplay))

    def test_kommazahl_und_vorzeichen(self):
        spin = QDoubleSpinBox()
        spin.setRange(-10.0, 10.0)
        spin.setDecimals(2)
        spin.setValue(0.0)
        self._fenster(spin)
        block = bt.oeffnen(spin.lineEdit())
        komma = block._komma
        for z in ("3", komma, "2", "5", "9"):
            block.tippe(z)
        self.assertEqual(block.anzeige.text(), f"3{komma}25", "nur so viele Stellen wie das Feld")
        block.tasten["±"].click()
        block.uebernehmen()
        QApplication.processEvents()
        self.assertAlmostEqual(spin.value(), -3.25)

    def test_ziffernblock_tasten_gross(self):
        spin = QSpinBox()
        self._fenster(spin)
        block = bt.oeffnen(spin.lineEdit())
        QApplication.processEvents()
        for t in list(block.tasten.values()) + [block.btn_ok, block.btn_abbruch]:
            self.assertGreaterEqual(t.height(), 44, t.text())
            self.assertGreaterEqual(t.width(), 44, t.text())
        a, b = block.tasten["1"].geometry(), block.tasten["2"].geometry()
        self.assertGreaterEqual(b.left() - a.right() - 1, 8, "Abstand zwischen Tasten")

    def test_plus_knopf_zaehlt_und_oeffnet_nichts(self):
        spin = QSpinBox()
        spin.setRange(0, 100)
        spin.setValue(5)
        self._fenster(spin)
        up, _dn = _knoepfe(spin)
        _Finger(spin).tipp(up.center())
        QApplication.processEvents()
        self.assertEqual(spin.value(), 6)
        self.assertIsNone(QApplication.activePopupWidget())

    def test_maus_klick_oeffnet_nichts(self):
        spin = QSpinBox()
        feld = QLineEdit()
        self._fenster(spin, feld)
        for le in (spin.lineEdit(), feld):
            QTest.mouseClick(le, Qt.MouseButton.LeftButton, pos=le.rect().center())
            QApplication.processEvents()
            self.assertIsNone(QApplication.activePopupWidget())

    def test_zahlenfeld_knoepfe_gross_mit_abstand(self):
        spin = QSpinBox()
        spin.setRange(0, 8000)
        self._fenster(spin)
        up, dn = _knoepfe(spin)
        for r in (up, dn):
            self.assertGreaterEqual(r.width(), 36)
            self.assertGreaterEqual(r.height(), 36)
        self.assertGreater(up.left(), dn.right(), "− links, + rechts")
        self.assertGreaterEqual(up.left() - dn.right() - 1, 8, "Abstand zwischen −/+")
        le = spin.lineEdit().geometry()
        self.assertGreaterEqual(le.left(), dn.right(), "Zahl liegt zwischen den Knoepfen")
        self.assertLessEqual(le.right(), up.left())
        self.assertGreaterEqual(le.width(), 40, "Platz fuer vierstellige Werte")


class TastaturTest(_Basis):

    def test_fingertipp_oeffnet_tastatur_und_tippt_live(self):
        feld = QLineEdit("ab")
        gesehen = []
        feld.textEdited.connect(gesehen.append)
        self._fenster(feld)
        _Finger(feld).tipp(feld.rect().center())
        QApplication.processEvents()
        kb = getattr(feld, "_bildschirm_popup", None)
        self.assertIsInstance(kb, bt.Bildschirmtastatur)
        feld.end(False)
        kb.umschalten()
        taste_q = next(t for t in kb._buchstaben if t.property("klein") == "q")
        self.assertEqual(taste_q.text(), "Q")
        taste_q.click()
        self.assertEqual(taste_q.text(), "q", "Umschalt gilt fuer ein Zeichen")
        taste_q.click()
        self.assertEqual(feld.text(), "abQq")
        self.assertTrue(gesehen, "textEdited wie beim echten Tippen (Suchfilter)")
        self.assertEqual(kb.anzeige.text(), "abQq")
        kb.loeschen()
        self.assertEqual(feld.text(), "abQ")
        kb.btn_fertig.click()
        QApplication.processEvents()
        self.assertEqual(feld.text(), "abQ")
        self.assertTrue(_zu(kb))

    def test_abbruch_stellt_text_her(self):
        feld = QLineEdit("Robin")
        self._fenster(feld)
        kb = bt.oeffnen(feld)
        kb.leeren()
        kb.tippe("x")
        self.assertEqual(feld.text(), "x")
        kb.btn_abbruch.click()
        QApplication.processEvents()
        self.assertEqual(feld.text(), "Robin")

    def test_eingabe_schickt_return(self):
        feld = QLineEdit()
        treffer = []
        feld.returnPressed.connect(lambda: treffer.append(1))
        self._fenster(feld)
        kb = bt.oeffnen(feld)
        kb.tippe("1")
        kb.btn_eingabe.click()
        QApplication.processEvents()
        self.assertEqual(treffer, [1])

    def test_tasten_gross_und_auf_dem_bildschirm(self):
        feld = QLineEdit()
        self._fenster(feld)
        kb = bt.oeffnen(feld)
        QApplication.processEvents()
        for t in kb._buchstaben + [kb.btn_fertig, kb.btn_abbruch, kb.btn_umschalt]:
            self.assertGreaterEqual(t.height(), 44)
            self.assertGreaterEqual(t.width(), 40)
        frei = feld.screen().availableGeometry()
        self.assertTrue(frei.contains(kb.frameGeometry()), "ganz auf dem Bildschirm")

    def test_wisch_nur_lesbar_und_abgeschaltet_oeffnen_nichts(self):
        feld = QLineEdit("Text zum Markieren " * 3)
        nur = QLineEdit("fest")
        nur.setReadOnly(True)
        aus = QLineEdit()
        aus.setProperty(bt.EIN_AUS, False)
        self._fenster(feld, nur, aus)
        _Finger(feld).wisch(QPoint(10, feld.height() // 2), QPoint(120, 0))
        self.assertIsNone(QApplication.activePopupWidget(), "Wisch markiert, kein Tipp")
        for f in (nur, aus):
            _Finger(f).tipp(f.rect().center())
            self.assertIsNone(QApplication.activePopupWidget())

    def test_im_modalen_dialog(self):
        dlg = QDialog()
        lay = QVBoxLayout(dlg)
        feld = QLineEdit()
        lay.addWidget(feld)
        dlg.setModal(True)
        dlg.show()
        QApplication.processEvents()
        self.addCleanup(dlg.deleteLater)
        self.addCleanup(dlg.close)
        _Finger(feld).tipp(feld.rect().center())
        kb = getattr(feld, "_bildschirm_popup", None)
        self.assertIsInstance(kb, bt.Bildschirmtastatur)
        kb.tippe("7")
        kb.fertig()
        self.assertEqual(feld.text(), "7")


class OhneTouchTest(_Basis):
    touch = False

    def test_finger_ohne_touch_modus_oeffnet_nichts(self):
        spin = QSpinBox()
        feld = QLineEdit()
        self._fenster(spin, feld)
        self.assertFalse(tk.is_touch_mode())
        self._tipp_in_zahl(spin)
        _Finger(feld).tipp(feld.rect().center())
        self.assertIsNone(QApplication.activePopupWidget())

    def test_maus_zahlenfeld_wie_bisher(self):
        spin = QSpinBox()
        self._fenster(spin)
        up, dn = _knoepfe(spin)
        self.assertLess(up.width(), 30, "ohne Touch die schmalen Pfeile")
        self.assertEqual(up.left(), dn.left(), "uebereinander wie bisher")


class SpaltenTest(_Basis):

    def _indikator(self, cb):
        opt = QStyleOptionButton()
        cb.initStyleOption(opt)
        return cb.style().subElementRect(QStyle.SubElement.SE_CheckBoxIndicator, opt, cb)

    def test_haken_in_touch_spalte(self):
        spalte = QWidget()
        spalte.setObjectName("touchSpalte")
        cb = QCheckBox("Snap", spalte)
        QVBoxLayout(spalte).addWidget(cb)
        draussen = QCheckBox("anderswo")
        self._fenster(spalte, draussen)
        r = self._indikator(cb)
        self.assertGreaterEqual(r.height(), 26)
        self.assertGreaterEqual(cb.height(), 36)
        # UI-119 (A-16): seit dem allgemeinen Touch-QSS auch ausserhalb der Spalte.
        self.assertGreaterEqual(self._indikator(draussen).height(), 26)

    def test_live_spalte_zahlenfelder_trotz_eigenem_stil(self):
        from src.ui.views.live_view import LiveView
        stil = LiveView._spinbox_style()
        self.assertIn("subcontrol-position: center right", stil)
        spin = QSpinBox()
        spin.setStyleSheet(stil)
        self._fenster(spin)
        up, dn = _knoepfe(spin)
        self.assertGreaterEqual(up.width(), 36)
        self.assertGreaterEqual(up.height(), 36)
        self.assertGreater(up.left(), dn.right())
        tk.setze_touch_modus(False)
        self.assertNotIn("subcontrol-position", LiveView._spinbox_style())

    def test_live_ansicht_am_finger_gemessen(self):
        from src.ui.views.live_view import LiveView
        lv = LiveView()
        lv.setStyleSheet(_dark_qss(True))       # wie das Hauptfenster mit --touch
        lv.resize(1200, 800)
        lv.show()
        QApplication.processEvents()
        self.assertEqual(lv._right_panel.width(), 260)
        up, dn = _knoepfe(lv._sb_world_w)
        self.assertGreaterEqual(min(up.width(), up.height(), dn.width(), dn.height()), 36)
        self.assertGreaterEqual(up.left() - dn.right() - 1, 8)
        self.assertLessEqual(lv._sb_world_w.geometry().right(),
                             lv._sb_world_w.parentWidget().width(), "passt in die Spalte")
        self.assertGreaterEqual(self._indikator(lv._cb_snap).height(), 26)
        lv.close()

    def test_spalten_tragen_den_namen(self):
        live = (_WURZEL / "src/ui/views/live_view.py").read_text(encoding="utf-8")
        viz = (_WURZEL / "src/ui/visualizer/visualizer_window.py").read_text(encoding="utf-8")
        self.assertIn('self._right_panel.setObjectName("touchSpalte")', live)
        self.assertIn('panel.setObjectName("touchSpalte")', viz)

    def test_hauptfenster_haengt_touch_qss_an(self):
        from src.ui.main_window import MainWindow

        class _F:
            _touch_mode = True
            qss = ""

            def setStyleSheet(self, s):
                self.qss = s

        f = _F()
        MainWindow._apply_theme(f)
        self.assertIn("#touchSpalte QCheckBox::indicator", f.qss)
        self.assertIn("zahl_plus.svg", f.qss)
        f._touch_mode = False
        MainWindow._apply_theme(f)
        self.assertNotIn("zahl_plus.svg", f.qss)

    def test_symbole_vorhanden(self):
        for name in ("zahl_plus.svg", "zahl_minus.svg"):
            self.assertTrue((_WURZEL / "assets" / "icons" / name).is_file(), name)


if __name__ == "__main__":
    unittest.main()
