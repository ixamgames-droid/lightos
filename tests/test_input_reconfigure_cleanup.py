"""NET-08: Umkonfigurieren des Eingangs-Universums raeumt die alte Merge-Config.

Vorher rief ``_apply_sacn_input``/``_apply_artnet_input`` beim Setzen einer neuen
Input-Merge-Konfiguration nie ``remove_merge``/``clear_merges`` — die alte Quelle
(z. B. U5) blieb im ``_merges``-Register des Empfaengers und mischte nach der
Umstellung auf U7 ueber den weiter aktiven Empfangs-Handler in dasselbe
out-Universe. Der Fix raeumt vor dem Einrichten des neuen Merge den alten in_u.

Headless: die Empfaenger-Singletons werden durch ein Fake ersetzt, das nur das
``_merges``-Register + die Lifecycle-Methoden nachbildet (kein echter Socket).
"""
import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import src.ui.widgets.output_config as oc
import src.core.dmx.sacn_input as sacn_input
import src.core.dmx.artnet_input as artnet_input

_app = QApplication.instance() or QApplication([])


class _FakeReceiver:
    """Bildet nur das Merge-Register + die Lifecycle-API der echten Empfaenger
    nach — genug fuer den Reconfigure-Pfad, ohne einen Socket zu oeffnen."""

    def __init__(self):
        self._merges: dict[int, tuple[int, str]] = {}
        self._running = True

    def is_running(self):
        return self._running

    def start(self, universes=None):
        self._running = True

    def join_universe(self, universe):
        pass

    def set_merge(self, in_universe, out_universe, mode="HTP"):
        if mode not in ("HTP", "LTP", "REPLACE"):
            mode = "HTP"
        self._merges[int(in_universe)] = (int(out_universe), mode)

    def remove_merge(self, in_universe):
        self._merges.pop(int(in_universe), None)

    def clear_merges(self):
        self._merges.clear()


class _ReconfigureBase:
    """Gemeinsame Assertions fuer sACN + Art-Net Input-Reconfigure."""

    spin_univ_attr = ""
    spin_out_attr = ""
    check_attr = ""
    mode_attr = ""
    apply_method = ""

    def setUp(self):
        self.rx = _FakeReceiver()
        self.fake_state = mock.Mock()
        self._orig_get_state = oc.get_state
        oc.get_state = lambda: self.fake_state
        self.dlg = oc.OutputConfigDialog()

    def tearDown(self):
        oc.get_state = self._orig_get_state
        self.dlg.deleteLater()

    def _configure(self, in_u, out_u):
        getattr(self.dlg, self.spin_univ_attr).setValue(in_u)
        getattr(self.dlg, self.spin_out_attr).setValue(out_u)
        getattr(self.dlg, self.check_attr).setChecked(True)
        getattr(self.dlg, self.mode_attr).setCurrentText("HTP")
        getattr(self.dlg, self.apply_method)()

    def test_reconfigure_removes_stale_input_merge(self):
        # 1) Input U5 -> out U1 konfigurieren.
        self._configure(5, 1)
        self.assertIn(5, self.rx._merges)
        self.assertEqual(self.rx._merges[5], (1, "HTP"))

        # 2) Auf U7 umstellen (gleiches out-Universe) -> die alte U5-Merge-Config
        #    muss weg sein, sonst mischt U5 weiter in out U1.
        self._configure(7, 1)
        self.assertNotIn(5, self.rx._merges,
                         "alte U5-Merge-Config mischt nach Umstellung weiter")
        self.assertIn(7, self.rx._merges)
        self.assertEqual(self.rx._merges[7], (1, "HTP"))
        # Nur genau die neue Config bleibt uebrig.
        self.assertEqual(set(self.rx._merges), {7})

    def test_reconfigure_out_change_clears_frozen_layer(self):
        # in_u UND out_u aendern -> alte Eingangs-Schicht (out U1) soll geleert
        # werden, damit keine eingefrorenen Werte zurueckbleiben (clear_input_merge).
        self._configure(5, 1)
        self.fake_state.clear_input_merge.reset_mock()
        self._configure(7, 2)
        self.assertNotIn(5, self.rx._merges)
        self.assertEqual(self.rx._merges[7], (2, "HTP"))
        self.fake_state.clear_input_merge.assert_called_once_with(1)


class TestSacnInputReconfigure(_ReconfigureBase, unittest.TestCase):
    spin_univ_attr = "_spin_sacn_in_univ"
    spin_out_attr = "_spin_sacn_in_out"
    check_attr = "_check_sacn_in"
    mode_attr = "_combo_sacn_in_mode"
    apply_method = "_apply_sacn_input"

    def setUp(self):
        super().setUp()
        self._orig_getrx = sacn_input.get_sacn_receiver
        sacn_input.get_sacn_receiver = lambda: self.rx

    def tearDown(self):
        sacn_input.get_sacn_receiver = self._orig_getrx
        super().tearDown()


class TestArtnetInputReconfigure(_ReconfigureBase, unittest.TestCase):
    spin_univ_attr = "_spin_artnet_in_univ"
    spin_out_attr = "_spin_artnet_in_out"
    check_attr = "_check_artnet_in"
    mode_attr = "_combo_artnet_in_mode"
    apply_method = "_apply_artnet_input"

    def setUp(self):
        super().setUp()
        self._orig_getrx = artnet_input.get_artnet_receiver
        artnet_input.get_artnet_receiver = lambda: self.rx

    def tearDown(self):
        artnet_input.get_artnet_receiver = self._orig_getrx
        super().tearDown()


if __name__ == "__main__":
    unittest.main()
