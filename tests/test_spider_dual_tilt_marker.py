"""Expliziter Spider/Dual-Tilt-Marker (``PatchedFixture.spider_dual_tilt``).

Hintergrund: Aus QLC+ importierte Butterfly-/Derby-Spider (U-King „Speider" u.ä.)
haben ihre zwei Tilt-Bar-Motoren oft faelschlich als ``pan``/``tilt`` gemappt
statt ``tilt``/``tilt``. Dadurch greift die automatische Spider-Erkennung
(``is_dual_tilt_fixture`` = >=2 Tilt + 0 Pan) NICHT — Position-Tab zeigt das
nutzlose XY-Pad, EFX-Tab zeigt Pan/Tilt-Figuren (Kreis …). Eine sichere
Auto-Erkennung ist unmoeglich (echte Pan+Tilt-Mover sehen strukturell identisch
aus), daher ein bewusst gesetzter Pro-Geraet-Marker.

Gedeckt:
  - ``_as_dual_tilt_channels`` deutet pan->tilt / pan_fine->tilt_fine um, laesst
    den Rest unberuehrt, bewahrt die Reihenfolge und mutiert das Original NICHT.
  - ``get_channels_for_patched`` wendet die Umdeutung NUR bei gesetztem Flag an
    (Cache-Isolation: dasselbe Profil ungeflaggt bleibt Pan+Tilt).
  - ``is_dual_tilt_fixture``/``tilt_head_count`` kippen mit dem Flag.
  - ``update_fixture(spider_dual_tilt=True)`` persistiert + invalidiert den Cache.
  - Position-Tab (``_selection_is_spider``) und EFX-Tab (Spider-Modus) schalten um.
  - Per-Kopf-Schreiben trifft BEIDE Motoren (tilt Kopf 0 = CH1, tilt#1 Kopf 1 = CH2).
  - Persistenz-Roundtrip ueber die Show-Datei.
"""
import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from sqlalchemy import select
from sqlalchemy.orm import Session

import src.core.app_state as A
from src.core.app_state import (get_state, is_dual_tilt_fixture, is_spider_fixture,
                                 tilt_head_count, get_channels_for_patched,
                                 clear_channel_cache)
from src.core.database.fixture_db import (engine as fdb_engine, create_user_profile)
from src.core.database.models import (PatchedFixture, FixtureProfile, FixtureMode,
                                       FixtureChannel)
from src.core.engine.function_manager import get_function_manager
from src.core.show.show_file import reset_show


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


# Fehl-gemapptes Spider-Layout: CH1 Pan-Motor, CH2 Tilt-Motor, dann Speed/Dimmer/
# Shutter, zwei RGBW-Baenke, Reset — exakt die Struktur des U-King „Speider 14ch".
_MISMAPPED_SPIDER_ATTRS = [
    ("Moter 1", "pan"), ("Motor 2", "tilt"), ("Speed", "speed"),
    ("Dimmer", "intensity"), ("Shutter", "shutter"),
    ("Red", "color_r"), ("Green", "color_g"), ("Blue", "color_b"), ("White", "color_w"),
    ("Red 2", "color_r"), ("Green 2", "color_g"), ("Blue 2", "color_b"), ("White 2", "color_w"),
    ("Neu Start", "raw"),
]


def _make_mismapped_spider_profile(*, source="user", name="TEST Speider DualTilt") -> int:
    payload = {
        "manufacturer": "TEST-DualTilt",
        "name": name,
        "fixture_type": "moving_head",
        "source": source,
        "modes": [{
            "name": "14ch",
            "channel_count": len(_MISMAPPED_SPIDER_ATTRS),
            "channels": [
                {"channel_number": i, "name": n, "attribute": a}
                for i, (n, a) in enumerate(_MISMAPPED_SPIDER_ATTRS, 1)
            ],
        }],
    }
    return create_user_profile(payload)


def _delete_profile(pid: int):
    with Session(fdb_engine()) as s:
        prof = s.get(FixtureProfile, pid)
        if prof is not None:
            s.delete(prof)        # cascade -> Modi/Kanaele/Ranges
            s.commit()
    clear_channel_cache()


class AsDualTiltTransformTest(unittest.TestCase):
    """Reiner Transform — ohne DB/Qt."""

    def _chans(self, *attrs):
        return [SimpleNamespace(attribute=a, channel_number=i, name=a)
                for i, a in enumerate(attrs, 1)]

    def test_relabels_pan_and_panfine(self):
        src = self._chans("pan", "pan_fine", "tilt", "tilt_fine", "intensity", "color_r")
        out = A._as_dual_tilt_channels(src)
        self.assertEqual([c.attribute for c in out],
                         ["tilt", "tilt_fine", "tilt", "tilt_fine", "intensity", "color_r"])

    def test_preserves_order_and_passthrough_fields(self):
        src = self._chans("pan", "tilt", "color_r")
        out = A._as_dual_tilt_channels(src)
        self.assertEqual([c.channel_number for c in out], [1, 2, 3])
        # Nicht-Bewegungskanaele werden unveraendert (dasselbe Objekt) durchgereicht.
        self.assertIs(out[2], src[2])
        # Durchgereichte Felder (name) bleiben am umgedeuteten Kanal erreichbar.
        self.assertEqual(out[0].name, "pan")

    def test_does_not_mutate_original(self):
        src = self._chans("pan", "tilt")
        A._as_dual_tilt_channels(src)
        self.assertEqual(src[0].attribute, "pan")   # Original unangetastet

    def test_no_pan_is_noop(self):
        src = self._chans("tilt", "tilt", "intensity")
        out = A._as_dual_tilt_channels(src)
        self.assertEqual([c.attribute for c in out], ["tilt", "tilt", "intensity"])


class _DbBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _app()
        cls.pid = _make_mismapped_spider_profile()
        cls.qlc_pid = _make_mismapped_spider_profile(
            source="qlcplus", name="TEST QLC Speider DualTilt")

    @classmethod
    def tearDownClass(cls):
        _delete_profile(cls.pid)
        _delete_profile(cls.qlc_pid)

    def setUp(self):
        reset_show()
        self.state = get_state()
        self.fm = get_function_manager()
        self.fm.stop_all()
        clear_channel_cache()

    def tearDown(self):
        self.fm.stop_all()

    def _add(self, fid, *, dual: bool, addr=1, pid=None):
        profile_id = self.pid if pid is None else pid
        self.state.add_fixture(PatchedFixture(
            fid=fid, label="Speider", fixture_profile_id=profile_id,
            mode_name="14ch", universe=1, address=addr, channel_count=14,
            manufacturer_name="TEST-DualTilt", fixture_name="TEST Speider DualTilt",
            fixture_type="moving_head", spider_dual_tilt=dual), undoable=False)
        self.state._rebuild_render_plan()
        return next(f for f in self.state.get_patched_fixtures() if f.fid == fid)


class ChannelRemapIntegrationTest(_DbBase):
    def test_flagged_relabels_to_dual_tilt(self):
        fx = self._add(1, dual=True)
        attrs = [c.attribute for c in get_channels_for_patched(fx)]
        self.assertEqual(attrs[:2], ["tilt", "tilt"])      # CH1 Pan -> Tilt
        self.assertNotIn("pan", attrs)
        self.assertTrue(is_dual_tilt_fixture(fx))
        self.assertEqual(tilt_head_count(fx), 2)
        self.assertTrue(is_spider_fixture(fx))             # 2 Farb-Banken

    def test_unflagged_same_profile_unchanged(self):
        # Cache-Isolation: dasselbe Profil OHNE Flag bleibt Pan+Tilt.
        plain = self._add(2, dual=False, addr=40)
        attrs = [c.attribute for c in get_channels_for_patched(plain)]
        self.assertEqual(attrs[:2], ["pan", "tilt"])
        self.assertFalse(is_dual_tilt_fixture(plain))
        self.assertEqual(tilt_head_count(plain), 1)

    def test_unflagged_qlc_spider_is_detected_automatically(self):
        auto = self._add(4, dual=False, addr=120, pid=self.qlc_pid)
        attrs = [c.attribute for c in get_channels_for_patched(auto)]
        self.assertEqual(attrs[:2], ["tilt", "tilt"])
        self.assertNotIn("pan", attrs)
        self.assertTrue(is_dual_tilt_fixture(auto))
        self.assertEqual(tilt_head_count(auto), 2)

    def test_both_flagged_and_unflagged_coexist(self):
        dual = self._add(1, dual=True)
        plain = self._add(2, dual=False, addr=40)
        self.assertTrue(is_dual_tilt_fixture(dual))
        self.assertFalse(is_dual_tilt_fixture(plain))

    def test_toggle_via_update_fixture(self):
        self._add(3, dual=False, addr=80)
        fx = next(f for f in self.state.get_patched_fixtures() if f.fid == 3)
        self.assertFalse(is_dual_tilt_fixture(fx))
        ok = self.state.update_fixture(3, spider_dual_tilt=True, undoable=False)
        self.assertTrue(ok)
        fx = next(f for f in self.state.get_patched_fixtures() if f.fid == 3)
        self.assertTrue(is_dual_tilt_fixture(fx))          # Cache invalidiert + persistiert


class ProgrammerAndEfxUiTest(_DbBase):
    def test_selection_is_spider_for_flagged(self):
        from src.ui.views.programmer_view import ProgrammerView
        dual = self._add(1, dual=True)
        plain = self._add(2, dual=False, addr=40)
        is_spider = ProgrammerView._selection_is_spider
        self.assertTrue(is_spider(None, [dual]))
        self.assertFalse(is_spider(None, [plain]))

    def test_writes_both_motors(self):
        from src.ui.widgets.spider_position_tool import SpiderPositionTool
        self._add(1, dual=True)
        self.state.set_selected_fids([1])
        t = SpiderPositionTool(head_count=2)
        t.set_live(False)
        t.set_tilts([40, 210])
        t._apply_to_selection()
        # Kopf 0 -> CH1 (ehem. Pan), Kopf 1 -> CH2 (Tilt) — beide Motoren getrennt.
        self.assertEqual(self.state.get_programmer_value(1, "tilt", head=0), 40)
        self.assertEqual(self.state.get_programmer_value(1, "tilt", head=1), 210)

    def test_efx_follow_enables_spider_mode(self):
        from src.ui.views.efx_view import EfxView
        self._add(1, dual=True)
        v = EfxView(follow_selection=True)
        v._add_efx()
        # Seit dem Wurzel-Fix (#53) wirkt das Follow-Assignment nur bei sichtbarer
        # Editor-Seite (sonst wuerde der Hintergrund die Geraete der gespielten EFX
        # leeren). Im Test daher sichtbar machen.
        v.show()
        self.state.set_selected_fids([1])
        self.assertIsNotNone(v._current)
        self.assertEqual([f.fid for f in v._current.fixtures], [1])
        self.assertTrue(v._spider_mode)
        v.deleteLater()


class PersistenceRoundtripTest(_DbBase):
    def test_show_file_roundtrip_preserves_flag(self):
        from src.core.show import show_file
        self._add(1, dual=True)
        d = show_file._fixture_to_dict(next(
            f for f in self.state.get_patched_fixtures() if f.fid == 1))
        self.assertTrue(d["spider_dual_tilt"])
        restored = show_file._patched_fixture_from_data(d, 1)
        self.assertTrue(bool(restored.spider_dual_tilt))

    def test_default_is_false(self):
        plain = self._add(2, dual=False, addr=40)
        from src.core.show import show_file
        d = show_file._fixture_to_dict(plain)
        self.assertFalse(d["spider_dual_tilt"])


if __name__ == "__main__":
    unittest.main()
