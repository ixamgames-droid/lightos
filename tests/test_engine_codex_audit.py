"""Codex-Audit-Fixes in der Engine/Preset/EFX-Schicht (ENG-03..06).

- ENG-03: Palette.apply_to_programmer schreibt Mehrkopf-Keys (attr#N) NICHT auf
  Einkopf-Fixtures (kein Bogus-attr#N, das in Snaps/Paletten weiterwandert).
- ENG-04: Palette.record_from_programmer raeumt beim selektiven Overwrite die
  alten Pro-Fixture-Werte der Ziel-fids, sodass stale Werte nicht ueberleben.
- ENG-05: gleichnamige Fixture-Gruppen werden ueber die Gruppen-ID eindeutig
  aufgeloest; der Namens-Pfad crasht nicht mehr (scalars().first()).
- ENG-06: EfxView ruft nach der Auto-Zuweisung _update_spider_mode -> die
  Spider-Controls erscheinen auch bei auto-zugewiesenen Spider-Fixtures.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.app_state import get_state
from src.core.database.fixture_db import engine as fdb_engine, ensure_builtins
from src.core.database.models import PatchedFixture, FixtureProfile, FixtureGroup
from src.core.show.show_file import reset_show
from src.core.engine.palette import Palette, PaletteType
from src.core.engine.preset_search import group_entries


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _pid(short: str) -> int:
    with Session(fdb_engine()) as s:
        return int(s.execute(select(FixtureProfile.id).where(
            FixtureProfile.short_name == short)).scalar_one())


class _StateBase(unittest.TestCase):
    def setUp(self):
        _app()
        ensure_builtins()
        reset_show()
        self.state = get_state()


class ENG03PaletteNoPhantomHeads(_StateBase):
    def setUp(self):
        super().setUp()
        # Einkopf-RGBW-PAR (color_r/g/b/w je EINMAL).
        self.state.add_fixture(PatchedFixture(
            fid=1, label="PAR", fixture_profile_id=_pid("ZQ01424"),
            mode_name="8-Kanal RGBW", universe=1, address=1, channel_count=8,
            manufacturer_name="Generic", fixture_name="Stage Light ZQ01424",
            fixture_type="par"), undoable=False)
        # Mehrkopf-Spider (color_r/g/b/w je ZWEIMAL = Kopf 0 + Kopf 1).
        self.state.add_fixture(PatchedFixture(
            fid=2, label="Spider", fixture_profile_id=_pid("SPIDER14"),
            mode_name="14-Kanal", universe=1, address=20, channel_count=14,
            manufacturer_name="U King", fixture_name="Spider 14ch",
            fixture_type="moving_head"), undoable=False)
        self.state._rebuild_render_plan()

    def test_single_head_skips_bogus_head_key(self):
        pal = Palette("p", PaletteType.COLOR,
                      fixture_values={1: {"color_r": 50, "color_r#1": 99}})
        pal.apply_to_programmer([1])
        prog = self.state.programmer.get(1, {})
        self.assertEqual(prog.get("color_r"), 50, "Kopf 0 muss geschrieben werden")
        self.assertNotIn("color_r#1", prog,
                         "Bogus-Mehrkopf-Key darf NICHT auf der Einkopf-Fixture "
                         "landen (ENG-03)")

    def test_real_multihead_still_written(self):
        pal = Palette("p", PaletteType.COLOR,
                      fixture_values={2: {"color_r": 50, "color_r#1": 99}})
        pal.apply_to_programmer([2])
        prog = self.state.programmer.get(2, {})
        self.assertEqual(prog.get("color_r"), 50)
        self.assertEqual(prog.get("color_r#1"), 99,
                         "Echter 2. Kopf muss weiterhin geschrieben werden")


class ENG04PaletteOverwriteEvictsStale(_StateBase):
    def test_cleared_target_drops_stale_values(self):
        pal = Palette("p", PaletteType.COLOR)
        pal.fixture_values = {1: {"color_r": 100}, 2: {"color_g": 200}}
        # fid 1 hat jetzt KEINE Programmer-Werte mehr (geleert).
        self.state.programmer = {}
        pal.record_from_programmer([1])   # selektiver Overwrite nur fid 1
        self.assertNotIn(1, pal.fixture_values,
                         "stale Pro-Fixture-Werte des geleerten Ziels muessen weg "
                         "sein (ENG-04)")
        self.assertEqual(pal.fixture_values.get(2), {"color_g": 200},
                         "fid ausserhalb der Auswahl bleibt unberuehrt")

    def test_changed_target_replaces_not_merges(self):
        pal = Palette("p", PaletteType.COLOR)
        pal.fixture_values = {1: {"color_r": 100}}
        self.state.programmer = {1: {"color_b": 30}}   # color_r ist weg
        pal.record_from_programmer([1])
        self.assertEqual(pal.fixture_values.get(1), {"color_b": 30})
        self.assertNotIn("color_r", pal.fixture_values.get(1, {}),
                         "alter color_r-Wert darf nicht stehen bleiben")


class ENG05DuplicateGroupNames(_StateBase):
    def _add_group(self, name, fid):
        with self.state._session() as s:
            g = FixtureGroup(name=name, cols=8, rows=8,
                             positions_json='{"0,0": %d}' % fid)
            s.add(g)
            s.commit()
            return g.id

    def test_id_lookup_resolves_duplicates_exactly(self):
        gid_a = self._add_group("Dup", 10)
        gid_b = self._add_group("Dup", 20)
        self.assertNotEqual(gid_a, gid_b)
        # ID-Ref loest EINDEUTIG auf:
        self.assertTrue(self.state.select_group_by_name((gid_b, "Dup")))
        self.assertEqual(self.state.selected_fids, [20])
        self.assertTrue(self.state.select_group_by_name((gid_a, "Dup")))
        self.assertEqual(self.state.selected_fids, [10])

    def test_name_lookup_does_not_crash_on_duplicates(self):
        self._add_group("Dup", 10)
        self._add_group("Dup", 20)
        # Namens-Pfad (VCButton) darf bei Duplikaten nicht crashen/False liefern.
        ok = self.state.select_group_by_name("Dup")
        self.assertTrue(ok, "Namens-Lookup muss eine (erste) Gruppe finden, nicht "
                            "an MultipleResultsFound scheitern (ENG-05)")
        self.assertIn(self.state.selected_fids, ([10], [20]))

    def test_group_entries_ref_carries_id(self):
        gid = self._add_group("Solo", 5)
        entries = group_entries(self.state.list_fixture_groups())
        e = next(x for x in entries if x.name == "Solo")
        self.assertEqual(e.ref, (gid, "Solo"))


# ── ENG-06: EfxView Spider-Modus nach Auto-Zuweisung ──────────────────────────
import src.core.app_state as _A
from src.ui.views.efx_view import EfxView


class _Ch:
    def __init__(self, attr, num):
        self.attribute = attr
        self.channel_number = num
        self.default_value = 0
        self.highlight_value = 255
        self.ranges = []


class _Fx:
    fixture_profile_id = 1
    mode_name = "m"
    channel_count = 4

    def __init__(self, fid, address, chans):
        self.fid = fid
        self.universe = 1
        self.address = address
        self._chans = chans


def _spider_chans():
    # Dual-Tilt-Spider: ZWEI Tilt-Kanaele, KEIN Pan -> is_dual_tilt_fixture True.
    return [_Ch("tilt", 1), _Ch("tilt", 2), _Ch("intensity", 3)]


class ENG06SpiderModeAfterAutoAssign(unittest.TestCase):
    def setUp(self):
        _app()
        self.sp1 = _Fx(1, 10, _spider_chans())
        self.sp2 = _Fx(2, 20, _spider_chans())
        self._all = [self.sp1, self.sp2]
        self._sel: list[int] = []
        self._orig_gcp = _A.get_channels_for_patched
        _A.get_channels_for_patched = lambda fx: getattr(fx, "_chans", [])
        st = _A.get_state()
        st.get_patched_fixtures = lambda: list(self._all)
        st.get_selected_fids = lambda: list(self._sel)
        self.v = EfxView()
        self._pre_ids = {f.id for f in self.v._instances}

    def tearDown(self):
        _A.get_channels_for_patched = self._orig_gcp
        try:
            for inst in list(self.v._instances):
                if inst.id not in self._pre_ids:
                    self.v._fm.remove(inst.id)
        except Exception:
            pass

    def test_add_efx_enables_spider_mode_for_autoassigned_spiders(self):
        self.v._add_efx()
        cur = self.v._current
        self.assertIsNotNone(cur)
        self.assertEqual([f.fid for f in cur.fixtures], [1, 2],
                         "beide Spider auto-zugewiesen")
        self.assertTrue(self.v._current_is_spider(),
                        "die zugewiesenen Geraete sind Dual-Tilt-Spider")
        self.assertTrue(getattr(self.v, "_spider_mode", False),
                        "ENG-06: _update_spider_mode muss nach der Auto-Zuweisung "
                        "den Spider-Modus aktiviert haben (Controls sichtbar)")


if __name__ == "__main__":
    unittest.main()
