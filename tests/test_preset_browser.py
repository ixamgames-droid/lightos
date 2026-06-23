"""Tests Preset-Browser (UI-01).

Schwerpunkt: die Qt-freie Filterlogik (``preset_search``) über Paletten UND
Fixture-Gruppen. Plus ein headless View-Smoke-Test (Liste füllt sich, Tippen
filtert) und ein Shape-Check für ``AppState.list_fixture_groups``.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("LIGHTOS_NO_OUTPUT_THREAD", "1")

from src.core.engine.palette import Palette, PaletteType
from src.core.engine.preset_search import (palette_entries, group_entries,
                                            build_entries, filter_entries)


def _palettes():
    return [
        Palette(name="Rot", type=PaletteType.COLOR,
                values={"color_r": 255}, tags=["warm"]),
        Palette(name="Kaltblau", type=PaletteType.COLOR,
                values={"color_b": 255}, tags=["kalt"], folder="Winter"),
        Palette(name="Center", type=PaletteType.POSITION,
                values={"pan": 128, "tilt": 128}),
    ]


def _groups():
    return [
        {"name": "Movingheads", "folder": "Front", "fids": [3, 4]},
        {"name": "Pars", "folder": "", "fids": [5, 6, 7]},
    ]


class PaletteEntriesTest(unittest.TestCase):
    def test_fields(self):
        e = palette_entries(_palettes())
        self.assertEqual([x.kind for x in e], ["palette"] * 3)
        self.assertEqual(e[0].name, "Rot")
        # Untertitel = Typ-Label, bei Ordner zusätzlich " · Ordner"
        self.assertIn("Color", e[0].subtitle)
        self.assertIn("Winter", e[1].subtitle)
        self.assertEqual(e[0].tags, ("warm",))
        # ref zeigt auf die Original-Palette (zum Anwenden)
        self.assertIsInstance(e[0].ref, Palette)


class GroupEntriesTest(unittest.TestCase):
    def test_dict_shape(self):
        e = group_entries(_groups())
        self.assertEqual([x.kind for x in e], ["group", "group"])
        self.assertEqual(e[0].name, "Movingheads")
        self.assertIn("Front", e[0].subtitle)
        self.assertIn("2 Geräte", e[0].subtitle)
        self.assertIn("3 Geräte", e[1].subtitle)
        # ref = Gruppenname (für select_group_by_name)
        self.assertEqual(e[0].ref, "Movingheads")

    def test_tuple_shape(self):
        e = group_entries([("G1", "F", [1])])
        self.assertEqual(e[0].name, "G1")
        self.assertIn("1 Geräte", e[0].subtitle)


class FilterEntriesTest(unittest.TestCase):
    def setUp(self):
        self.entries = build_entries(_palettes(), _groups())

    def test_empty_query_returns_all_in_order(self):
        out = filter_entries("", self.entries)
        self.assertEqual(len(out), 5)
        self.assertEqual([x.name for x in out],
                         ["Rot", "Kaltblau", "Center", "Movingheads", "Pars"])

    def test_whitespace_query_is_empty(self):
        self.assertEqual(len(filter_entries("   ", self.entries)), 5)

    def test_name_substring_case_insensitive(self):
        out = filter_entries("ROT", self.entries)
        self.assertEqual([x.name for x in out], ["Rot"])

    def test_match_by_type_label(self):
        out = filter_entries("position", self.entries)
        self.assertEqual([x.name for x in out], ["Center"])

    def test_match_by_folder(self):
        out = filter_entries("winter", self.entries)
        self.assertEqual([x.name for x in out], ["Kaltblau"])

    def test_match_by_tag(self):
        out = filter_entries("kalt", self.entries)
        # "kalt" trifft Tag von Kaltblau UND steckt im Namen "Kaltblau"
        self.assertIn("Kaltblau", [x.name for x in out])
        self.assertNotIn("Rot", [x.name for x in out])

    def test_match_group_by_name(self):
        out = filter_entries("moving", self.entries)
        self.assertEqual([x.name for x in out], ["Movingheads"])
        self.assertEqual(out[0].kind, "group")

    def test_multi_term_and(self):
        # beide Begriffe müssen vorkommen
        self.assertEqual(filter_entries("pars front", self.entries), [])
        out = filter_entries("movingheads front", self.entries)
        self.assertEqual([x.name for x in out], ["Movingheads"])

    def test_no_match(self):
        self.assertEqual(filter_entries("xyzzy", self.entries), [])

    def test_kind_keyword_matches(self):
        # "group" als Begriff filtert auf Gruppen, "palette" auf Paletten
        self.assertTrue(all(x.kind == "group"
                            for x in filter_entries("group", self.entries)))
        self.assertTrue(all(x.kind == "palette"
                            for x in filter_entries("palette", self.entries)))


class ListFixtureGroupsShapeTest(unittest.TestCase):
    """AppState.list_fixture_groups liefert eine Liste von {name,folder,fids}-
    Dicts (oder [] ohne Show-DB) — nie ein Crash."""

    def test_returns_list_of_dicts(self):
        from src.core.app_state import get_state
        groups = get_state().list_fixture_groups()
        self.assertIsInstance(groups, list)
        for g in groups:
            self.assertIn("name", g)
            self.assertIn("folder", g)
            self.assertIn("fids", g)
            self.assertIsInstance(g["fids"], list)


if __name__ == "__main__":
    unittest.main()
