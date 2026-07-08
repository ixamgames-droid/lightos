"""OUT-04: Art-Net/sACN „Übernehmen" belegt NUR das gewählte Universum.

Vorher looptén `_apply_artnet`/`_apply_sacn` über ALLE Universen und riefen für
jedes `add_artnet`/`add_sacn` + `_persist_output` — das überschrieb jede andere
Adapter-Zuweisung (live UND in universes.json), also z. B. einen Enttec auf U1,
wenn man Art-Net „übernahm". Jetzt gibt es je ein Ziel-Universe-Feld
(`_spin_artnet_univ`/`_spin_sacn_univ`), und die Apply-Methoden wirken nur darauf.

Der Test hängt sich an keinen echten OutputManager und keine echte universes.json:
`get_state` und `_persist_output` sind gemockt.
"""
import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import src.ui.widgets.output_config as oc

_app = QApplication.instance() or QApplication([])


class TestOutputConfigPerUniverseApply(unittest.TestCase):
    def setUp(self):
        # get_state + _persist_output ersetzen -> kein echter OutputManager, keine
        # echte universes.json wird angefasst.
        self._orig_get_state = oc.get_state
        self._orig_persist = oc._persist_output
        self.fake_om = mock.Mock()
        self.fake_state = mock.Mock()
        self.fake_state.output_manager = self.fake_om
        # Mehrere Universen vorhanden -> der ALTE „Schleife über alle"-Code hätte
        # add_* dreimal gerufen; der neue nur einmal fürs Zieluniversum.
        self.fake_state.universes = {1: object(), 2: object(), 3: object()}
        oc.get_state = lambda: self.fake_state
        self.persist_calls = []
        oc._persist_output = lambda num, output, patch: self.persist_calls.append(
            (num, output, patch))
        self.dlg = oc.OutputConfigDialog()

    def tearDown(self):
        oc.get_state = self._orig_get_state
        oc._persist_output = self._orig_persist
        self.dlg.deleteLater()

    def test_artnet_applies_only_to_selected_universe(self):
        self.dlg._spin_artnet_univ.setValue(2)
        self.dlg._check_artnet.setChecked(True)
        self.dlg._edit_artnet_ip.setText("10.0.0.5")
        self.dlg._apply_artnet()
        # NUR Universum 2 belegt — genau EIN add_artnet, nicht drei.
        self.fake_om.add_artnet.assert_called_once_with(2, "10.0.0.5")
        self.assertEqual(self.persist_calls, [(2, "ArtNet", "10.0.0.5")])
        # Universum 2 existiert bereits -> es wird nicht neu angelegt.
        self.fake_om.add_universe.assert_not_called()

    def test_sacn_applies_only_to_selected_universe(self):
        self.dlg._spin_sacn_univ.setValue(3)
        self.dlg._check_sacn.setChecked(True)
        self.dlg._check_sacn_multicast.setChecked(True)   # -> target_ip = None (Multicast)
        self.dlg._apply_sacn()
        self.fake_om.add_sacn.assert_called_once_with(3, None)
        self.assertEqual(self.persist_calls, [(3, "sACN", "")])
        self.fake_om.add_universe.assert_not_called()

    def test_artnet_disabled_does_nothing(self):
        self.dlg._check_artnet.setChecked(False)
        self.dlg._apply_artnet()
        self.fake_om.add_artnet.assert_not_called()
        self.assertEqual(self.persist_calls, [])

    def test_apply_creates_target_universe_if_missing(self):
        # Zieluniversum 9 existiert NICHT -> es wird genau EINMAL angelegt (fürs
        # Zieluniversum), nicht pauschal.
        self.dlg._spin_artnet_univ.setValue(9)
        self.dlg._check_artnet.setChecked(True)
        self.dlg._apply_artnet()
        self.fake_om.add_universe.assert_called_once_with(9)
        self.fake_om.add_artnet.assert_called_once_with(9, "255.255.255.255")


if __name__ == "__main__":
    unittest.main()
