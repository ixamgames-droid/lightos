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
        ch2 = modes["2-Kanal (Nebel + Lüfter)"].channels
        self.assertEqual([c.name for c in ch2], ["Nebel", "Lüfter"])

    def test_idempotent_no_duplicate(self):
        fdb.ensure_builtins()
        fdb.ensure_builtins()
        with Session(fdb.engine()) as s:
            rows = s.execute(select(FixtureProfile).where(
                FixtureProfile.short_name == "EURON10")).scalars().all()
            self.assertEqual(len(rows), 1, "EURON10 wurde dupliziert")


if __name__ == "__main__":
    unittest.main()
