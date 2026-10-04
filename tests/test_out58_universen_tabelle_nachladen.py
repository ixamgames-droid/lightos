"""OUT-58: Enttec-„Verbinden" und sACN-„Übernehmen" laden den Universen-Tab neu.

Die Tabelle im Tab „Universen" wird beim Dialogbau aus ``universes.json``
gefuellt. A3D-15 hat sie nach Art-Net-„Übernehmen" neu geladen, Enttec und sACN
nicht. Folge, nachgestellt: Universum 2 steht in der Datei auf „Disabled",
der Nutzer verbindet im Enttec-Tab (Datei: „Enttec"), wechselt in den Tab
„Universen" — dort steht weiter „Disabled" — und druckt „Speichern". Die alte
Zeile ueberschreibt die eben gespeicherte, nach dem Neustart ist der Ausgang weg.

Netz und Adapter sind Attrappen; geprueft wird der Dialog und die Datei.
"""
import json
import os
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import src.ui.widgets.output_config as oc

import pytest as _pytest_xplat15                      # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402  XPLAT-15


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    from PySide6.QtWidgets import QApplication as _QApp
    destroy_all_top_level_widgets(_QApp.instance())


class UniversenTabNachAusgabeTest(unittest.TestCase):

    def setUp(self):
        QApplication.instance() or QApplication([])
        fd, self._tmp = tempfile.mkstemp(suffix="_universes.json")
        os.close(fd)
        self.addCleanup(lambda: os.path.exists(self._tmp) and os.remove(self._tmp))
        alt = oc._UNIV_CONFIG_PATH
        oc._UNIV_CONFIG_PATH = self._tmp
        self.addCleanup(setattr, oc, "_UNIV_CONFIG_PATH", alt)
        oc._save_universe_config([
            {"num": 1, "name": "Main", "output": "Disabled", "patch": ""},
            {"num": 2, "name": "Bühne", "output": "Disabled", "patch": ""},
        ])
        from src.core.app_state import get_state
        state = get_state()
        om = state.output_manager
        for name in ("add_enttec", "add_sacn", "remove_output"):
            p = mock.patch.object(om, name, lambda *a, **k: None)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(state, "apply_output_config", lambda *a, **k: None)
        p.start()
        self.addCleanup(p.stop)
        p = mock.patch.object(oc, "QMessageBox")   # „Gespeichert" blockiert sonst
        p.start()
        self.addCleanup(p.stop)
        self.dlg = oc.OutputConfigDialog()
        self.addCleanup(self.dlg.deleteLater)

    def _tabelle(self, num):
        t = self.dlg._univ_table
        for r in range(t.rowCount()):
            if t.item(r, 0) and t.item(r, 0).text() == str(num):
                return t.cellWidget(r, 2).currentText(), t.item(r, 3).text()
        self.fail(f"Universum {num} fehlt in der Tabelle")

    def _datei(self, num):
        with open(self._tmp, encoding="utf-8") as fh:
            return next(r for r in json.load(fh) if r["num"] == num)

    def _enttec_verbinden(self, univ, port="/dev/ttyTEST0"):
        self.dlg._enttec_status_pruefen_spaeter = lambda *a, **k: None
        self.dlg._combo_port.clear()
        self.dlg._combo_port.addItem("Test-Adapter", port)
        self.dlg._spin_enttec_univ.setValue(univ)
        self.dlg._connect_enttec()

    def _sacn_uebernehmen(self, univ):
        self.dlg._check_sacn.setChecked(True)
        self.dlg._check_sacn_multicast.setChecked(True)
        self.dlg._spin_sacn_univ.setValue(univ)
        self.dlg._apply_sacn()

    def test_enttec_steht_sofort_in_der_tabelle(self):
        self._enttec_verbinden(2)
        self.assertEqual(self._datei(2)["output"], "Enttec")
        self.assertEqual(self._tabelle(2), ("Enttec", "/dev/ttyTEST0"))

    def test_sacn_steht_sofort_in_der_tabelle(self):
        self._sacn_uebernehmen(2)
        self.assertEqual(self._datei(2)["output"], "sACN")
        self.assertEqual(self._tabelle(2)[0], "sACN")

    def test_speichern_im_universen_tab_behaelt_den_enttec_ausgang(self):
        """Der eigentliche Schaden: „Speichern" danach loeschte den Ausgang."""
        self._enttec_verbinden(2)
        self.dlg._univ_save()
        self.assertEqual(self._datei(2)["output"], "Enttec")
        self.assertEqual(self._datei(2)["patch"], "/dev/ttyTEST0")

    def test_speichern_im_universen_tab_behaelt_den_sacn_ausgang(self):
        self._sacn_uebernehmen(2)
        self.dlg._univ_save()
        self.assertEqual(self._datei(2)["output"], "sACN")

    def test_andere_zeilen_bleiben(self):
        self._sacn_uebernehmen(2)
        self.dlg._univ_save()
        self.assertEqual(self._datei(1)["output"], "Disabled")
        self.assertEqual(self._datei(1)["name"], "Main")


if __name__ == "__main__":
    unittest.main()
