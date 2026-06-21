"""Tests fuer das U King Spider 14ch Profil (China-Strahler des Nutzers,
2026-06-14, aus der QLC+-Definition U-King-Speider.qxf).

Abgedeckt:
- 14-Kanal-Layout (2x Tilt [Bar L/R] /Speed/Dimmer/Shutter + 2x RGBW + Reset).
- Beide RGBW-Baenke teilen die Farbattribute -> gemeinsame Farbe.
- Shutter-Bereiche/kinds (offen/strobe/blinken) + offener Default -> leuchtet.
- Fixture-Typ moving_head (echte Pan/Tilt-Motoren).
- open_value_for() liefert einen offenen Shutter-Wert.
- ensure_builtins() ruestet das Profil in einer bestehenden DB nach (idempotent).
"""
import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload


def _temp_seeded_engine():
    """Frische Temp-DB mit komplettem Seed; gibt (modul, engine, alt) zurueck."""
    from src.core.database import fixture_db as FDB
    from src.core.database.fixture_db import get_engine, _seed
    saved = FDB._engine
    eng = get_engine(tempfile.mktemp(suffix=".db"))
    with Session(eng) as s:
        _seed(s)
        s.commit()
    FDB._engine = eng
    return FDB, eng, saved


def _load_spider(s):
    from src.core.database.models import (FixtureProfile, FixtureMode,
                                          FixtureChannel)
    return s.execute(
        select(FixtureProfile)
        .options(selectinload(FixtureProfile.manufacturer),
                 selectinload(FixtureProfile.modes)
                 .selectinload(FixtureMode.channels)
                 .selectinload(FixtureChannel.ranges))
        .where(FixtureProfile.short_name == "SPIDER14")
    ).scalars().first()


def _mode(prof, name="14-Kanal"):
    return next(m for m in prof.modes if m.name == name)


def _chans(mode):
    return sorted(mode.channels, key=lambda c: c.channel_number)


def _attrs(mode):
    return [c.attribute for c in _chans(mode)]


class SpiderProfileTest(unittest.TestCase):
    """Kanal-Layout + Wertebereiche des Spider-Profils."""

    @classmethod
    def setUpClass(cls):
        cls._FDB, cls._eng, cls._saved = _temp_seeded_engine()

    @classmethod
    def tearDownClass(cls):
        cls._FDB._engine = cls._saved

    def test_existiert_und_typ(self):
        with Session(self._eng) as s:
            prof = _load_spider(s)
            self.assertIsNotNone(prof, "Spider-Profil muss geseedet sein")
            self.assertEqual(prof.fixture_type, "moving_head")
            self.assertEqual(prof.manufacturer.name, "U King")
            self.assertEqual(len(prof.modes), 1)

    def test_layout_14_kanal(self):
        with Session(self._eng) as s:
            attrs = _attrs(_mode(_load_spider(s)))
        self.assertEqual(attrs, [
            "tilt", "tilt", "speed", "intensity", "shutter",
            "color_r", "color_g", "color_b", "color_w",
            "color_r", "color_g", "color_b", "color_w", "reset"])

    def test_zwei_rgbw_baenke_teilen_farbe(self):
        """Beide LED-Baenke benutzen dieselben Farbattribute -> ein Programmer-
        Farbwert faerbt beide Koepfe (wie LED-Bar-Segmente)."""
        with Session(self._eng) as s:
            attrs = _attrs(_mode(_load_spider(s)))
        for c in ("color_r", "color_g", "color_b", "color_w"):
            self.assertEqual(attrs.count(c), 2, c)

    def test_shutter_offen_default_und_ranges(self):
        with Session(self._eng) as s:
            sh = next(c for c in _mode(_load_spider(s)).channels
                      if c.attribute == "shutter")
            self.assertEqual(sh.default_value, 8, "Default offen -> leuchtet")
            ranges = {(r.range_from, r.range_to): r.kind
                      for r in sh.ranges}
        self.assertEqual(ranges[(0, 7)], "closed")
        self.assertEqual(ranges[(8, 15)], "open")
        self.assertEqual(ranges[(16, 131)], "strobe")
        self.assertEqual(ranges[(140, 181)], "strobe")    # Blinken 1
        self.assertEqual(ranges[(248, 255)], "open")

    def test_shutter_hat_offenen_slot(self):
        """Der erste 'open'-Slot (8..15) macht den Shutter via open_value_for
        ableitbar — EFX oeffnet ihn so automatisch (efx.py)."""
        with Session(self._eng) as s:
            sh = next(c for c in _mode(_load_spider(s)).channels
                      if c.attribute == "shutter")
            first_open = next(r for r in sorted(sh.ranges,
                                                key=lambda r: r.range_from)
                              if (r.kind or "").lower() == "open")
            mid = (first_open.range_from + first_open.range_to) // 2
        self.assertEqual((first_open.range_from, first_open.range_to), (8, 15))
        self.assertEqual(mid, 11)   # open_value_for-Mittelwert, offen

    def test_tilts_zentriert(self):
        # Mehrkopf 2026-06-16: zwei separate Tilts (Bar L/R), kein Pan mehr.
        with Session(self._eng) as s:
            chans = _chans(_mode(_load_spider(s)))
        tilts = [c for c in chans if c.attribute == "tilt"]
        self.assertEqual(len(tilts), 2, "zwei separate Tilts (Bar L/R)")
        for t in tilts:
            self.assertEqual(t.default_value, 128)
        inten = next(c for c in chans if c.attribute == "intensity")
        self.assertEqual(inten.default_value, 0)


class EnsureBuiltinsSpiderTest(unittest.TestCase):
    """ensure_builtins() ruestet das Spider-Profil in einer DB nach, die es
    noch nicht hat (Nutzer-DB existiert bereits) — und bleibt idempotent."""

    def setUp(self):
        self._FDB, self._eng, self._saved = _temp_seeded_engine()

    def tearDown(self):
        self._FDB._engine = self._saved

    def _delete_spider(self):
        from src.core.database.models import FixtureProfile
        with Session(self._eng) as s:
            prof = s.execute(
                select(FixtureProfile)
                .where(FixtureProfile.short_name == "SPIDER14")
            ).scalars().first()
            if prof is not None:
                s.delete(prof)
                s.commit()

    def test_nachruesten_wenn_fehlt(self):
        from src.core.database.fixture_db import ensure_builtins
        from src.core.database.models import FixtureProfile
        self._delete_spider()
        with Session(self._eng) as s:
            self.assertIsNone(s.execute(
                select(FixtureProfile)
                .where(FixtureProfile.short_name == "SPIDER14")
            ).scalars().first())
        ensure_builtins()
        with Session(self._eng) as s:
            prof = _load_spider(s)
            self.assertIsNotNone(prof, "ensure_builtins muss Spider anlegen")
            self.assertEqual(len(_mode(prof).channels), 14)
            self.assertEqual(prof.manufacturer.name, "U King")

    def test_idempotent_kein_duplikat(self):
        from src.core.database.fixture_db import ensure_builtins
        from src.core.database.models import FixtureProfile
        ensure_builtins()
        ensure_builtins()
        with Session(self._eng) as s:
            n = len(s.execute(
                select(FixtureProfile)
                .where(FixtureProfile.short_name == "SPIDER14")
            ).scalars().all())
        self.assertEqual(n, 1, "kein Duplikat durch wiederholtes ensure_builtins")


def _load_short(s, short):
    from src.core.database.models import (FixtureProfile, FixtureMode,
                                          FixtureChannel)
    return s.execute(
        select(FixtureProfile)
        .options(selectinload(FixtureProfile.manufacturer),
                 selectinload(FixtureProfile.modes)
                 .selectinload(FixtureMode.channels)
                 .selectinload(FixtureChannel.ranges))
        .where(FixtureProfile.short_name == short)
    ).scalars().first()


class WeitereDaniStrahlerTest(unittest.TestCase):
    """Conti Moving Head 11ch, Klein Conti 7ch RGBW, Party Lights Laser 7ch."""

    @classmethod
    def setUpClass(cls):
        cls._FDB, cls._eng, cls._saved = _temp_seeded_engine()

    @classmethod
    def tearDownClass(cls):
        cls._FDB._engine = cls._saved

    def test_conti_mh_layout(self):
        with Session(self._eng) as s:
            prof = _load_short(s, "CONTIMH")
            self.assertIsNotNone(prof)
            self.assertEqual(prof.fixture_type, "moving_head")
            self.assertEqual(prof.manufacturer.name, "Conti")
            mode = prof.modes[0]
            attrs = [c.attribute for c in sorted(mode.channels,
                                                 key=lambda c: c.channel_number)]
        self.assertEqual(attrs, [
            "pan", "pan_fine", "tilt", "tilt_fine", "color_wheel",
            "gobo_wheel", "shutter", "intensity", "speed", "macro", "reset"])

    def test_conti_gobo_namen(self):
        with Session(self._eng) as s:
            prof = _load_short(s, "CONTIMH")
            gobo = next(c for c in prof.modes[0].channels
                        if c.attribute == "gobo_wheel")
            slots = {(r.range_from, r.range_to): (r.name, r.kind)
                     for r in gobo.ranges}
        self.assertEqual(slots[(8, 15)], ("Ring", "gobo"))
        self.assertEqual(slots[(56, 63)], ("Zebra", "gobo"))
        self.assertEqual(slots[(72, 79)][1], "shake")
        self.assertEqual(slots[(128, 255)][1], "rotate")

    def test_klein_conti_par(self):
        with Session(self._eng) as s:
            prof = _load_short(s, "KLEINCONTI")
            self.assertIsNotNone(prof)
            self.assertEqual(prof.fixture_type, "par")
            self.assertEqual(prof.manufacturer.name, "Klein")
            mode = prof.modes[0]
            chans = {c.attribute: c for c in mode.channels}
            attrs = [c.attribute for c in sorted(mode.channels,
                                                 key=lambda c: c.channel_number)]
            sh_ranges = {(r.range_from, r.range_to): r.kind
                         for r in chans["shutter"].ranges}
        self.assertEqual(attrs, ["intensity", "color_r", "color_g", "color_b",
                                 "color_w", "shutter", "color_wheel"])
        # Shutter 0 = offen -> PAR leuchtet bei Default
        self.assertEqual(sh_ranges[(0, 0)], "open")

    def test_party_laser(self):
        with Session(self._eng) as s:
            prof = _load_short(s, "PARTYLASER")
            self.assertIsNotNone(prof)
            self.assertEqual(prof.fixture_type, "laser")
            self.assertEqual(prof.manufacturer.name, "Party Lights")
            mode = prof.modes[0]
            attrs = [c.attribute for c in sorted(mode.channels,
                                                 key=lambda c: c.channel_number)]
        # Zwei rote Dioden teilen color_r, Motor = pan
        self.assertEqual(attrs, ["macro", "color_r", "color_r", "color_g",
                                 "color_b", "shutter", "pan"])

    def test_eurolite_gross_par(self):
        with Session(self._eng) as s:
            prof = _load_short(s, "EUROGROSS")
            self.assertIsNotNone(prof)
            self.assertEqual(prof.fixture_type, "par")
            self.assertEqual(prof.manufacturer.name, "Eurolite")
            mode = prof.modes[0]
            attrs = [c.attribute for c in sorted(mode.channels,
                                                 key=lambda c: c.channel_number)]
        # Kanal-Reihenfolge laut QXF-Mode: R, G, B, Dimmer, Shutter
        self.assertEqual(attrs, ["color_r", "color_g", "color_b",
                                 "intensity", "shutter"])

    def test_ensure_builtins_ruestet_alle_nach(self):
        from src.core.database.fixture_db import ensure_builtins
        from src.core.database.models import FixtureProfile
        shorts = ("CONTIMH", "KLEINCONTI", "PARTYLASER", "EUROGROSS")
        with Session(self._eng) as s:
            for short in shorts:
                prof = s.execute(select(FixtureProfile)
                                 .where(FixtureProfile.short_name == short)
                                 ).scalars().first()
                if prof is not None:
                    s.delete(prof)
            s.commit()
        ensure_builtins()
        with Session(self._eng) as s:
            for short in shorts:
                self.assertIsNotNone(_load_short(s, short), short)


if __name__ == "__main__":
    unittest.main()
