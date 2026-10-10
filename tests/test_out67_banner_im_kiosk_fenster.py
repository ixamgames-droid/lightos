"""OUT-67 — das Ausfall-Banner sitzt im echten Hauptfenster, auch im Kiosk-Modus.

Im Kiosk-Modus sind Menue, Sektionsleiste und Statusleiste ausgeblendet — also
genau die Stellen, an denen ein Ausfall bisher stand. Das Banner haengt deshalb
im Wurzel-Layout und muss dort sichtbar bleiben.

Eigene Datei, weil hier ein ganzes ``MainWindow`` gebaut wird (ein Prozess je
Testdatei); die Regeln selbst prueft ``test_out67_ausgabe_ausfall_banner.py``
ohne Fenster. Der Ausgang ist eine Attrappe — kein Port, kein Netz.
"""
from __future__ import annotations

import io
import os
import sys
import unittest
from contextlib import redirect_stdout

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication  # noqa: E402

from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402  XPLAT-15


class _Manager:
    """Nur die eine Frage, die das Banner stellt."""

    def __init__(self):
        self.wege = []

    def ausgabe_status(self):
        return list(self.wege)


class BannerImKioskFensterTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        from src.ui import main_window as mw
        cls.win = mw.MainWindow(kiosk=True)
        cls.win._hw_timer.stop()        # der Test taktet selbst

    @classmethod
    def tearDownClass(cls):
        try:
            cls.win.deleteLater()
        except Exception:
            pass
        cls.app.processEvents()
        destroy_all_top_level_widgets(cls.app)
        cls.app.processEvents()

    def test_ausfall_ist_im_kiosk_sichtbar_und_geht_wieder(self):
        from src.ui.ausgabe_banner import HALTE_S
        win = self.win
        steuerung = win._ausgabe_banner
        banner = steuerung.widget
        t = [1000.0]
        steuerung._uhr = lambda: t[0]
        om = _Manager()

        # Was im Kiosk-Modus NICHT zu sehen ist — daher das Banner.
        self.assertTrue(win.statusBar().isHidden())
        self.assertTrue(win._section_bar.isHidden())
        self.assertIs(banner.window(), win)
        self.assertTrue(steuerung.kiosk)
        self.assertIsNone(steuerung.bei_stoerung_klick,
                          "Kiosk: kein Weg in die Einstellungen")

        om.wege = [{"universum": 1, "weg": "Enttec", "ziel": "COM9",
                    "verbunden": False, "problem": ""}]
        with redirect_stdout(io.StringIO()):
            steuerung.aktualisiere(om)
        self.assertTrue(banner.isVisibleTo(win),
                        "das Banner muss im Kiosk-Fenster sichtbar sein")
        self.assertIn("Ausgabe gestört: U1 Enttec (COM9)", banner.text())
        # Ueber dem Inhalt, nicht darunter.
        lay = win.centralWidget().layout()
        self.assertLess(lay.indexOf(banner), lay.indexOf(win._stack))

        om.wege[0]["verbunden"] = True
        with redirect_stdout(io.StringIO()):
            steuerung.aktualisiere(om)
            t[0] += HALTE_S + 0.1
            steuerung.aktualisiere(om)
        self.assertFalse(banner.isVisibleTo(win))

    def test_hardware_takt_fuettert_das_banner(self):
        """``_check_hardware`` -> ``_update_ausgabe_label`` -> Banner: derselbe
        Takt wie die Statusleiste, kein zweiter Timer."""
        win = self.win
        gerufen = []
        echt = win._ausgabe_banner.aktualisiere
        win._ausgabe_banner.aktualisiere = (
            lambda om, wege=None: gerufen.append(wege))
        try:
            win._update_ausgabe_label()
        finally:
            win._ausgabe_banner.aktualisiere = echt
        self.assertEqual(len(gerufen), 1)
        self.assertIsNotNone(gerufen[0])


if __name__ == "__main__":
    unittest.main()
