"""FM-HEADLAYOUT A2: Kopf-Ziele in Fächer-Werkzeug und Snap-Aufnahme.

Nach A1 (der Kopf ist ein selektierbares Ziel) folgen die Konsumenten. Diese
Runde deckt die zwei ab, die rein auf der **Programmer-Ebene** arbeiten, wo Köpfe
über die ``attr#N``-Konvention ohnehin ausdrückbar sind:

* **Fächer (Fan):** fächert über die gewählten KÖPFE — die 4 Köpfe einer PAR-Bar
  bekommen einen Verlauf statt vier gleicher Werte.
* **Snap-Aufnahme:** ist im Programmer nur Kopf 2 gewählt, landet auch nur dessen
  Wert im Snap (vorher nahm der Geräte-Scope die anderen Köpfe still mit).

EFX und VC-Slider bleiben bewusst offen (A3): der eine speichert seine Ziele in
der Show-Datei, der andere maskiert im DMX-Ausgang — beides eigene Baustellen.
"""
from __future__ import annotations
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.core.app_state import get_state
from src.core.show.show_file import reset_show
from src.ui.views.snap_file_panel import ChannelSelectDialog, _scope_heads
from src.ui.widgets.fan_tool import FanTool


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


class ScopeHeadsTest(unittest.TestCase):
    """Der Speicher-Scope kennt jetzt auch Köpfe."""

    def setUp(self):
        _app()
        reset_show()
        self.state = get_state()

    def test_whole_device_selection_has_no_head_scope(self):
        self.state.set_selected_fids([4, 5])
        self.assertEqual(self.state.active_scope_heads(), {},
                         "ganz gewähltes Gerät darf keine Kopf-Einschränkung setzen")

    def test_head_selection_yields_head_scope(self):
        self.state.set_selected_cells(["4:1", "4:2", "5"])
        self.assertEqual(self.state.active_scope_heads(), {4: {1, 2}})
        self.assertEqual(self.state.active_scope_fids(), [4, 5])

    def test_helper_tolerates_state_without_api(self):
        class _Old:
            pass
        self.assertEqual(_scope_heads(_Old()), {})


class SnapScopeTest(unittest.TestCase):
    """Snap-Aufnahme: nur die gewählten Köpfe."""

    def setUp(self):
        _app()

    def _dlg(self, prog, **kw):
        dlg = ChannelSelectDialog(prog, None, **kw)
        self.addCleanup(dlg.deleteLater)
        return dlg

    def test_head_scope_filters_other_heads(self):
        prog = {1: {"color_r": 10, "color_r#1": 20, "color_r#2": 30}}
        dlg = self._dlg(prog, scope_fids=[1], scope_heads={1: {1}})
        self.assertEqual(dlg._in_scope(prog), {1: {"color_r#1": 20}})

    def test_head_zero_is_the_plain_key(self):
        prog = {1: {"color_r": 10, "color_r#1": 20}}
        dlg = self._dlg(prog, scope_fids=[1], scope_heads={1: {0}})
        self.assertEqual(dlg._in_scope(prog), {1: {"color_r": 10}})

    def test_without_head_scope_everything_stays(self):
        prog = {1: {"color_r": 10, "color_r#1": 20}}
        dlg = self._dlg(prog, scope_fids=[1])
        self.assertEqual(dlg._in_scope(prog), prog)

    def test_device_without_matching_head_drops_out(self):
        prog = {1: {"color_r": 10}, 2: {"color_r#3": 99}}
        dlg = self._dlg(prog, scope_fids=[1, 2], scope_heads={1: {2}, 2: {3}})
        self.assertEqual(dlg._in_scope(prog), {2: {"color_r#3": 99}},
                         "Gerät ohne Wert für den gewählten Kopf muss rausfallen")

    def test_malformed_head_suffix_counts_as_head_zero(self):
        prog = {1: {"color_r#x": 5, "color_r": 7}}
        dlg = self._dlg(prog, scope_fids=[1], scope_heads={1: {0}})
        self.assertEqual(dlg._in_scope(prog), {1: {"color_r#x": 5, "color_r": 7}})

    def test_other_devices_still_filtered_by_fid_scope(self):
        prog = {1: {"color_r": 1}, 9: {"color_r": 2}}
        dlg = self._dlg(prog, scope_fids=[1], scope_heads={1: {0}})
        self.assertEqual(dlg._in_scope(prog), {1: {"color_r": 1}})


class FanHeadTargetsTest(unittest.TestCase):
    """Fächer über Köpfe statt nur über Geräte."""

    def setUp(self):
        _app()
        reset_show()
        self.state = get_state()
        self.ft = FanTool()
        self.addCleanup(self.ft.deleteLater)

    def test_set_cells_splits_fids_and_heads(self):
        self.ft.set_cells(["7:0", "7:1", "7:2", "7:3"])
        self.assertEqual(self.ft._selected_fids, [7, 7, 7, 7])
        self.assertEqual(self.ft._selected_heads, [0, 1, 2, 3])

    def test_set_selection_keeps_whole_device_semantics(self):
        self.ft.set_selection([3, 4])
        self.assertEqual(self.ft._selected_heads, [None, None])
        self.assertIsNone(self.ft._head_of(0))

    def test_garbage_cells_are_skipped(self):
        self.ft.set_cells(["7:0", "quatsch", None, "8"])
        self.assertEqual(self.ft._selected_fids, [7, 8])
        self.assertEqual(self.ft._selected_heads, [0, None])

    def test_apply_writes_per_head_values(self):
        # Kernnutzen: vier Köpfe EINES Geräts bekommen VERSCHIEDENE Werte.
        self.ft.set_cells(["7:0", "7:1", "7:2", "7:3"])
        self.ft._slider_min.setValue(0)
        self.ft._slider_max.setValue(255)
        self._pick_attr("color_r")
        for i in range(self.ft._combo_mode.count()):
            if self.ft._combo_mode.itemData(i) == "Start":
                self.ft._combo_mode.setCurrentIndex(i)
                break
        self.ft._apply()
        vals = [self.state.get_programmer_value(7, "color_r", head=h)
                for h in range(4)]
        self.assertTrue(all(v is not None for v in vals),
                        f"nicht alle Köpfe beschrieben: {vals}")
        self.assertEqual(len(set(vals)), 4, f"kein Verlauf über die Köpfe: {vals}")

    def _pick_attr(self, attr: str):
        """Attribut im Combo wählen — der Default ist „Pan", nicht das, was ein
        Test zufällig annimmt."""
        for i in range(self.ft._combo_attr.count()):
            if self.ft._combo_attr.itemData(i) == attr:
                self.ft._combo_attr.setCurrentIndex(i)
                return
        self.fail(f"Fan-Attribut {attr!r} nicht im Combo")

    def test_apply_whole_devices_unchanged(self):
        # Regressionsschutz: ohne Kopf-Ziele schreibt der Fächer wie bisher auf
        # den einfachen Schlüssel (Kopf 0).
        self.ft.set_selection([5, 6])
        self._pick_attr("intensity")
        self.ft._slider_min.setValue(10)
        self.ft._slider_max.setValue(200)
        self.ft._apply()
        self.assertIsNotNone(self.state.get_programmer_value(5, "intensity", head=0))
        self.assertIsNone(self.state.get_programmer_value(5, "intensity", head=1))

    def test_head_labels_are_shown_in_the_preview(self):
        self.ft.set_cells(["7:0", "7:2"])
        rows = self.ft._table.rowCount()
        self.assertEqual(rows, 2)
        texts = [self.ft._table.item(r, 1).text() for r in range(rows)]
        self.assertTrue(any("K1" in t for t in texts), texts)
        self.assertTrue(any("K3" in t for t in texts), texts)


if __name__ == "__main__":
    unittest.main()
