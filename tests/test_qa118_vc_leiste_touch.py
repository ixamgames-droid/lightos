"""QA-118 (e): „Mehrfach“ und „Touch-Lock“ sind im ECHTEN Hauptfenster >= 44 px hoch.

**Der Befund (Touch-Probe 15.11.2026, Windows x64, echte App ``--touch``,
250 %).** Beide Knoepfe der VC-Werkzeugleiste waren 40 px hoch, obwohl die
Ansicht sie mit ``setFixedHeight(44)`` baut und ``test_ui121``/``test_ui126``
in der EINZELNEN Ansicht >= 44 messen. Ursache: das Touch-Stylesheet des
Hauptfensters (``QPushButton { min-height: 38px; ... }``) ueberschreibt beim
Polieren das Minimum aus ``setFixedHeight`` - uebrig bleiben 38 + 2 px Rand.
Gemessen wird deshalb hier im gebauten Hauptfenster.
"""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication                           # noqa: E402

_app = QApplication.instance() or QApplication([])


def _fenster(touch: bool):
    from src.ui.main_window import MainWindow
    w = MainWindow(touch=touch)
    w._hw_timer.stop()
    w.resize(1440, 900)
    w.show()
    for _ in range(5):
        QApplication.processEvents()
    return w


def _vc(fenster):
    from src.ui.views.virtual_console_view import VirtualConsoleView
    return fenster.findChildren(VirtualConsoleView)[0]


class LeisteImHauptfensterTest(unittest.TestCase):

    def tearDown(self):
        from src.ui import touch_keyboard as tk
        tk.setze_touch_modus(False)

    def _bearbeiten(self, touch: bool):
        w = _fenster(touch)
        self.addCleanup(w.deleteLater)
        self.addCleanup(w.close)
        v = _vc(w)
        v._btn_edit.setChecked(True)
        v.show()
        for _ in range(5):
            QApplication.processEvents()
        return v

    def test_touch_mehrfach_und_sperre_44px(self):
        v = self._bearbeiten(True)
        for name in ("_btn_mehrfach", "_btn_touch_lock"):
            k = getattr(v, name)
            with self.subTest(knopf=k.text()):
                self.assertTrue(k.isVisible(), k.text())
                self.assertGreaterEqual(k.height(), 44,
                                        f"{k.text()}: {k.height()} px im Hauptfenster")

    def test_touch_alle_festen_leistenknoepfe_44px(self):
        """Dieselbe Ursache trifft jeden Knopf, den die Leiste auf 44 px setzt."""
        from PySide6.QtWidgets import QPushButton
        v = self._bearbeiten(True)
        zu_klein = [(b.text(), b.height()) for b in v._toolbar_widget.findChildren(QPushButton)
                    if b.isVisible() and b.maximumHeight() == 44 and b.height() < 44]
        self.assertEqual([], zu_klein)

    def test_touch_bank_und_bearbeiten_behalten_ihre_feste_hoehe(self):
        """QA-120: auch Knoepfe mit eigener Polsterung oder anderer Hoehe.

        Gemessen mit QA-118 (e): Bank ◀/▶ 52 statt 56 px, Bank-Etikett 38
        statt 56, „Bearbeiten“ 56 statt 44 - die Fenster-Polsterung
        (``padding: 6px 14px``) kam zur eigenen ``min-height`` dazu."""
        v = self._bearbeiten(True)
        soll = {"_btn_bank_prev": 56, "_lbl_bank": 56, "_btn_bank_next": 56,
                "_btn_edit": 44, "_btn_mehrfach": 44, "_btn_touch_lock": 44}
        ist = {name: getattr(v, name).height() for name in soll}
        self.assertEqual(soll, ist)

    def test_touch_hoehe_haelt_auch_nach_neuem_fenster_stylesheet(self):
        """QA-120: setzt das Fenster sein Stylesheet neu (Touch-Modus, Thema),
        wird jeder Knopf neu poliert - die feste Hoehe muss das ueberstehen."""
        v = self._bearbeiten(True)
        w = v.window()
        w.setStyleSheet(w.styleSheet() + "\nQPushButton { min-height: 30px; }\n")
        for _ in range(5):
            QApplication.processEvents()
        self.assertEqual((56, 56, 44), (v._btn_bank_prev.height(), v._lbl_bank.height(),
                                        v._btn_edit.height()))

    def test_maus_leiste_bleibt_flach(self):
        """Gegenprobe: ohne Touch bleibt die Leiste wie bisher (26 px)."""
        v = self._bearbeiten(False)
        self.assertLessEqual(v._btn_touch_lock.height(), 30, v._btn_touch_lock.height())


if __name__ == "__main__":
    unittest.main()
