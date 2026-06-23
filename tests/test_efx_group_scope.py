"""Programmer-EFX: Gruppen-Bindung (source_group) + Listen-Filterung.

Feature (analog zur Matrix, project_matrix_group_scope_2026_06_21): Im Programmer
sollen EFX-Bewegungen nur unter der Gruppe gelistet werden, fuer die sie erstellt
wurden, damit man pro Gruppe (Strahler/Moving Heads/Spider) sieht, welche EFX es
gibt. Die Bindung erfolgt per Gruppen-NAME (stabil ueber Show-Save/Load — DB-ids
aendern sich beim Neuladen).

Zwei Ebenen:
- Datenmodell (EfxInstance.source_group) — round-trippt + ist alt-kompatibel.
- View-Filterung (_visible_instances) — Bibliothek zeigt alle, Programmer filtert
  auf die aktive Gruppe (+ ungebundene/verwaiste). Der Gruppen-Kontext wird hier
  gemockt, damit der Test ohne DB/Programmer-Zustand laeuft.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.engine.efx import EfxInstance


class SourceGroupModelTest(unittest.TestCase):
    def test_default_is_none(self):
        self.assertIsNone(EfxInstance("E").source_group)

    def test_roundtrip_to_from_dict(self):
        e = EfxInstance("E")
        e.source_group = "Strahler"
        d = e.to_dict()
        self.assertEqual(d["source_group"], "Strahler")
        e2 = EfxInstance.from_dict(d)
        self.assertEqual(e2.source_group, "Strahler")

    def test_legacy_dict_without_key_is_none(self):
        # Alt-Shows ohne den Key -> ungebunden.
        e = EfxInstance.from_dict({"name": "old"})
        self.assertIsNone(e.source_group)

    def test_empty_string_normalized_to_none(self):
        e = EfxInstance.from_dict({"name": "x", "source_group": ""})
        self.assertIsNone(e.source_group)

    def test_source_group_does_not_break_motion_discriminator(self):
        # source_group darf den EFX-Diskriminator (motion/speed_hz) nicht
        # verdraengen — sonst laedt die Show als LayeredEffect (stiller Verlust).
        e = EfxInstance("E")
        e.source_group = "Moving Heads"
        d = e.to_dict()
        self.assertTrue(d.get("motion"))
        self.assertIn("speed_hz", d)


class VisibleFilterTest(unittest.TestCase):
    """_visible_instances mit gemocktem Gruppen-Kontext (kein DB-Zugriff)."""

    def setUp(self):
        from PySide6.QtWidgets import QApplication
        from src.core.engine.function_manager import get_function_manager
        from src.ui.views.efx_view import EfxView
        self.app = QApplication.instance() or QApplication([])
        self.fm = get_function_manager()
        self.fm.stop_all()
        self._pre = {f.id for f in self.fm.all()}
        # Standalone-View (kein Folgemodus) -> kein Auto-Anlegen, kein DB-Zugriff.
        self.view = EfxView()

    def tearDown(self):
        self.fm.stop_all()
        for f in list(self.fm.all()):
            if f.id not in self._pre:
                self.fm.remove(f.id)

    def _mk(self, name, group=None):
        e = self.fm.new_efx(name=name)
        e.source_group = group
        return e

    def test_standalone_shows_all(self):
        a = self._mk("A", "G1"); b = self._mk("B", "G2"); c = self._mk("C", None)
        ids = {x.id for x in self.view._visible_instances()}
        self.assertLessEqual({a.id, b.id, c.id}, ids)

    def test_follow_filters_by_group(self):
        a = self._mk("A", "G1"); b = self._mk("B", "G2"); c = self._mk("C", None)
        self.view._follow = True
        self.view._group_context = lambda: ("G1", {"G1", "G2"})
        ids = {x.id for x in self.view._visible_instances()}
        self.assertIn(a.id, ids)        # gebunden an G1 -> sichtbar
        self.assertIn(c.id, ids)        # ungebunden -> ueberall sichtbar
        self.assertNotIn(b.id, ids)     # gebunden an G2 -> ausgeblendet

    def test_orphan_binding_shows_everywhere(self):
        # Gruppe umbenannt/geloescht -> Bindung „verwaist" -> nie verlieren.
        a = self._mk("A", "GhostGroup")
        self.view._follow = True
        self.view._group_context = lambda: ("G1", {"G1"})
        ids = {x.id for x in self.view._visible_instances()}
        self.assertIn(a.id, ids)

    def test_no_active_group_shows_all(self):
        a = self._mk("A", "G1")
        self.view._follow = True
        self.view._group_context = lambda: (None, set())
        ids = {x.id for x in self.view._visible_instances()}
        self.assertIn(a.id, ids)

    def test_add_binds_new_efx_to_active_group(self):
        # „+ Neu" im Folgemodus bindet die neue EFX sofort an die aktive Gruppe.
        self.view._follow = True
        self.view._group_context = lambda: ("Strahler", {"Strahler"})
        # Die nachgelagerten Schritte brauchen Programmer-Zustand/DB -> stubben,
        # damit der Test die Bindung isoliert prueft.
        self.view._rebuild_from_state = lambda: None
        self.view._assign_from_selection = lambda: None
        before = {f.id for f in self.fm.all()}
        self.view._add_efx()
        new = [e for e in self.view._instances if e.id not in before]
        self.assertEqual(len(new), 1)
        self.assertEqual(new[0].source_group, "Strahler")


if __name__ == "__main__":
    unittest.main()
