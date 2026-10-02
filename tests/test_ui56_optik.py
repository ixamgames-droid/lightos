"""UI-56: im Speichern-Dialog heisst die Gruppe Fokus/Zoom/Prisma/Iris „Optik".

Entschieden 2026-10-02 (Projektinhaber): umbenennen, nichts verschieben. „Beam"
wurde als „Weiteres" gelesen und dort nicht gesucht. Umbenannt wird nur die
ANZEIGE — der Gruppen-Schluessel bleibt "Beam", weil ``get_selected_groups``
und ``classify_attr`` ihn an Aufrufer weitergeben.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QCheckBox               # noqa: E402

from src.core.attr_groups import (ATTR_GROUP_ORDER, classify_attr,  # noqa: E402
                                  group_label)
from src.ui.views.snap_file_panel import ChannelSelectDialog        # noqa: E402


def _app():
    return QApplication.instance() or QApplication([])


class OptikImSpeichernDialog(unittest.TestCase):

    def setUp(self):
        _app()
        self.dlg = ChannelSelectDialog(
            {1: {"zoom": 10, "focus": 20, "prism": 30, "iris": 40, "intensity": 255}})
        self.addCleanup(self.dlg.deleteLater)

    def _gruppen_texte(self):
        return [cb.text() for cb in self.dlg._checks.values()]

    def test_gruppe_heisst_optik(self):
        self.assertIn("Optik  (4 Werte)", self._gruppen_texte())

    def test_beam_steht_nirgends_mehr_im_dialog(self):
        texte = [cb.text() for cb in self.dlg.findChildren(QCheckBox)]
        self.assertFalse([t for t in texte if "Beam" in t], texte)

    def test_schluessel_bleibt_beam(self):
        """Aufrufer lesen die gewaehlten Gruppen ueber den Schluessel."""
        self.assertIn("Beam", self.dlg.get_selected_groups())
        self.assertEqual(self.dlg._checks["Beam"].text(), "Optik  (4 Werte)")

    def test_abwaehlen_von_optik_laesst_die_kanaele_weg(self):
        self.dlg._checks["Beam"].setChecked(False)
        self.assertEqual(self.dlg.get_selected_attrs() & {"zoom", "focus", "prism", "iris"},
                         set())


class Anzeigename(unittest.TestCase):

    def test_nur_beam_wird_umbenannt(self):
        self.assertEqual(group_label("Beam"), "Optik")
        for gruppe in ATTR_GROUP_ORDER:
            if gruppe != "Beam":
                self.assertEqual(group_label(gruppe), gruppe)

    def test_einordnung_unveraendert(self):
        for attr in ("zoom", "focus", "frost", "iris", "prism"):
            self.assertEqual(classify_attr(attr), "Beam")


if __name__ == "__main__":
    unittest.main()
