"""Patch → Fixture-Gruppen (Grid-Editor) — UX-Fixes (PATCH-GRP-01).

Zwei reproduzierbare Live-Fallen (David, Show-Bau 2026-07-07):

1) Gruppen-Auswahl sprang nach „+ Neu"/„Speichern" hart auf die alphabetisch
   erste Gruppe zurück (`_reload_group_list` setzte `_current_group = groups[0]`).
   Folge: Drags/Speichern trafen die FALSCHE Gruppe (Spiders → MovingHeads).
   Fix: die gewählte Gruppe wird per ID erhalten; `+ Neu` selektiert die neue.

2) Externer Drop aufs Raster überschrieb belegte Zellen still und verpuffte am
   Rand. Fix: `place_fixture`/`_nearest_free_cell` weichen auf die nächste FREIE
   Zelle aus, Rand wird geklemmt; Live-Highlight (`resolve_drop_cell`) zeigt das
   Einrasten. Plus Shortcut „Alle → Raster" (`_add_all_fixtures`).

Alles headless (QT_QPA_PLATFORM=offscreen via conftest).
"""
from __future__ import annotations
import json
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.app_state import get_state
from src.core.database.fixture_db import engine as fdb_engine, ensure_builtins
from src.core.database.models import PatchedFixture, FixtureProfile, FixtureGroup
from src.core.show.show_file import reset_show
from src.ui.views.fixture_group_view import FixtureGridWidget, FixtureGroupView


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _pid(short: str) -> int:
    with Session(fdb_engine()) as s:
        return int(s.execute(select(FixtureProfile.id).where(
            FixtureProfile.short_name == short)).scalar_one())


# ── Gruppe 1: Grid-Widget-Zielfindung (rein logisch, keine DB) ────────────────

class GridPlacementTest(unittest.TestCase):
    def _grid(self, cols=8, rows=1) -> FixtureGridWidget:
        _app()
        w = FixtureGridWidget()
        w.set_grid(cols, rows)
        return w

    def test_drop_empty_cell_lands_exactly(self):
        w = self._grid()
        self.assertEqual(w.place_fixture(1, 3, 0), (3, 0))
        self.assertEqual(w.positions.get((3, 0)), 1)

    def test_drop_occupied_finds_nearest_free_no_overwrite(self):
        w = self._grid()
        w.positions = {(2, 0): 99}
        target = w.place_fixture(1, 2, 0)          # Zielzelle belegt
        self.assertIsNotNone(target)
        self.assertNotEqual(target, (2, 0), "darf nicht auf die belegte Zelle")
        self.assertEqual(w.positions.get((2, 0)), 99, "Altbelegung bleibt (kein Overwrite)")
        self.assertEqual(w.positions.get(target), 1)
        # naechste freie zu (2,0) in 8x1 ist (1,0) oder (3,0) (Distanz 1)
        self.assertIn(target, [(1, 0), (3, 0)])

    def test_drop_same_fid_is_noop(self):
        w = self._grid()
        w.positions = {(4, 0): 5}
        self.assertEqual(w.place_fixture(5, 4, 0), (4, 0))
        self.assertEqual(list(w.positions.values()).count(5), 1, "kein Duplikat")

    def test_drop_moves_existing_fid_frees_old_cell(self):
        w = self._grid()
        w.positions = {(0, 0): 7}
        self.assertEqual(w.place_fixture(7, 5, 0), (5, 0))
        self.assertNotIn((0, 0), w.positions, "alte Zelle freigegeben")
        self.assertEqual(w.positions.get((5, 0)), 7)
        self.assertEqual(list(w.positions.values()).count(7), 1)

    def test_edge_drop_is_clamped(self):
        w = self._grid(cols=8, rows=1)
        # weit rechts/unten daneben -> in die Randzelle statt ins Leere
        self.assertEqual(w.place_fixture(2, 99, 99), (7, 0))
        self.assertEqual(w.positions.get((7, 0)), 2)

    def test_full_grid_does_not_overwrite(self):
        w = self._grid(cols=2, rows=1)
        w.positions = {(0, 0): 10, (1, 0): 20}
        self.assertIsNone(w._nearest_free_cell(0, 0))
        self.assertIsNone(w.place_fixture(30, 0, 0), "voll -> nichts platzieren")
        self.assertEqual(w.positions, {(0, 0): 10, (1, 0): 20}, "unveraendert")

    def test_resolve_drop_cell_matches_actual_placement(self):
        w = self._grid()
        w.positions = {(3, 0): 99}
        resolved = w.resolve_drop_cell(1, 3, 0)     # Highlight-Ziel
        placed = w.place_fixture(1, 3, 0)           # echtes Ablegen
        self.assertEqual(resolved, placed, "Highlight muss dem echten Drop entsprechen")

    def test_first_free_cells_grows_rows(self):
        w = self._grid(cols=8, rows=1)
        cells = w.first_free_cells(13)
        self.assertEqual(len(cells), 13)
        self.assertEqual(len(set(cells)), 13, "keine Doppel")
        self.assertTrue(any(r >= 1 for (_c, r) in cells), "Reihen wachsen ueber rows=1 hinaus")

    def test_first_free_cells_skips_occupied(self):
        w = self._grid(cols=4, rows=2)
        w.positions = {(0, 0): 1, (1, 0): 2}
        cells = w.first_free_cells(3)
        self.assertNotIn((0, 0), cells)
        self.assertNotIn((1, 0), cells)
        self.assertEqual(cells, [(2, 0), (3, 0), (0, 1)])


# ── Gruppe 2: Gruppen-Auswahl bleibt stabil (DB + View) ───────────────────────

class GroupSelectionStabilityTest(unittest.TestCase):
    def setUp(self):
        _app()
        ensure_builtins()
        reset_show()
        self.state = get_state()
        self.view = FixtureGroupView()

    def _add_group(self, name, positions=None) -> int:
        with self.state._session() as s:
            g = FixtureGroup(name=name, cols=8, rows=8,
                             positions_json=json.dumps(positions or {}))
            s.add(g)
            s.commit()
            return g.id

    def test_reload_preserves_current_selection(self):
        # "MovingHeads" sortiert VOR "Spiders" -> frueher sprang die Auswahl.
        self._add_group("MovingHeads")
        gid_sp = self._add_group("Spiders")
        self.view._reload_group_list(select_gid=gid_sp)
        self.assertEqual(self.view._current_group.name, "Spiders")
        # Ein weiterer Reload OHNE Argument darf NICHT auf groups[0] zurueckspringen.
        self.view._reload_group_list()
        self.assertEqual(self.view._current_group.name, "Spiders")
        self.assertIn("Spiders", self.view._combo_group.currentText())

    def test_new_group_selects_new_not_first(self):
        self._add_group("MovingHeads")
        # frisch angelegte Gruppe (wie _new_group es tut) muss selektiert werden
        gid_new = self._add_group("Spiders")
        self.view._reload_group_list(select_gid=gid_new)
        self.assertEqual(self.view._current_group.id, gid_new)
        self.assertEqual(self.view._current_group.name, "Spiders")

    def test_save_writes_to_selected_group_and_keeps_it(self):
        gid_mh = self._add_group("MovingHeads")
        gid_sp = self._add_group("Spiders")
        self.view._reload_group_list(select_gid=gid_sp)
        # Fixtures in die (Spiders-)Rasteransicht ziehen (simuliert per positions)
        self.view._grid_widget.positions = {(0, 0): 1, (1, 0): 2}
        with patch("src.ui.views.fixture_group_view.QMessageBox"):
            self.view._save_group()          # emittiert GROUP_CHANGED -> reload
        # Auswahl bleibt Spiders (kein Rueck-Sprung auf MovingHeads):
        self.assertEqual(self.view._current_group.name, "Spiders")
        # Spiders hat die Fixtures, MovingHeads ist unberuehrt:
        with self.state._session() as s:
            sp = s.get(FixtureGroup, gid_sp)
            mh = s.get(FixtureGroup, gid_mh)
            self.assertEqual(set(json.loads(sp.positions_json).values()), {1, 2})
            self.assertEqual(json.loads(mh.positions_json), {})

    def test_reload_empty_clears_current(self):
        # Keine Gruppen -> current_group None (kein Crash, kein Geister-Load).
        self.view._reload_group_list()
        self.assertIsNone(self.view._current_group)


# ── Gruppe 3: „Alle → Raster"-Shortcut ────────────────────────────────────────

class AddAllFixturesTest(unittest.TestCase):
    def setUp(self):
        _app()
        ensure_builtins()
        reset_show()
        self.state = get_state()
        pid = _pid("ZQ01424")
        for i in range(3):
            self.state.add_fixture(PatchedFixture(
                fid=i + 1, label=f"PAR-{i+1}", fixture_profile_id=pid,
                mode_name="8-Kanal RGBW", universe=1, address=1 + i * 8,
                channel_count=8, manufacturer_name="Generic",
                fixture_name="Stage Light ZQ01424", fixture_type="par"),
                undoable=False)
        self.view = FixtureGroupView()
        self.view._refresh_fixtures()

    def test_add_all_fills_grid_and_grows_rows(self):
        gw = self.view._grid_widget
        gw.set_grid(2, 1)
        self.view._spin_cols.setValue(2)
        self.view._spin_rows.setValue(1)
        self.view._add_all_fixtures()
        self.assertEqual(set(gw.positions.values()), {1, 2, 3})
        self.assertEqual(gw.rows, 2, "3 Fixtures in 2 Spalten -> 2 Reihen")
        self.assertEqual(self.view._spin_rows.value(), 2, "Spinbox nachgezogen")

    def test_add_all_keeps_existing_placements(self):
        gw = self.view._grid_widget
        gw.set_grid(8, 1)
        gw.positions = {(5, 0): 2}      # fid 2 liegt schon fest
        self.view._add_all_fixtures()
        self.assertEqual(gw.positions.get((5, 0)), 2, "bestehende Platzierung bleibt")
        self.assertEqual(set(gw.positions.values()), {1, 2, 3})
        self.assertEqual(list(gw.positions.values()).count(2), 1, "kein Duplikat von fid 2")

    def test_add_all_when_all_placed_is_noop(self):
        gw = self.view._grid_widget
        gw.set_grid(8, 1)
        gw.positions = {(0, 0): 1, (1, 0): 2, (2, 0): 3}
        before = dict(gw.positions)
        with patch("src.ui.views.fixture_group_view.QMessageBox"):
            self.view._add_all_fixtures()
        self.assertEqual(gw.positions, before, "alles schon platziert -> unveraendert")


if __name__ == "__main__":
    unittest.main()
