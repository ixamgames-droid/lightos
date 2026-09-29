"""STAB-27: doppelte Geraete-Nummer (fid) in einer Show-Datei.

Der Loader nummerierte das zweite Geraet schon um, aber still — und die neue
Nummer konnte mit einem Geraet kollidieren, das weiter unten in der Datei
steht: bei [1, 1, 2] bekam das Duplikat die 2, das echte Geraet 2 wurde
seinerseits umnummeriert, und dessen Programmer-Werte, 3D-Position und
Gruppen landeten auf dem falschen Geraet. Echter Speicher- und Ladeweg.
"""
import json
import os
import tempfile
import unittest
import zipfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from sqlalchemy import select                                    # noqa: E402
from sqlalchemy.orm import Session                               # noqa: E402

from src.core.app_state import get_state                         # noqa: E402
from src.core.database.fixture_db import engine as fdb_engine    # noqa: E402
from src.core.database.models import FixtureProfile, PatchedFixture  # noqa: E402
from src.core.show.show_file import (letzte_ladeprobleme, load_show,  # noqa: E402
                                     reset_show, save_show)


def _pid(short):
    with Session(fdb_engine()) as s:
        return int(s.execute(select(FixtureProfile.id).where(
            FixtureProfile.short_name == short)).scalars().first())


class DoppelteFidTest(unittest.TestCase):

    def setUp(self):
        reset_show()
        self.st = get_state()
        pid = _pid("ZQ01424")
        for fid, label, adr in ((1, "A", 1), (2, "B", 9), (3, "C", 17)):
            self.st.add_fixture(PatchedFixture(
                fid=fid, label=label, fixture_profile_id=pid, mode_name="8-Kanal RGBW",
                universe=1, address=adr, channel_count=8), undoable=False)
        self.st.set_programmer_value(2, "intensity", 222)
        d = tempfile.mkdtemp()
        self.pfad = os.path.join(d, "doppelt.lshow")
        save_show(self.pfad)
        self._patch_bearbeiten(lambda patch: [
            dict(e, fid=1) if e["label"] == "C" else e for e in patch])

    def _patch_bearbeiten(self, fn):
        with zipfile.ZipFile(self.pfad) as z:
            namen = z.namelist()
            inhalt = {n: z.read(n) for n in namen}
        data = json.loads(inhalt["show.json"])
        # Reihenfolge wie im Befund: A(1), C(jetzt 1), B(2)
        patch = fn(data["patch"])
        patch.sort(key=lambda e: {"A": 0, "C": 1, "B": 2}[e["label"]])
        data["patch"] = patch
        inhalt["show.json"] = json.dumps(data).encode()
        with zipfile.ZipFile(self.pfad, "w") as z:
            for n, b in inhalt.items():
                z.writestr(n, b)

    def test_echtes_geraet_behaelt_seine_nummer_und_werte(self):
        reset_show()
        load_show(self.pfad)
        st = get_state()
        nach_label = {f.label: f.fid for f in st.get_patched_fixtures()}
        self.assertEqual(nach_label["A"], 1)
        self.assertEqual(nach_label["B"], 2, "das echte Geraet 2 bleibt 2")
        self.assertNotIn(nach_label["C"], (1, 2))
        self.assertEqual(st.programmer.get(2, {}).get("intensity"), 222,
                         "Werte von 2 bleiben bei B")
        self.assertNotIn(nach_label["C"], st.programmer)

    def test_wird_gemeldet(self):
        reset_show()
        load_show(self.pfad)
        meldungen = [m for m in letzte_ladeprobleme() if "Doppelte Geräte-Nummer" in m]
        self.assertEqual(len(meldungen), 1, letzte_ladeprobleme())
        self.assertIn("„C“", meldungen[0])
        self.assertIn("„A“", meldungen[0])

    def test_saubere_datei_meldet_nichts(self):
        self._patch_bearbeiten(lambda patch: [
            dict(e, fid=3) if e["label"] == "C" else e for e in patch])
        reset_show()
        load_show(self.pfad)
        self.assertFalse([m for m in letzte_ladeprobleme() if "Doppelte" in m])
        self.assertEqual(sorted(f.fid for f in get_state().get_patched_fixtures()), [1, 2, 3])


if __name__ == "__main__":
    unittest.main()
