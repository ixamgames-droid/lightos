"""Tests fuer das Robe-MegaPointe-Builtin (FM-15) — Beam/Spot/Wash-Hybrid, 39ch.

Chart DOPPELT verifiziert: offizielles Robe-DMX-Protokoll v1.5 + Blizzard-Lighting-
Fixture-Library (.fix, Brand Robe, 2017) — kanal-fuer-kanal deckungsgleich
(QLC+ UND OFL enthalten die MegaPointe NICHT, nur die aeltere Pointe). Standard
16-bit 39-Kanal-Modus. Farbe ueber echtes CMY (cmy_c/m/y) + Farbrad. KEINE Iris.
Single-Head trotz vieler wiederholter 'raw'-Kanaele (0 color_r, 1 pan / 1 tilt).
Safety: Shutter-Default 32 = offen (0-31 zu), Dimmer 0, Power/Special 0 = keine
Funktion (kein versehentlicher Reset / keine Lampe-aus).
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
        .where(FixtureProfile.short_name == "MEGAPNT")
    ).scalars().first()


def _channels(mode):
    return sorted(mode.channels, key=lambda channel: channel.channel_number)


# Verifizierte 39ch-Attribut-Sequenz (Mode 1, Robe-Protokoll v1.5). 'raw' =
# Spezial-/Fine-Kanal ohne kanonisches Attribut (virt. Farbrad, Effektrad, Pattern,
# Beam-Shaper, Hotspot, 2. Prisma, Fine-Kanaele).
EXPECTED_ATTRS = [
    "pan", "pan_fine", "tilt", "tilt_fine", "speed", "macro",
    "cmy_c", "cmy_m", "cmy_y", "color_wheel", "raw", "raw",
    "effect_speed", "raw", "raw", "animation", "raw", "raw",
    "gobo_wheel", "gobo_wheel2", "gobo_rotation", "raw",
    "prism", "prism_rotation", "raw", "raw", "raw", "raw", "raw", "raw",
    "frost", "zoom", "raw", "focus", "raw", "raw",
    "shutter", "intensity", "raw",
]
MODE = "39-Kanal (Standard 16-bit)"


class MegaPointeProfileTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._FDB, cls._eng, cls._saved = _temp_seeded_engine()

    @classmethod
    def tearDownClass(cls):
        cls._FDB._engine = cls._saved

    def test_profile_and_mode_exist(self):
        with Session(self._eng) as s:
            p = _load(s)
            self.assertIsNotNone(p)
            self.assertEqual(p.name, "MegaPointe (Beam/Spot 39ch)")
            self.assertEqual(p.fixture_type, "moving_head")
            self.assertEqual(p.manufacturer.name, "Robe")
            self.assertEqual(
                {m.name: m.channel_count for m in p.modes}, {MODE: 39})

    def test_verified_chart_attr_sequence(self):
        with Session(self._eng) as s:
            attrs = [c.attribute for c in _channels(_load(s).modes[0])]
            self.assertEqual(attrs, EXPECTED_ATTRS)

    def test_single_head_despite_repeated_raw(self):
        # MegaPointe hat viele wiederholte 'raw'-Kanaele — das ist Konvention (wie
        # L2600-Fines) und darf NICHT als Mehrkopf gedeutet werden. Entscheidend:
        # 0 color_r (kein is_spider), genau 1 pan / 1 tilt (kein Pan/Tilt-Mehrkopf).
        import src.core.app_state as A
        with Session(self._eng) as s:
            ch = _channels(_load(s).modes[0])
        attrs = [c.attribute for c in ch]
        self.assertEqual(attrs.count("color_r"), 0)
        self.assertEqual(attrs.count("pan"), 1)
        self.assertEqual(attrs.count("tilt"), 1)
        orig = A.get_channels_for_patched
        A.get_channels_for_patched = lambda fx: ch
        try:
            fx = type("FX", (), {"fixture_type": "moving_head"})()
            self.assertFalse(A.is_spider_fixture(fx))
            self.assertEqual(A.pan_tilt_head_count(fx), 1)
            self.assertEqual(A.color_head_count(fx), 1)
        finally:
            A.get_channels_for_patched = orig

    def test_no_iris(self):
        # Die MegaPointe hat KEINEN Iris-Kanal (fehlerhafte Community-Charts erfinden
        # eine). Beam-Verkleinerung via Zoom + Beam-Reducer im statischen Gobo-Rad.
        with Session(self._eng) as s:
            attrs = [c.attribute for c in _channels(_load(s).modes[0])]
        self.assertNotIn("iris", attrs)

    def test_cmy_color_group(self):
        # Echtes CMY-Subtraktivmischen -> im Color-Tab steuerbar (FLA-2: cmy_c/m/y,
        # NICHT cyan/magenta/yellow).
        from src.core.attr_groups import classify_attr
        for a in ("cmy_c", "cmy_m", "cmy_y"):
            self.assertEqual(classify_attr(a), "Color", a)
        with Session(self._eng) as s:
            attrs = [c.attribute for c in _channels(_load(s).modes[0])]
        self.assertEqual([a for a in attrs if a.startswith("cmy_")],
                         ["cmy_c", "cmy_m", "cmy_y"])

    def test_safety_defaults(self):
        with Session(self._eng) as s:
            ch = _channels(_load(s).modes[0])
        d = {c.attribute: (c.default_value, c.highlight_value) for c in ch}
        # Shutter (Ch37) 32 = offen (0-31 zu); dunkel via Dimmer 0.
        self.assertEqual(d["shutter"][0], 32)
        self.assertEqual(d["intensity"], (0, 255))
        # Pan/Tilt/Zoom/Fokus Mitte.
        self.assertEqual(d["pan"][0], 128)
        self.assertEqual(d["tilt"][0], 128)
        self.assertEqual(d["zoom"][0], 128)
        self.assertEqual(d["focus"][0], 128)
        # Power/Special (Ch6) 0 = keine Funktion (kein Reset/Lampe-aus).
        self.assertEqual(d["macro"][0], 0)

    def test_shutter_ranges_closed_at_zero_open_at_default(self):
        with Session(self._eng) as s:
            sh = next(c for c in _channels(_load(s).modes[0])
                      if c.attribute == "shutter")
            names = {(r.range_from, r.range_to): r.name for r in sh.ranges}
        self.assertEqual(names[(0, 31)], "Geschlossen")
        self.assertEqual(names[(32, 63)], "Offen")   # = Default 32

    def test_power_reset_lamp_bands_not_at_default(self):
        # Safety: der Power-Default (0) darf NICHT in einem Reset-/Lampe-aus-Band
        # liegen (sonst wuerde ein frisch gepatchtes Gerat sich reset/Lampe schalten).
        with Session(self._eng) as s:
            power = next(c for c in _channels(_load(s).modes[0])
                         if c.attribute == "macro")
            bands = [(r.range_from, r.range_to, r.name) for r in power.ranges]
        for lo, hi, name in bands:
            if any(k in name for k in ("Reset", "Lampe AUS")):
                self.assertFalse(lo <= 0 <= hi,
                                 f"Default 0 liegt im gefaehrlichen Band {name}")
        # und Default 0 liegt im "Keine Funktion"-Band.
        nofunc = next((lo, hi) for lo, hi, name in bands
                      if name == "Keine Funktion")
        self.assertTrue(nofunc[0] <= 0 <= nofunc[1])


if __name__ == "__main__":
    unittest.main()
