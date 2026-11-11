"""UI-71: der Controller-Browser verspricht keine Aktion, die es nicht gibt.

MIDI-18 (2026-11-11): den Weg gibt es wieder — als Knopf „In Virtual Console
einfügen“ im Browser selbst. Der Hinweis nennt jetzt diesen Knopf.

Bei APC mini / mk2 zeigte die Detailansicht „✔ VC-Vorlage verfügbar — in der
Virtual Console über „Controller-Vorlage einfügen“ nutzbar.“ Eine solche Aktion
gibt es weder in der Werkzeugleiste noch im Rechtsklick-Menü der Virtual
Console (die Baukasten-Blöcke sind seit 2026-07 entfernt); das Modul mit den
Vorlagen wird von keinem Bedienweg importiert.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication                     # noqa: E402

import pytest as _pytest                                        # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets         # noqa: E402

_app = QApplication.instance() or QApplication([])


@_pytest.fixture(autouse=True)
def _keine_fenster_uebrig():
    yield
    destroy_all_top_level_widgets(QApplication.instance())


class ControllerVorlageHinweisTest(unittest.TestCase):

    def _details_fuer(self, vc_template_gesetzt: bool) -> list[str]:
        from PySide6.QtCore import Qt
        from src.ui.widgets.controller_browser import ControllerBrowserDialog
        dlg = ControllerBrowserDialog(midi_only=True)
        self.addCleanup(dlg.deleteLater)
        texte = []
        for i in range(dlg._list.count()):
            dlg._list.setCurrentRow(i)
            p = dlg._lib.find(dlg._list.item(i).data(Qt.ItemDataRole.UserRole))
            if bool(p and p.vc_template) == vc_template_gesetzt:
                texte.append(dlg._details.toPlainText())
        return texte

    def test_es_gibt_profile_mit_vc_vorlage(self):
        """Positivkontrolle: ohne solche Profile prueft der Test nichts."""
        self.assertTrue(self._details_fuer(True),
                        "kein Profil mit vc_template (APC mini erwartet)")

    def test_keine_verheissung_einer_einfuege_aktion(self):
        """Der alte Text nannte eine Aktion der Virtual Console, die es nicht
        gibt — er kommt nicht zurueck."""
        for text in self._details_fuer(True):
            self.assertNotIn("Controller-Vorlage einfügen", text)

    def test_hinweis_nennt_den_knopf_den_es_gibt(self):
        """MIDI-18: der Weg ist zurueck — als Knopf im Browser selbst."""
        from src.ui.widgets.controller_browser import ControllerBrowserDialog
        dlg = ControllerBrowserDialog(midi_only=True)
        self.addCleanup(dlg.deleteLater)
        self.assertEqual(dlg._btn_vc.text(), "In Virtual Console einfügen")
        for text in self._details_fuer(True):
            self.assertIn("In Virtual Console einfügen", text)
        for text in self._details_fuer(False):
            self.assertNotIn("Vorlage für die Virtual Console", text)

if __name__ == "__main__":
    unittest.main()
