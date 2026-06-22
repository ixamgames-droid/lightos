"""Spider-spezifische Bedienung in Position- und FX-Tab (Doppelbar, zwei Tilts).

Deckt ab:
  - SpiderPositionTool schreibt die zwei Bars getrennt (tilt Kopf 0 / tilt#1
    Kopf 1) und nur auf echte Spider.
  - SpiderBarsView Winkel-Mapping.
  - EfxView-Follow nimmt Spider (Tilt ohne Pan) als Geraet auf und schaltet in
    den Spider-Modus; Moving Heads bleiben im Normal-Modus.
  - Spider-Bewegungsmuster setzen eine reine Tilt-Figur (width=0/rotation=0) und
    die Engine schwenkt die zwei Bars gegenphasig.
  - Programmer._selection_is_spider erkennt reine Spider-Auswahl.
"""
import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.app_state import get_state, is_spider_fixture
from src.core.database.fixture_db import engine as fdb_engine, ensure_builtins
from src.core.database.models import PatchedFixture, FixtureProfile
from src.core.engine.function_manager import get_function_manager
from src.core.engine.efx import EfxAlgorithm
from src.core.show.show_file import reset_show


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _pid(short: str) -> int:
    with Session(fdb_engine()) as s:
        return int(s.execute(select(FixtureProfile.id).where(
            FixtureProfile.short_name == short)).scalar_one())


class _SpiderBase(unittest.TestCase):
    def setUp(self):
        _app()
        ensure_builtins()
        reset_show()
        self.state = get_state()
        self.fm = get_function_manager()
        self.fm.stop_all()

    def tearDown(self):
        self.fm.stop_all()

    def _ensure_uni(self):
        u = self.state.universes.get(1)
        if u is None:
            u = self.state.output_manager.add_universe(1)
            self.state.universes[1] = u
        return self.state.universes[1]

    def _add_spider(self, fid=1, addr=1):
        self.state.add_fixture(PatchedFixture(
            fid=fid, label="Spider", fixture_profile_id=_pid("SPIDER14"),
            mode_name="14-Kanal", universe=1, address=addr, channel_count=14,
            manufacturer_name="U King", fixture_name="Spider 14ch",
            fixture_type="moving_head"), undoable=False)
        self.state._rebuild_render_plan()
        return self._ensure_uni()

    def _add_mh(self, fid=2, addr=40):
        self.state.add_fixture(PatchedFixture(
            fid=fid, label="MH", fixture_profile_id=_pid("ZQ02001"),
            mode_name="11-Kanal", universe=1, address=addr, channel_count=11,
            manufacturer_name="U King", fixture_name="ZQ02001",
            fixture_type="moving_head"), undoable=False)
        self.state._rebuild_render_plan()
        return self._ensure_uni()

    def _fx(self, fid):
        return next(f for f in self.state.get_patched_fixtures() if f.fid == fid)


class SpiderBarsViewTest(unittest.TestCase):
    def test_swing_mapping(self):
        from src.ui.widgets.spider_bars_view import tilt_to_swing_deg
        self.assertAlmostEqual(tilt_to_swing_deg(128), 0.0, delta=1.0)
        self.assertLess(tilt_to_swing_deg(0), 0.0)
        self.assertGreater(tilt_to_swing_deg(255), 0.0)


class DualTiltDetectionTest(unittest.TestCase):
    """is_dual_tilt_fixture/tilt_head_count über gefälschte Kanal-Layouts —
    breiter als is_spider_fixture (greift auch ohne zwei Farb-Banks)."""

    def setUp(self):
        import src.core.app_state as A
        self.A = A
        self._orig = A.get_channels_for_patched

    def tearDown(self):
        self.A.get_channels_for_patched = self._orig

    def _patch(self, *attrs):
        self.A.get_channels_for_patched = \
            lambda fx, _a=attrs: [SimpleNamespace(attribute=a) for a in _a]

    def test_mini_spider_without_color(self):
        # 2 Tilts, KEINE Farbe (z. B. Domin8R/Mini-Spider 7ch) → Doppeltilter,
        # aber KEIN is_spider_fixture (zu wenig Farb-Banks).
        self._patch("tilt", "tilt", "intensity", "shutter")
        self.assertTrue(self.A.is_dual_tilt_fixture(object()))
        self.assertFalse(self.A.is_spider_fixture(object()))
        self.assertEqual(self.A.tilt_head_count(object()), 2)

    def test_eight_tilt_spider(self):
        self._patch(*(["tilt"] * 8 + ["intensity"]))
        self.assertTrue(self.A.is_dual_tilt_fixture(object()))
        self.assertEqual(self.A.tilt_head_count(object()), 8)

    def test_single_moving_head_not_dual(self):
        self._patch("pan", "tilt", "tilt_fine", "intensity")
        self.assertFalse(self.A.is_dual_tilt_fixture(object()))
        self.assertEqual(self.A.tilt_head_count(object()), 1)

    def test_twin_head_with_pan_not_dual(self):
        # Zwei Köpfe MIT je Pan+Tilt (Twin Moving Head) → hat Pan → NICHT Spider.
        self._patch("pan", "tilt", "pan", "tilt", "intensity")
        self.assertFalse(self.A.is_dual_tilt_fixture(object()))


class SpiderPositionToolTest(_SpiderBase):
    def test_writes_both_tilt_heads(self):
        self._add_spider()
        self.state.set_selected_fids([1])
        from src.ui.widgets.spider_position_tool import SpiderPositionTool
        t = SpiderPositionTool(head_count=2)
        t.set_live(False)
        t.set_tilts([40, 210])
        t._apply_to_selection()
        self.assertEqual(self.state.get_programmer_value(1, "tilt", head=0), 40)
        self.assertEqual(self.state.get_programmer_value(1, "tilt", head=1), 210)

    def test_scissor_mode_mirrors_right(self):
        from src.ui.widgets.spider_position_tool import SpiderPositionTool
        t = SpiderPositionTool(head_count=2)
        t._chk_scissor.setChecked(True)
        t._sliders[0].setValue(60)
        self.assertEqual(t.tilts(), [60, 195])

    def test_link_mode_couples(self):
        from src.ui.widgets.spider_position_tool import SpiderPositionTool
        t = SpiderPositionTool(head_count=2)
        t._chk_link.setChecked(True)
        t._sliders[0].setValue(70)
        self.assertEqual(t.tilts(), [70, 70])

    def test_skips_non_spider_fixtures(self):
        self._add_spider()
        self._add_mh()
        self.state.set_selected_fids([1, 2])
        from src.ui.widgets.spider_position_tool import SpiderPositionTool
        t = SpiderPositionTool(head_count=2)
        t.set_live(False)
        t.set_tilts([100, 150])
        t._apply_to_selection()
        # Spider bekommt beide Bars …
        self.assertEqual(self.state.get_programmer_value(1, "tilt", head=0), 100)
        self.assertEqual(self.state.get_programmer_value(1, "tilt", head=1), 150)
        # … der Moving Head bekommt gar nichts (kein versehentliches tilt#1).
        self.assertIsNone(self.state.get_programmer_value(2, "tilt", head=0))
        self.assertIsNone(self.state.get_programmer_value(2, "tilt", head=1))


class ProgrammerSpiderDetectionTest(_SpiderBase):
    def test_selection_is_spider(self):
        from src.ui.views.programmer_view import ProgrammerView
        self._add_spider()
        self._add_mh()
        is_spider = ProgrammerView._selection_is_spider
        self.assertTrue(is_spider(None, [self._fx(1)]))           # nur Spider
        self.assertFalse(is_spider(None, [self._fx(2)]))          # nur MH
        self.assertFalse(is_spider(None, [self._fx(1), self._fx(2)]))  # gemischt
        self.assertFalse(is_spider(None, []))                     # leer


class SpiderEfxModeTest(_SpiderBase):
    def _view(self):
        from src.ui.views.efx_view import EfxView
        return EfxView(follow_selection=True)

    def test_follow_includes_spider_and_enables_mode(self):
        self._add_spider()
        v = self._view()
        self.state.set_selected_fids([1])     # feuert _assign_from_selection
        self.assertIsNotNone(v._current)
        self.assertEqual([f.fid for f in v._current.fixtures], [1])
        self.assertTrue(v._spider_mode)
        v.deleteLater()

    def test_moving_head_keeps_normal_mode(self):
        self._add_mh()
        v = self._view()
        self.state.set_selected_fids([2])
        self.assertEqual([f.fid for f in v._current.fixtures], [2])
        self.assertFalse(v._spider_mode)
        v.deleteLater()

    def test_pattern_sets_tilt_only_figure(self):
        self._add_spider()
        v = self._view()
        self.state.set_selected_fids([1])
        v._apply_spider_pattern("wippe")
        e = v._current
        self.assertEqual(e.algorithm, EfxAlgorithm.CIRCLE)
        self.assertEqual(e.width, 0)
        self.assertEqual(e.rotation, 0)
        self.assertEqual(e.height, 200)
        v.deleteLater()

    def test_pattern_renders_counter_phase(self):
        u = self._add_spider()
        v = self._view()
        self.state.set_selected_fids([1])
        v._apply_spider_pattern("wippe")
        e = v._current
        e.open_beam = True
        e.speed_hz = 1.0
        self.fm.start(e.id)
        for _ in range(8):
            self.state._render_frame(1 / 44.0)
        t0 = u.get_channel(1)    # Tilt Bar L (Kopf 0)
        t1 = u.get_channel(2)    # Tilt Bar R (Kopf 1)
        self.assertLessEqual(abs((t0 + t1) - 255), 2,
                             f"Bars sollten gegenphasig schwenken: {t0}+{t1}")
        v.deleteLater()


if __name__ == "__main__":
    unittest.main()
