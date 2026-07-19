"""Katalog-Erweiterung Runde 4 (2026-07-19): namhafte reale Profi-Flaggschiffe.

  (A) Martin Atomic 3000 DMX  — Xenon-Strobe/Blinder (fixture_type 'strobe'),
      native Modi NUR 1/3/4 Kanal (Farbe/Luefter = separates 'Atomic Colors'-
      Zubehoer, bewusst NICHT enthalten). Neues Attribut 'duration' (Blitzdauer).
  (B) Robe Pointe             — Beam/Spot-Hybrid Moving Head (16-Kanal). Zwei
      Gobo-Raeder (gobo_wheel + gobo_wheel2) + zwei Speed (speed + effect_speed)
      distinkt. Neues Attribut 'gobo_wheel2'.
  (C) Martin MAC Aura         — RGBW-LED-Wash Moving Head (Standard 14ch). EINE
      RGBW-Bank -> Single-'moving_head' (Extended-25ch bewusst weggelassen).

Getestet: Profil-Struktur/Geraeteklasse, die gegen QLC+ .qxf + HERSTELLER-DMX-
Protokoll (Martin/Robe) + OFL verifizierten Charts, die Safety-Defaults (Strobe
= Blackout beim Patchen; MH-Shutter = offen), die Distinkt-Attribut-Layouts
(keine Programmer-Dedup), die neuen Attribute (Klassifikation + kein Grand-
Master-Dim von 'duration') und die ECHTE viz_model_for-Routing-Entscheidung
(alle Single-Head -> fixture_type, kein Spider/mover_bar). Analog Runde 2/3.
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


def _range_at(channel, value):
    return next(r for r in channel.ranges
               if r.range_from <= value <= r.range_to)


class _SeededCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._FDB, cls._eng, cls._saved = _temp_seeded_engine()

    @classmethod
    def tearDownClass(cls):
        cls._FDB._engine = cls._saved

    def _first(self, short, mode_name, attr):
        with Session(self._eng) as s:
            return next(c for c in _channels(_mode(_load(s, short), mode_name))
                        if c.attribute == attr)

    def _assert_shutter_default_open(self, short, mode_name):
        sh = self._first(short, mode_name, "shutter")
        hit = _range_at(sh, sh.default_value)
        self.assertEqual(hit.kind, "open",
                         f"{short}/{mode_name}: Shutter-Default {sh.default_value} "
                         f"faellt auf '{hit.name}' ({hit.kind}), erwartet 'open'")


class MartinAtomic3000Test(_SeededCase):
    """Martin Atomic 3000 DMX — Xenon-Strobe/Blinder, Chart: QLC+ + Martin-Protokoll."""

    def test_profile_class_and_modes(self):
        with Session(self._eng) as s:
            p = _load(s, "ATOMIC3000")
            self.assertIsNotNone(p)
            self.assertEqual(p.name, "Atomic 3000 DMX")
            self.assertEqual(p.fixture_type, "strobe")
            self.assertEqual(p.manufacturer.name, "Martin")
            self.assertEqual(
                {m.name: m.channel_count for m in p.modes},
                {"1-Kanal": 1, "3-Kanal": 3, "4-Kanal (+ Effekte)": 4},
            )

    def test_channel_charts(self):
        with Session(self._eng) as s:
            p = _load(s, "ATOMIC3000")
            self.assertEqual(_attrs(_mode(p, "1-Kanal")), ["shutter"])
            self.assertEqual(_attrs(_mode(p, "3-Kanal")),
                             ["intensity", "duration", "strobe"])
            self.assertEqual(_attrs(_mode(p, "4-Kanal (+ Effekte)")),
                             ["intensity", "duration", "strobe", "macro"])

    def test_strobe_default_is_blackout_not_flashing(self):
        """Safety: Xenon-Strobe darf beim Patchen NICHT losblitzen. Der 1-Kanal-
        Shutter defaultet auf 0 = Blackout (kind 'closed'), NICHT auf eine Blitz-
        rate; Intensity/Rate defaulten ebenfalls auf 0 (kein Blitz)."""
        with Session(self._eng) as s:
            p = _load(s, "ATOMIC3000")
            sh = next(c for c in _channels(_mode(p, "1-Kanal"))
                      if c.attribute == "shutter")
            self.assertEqual(sh.default_value, 0)
            self.assertEqual(_range_at(sh, 0).kind, "closed")
            # 3-/4-Kanal: Intensity-Default 0 (blackout) + Rate-Default 0 (kein Blitz).
            for mode_name in ("3-Kanal", "4-Kanal (+ Effekte)"):
                intens = next(c for c in _channels(_mode(p, mode_name))
                              if c.attribute == "intensity")
                self.assertEqual(intens.default_value, 0)
                rate = next(c for c in _channels(_mode(p, mode_name))
                            if c.attribute == "strobe")
                self.assertEqual(rate.default_value, 0)
                self.assertNotEqual(_range_at(rate, 0).kind, "strobe")

    def test_no_repeated_attribute(self):
        with Session(self._eng) as s:
            p = _load(s, "ATOMIC3000")
            for m in p.modes:
                a = _attrs(m)
                self.assertEqual(len(a), len(set(a)),
                                 f"{m.name}: doppeltes Attribut {sorted(a)}")

    def test_effects_default_no_effect(self):
        # Effekt-Kanal (macro) Default 0 = "Kein Effekt".
        ch = self._first("ATOMIC3000", "4-Kanal (+ Effekte)", "macro")
        self.assertEqual(ch.default_value, 0)
        self.assertEqual(_range_at(ch, 0).name, "Kein Effekt")


class RobePointeTest(_SeededCase):
    """Robe Pointe — Beam/Spot-Hybrid Moving Head (16ch), Chart: QLC+ + Robe-Protokoll."""

    _EXPECTED = [
        "pan", "tilt", "speed", "macro", "color_wheel", "effect_speed",
        "gobo_wheel", "gobo_wheel2", "gobo_rotation", "prism", "prism_rotation",
        "frost", "zoom", "focus", "shutter", "intensity",
    ]

    def test_profile_class_and_mode(self):
        with Session(self._eng) as s:
            p = _load(s, "POINTE")
            self.assertIsNotNone(p)
            self.assertEqual(p.name, "Pointe (Beam/Spot 16ch)")
            self.assertEqual(p.fixture_type, "moving_head")
            self.assertEqual(p.manufacturer.name, "Robe")
            self.assertEqual({m.name: m.channel_count for m in p.modes},
                             {"16-Kanal": 16})

    def test_channel_chart_exact(self):
        with Session(self._eng) as s:
            self.assertEqual(_attrs(_mode(_load(s, "POINTE"), "16-Kanal")),
                             self._EXPECTED)

    def test_two_gobo_wheels_and_two_speeds_distinct(self):
        """Zwei Gobo-Raeder (statisch + rotierend) und zwei Speed-Kanaele muessen
        DISTINKTE Attribute tragen — sonst dedupliziert der Programmer sie zu je
        einem Regler (EURON10-Falle). 16 Kanaele -> 16 verschiedene Attribute."""
        with Session(self._eng) as s:
            a = _attrs(_mode(_load(s, "POINTE"), "16-Kanal"))
        self.assertEqual(len(a), len(set(a)), f"doppeltes Attribut: {sorted(a)}")
        self.assertIn("gobo_wheel", a)
        self.assertIn("gobo_wheel2", a)
        self.assertIn("speed", a)
        self.assertIn("effect_speed", a)

    def test_shutter_default_open(self):
        # 0-31 = zu (Lampe reduziert) -> Default 40 MUSS auf 32-63 (offen) fallen.
        self._assert_shutter_default_open("POINTE", "16-Kanal")
        sh = self._first("POINTE", "16-Kanal", "shutter")
        self.assertEqual(sh.default_value, 40)

    def test_gobo_wheels_have_slot_ranges(self):
        # Beide Gobo-Raeder tragen Slot-Ranges (open/gobo/rotate/shake) fuer die
        # Schnellwahl-/kind-Ableitung.
        for attr in ("gobo_wheel", "gobo_wheel2"):
            ch = self._first("POINTE", "16-Kanal", attr)
            kinds = {r.kind for r in ch.ranges}
            self.assertIn("gobo", kinds, attr)
            self.assertIn("open", kinds, attr)


class MartinMacAuraTest(_SeededCase):
    """Martin MAC Aura — RGBW-LED-Wash Moving Head (Standard 14ch), Chart: QLC+ + Manual."""

    _EXPECTED = [
        "shutter", "intensity", "zoom", "pan", "pan_fine", "tilt", "tilt_fine",
        "macro", "color_wheel", "color_r", "color_g", "color_b", "color_w", "raw",
    ]

    def test_profile_class_and_mode(self):
        with Session(self._eng) as s:
            p = _load(s, "MACAURA")
            self.assertIsNotNone(p)
            self.assertEqual(p.name, "MAC Aura (Wash 14ch)")
            self.assertEqual(p.fixture_type, "moving_head")
            self.assertEqual(p.manufacturer.name, "Martin")
            self.assertEqual({m.name: m.channel_count for m in p.modes},
                             {"14-Kanal (Standard)": 14})

    def test_channel_chart_exact(self):
        with Session(self._eng) as s:
            self.assertEqual(_attrs(_mode(_load(s, "MACAURA"), "14-Kanal (Standard)")),
                             self._EXPECTED)

    def test_single_rgbw_bank_and_ctc_raw(self):
        # Genau EINE RGBW-Bank (color_r einmal) -> kein Multi-Emitter. CTC='raw'.
        with Session(self._eng) as s:
            a = _attrs(_mode(_load(s, "MACAURA"), "14-Kanal (Standard)"))
        self.assertEqual(a.count("color_r"), 1)
        self.assertEqual(a.count("raw"), 1)   # CTC
        self.assertEqual(len(a), len(set(a)))  # keine Dedup-Kollision

    def test_shutter_default_open_factory(self):
        # Werksdefault 22 = offen (0-19 = zu).
        self._assert_shutter_default_open("MACAURA", "14-Kanal (Standard)")
        sh = self._first("MACAURA", "14-Kanal (Standard)", "shutter")
        self.assertEqual(sh.default_value, 22)

    def test_colorwheel_open_default_enables_rgbw(self):
        # Farbrad-Default 0 = "offen, RGBW-Mischung aktiv" (sonst blockiert das Rad
        # die RGBW-Farbe). color_wheel + RGBW koexistieren (wie ADJ FlatPar).
        cw = self._first("MACAURA", "14-Kanal (Standard)", "color_wheel")
        self.assertEqual(cw.default_value, 0)
        self.assertEqual(_range_at(cw, 0).kind, "open")


class CatalogRound4RoutingTest(_SeededCase):
    """ECHTE _viz_model_for-Entscheidung: alle drei sind Single-Head -> der
    Renderer nutzt den fixture_type (strobe/moving_head), NIE Spider/mover_bar
    (keiner hat >=2 color_r-Banks)."""

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

    def test_atomic_routes_to_strobe(self):
        for mode_name in ("1-Kanal", "3-Kanal", "4-Kanal (+ Effekte)"):
            self.assertEqual(self._model_for("ATOMIC3000", mode_name, "strobe"),
                             "strobe", mode_name)

    def test_pointe_routes_to_moving_head(self):
        self.assertEqual(self._model_for("POINTE", "16-Kanal", "moving_head"),
                         "moving_head")

    def test_mac_aura_routes_to_moving_head(self):
        # EINE RGBW-Bank -> kein Spider/mover_bar trotz color_r + color_wheel.
        self.assertEqual(
            self._model_for("MACAURA", "14-Kanal (Standard)", "moving_head"),
            "moving_head")


class CatalogRound4VocabularyTest(unittest.TestCase):
    """Die zwei neuen Attribute sind exact-match klassifiziert + beschriftet und
    'duration' wird NICHT vom Grand Master gedimmt (Effect, nicht Intensity)."""

    def test_new_attributes_classify_exact(self):
        from src.core.attr_groups import classify_attr, attr_label
        self.assertEqual(classify_attr("duration"), "Effect")
        self.assertEqual(classify_attr("gobo_wheel2"), "Gobo")
        self.assertEqual(attr_label("duration"), "Blitzdauer")
        self.assertEqual(attr_label("gobo_wheel2"), "Rotier-Gobo-Rad")
        # Mehrkopf-Suffix aendert die Gruppe/Label-Basis nicht.
        self.assertEqual(classify_attr("gobo_wheel2#1"), "Gobo")

    def test_duration_not_grand_master_dimmed(self):
        # 'duration' ist ein Parameter (Blitzdauer), KEIN Helligkeitswert -> darf
        # nicht im Dimmer-Sentinel stehen, sonst skaliert der Grand Master ihn.
        from src.core.app_state import _DIM_INTENSITY_ATTRS
        self.assertNotIn("duration", _DIM_INTENSITY_ATTRS)

    def test_new_attributes_in_editor_vocabulary(self):
        from src.ui.widgets.fixture_editor import CHANNEL_ATTRS
        for attr in ("duration", "gobo_wheel2", "effect_speed", "fan"):
            self.assertIn(attr, CHANNEL_ATTRS, attr)


class CatalogRound4IdempotencyTest(_SeededCase):
    """ensure_builtins darf die Runde-4-Builtins nicht duplizieren (NEUE Builtins
    -> nur Backfill, keine Signatur-Migration; Profil-ID bleibt stabil)."""

    def test_ensure_builtins_idempotent(self):
        from src.core.database.models import FixtureProfile
        self._FDB.ensure_builtins()
        self._FDB.ensure_builtins()
        with Session(self._eng) as s:
            for short in ("ATOMIC3000", "POINTE", "MACAURA"):
                rows = s.execute(
                    select(FixtureProfile.id)
                    .where(FixtureProfile.short_name == short,
                           FixtureProfile.source == "builtin")
                ).all()
                self.assertEqual(len(rows), 1, f"{short}: {len(rows)} Profile (erwartet 1)")


if __name__ == "__main__":
    unittest.main()
