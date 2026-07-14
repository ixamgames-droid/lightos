"""QOL-02: 'Zuletzt verwendet' — gleichnamige Shows unterscheidbar + Kanon-Dedup.

Sichert die reinen Helfer aus `main_window` gegen Regression:
- `_recent_menu_labels`: gleicher Dateiname aus verschiedenen Ordnern -> je ein
  unterscheidendes Ordner-Suffix (kuerzestmoeglich); eindeutige Namen bleiben
  schlichtes basename.
- `_canon_path`: gleiche Datei in anderer Schreibweise (Gross/Klein, Slash) faellt
  auf denselben Schluessel; verschiedene Dateien nicht.
- `_add_recent_file`: dedupliziert nach Kanonpfad (ohne die echte recent.json zu
  beruehren — Load/Save sind gemockt).
"""
import os
import unittest
from unittest import mock

from src.ui import main_window as mw


class TestRecentMenuLabels(unittest.TestCase):
    def test_unique_basenames_are_plain(self):
        paths = [r"C:\a\show1.lshow", r"C:\b\show2.lshow"]
        self.assertEqual(mw._recent_menu_labels(paths), ["show1.lshow", "show2.lshow"])

    def test_same_basename_gets_folder_hint(self):
        paths = [r"C:\Users\x\AppData\LightOS\grosses_rig_2026.lshow",
                 r"C:\Users\x\Projekte\lightos-main\grosses_rig_2026.lshow"]
        labels = mw._recent_menu_labels(paths)
        self.assertNotEqual(labels[0], labels[1])
        self.assertTrue(all(l.startswith("grosses_rig_2026.lshow") for l in labels))
        self.assertIn("LightOS", labels[0])
        self.assertIn("lightos-main", labels[1])

    def test_three_way_collision_all_distinct(self):
        paths = [r"C:\x\a\s.lshow", r"C:\x\b\s.lshow", r"C:\x\c\s.lshow"]
        labels = mw._recent_menu_labels(paths)
        self.assertEqual(len(set(labels)), 3)

    def test_shortest_distinguishing_suffix(self):
        # unterscheiden sich schon im letzten Ordner -> nur EIN Ordner im Hinweis,
        # der gemeinsame Elternordner 'path' soll NICHT noetig sein
        paths = [r"C:\deep\path\alpha\s.lshow", r"C:\deep\path\beta\s.lshow"]
        labels = mw._recent_menu_labels(paths)
        self.assertIn("alpha", labels[0])
        self.assertIn("beta", labels[1])
        self.assertNotIn("path", labels[0])
        self.assertNotIn("deep", labels[1])

    def test_forward_and_back_slashes_mixed(self):
        paths = ["C:/x/a/s.lshow", r"C:\x\b\s.lshow"]
        labels = mw._recent_menu_labels(paths)
        self.assertEqual(len(set(labels)), 2)

    def test_empty_and_single(self):
        self.assertEqual(mw._recent_menu_labels([]), [])
        self.assertEqual(mw._recent_menu_labels([r"C:\a\solo.lshow"]), ["solo.lshow"])


class TestCanonPath(unittest.TestCase):
    def test_different_files_differ(self):
        self.assertNotEqual(mw._canon_path(r"C:\a\show.lshow"),
                            mw._canon_path(r"C:\b\show.lshow"))

    @unittest.skipUnless(os.name == "nt", "normcase/normpath-Folding ist Windows-spezifisch")
    def test_case_and_slash_insensitive(self):
        self.assertEqual(mw._canon_path(r"C:\Users\X\Show.lshow"),
                         mw._canon_path("c:/users/x/show.lshow"))


class TestAddRecentDedup(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "Kanon-Gleichheit unterschiedlicher Schreibweise ist Windows-spezifisch")
    def test_add_dedups_by_canon(self):
        store = [r"C:\a\show.lshow", r"C:\b\other.lshow"]
        with mock.patch.object(mw, "_load_recent_files", return_value=list(store)), \
             mock.patch.object(mw, "_save_recent_files"):
            out = mw._add_recent_file("c:/a/show.lshow")  # gleiche Datei, andere Schreibweise
        # vorne steht der neu hinzugefuegte (Original-)Pfad, und show.lshow nur EINMAL
        self.assertEqual(mw._canon_path(out[0]), mw._canon_path(r"C:\a\show.lshow"))
        canons = [mw._canon_path(p) for p in out]
        self.assertEqual(len(canons), len(set(canons)), "keine Kanon-Duplikate")
        self.assertIn(mw._canon_path(r"C:\b\other.lshow"), canons)

    def test_add_moves_existing_to_front(self):
        store = [r"C:\b\other.lshow", r"C:\a\show.lshow"]
        with mock.patch.object(mw, "_load_recent_files", return_value=list(store)), \
             mock.patch.object(mw, "_save_recent_files"):
            out = mw._add_recent_file(r"C:\a\show.lshow")
        self.assertEqual(mw._canon_path(out[0]), mw._canon_path(r"C:\a\show.lshow"))
        self.assertEqual(len([p for p in out
                              if mw._canon_path(p) == mw._canon_path(r"C:\a\show.lshow")]), 1)


if __name__ == "__main__":
    unittest.main()
