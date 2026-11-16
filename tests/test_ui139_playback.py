"""UI-139 (Klick-Test 16.11.2026, Fund 4): Playback im Touch-Modus.

* Page-Knoepfe waren fest 34 px breit — mit Touch-Schrift und -Innenabstand
  blieb von „10“ nur „(“ (mit der Maus fehlte bei „10“ auch schon ein Stueck).
* GO/◄/FL je Executor: 32 px breit, das Zahnrad 18 px breit.
* Die Kurven-Auswahl zeigte „S-Kurve (Standarc“ und war hoeher als ihre Zeile.

Gemessen offscreen bei kleiner Aufloesung mit dem Fenster-Stylesheet; mit der
Maus bleibt die Leiste kompakt.
"""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                                        # noqa: E402
from PySide6.QtCore import QPoint                                    # noqa: E402
from PySide6.QtTest import QTest                                     # noqa: E402
from PySide6.QtWidgets import QApplication, QComboBox                # noqa: E402

import _ui139_masse as m                                             # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets              # noqa: E402
from src.core.engine import fade_curve                               # noqa: E402

_app = QApplication.instance() or QApplication([])
_DEV = QTest.createTouchDevice()


@pytest.fixture(autouse=True)
def _aufraeumen():
    yield
    destroy_all_top_level_widgets(_app)


def _combo_text_passt(cb: QComboBox) -> bool:
    from PySide6.QtWidgets import QStyle, QStyleOptionComboBox
    cb.ensurePolished()
    opt = QStyleOptionComboBox()
    cb.initStyleOption(opt)
    feld = cb.style().subControlRect(QStyle.ComplexControl.CC_ComboBox, opt,
                                     QStyle.SubControl.SC_ComboBoxEditField, cb)
    return cb.fontMetrics().horizontalAdvance(cb.currentText()) <= feld.width()


class _Basis(unittest.TestCase):
    def _ansicht(self, touch, groesse):
        m.touch_setzen(self, touch)
        from src.ui.views.playback_view import PlaybackView
        r = m.Rahmen(touch, groesse)
        return r, r.zeige(PlaybackView())


class PageKnoepfeTest(_Basis):
    def test_ziffern_ganz_lesbar(self):
        for touch in (False, True):
            for name, groesse in m.KLEIN.items():
                r, v = self._ansicht(touch, groesse)
                for b in v._page_buttons:
                    with self.subTest(touch=touch, aufl=name, page=b.text()):
                        self.assertTrue(m.text_passt(b), f"{b.text()} in {b.size()}")
                        if touch:
                            self.assertGreaterEqual(b.height(), 44)
                            self.assertGreaterEqual(b.width(), 44)
                r.close()

    def test_maus_bleibt_kompakt(self):
        r, v = self._ansicht(False, m.KLEIN["1366x768"])
        for b in v._page_buttons:
            self.assertLessEqual(b.width(), 40)
            self.assertLessEqual(b.height(), 32)

    def test_maus_hoehe_wie_bisher(self):
        """Nachbesserung nach Pruefung: mit der Maus waren die Page-Knoepfe
        32 px hoch (Theme: min-height 22 + Innenabstand 4 + Rand) — der
        schmale Innenabstand darf sie nicht auf 26 px schrumpfen lassen."""
        r, v = self._ansicht(False, m.KLEIN["1366x768"])
        for b in v._page_buttons:
            with self.subTest(page=b.text()):
                self.assertEqual(b.height(), 32)
                self.assertTrue(m.text_passt(b), b.text())

    def test_fingertipp_auf_page_10(self):
        r, v = self._ansicht(True, m.KLEIN["1280x800"])
        b = v._page_buttons[9]
        p = b.mapTo(r, QPoint(b.width() // 2, b.height() // 2))
        QTest.touchEvent(r, _DEV).press(0, p, r).commit()
        QTest.touchEvent(r, _DEV).release(0, p, r).commit()
        QApplication.processEvents()
        self.assertTrue(b.isChecked())
        v._switch_page(0)


class ExecutorTest(_Basis):
    def test_touch_tasten_und_zahnrad(self):
        for name, groesse in m.KLEIN.items():
            r, v = self._ansicht(True, groesse)
            for ex in v._executors_widgets:
                for b in ex._fn_buttons:
                    with self.subTest(aufl=name, ex=ex._slot, taste=b.text()):
                        self.assertGreaterEqual(b.height(), 44)
                        self.assertGreaterEqual(b.width(), 44)
                        self.assertTrue(m.text_passt(b))
                with self.subTest(aufl=name, ex=ex._slot, taste="Zahnrad"):
                    self.assertGreaterEqual(ex._btn_cfg.width(), 32)
                    self.assertGreaterEqual(ex._btn_cfg.height(), 32)
                    self.assertTrue(m.text_passt(ex._btn_cfg))
            r.close()

    def test_maus_bleibt_wie_bisher(self):
        r, v = self._ansicht(False, m.KLEIN["1366x768"])
        ex = v._executors_widgets[0]
        self.assertEqual(ex._btn_cfg.width(), 18)
        self.assertLessEqual(ex.width(), 110)
        for b in ex._fn_buttons:
            self.assertTrue(m.text_passt(b))
            self.assertLessEqual(b.height(), 30)


class KurvenAuswahlTest(_Basis):
    def _mit_cues(self, touch, groesse):
        from src.core.app_state import get_state
        from src.core.engine.cue import Cue
        from src.core.engine.cue_stack import CueStack
        st = get_state()
        stack = CueStack("UI139 Liste")
        for i in range(3):
            stack.cues.append(Cue(number=float(i + 1), label=f"C{i}"))
        alt = list(st.cue_stacks)
        st.cue_stacks.append(stack)
        self.addCleanup(lambda: st.cue_stacks.__setitem__(slice(None), alt))
        r, v = self._ansicht(touch, groesse)
        v._current_stack = stack
        v._refresh_table()
        for _ in range(3):
            QApplication.processEvents()
        return r, v

    def test_kurzname_ganz_lesbar_und_passt_in_die_zeile(self):
        for touch in (False, True):
            for name, groesse in m.KLEIN.items():
                r, v = self._mit_cues(touch, groesse)
                t = v._table
                for zeile in range(t.rowCount()):
                    cb = t.cellWidget(zeile, 6)
                    with self.subTest(touch=touch, aufl=name, zeile=zeile):
                        self.assertEqual(cb.currentText(), "S-Kurve")
                        self.assertTrue(_combo_text_passt(cb),
                                        f"{cb.currentText()} in {cb.width()} px")
                        self.assertLessEqual(cb.height(), t.rowHeight(zeile))
                        self.assertIn("S-Kurve (Standard)",
                                      cb.itemData(0, 3) or cb.toolTip())
                r.close()

    def test_wahl_schreibt_weiter_den_namen(self):
        r, v = self._mit_cues(False, m.KLEIN["1366x768"])
        cb = v._table.cellWidget(0, 6)
        cb.setCurrentIndex(fade_curve.CURVE_NAMES.index("linear"))
        self.assertEqual(v._current_stack.cues[0].fade_curve, "linear")


if __name__ == "__main__":
    unittest.main()
