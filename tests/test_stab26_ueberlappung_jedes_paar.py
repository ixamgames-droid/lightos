"""STAB-26: die Adress-Pruefung findet JEDES ueberlappende Paar.

Bis 2026-09-29 verglich Check 5 von ``validate_and_repair`` nur Nachbarn in
Adress-Reihenfolge: ein Geraet, das komplett in einem langen Bereich lag,
verschwand hinter seinem Nachbarn (A 1-100, B 10-12, C 20-22 -> nur A/B).
Echter Patch ueber den AppState (eingebautes Profil, QA-23).
"""
import os
import re
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from sqlalchemy import select                                    # noqa: E402
from sqlalchemy.orm import Session                               # noqa: E402

from src.core.app_state import get_state                         # noqa: E402
from src.core.database.fixture_db import engine as fdb_engine    # noqa: E402
from src.core.database.models import FixtureProfile, PatchedFixture  # noqa: E402
from src.core.show.show_file import reset_show                   # noqa: E402
from src.core.sync import validate_and_repair                    # noqa: E402


def _pid(short):
    with Session(fdb_engine()) as s:
        return int(s.execute(select(FixtureProfile.id).where(
            FixtureProfile.short_name == short)).scalars().first())


class JedesPaarTest(unittest.TestCase):

    def setUp(self):
        reset_show()
        self.st = get_state()
        self.pid = _pid("ZQ01424")

    def _patch(self, fid, adresse, kanaele, universe=1):
        self.st.add_fixture(PatchedFixture(
            fid=fid, label=f"G{fid}", fixture_profile_id=self.pid,
            mode_name="8-Kanal RGBW", universe=universe, address=adresse,
            channel_count=kanaele), undoable=False)

    def _paare(self):
        out = set()
        for i in validate_and_repair(self.st, fix=False):
            if "Adresskonflikt" in i.message:
                out.add(tuple(sorted(int(x) for x in re.findall(r"fid (\d+)", i.message))))
        return out

    def test_geraet_im_langen_bereich_wird_gefunden(self):
        self._patch(1, 1, 100)
        self._patch(2, 10, 3)
        self._patch(3, 20, 3)
        self.assertEqual(self._paare(), {(1, 2), (1, 3)})

    def test_kette_von_drei(self):
        self._patch(1, 1, 10)
        self._patch(2, 5, 10)
        self._patch(3, 12, 5)
        self.assertEqual(self._paare(), {(1, 2), (2, 3)})

    def test_sauberer_patch_meldet_nichts(self):
        """Positivkontrolle: dicht an dicht, und dieselbe Adresse in einem
        anderen Universe."""
        self._patch(1, 1, 8)
        self._patch(2, 9, 8)
        self._patch(3, 17, 8)
        self._patch(4, 1, 8, universe=2)
        self.assertEqual(self._paare(), set())


if __name__ == "__main__":
    unittest.main()
