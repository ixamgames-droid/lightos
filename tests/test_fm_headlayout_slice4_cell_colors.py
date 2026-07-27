"""FM-HEADLAYOUT Slice 4: Farbton je Gerät, Helligkeit je Kopf + Legende.

Davids Vision-Baustein (4): „eine schöne UI, die klar anzeigt, welche Zellen zu
welchem Fixture/Kopf gehören." Vorher waren ALLE Rasterzellen gleich blau (nur
Kopf-Zellen minimal dunkler) — in einer zusammengelegten Kopf-Matrix (z. B. 2×
Hydrabeam = 8 Kopf-Zellen) war die Zugehörigkeit nicht ablesbar.

Jetzt: ``fixture_cell_color(fid, head, fid_order)`` gibt je GERÄT einen eigenen
Farbton (Index = Position in der Raster-Reihenfolge, also innerhalb einer Gruppe
garantiert verschieden) und hellt je KOPF auf (K1 dunkel → höhere Köpfe heller),
plus eine Legende „Farbe → Gerät" unter dem Raster.
"""
from __future__ import annotations
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.app_state import get_state
from src.core.database.fixture_db import engine as fdb_engine, ensure_builtins
from src.core.database.models import PatchedFixture, FixtureProfile
from src.core.show.show_file import reset_show
from src.ui.views.fixture_group_view import (
    FixtureGridWidget, FixtureGroupView, fixture_cell_color,
    _FIXTURE_CELL_COLORS,
)


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _pid(short: str) -> int:
    with Session(fdb_engine()) as s:
        return int(s.execute(select(FixtureProfile.id).where(
            FixtureProfile.short_name == short)).scalar_one())


class CellColorTest(unittest.TestCase):
    """Reine Farbfunktion — headless, ohne Widget-Zustand."""

    def setUp(self):
        _app()

    def test_first_device_keeps_the_historic_blue(self):
        # Ein-Geräte-Gruppen sollen aussehen wie vor Slice 4 (kein Gewohnheitsbruch).
        self.assertEqual(fixture_cell_color(7, None, [7]).name().lower(),
                         _FIXTURE_CELL_COLORS[0].lower())

    def test_devices_in_one_group_get_distinct_hues(self):
        order = [5, 6, 7, 8]
        names = {fixture_cell_color(f, None, order).name() for f in order}
        self.assertEqual(len(names), 4, "zwei Geräte teilen denselben Farbton")

    def test_color_follows_position_not_fid_value(self):
        # fid 1 und fid 9 würden bei `fid % 8` kollidieren — die Position im Raster
        # verhindert das genau dann, wenn es zählt (beide in DERSELBEN Gruppe).
        order = [1, 9]
        self.assertNotEqual(fixture_cell_color(1, None, order).name(),
                            fixture_cell_color(9, None, order).name())

    def test_heads_of_one_device_share_hue_but_differ_in_lightness(self):
        order = [3]
        cols = [fixture_cell_color(3, h, order) for h in range(4)]
        hues = {c.hue() for c in cols}
        self.assertEqual(len(hues), 1, "Köpfe eines Geräts haben verschiedene Farbtöne")
        lights = [c.lightness() for c in cols]
        self.assertEqual(lights, sorted(lights), "Kopf-Rampe ist nicht monoton")
        self.assertLess(lights[0], lights[-1], "K1 und Kn sind gleich hell")

    def test_head_lightness_is_capped_for_readable_white_text(self):
        order = [3]
        # Auch ein 12-Kopf-Panel darf nicht so hell werden, dass weisse Schrift
        # unlesbar wird.
        for h in range(12):
            self.assertLessEqual(fixture_cell_color(3, h, order).lightness(), 158)

    def test_two_devices_stay_distinguishable_per_head(self):
        order = [1, 2]
        a = fixture_cell_color(1, 3, order)
        b = fixture_cell_color(2, 0, order)
        self.assertNotEqual(a.hue(), b.hue(),
                            "aufgehellter Kopf von Gerät A trifft Farbton von Gerät B")

    def test_unknown_fid_does_not_crash(self):
        self.assertIsNotNone(fixture_cell_color(99, None, [1, 2]))
        self.assertIsNotNone(fixture_cell_color(None, None, []))

    def test_more_devices_than_palette_wraps_without_error(self):
        order = list(range(1, len(_FIXTURE_CELL_COLORS) + 3))
        cols = [fixture_cell_color(f, None, order) for f in order]
        self.assertEqual(len(cols), len(order))
        self.assertEqual(cols[0].name(), cols[len(_FIXTURE_CELL_COLORS)].name(),
                         "Palette wickelt nicht deterministisch")


class GridPaintUsesPerFixtureColorsTest(unittest.TestCase):
    """Das Raster muss die Farbfunktion wirklich benutzen (eine Farbquelle)."""

    def setUp(self):
        _app()
        self.gw = FixtureGridWidget()
        self.gw.set_grid(8, 8)
        self.addCleanup(self.gw.deleteLater)

    def test_paint_does_not_crash_with_mixed_cells(self):
        # Ganzes Gerät + Kopf-Zellen zweier Geräte gemischt -> paintEvent muss
        # sauber durchlaufen (Farbindex-Auflösung pro Paint).
        self.gw.place_fixture(4, 0, 0)
        self.gw.place_fixture_heads(5, 4, 0, 1)
        self.gw.place_fixture_heads(6, 2, 0, 2)
        self.gw.resize(320, 320)
        self.gw.render(self.gw.grab())     # erzwingt paintEvent ohne Fensterschau
        self.assertEqual(len(self.gw.positions), 7)


class LegendTest(unittest.TestCase):
    """Legende: erst ab zwei Geräten sichtbar, Farben identisch zum Raster."""

    def setUp(self):
        _app()
        ensure_builtins()
        reset_show()
        self.state = get_state()
        self.state.add_fixture(PatchedFixture(
            fid=1, label="Spider", fixture_profile_id=_pid("SPIDER14"),
            mode_name="14-Kanal", universe=1, address=1, channel_count=14,
            manufacturer_name="U King", fixture_name="Spider 14ch",
            fixture_type="moving_head"), undoable=False)
        self.state.add_fixture(PatchedFixture(
            fid=2, label="Bar", fixture_profile_id=_pid("PARBAR4"),
            mode_name="12-Kanal 4×RGB", universe=1, address=40, channel_count=12,
            manufacturer_name="Generic", fixture_name="LED PAR Bar 4×",
            fixture_type="led_bar"), undoable=False)
        self.view = FixtureGroupView()
        self.addCleanup(self.view.deleteLater)

    def test_hidden_for_single_device_grid(self):
        gw = self.view._grid_widget
        gw.positions.clear()
        gw.place_fixture_heads(1, 2, 0, 0)
        self.view._highlight_group_members()
        self.assertFalse(self.view._legend.isVisible())
        self.assertEqual(self.view._legend.text(), "")

    def test_shows_one_entry_per_device_with_matching_color(self):
        gw = self.view._grid_widget
        gw.positions.clear()
        gw.set_grid(8, 8)
        gw.place_fixture_heads(1, 2, 0, 0)
        gw.place_fixture_heads(2, 4, 0, 2)
        self.view._highlight_group_members()
        txt = self.view._legend.text()
        self.assertIn("Spider", txt)
        self.assertIn("Bar", txt)
        # Kopfzahl wird genannt ...
        self.assertIn("2 Köpfe", txt)
        self.assertIn("4 Köpfe", txt)
        # ... und die Farbfelder tragen GENAU die Rasterfarben (keine zweite Quelle).
        order = self.view._group_fids()
        for fid in (1, 2):
            self.assertIn(fixture_cell_color(fid, None, order).name(), txt)

    def test_legend_updates_when_grid_changes(self):
        gw = self.view._grid_widget
        gw.positions.clear()
        gw.set_grid(8, 8)
        gw.place_fixture_heads(1, 2, 0, 0)
        gw.place_fixture(2, 4, 4)
        self.view._highlight_group_members()
        self.assertIn("Bar", self.view._legend.text())
        # Gerät 2 wieder entfernen -> Legende verschwindet (nur noch ein Gerät).
        gw.positions = {c: v for c, v in gw.positions.items()
                        if not str(v).startswith("2")}
        self.view._highlight_group_members()
        self.assertFalse(self.view._legend.isVisible())


if __name__ == "__main__":
    unittest.main()
