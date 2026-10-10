"""FM-72: beim Start mit ``--show`` blockiert die Erststart-Frage zur Geraete-
Bibliothek nicht mehr modal.

Gefunden 2026-10-08 (Sitzung D, Setup-Test XPLAT-47, frisches Profil): das
installierte LightOS mit ``--show Mega_Arena_2026.lshow`` lud die Show, dann
legte sich nach 0,8 s der modale Dialog „Geraete-Bibliothek herunterladen?“
davor und blockierte die Bedienung bis zum Klick. Jetzt: mit ``--show`` nur ein
Knopf in der Statuszeile (die Frage bleibt offen und kommt beim naechsten Start
ohne ``--show``); ohne ``--show`` die Frage wie bisher; im Kiosk-Modus nichts.
"""
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtTest import QTest                                  # noqa: E402
from PySide6.QtWidgets import QApplication, QMainWindow, QPushButton  # noqa: E402

_app = QApplication.instance() or QApplication([])

import main as M                                                  # noqa: E402
from src.core.database import bibliothek_download as BD           # noqa: E402
from src.ui.main_window import MainWindow                         # noqa: E402


class _Fenster:
    """Steht fuer das Hauptfenster: merkt sich nur, was der Start aufruft."""

    def __init__(self):
        self.dialog = mock.Mock()
        self.hinweis = mock.Mock()

    def _open_bibliothek_download(self, erststart=False):
        self.dialog(erststart=erststart)

    def _bibliothek_hinweis_zeigen(self):
        self.hinweis()


class ErststartFrage(unittest.TestCase):

    def _starten(self, mit_show: bool) -> _Fenster:
        fenster = _Fenster()
        with mock.patch.object(BD, "beim_start_fragen", return_value=True), \
                mock.patch("src.core.database.fixture_db.engine", return_value=None):
            M._bibliothek_beim_erststart(fenster, mit_show=mit_show)
        QTest.qWait(1000)          # der Start wartet 0,8 s, bis die UI steht
        return fenster

    def test_mit_show_kein_modaler_dialog_sondern_hinweis(self):
        fenster = self._starten(mit_show=True)
        fenster.dialog.assert_not_called()
        fenster.hinweis.assert_called_once()

    def test_ohne_show_bleibt_die_erststart_frage(self):
        fenster = self._starten(mit_show=False)
        fenster.dialog.assert_called_once_with(erststart=True)
        fenster.hinweis.assert_not_called()

    def test_main_reicht_show_durch_und_kiosk_fragt_nie(self):
        quelle = (ROOT / "main.py").read_text(encoding="utf-8")
        self.assertIn("if not args.kiosk:\n        _bibliothek_beim_erststart("
                      "window, mit_show=bool(args.show))", quelle)


class HinweisKnopf(unittest.TestCase):

    def test_knopf_oeffnet_den_dialog_und_verschwindet(self):
        fenster = QMainWindow()
        self.addCleanup(fenster.deleteLater)
        fenster._open_bibliothek_download = mock.Mock()
        MainWindow._bibliothek_hinweis_zeigen(fenster)
        MainWindow._bibliothek_hinweis_zeigen(fenster)   # zweimal: ein Knopf
        knoepfe = [b for b in fenster.statusBar().findChildren(QPushButton)
                   if "Bibliothek" in b.text()]
        self.assertEqual(len(knoepfe), 1, [b.text() for b in knoepfe])
        knoepfe[0].click()
        fenster._open_bibliothek_download.assert_called_once_with(erststart=True)
        self.assertIsNone(fenster._btn_bibliothek_hinweis)
        QTest.qWait(50)            # deleteLater
        uebrig = [b for b in fenster.statusBar().findChildren(QPushButton)
                  if "Bibliothek" in b.text()]
        self.assertEqual(uebrig, [])

    def test_ohne_klick_bleibt_die_frage_offen(self):
        """Der Hinweis allein beantwortet nichts: kein Merker geschrieben."""
        with mock.patch.object(BD, "merker_schreiben") as schreiben:
            fenster = QMainWindow()
            self.addCleanup(fenster.deleteLater)
            fenster._open_bibliothek_download = mock.Mock()
            MainWindow._bibliothek_hinweis_zeigen(fenster)
            schreiben.assert_not_called()


if __name__ == "__main__":
    unittest.main()
