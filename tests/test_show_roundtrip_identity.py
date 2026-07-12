"""STAB-10: .lshow-Round-Trip-Identitaet der Fixture-Serialisierung.

Verifizierte Drift: der Dump (`_fixture_to_dict`) klemmte address/channel_count nur
nach unten (`max(1,…)`), der Load (`_patched_fixture_from_data`) auf [1,512]. Ein
Fixture mit address/channel_count>512 driftete deshalb still beim Save->Load->Save.
Fix = symmetrische Klemmung beim Dump. Diese Tests fangen die Drift (Fixpunkt-
Bedingung) und guarden alle committeten Shows.
"""
import json
import os
import unittest
import zipfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.show.show_file import _fixture_to_dict, _patched_fixture_from_data

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOWS_DIR = os.path.join(REPO, "shows")


def _load_dump(d, i=1):
    """dict -> PatchedFixture (Load-Klemmung) -> dict (Dump)."""
    return _fixture_to_dict(_patched_fixture_from_data(d, i))


class FixtureClampSymmetryTest(unittest.TestCase):
    def _assert_roundtrip_stable(self, d):
        """Echte Save->Load->Save-Identitaet: load∘dump ist idempotent."""
        x = _load_dump(d)
        self.assertEqual(x, _load_dump(x))
        return x

    def test_out_of_range_address_and_channelcount_clamped_on_dump(self):
        d = {"fid": 1, "universe": 1, "address": 600, "channel_count": 700,
             "fixture_type": "par"}
        dumped = _fixture_to_dict(d)
        self.assertEqual(dumped["address"], 512)          # frueher 600 (Drift)
        self.assertEqual(dumped["channel_count"], 512)    # frueher 700 (Drift)
        self._assert_roundtrip_stable(d)

    def test_negative_universe_clamped_symmetric(self):
        d = {"fid": 2, "universe": 0, "address": 1, "channel_count": 1}
        dumped = _fixture_to_dict(d)
        self.assertEqual(dumped["universe"], 1)
        self._assert_roundtrip_stable(d)

    def test_valid_fixture_values_unchanged(self):
        d = {"fid": 3, "universe": 2, "address": 100, "channel_count": 16,
             "fixture_type": "moving_head"}
        dumped = _fixture_to_dict(d)
        self.assertEqual((dumped["universe"], dumped["address"], dumped["channel_count"]),
                         (2, 100, 16))
        self._assert_roundtrip_stable(d)

    def test_object_and_dict_branches_agree(self):
        # dict-Zweig vs. Objekt-Zweig muessen dieselbe (geklemmte) Ausgabe liefern.
        d = {"fid": 4, "universe": 3, "address": 999, "channel_count": 999}
        from_dict = _fixture_to_dict(d)
        from_obj = _fixture_to_dict(_patched_fixture_from_data(d, 4))
        self.assertEqual(from_dict["address"], from_obj["address"])
        self.assertEqual(from_dict["channel_count"], from_obj["channel_count"])
        self.assertEqual(from_dict["universe"], from_obj["universe"])


class CommittedShowsRoundTripTest(unittest.TestCase):
    def _shows(self):
        if not os.path.isdir(SHOWS_DIR):
            return []
        return sorted(f for f in os.listdir(SHOWS_DIR) if f.endswith(".lshow"))

    def test_committed_show_patches_are_roundtrip_stable(self):
        shows = self._shows()
        self.assertGreater(len(shows), 0, "keine committeten Shows gefunden")
        for name in shows:
            with zipfile.ZipFile(os.path.join(SHOWS_DIR, name)) as zf:
                data = json.loads(zf.read("show.json").decode("utf-8"))
            for i, fx in enumerate(data.get("patch", []) or []):
                if not isinstance(fx, dict):
                    continue
                d1 = _load_dump(fx, i + 1)
                d2 = _load_dump(d1, i + 1)     # Fixpunkt: zweiter Durchlauf == erster
                self.assertEqual(d1, d2, f"{name}: Fixture #{i} nicht Round-Trip-stabil")
                self.assertLessEqual(d1["address"], 512)
                self.assertLessEqual(d1["channel_count"], 512)
                self.assertGreaterEqual(d1["universe"], 1)


if __name__ == "__main__":
    unittest.main()
