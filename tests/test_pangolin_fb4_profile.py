"""Tests fuer das Pangolin-FB4-Builtin (Profi-Laser-Interface im DMX-Modus,
16ch "FB3"-Profil + 39ch — offizielle Charts aus dem Pangolin-Wiki, LAS-08)."""
import tempfile
import unittest

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload


def _temp_seeded_engine():
    from src.core.database import fixture_db as FDB
    from src.core.database.fixture_db import get_engine, _seed
    saved = FDB._engine
    eng = get_engine(tempfile.mktemp(suffix=".db"))
    with Session(eng) as s:
        _seed(s)
        s.commit()
    FDB._engine = eng
    return FDB, eng, saved


def _load(session):
    from src.core.database.models import (
        FixtureChannel, FixtureMode, FixtureProfile,
    )
    return session.execute(
        select(FixtureProfile)
        .options(
            selectinload(FixtureProfile.manufacturer),
            selectinload(FixtureProfile.modes)
            .selectinload(FixtureMode.channels)
            .selectinload(FixtureChannel.ranges),
        )
        .where(FixtureProfile.short_name == "PANGFB4")
    ).scalars().first()


def _mode(profile, name):
    return next(mode for mode in profile.modes if mode.name == name)


def _channels(mode):
    return sorted(mode.channels, key=lambda channel: channel.channel_number)


class PangolinFb4ProfileTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._FDB, cls._eng, cls._saved = _temp_seeded_engine()

    @classmethod
    def tearDownClass(cls):
        cls._FDB._engine = cls._saved

    def test_profile_and_modes_exist(self):
        with Session(self._eng) as s:
            profile = _load(s)
            self.assertIsNotNone(profile)
            self.assertEqual(profile.name, "FB4 (DMX-Modus)")
            self.assertEqual(profile.fixture_type, "laser")
            self.assertEqual(profile.manufacturer.name, "Pangolin")
            self.assertEqual(
                {mode.name: mode.channel_count for mode in profile.modes},
                {"16-Kanal (FB3-Profil)": 16, "39-Kanal": 39},
            )

    def test_16ch_layout(self):
        with Session(self._eng) as s:
            channels = _channels(_mode(_load(s), "16-Kanal (FB3-Profil)"))
            attrs = [ch.attribute for ch in channels]
            self.assertEqual(attrs, [
                "shutter", "laser_bank", "gobo_wheel", "speed", "intensity",
                "zoom", "laser_zoom_x", "laser_zoom_y", "gobo_rotation",
                "laser_x", "laser_y", "laser_draw", "laser_scan_rate",
                "macro", "laser_color_change", "raw",
            ])
            # Safety: Blackout-Default auf Ch1 und Dimmer 0.
            kinds1 = {(r.range_from, r.range_to): r.kind
                      for r in channels[0].ranges}
            self.assertEqual(channels[0].default_value, 0)
            self.assertEqual(kinds1[(0, 32)], "closed")
            self.assertEqual(kinds1[(225, 255)], "open")
            self.assertEqual(channels[4].default_value, 0)      # Dimmer
            self.assertEqual(channels[9].default_value, 128)    # Pos X Mitte
            self.assertEqual(channels[10].default_value, 128)   # Pos Y Mitte

    def test_39ch_multihead_layout_and_safety(self):
        with Session(self._eng) as s:
            channels = _channels(_mode(_load(s), "39-Kanal"))
            attrs = [ch.attribute for ch in channels]
        self.assertEqual(len(attrs), 39)
        # Setup-/Playback-Duplikate als Mehrkopf (Kopf 0 = Setup, 1 = Playback);
        # gobo_rotation hat zusaetzlich die kontinuierliche Z-Rotation (Kopf 2).
        expected_counts = {
            "shutter": 1, "intensity": 2, "laser_zoom_x": 2, "laser_zoom_y": 2,
            "laser_x": 2, "laser_y": 2, "gobo_rotation": 3, "laser_bank": 1,
            "gobo_wheel": 1, "speed": 1, "zoom": 1, "laser_scan_rate": 1,
            "color_r": 1, "color_g": 1, "color_b": 1, "laser_color": 1,
            "laser_draw": 2, "strobe": 1, "macro": 1, "raw": 12,
        }
        for attr, count in expected_counts.items():
            self.assertEqual(attrs.count(attr), count, attr)
        self.assertEqual(sum(expected_counts.values()), 39)

        with Session(self._eng) as s:
            channels = _channels(_mode(_load(s), "39-Kanal"))
            ch1 = channels[0]
            self.assertEqual(ch1.default_value, 0)          # Blackout/Safe
            self.assertEqual(ch1.highlight_value, 251)      # Playback
            kinds1 = {(r.range_from, r.range_to): r.kind for r in ch1.ranges}
            self.assertEqual(kinds1[(0, 239)], "closed")
            self.assertEqual(kinds1[(251, 255)], "open")
            # Kontinuierliche Z-Rotation defaultet auf Stillstand (128 = 0 RPM).
            zrot = channels[25]
            self.assertEqual(zrot.attribute, "gobo_rotation")
            self.assertEqual(zrot.default_value, 128)
            # Playback-Dimmer (Ch17) aus, Setup-Limit (Ch2) offen.
            self.assertEqual(channels[16].default_value, 0)
            self.assertEqual(channels[1].default_value, 255)
            # Strobe-Kanal traegt den strobe-kind.
            strobe_kinds = {r.kind for r in channels[38].ranges}
            self.assertIn("strobe", strobe_kinds)

    def test_scan_rate_attr_registered(self):
        from src.core.attr_groups import classify_attr
        from src.ui.widgets.fixture_editor import CHANNEL_ATTRS
        self.assertIn("laser_scan_rate", CHANNEL_ATTRS)
        self.assertEqual(classify_attr("laser_scan_rate"), "Effect")


class EnsureBuiltinsFb4Test(unittest.TestCase):
    def setUp(self):
        self._FDB, self._eng, self._saved = _temp_seeded_engine()

    def tearDown(self):
        self._FDB._engine = self._saved

    def test_backfill_is_idempotent(self):
        from src.core.database.fixture_db import ensure_builtins
        from src.core.database.models import FixtureProfile
        with Session(self._eng) as s:
            profile = s.execute(
                select(FixtureProfile)
                .where(FixtureProfile.short_name == "PANGFB4")
            ).scalars().one()
            s.delete(profile)
            s.commit()

        ensure_builtins()
        ensure_builtins()

        with Session(self._eng) as s:
            profiles = s.execute(
                select(FixtureProfile)
                .where(FixtureProfile.short_name == "PANGFB4")
            ).scalars().all()
            self.assertEqual(len(profiles), 1)
            self.assertEqual(len(_load(s).modes), 2)


if __name__ == "__main__":
    unittest.main()
