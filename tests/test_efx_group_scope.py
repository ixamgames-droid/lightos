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

    def _mk(self, name, group=None, fids=()):
        e = self.fm.new_efx(name=name)
        e.source_group = group
        if fids:
            from src.core.engine.efx import EfxFixture
            e.fixtures = [EfxFixture(fid=f) for f in fids]
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
        self.assertIn(c.id, ids)        # ungebunden OHNE Geraete -> ueberall sichtbar
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

    def test_add_creates_unbound_draft_save_binds_to_active_group(self):
        # „Entwurf bis Speichern": „+ Neu" im Folgemodus erzeugt einen UNGEBUNDENEN
        # Live-Entwurf (committed=False, source_group=None). Erst „💾 Speichern"
        # bindet an die aktive Gruppe und committed.
        self.view._follow = True
        self.view._group_context = lambda: ("Strahler", {"Strahler"})
        # Nur die DB-/Programmer-abhaengige Geraete-Zuweisung stubben. Den echten
        # Listen-Rebuild laufen lassen, damit setCurrentRow auf die Entwurfs-Zeile
        # zeigt (sonst wuerde _select_efx ueber eine stale Zeile den frischen
        # Entwurf sofort verwerfen).
        self.view._assign_from_selection = lambda: None
        before = {f.id for f in self.fm.all()}
        self.view._add_efx()
        new = [e for e in self.view._instances if e.id not in before]
        self.assertEqual(len(new), 1)
        draft = new[0]
        # Entwurf: noch nicht gebunden, noch nicht committed.
        self.assertFalse(draft.committed)
        self.assertIsNone(draft.source_group)
        self.assertEqual(self.view._draft_id, draft.id)
        # _save_efx braucht das selektierte _current als Entwurf.
        self.view._current = draft
        self.view._save_efx()
        self.assertTrue(draft.committed)
        self.assertEqual(draft.source_group, "Strahler")
        self.assertIsNone(self.view._draft_id)

    def test_unbound_with_fixtures_filters_by_group_membership(self):
        # Backfix-2: Bestehende/ungebundene EFX (kein 💾-Bind moeglich) erscheinen
        # NUR unter der Gruppe, deren Geraete sie steuern — nicht mehr ueberall.
        a = self._mk("Alt-L", None, fids=[1, 2])
        self.view._follow = True
        self.view._group_context = lambda: ("MH-Links", {"MH-Links", "MH-Rechts"})
        self.view._active_group_fids = lambda: {1, 2}
        self.assertIn(a.id, {x.id for x in self.view._visible_instances()})   # steuert L
        self.view._active_group_fids = lambda: {3, 4}
        self.assertNotIn(a.id, {x.id for x in self.view._visible_instances()})  # nicht R

    def test_unbound_without_fixtures_shows_everywhere(self):
        # Frisch angelegte EFX (noch ohne Geraete) duerfen nicht verschwinden.
        a = self._mk("frisch", None)  # keine fixtures
        self.view._follow = True
        self.view._group_context = lambda: ("MH-Links", {"MH-Links"})
        self.view._active_group_fids = lambda: {1, 2}
        self.assertIn(a.id, {x.id for x in self.view._visible_instances()})

    def test_orphan_with_fixtures_filters_by_membership(self):
        # Verwaiste Bindung (Gruppe weg) -> ebenfalls nach Geraete-Zugehoerigkeit.
        a = self._mk("Ghost-L", "GoneGroup", fids=[1, 2])
        self.view._follow = True
        self.view._group_context = lambda: ("MH-Rechts", {"MH-Rechts"})
        self.view._active_group_fids = lambda: {3, 4}
        self.assertNotIn(a.id, {x.id for x in self.view._visible_instances()})


if __name__ == "__main__":
    unittest.main()
