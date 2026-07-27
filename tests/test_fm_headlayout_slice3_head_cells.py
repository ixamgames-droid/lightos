"""FM-HEADLAYOUT Slice 3: Kopf-Zellen im Gruppen-Raster von Hand anordnen.

Davids Kernwunsch aus der Live-Session: die Köpfe eines Multi-Head-Strahlers
(Hydrabeam, Spider-Bar) im Gruppen-/Raster-Editor **frei platzieren** — „mal
hochkant, mal horizontal, je nach realem Rig-Aufbau". Bisher konnte man ein
Mehrkopf-Gerät nur als EINE ganze Zelle ins Raster ziehen; Kopf-Zellen
(``"fid:head"``) entstanden ausschliesslich automatisch beim Patchen als 1×N-Reihe
(``create_head_matrix_group``) und liessen sich nur nachträglich verschieben.

Neu: ``FixtureGridWidget.place_fixture_heads(fid, n, col, row, vertical=…)`` setzt
die N Köpfe als Streifen (Zeile ODER Spalte) und ``collapse_fixture_heads(fid)``
fasst sie wieder zu einer Zelle zusammen. Beide halten die Raster-Invarianten des
externen Drops: kein stilles Überschreiben, kein Duplikat desselben Geräts.
"""
from __future__ import annotations
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.app_state import get_state
from src.core.database.fixture_db import engine as fdb_engine, ensure_builtins
from src.core.database.models import PatchedFixture, FixtureProfile
from src.core.group_cells import base_fids_in_grid_order
from src.core.show.show_file import reset_show
from src.ui.views.fixture_group_view import FixtureGridWidget, FixtureGroupView


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _pid(short: str) -> int:
    with Session(fdb_engine()) as s:
        return int(s.execute(select(FixtureProfile.id).where(
            FixtureProfile.short_name == short)).scalar_one())


class HeadStripPlacementTest(unittest.TestCase):
    """Reine Raster-Logik (ohne Patch/DB) — Streifen, Orientierung, Invarianten."""

    def setUp(self):
        _app()
        self.gw = FixtureGridWidget()
        self.gw.set_grid(8, 8)
        self.addCleanup(self.gw.deleteLater)

    def test_horizontal_strip_is_contiguous_row(self):
        cells = self.gw.place_fixture_heads(7, 4, 2, 3)
        self.assertEqual(cells, [(2, 3), (3, 3), (4, 3), (5, 3)])
        self.assertEqual([self.gw.positions[c] for c in cells],
                         ["7:0", "7:1", "7:2", "7:3"])

    def test_vertical_strip_is_contiguous_column(self):
        cells = self.gw.place_fixture_heads(7, 4, 2, 1, vertical=True)
        self.assertEqual(cells, [(2, 1), (2, 2), (2, 3), (2, 4)])
        self.assertEqual([self.gw.positions[c] for c in cells],
                         ["7:0", "7:1", "7:2", "7:3"])

    def test_strip_start_shifts_back_to_stay_contiguous(self):
        # Start so weit rechts, dass 4 Köpfe nicht mehr passen (Spalten 0..7)
        # -> Start rutscht auf 4, statt hinten abzuschneiden/zu streuen.
        cells = self.gw.place_fixture_heads(7, 4, 6, 0)
        self.assertEqual(cells, [(4, 0), (5, 0), (6, 0), (7, 0)])

    def test_strip_shift_also_vertical(self):
        cells = self.gw.place_fixture_heads(7, 3, 1, 7, vertical=True)
        self.assertEqual(cells, [(1, 5), (1, 6), (1, 7)])

    def test_occupied_cell_is_not_overwritten(self):
        self.gw.positions[(3, 0)] = 99            # fremdes Gerät im Weg
        cells = self.gw.place_fixture_heads(7, 3, 2, 0)
        self.assertEqual(self.gw.positions[(3, 0)], 99, "fremde Zelle überschrieben")
        self.assertEqual(len(cells), 3, "ein Kopf ist verloren gegangen")
        self.assertEqual(len(set(cells)), 3, "zwei Köpfe auf derselben Zelle")
        self.assertEqual({self.gw.positions[c] for c in cells},
                         {"7:0", "7:1", "7:2"})

    def test_replaces_own_whole_fixture_cell_no_duplicate(self):
        self.gw.place_fixture(7, 0, 0)            # erst als ganzes Gerät
        self.gw.place_fixture_heads(7, 4, 0, 2)   # dann kopfweise
        self.assertNotIn(7, self.gw.positions.values(),
                         "Ganz-Fixture-Zelle blieb neben den Kopf-Zellen liegen")
        self.assertEqual(base_fids_in_grid_order(
            {f"{c},{r}": v for (c, r), v in self.gw.positions.items()}), [7])

    def test_second_call_moves_instead_of_duplicating(self):
        self.gw.place_fixture_heads(7, 4, 0, 0)
        cells = self.gw.place_fixture_heads(7, 4, 0, 5, vertical=False)
        self.assertEqual(cells, [(0, 5), (1, 5), (2, 5), (3, 5)])
        self.assertEqual(len(self.gw.positions), 4, "alte Kopf-Zellen blieben liegen")

    def test_full_grid_places_nothing_and_destroys_nothing(self):
        self.gw.set_grid(2, 1)
        self.gw.positions[(0, 0)] = 41
        self.gw.positions[(1, 0)] = 42
        cells = self.gw.place_fixture_heads(7, 2, 0, 0)
        self.assertEqual(cells, [])
        self.assertEqual(self.gw.positions, {(0, 0): 41, (1, 0): 42})

    def test_partial_placement_when_grid_almost_full(self):
        self.gw.set_grid(3, 1)
        self.gw.positions[(2, 0)] = 42
        cells = self.gw.place_fixture_heads(7, 4, 0, 0)
        self.assertEqual(len(cells), 2, "es müssen genau die 2 freien Zellen belegt sein")
        self.assertEqual(self.gw.positions[(2, 0)], 42)

    def test_zero_or_negative_count_is_noop(self):
        self.gw.positions[(0, 0)] = 5
        self.assertEqual(self.gw.place_fixture_heads(7, 0, 0, 0), [])
        self.assertEqual(self.gw.place_fixture_heads(7, -3, 0, 0), [])
        self.assertEqual(self.gw.positions, {(0, 0): 5})

    def test_whole_fixture_drop_replaces_own_head_cells_in_full_grid(self):
        # Gegenrichtung zum Streifen: das Gerät als EINE Zelle zurückziehen, obwohl
        # seine Kopf-Zellen das (kleine) Raster komplett füllen — genau die Form der
        # Auto-Kopf-Matrix (1×N). Vorher scheiterte der Drop still, weil die
        # Zielsuche die eigenen Zellen als belegt zählte.
        self.gw.set_grid(2, 1)
        self.gw.place_fixture_heads(7, 2, 0, 0)
        self.assertEqual(len(self.gw.positions), 2, "Vorbedingung: Raster voll")
        target = self.gw.place_fixture(7, 0, 0)
        self.assertEqual(target, (0, 0))
        self.assertEqual(self.gw.positions, {(0, 0): 7})

    def test_foreign_full_grid_still_blocks_drop(self):
        # Gegenprobe zur Zeile davor: FREMDE Zellen bleiben Blocker.
        self.gw.set_grid(2, 1)
        self.gw.positions[(0, 0)] = 41
        self.gw.positions[(1, 0)] = 42
        self.assertIsNone(self.gw.place_fixture(7, 0, 0))
        self.assertEqual(self.gw.positions, {(0, 0): 41, (1, 0): 42})

    def test_highlight_matches_placement_for_own_head_cells(self):
        # Highlight (resolve_drop_cell) und echte Platzierung müssen dieselbe Zelle
        # nennen — sonst rastet der Drop woanders ein als angezeigt.
        self.gw.set_grid(2, 1)
        self.gw.place_fixture_heads(7, 2, 0, 0)
        preview = self.gw.resolve_drop_cell(7, 1, 0)
        self.assertEqual(preview, self.gw.place_fixture(7, 1, 0))

    def test_collapse_heads_back_to_single_cell(self):
        self.gw.place_fixture_heads(7, 4, 1, 2)
        cell = self.gw.collapse_fixture_heads(7)
        self.assertEqual(cell, (1, 2), "Zusammenfassen landet nicht auf der ersten Kopf-Zelle")
        self.assertEqual(self.gw.positions, {(1, 2): 7})

    def test_collapse_uses_first_cell_in_grid_order(self):
        # Köpfe verstreut: Raster-Reihenfolge ist Zeile, dann Spalte.
        self.gw.positions[(5, 4)] = "7:0"
        self.gw.positions[(1, 2)] = "7:1"
        self.gw.positions[(3, 2)] = "7:2"
        self.assertEqual(self.gw.collapse_fixture_heads(7), (1, 2))
        self.assertEqual(self.gw.positions, {(1, 2): 7})

    def test_collapse_without_head_cells_changes_nothing(self):
        self.gw.positions[(0, 0)] = 7             # ganzes Gerät, keine Köpfe
        self.assertIsNone(self.gw.collapse_fixture_heads(7))
        self.assertEqual(self.gw.positions, {(0, 0): 7})

    def test_collapse_leaves_other_fixtures_alone(self):
        self.gw.place_fixture_heads(7, 3, 0, 0)
        self.gw.positions[(0, 4)] = "8:0"
        self.gw.positions[(1, 4)] = "8:1"
        self.gw.collapse_fixture_heads(7)
        self.assertEqual(self.gw.positions[(0, 4)], "8:0")
        self.assertEqual(self.gw.positions[(1, 4)], "8:1")

    def test_head_cells_stay_individually_movable_and_removable(self):
        # Der bestehende interne Drag/Rechtsklick-Pfad muss auf Kopf-Zellen wirken
        # (FM-16e): eine Kopf-Zelle allein verschieben bzw. entfernen.
        self.gw.place_fixture_heads(7, 4, 0, 0)
        self.gw.positions[(0, 3)] = self.gw.positions.pop((2, 0))   # Kopf 2 wandert
        self.assertEqual(self.gw.positions[(0, 3)], "7:2")
        del self.gw.positions[(3, 0)]                               # Kopf 3 weg
        self.assertEqual(sorted(self.gw.positions.values()),
                         ["7:0", "7:1", "7:2"])


class HeadStripViewWiringTest(unittest.TestCase):
    """View-Verdrahtung: Kopfzahl aus derselben Quelle wie die Auto-Kopf-Matrix,
    Baum-Auswahl als Ziel, ehrliche Hinweise statt stiller No-Ops."""

    def setUp(self):
        _app()
        ensure_builtins()
        reset_show()
        self.state = get_state()
        # SPIDER14: color_r/g/b/w DOPPELT -> 2 Köpfe. PAR: Einzelkopf.
        self.state.add_fixture(PatchedFixture(
            fid=1, label="Spider", fixture_profile_id=_pid("SPIDER14"),
            mode_name="14-Kanal", universe=1, address=1, channel_count=14,
            manufacturer_name="U King", fixture_name="Spider 14ch",
            fixture_type="moving_head"), undoable=False)
        self.state.add_fixture(PatchedFixture(
            fid=2, label="PAR", fixture_profile_id=_pid("ZQ01424"),
            mode_name="8-Kanal RGBW", universe=1, address=20, channel_count=8,
            manufacturer_name="Generic", fixture_name="Stage Light ZQ01424",
            fixture_type="par"), undoable=False)
        self.view = FixtureGroupView()
        self.addCleanup(self.view.deleteLater)

    def _select_tree_fid(self, fid: int) -> bool:
        """Das Baum-Item mit diesem fid selektieren (True bei Erfolg)."""
        tree = self.view._fixture_list
        from PySide6.QtCore import Qt
        for i in range(tree.topLevelItemCount()):
            top = tree.topLevelItem(i)
            for j in range(top.childCount()):
                child = top.child(j)
                if child.data(0, Qt.ItemDataRole.UserRole) == fid:
                    tree.setCurrentItem(child)
                    return True
        return False

    def test_places_two_head_cells_for_spider(self):
        self.assertTrue(self._select_tree_fid(1), "Spider nicht im Baum")
        with patch("src.ui.views.fixture_group_view.QMessageBox.information") as info:
            self.view._place_heads_horizontal()
        info.assert_not_called()
        vals = sorted(self.view._grid_widget.positions.values())
        self.assertEqual(vals, ["1:0", "1:1"])

    def test_vertical_variant_grows_rows_instead_of_tipping_over(self):
        # Der View öffnet auf der beim Patchen automatisch angelegten
        # Kopf-Matrix-Gruppe („Spider · Köpfe", 1 Reihe). Ein hochkant-Streifen
        # passt dort NICHT — das Raster muss wachsen, statt die Köpfe über die
        # Ausweich-Regel wieder waagerecht zu verteilen.
        self.assertTrue(self._select_tree_fid(1))
        gw = self.view._grid_widget
        self.assertEqual(gw.rows, 1, "Vorbedingung: Auto-Kopf-Matrix ist 1 Reihe")
        self.view._place_heads_vertical()
        self.assertGreaterEqual(gw.rows, 2, "Reihen sind nicht mitgewachsen")
        self.assertEqual(self.view._spin_rows.value(), gw.rows,
                         "Spinbox zeigt eine andere Reihenzahl als das Raster")
        cells = [c for c, v in gw.positions.items() if str(v).startswith("1:")]
        self.assertEqual(len(cells), 2)
        self.assertEqual(len({c for c, _r in cells}), 1, "Köpfe nicht in EINER Spalte")

    def test_single_head_fixture_gets_honest_hint_not_silent_noop(self):
        self.assertTrue(self._select_tree_fid(2), "PAR nicht im Baum")
        before = dict(self.view._grid_widget.positions)
        with patch("src.ui.views.fixture_group_view.QMessageBox.information") as info:
            self.view._place_heads_horizontal()
        info.assert_called_once()
        self.assertEqual(self.view._grid_widget.positions, before,
                         "Einzelkopf-PAR hat das Raster verändert")

    def test_no_selection_but_single_device_group_resolves_target(self):
        # LIVE-FUND: das blaue Hervorheben im Baum sind die GRUPPEN-MITGLIEDER
        # (Hintergrundfarbe), keine Auswahl — bei der frisch gepatchten
        # Kopf-Matrix-Gruppe sah das Gerät gewählt aus, die Aktion verlangte aber
        # ein Anklicken. Enthält die Gruppe genau EIN Gerät, ist das Ziel
        # eindeutig und die Aktion muss laufen (kein Raten).
        self.view._fixture_list.setCurrentItem(None)
        self.view._grid_widget.positions.clear()
        self.view._grid_widget.place_fixture_heads(1, 2, 0, 0)   # nur fid 1 drin
        with patch("src.ui.views.fixture_group_view.QMessageBox.information") as info:
            self.view._place_heads_vertical()
        info.assert_not_called()
        cells = [c for c, v in self.view._grid_widget.positions.items()
                 if str(v).startswith("1:")]
        self.assertEqual(len({c for c, _r in cells}), 1, "nicht hochkant gelandet")

    def test_ambiguous_target_gets_hint_that_explains_the_blue(self):
        # Zwei Geräte im Raster, nichts angeklickt -> nicht raten, sondern
        # erklären (der Hinweis muss die blaue Markierung entzaubern).
        self.view._fixture_list.setCurrentItem(None)
        gw = self.view._grid_widget
        gw.positions.clear()
        gw.set_grid(4, 4)
        gw.place_fixture(1, 0, 0)
        gw.place_fixture(2, 1, 0)
        before = dict(gw.positions)
        with patch("src.ui.views.fixture_group_view.QMessageBox.information") as info:
            self.view._place_heads_horizontal()
        info.assert_called_once()
        _args = info.call_args[0]
        self.assertIn("blaue Markierung", _args[2],
                      "Hinweis erklärt die blaue Mitglieder-Markierung nicht")
        self.assertEqual(gw.positions, before)

    def test_single_selected_item_is_used_as_target(self):
        self.view._fixture_list.setCurrentItem(None)
        tree = self.view._fixture_list
        from PySide6.QtCore import Qt as _Qt
        for i in range(tree.topLevelItemCount()):
            top = tree.topLevelItem(i)
            for j in range(top.childCount()):
                child = top.child(j)
                if child.data(0, _Qt.ItemDataRole.UserRole) == 1:
                    child.setSelected(True)
        self.assertEqual(self.view._target_fid(), 1)

    def test_collapse_via_view_round_trip(self):
        self.assertTrue(self._select_tree_fid(1))
        self.view._place_heads_horizontal()
        with patch("src.ui.views.fixture_group_view.QMessageBox.information") as info:
            self.view._collapse_heads()
        info.assert_not_called()
        self.assertEqual(list(self.view._grid_widget.positions.values()), [1])

    def test_collapse_without_heads_gets_hint(self):
        self.assertTrue(self._select_tree_fid(1))
        self.view._grid_widget.place_fixture(1, 0, 0)      # ganzes Gerät
        before = dict(self.view._grid_widget.positions)
        with patch("src.ui.views.fixture_group_view.QMessageBox.information") as info:
            self.view._collapse_heads()
        info.assert_called_once()
        self.assertEqual(self.view._grid_widget.positions, before)
        self.assertEqual(before, {(0, 0): 1},
                         "place_fixture hat die Auto-Kopf-Zellen nicht ersetzt")


if __name__ == "__main__":
    unittest.main()
