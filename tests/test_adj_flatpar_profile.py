"""Tests fuer das ADJ Flat Par QWH12X Profil (12x5W RGBW, Art.-Nr. 1226100244,
2026-06-25). Faithful aus dem ADJ-Handbuch der baugleichen QA12X-Serie.

Abgedeckt:
- Profil existiert, Typ "par", Hersteller "ADJ".
- Modi 4/5/7/8-Kanal mit korrektem Attribut-Layout (Reihenfolge laut Handbuch).
- Strobe 0 = offen (Default) -> Geraet leuchtet; Strobe-Ranges/kinds.
- Farb-Makro-Slots (color_wheel) inkl. RGBW-Makro (Amber->Weiss).
- ensure_builtins() ruestet das Profil in einer bestehenden DB nach (idempotent).
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


def _load(s, short="FPQWH12X"):
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


def _mode(prof, name):
    return next(m for m in prof.modes if m.name == name)


def _attrs(mode):
    return [c.attribute for c in sorted(mode.channels,
                                        key=lambda c: c.channel_number)]


class FlatParProfileTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._FDB, cls._eng, cls._saved = _temp_seeded_engine()

    @classmethod
    def tearDownClass(cls):
        cls._FDB._engine = cls._saved

    def test_existiert_und_typ(self):
        with Session(self._eng) as s:
            prof = _load(s)
            self.assertIsNotNone(prof, "Flat Par muss geseedet sein")
            self.assertEqual(prof.fixture_type, "par")
            self.assertEqual(prof.manufacturer.name, "ADJ")
            self.assertEqual(prof.name, "Flat Par QWH12X")
            self.assertEqual({m.name for m in prof.modes}, {
                "4-Kanal RGBW", "5-Kanal RGBW + Dimmer",
                "7-Kanal RGBW + Strobe", "8-Kanal Voll"})

    def test_layouts(self):
        with Session(self._eng) as s:
            prof = _load(s)
            self.assertEqual(_attrs(_mode(prof, "4-Kanal RGBW")),
                             ["color_r", "color_g", "color_b", "color_w"])
            self.assertEqual(_attrs(_mode(prof, "5-Kanal RGBW + Dimmer")),
                             ["color_r", "color_g", "color_b", "color_w",
                              "intensity"])
            self.assertEqual(_attrs(_mode(prof, "7-Kanal RGBW + Strobe")),
                             ["color_r", "color_g", "color_b", "color_w",
                              "intensity", "shutter", "color_wheel"])
            self.assertEqual(_attrs(_mode(prof, "8-Kanal Voll")),
                             ["color_r", "color_g", "color_b", "color_w",
                              "intensity", "shutter", "macro", "color_wheel"])

    def test_channel_count_matcht_modus(self):
        with Session(self._eng) as s:
            prof = _load(s)
            for name, n in (("4-Kanal RGBW", 4), ("5-Kanal RGBW + Dimmer", 5),
                            ("7-Kanal RGBW + Strobe", 7), ("8-Kanal Voll", 8)):
                m = _mode(prof, name)
                self.assertEqual(m.channel_count, n, name)
                self.assertEqual(len(m.channels), n, name)

    def test_strobe_offen_default_und_ranges(self):
        with Session(self._eng) as s:
            sh = next(c for c in _mode(_load(s), "7-Kanal RGBW + Strobe").channels
                      if c.attribute == "shutter")
            self.assertEqual(sh.default_value, 0, "Default offen -> leuchtet")
            ranges = {(r.range_from, r.range_to): r.kind for r in sh.ranges}
        self.assertEqual(ranges[(0, 15)], "open")
        self.assertEqual(ranges[(16, 255)], "strobe")

    def test_farb_makros_rgbw(self):
        with Session(self._eng) as s:
            cw = next(c for c in _mode(_load(s), "7-Kanal RGBW + Strobe").channels
                      if c.attribute == "color_wheel")
            slots = {(r.range_from, r.range_to): (r.name, r.kind)
                     for r in cw.ranges}
        self.assertEqual(slots[(0, 15)], ("Aus", "open"))
        self.assertEqual(slots[(64, 79)], ("Weiß", "color"))   # Amber->Weiss
        self.assertEqual(slots[(240, 255)],
                         ("Rot + Grün + Blau + Weiß", "color"))


class EnsureBuiltinsFlatParTest(unittest.TestCase):
    def setUp(self):
        self._FDB, self._eng, self._saved = _temp_seeded_engine()

    def tearDown(self):
        self._FDB._engine = self._saved

    def _delete(self):
        from src.core.database.models import FixtureProfile
        with Session(self._eng) as s:
            prof = s.execute(select(FixtureProfile)
                             .where(FixtureProfile.short_name == "FPQWH12X")
                             ).scalars().first()
            if prof is not None:
                s.delete(prof)
                s.commit()

    def test_nachruesten_wenn_fehlt(self):
        from src.core.database.fixture_db import ensure_builtins
        from src.core.database.models import FixtureProfile
        self._delete()
        with Session(self._eng) as s:
            self.assertIsNone(s.execute(select(FixtureProfile)
                              .where(FixtureProfile.short_name == "FPQWH12X")
                              ).scalars().first())
        ensure_builtins()
        with Session(self._eng) as s:
            prof = _load(s)
            self.assertIsNotNone(prof, "ensure_builtins muss Flat Par anlegen")
            self.assertEqual(len(prof.modes), 4)
            self.assertEqual(prof.manufacturer.name, "ADJ")

    def test_idempotent_kein_duplikat(self):
        from src.core.database.fixture_db import ensure_builtins
        from src.core.database.models import FixtureProfile
        ensure_builtins()
        ensure_builtins()
        with Session(self._eng) as s:
            n = len(s.execute(select(FixtureProfile)
                    .where(FixtureProfile.short_name == "FPQWH12X")
                    ).scalars().all())
        self.assertEqual(n, 1, "kein Duplikat durch wiederholtes ensure_builtins")


if __name__ == "__main__":
    unittest.main()
