"""„Geräte-Solo" 2026-06-15.

David: Effekte aus einer anderen Bank blieben aktiv und konkurrierten mit dem
gerade gewählten Effekt. Neue VC-Pad-Option „Andere Effekte auf denselben Geräten
stoppen" — beim Start ersetzt der Effekt nur die OTHER laufenden Effekte, die
DIESELBEN Strahler benutzen (auch bankübergreifend); Effekte auf anderen Geräten
laufen weiter.

Engine-Basis: FunctionManager.affected_fids() (alle Typen, rekursiv) +
stop_others_sharing_fixtures().
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.core.engine.function_manager import FunctionManager
from src.core.engine.efx import EfxFixture
from src.ui.virtualconsole.vc_button import VCButton, ButtonAction
from src.core.app_state import get_state

_app = QApplication.instance() or QApplication([])


class AffectedFidsTest(unittest.TestCase):
    def setUp(self):
        self.fm = FunctionManager()

    def test_efx_fixtures(self):
        e = self.fm.new_efx("efx")
        e.fixtures = [EfxFixture(fid=1), EfxFixture(fid=2)]
        self.assertEqual(self.fm.affected_fids(e.id), {1, 2})

    def test_carousel_and_layered_fixture_ids(self):
        c = self.fm.new_carousel("car")
        c.fixture_ids = [3, 4]
        self.assertEqual(self.fm.affected_fids(c.id), {3, 4})
        le = self.fm.new_layered_effect("lay")
        le.fixture_ids = [5]
        self.assertEqual(self.fm.affected_fids(le.id), {5})

    def test_matrix_fixture_grid_skips_gaps(self):
        m = self.fm.new_rgb_matrix("mtx")
        m.fixture_grid = [7, None, 8, None]
        self.assertEqual(self.fm.affected_fids(m.id), {7, 8})

    def test_scene_values(self):
        s = self.fm.new_scene("scn")
        s.set_value(9, 1, 255)
        s.set_value(10, 1, 128)
        self.assertEqual(self.fm.affected_fids(s.id), {9, 10})

    def test_chaser_resolves_steps_recursively(self):
        s1 = self.fm.new_scene("s1"); s1.set_value(11, 1, 255)
        s2 = self.fm.new_scene("s2"); s2.set_value(12, 1, 255)
        ch = self.fm.new_chaser("ch")
        ch.add_step(s1.id)
        ch.add_step(s2.id)
        self.assertEqual(self.fm.affected_fids(ch.id), {11, 12})

    def test_collection_resolves_members(self):
        e = self.fm.new_efx("e"); e.fixtures = [EfxFixture(fid=20)]
        s = self.fm.new_scene("s"); s.set_value(21, 1, 255)
        col = self.fm.new_collection("col")
        col.function_ids = [e.id, s.id]
        self.assertEqual(self.fm.affected_fids(col.id), {20, 21})

    def test_cycle_is_guarded(self):
        # Collection, die sich (indirekt) selbst referenziert -> kein Stack-Overflow.
        col = self.fm.new_collection("c")
        col.function_ids = [col.id]
        self.assertEqual(self.fm.affected_fids(col.id), set())

    def test_unknown_id_empty(self):
        self.assertEqual(self.fm.affected_fids(99999), set())


class StopOthersSharingFixturesTest(unittest.TestCase):
    def setUp(self):
        self.fm = FunctionManager()
        self.a = self.fm.new_efx("A"); self.a.fixtures = [EfxFixture(fid=1), EfxFixture(fid=2)]
        self.b = self.fm.new_efx("B"); self.b.fixtures = [EfxFixture(fid=2), EfxFixture(fid=3)]
        self.c = self.fm.new_efx("C"); self.c.fixtures = [EfxFixture(fid=8), EfxFixture(fid=9)]

    def test_stops_only_overlapping(self):
        self.fm.start(self.b.id)   # teilt fid 2 mit A
        self.fm.start(self.c.id)   # disjunkt zu A
        stopped = self.fm.stop_others_sharing_fixtures(self.a.id)
        self.assertEqual(stopped, 1)
        self.assertFalse(self.fm.is_running(self.b.id))   # ueberlappt -> gestoppt
        self.assertTrue(self.fm.is_running(self.c.id))    # disjunkt -> laeuft weiter

    def test_does_not_stop_self(self):
        self.fm.start(self.a.id)
        self.fm.stop_others_sharing_fixtures(self.a.id)
        self.assertTrue(self.fm.is_running(self.a.id))

    def test_no_fixtures_stops_nothing(self):
        empty = self.fm.new_efx("leer")
        self.fm.start(self.b.id)
        self.assertEqual(self.fm.stop_others_sharing_fixtures(empty.id), 0)
        self.assertTrue(self.fm.is_running(self.b.id))

    def test_group_members_do_not_stop_each_other(self):
        external = self.fm.new_efx("External")
        external.fixtures = [EfxFixture(fid=3)]
        for fn in (self.a, self.b, self.c, external):
            self.fm.start(fn.id)

        stopped = self.fm.stop_others_sharing_fixture_group([self.a.id, self.b.id])

        self.assertEqual(stopped, 1)
        self.assertTrue(self.fm.is_running(self.a.id))
        self.assertTrue(self.fm.is_running(self.b.id))
        self.assertTrue(self.fm.is_running(self.c.id))
        self.assertFalse(self.fm.is_running(external.id))


class ButtonSoloFixturesTest(unittest.TestCase):
    """End-to-end über den echten VC-Button + den globalen FunctionManager."""
    def setUp(self):
        self.fm = get_state().function_manager
        self.a = self.fm.new_efx("A"); self.a.fixtures = [EfxFixture(fid=101), EfxFixture(fid=102)]
        self.b = self.fm.new_efx("B"); self.b.fixtures = [EfxFixture(fid=102), EfxFixture(fid=103)]
        self.d = self.fm.new_efx("D"); self.d.fixtures = [EfxFixture(fid=201)]

    def tearDown(self):
        for f in (self.a, self.b, self.d):
            self.fm.stop(f.id); self.fm.remove(f.id)

    def _btn(self, fid, solo):
        b = VCButton("Pad")
        b.action = ButtonAction.FUNCTION_TOGGLE
        b.function_id = fid
        b.solo_fixtures = solo
        return b

    def test_solo_button_replaces_overlapping(self):
        self.fm.start(self.a.id)             # laeuft auf 101,102
        self.fm.start(self.d.id)             # laeuft auf 201 (disjunkt)
        self._btn(self.b.id, solo=True)._trigger(True)   # B teilt 102 mit A
        self.assertTrue(self.fm.is_running(self.b.id))
        self.assertFalse(self.fm.is_running(self.a.id))  # abgeloest
        self.assertTrue(self.fm.is_running(self.d.id))   # bleibt

    def test_without_solo_both_run(self):
        self.fm.start(self.a.id)
        self._btn(self.b.id, solo=False)._trigger(True)
        self.assertTrue(self.fm.is_running(self.a.id))
        self.assertTrue(self.fm.is_running(self.b.id))

    def test_roundtrip(self):
        b = self._btn(self.b.id, solo=True)
        b2 = VCButton("x"); b2.apply_dict(b.to_dict())
        self.assertTrue(b2.solo_fixtures)


if __name__ == "__main__":
    unittest.main()
