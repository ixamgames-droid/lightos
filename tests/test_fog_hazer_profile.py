"""FIX-FOG: eingebautes Nebel-/Hazer-Profil (Eurolite N-10, EURON10).

Vor dem Fix hatte die Library PAR/MH/Spider/Laser, aber KEINE Nebelmaschine —
eine Fog-/Smoke-Maschine liess sich nur ueber ein selbst angelegtes Profil
patchen (UXTEST-3-Audit). Jetzt ist sie ein Builtin (Seed + Migration).
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from src.core.database import fixture_db as fdb
from src.core.database.models import FixtureProfile, FixtureMode


def _profile():
    fdb.ensure_builtins()
    with Session(fdb.engine()) as s:
        return s.execute(
            select(FixtureProfile)
            .options(selectinload(FixtureProfile.modes).selectinload(FixtureMode.channels))
            .where(FixtureProfile.short_name == "EURON10")
        ).scalars().first()


class TestFogHazerBuiltin(unittest.TestCase):
    def test_seeded_as_hazer(self):
        prof = _profile()
        self.assertIsNotNone(prof, "EURON10-Builtin fehlt nach ensure_builtins")
        self.assertEqual(prof.fixture_type, "hazer")
        self.assertEqual(prof.source, "builtin")

    def test_modes_and_fog_channel(self):
        prof = _profile()
        modes = {m.name: m for m in prof.modes}
        self.assertIn("1-Kanal (Nebel)", modes)
        self.assertIn("2-Kanal (Nebel + Lüfter)", modes)
        ch = modes["1-Kanal (Nebel)"].channels
        self.assertEqual(len(ch), 1)
        # der Nebel-Ausstoss ist ein Intensitaets-Kanal (GM/Blackout skalieren mit)
        self.assertEqual(ch[0].attribute, "dimmer")
        self.assertEqual(ch[0].name, "Nebel")
        # 2-Kanal-Modus hat zusaetzlich den Luefter
        ch2 = sorted(modes["2-Kanal (Nebel + Lüfter)"].channels, key=lambda c: c.channel_number)
        self.assertEqual([c.name for c in ch2], ["Nebel", "Lüfter"])

    def test_luefter_has_distinct_fan_attribute(self):
        # CDX-07: Nebel + Lüfter MUESSEN unterschiedliche Attribute haben, sonst
        # dedupliziert der Programmer (Slider pro Attribut) sie zu EINEM Regler und
        # der Lüfter spiegelt still den Nebelwert (nicht getrennt steuerbar).
        prof = _profile()
        m2 = {m.name: m for m in prof.modes}["2-Kanal (Nebel + Lüfter)"]
        chans = sorted(m2.channels, key=lambda c: c.channel_number)
        attrs = [c.attribute for c in chans]
        self.assertEqual(attrs, ["dimmer", "fan"])
        self.assertEqual(len(set(attrs)), 2, "Nebel + Lüfter haben dasselbe Attribut (Dedup-Falle)")

    def test_fan_attribute_registered_in_attr_groups(self):
        from src.core import attr_groups as ag
        # `fan` ist ein bekanntes Attribut (bekommt einen eigenen Regler) und liegt
        # in Effect, NICHT Intensity -> wird NICHT vom Grand-Master/Blackout skaliert.
        self.assertIn("fan", ag.ATTR_GROUPS["Effect"])
        self.assertNotIn("fan", ag.ATTR_GROUPS["Intensity"])
        self.assertEqual(ag.ATTR_LABELS.get("fan"), "Lüfter")

    def test_migration_repairs_old_dimmer_luefter(self):
        # Alt-Zustand simulieren (Vor-CDX-07: Lüfter = `dimmer`), dann muss
        # ensure_builtins() den 2-Kanal-Modus in-place auf `fan` reparieren.
        fdb.ensure_builtins()
        with Session(fdb.engine()) as s:
            prof = s.execute(
                select(FixtureProfile)
                .options(selectinload(FixtureProfile.modes).selectinload(FixtureMode.channels))
                .where(FixtureProfile.short_name == "EURON10")).scalars().first()
            for m in prof.modes:
                if m.name.startswith("2-Kanal"):
                    for c in m.channels:
                        if c.name == "Lüfter":
                            c.attribute = "dimmer"      # zurueck auf den Bug-Stand
            s.commit()
        fdb.ensure_builtins()                            # Migration
        prof = _profile()
        m2 = {m.name: m for m in prof.modes}["2-Kanal (Nebel + Lüfter)"]
        attrs = [c.attribute for c in sorted(m2.channels, key=lambda c: c.channel_number)]
        self.assertEqual(attrs, ["dimmer", "fan"], "Migration hat den Lüfter nicht auf `fan` repariert")

    def test_idempotent_no_duplicate(self):
        fdb.ensure_builtins()
        fdb.ensure_builtins()
        with Session(fdb.engine()) as s:
            rows = s.execute(select(FixtureProfile).where(
                FixtureProfile.short_name == "EURON10")).scalars().all()
            self.assertEqual(len(rows), 1, "EURON10 wurde dupliziert")


if __name__ == "__main__":
    unittest.main()
