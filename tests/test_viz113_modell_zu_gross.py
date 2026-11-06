"""VIZ-113: ein Modell ueber 60 m (grosser Hallenplan, falsche Einheit) wird
nicht mehr nur abgelehnt — der Import bietet an, es passend zu verkleinern."""
import os
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.stage import modell_import as mi  # noqa: E402
from test_viz67_modell_import import FensterImportTest, _datei  # noqa: E402


class ZuGrossTest(unittest.TestCase):
    def test_fehler_nennt_groesse_und_passenden_massstab(self):
        # 0,1-m-Quader als Meter gelesen = 100 m Kante
        with self.assertRaises(mi.ModellZuGross) as cm:
            mi.lies_datei(_datei("viz67_quader_binaer.stl"), "m", True)
        e = cm.exception
        self.assertAlmostEqual(max(e.groesse), 100.0, places=3)
        self.assertLess(e.passend * 100.0, mi.MAX_KANTE_M + 1e-6)
        netz = mi.lies_datei(_datei("viz67_quader_binaer.stl"), "m", True, massstab=e.passend)
        self.assertLessEqual(max(netz.groesse[0], netz.groesse[2]), mi.MAX_KANTE_M)
        self.assertGreater(max(netz.groesse), mi.MAX_KANTE_M * 0.99)

    def test_ungueltiger_massstab_wird_abgelehnt(self):
        for m in (0.0, -1.0, 1.5):
            with self.subTest(m=m), self.assertRaises(mi.ModellImportFehler):
                mi.lies_datei(_datei("viz67_quader_binaer.stl"), "mm", True, massstab=m)


class FensterVerkleinernTest(FensterImportTest):
    def test_ja_verkleinert_und_legt_an(self):
        from PySide6.QtWidgets import QMessageBox
        VW, fake = self._fake()
        with mock.patch.object(QMessageBox, "warning"), mock.patch.object(
                QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes) as frage:
            el = VW.VisualizerWindow._import_model_file(
                fake, _datei("viz67_quader_binaer.stl"), "m", True)
        frage.assert_called_once()
        self.assertIsNotNone(el)
        self.assertLessEqual(max(el.w, el.d), mi.MAX_KANTE_M)
        self.assertGreater(max(el.w, el.d), mi.MAX_KANTE_M * 0.99)

    def test_abbrechen_legt_nichts_an(self):
        from PySide6.QtWidgets import QMessageBox
        VW, fake = self._fake()
        with mock.patch.object(QMessageBox, "warning"), mock.patch.object(
                QMessageBox, "question", return_value=QMessageBox.StandardButton.Cancel):
            el = VW.VisualizerWindow._import_model_file(
                fake, _datei("viz67_quader_binaer.stl"), "m", True)
        self.assertIsNone(el)
        self.assertEqual(fake._current_stage.elements, [])


if __name__ == "__main__":
    unittest.main()
