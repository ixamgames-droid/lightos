"""Programmer-Matrix: Gruppen-Bindung (source_group) + Listen-Filterung.

Feature: Im Programmer sollen Matrix-Effekte nur unter der Gruppe gelistet werden,
fuer die sie erstellt/gespeichert wurden, damit man pro Gruppe sieht, welche
Matrix-Programme es gibt. Die Bindung erfolgt per Gruppen-NAME (stabil ueber
Show-Save/Load — DB-ids aendern sich beim Neuladen).

Zwei Ebenen:
- Datenmodell (RgbMatrixInstance.source_group) — round-trippt + ist alt-kompatibel.
- View-Filterung (_visible_instances) — Bibliothek zeigt alle, Programmer filtert
  auf die aktive Gruppe (+ ungebundene/verwaiste). Der Gruppen-Kontext wird hier
  gemockt, damit der Test ohne DB/Programmer-Zustand laeuft.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.engine.rgb_matrix import RgbMatrixInstance


class SourceGroupModelTest(unittest.TestCase):
    def test_default_is_none(self):
        self.assertIsNone(RgbMatrixInstance("M").source_group)

    def test_roundtrip_to_from_dict(self):
        m = RgbMatrixInstance("M")
        m.source_group = "Strahler"
        d = m.to_dict()
        self.assertEqual(d["source_group"], "Strahler")
        m2 = RgbMatrixInstance.from_dict(d)
        self.assertEqual(m2.source_group, "Strahler")

    def test_legacy_dict_without_key_is_none(self):
        # Alt-Shows ohne den Key -> ungebunden.
        m = RgbMatrixInstance.from_dict({"name": "old"})
        self.assertIsNone(m.source_group)

    def test_empty_string_normalized_to_none(self):
        m = RgbMatrixInstance.from_dict({"name": "x", "source_group": ""})
        self.assertIsNone(m.source_group)


class VisibleFilterTest(unittest.TestCase):
    """_visible_instances mit gemocktem Gruppen-Kontext (kein DB-Zugriff)."""

    def setUp(self):
        from PySide6.QtWidgets import QApplication
        from src.core.engine.function_manager import get_function_manager
        from src.ui.views.rgb_matrix_view import RgbMatrixView
        self.app = QApplication.instance() or QApplication([])
        self.fm = get_function_manager()
        self.fm.stop_all()
        self._pre = {f.id for f in self.fm.all()}
        # Standalone-View (kein Folgemodus) -> kein Auto-Anlegen, kein DB-Zugriff.
        self.view = RgbMatrixView()

    def tearDown(self):
        self.fm.stop_all()
        for f in list(self.fm.all()):
            if f.id not in self._pre:
                self.fm.remove(f.id)

    def _mk(self, name, group=None):
        m = self.fm.new_rgb_matrix(name=name)
        m.source_group = group
        return m

    def test_standalone_shows_all(self):
        a = self._mk("A", "G1"); b = self._mk("B", "G2"); c = self._mk("C", None)
        ids = {x.id for x in self.view._visible_instances()}
        self.assertLessEqual({a.id, b.id, c.id}, ids)

    def test_follow_filters_by_group(self):
        a = self._mk("A", "G1"); b = self._mk("B", "G2"); c = self._mk("C", None)
        self.view._follow_selection = True
        self.view._group_context = lambda: ("G1", {"G1", "G2"})
        ids = {x.id for x in self.view._visible_instances()}
        self.assertIn(a.id, ids)        # gebunden an G1 -> sichtbar
        self.assertIn(c.id, ids)        # ungebunden -> ueberall sichtbar
        self.assertNotIn(b.id, ids)     # gebunden an G2 -> ausgeblendet

    def test_orphan_binding_shows_everywhere(self):
        # Gruppe umbenannt/geloescht -> Bindung „verwaist" -> nie verlieren.
        a = self._mk("A", "GhostGroup")
        self.view._follow_selection = True
        self.view._group_context = lambda: ("G1", {"G1"})
        ids = {x.id for x in self.view._visible_instances()}
        self.assertIn(a.id, ids)

    def test_no_active_group_shows_all(self):
        a = self._mk("A", "G1")
        self.view._follow_selection = True
        self.view._group_context = lambda: (None, set())
        ids = {x.id for x in self.view._visible_instances()}
        self.assertIn(a.id, ids)


if __name__ == "__main__":
    unittest.main()
