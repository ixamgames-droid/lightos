"""VIZ-14 (Slice 1a): 3D-Selektion + Visualizer-Geräteliste treiben die globale
Programmer-Auswahl (SELECTION_CHANGED). Die Rückrichtung (globale Auswahl ->
Puls im 3D) ist ein Folge-Slice.

Getestet werden die Fenster-Handler chirurgisch über ein Stub-``self`` (ohne die
QtWebEngine-schwere VisualizerWindow zu bauen) — sie berühren nur `_state`,
`_patch_list`, `_btn_align`, `_applying_selection`.
"""
import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QListWidget, QListWidgetItem, QPushButton
from PySide6.QtCore import Qt

import src.ui.visualizer.visualizer_window as VW
from src.ui.visualizer.visualizer_window import VisualizerWindow
from src.core.app_state import get_state

_app = QApplication.instance() or QApplication([])


def _list(fids):
    lst = QListWidget()
    for fid in fids:
        it = QListWidgetItem(f"[{fid:03d}] Fixture {fid}")
        it.setData(Qt.ItemDataRole.UserRole, fid)
        lst.addItem(it)
    return lst


def _stub(state, fids=(3, 5, 7)):
    return SimpleNamespace(_state=state, _patch_list=_list(fids),
                           _btn_align=QPushButton(), _applying_selection=False)


class TestViz14SelectionSync(unittest.TestCase):
    def setUp(self):
        self.state = get_state()
        self.state.set_selected_fids([])   # sauberer Ausgangszustand

    def test_3d_selection_drives_global(self):
        s = _stub(self.state)
        VisualizerWindow._on_fixture_selection_from_js(s, [3, 5])
        self.assertEqual(self.state.selected_fids, [3, 5])   # alle fids, nicht nur der erste
        self.assertTrue(s._btn_align.isEnabled())            # >=2 -> Ausrichten aktiv

    def test_3d_empty_selection_does_not_change_global(self):
        self.state.set_selected_fids([9])
        s = _stub(self.state)
        VisualizerWindow._on_fixture_selection_from_js(s, [])
        self.assertEqual(self.state.selected_fids, [9])      # leere 3D-Auswahl loescht NICHT
        self.assertFalse(s._btn_align.isEnabled())

    def test_list_selection_drives_global(self):
        s = _stub(self.state)
        s._patch_list.setCurrentRow(1)                       # fid 5
        VisualizerWindow._on_patch_list_selected(s)
        self.assertEqual(self.state.selected_fids, [5])

    def test_guard_prevents_list_clobbering_multiselect(self):
        # Simuliert den A->E-Pfad: 3D setzt Mehrfachauswahl, die Listen-Markierung
        # (unter _applying_selection) darf sie NICHT auf ein Fixture reduzieren.
        self.state.set_selected_fids([3, 5])
        s = _stub(self.state)
        s._applying_selection = True
        s._patch_list.setCurrentRow(0)                       # fid 3
        VisualizerWindow._on_patch_list_selected(s)
        self.assertEqual(self.state.selected_fids, [3, 5])   # Mehrfachauswahl bleibt


class TestViz14ReverseSelection(unittest.TestCase):
    """Slice 1b: globale/Programmer-Auswahl -> 3D (Rueckrichtung).

    _on_global_selection spiegelt SELECTION_CHANGED in den Bridge-Poll
    (selectFixtures -> _poll_set("selection", ...)); JS zeigt die Outlines.
    """

    def test_window_handler_forwards_selection_to_bridge(self):
        # Fenster-Handler: gibt die Auswahl als JSON an bridge.selectFixtures.
        stub = SimpleNamespace(_bridge=MagicMock())
        VisualizerWindow._on_global_selection(stub, "SELECTION_CHANGED", [3, 5, 7])
        stub._bridge.selectFixtures.emit.assert_called_once()
        arg = stub._bridge.selectFixtures.emit.call_args[0][0]
        self.assertEqual(json.loads(arg), [3, 5, 7])

    def test_window_handler_empty_selection_forwards_empty(self):
        stub = SimpleNamespace(_bridge=MagicMock())
        VisualizerWindow._on_global_selection(stub, "SELECTION_CHANGED", [])
        arg = stub._bridge.selectFixtures.emit.call_args[0][0]
        self.assertEqual(json.loads(arg), [])

    def test_window_handler_without_bridge_is_noop(self):
        # Defensiv: kein _bridge -> kein Crash (Test-Fakes/Teardown).
        stub = SimpleNamespace()
        VisualizerWindow._on_global_selection(stub, "SELECTION_CHANGED", [1])  # darf nicht werfen


class TestViz14BridgePollMirror(unittest.TestCase):
    """Slice 1b: das echte selectFixtures-Signal spiegelt in den pollControl-
    Zustand (den einzigen zuverlaessigen Python->JS-Weg an die Post-Load-Seite).
    """

    def setUp(self):
        self.state = get_state()
        self.bridge = VW.VisualizerBridge(self.state)

    def tearDown(self):
        self.bridge.dispose()

    def test_select_fixtures_signal_exists(self):
        self.assertTrue(hasattr(VW.VisualizerBridge, "selectFixtures"),
                        "VisualizerBridge muss ein selectFixtures-Signal exponieren")

    def test_emit_mirrors_into_poll_state(self):
        self.bridge.selectFixtures.emit("[3, 5]")
        self.assertEqual(self.bridge._poll_state.get("selection"), "[3, 5]")

    def test_poll_control_returns_selection(self):
        self.bridge.selectFixtures.emit("[9]")
        out = json.loads(self.bridge.pollControl())
        self.assertEqual(out.get("selection"), "[9]")


if __name__ == "__main__":
    unittest.main()
