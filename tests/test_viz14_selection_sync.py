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

from PySide6.QtWidgets import (QApplication, QListWidget, QListWidgetItem,
                               QPushButton, QAbstractItemView)
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

    def test_window_handler_ohne_bridge_markiert_trotzdem_die_liste(self):
        """★★ QA-56: hier stand ein nacktes ``SimpleNamespace()`` und der Aufruf
        „darf nicht werfen". Das belegte weder Wirkung noch Wirkungslosigkeit —
        und wirkungslos IST der Handler ohne Bridge gerade nicht: die
        Geraeteliste wird trotzdem markiert (die Markierung steht bewusst VOR der
        Bridge-Wache, ``_mark_patch_list`` hat genau deshalb zwei Aufrufer).
        Wandert die Wache nach oben, verschwindet die Markierung still — sichtbar
        nur daran, dass die Liste nach einer Programmer-Auswahl leer bleibt.
        Jetzt wird beides gemessen: die Markierung laeuft, und am Fenster
        entsteht dabei kein neuer Zustand."""
        markiert = []
        stub = SimpleNamespace(
            _mark_patch_list=lambda fids: markiert.append(list(fids)))
        felder_vorher = dict(vars(stub))

        VisualizerWindow._on_global_selection(stub, "SELECTION_CHANGED", [1, 4])

        self.assertEqual(markiert, [[1, 4]],
                         "ohne Bridge muss die Geraeteliste weiter markiert werden")
        self.assertEqual(vars(stub), felder_vorher,
                         "der Handler legt keinen Ersatz-Zustand am Fenster an")


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


class TestViz14ListFollowsSelection(unittest.TestCase):
    """VIZ-14-Folge: die Visualizer-Geräteliste folgt der GEMEINSAMEN Auswahl.

    Der offen gebliebene Review-Fund aus Slice 1b: die Rückrichtung setzte nur
    die 3D-Outlines — die Liste daneben blieb auf dem alten Eintrag stehen und
    zeigte damit etwas anderes an als die Szene, auf die sie sich bezieht.
    """

    def setUp(self):
        self.state = get_state()
        self.state.set_selected_fids([])

    def _fenster_stub(self, fids=(3, 5, 7)):
        """Stub mit der ECHTEN Markier-Methode — die Sperre, die hier geprüft
        wird (`blockSignals`), lebt genau darin."""
        s = _stub(self.state, fids)
        s._patch_list.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)
        s._patch_list.itemSelectionChanged.connect(
            lambda: VisualizerWindow._on_patch_list_selected(s))
        s._mark_patch_list = lambda f: VisualizerWindow._mark_patch_list(s, f)
        s._bridge = MagicMock()
        return s

    def _markiert(self, s):
        return sorted(it.data(Qt.ItemDataRole.UserRole)
                      for it in s._patch_list.selectedItems())

    def test_globale_auswahl_markiert_die_liste(self):
        s = self._fenster_stub()
        VisualizerWindow._on_global_selection(s, "SELECTION_CHANGED", [3, 7])
        self.assertEqual(self._markiert(s), [3, 7])

    def test_markieren_schreibt_die_auswahl_nicht_zurueck(self):
        """★ Ohne blockSignals würde jeder markierte Eintrag einzeln
        `set_selected_fids` rufen — die Zwischenstände wären für Programmer,
        EFX und Matrix echte Auswahl-Änderungen."""
        self.state.set_selected_fids([3, 7])
        s = self._fenster_stub()
        rufe = []
        s._state = SimpleNamespace(
            set_selected_fids=lambda f: rufe.append(list(f)),
            get_selected_fids=lambda: [3, 7],
            visualizer_positions={}, visualizer_rotations={})
        VisualizerWindow._on_global_selection(s, "SELECTION_CHANGED", [3, 7])
        self.assertEqual(rufe, [], "die Markierung darf nichts zurückschreiben")

    def test_leere_auswahl_raeumt_die_markierung(self):
        s = self._fenster_stub()
        VisualizerWindow._on_global_selection(s, "SELECTION_CHANGED", [5])
        VisualizerWindow._on_global_selection(s, "SELECTION_CHANGED", [])
        self.assertEqual(self._markiert(s), [])

    def test_current_item_bleibt_wenn_es_zur_auswahl_gehoert(self):
        """An `currentItem` hängen die Eigenschaftsfelder — es darf nicht unter
        der Hand das Gerät wechseln, solange es noch gewählt ist."""
        s = self._fenster_stub()
        VisualizerWindow._on_global_selection(s, "SELECTION_CHANGED", [3, 5, 7])
        s._patch_list.setCurrentRow(2)                      # fid 7
        VisualizerWindow._on_global_selection(s, "SELECTION_CHANGED", [5, 7])
        self.assertEqual(s._patch_list.currentItem().data(Qt.ItemDataRole.UserRole), 7)

    def test_current_item_wandert_wenn_es_rausfaellt(self):
        s = self._fenster_stub()
        VisualizerWindow._on_global_selection(s, "SELECTION_CHANGED", [3])
        VisualizerWindow._on_global_selection(s, "SELECTION_CHANGED", [5, 7])
        self.assertEqual(s._patch_list.currentItem().data(Qt.ItemDataRole.UserRole), 5)

    def test_mehrfachmarkierung_in_der_liste_meldet_alle(self):
        """Gegenrichtung: Strg-Klick auf drei Geräte darf die Auswahl der
        anderen Ansichten nicht auf eines zusammenstreichen."""
        s = self._fenster_stub()
        for row in (0, 2):
            s._patch_list.item(row).setSelected(True)
        s._patch_list.setCurrentRow(2)
        VisualizerWindow._on_patch_list_selected(s)
        self.assertEqual(self.state.selected_fids, [3, 7])

    def test_handler_ohne_liste_bleibt_ein_noop(self):
        """Der Handler laeuft in Bestandstests mit einem Stub ohne Liste."""
        stub = SimpleNamespace(_bridge=MagicMock())
        VisualizerWindow._on_global_selection(stub, "SELECTION_CHANGED", [3])
        stub._bridge.selectFixtures.emit.assert_called_once()
