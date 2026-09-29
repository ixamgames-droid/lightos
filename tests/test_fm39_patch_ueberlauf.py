"""FM-39: im Hinzufuegen-Dialog gilt fuer das ERSTE Geraet dieselbe Regel wie
fuer die Kopien — und ein Ausweichen ins naechste Universe wird gemeldet.

Gemessen im Stabilitaets-Durchlauf 2026-08-31: das erste Geraet lief still
ueber Kanal 512 hinaus (seine letzten Kanaele gingen nirgends hin), die Kopien
wurden ins naechste Universe gerollt — dieselbe Aktion, zwei Verhalten.
"""
import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication                     # noqa: E402

from src.core.app_state import get_state                       # noqa: E402
from src.core.show.show_file import reset_show                 # noqa: E402
from src.ui.widgets.fixture_browser import (                   # noqa: E402
    FixtureBrowserDialog, plane_patch_adressen)

_app = QApplication.instance() or QApplication([])


class PlanTest(unittest.TestCase):

    def test_erstes_geraet_rollt_wie_die_kopien(self):
        plan, weg, gerollt = plane_patch_adressen(1, 510, 8, 1, 8)
        self.assertEqual((plan, weg, gerollt), ([(2, 1)], 0, [0]))

    def test_kopie_rollt_und_wird_genannt(self):
        plan, weg, gerollt = plane_patch_adressen(1, 497, 8, 4, 8)
        self.assertEqual(plan, [(1, 497), (1, 505), (2, 1), (2, 9)])
        self.assertEqual((weg, gerollt), (0, [2]))

    def test_passt_genau_bis_512(self):
        self.assertEqual(plane_patch_adressen(1, 505, 8, 1, 8), ([(1, 505)], 0, []))

    def test_hinter_universe_32_ist_schluss(self):
        plan, weg, gerollt = plane_patch_adressen(32, 505, 8, 3, 8)
        self.assertEqual((plan, weg, gerollt), ([(32, 505)], 2, []))

    def test_geraet_groesser_als_ein_universe(self):
        self.assertEqual(plane_patch_adressen(1, 1, 600, 1, 600), ([], 1, []))

    def test_ohne_ueberlauf_unveraendert(self):
        self.assertEqual(plane_patch_adressen(3, 1, 8, 3, 8),
                         ([(3, 1), (3, 9), (3, 17)], 0, []))


class DialogTest(unittest.TestCase):
    """Echter Dialog, echter Anwenderweg (suchen, waehlen, Hinzufuegen)."""

    def setUp(self):
        reset_show()
        self.st = get_state()

    def _hinzufuegen(self, adresse, anzahl=1):
        d = FixtureBrowserDialog(self.st.next_fid())
        self.addCleanup(d.deleteLater)
        d._search.setText("ZQ01424")
        d._tree.setCurrentItem(d._tree.topLevelItem(0))
        d._spin_count.setValue(anzahl)
        d._spin_universe.setValue(1)
        d._spin_address.setValue(adresse)
        d._btn_add.click()
        return d

    def test_erstes_geraet_laeuft_nicht_mehr_ueber_512(self):
        d = self._hinzufuegen(510)
        f = d.result_fixture
        self.assertLessEqual(f.address + f.channel_count - 1, 512)
        self.assertEqual((f.universe, f.address), (2, 1))
        self.assertEqual(d.gerollt, [0])

    def test_patch_view_meldet_das_ausweichen(self):
        from src.ui.views import patch_view as pv
        d = self._hinzufuegen(510)
        with mock.patch.object(pv, "FixtureBrowserDialog", return_value=d), \
                mock.patch.object(d, "exec", return_value=True), \
                mock.patch.object(pv.QMessageBox, "information") as info:
            view = pv.PatchView.__new__(pv.PatchView)
            view._state = self.st
            pv.PatchView._add_fixture(view)
        self.assertEqual(info.call_count, 1)
        self.assertIn("Universe 2", info.call_args[0][2])
        self.assertEqual([(f.universe, f.address) for f in self.st.get_patched_fixtures()],
                         [(2, 1)])


if __name__ == "__main__":
    unittest.main()
