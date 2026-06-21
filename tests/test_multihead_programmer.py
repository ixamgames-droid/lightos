"""Mehrkopf (X-6): Programmer-Werte pro Kopf (head) auf wiederholten Attributen.

Der Spider (SPIDER14) hat color_r/g/b/w DOPPELT (Bank 1 = CH6-9, Bank 2 = CH10-13).
head=0 schreibt Bank 1 ("color_r"), head=1 schreibt Bank 2 ("color_r#1"). Ohne
separaten head=1-Wert spiegelt Bank 2 Bank 1 (byte-genau wie bisher).
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.app_state import get_state
from src.core.database.fixture_db import engine as fdb_engine
from src.core.database.models import PatchedFixture, FixtureProfile
from src.core.show.show_file import reset_show


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _pid(short: str) -> int:
    with Session(fdb_engine()) as s:
        return int(s.execute(select(FixtureProfile.id).where(
            FixtureProfile.short_name == short)).scalar_one())


class MultiHeadProgrammerTest(unittest.TestCase):

    def setUp(self):
        _app()
        reset_show()
        self.state = get_state()
        self.state.add_fixture(PatchedFixture(
            fid=1, label="Spider", fixture_profile_id=_pid("SPIDER14"), mode_name="14-Kanal",
            universe=1, address=1, channel_count=14, manufacturer_name="U King",
            fixture_name="Spider 14ch", fixture_type="moving_head"), undoable=False)
        self.state.add_fixture(PatchedFixture(
            fid=2, label="PAR", fixture_profile_id=_pid("ZQ01424"), mode_name="8-Kanal RGBW",
            universe=1, address=20, channel_count=8, manufacturer_name="Generic",
            fixture_name="Stage Light ZQ01424", fixture_type="par"), undoable=False)
        self.state._rebuild_render_plan()
        u = self.state.universes.get(1)
        if u is None:
            u = self.state.output_manager.add_universe(1)
            self.state.universes[1] = u
        self.u = self.state.universes[1]

    def test_per_bar_color_separate(self):
        # Bank 1 (CH6) = 200, Bank 2 (CH10) = 50 -> getrennte Farben pro Bar.
        self.state.set_programmer_value(1, "color_r", 200, head=0)
        self.state.set_programmer_value(1, "color_r", 50, head=1)
        self.assertEqual(self.u.get_channel(6), 200)
        self.assertEqual(self.u.get_channel(10), 50)
        self.assertEqual(self.state.get_programmer_value(1, "color_r", head=1), 50)
        self.assertEqual(self.state.get_programmer_value(1, "color_r", head=0), 200)

    def test_head0_mirrors_to_bank2_when_no_override(self):
        # Nur head=0 gesetzt -> Bank 2 spiegelt Bank 1 (byte-genau wie frueher).
        self.state.set_programmer_value(1, "color_r", 180, head=0)
        self.assertEqual(self.u.get_channel(6), 180)
        self.assertEqual(self.u.get_channel(10), 180)

    def test_single_head_fixture_unchanged(self):
        # PAR hat color_r nur EINMAL (CH2 -> abs 21) -> head=0 wie immer.
        self.state.set_programmer_value(2, "color_r", 123, head=0)
        # CH-Attribut color_r des PAR finden
        from src.core.app_state import get_channels_for_patched
        fx = next(f for f in self.state.get_patched_fixtures() if f.fid == 2)
        ch = next(c for c in get_channels_for_patched(fx) if (c.attribute or "") == "color_r")
        self.assertEqual(self.u.get_channel(20 + ch.channel_number - 1), 123)


if __name__ == "__main__":
    unittest.main()
