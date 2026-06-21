"""VCButton zeigt das Gobo-Icon, wenn der Button einen Gobo setzt (Snap oder Szene).

Nur echte Gobo-Ranges (kind gobo/shake/rotate) bekommen ein Icon; 'Kein Gobo'
(open) und Nicht-Gobo-Buttons bleiben ohne.
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
from src.core.engine.function_manager import get_function_manager
from src.core.show.show_file import reset_show


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _pid(short: str) -> int:
    with Session(fdb_engine()) as s:
        return int(s.execute(select(FixtureProfile.id).where(
            FixtureProfile.short_name == short)).scalar_one())


class GoboIconTest(unittest.TestCase):

    def setUp(self):
        _app()
        reset_show()
        self.state = get_state()
        self.fm = get_function_manager()
        self.fm.stop_all()
        self.state.add_fixture(PatchedFixture(
            fid=1, label="MH", fixture_profile_id=_pid("ZQ02001"), mode_name="11-Kanal",
            universe=1, address=1, channel_count=11, manufacturer_name="U King",
            fixture_name="ZQ02001 Mini Moving Head", fixture_type="moving_head"), undoable=False)
        self.state._rebuild_render_plan()

    def tearDown(self):
        self.fm.stop_all()

    def test_scene_gobo_button_has_icon(self):
        from src.ui.virtualconsole.vc_button import VCButton, ButtonAction
        sc = self.fm.new_scene("Gobo Ring")
        sc.set_value(1, 6, 8)   # gobo_wheel (rel. Kanal 6) = 8 -> "Gobo 1 (Ring, 3 Spalten)"
        b = VCButton("Gobo")
        b.action = ButtonAction.FUNCTION_TOGGLE
        b.function_id = sc.id
        pm = b._gobo_icon()
        self.assertIsNotNone(pm)
        self.assertFalse(pm.isNull())

    def test_non_gobo_button_no_icon(self):
        from src.ui.virtualconsole.vc_button import VCButton, ButtonAction
        sc = self.fm.new_scene("Nur Dimmer")
        sc.set_value(1, 8, 255)   # Master Dimmer, kein Gobo
        b = VCButton("Dim")
        b.action = ButtonAction.FUNCTION_TOGGLE
        b.function_id = sc.id
        self.assertIsNone(b._gobo_icon())

    def test_open_gobo_no_icon(self):
        from src.ui.virtualconsole.vc_button import VCButton, ButtonAction
        sc = self.fm.new_scene("Kein Gobo")
        sc.set_value(1, 6, 0)     # 0-7 = "Kein Gobo" (open) -> kein Icon
        b = VCButton("x")
        b.action = ButtonAction.FUNCTION_TOGGLE
        b.function_id = sc.id
        self.assertIsNone(b._gobo_icon())

    def test_cache_recomputes_on_rebind(self):
        from src.ui.virtualconsole.vc_button import VCButton, ButtonAction
        sc = self.fm.new_scene("Gobo Zebra")
        sc.set_value(1, 6, 56)    # 56-63 = "Gobo 7 (Zebra)"
        b = VCButton("g")
        b.action = ButtonAction.FUNCTION_TOGGLE
        b.function_id = sc.id
        self.assertIsNotNone(b._gobo_icon())
        b.function_id = None      # Bindung weg -> Cache neu, kein Icon
        self.assertIsNone(b._gobo_icon())


if __name__ == "__main__":
    unittest.main()
