"""Tests fuer das Ehaho-L2600-Builtin (3D-Animations-Laser, 6ch/34ch) und den
Fixture-Klassen-Audit der Builtins (jedes Builtin traegt einen echten Typ)."""
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


def _load(session, short_name="L2600LASER"):
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
        .where(FixtureProfile.short_name == short_name)
    ).scalars().first()


def _mode(profile, name):
    return next(mode for mode in profile.modes if mode.name == name)


def _channels(mode):
    return sorted(mode.channels, key=lambda channel: channel.channel_number)


# Muster-Steuerblock (Ch5-17 bzw. Ch22-34): identische Attribute fuer Gruppe
# A und B -> Mehrkopf-Konvention (2. Vorkommen = Kopf 1 = ``attr#1``).
_BLOCK_ATTRS = [
    "zoom", "gobo_rotation", "laser_x", "laser_y", "laser_zoom_x",
    "laser_zoom_y", "laser_color", "laser_color_change", "laser_dots",
    "laser_draw", "laser_draw_mode", "laser_twist", "laser_grating",
]


class EhahoL2600ProfileTest(unittest.TestCase):
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
            self.assertEqual(profile.name, "L2600 3D Animation RGB Laser")
            self.assertEqual(profile.fixture_type, "laser")
            self.assertEqual(profile.manufacturer.name, "Ehaho")
            self.assertEqual(
                {mode.name: mode.channel_count for mode in profile.modes},
                {
                    "6-Kanal (Simple DMX)": 6,
                    "34-Kanal (Professional DMX)": 34,
                },
            )

    def test_34ch_group_a_b_attribute_layout(self):
        with Session(self._eng) as s:
            attrs = [
                channel.attribute
                for channel in _channels(
                    _mode(_load(s), "34-Kanal (Professional DMX)"))
            ]
        expected = (
            ["shutter", "laser_boundary", "laser_bank", "gobo_wheel"]
            + _BLOCK_ATTRS
            + ["shutter", "laser_boundary", "raw", "gobo_wheel"]
            + _BLOCK_ATTRS
        )
        self.assertEqual(attrs, expected)
        # Mehrkopf-Erwartung: jedes Gruppen-Attribut exakt 2x (A=Kopf 0,
        # B=Kopf 1); Bank und Leerkanal existieren nur einmal.
        for attr in ["shutter", "laser_boundary", "gobo_wheel"] + _BLOCK_ATTRS:
            self.assertEqual(attrs.count(attr), 2, attr)
        self.assertEqual(attrs.count("laser_bank"), 1)
        self.assertEqual(attrs.count("raw"), 1)

    def test_34ch_safety_defaults_and_kinds(self):
        with Session(self._eng) as s:
            channels = _channels(
                _mode(_load(s), "34-Kanal (Professional DMX)"))
            ch1, ch18 = channels[0], channels[17]
            # Laser-Safety: beide Shutter-Kanaele defaulten auf AUS.
            self.assertEqual((ch1.default_value, ch1.highlight_value), (0, 255))
            self.assertEqual((ch18.default_value, ch18.highlight_value), (0, 0))
            kinds1 = {(r.range_from, r.range_to): r.kind for r in ch1.ranges}
            self.assertEqual(kinds1[(0, 0)], "closed")
            self.assertEqual(kinds1[(100, 199)], "sound")
            self.assertEqual(kinds1[(255, 255)], "open")
            # Twist: 255 = keine Verdrehung -> neutraler Default.
            twist = channels[15]
            self.assertEqual(twist.attribute, "laser_twist")
            self.assertEqual(twist.default_value, 255)
            # Musterauswahl als Gobo-Slot, Farb-Slots am Farbwechsel-Kanal.
            gobo = {r.kind for r in channels[3].ranges}
            self.assertIn("gobo", gobo)
            color_slots = {
                (r.range_from, r.range_to): (r.name, r.kind)
                for r in channels[11].ranges
            }
            self.assertEqual(color_slots[(8, 15)], ("Rot", "color"))
            self.assertEqual(color_slots[(56, 63)], ("Weiß", "color"))

    def test_6ch_simple_mode_has_own_layout(self):
        with Session(self._eng) as s:
            channels = _channels(_mode(_load(s), "6-Kanal (Simple DMX)"))
            attrs = [channel.attribute for channel in channels]
            self.assertEqual(
                attrs,
                ["shutter", "macro", "laser_bank", "color_wheel",
                 "raw", "speed"],
            )
            self.assertEqual(channels[0].default_value, 0)
            self.assertEqual(channels[0].highlight_value, 255)
            colors = [
                (r.name, r.kind)
                for r in sorted(channels[3].ranges,
                                key=lambda r: r.range_from)
            ]
        self.assertEqual(len(colors), 8)
        self.assertEqual(colors[0], ("Vollfarbe", "color"))
        self.assertTrue(all(kind == "color" for _, kind in colors))

    def test_laser_attrs_registered_in_vocabulary(self):
        from src.core.attr_groups import classify_attr
        from src.ui.widgets.fixture_editor import CHANNEL_ATTRS
        laser_attrs = ["laser_boundary", "laser_bank"] + _BLOCK_ATTRS
        for attr in laser_attrs:
            if attr in ("zoom", "gobo_rotation"):
                continue
            self.assertIn(attr, CHANNEL_ATTRS, attr)
            self.assertEqual(classify_attr(attr), "Effect", attr)
        # Regressionsschutz: der Color-Substring darf die Laser-Farbkanaele
        # NICHT in die Color-Gruppe ziehen (Feature-Dimmer wuerde sonst
        # Range-Select-Werte skalieren) — auch nicht als Mehrkopf-Key.
        self.assertEqual(classify_attr("laser_color#1"), "Effect")
        self.assertEqual(classify_attr("laser_color_change#1"), "Effect")


class EnsureBuiltinsL2600Test(unittest.TestCase):
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
                .where(FixtureProfile.short_name == "L2600LASER")
            ).scalars().one()
            s.delete(profile)
            s.commit()

        ensure_builtins()
        ensure_builtins()

        with Session(self._eng) as s:
            profiles = s.execute(
                select(FixtureProfile)
                .where(FixtureProfile.short_name == "L2600LASER")
            ).scalars().all()
            self.assertEqual(len(profiles), 1)
            self.assertEqual(len(_load(s).modes), 2)


class BuiltinTypeAuditTest(unittest.TestCase):
    """Fixture-Klassen-Audit 2026-07-02: jedes Builtin traegt eine echte
    Klasse (nie 'other'), Schluessel-Geraete sind explizit festgenagelt."""

    @classmethod
    def setUpClass(cls):
        cls._FDB, cls._eng, cls._saved = _temp_seeded_engine()

    @classmethod
    def tearDownClass(cls):
        cls._FDB._engine = cls._saved

    def test_all_builtins_have_real_class(self):
        from src.core.database.models import FixtureProfile
        from src.ui.widgets.fixture_editor import FIXTURE_TYPES
        with Session(self._eng) as s:
            rows = s.execute(
                select(FixtureProfile.short_name, FixtureProfile.fixture_type)
                .where(FixtureProfile.source == "builtin")
            ).all()
        self.assertTrue(rows)
        for short, ftype in rows:
            self.assertIn(ftype, FIXTURE_TYPES, short)
            self.assertNotEqual(ftype, "other", short)

    def test_key_builtins_expected_classes(self):
        from src.core.database.models import FixtureProfile
        expected = {
            "ZQ01424": "par", "KLEINCONTI": "par", "EUROGROSS": "par",
            "FPQWH12X": "par",
            "ZQ02001": "moving_head", "SPIDER14": "moving_head",
            "CONTIMH": "moving_head",
            "DOTZTPAR": "led_bar",
            "PARTYLASER": "laser", "L2600LASER": "laser", "PANGFB4": "laser",
        }
        with Session(self._eng) as s:
            rows = dict(s.execute(
                select(FixtureProfile.short_name, FixtureProfile.fixture_type)
                .where(FixtureProfile.short_name.in_(expected))
            ).all())
        self.assertEqual(rows, expected)


if __name__ == "__main__":
    unittest.main()
