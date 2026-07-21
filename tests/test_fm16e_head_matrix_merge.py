"""FM-16 (e): Kopf-Matrizen ZUSAMMENLEGEN + Gruppen-Editor versteht Kopf-Zellen.

- ``AppState._stack_group_grids`` (rein): stapelt mehrere Raster vertikal, Zellwerte
  (``fid`` / ``"fid:head"``) bleiben erhalten.
- ``AppState.merge_head_matrix_groups``: fasst mehrere (Kopf-)Matrix-Gruppen zu EINER
  größeren zusammen (z. B. 2× Hydrabeam 1×4 → eine 4×2), nicht-destruktiv; die Matrix-
  Engine (``grids_from_positions``) spricht die Köpfe weiter einzeln an.
- Gruppen-Editor: ``_load_group`` verwirft ``"fid:head"``-Zellen nicht mehr still,
  ``_group_fids`` liefert die Basis-fids; ``_split_cell`` als Parser.

Alles headless (QT_QPA_PLATFORM=offscreen via conftest).
"""
from __future__ import annotations
import json
import os
import tempfile
import unittest
from types import SimpleNamespace as NS

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import src.core.app_state as A
from src.core.engine.rgb_matrix import grids_from_positions
from src.ui.views.fixture_group_view import _split_cell, FixtureGridWidget


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _rgbw_heads(n):
    """n RGBW-Bänke auf fortlaufenden Kanälen (Multi-Head-Erkennung = color_r-Zahl)."""
    chans, num = [], 1
    for _h in range(n):
        for a in ("color_r", "color_g", "color_b", "color_w"):
            chans.append(NS(attribute=a, channel_number=num, default_value=0))
            num += 1
    return chans


# ── Rein: Zell-Parser ─────────────────────────────────────────────────────────

class SplitCellTest(unittest.TestCase):
    def test_head_cell(self):
        self.assertEqual(_split_cell("5:2"), (5, 2))

    def test_whole_fid_str_and_int(self):
        self.assertEqual(_split_cell("7"), (7, None))
        self.assertEqual(_split_cell(7), (7, None))

    def test_unparsable(self):
        self.assertEqual(_split_cell("x:y"), (None, None))
        self.assertEqual(_split_cell(None), (None, None))


# ── Rein: Raster-Stapeln ──────────────────────────────────────────────────────

class StackGridsTest(unittest.TestCase):
    def test_stack_two_1x4_head_matrices(self):
        g1 = (4, 1, {(0, 0): "5:0", (1, 0): "5:1", (2, 0): "5:2", (3, 0): "5:3"})
        g2 = (4, 1, {(0, 0): "9:0", (1, 0): "9:1", (2, 0): "9:2", (3, 0): "9:3"})
        cols, rows, merged = A.AppState._stack_group_grids([g1, g2])
        self.assertEqual((cols, rows), (4, 2))
        self.assertEqual(merged[(0, 0)], "5:0")   # erste Reihe = Gruppe 1
        self.assertEqual(merged[(3, 0)], "5:3")
        self.assertEqual(merged[(0, 1)], "9:0")   # zweite Reihe = Gruppe 2 (versetzt)
        self.assertEqual(merged[(3, 1)], "9:3")

    def test_varying_widths_take_max(self):
        g1 = (2, 1, {(0, 0): "1:0", (1, 0): "1:1"})
        g2 = (4, 1, {(0, 0): "2:0", (1, 0): "2:1", (2, 0): "2:2", (3, 0): "2:3"})
        cols, rows, merged = A.AppState._stack_group_grids([g1, g2])
        self.assertEqual((cols, rows), (4, 2))
        self.assertEqual(merged[(0, 0)], "1:0")
        self.assertEqual(merged[(3, 1)], "2:3")

    def test_whole_fid_cells_preserved(self):
        g1 = (2, 1, {(0, 0): 5, (1, 0): 6})            # ganze fids (int)
        g2 = (2, 1, {(0, 0): "7:0", (1, 0): "7:1"})
        _c, _r, merged = A.AppState._stack_group_grids([g1, g2])
        self.assertEqual(merged[(0, 0)], 5)
        self.assertEqual(merged[(0, 1)], "7:0")

    def test_multirow_offset_accumulates(self):
        g = (1, 2, {(0, 0): "1:0", (0, 1): "1:1"})     # 1×2
        _c, rows, merged = A.AppState._stack_group_grids([g, g, g])
        self.assertEqual(rows, 6)                       # 3× Höhe 2
        self.assertIn((0, 5), merged)                   # letzte Reihe belegt


# ── Integration: Merge über den echten Show-DB-/Gruppen-Pfad ──────────────────

class MergeHeadMatrixTest(unittest.TestCase):
    def setUp(self):
        self._orig = A.get_channels_for_patched
        A.get_channels_for_patched = lambda fx: _rgbw_heads(4)
        self.state = A.AppState()
        self.state.open_show(tempfile.mktemp(suffix=".db"))

    def tearDown(self):
        A.get_channels_for_patched = self._orig

    def _load(self, gid):
        from sqlalchemy.orm import Session
        from src.core.database.models import FixtureGroup
        with Session(self.state._show_engine) as s:
            return s.get(FixtureGroup, gid)

    def _two_head_groups(self):
        g1 = self.state.create_head_matrix_group(NS(fid=5, label="HydraA", fixture_type="moving_head"))
        g2 = self.state.create_head_matrix_group(NS(fid=9, label="HydraB", fixture_type="moving_head"))
        self.assertIsNotNone(g1)
        self.assertIsNotNone(g2)
        return g1, g2

    def test_merge_stacks_rows_and_keeps_head_cells(self):
        g1, g2 = self._two_head_groups()
        merged = self.state.merge_head_matrix_groups([g1, g2])
        self.assertIsNotNone(merged)
        mg = self._load(merged)
        self.assertEqual((mg.cols, mg.rows), (4, 2))
        self.assertEqual(mg.folder, "Matrizen")
        pos = json.loads(mg.positions_json)
        self.assertEqual(pos["0,0"], "5:0")
        self.assertEqual(pos["3,0"], "5:3")
        self.assertEqual(pos["0,1"], "9:0")
        self.assertEqual(pos["3,1"], "9:3")

    def test_merge_non_destructive(self):
        g1, g2 = self._two_head_groups()
        self.state.merge_head_matrix_groups([g1, g2])
        self.assertEqual((self._load(g1).cols, self._load(g1).rows), (4, 1))
        self.assertEqual((self._load(g2).cols, self._load(g2).rows), (4, 1))

    def test_merged_matrix_addresses_each_head(self):
        g1, g2 = self._two_head_groups()
        merged = self.state.merge_head_matrix_groups([g1, g2])
        pos = json.loads(self._load(merged).positions_json)
        fid_grid, head_grid = grids_from_positions(pos, 4, 2)
        self.assertEqual(fid_grid[0], 5)
        self.assertEqual(head_grid[0], 0)      # Reihe 0, Spalte 0 = fid5 Kopf 0
        self.assertEqual(fid_grid[4], 9)       # idx = row*cols+col = 1*4+0
        self.assertEqual(head_grid[4], 0)
        self.assertEqual(fid_grid[7], 9)
        self.assertEqual(head_grid[7], 3)      # Reihe 1, Spalte 3 = fid9 Kopf 3

    def test_merge_needs_at_least_two(self):
        g1, _g2 = self._two_head_groups()
        self.assertIsNone(self.state.merge_head_matrix_groups([g1]))
        self.assertIsNone(self.state.merge_head_matrix_groups([]))


# ── Editor: Kopf-Zellen nicht mehr stumm verwerfen ────────────────────────────

class EditorHeadCellTest(unittest.TestCase):
    def setUp(self):
        _app()
        from src.core.show.show_file import reset_show
        reset_show()
        from src.ui.views.fixture_group_view import FixtureGroupView
        self.view = FixtureGroupView()

    def test_load_group_preserves_head_cells(self):
        g = NS(cols=4, rows=1,
               positions_json=json.dumps({"0,0": "5:0", "1,0": "5:1",
                                          "2,0": "5:2", "3,0": "5:3"}))
        self.view._current_group = g
        self.view._load_group(g)
        pos = self.view._grid_widget.positions
        # Frueher fielen alle Zellen weg (int("5:0") warf) -> leer.
        self.assertEqual(len(pos), 4)
        self.assertEqual(pos[(0, 0)], "5:0")
        self.assertEqual(pos[(3, 0)], "5:3")

    def test_group_fids_from_head_cells(self):
        g = NS(cols=4, rows=2,
               positions_json=json.dumps({"0,0": "5:0", "1,0": "5:1",
                                          "0,1": "9:0", "1,1": "9:1"}))
        self.view._current_group = g
        self.view._load_group(g)
        fids = self.view._group_fids()
        self.assertEqual(sorted(fids), [5, 9])     # Basis-fids, dedupliziert

    def test_paint_head_cells_does_not_crash(self):
        from PySide6.QtGui import QPixmap
        w = FixtureGridWidget()
        w.set_grid(4, 1)
        w.positions = {(0, 0): "5:0", (1, 0): "5:1", (2, 0): 6, (3, 0): "5:3"}
        w.resize(200, 60)
        pm = QPixmap(w.size())
        w.render(pm)   # ruft paintEvent — darf mit gemischten int/"fid:head" nicht crashen

    def test_place_whole_fid_clears_its_head_cells(self):
        # Review-Fund (LOW): ein extern platziertes GANZES Fixture räumt seine
        # etwaigen Kopf-Zellen desselben fid weg (kein Doppel), Basis-fid-Vergleich.
        w = FixtureGridWidget()
        w.set_grid(8, 2)
        w.positions = {(0, 0): "5:0", (1, 0): "5:1", (2, 0): 6}
        w.place_fixture(5, 4, 1)
        vals = list(w.positions.values())
        self.assertNotIn("5:0", vals)
        self.assertNotIn("5:1", vals)
        self.assertIn(5, vals)      # als ganzes platziert
        self.assertIn(6, vals)      # anderes Fixture unberührt


# ── Review-Fund (HIGH): „Bearbeiten…"-Dialog darf Kopf-Matrizen nicht wipen ────

class GroupEditDialogHeadCellTest(unittest.TestCase):
    def setUp(self):
        _app()

    def _dlg(self, positions_json, cols, rows, labels):
        from src.ui.widgets.group_edit_dialog import GroupEditDialog
        return GroupEditDialog("G", positions_json, cols, rows, labels)

    def test_pure_head_matrix_not_wiped_on_save(self):
        # Frueher: int("5:0") warf -> Mitglieder leer -> Speichern schrieb "{}".
        pj = json.dumps({"0,0": "5:0", "1,0": "5:1", "2,0": "5:2", "3,0": "5:3"})
        out_json, _c, _r = self._dlg(pj, 4, 1, {5: "Hydra"}).result_positions()
        self.assertEqual(json.loads(out_json), json.loads(pj))

    def test_mixed_group_preserves_heads_and_whole_member(self):
        pj = json.dumps({"0,0": "5:0", "1,0": "5:1", "0,1": 7})
        out = json.loads(self._dlg(pj, 2, 2, {5: "A", 7: "B"}).result_positions()[0])
        self.assertEqual(out["0,0"], "5:0")     # Kopf-Zellen erhalten
        self.assertEqual(out["1,0"], "5:1")
        self.assertIn(7, out.values())          # ganzes Mitglied erhalten

    def test_group_member_fids_skips_head_cells(self):
        from src.ui.widgets.group_edit_dialog import group_member_fids
        pj = json.dumps({"0,0": "5:0", "1,0": "5:1", "0,1": 7})
        self.assertEqual(group_member_fids(pj), [7])   # nur ganzes Fixture


if __name__ == "__main__":
    unittest.main()
