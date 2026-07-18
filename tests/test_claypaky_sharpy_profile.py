"""Tests fuer das Clay-Paky-Sharpy-Builtin — Beam Moving Head, 16ch Standard-Chart.

Chart verifiziert gegen Open Fixture Library (clay-paky/sharpy) + Web-Gegencheck
(2026-07-18). Fuellt die BEAM-Luecke der Library (alle bisherigen MHs sind
Spot/Wash). Ungewoehnliche Sharpy-Reihenfolge: Farbe/Strobe/Dimmer VOR Pan/Tilt
(10-13), Control 14-16; KEIN Zoom. Safety: Shutter-Default 106 = offen (0-3 = zu),
Dimmer 0, Reset/Lampe/Funktion 0 = keine Funktion.
"""
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
        .where(FixtureProfile.short_name == "SHARPY")
    ).scalars().first()


def _mode(profile, name):
    return next(mode for mode in profile.modes if mode.name == name)


def _channels(mode):
    return sorted(mode.channels, key=lambda channel: channel.channel_number)


class SharpyProfileTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._FDB, cls._eng, cls._saved = _temp_seeded_engine()

    @classmethod
    def tearDownClass(cls):
        cls._FDB._engine = cls._saved

    def test_profile_and_mode_exist(self):
        with Session(self._eng) as s:
            profile = _load(s)
            self.assertIsNotNone(profile)
            self.assertEqual(profile.name, "Sharpy (Beam 16ch)")
            self.assertEqual(profile.fixture_type, "moving_head")
            self.assertEqual(profile.manufacturer.name, "Clay Paky")
            self.assertEqual(
                {mode.name: mode.channel_count for mode in profile.modes},
                {"16-Kanal (Standard)": 16},
            )

    def test_16ch_layout_verified_chart(self):
        with Session(self._eng) as s:
            channels = _channels(_mode(_load(s), "16-Kanal (Standard)"))
            attrs = [ch.attribute for ch in channels]
            self.assertEqual(attrs, [
                "color_wheel", "shutter", "intensity", "gobo_wheel",
                "prism", "prism_rotation", "speed", "frost", "focus",
                "pan", "pan_fine", "tilt", "tilt_fine",
                "macro", "reset", "lamp",
            ])

    def test_single_head_no_multihead_marker(self):
        # Kein Attribut doppelt -> keine attr#N-Deutung -> Single-Head (buildMovingHead,
        # nicht Spider/Bar). Genau die ENG-03/07/09-Falle, die der Skill nennt.
        with Session(self._eng) as s:
            attrs = [ch.attribute for ch in
                     _channels(_mode(_load(s), "16-Kanal (Standard)"))]
        self.assertTrue(all("#" not in a for a in attrs))
        self.assertEqual(len(attrs), len(set(attrs)),
                         "Sharpy hat ein doppeltes Attribut -> wuerde faelschlich als "
                         "Mehrkopf gedeutet")

    def test_safety_defaults(self):
        with Session(self._eng) as s:
            ch = _channels(_mode(_load(s), "16-Kanal (Standard)"))
            # Shutter (Ch2): Sharpy 0-3 = ZU -> Default 106 (offen); dunkel via Dimmer 0.
            self.assertEqual(ch[1].attribute, "shutter")
            self.assertEqual(ch[1].default_value, 106)
            # Dimmer (Ch3) aus.
            self.assertEqual(ch[2].attribute, "intensity")
            self.assertEqual(ch[2].default_value, 0)
            self.assertEqual(ch[2].highlight_value, 255)
            # Pan/Tilt (Ch10/12) Mitte; Fokus (Ch9) Mitte.
            self.assertEqual(ch[8].default_value, 128)   # focus
            self.assertEqual(ch[9].default_value, 128)   # pan
            self.assertEqual(ch[11].default_value, 128)  # tilt
            # Control-Kanaele (Ch14-16) auf 0 = keine Funktion (kein versehentlicher
            # Reset / keine Lampe-aus).
            self.assertEqual(ch[13].attribute, "macro")
            self.assertEqual(ch[13].default_value, 0)
            self.assertEqual(ch[14].attribute, "reset")
            self.assertEqual(ch[14].default_value, 0)
            self.assertEqual(ch[15].attribute, "lamp")
            self.assertEqual(ch[15].default_value, 0)

    def test_shutter_ranges_closed_at_zero(self):
        with Session(self._eng) as s:
            shutter = _channels(_mode(_load(s), "16-Kanal (Standard)"))[1]
            names = {(r.range_from, r.range_to): r.name for r in shutter.ranges}
            self.assertEqual(names[(0, 3)], "Geschlossen")
            self.assertEqual(names[(104, 107)], "Offen")

    def test_lamp_range_off_band_not_at_default(self):
        # Der Default (0) darf NICHT im "Lampe AUS"-Band (26-100) liegen.
        with Session(self._eng) as s:
            lamp = _channels(_mode(_load(s), "16-Kanal (Standard)"))[15]
            off = next(r for r in lamp.ranges if r.name == "Lampe AUS")
            self.assertFalse(off.range_from <= lamp.default_value <= off.range_to)

    def test_color_and_gobo_slots_have_kinds(self):
        with Session(self._eng) as s:
            ch = _channels(_mode(_load(s), "16-Kanal (Standard)"))
            color_kinds = [r.kind for r in sorted(ch[0].ranges, key=lambda r: r.range_from)]
            self.assertEqual(color_kinds[0], "open")           # erster Slot offen
            self.assertIn("color", color_kinds)                # Farb-Slots
            self.assertEqual(color_kinds[-1], "rotate")        # Farbrad-Rotation
            gobo_kinds = [r.kind for r in ch[3].ranges]
            self.assertIn("gobo", gobo_kinds)

    def test_reset_and_lamp_registered_in_vocab(self):
        from src.core.attr_groups import classify_attr, attr_label
        from src.ui.widgets.fixture_editor import CHANNEL_ATTRS
        self.assertIn("reset", CHANNEL_ATTRS)
        self.assertIn("lamp", CHANNEL_ATTRS)
        # Control-Kanaele: Auffang-Gruppe "Other" (kein falscher Substring-Treffer).
        self.assertEqual(classify_attr("reset"), "Other")
        self.assertEqual(classify_attr("lamp"), "Other")
        self.assertEqual(attr_label("lamp"), "Lampe")


class EnsureBuiltinsSharpyTest(unittest.TestCase):
    def setUp(self):
        self._FDB, self._eng, self._saved = _temp_seeded_engine()

    def tearDown(self):
        self._FDB._engine = self._saved

    def test_backfill_is_idempotent(self):
        from src.core.database.fixture_db import ensure_builtins
        from src.core.database.models import FixtureProfile
        with Session(self._eng) as s:
            profile = s.execute(
                select(FixtureProfile).where(FixtureProfile.short_name == "SHARPY")
            ).scalars().one()
            s.delete(profile)
            s.commit()

        ensure_builtins()
        ensure_builtins()

        with Session(self._eng) as s:
            profiles = s.execute(
                select(FixtureProfile).where(FixtureProfile.short_name == "SHARPY")
            ).scalars().all()
            self.assertEqual(len(profiles), 1)
            self.assertEqual(len(_load(s).modes), 1)


if __name__ == "__main__":
    unittest.main()
