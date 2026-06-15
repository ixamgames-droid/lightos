"""SnapLibrary.move_folder — Ordner UNTER einen anderen Ordner verschieben
(Re-Parenting), inkl. Unterordner + enthaltener Snaps. Deckt die fehlende
„Ordner in Ordner ziehen"-Faehigkeit ab."""
import unittest

from src.core.engine.snap_library import SnapLibrary


class MoveFolderTest(unittest.TestCase):
    def setUp(self):
        self.lib = SnapLibrary()
        self.lib.clear()                       # evtl. migrierte Alt-Snaps ignorieren

    def _add(self, name, folder):
        return self.lib.add_snap(name, folder, {1: {"intensity": 255}})

    def test_move_folder_into_another(self):
        self.lib.add_folder("A")
        self.lib.add_folder("B")
        s = self._add("snap1", "A")
        new = self.lib.move_folder("A", "B")
        self.assertEqual(new, "B/A")
        self.assertIn("B/A", self.lib.folders())
        self.assertNotIn("A", self.lib._folders)
        self.assertEqual(s.folder, "B/A")       # Snap mitgezogen

    def test_subfolders_and_snaps_follow(self):
        self.lib.add_folder("A/Sub")
        s1 = self._add("s1", "A")
        s2 = self._add("s2", "A/Sub")
        new = self.lib.move_folder("A", "B")
        self.assertEqual(new, "B/A")
        self.assertEqual(s1.folder, "B/A")
        self.assertEqual(s2.folder, "B/A/Sub")
        self.assertIn("B/A/Sub", self.lib.folders())

    def test_move_to_root(self):
        self.lib.add_folder("B/A")
        s = self._add("s", "B/A")
        new = self.lib.move_folder("B/A", "")
        self.assertEqual(new, "A")
        self.assertEqual(s.folder, "A")

    def test_into_self_rejected(self):
        self.lib.add_folder("A")
        self.assertIsNone(self.lib.move_folder("A", "A"))

    def test_into_own_descendant_rejected(self):
        self.lib.add_folder("A/Sub")
        self.assertIsNone(self.lib.move_folder("A", "A/Sub"))

    def test_noop_same_parent(self):
        self.lib.add_folder("B/A")
        # „A" liegt schon unter „B" → erneutes Verschieben unter „B" ist No-op.
        self.assertEqual(self.lib.move_folder("B/A", "B"), "B/A")

    def test_merge_into_existing(self):
        # Zielordner B/A existiert bereits mit Inhalt → Verschmelzung.
        self.lib.add_folder("B/A")
        existing = self._add("keep", "B/A")
        moved = self._add("moved", "A")
        new = self.lib.move_folder("A", "B")
        self.assertEqual(new, "B/A")
        self.assertEqual(existing.folder, "B/A")
        self.assertEqual(moved.folder, "B/A")


if __name__ == "__main__":
    unittest.main()
