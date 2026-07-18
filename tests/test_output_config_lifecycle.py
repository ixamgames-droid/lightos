"""MU-01/MU-02: Output-Live-Buttons raeumen das Ziel-Universum vor jedem add_*.

Vorher riefen ``_connect_enttec``/``_apply_artnet``/``_apply_sacn`` nur
``add_enttec``/``add_artnet``/``add_sacn`` — diese schreiben via ``_swap_device``
NUR in ihre eigene Registry. Bei einem Cross-Typ-Wechsel auf demselben Universum
blieben so BEIDE Adapter aktiv (Doppel-Output/Leak, OUT-05 lebte nur im
Rehydrierungs-Pfad ``apply_output_config``). Zudem stoppte das Abwaehlen der
„aktivieren"-Checkbox die Ausgabe nicht (Label wurde gesetzt, Adapter blieb
registriert -> ``_send_all`` sendete weiter).

Der Fix ruft vor jedem ``add_*`` (und im Deaktivieren-Zweig) ``remove_output(univ)``.

Headless: ``get_state`` wird durch ein Fake mit einem OutputManager-Stub ersetzt,
der die Adapter-Registries + eine ``remove_output``-Spy nachbildet (kein Socket,
keine echte Hardware) — analog test_input_reconfigure_cleanup.py.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import src.ui.widgets.output_config as oc

_app = QApplication.instance() or QApplication([])


class _FakeOutputManager:
    """Bildet nur die Registries + die im Live-Pfad genutzte API nach. ``calls``
    protokolliert die Reihenfolge, damit „remove VOR add" pruefbar ist."""

    def __init__(self):
        self._enttec_outputs: dict[int, object] = {}
        self._artnet_outputs: dict[int, object] = {}
        self._sacn_outputs: dict[int, object] = {}
        self.calls: list[tuple[str, int]] = []

    def add_universe(self, universe):
        return object()

    def add_enttec(self, universe, port):
        self.calls.append(("add_enttec", int(universe)))
        self._enttec_outputs[int(universe)] = object()

    def add_artnet(self, universe, target_ip="255.255.255.255", out_universe=None):
        # A3D-15: out_universe (externe Art-Net-Universe) muss angenommen werden,
        # seit _apply_artnet die Startuniversum-Spinbox durchreicht. Format des
        # calls-Spy unveraendert (2-Tupel), damit bestehende Assertions gelten.
        self.calls.append(("add_artnet", int(universe)))
        self.last_out_universe = out_universe
        self._artnet_outputs[int(universe)] = object()

    def add_sacn(self, universe, target_ip=None, out_universe=None):
        self.calls.append(("add_sacn", int(universe)))
        self.last_out_universe = out_universe
        self._sacn_outputs[int(universe)] = object()

    def remove_output(self, universe):
        """Wie OUT-05: entfernt ALLE Adapter dieses Universums (Spy + Registry)."""
        self.calls.append(("remove_output", int(universe)))
        for reg in (self._enttec_outputs, self._artnet_outputs, self._sacn_outputs):
            reg.pop(int(universe), None)

    def active_registries(self, universe):
        return [name for name, reg in (
            ("enttec", self._enttec_outputs),
            ("artnet", self._artnet_outputs),
            ("sacn", self._sacn_outputs),
        ) if int(universe) in reg]


class _FakeState:
    def __init__(self):
        self.output_manager = _FakeOutputManager()
        self.universes: dict[int, object] = {}


class TestOutputConfigLifecycle(unittest.TestCase):
    def setUp(self):
        self.state = _FakeState()
        self._orig_get_state = oc.get_state
        oc.get_state = lambda: self.state
        self.dlg = oc.OutputConfigDialog()

    def tearDown(self):
        oc.get_state = self._orig_get_state
        self.dlg.deleteLater()

    def _select_enttec_port(self, univ, port="COM_FAKE"):
        # _refresh_ports fuellt echte Ports (headless meist leer). Fuer den Test
        # einen definierten Port-Eintrag setzen, dessen currentData() den Pfad liefert.
        self.dlg._combo_port.clear()
        self.dlg._combo_port.addItem(port, port)
        self.dlg._spin_enttec_univ.setValue(univ)

    # ── MU-01: Cross-Typ-Wechsel raeumt das Universum ────────────────────────

    def test_enttec_then_artnet_removes_before_add(self):
        # 1) Enttec auf Universe 1 verbinden.
        self._select_enttec_port(1)
        self.dlg._connect_enttec()
        self.assertEqual(self.state.output_manager.active_registries(1), ["enttec"])

        # 2) Art-Net auf DEMSELBEN Universum uebernehmen.
        self.dlg._spin_artnet_univ.setValue(1)
        self.dlg._check_artnet.setChecked(True)
        self.dlg._apply_artnet()

        calls = self.state.output_manager.calls
        # remove_output(1) muss VOR add_artnet(1) gelaufen sein.
        self.assertIn(("remove_output", 1), calls)
        self.assertIn(("add_artnet", 1), calls)
        rm_idx = max(i for i, c in enumerate(calls) if c == ("remove_output", 1))
        add_idx = calls.index(("add_artnet", 1))
        self.assertLess(rm_idx, add_idx,
                        "remove_output muss vor add_artnet laufen (MU-01)")
        # Genau EIN Adapter aktiv -> kein Doppel-Output/Leak.
        self.assertEqual(self.state.output_manager.active_registries(1), ["artnet"])

    def test_enttec_then_sacn_removes_before_add(self):
        self._select_enttec_port(2)
        self.dlg._connect_enttec()
        self.dlg._spin_sacn_univ.setValue(2)
        self.dlg._check_sacn.setChecked(True)
        self.dlg._apply_sacn()

        calls = self.state.output_manager.calls
        rm_idx = max(i for i, c in enumerate(calls) if c == ("remove_output", 2))
        add_idx = calls.index(("add_sacn", 2))
        self.assertLess(rm_idx, add_idx)
        self.assertEqual(self.state.output_manager.active_registries(2), ["sacn"])

    def test_connect_enttec_removes_before_add(self):
        self._select_enttec_port(3)
        self.dlg._connect_enttec()
        calls = self.state.output_manager.calls
        self.assertEqual(calls, [("remove_output", 3), ("add_enttec", 3)])

    # ── MU-02: Deaktivieren stoppt den Adapter wirklich ──────────────────────

    def test_deactivate_artnet_calls_remove_output(self):
        # Erst aktiv setzen, dann Checkbox abwaehlen -> remove_output + Label.
        self.dlg._spin_artnet_univ.setValue(4)
        self.dlg._check_artnet.setChecked(True)
        self.dlg._apply_artnet()
        self.assertEqual(self.state.output_manager.active_registries(4), ["artnet"])

        self.dlg._check_artnet.setChecked(False)
        self.dlg._apply_artnet()
        self.assertIn(("remove_output", 4), self.state.output_manager.calls)
        self.assertEqual(self.state.output_manager.active_registries(4), [])
        self.assertEqual(self.dlg._lbl_artnet_status.text(), "Inaktiv")

    def test_deactivate_sacn_calls_remove_output(self):
        self.dlg._spin_sacn_univ.setValue(5)
        self.dlg._check_sacn.setChecked(True)
        self.dlg._apply_sacn()
        self.assertEqual(self.state.output_manager.active_registries(5), ["sacn"])

        self.dlg._check_sacn.setChecked(False)
        self.dlg._apply_sacn()
        self.assertIn(("remove_output", 5), self.state.output_manager.calls)
        self.assertEqual(self.state.output_manager.active_registries(5), [])
        self.assertEqual(self.dlg._lbl_sacn_status.text(), "Inaktiv")

    def test_deactivate_artnet_removes_applied_univ_not_current_spin(self):
        # Review-Fix (MU-02b): Art-Net auf U1 aktiv, dann Spin auf U2 (dort laeuft
        # bewusst sACN), dann Art-Net abwaehlen -> es MUSS U1 geraeumt werden (das
        # tatsaechlich belegte), NICHT U2 — sonst wird der fremde sACN-Adapter auf U2
        # faelschlich gekillt.
        self.dlg._spin_artnet_univ.setValue(1)
        self.dlg._check_artnet.setChecked(True)
        self.dlg._apply_artnet()                        # Art-Net auf U1
        self.dlg._spin_sacn_univ.setValue(2)
        self.dlg._check_sacn.setChecked(True)
        self.dlg._apply_sacn()                          # sACN auf U2
        self.assertEqual(self.state.output_manager.active_registries(2), ["sacn"])

        self.dlg._spin_artnet_univ.setValue(2)          # Spin (irrefuehrend) auf U2
        self.dlg._check_artnet.setChecked(False)
        self.state.output_manager.calls.clear()
        self.dlg._apply_artnet()                        # Art-Net abwaehlen

        self.assertIn(("remove_output", 1), self.state.output_manager.calls)
        self.assertNotIn(("remove_output", 2), self.state.output_manager.calls)
        # Der fremde sACN-Adapter auf U2 ueberlebt; U1 ist leer.
        self.assertEqual(self.state.output_manager.active_registries(2), ["sacn"])
        self.assertEqual(self.state.output_manager.active_registries(1), [])


if __name__ == "__main__":
    unittest.main()
