"""X-3: Generische Moving-Head-Spots (MH8/MH16) tragen Farb-/Gobo-Rad-Slots
mit ``kind``, damit die Schnellwahl (PresetTile) Kacheln ableiten kann. Eine
aeltere DB ohne diese Ranges wird von ensure_builtins() in-place nachgeruestet.
"""
import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

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


def _load(eng, short):
    from src.core.database.models import FixtureProfile, FixtureMode, FixtureChannel
    with Session(eng) as s:
        prof = s.execute(
            select(FixtureProfile)
            .options(selectinload(FixtureProfile.modes)
                     .selectinload(FixtureMode.channels)
                     .selectinload(FixtureChannel.ranges))
            .where(FixtureProfile.short_name == short)
        ).scalars().first()
        # In ein einfaches Dict materialisieren, damit es ausserhalb der Session lebt
        out = {}
        for m in prof.modes:
            for c in m.channels:
                out[(m.name, c.attribute)] = sorted(
                    (r.range_from, r.range_to, r.kind) for r in c.ranges)
        return prof.id, out


class GenericMHWheelSlotsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._FDB, cls._eng, cls._saved = _temp_seeded_engine()

    @classmethod
    def tearDownClass(cls):
        cls._FDB._engine = cls._saved

    def test_mh8_color_wheel_slots(self):
        _, slots = _load(self._eng, "MH8")
        rr = slots[("8-Kanal", "color_wheel")]
        self.assertTrue(rr)
        kinds = {k for _, _, k in rr}
        self.assertIn("color", kinds)
        self.assertIn("open", kinds)
        self.assertIn("rotate", kinds)

    def test_mh8_gobo_wheel_slots(self):
        _, slots = _load(self._eng, "MH8")
        kinds = {k for _, _, k in slots[("8-Kanal", "gobo_wheel")]}
        self.assertIn("gobo", kinds)
        self.assertIn("open", kinds)

    def test_mh16_wheels_have_slots(self):
        _, slots = _load(self._eng, "MH16")
        self.assertTrue(slots[("16-Kanal", "color_wheel")])
        self.assertTrue(slots[("16-Kanal", "gobo_wheel")])


class EnsureWheelRangesUpgradeTest(unittest.TestCase):
    """ensure_builtins() ruestet Wheel-Slots in einer alten DB nach (Profil-ID stabil)."""

    def setUp(self):
        self._FDB, self._eng, self._saved = _temp_seeded_engine()

    def tearDown(self):
        self._FDB._engine = self._saved

    def test_old_db_without_ranges_gets_upgraded(self):
        from src.core.database.fixture_db import ensure_builtins
        from src.core.database.models import (FixtureProfile, FixtureMode,
                                              FixtureChannel)
        # Alt-Zustand: Wheel-Ranges von MH8 entfernen
        with Session(self._eng) as s:
            prof = s.execute(
                select(FixtureProfile)
                .options(selectinload(FixtureProfile.modes)
                         .selectinload(FixtureMode.channels)
                         .selectinload(FixtureChannel.ranges))
                .where(FixtureProfile.short_name == "MH8")
            ).scalars().first()
            old_id = prof.id
            for m in prof.modes:
                for c in m.channels:
                    if c.attribute in ("color_wheel", "gobo_wheel"):
                        c.ranges.clear()
            s.commit()

        ensure_builtins()

        new_id, slots = _load(self._eng, "MH8")
        self.assertEqual(new_id, old_id, "Profil-ID muss stabil bleiben")
        self.assertTrue(slots[("8-Kanal", "color_wheel")],
                        "color_wheel-Slots wurden nachgeruestet")
        self.assertTrue(slots[("8-Kanal", "gobo_wheel")])

    def test_idempotent_when_already_present(self):
        from src.core.database.fixture_db import ensure_builtins
        before_id, before = _load(self._eng, "MH8")
        ensure_builtins()
        after_id, after = _load(self._eng, "MH8")
        self.assertEqual(before_id, after_id)
        self.assertEqual(before, after, "korrekte Slots nicht unnoetig neu aufbauen")


if __name__ == "__main__":
    unittest.main()
