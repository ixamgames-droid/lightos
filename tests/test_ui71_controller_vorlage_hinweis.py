"""UI-71: der Controller-Browser verspricht keine Aktion, die es nicht gibt.

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
        for text in self._details_fuer(True):
            self.assertNotIn("Controller-Vorlage einfügen", text)
            self.assertNotIn("VC-Vorlage verfügbar", text)

    def test_die_aktion_gibt_es_wirklich_nicht(self):
        """Faellt rot, sobald jemand die Einfuege-Aktion (wieder) baut — dann
        darf der Hinweis zurueck, und dieser Test gehoert angepasst."""
        import glob
        import re
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        treffer = []
        for pfad in glob.glob(os.path.join(root, "src", "**", "*.py"), recursive=True):
            with open(pfad, encoding="utf-8") as fh:
                quelle = fh.read()
            if re.search(r"^\s*(from|import)\s.*controller_templates", quelle, re.M):
                treffer.append(os.path.relpath(pfad, root))
        self.assertEqual(treffer, [])


if __name__ == "__main__":
    unittest.main()
