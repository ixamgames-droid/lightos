"""Programmer-EFX: „Entwurf bis Speichern" (committed-Flag).

Feature (Nutzer-Wunsch): „+ Neu" erzeugt einen EFX-ENTWURF, der live laeuft
(im FunctionManager tickt + Vorschau), aber NICHT serialisiert und NICHT an die
aktive Gruppe gebunden wird. Erst „💾 Speichern" committed ihn (serialisierbar +
Gruppen-Bindung im Folgemodus). Ungespeicherte Entwuerfe werden beim
Wegwechseln/Loeschen/erneutem „+ Neu" verworfen.

Mechanik: EfxInstance.committed (Default True = back-compat, geladene EFX sind
committed). Das Flag wird BEWUSST NICHT serialisiert -> from_dict erbt den
__init__-Default True. FunctionManager.to_dict filtert committed==False heraus.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.engine.efx import EfxInstance


class CommittedModelTest(unittest.TestCase):
    def test_new_efx_default_committed(self):
        # Frisch konstruiert -> committed (Default True).
        self.assertTrue(EfxInstance("X").committed)

    def test_from_dict_committed_back_compat(self):
        # Von Disk geladen -> immer committed (Flag nicht serialisiert, erbt
        # __init__-Default).
        self.assertTrue(EfxInstance.from_dict({"name": "x"}).committed)

    def test_committed_not_serialized(self):
        # to_dict traegt das Flag bewusst NICHT (Default-Mechanik robuster).
        self.assertNotIn("committed", EfxInstance("X").to_dict())


class ToDictFilterTest(unittest.TestCase):
    """FunctionManager.to_dict ueberspringt nur Entwuerfe (committed==False)."""

    def setUp(self):
        from src.core.engine.function_manager import get_function_manager
        self.fm = get_function_manager()
        self.fm.stop_all()
        self._pre = {f.id for f in self.fm.all()}

    def tearDown(self):
        self.fm.stop_all()
        for f in list(self.fm.all()):
            if f.id not in self._pre:
                self.fm.remove(f.id)

    def test_to_dict_filters_only_drafts(self):
        keep = self.fm.new_efx(name="committed")    # committed=True (Default)
        draft = self.fm.new_efx(name="draft")
        draft.committed = False
        scene = self.fm.new_scene(name="Szene")      # kein committed-Attribut
        ids = {f["id"] for f in self.fm.to_dict()["functions"]}
        self.assertIn(keep.id, ids)
        self.assertIn(scene.id, ids)                 # andere Typen unveraendert
        self.assertNotIn(draft.id, ids)              # Entwurf raus


class DraftViewTest(unittest.TestCase):
    """EfxView-Entwurfs-Lebenszyklus (headless, kein GUI-Mainloop)."""

    def setUp(self):
        from PySide6.QtWidgets import QApplication
        from src.core.engine.function_manager import get_function_manager
        from src.ui.views.efx_view import EfxView
        self.app = QApplication.instance() or QApplication([])
        self.fm = get_function_manager()
        self.fm.stop_all()
        self._pre = {f.id for f in self.fm.all()}
        self.view = EfxView()

    def tearDown(self):
        self.fm.stop_all()
        for f in list(self.fm.all()):
            if f.id not in self._pre:
                self.fm.remove(f.id)

    def test_draft_not_serialized_until_save(self):
        self.view._add_efx()
        did = self.view._draft_id
        self.assertIsNotNone(did)
        draft = self.fm.get(did)
        self.assertFalse(draft.committed)
        ids = {f["id"] for f in self.fm.to_dict()["functions"]}
        self.assertNotIn(did, ids)                   # Entwurf nicht in der Show
        # Speichern -> committed -> serialisierbar.
        self.view._current = draft
        self.view._save_efx()
        self.assertTrue(draft.committed)
        self.assertIsNone(self.view._draft_id)
        ids = {f["id"] for f in self.fm.to_dict()["functions"]}
        self.assertIn(did, ids)

    def test_draft_discarded_on_select_away(self):
        # Bestehender (committed) EFX + neuer Entwurf; Auswahl WEG -> Entwurf weg.
        other = self.fm.new_efx(name="bestehend")
        self.view._rebuild_from_state()
        self.view._add_efx()
        did = self.view._draft_id
        self.assertIsNotNone(self.fm.get(did))
        # Auf den anderen EFX wechseln -> Entwurf wird verworfen.
        vis = self.view._visible_instances()
        row = next(i for i, e in enumerate(vis) if e.id == other.id)
        self.view._select_efx(row)
        self.assertIsNone(self.fm.get(did))
        self.assertIsNone(self.view._draft_id)

    def test_second_new_discards_previous(self):
        self.view._add_efx()
        first = self.view._draft_id
        self.view._add_efx()
        second = self.view._draft_id
        self.assertNotEqual(first, second)
        self.assertIsNone(self.fm.get(first))        # erster Entwurf weg
        # Genau EIN Entwurf — nur die in DIESEM Test erzeugten zaehlen (der globale
        # FM kann aus anderen Tests fluechtige Reste tragen).
        drafts = [f for f in self.fm.all()
                  if isinstance(f, EfxInstance) and not f.committed
                  and f.id not in self._pre]
        self.assertEqual(len(drafts), 1)
        self.assertEqual(drafts[0].id, second)

    def test_delete_discards_draft(self):
        self.view._add_efx()
        did = self.view._draft_id
        # Der Entwurf ist selektiert -> Loeschen verwirft ihn (Anzahl sinkt).
        before = len(self.fm.all())
        self.view._delete_efx()
        self.assertIsNone(self.fm.get(did))
        self.assertIsNone(self.view._draft_id)
        self.assertEqual(len(self.fm.all()), before - 1)

    def test_save_binds_group_in_follow(self):
        self.view._follow = True
        self.view._group_context = lambda: ("G1", {"G1"})
        # Nur die DB-/Programmer-abhaengige Geraete-Zuweisung stubben; den echten
        # Listen-Rebuild laufen lassen (sonst zeigt setCurrentRow auf eine stale
        # Zeile und _select_efx verwirft den frischen Entwurf).
        self.view._assign_from_selection = lambda: None
        self.view._add_efx()
        draft = self.fm.get(self.view._draft_id)
        self.assertIsNone(draft.source_group)        # Entwurf NICHT gebunden
        self.view._current = draft
        self.view._save_efx()
        self.assertEqual(draft.source_group, "G1")
        self.assertTrue(draft.committed)
        self.assertIsNone(self.view._draft_id)

    def test_discard_keeps_committed(self):
        # Nach dem Speichern darf _discard_draft den nun committed EFX NICHT
        # entfernen (committed-Gate).
        self.view._add_efx()
        did = self.view._draft_id
        self.view._current = self.fm.get(did)
        self.view._save_efx()
        self.view._discard_draft()                   # No-Op (kein Entwurf offen)
        self.assertIsNotNone(self.fm.get(did))


if __name__ == "__main__":
    unittest.main()
