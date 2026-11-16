"""QA-121 (Fund 1): Umschalt + 'ß' auf der Bildschirmtastatur.

'ß'.upper() ist in Python 'SS' (zwei Zeichen). Die Taste darf im Gross-Modus
nicht 'SS' zeigen und nicht zwei Zeichen tippen. Jede Buchstabentaste traegt
im Gross-Modus genau ein Zeichen. Bedient wird mit dem Finger
(``QTest.touchEvent``), wie am Geraet.
"""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                                          # noqa: E402
from PySide6.QtTest import QTest                                       # noqa: E402
from PySide6.QtWidgets import QApplication, QLineEdit, QVBoxLayout, QWidget  # noqa: E402

from src.ui import bildschirm_tastatur as bt                           # noqa: E402
from src.ui import touch_keyboard as tk                                # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets               # noqa: E402

_app = QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _keine_fenster_mitnehmen():
    yield
    destroy_all_top_level_widgets(QApplication.instance())


def _finger_tipp(widget):
    dev = QTest.createTouchDevice()
    win = widget.window()
    p = widget.mapTo(win, widget.rect().center())
    QTest.touchEvent(win, dev).press(0, p, win).commit()
    QTest.touchEvent(win, dev).release(0, p, win).commit()
    QApplication.processEvents()


class EszettTest(unittest.TestCase):

    def setUp(self):
        alt = tk.is_touch_mode()
        self.addCleanup(tk.setze_touch_modus, alt)
        tk.install(_app, touch=True)
        alt_app = bt.APP_TEXT_TASTATUR
        bt.APP_TEXT_TASTATUR = True
        self.addCleanup(setattr, bt, "APP_TEXT_TASTATUR", alt_app)
        self.w = QWidget()
        lay = QVBoxLayout(self.w)
        self.feld = QLineEdit("Stra")
        lay.addWidget(self.feld)
        self.w.resize(420, 200)
        self.w.show()
        QApplication.processEvents()
        self.addCleanup(self.w.close)
        self.kb = bt.Bildschirmtastatur(self.feld)
        self.kb.show()
        QApplication.processEvents()
        self.addCleanup(self.kb.close)
        self.feld.end(False)

    def _taste(self, klein):
        return next(t for t in self.kb._buchstaben if t.property("klein") == klein)

    def test_gross_modus_jede_buchstabentaste_ein_zeichen(self):
        self.kb.umschalten()
        for t in self.kb._buchstaben:
            self.assertEqual(len(t.text()), 1, f"Taste {t.property('klein')!r}: {t.text()!r}")

    def test_umschalt_eszett_tippt_ein_zeichen_per_finger(self):
        _finger_tipp(self.kb.btn_umschalt)
        eszett = self._taste("ß")
        self.assertNotEqual(eszett.text(), "SS")
        _finger_tipp(eszett)
        self.assertEqual(self.feld.text(), "Straß")
        # normale Buchstaben werden weiter gross
        _finger_tipp(self.kb.btn_umschalt)
        _finger_tipp(self._taste("e"))
        self.assertEqual(self.feld.text(), "StraßE")


if __name__ == "__main__":
    unittest.main()
