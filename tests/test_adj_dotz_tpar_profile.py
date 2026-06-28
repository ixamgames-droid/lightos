"""Tests for the ADJ Dotz TPar System builtin profile."""
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
        .where(FixtureProfile.short_name == "DOTZTPAR")
    ).scalars().first()


def _mode(profile, name):
    return next(mode for mode in profile.modes if mode.name == name)


def _channels(mode):
    return sorted(mode.channels, key=lambda channel: channel.channel_number)


class DotzTParProfileTest(unittest.TestCase):
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
            self.assertEqual(profile.name, "Dotz TPar System")
            self.assertEqual(profile.fixture_type, "led_bar")
            self.assertEqual(profile.power_w, 144)
            self.assertEqual(profile.manufacturer.name, "ADJ")
            self.assertEqual(
                {mode.name: mode.channel_count for mode in profile.modes},
                {
                    "3-Kanal RGB": 3,
                    "5-Kanal RGB + Zusatzlicht": 5,
                    "9-Kanal Voll": 9,
                    "12-Kanal 4x RGB": 12,
                    "18-Kanal 4x RGB Voll": 18,
                },
            )

    def test_individual_head_layouts(self):
        with Session(self._eng) as s:
            profile = _load(s)
            attrs12 = [
                channel.attribute
                for channel in _channels(_mode(profile, "12-Kanal 4x RGB"))
            ]
            attrs18 = [
                channel.attribute
                for channel in _channels(_mode(profile, "18-Kanal 4x RGB Voll"))
            ]
        expected = ["color_r", "color_g", "color_b"] * 4
        self.assertEqual(attrs12, expected)
        self.assertEqual(
            attrs18,
            expected + ["color_wheel", "intensity", "shutter",
                        "raw", "raw", "raw"],
        )

    def test_macro_program_and_aux_ranges(self):
        with Session(self._eng) as s:
            channels = _channels(_mode(_load(s), "9-Kanal Voll"))
            macros = {
                (r.range_from, r.range_to): (r.name, r.kind)
                for r in channels[3].ranges
            }
            aux = {
                (r.range_from, r.range_to): (r.name, r.kind)
                for r in channels[7].ranges
            }
        self.assertEqual(
            macros[(0, 15)], ("Manuelle RGB-Steuerung", "open")
        )
        self.assertEqual(macros[(16, 23)], ("Rot", "color"))
        self.assertEqual(macros[(240, 255)], ("Sound Active", "sound"))
        self.assertEqual(aux[(0, 127)], ("Aus", "closed"))
        self.assertEqual(aux[(128, 255)], ("An", "open"))


class EnsureBuiltinsDotzTParTest(unittest.TestCase):
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
                .where(FixtureProfile.short_name == "DOTZTPAR")
            ).scalars().one()
            s.delete(profile)
            s.commit()

        ensure_builtins()
        ensure_builtins()

        with Session(self._eng) as s:
            profiles = s.execute(
                select(FixtureProfile)
                .where(FixtureProfile.short_name == "DOTZTPAR")
            ).scalars().all()
            self.assertEqual(len(profiles), 1)
            self.assertEqual(len(_load(s).modes), 5)


if __name__ == "__main__":
    unittest.main()
