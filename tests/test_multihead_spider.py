"""Mehrkopf-Spider (X-6): Profil = 2 Tilts, Farbe je Bar (VCColor head),
EFX schwenkt die zwei Bars gegenphasig.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.app_state import get_state, get_channels_for_patched
from src.core.database.fixture_db import engine as fdb_engine, ensure_builtins
from src.core.database.models import PatchedFixture, FixtureProfile
from src.core.engine.function_manager import get_function_manager
from src.core.engine.efx import EfxFixture, EfxAlgorithm
from src.core.show.show_file import reset_show


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _pid(short: str) -> int:
    with Session(fdb_engine()) as s:
        return int(s.execute(select(FixtureProfile.id).where(
            FixtureProfile.short_name == short)).scalar_one())


class MultiHeadSpiderTest(unittest.TestCase):

    def setUp(self):
        _app()
        ensure_builtins()        # Profil-Migration auf 2 Tilts sicherstellen
        reset_show()
        self.state = get_state()
        self.fm = get_function_manager()
        self.fm.stop_all()
        self.state.add_fixture(PatchedFixture(
            fid=1, label="Spider", fixture_profile_id=_pid("SPIDER14"), mode_name="14-Kanal",
            universe=1, address=1, channel_count=14, manufacturer_name="U King",
            fixture_name="Spider 14ch", fixture_type="moving_head"), undoable=False)
        self.state._rebuild_render_plan()
        u = self.state.universes.get(1)
        if u is None:
            u = self.state.output_manager.add_universe(1)
            self.state.universes[1] = u
        self.u = self.state.universes[1]

    def tearDown(self):
        self.fm.stop_all()

    def test_profile_has_two_tilts_no_pan(self):
        chans = get_channels_for_patched(
            next(f for f in self.state.get_patched_fixtures() if f.fid == 1))
        tilts = [c for c in chans if (c.attribute or "") == "tilt"]
        pans = [c for c in chans if (c.attribute or "") == "pan"]
        self.assertEqual(len(tilts), 2, "Spider sollte zwei Tilt-Kanaele haben")
        self.assertEqual(len(pans), 0, "Spider sollte keinen Pan-Kanal mehr haben")
        # color_r kommt zweimal vor (Bank 1 + Bank 2)
        self.assertEqual(sum(1 for c in chans if (c.attribute or "") == "color_r"), 2)

    def test_vccolor_head_colors_bank2_only(self):
        from src.ui.virtualconsole.vc_color import VCColor, ColorTarget
        c = VCColor("Bar R rot")
        c.target = ColorTarget.ALL
        c.head = 1
        c.color_r, c.color_g, c.color_b, c.color_w = 200, 0, 0, 0
        c.with_intensity = False
        c._apply()
        # Bank 2 (CH10) rot, Bank 1 (CH6) bleibt 0
        self.assertEqual(self.u.get_channel(10), 200)
        self.assertEqual(self.u.get_channel(6), 0)

    def test_efx_swings_bars_counter(self):
        e = self.fm.new_efx("Spider Schwenk")
        e.algorithm = EfxAlgorithm.CIRCLE
        e.fixtures = [EfxFixture(fid=1)]
        e.open_beam = True
        e.speed_hz = 1.0
        e.width = e.height = 200.0
        self.fm.start(e.id)
        # ein paar Frames rendern, dann Tilt-Kanaele lesen
        for _ in range(6):
            self.state._render_frame(1 / 44.0)
        t0 = self.u.get_channel(1)    # Tilt Bar L (Kopf 0)
        t1 = self.u.get_channel(2)    # Tilt Bar R (Kopf 1) — gegenphasig
        self.assertLessEqual(abs((t0 + t1) - 255), 2,
                             f"Bars sollten gegenphasig schwenken: {t0}+{t1}")


if __name__ == "__main__":
    unittest.main()
