"""UI-03: Fixture-Kopieren mit Offset.

plan_offset_copies ist reine Logik (kein Qt/DB) und wird direkt getestet; der
echte UI-Pfad PatchView._copy_with_offset wird ueber ein Fake-self mit gepatchtem
Dialog durchlaufen (wie test_patch_undo), damit ein versehentliches undoable=False
oder eine falsche Adress-/fid-Vergabe auffaellt.
"""
import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.app_state import get_state
from src.core.database.fixture_db import engine as fdb_engine, ensure_builtins
from src.core.database.models import PatchedFixture, FixtureProfile
from src.core.engine.function_manager import get_function_manager
from src.core.show.show_file import reset_show
from src.core.undo import get_undo_stack
from src.ui.views import patch_view as pv


class PlanOffsetCopiesTest(unittest.TestCase):
    def test_basic_spacing_and_contiguous_fids(self):
        src = SimpleNamespace(address=1, universe=1, channel_count=4)
        specs, skipped = pv.plan_offset_copies(src, count=3, offset=4, base_fid=10)
        self.assertEqual(skipped, 0)
        self.assertEqual([s["address"] for s in specs], [5, 9, 13])
        self.assertEqual([s["fid"] for s in specs], [10, 11, 12])
        self.assertTrue(all(s["universe"] == 1 for s in specs))

    def test_skips_universe_overflow_and_keeps_fids_contiguous(self):
        src = SimpleNamespace(address=400, universe=2, channel_count=4)
        # 450(ok), 500(ok), 550(550+3>512 -> skip), 600(skip)
        specs, skipped = pv.plan_offset_copies(src, count=4, offset=50, base_fid=100)
        self.assertEqual([s["address"] for s in specs], [450, 500])
        self.assertEqual([s["fid"] for s in specs], [100, 101])  # luckenlos trotz skip
        self.assertEqual(skipped, 2)
        self.assertTrue(all(s["universe"] == 2 for s in specs))

    def test_copy_fixture_carries_over_all_fields(self):
        src = SimpleNamespace(
            label="Wash", fixture_profile_id=7, mode_name="8ch", channel_count=8,
            manufacturer_name="ACME", fixture_name="W8", fixture_type="moving_head",
            invert_pan=True, invert_tilt=False, swap_pan_tilt=True, spider_mirrored=False,
            spider_dual_tilt=True,
            pan_range_deg=540, tilt_range_deg=180, pan_zero_dmx=128, tilt_zero_dmx=120)
        c = pv._copy_fixture(src, fid=42, universe=3, address=100)
        self.assertEqual((c.fid, c.universe, c.address), (42, 3, 100))
        self.assertEqual((c.fixture_profile_id, c.mode_name, c.channel_count),
                         (7, "8ch", 8))
        self.assertEqual((c.fixture_type, c.invert_pan, c.swap_pan_tilt,
                          c.tilt_range_deg, c.tilt_zero_dmx, c.spider_dual_tilt),
                         ("moving_head", True, True, 180, 120, True))


class CopyWithOffsetUITest(unittest.TestCase):
    def setUp(self):
        QApplication.instance() or QApplication([])
        ensure_builtins()
        reset_show()
        self.state = get_state()
        self.fm = get_function_manager()
        self.fm.stop_all()
        self.undo = get_undo_stack()
        self.undo.clear()

    def tearDown(self):
        self.fm.stop_all()
        self.undo.clear()

    def _any_pid(self) -> int:
        with Session(fdb_engine()) as s:
            return int(s.execute(select(FixtureProfile.id)).scalars().first())

    def _add(self, fid: int, addr: int, ch: int = 4):
        self.state.add_fixture(PatchedFixture(
            fid=fid, label=f"F{fid}", fixture_profile_id=self._any_pid(),
            mode_name="", universe=1, address=addr, channel_count=ch,
            manufacturer_name="T", fixture_name="T", fixture_type="dimmer"),
            undoable=False)

    def _fids(self):
        return {f.fid for f in self.state.get_patched_fixtures()}

    def _fake_self(self, fid_for_row0: int):
        return SimpleNamespace(
            _table=SimpleNamespace(
                selectedIndexes=lambda: [SimpleNamespace(row=lambda: 0)]),
            _fid_at_row=lambda r: fid_for_row0,
            _state=self.state,
        )

    def test_creates_spaced_undoable_copies(self):
        self._add(1, addr=1, ch=4)
        fake_dlg = SimpleNamespace(exec=lambda: 1, count=lambda: 2, offset=lambda: 4)
        with mock.patch.object(pv, "CopyWithOffsetDialog", return_value=fake_dlg):
            pv.PatchView._copy_with_offset(self._fake_self(1))
        addrs = sorted(f.address for f in self.state.get_patched_fixtures())
        self.assertEqual(addrs, [1, 5, 9], "Original + 2 Kopien bei Offset 4")
        self.assertEqual(len(self._fids()), 3)
        self.assertTrue(self.undo.can_undo(), "Kopien muessen undoable sein")

    def test_cancel_creates_nothing(self):
        self._add(1, addr=1)
        fake_dlg = SimpleNamespace(exec=lambda: 0, count=lambda: 5, offset=lambda: 4)
        with mock.patch.object(pv, "CopyWithOffsetDialog", return_value=fake_dlg):
            pv.PatchView._copy_with_offset(self._fake_self(1))
        self.assertEqual(self._fids(), {1}, "Abbruch -> keine Kopie")
        self.assertFalse(self.undo.can_undo())

    def test_no_selection_is_noop(self):
        self._add(1, addr=1)
        fake = SimpleNamespace(
            _table=SimpleNamespace(selectedIndexes=lambda: []),
            _fid_at_row=lambda r: None, _state=self.state)
        with mock.patch.object(pv.QMessageBox, "information", return_value=None):
            pv.PatchView._copy_with_offset(fake)
        self.assertEqual(self._fids(), {1})


if __name__ == "__main__":
    unittest.main()
