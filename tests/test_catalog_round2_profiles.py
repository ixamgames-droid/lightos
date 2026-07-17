"""Katalog-Erweiterung Runde 2 (2026-07-17): gaengige Wash-/Matrix-Scheinwerfer +
LED-Bars als Builtins.

Deckt die Bibliothek ueber die Nutzer-Strahler hinaus auf verbreitete
Markengeraete aus (Cameo FLAT PRO 7, ADJ 5PX HEX, Stairville LED Bar 240/8,
Chauvet DJ COLORband PiX). Getestet werden Profil-Struktur/Geraeteklasse, die
gegen Primaer-/Community-Quellen (Open Fixture Library / QLC+) verifizierten
Kanal-Charts, die Safety-Shutter-Defaults und die ECHTE viz_model_for-Routing-
Entscheidung (Segment-/Pixel-Modi -> 'par_bar'). Analog test_generic_bars_profile.
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


class _SeededCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._FDB, cls._eng, cls._saved = _temp_seeded_engine()

    @classmethod
    def tearDownClass(cls):
        cls._FDB._engine = cls._saved

    def _shutter(self, short, mode_name):
        with Session(self._eng) as s:
            return next(c for c in _channels(_mode(_load(s, short), mode_name))
                       if c.attribute == "shutter")

    def _assert_default_open(self, short, mode_name):
        """Der Shutter-Default MUSS auf einen 'open'-Range fallen, sonst haengt
        das Geraet im geschlossenen Shutter (dunkel) — dokumentierte Falle."""
        sh = self._shutter(short, mode_name)
        hit = next(r for r in sh.ranges
                   if r.range_from <= sh.default_value <= r.range_to)
        self.assertEqual(hit.kind, "open",
                         f"{short}/{mode_name}: Shutter-Default "
                         f"{sh.default_value} faellt auf '{hit.name}' ({hit.kind})")


class CameoFlatPro7Test(_SeededCase):
    """Cameo FLAT PRO 7 — RGBWA-Flat-PAR, Chart: Open Fixture Library."""

    def test_profile_class_and_modes(self):
        with Session(self._eng) as s:
            p = _load(s, "FLATPRO7")
            self.assertIsNotNone(p)
            self.assertEqual(p.name, "FLAT PRO 7")
            self.assertEqual(p.fixture_type, "par")
            self.assertEqual(p.manufacturer.name, "Cameo")
            self.assertEqual(
                {m.name: m.channel_count for m in p.modes},
                {"3-Kanal RGB": 3, "5-Kanal RGBWA": 5,
                 "8-Kanal Voll": 8, "2-Kanal Dimmer+Makro": 2},
            )

    def test_channel_charts(self):
        with Session(self._eng) as s:
            p = _load(s, "FLATPRO7")
            self.assertEqual(_attrs(_mode(p, "5-Kanal RGBWA")),
                             ["color_r", "color_g", "color_b", "color_w", "color_a"])
            # 8ch laut OFL: Dimmer, Strobe, R, G, B, W, A, Farb-Makro
            self.assertEqual(_attrs(_mode(p, "8-Kanal Voll")),
                             ["intensity", "shutter", "color_r", "color_g",
                              "color_b", "color_w", "color_a", "color_wheel"])

    def test_strobe_default_open(self):
        self._assert_default_open("FLATPRO7", "8-Kanal Voll")


class Adj5pxHexTest(_SeededCase):
    """ADJ 5PX HEX — RGBWA+UV HEX-PAR, Chart: QLC+ Fixture-Library.
    Sicherheitskritisch: der Strobe-Kanal ist ein echter Shutter mit
    DMX 0..31 = 'LED OFF' -> Default darf NICHT 0 sein."""

    def test_profile_class_and_modes(self):
        with Session(self._eng) as s:
            p = _load(s, "ADJ5PXHEX")
            self.assertIsNotNone(p)
            self.assertEqual(p.name, "5PX HEX")
            self.assertEqual(p.fixture_type, "par")
            self.assertEqual(p.manufacturer.name, "ADJ")
            self.assertEqual(
                {m.name: m.channel_count for m in p.modes},
                {"6-Kanal RGBWA+UV": 6, "7-Kanal + Dimmer": 7,
                 "8-Kanal + Strobe": 8, "12-Kanal Voll": 12},
            )

    def test_six_in_one_color_order(self):
        with Session(self._eng) as s:
            self.assertEqual(
                _attrs(_mode(_load(s, "ADJ5PXHEX"), "6-Kanal RGBWA+UV")),
                ["color_r", "color_g", "color_b", "color_w", "color_a", "color_uv"])

    def test_strobe_default_not_closed(self):
        # In beiden Modi mit Strobe muss der Default in einem offenen Band liegen.
        for mode_name in ("8-Kanal + Strobe", "12-Kanal Voll"):
            sh = self._shutter("ADJ5PXHEX", mode_name)
            self.assertNotEqual(sh.default_value, 0, mode_name)
            self._assert_default_open("ADJ5PXHEX", mode_name)
            # Der 0..31-Bereich existiert und ist als 'closed' markiert.
            closed = next(r for r in sh.ranges if r.range_from == 0)
            self.assertEqual(closed.kind, "closed", mode_name)

    def test_no_repeated_attribute_in_single_head_modes(self):
        """Single-Head-Par: KEIN Attribut darf sich in einem Modus wiederholen,
        sonst deutet die Mehrkopf-Konvention (attr#N) das 2. Vorkommen als Kopf 1
        und es erbt den Wert des 1. (ENG-03/07/09-Falle). Konkret nagelt das die
        frueher doppelte 'macro'-Nutzung im 12ch-Modus (Programme + Dimmer-Modus)
        fest — der Dimmer-Modus-Kanal ist jetzt 'raw'."""
        with Session(self._eng) as s:
            p = _load(s, "ADJ5PXHEX")
            for m in p.modes:
                attrs = _attrs(m)
                self.assertEqual(len(attrs), len(set(attrs)),
                                 f"{m.name}: doppeltes Attribut {sorted(attrs)}")


class StairvilleBar2408Test(_SeededCase):
    """Stairville LED Bar 240/8 RGB — 8-Segment-Bar, Chart: Open Fixture Library."""

    def test_profile_class_and_modes(self):
        with Session(self._eng) as s:
            p = _load(s, "STAIRB2408")
            self.assertIsNotNone(p)
            self.assertEqual(p.name, "LED Bar 240/8 RGB")
            self.assertEqual(p.fixture_type, "led_bar")
            self.assertEqual(p.manufacturer.name, "Stairville")
            self.assertEqual(
                {m.name: m.channel_count for m in p.modes},
                {"2-Kanal Automatik": 2, "3-Kanal RGB": 3,
                 "5-Kanal RGB+Dimmer": 5, "24-Kanal 8×RGB": 24},
            )

    def test_eight_segments(self):
        with Session(self._eng) as s:
            attrs = _attrs(_mode(_load(s, "STAIRB2408"), "24-Kanal 8×RGB"))
        self.assertEqual(attrs, ["color_r", "color_g", "color_b"] * 8)
        self.assertEqual(attrs.count("color_r"), 8)     # 8 Banks -> par_bar

    def test_strobe_default_open(self):
        self._assert_default_open("STAIRB2408", "5-Kanal RGB+Dimmer")


class ChauvetColorbandPixTest(_SeededCase):
    """Chauvet DJ COLORband PiX — 12-Pixel-Bar, Chart: Open Fixture Library."""

    def test_profile_class_and_modes(self):
        with Session(self._eng) as s:
            p = _load(s, "CBANDPIX")
            self.assertIsNotNone(p)
            self.assertEqual(p.name, "COLORband PiX")
            self.assertEqual(p.fixture_type, "led_bar")
            self.assertEqual(p.manufacturer.name, "Chauvet DJ")
            self.assertEqual(
                {m.name: m.channel_count for m in p.modes},
                {"3-Kanal RGB": 3, "4-Kanal RGB+Dimmer": 4,
                 "7-Kanal Voll": 7, "36-Kanal 12×RGB": 36},
            )

    def test_twelve_pixels(self):
        with Session(self._eng) as s:
            attrs = _attrs(_mode(_load(s, "CBANDPIX"), "36-Kanal 12×RGB"))
        self.assertEqual(attrs, ["color_r", "color_g", "color_b"] * 12)
        self.assertEqual(attrs.count("color_r"), 12)    # 12 Banks -> par_bar

    def test_seven_channel_full_layout(self):
        # OFL 7ch: R, G, B, Farb-Makro, Strobe, Auto-Programm, Dimmer
        with Session(self._eng) as s:
            self.assertEqual(
                _attrs(_mode(_load(s, "CBANDPIX"), "7-Kanal Voll")),
                ["color_r", "color_g", "color_b", "color_wheel",
                 "shutter", "macro", "intensity"])


class CatalogRound2RoutingTest(_SeededCase):
    """Die ECHTE _viz_model_for-Entscheidung ueber die geseedeten Profil-Kanaele:
    Segment-/Pixel-Modi (>=2 color_r, keine Bewegung) -> 'par_bar'; Single-Bank
    -> None (Aufrufer nutzt den fixture_type)."""

    def _model_for(self, short, mode_name, fixture_type):
        with Session(self._eng) as s:
            chans = [SimpleNamespace(attribute=c.attribute)
                     for c in _channels(_mode(_load(s, short), mode_name))]
        import src.core.app_state as AS
        from src.ui.visualizer.visualizer_window import VisualizerBridge
        saved = AS.get_channels_for_patched
        AS.get_channels_for_patched = lambda f: chans
        try:
            return VisualizerBridge._viz_model_for(
                SimpleNamespace(), SimpleNamespace(fixture_type=fixture_type))
        finally:
            AS.get_channels_for_patched = saved

    def test_segment_and_pixel_modes_route_to_par_bar(self):
        self.assertEqual(
            self._model_for("STAIRB2408", "24-Kanal 8×RGB", "led_bar"), "par_bar")
        self.assertEqual(
            self._model_for("CBANDPIX", "36-Kanal 12×RGB", "led_bar"), "par_bar")

    def test_single_bank_modes_keep_fixture_type(self):
        # Kein Multi-Emitter -> viz faellt auf den fixture_type zurueck.
        self.assertEqual(
            self._model_for("FLATPRO7", "5-Kanal RGBWA", "par"), "par")
        self.assertEqual(
            self._model_for("CBANDPIX", "3-Kanal RGB", "led_bar"), "led_bar")


class EnsureBuiltinsRound2Test(unittest.TestCase):
    """Nachruesten bei bereits befuellter (aelterer) DB ist idempotent —
    keine Duplikate, Profil-IDs bleiben stabil."""

    _SHORTS = ("FLATPRO7", "ADJ5PXHEX", "STAIRB2408", "CBANDPIX")

    def setUp(self):
        self._FDB, self._eng, self._saved = _temp_seeded_engine()

    def tearDown(self):
        self._FDB._engine = self._saved

    def test_backfill_is_idempotent(self):
        from src.core.database.fixture_db import ensure_builtins
        from src.core.database.models import FixtureProfile
        with Session(self._eng) as s:
            for short in self._SHORTS:
                s.delete(_load(s, short))
            s.commit()

        ensure_builtins()
        ensure_builtins()

        with Session(self._eng) as s:
            for short in self._SHORTS:
                rows = s.execute(
                    select(FixtureProfile)
                    .where(FixtureProfile.short_name == short)
                ).scalars().all()
                self.assertEqual(len(rows), 1, short)


if __name__ == "__main__":
    unittest.main()
