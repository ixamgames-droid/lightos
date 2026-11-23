"""UI-146: Klicktest-Befunde Programmer/Befehlszeile.

1. Tab in der Befehlszeile vervollstaendigte nicht und nahm ihr den Fokus
   (Qt verbraucht Tab fuer den Fokuswechsel vor ``keyPressEvent``); bei 'cl'
   gewann der exakte Kurz-Treffer 'cl' vor 'clear'.
2. Danach loeste weiteres Tippen Fenster-Kuerzel aus (H = Highlight schaltete
   alle gewaehlten Geraete voll weiss). Zentral: Zeichen in ein Textfeld mit
   Fokus loesen nie ein Kuerzel aus (``src/ui/textfeld_vorrang.py``).
3. Das XY-Pad im Position-Tool stand immer auf 127/127 statt auf den echten
   Pan/Tilt-Werten des Programmers.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, Qt                              # noqa: E402
from PySide6.QtGui import QAction, QKeyEvent                       # noqa: E402
from PySide6.QtTest import QTest                                   # noqa: E402
from PySide6.QtWidgets import (                                    # noqa: E402
    QApplication, QLineEdit, QSpinBox, QVBoxLayout, QWidget,
)

from src.core.show import show_file as SF                          # noqa: E402

from _qt_lifecycle import destroy_all_top_level_widgets           # noqa: E402


def _app():
    return QApplication.instance() or QApplication([])


def _warte(bedingung, ms=2000):
    """Auf eine Bedingung warten (kein fester Timer)."""
    import time
    ende = time.monotonic() + ms / 1000.0
    while not bedingung() and time.monotonic() < ende:
        QApplication.processEvents()
        QTest.qWait(10)
    return bedingung()


class BefehlszeileTab(unittest.TestCase):
    """Die Befehlszeile allein: Tab ergaenzt und behaelt den Fokus."""

    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def setUp(self):
        from src.ui.widgets.command_line import CommandLine
        self.host = QWidget()
        lay = QVBoxLayout(self.host)
        self.cmd = CommandLine()
        self.nachbar = QLineEdit()
        lay.addWidget(self.cmd)
        lay.addWidget(self.nachbar)
        self.host.show()
        self.host.activateWindow()
        QTest.qWaitForWindowActive(self.host, 2000)
        self.edit = self.cmd._edit
        self.edit.setFocus()
        self.assertTrue(_warte(self.edit.hasFocus))

    def tearDown(self):
        self.host.close()
        self.host.deleteLater()
        self.app.processEvents()

    def test_tab_ergaenzt_hig_zu_highlight_und_behaelt_fokus(self):
        QTest.keyClicks(self.edit, "hig")
        QTest.keyClick(self.edit, Qt.Key.Key_Tab)
        self.app.processEvents()
        self.assertEqual(self.edit.text(), "highlight")
        self.assertTrue(self.edit.hasFocus(), "Tab nahm der Befehlszeile den Fokus")
        self.assertEqual(self.edit.cursorPosition(), len("highlight"))

    def test_tab_ergaenzt_cl_zu_clear(self):
        QTest.keyClicks(self.edit, "cl")
        QTest.keyClick(self.edit, Qt.Key.Key_Tab)
        self.assertEqual(self.edit.text(), "clear")
        self.assertTrue(self.edit.hasFocus())

    def test_tab_mitten_im_befehl(self):
        QTest.keyClicks(self.edit, "1 thru 5 @ fu")
        QTest.keyClick(self.edit, Qt.Key.Key_Tab)
        self.assertEqual(self.edit.text(), "1 thru 5 @ full")

    def test_tab_ohne_wort_bleibt_im_feld(self):
        QTest.keyClick(self.edit, Qt.Key.Key_Tab)
        self.assertTrue(self.edit.hasFocus())
        self.assertEqual(self.edit.text(), "")

    def test_umschalt_tab_verlaesst_das_feld_weiter(self):
        QTest.keyClick(self.edit, Qt.Key.Key_Backtab,
                       Qt.KeyboardModifier.ShiftModifier)
        self.assertTrue(_warte(lambda: not self.edit.hasFocus()))


class TextfeldVorrang(unittest.TestCase):
    """Die zentrale Regel ohne Hauptfenster."""

    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def _override(self, key, text, mods=Qt.KeyboardModifier.NoModifier):
        return QKeyEvent(QEvent.Type.ShortcutOverride, key, mods, text)

    def test_zeichen_im_textfeld_hat_vorrang(self):
        from src.ui import textfeld_vorrang as tv
        host = QWidget()
        lay = QVBoxLayout(host)
        spin = QSpinBox()
        edit = QLineEdit()
        lay.addWidget(spin)
        lay.addWidget(edit)
        host.show()
        host.activateWindow()
        QTest.qWaitForWindowActive(host, 2000)
        try:
            for feld in (edit, spin):
                feld.setFocus()
                self.assertTrue(_warte(feld.hasFocus))
                ev = self._override(Qt.Key.Key_H, "h")
                self.assertTrue(tv.hat_vorrang(ev))
                self.assertTrue(ev.isAccepted())
                self.assertTrue(tv.hat_vorrang(
                    self._override(Qt.Key.Key_H, "H",
                                   Qt.KeyboardModifier.ShiftModifier)))
                self.assertTrue(tv.hat_vorrang(self._override(Qt.Key.Key_Space, " ")))
                # Kuerzel ohne Zeichen bzw. mit Strg bleiben Kuerzel.
                self.assertFalse(tv.hat_vorrang(self._override(
                    Qt.Key.Key_S, "\x13", Qt.KeyboardModifier.ControlModifier)))
                self.assertFalse(tv.hat_vorrang(self._override(Qt.Key.Key_Escape, "\x1b")))
                self.assertFalse(tv.hat_vorrang(self._override(Qt.Key.Key_F12, "")))
            edit.setReadOnly(True)
            edit.setFocus()
            self.assertTrue(_warte(edit.hasFocus))
            self.assertFalse(tv.hat_vorrang(self._override(Qt.Key.Key_H, "h")))
        finally:
            host.close()
            host.deleteLater()
            self.app.processEvents()


class BefehlszeileImHauptfenster(unittest.TestCase):
    """Nachgestellter Klicktest: 'hig' + Tab + 'h' loest KEIN Highlight aus."""

    @classmethod
    def setUpClass(cls):
        cls.app = _app()
        from src.ui import main_window as mw
        SF.reset_show()
        cls.win = mw.MainWindow()
        cls.win.show()
        cls.win.activateWindow()
        cls.app.processEvents()
        QTest.qWaitForWindowActive(cls.win, 2000)
        cls.app.processEvents()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.win.deleteLater()
        except Exception:
            pass
        cls.app.processEvents()
        destroy_all_top_level_widgets(cls.app)
        SF.reset_show()
        cls.app.processEvents()

    def _kuerzel_zaehler(self, folge: str) -> list:
        treffer = []
        acts = [a for a in self.win.findChildren(QAction)
                if any(s.toString() == folge for s in a.shortcuts())]
        self.assertTrue(acts, f"Kuerzel {folge} nicht gefunden")
        for a in acts:
            a.triggered.connect(lambda *_: treffer.append(1))
        return treffer

    def test_tab_dann_h_landet_in_der_befehlszeile(self):
        treffer = self._kuerzel_zaehler("H")
        edit = self.win._command_line._edit
        edit.clear()
        edit.setFocus()
        self.assertTrue(_warte(edit.hasFocus))
        QTest.keyClicks(edit, "hig")
        QTest.keyClick(edit, Qt.Key.Key_Tab)
        self.assertTrue(edit.hasFocus(), "Fokus sprang aus der Befehlszeile")
        fokus = QApplication.focusWidget() or edit
        QTest.keyClick(fokus, Qt.Key.Key_H)
        self.app.processEvents()
        self.assertEqual(treffer, [], "H = Highlight feuerte trotz Befehlszeile")
        self.assertEqual(edit.text(), "highlighth")
        edit.clear()

    def test_umschalt_h_und_leertaste_im_textfeld(self):
        treffer_h = self._kuerzel_zaehler("Shift+H")
        treffer_go = self._kuerzel_zaehler("Space")
        edit = self.win._command_line._edit
        edit.clear()
        edit.setFocus()
        self.assertTrue(_warte(edit.hasFocus))
        QTest.keyClick(edit, Qt.Key.Key_H, Qt.KeyboardModifier.ShiftModifier)
        QTest.keyClick(edit, Qt.Key.Key_Space)
        self.app.processEvents()
        self.assertEqual(treffer_h, [])
        self.assertEqual(treffer_go, [])
        # QTest liefert bei Umschalt den Kleinbuchstaben als Text.
        self.assertEqual(edit.text().lower(), "h ")
        edit.clear()


class XYPadFolgtProgrammer(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def setUp(self):
        SF.reset_show()
        from src.core.app_state import get_state
        self.state = get_state()

    def tearDown(self):
        SF.reset_show()
        self.app.processEvents()

    def test_pad_zeigt_echte_werte_und_schreibt_dabei_nichts(self):
        from src.ui.widgets.position_tool import PositionTool
        st = self.state
        st.set_programmer_value(12, "pan", 30)
        st.set_programmer_value(12, "tilt", 200)
        vorher = {k: dict(v) for k, v in st.programmer.items()}
        pt = PositionTool()
        try:
            pt.set_live(True)
            self.assertEqual(pt.position()[:2], (127, 127))
            self.assertTrue(pt.aus_programmer_laden())
            self.assertEqual(pt.position()[:2], (30, 200))
            self.assertEqual((pt._pad._pan, pt._pad._tilt), (30, 200))
            self.assertIn("Pan: 30", pt._lbl_values.text())
            self.assertIn("Tilt: 200", pt._lbl_values.text())
            # Nur gelesen: kein pan_fine/tilt_fine hinzugekommen (Live!).
            self.assertEqual({k: dict(v) for k, v in st.programmer.items()}, vorher)
            # Spaetere Aenderung (Befehlszeile/Wiederholen) wird uebernommen.
            st.set_programmer_value(12, "pan", 220)
            st.set_programmer_value(12, "tilt", 47)
            pt.aus_programmer_laden()
            self.assertEqual(pt.position()[:2], (220, 47))
        finally:
            pt.deleteLater()
            self.app.processEvents()

    def test_ohne_werte_bleibt_die_mitte(self):
        from src.ui.widgets.position_tool import PositionTool
        pt = PositionTool()
        try:
            self.assertFalse(pt.aus_programmer_laden())
            self.assertEqual(pt.position()[:2], (127, 127))
        finally:
            pt.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()


class BefehlBegrenzungMelden(unittest.TestCase):
    """Punkt 5 (Handgriff): '1 @ 300' wurde still auf 255 gesetzt."""

    def _state(self):
        from types import SimpleNamespace
        geschrieben = []

        class _St:
            def get_patched_fixtures(self):
                return [SimpleNamespace(fid=1), SimpleNamespace(fid=2)]

            def set_programmer_value(self, fid, attr, val, head=None):
                geschrieben.append((fid, attr, val))

            def __getattr__(self, name):
                raise AttributeError(name)
        return _St(), geschrieben

    def test_ueber_100_prozent_wird_gemeldet(self):
        from src.core.cmdline.parser import parse
        st, geschrieben = self._state()
        res = parse("1 @ 300").execute(st)
        self.assertTrue(res.ok, res.message)
        self.assertEqual(geschrieben, [(1, "intensity", 255)])
        self.assertIn("begrenzt", res.message)

    def test_gueltiger_wert_ohne_hinweis(self):
        from src.core.cmdline.parser import parse
        st, _ = self._state()
        res = parse("1 @ 80").execute(st)
        self.assertTrue(res.ok, res.message)
        self.assertNotIn("begrenzt", res.message)
