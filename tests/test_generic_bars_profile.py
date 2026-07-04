"""FM-5: Generische Multi-Head-Bar-Builtins (MOVBAR4 / PARBAR4).

Machen die neuen 3D-Modelle par_bar (FM-3) und mover_bar (FM-4) ueberhaupt
PATCHBAR — vorher wurden sie nur aus dem Kanal-Layout erkannt, es gab aber kein
Profil in der Bibliothek. Getestet werden Profil-Struktur (Mehrkopf-Layout),
Idempotenz von ensure_builtins und die ECHTE _viz_model_for-Routing-Entscheidung
ueber die real geseedeten Profil-Kanaele.
"""
import os
import tempfile
import unittest
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


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


def _load(session, short):
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
        .where(FixtureProfile.short_name == short)
    ).scalars().first()


def _mode(profile, name):
    return next(mode for mode in profile.modes if mode.name == name)


def _channels(mode):
    return sorted(mode.channels, key=lambda channel: channel.channel_number)


def _attrs(mode):
    return [c.attribute for c in _channels(mode)]


class MoverBar4ProfileTest(unittest.TestCase):
    """MOVBAR4: 4×(Pan/Tilt/RGB) + Master-Dimmer + offener Shutter."""

    @classmethod
    def setUpClass(cls):
        cls._FDB, cls._eng, cls._saved = _temp_seeded_engine()

    @classmethod
    def tearDownClass(cls):
        cls._FDB._engine = cls._saved

    def test_profile_exists_as_moving_head(self):
        with Session(self._eng) as s:
            p = _load(s, "MOVBAR4")
            self.assertIsNotNone(p)
            self.assertEqual(p.name, "LED Moving Bar 4×")
            self.assertEqual(p.fixture_type, "moving_head")
            self.assertEqual(p.manufacturer.name, "Generic")
            self.assertEqual(
                {m.name: m.channel_count for m in p.modes},
                {"22-Kanal 4×Move RGB": 22},
            )

    def test_per_head_pan_tilt_rgb_layout(self):
        with Session(self._eng) as s:
            attrs = _attrs(_mode(_load(s, "MOVBAR4"), "22-Kanal 4×Move RGB"))
        # 4 Kopf-Bloecke (Pan/Tilt/RGB) + Master-Dimmer + Shutter
        self.assertEqual(
            attrs,
            ["pan", "tilt", "color_r", "color_g", "color_b"] * 4
            + ["intensity", "shutter"],
        )
        # Mehrkopf: je 4 Vorkommen -> pan#0..3 / tilt#0..3 / color_r#0..3
        self.assertEqual(attrs.count("pan"), 4)
        self.assertEqual(attrs.count("tilt"), 4)
        self.assertEqual(attrs.count("color_r"), 4)

    def test_shutter_default_is_open(self):
        """Default 0 muss auf einen 'open'-Range fallen, sonst haengt die Bar
        dunkel im geschlossenen Shutter."""
        with Session(self._eng) as s:
            shutter = next(c for c in _channels(
                _mode(_load(s, "MOVBAR4"), "22-Kanal 4×Move RGB"))
                if c.attribute == "shutter")
            self.assertEqual(shutter.default_value, 0)
            hit = next(r for r in shutter.ranges
                       if r.range_from <= 0 <= r.range_to)
            self.assertEqual(hit.kind, "open")


class ParBar4ProfileTest(unittest.TestCase):
    """PARBAR4: 4×RGB (12ch) / 4×RGBW (16ch), keine Bewegung."""

    @classmethod
    def setUpClass(cls):
        cls._FDB, cls._eng, cls._saved = _temp_seeded_engine()

    @classmethod
    def tearDownClass(cls):
        cls._FDB._engine = cls._saved

    def test_profile_exists_as_led_bar(self):
        with Session(self._eng) as s:
            p = _load(s, "PARBAR4")
            self.assertIsNotNone(p)
            self.assertEqual(p.name, "LED PAR Bar 4×")
            self.assertEqual(p.fixture_type, "led_bar")
            self.assertEqual(p.manufacturer.name, "Generic")
            self.assertEqual(
                {m.name: m.channel_count for m in p.modes},
                {"12-Kanal 4×RGB": 12, "16-Kanal 4×RGBW": 16},
            )

    def test_head_layouts_have_no_movement(self):
        with Session(self._eng) as s:
            p = _load(s, "PARBAR4")
            rgb = _attrs(_mode(p, "12-Kanal 4×RGB"))
            rgbw = _attrs(_mode(p, "16-Kanal 4×RGBW"))
        self.assertEqual(rgb, ["color_r", "color_g", "color_b"] * 4)
        self.assertEqual(rgbw, ["color_r", "color_g", "color_b", "color_w"] * 4)
        for attrs in (rgb, rgbw):
            self.assertEqual(attrs.count("pan"), 0)
            self.assertEqual(attrs.count("tilt"), 0)
            self.assertEqual(attrs.count("color_r"), 4)


class EnsureBuiltinsGenericBarsTest(unittest.TestCase):
    """Nachruesten bei bereits befuellter (aelterer) DB ist idempotent."""

    def setUp(self):
        self._FDB, self._eng, self._saved = _temp_seeded_engine()

    def tearDown(self):
        self._FDB._engine = self._saved

    def test_backfill_is_idempotent(self):
        from src.core.database.fixture_db import ensure_builtins
        from src.core.database.models import FixtureProfile
        with Session(self._eng) as s:
            for short in ("MOVBAR4", "PARBAR4"):
                p = s.execute(
                    select(FixtureProfile)
                    .where(FixtureProfile.short_name == short)
                ).scalars().one()
                s.delete(p)
            s.commit()

        ensure_builtins()
        ensure_builtins()

        with Session(self._eng) as s:
            for short, n_modes in (("MOVBAR4", 1), ("PARBAR4", 2)):
                profiles = s.execute(
                    select(FixtureProfile)
                    .where(FixtureProfile.short_name == short)
                ).scalars().all()
                self.assertEqual(len(profiles), 1, short)
                self.assertEqual(len(_load(s, short).modes), n_modes, short)


class GenericBarsRoutingTest(unittest.TestCase):
    """Die ECHTE _viz_model_for-Entscheidung ueber die geseedeten Profil-Kanaele:
    MOVBAR4 -> 'mover_bar' (>=2 Pan), PARBAR4 -> 'par_bar' (keine Bewegung)."""

    @classmethod
    def setUpClass(cls):
        cls._FDB, cls._eng, cls._saved = _temp_seeded_engine()

    @classmethod
    def tearDownClass(cls):
        cls._FDB._engine = cls._saved

    def _chans_for(self, short, mode_name):
        with Session(self._eng) as s:
            return [SimpleNamespace(attribute=c.attribute)
                    for c in _channels(_mode(_load(s, short), mode_name))]

    def _model_for(self, chans):
        import src.ui.visualizer.visualizer_window as VW
        saved_g, saved_s = VW.get_channels_for_patched, VW.is_spider_fixture
        VW.get_channels_for_patched = lambda f: chans
        VW.is_spider_fixture = lambda f: sum(
            1 for c in chans if c.attribute == "color_r") >= 2
        try:
            return VW.VisualizerBridge._viz_model_for(
                SimpleNamespace(), SimpleNamespace(fixture_type="moving_head"))
        finally:
            VW.get_channels_for_patched = saved_g
            VW.is_spider_fixture = saved_s

    def test_mover_bar_routes_to_mover_bar(self):
        chans = self._chans_for("MOVBAR4", "22-Kanal 4×Move RGB")
        self.assertEqual(self._model_for(chans), "mover_bar")

    def test_par_bar_routes_to_par_bar(self):
        for mode in ("12-Kanal 4×RGB", "16-Kanal 4×RGBW"):
            chans = self._chans_for("PARBAR4", mode)
            self.assertEqual(self._model_for(chans), "par_bar", mode)


if __name__ == "__main__":
    unittest.main()
