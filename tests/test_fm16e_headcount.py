"""FM16E-HEADCOUNT: Kopf-Matrix-Gruppen zeigen ihre Geräte statt „(0)".

Eine per ``create_head_matrix_group`` entstandene Gruppe hat Zellwerte ``"fid:head"``
(statt ganzer ``fid``). Mehrere fid-Resolver parsten den Zellwert je für sich per
``int(v)`` → das warf bei ``"5:2"`` und liess die Kopf-Zelle STILL fallen: die Gruppe
erschien mit ``(0)`` Geräten und selektierte nichts. Jetzt läuft ALLES über die eine
Quelle ``src.core.group_cells`` (``parse_group_cell`` / ``base_fids_in_grid_order``).

Deckt ab:
- ``group_cells`` rein (Parsing, Dedup, Rasterreihenfolge, Rückwärtskompat);
- die beiden schon-korrekten Parser (``rgb_matrix._parse_cell`` /
  ``fixture_group_view._split_cell``) delegieren identisch → keine Drift;
- die 4 gefixten Resolver: Core ``group_fids_by_name`` + ``list_fixture_groups``,
  ``ProgrammerView._group_fids``, ``EfxView._active_group_fids``.

Headless (QT_QPA_PLATFORM=offscreen).
"""
from __future__ import annotations
import json
import os
import unittest
from types import SimpleNamespace as NS

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.core.group_cells import parse_group_cell, base_fids_in_grid_order
from src.core.app_state import get_state
from src.core.database.fixture_db import ensure_builtins
from src.core.database.models import FixtureGroup
from src.core.show.show_file import reset_show


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


# Kopf-Matrix 1×4 (Fixture 5, 4 Köpfe): Zellen "5:0".."5:3" in einer Spalte.
HEAD_MATRIX_1x4 = {"0,0": "5:0", "1,0": "5:1", "2,0": "5:2", "3,0": "5:3"}
# 2× Hydrabeam (fids 5,7) je 4 Köpfe, vertikal gestapelt (Merge-Ergebnis 4×2).
HEAD_MATRIX_MERGED = {**HEAD_MATRIX_1x4,
                      "0,1": "7:0", "1,1": "7:1", "2,1": "7:2", "3,1": "7:3"}
# Alt-Gruppe: reine fids (Rückwärtskompat).
PLAIN_GROUP = {"0,0": 3, "1,0": 1, "0,1": 9}
# Gemischt: ein ganzes Fixture + eine Kopf-Matrix.
MIXED_GROUP = {"0,0": 2, "0,1": "5:0", "1,1": "5:1"}


# ── Rein: kanonischer Parser ──────────────────────────────────────────────────
class GroupCellsUnitTest(unittest.TestCase):
    def test_parse_head_cell(self):
        self.assertEqual(parse_group_cell("5:2"), (5, 2))

    def test_parse_whole_fid(self):
        self.assertEqual(parse_group_cell(7), (7, None))
        self.assertEqual(parse_group_cell("7"), (7, None))

    def test_parse_unparsable(self):
        self.assertEqual(parse_group_cell("x:y"), (None, None))
        self.assertEqual(parse_group_cell(None), (None, None))

    def test_head_matrix_yields_base_fid_deduped(self):
        self.assertEqual(base_fids_in_grid_order(HEAD_MATRIX_1x4), [5])

    def test_merged_matrix_grid_order(self):
        # Rasterreihenfolge Zeile-dann-Spalte: erst Spalte 0 (fid 5), dann 1 (fid 7).
        self.assertEqual(base_fids_in_grid_order(HEAD_MATRIX_MERGED), [5, 7])

    def test_plain_group_unchanged(self):
        self.assertEqual(base_fids_in_grid_order(PLAIN_GROUP), [3, 1, 9])

    def test_mixed_group(self):
        self.assertEqual(base_fids_in_grid_order(MIXED_GROUP), [2, 5])

    def test_empty(self):
        self.assertEqual(base_fids_in_grid_order({}), [])
        self.assertEqual(base_fids_in_grid_order(None), [])


# ── Rein: die beiden Alt-Parser delegieren identisch (keine Drift) ────────────
class DelegationIdentityTest(unittest.TestCase):
    def test_rgb_matrix_parse_cell_delegates(self):
        from src.core.engine.rgb_matrix import _parse_cell
        for v in ("5:2", 7, "7", "x:y", None, "9:0"):
            self.assertEqual(_parse_cell(v), parse_group_cell(v), f"_parse_cell({v!r})")

    def test_fixture_group_view_split_cell_delegates(self):
        from src.ui.views.fixture_group_view import _split_cell
        for v in ("5:2", 7, "7", "x:y", None, "9:0"):
            self.assertEqual(_split_cell(v), parse_group_cell(v), f"_split_cell({v!r})")


# ── Rein: ProgrammerView._group_fids (staticmethod) ───────────────────────────
class ProgrammerViewGroupFidsTest(unittest.TestCase):
    def _fids(self, positions):
        from src.ui.views.programmer_view import ProgrammerView
        return ProgrammerView._group_fids(NS(positions_json=json.dumps(positions)))

    def test_head_matrix_not_empty(self):
        self.assertEqual(self._fids(HEAD_MATRIX_1x4), [5])

    def test_merged(self):
        self.assertEqual(self._fids(HEAD_MATRIX_MERGED), [5, 7])

    def test_plain_unchanged(self):
        self.assertEqual(self._fids(PLAIN_GROUP), [3, 1, 9])


# ── End-to-End: Resolver gegen eine echte Show-DB-Gruppe ──────────────────────
class _ShowBase(unittest.TestCase):
    def setUp(self):
        _app()
        ensure_builtins()
        reset_show()
        self.state = get_state()

    def _add_group(self, name, positions) -> int:
        with self.state._session() as s:
            g = FixtureGroup(name=name, cols=8, rows=8,
                             positions_json=json.dumps(positions))
            s.add(g)
            s.commit()
            return g.id


class CoreResolverHeadMatrixTest(_ShowBase):
    def test_group_fids_by_name_head_matrix(self):
        # DER Kernbug: vor dem Fix -> [] ("(0) Geräte"). Jetzt -> [5].
        self._add_group("Hydra · Köpfe", HEAD_MATRIX_1x4)
        self.assertEqual(self.state.group_fids_by_name("Hydra · Köpfe"), [5])

    def test_group_fids_by_name_merged(self):
        self._add_group("Merge · Köpfe", HEAD_MATRIX_MERGED)
        self.assertEqual(self.state.group_fids_by_name("Merge · Köpfe"), [5, 7])

    def test_group_fids_by_name_plain_unchanged(self):
        self._add_group("Alt", PLAIN_GROUP)
        self.assertEqual(self.state.group_fids_by_name("Alt"), [3, 1, 9])

    def test_select_group_by_name_head_matrix(self):
        gid = self._add_group("Sel · Köpfe", HEAD_MATRIX_1x4)
        self.assertTrue(self.state.select_group_by_name((gid, "Sel · Köpfe")))
        self.assertEqual(self.state.selected_fids, [5])

    def test_list_fixture_groups_head_matrix(self):
        self._add_group("Liste · Köpfe", HEAD_MATRIX_1x4)
        entry = next(g for g in self.state.list_fixture_groups()
                     if g["name"] == "Liste · Köpfe")
        self.assertEqual(entry["fids"], [5])


class EfxActiveGroupFidsTest(_ShowBase):
    def test_active_group_fids_head_matrix(self):
        from src.ui.views.efx_view import EfxView
        gid = self._add_group("EFX · Köpfe", HEAD_MATRIX_MERGED)
        self.state.set_selected_group_id(gid)
        v = EfxView()
        try:
            self.assertEqual(v._active_group_fids(), {5, 7})
        finally:
            v.deleteLater()


class LiveViewHeadMatrixTest(_ShowBase):
    """live_view Gruppen-Panel: Kopf-Matrix-Gruppe zeigt GERAETE-Count + hebt die
    Basis-fids hervor (vorher: „(4)" + toter Highlight, weil Roh-Strings in ein
    set[int] gingen; Review-Fund FM16E-HEADCOUNT)."""

    def test_group_panel_uses_base_fids(self):
        from PySide6.QtWidgets import QListWidgetItem
        from PySide6.QtCore import Qt
        from src.ui.views.live_view import LiveView
        gid = self._add_group("Live · Köpfe", HEAD_MATRIX_1x4)  # Fixture 5, 4 Köpfe
        lv = LiveView()
        try:
            lv._refresh_group_list()
            texts = [lv._group_list.item(i).text()
                     for i in range(lv._group_list.count())]
            self.assertIn("Live · Köpfe (1)", texts,
                          f"Count zeigt Geräte, nicht Zellen: {texts}")
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, gid)
            lv._on_group_selected(item)
            self.assertEqual(lv._canvas._highlight_fids, {5},
                             "Highlight muss den Basis-fid (int) treffen")
            self.assertEqual(lv._lbl_group_count.text(), "1 Fixtures")
        finally:
            lv.deleteLater()


if __name__ == "__main__":
    unittest.main()
