"""Pan/Tilt-Bereich + Nullpunkt pro Fixture: Serialisierung round-trips,
Alt-Shows ohne die Felder bekommen sinnvolle Defaults (540/270/128/128).
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.show.show_file import _fixture_to_dict, _patched_fixture_from_data
from src.core.database.models import PatchedFixture


class PanTiltRangePersistTest(unittest.TestCase):
    def test_roundtrip_object(self):
        f = PatchedFixture(
            fid=1, label="MH", fixture_profile_id=0, mode_name="m",
            universe=1, address=1, channel_count=14,
            pan_range_deg=540, tilt_range_deg=270,
            pan_zero_dmx=120, tilt_zero_dmx=130,
        )
        d = _fixture_to_dict(f)
        self.assertEqual(d["pan_range_deg"], 540)
        self.assertEqual(d["tilt_range_deg"], 270)
        self.assertEqual(d["pan_zero_dmx"], 120)
        self.assertEqual(d["tilt_zero_dmx"], 130)
        f2 = _patched_fixture_from_data(d, 1)
        self.assertEqual(f2.pan_range_deg, 540)
        self.assertEqual(f2.tilt_range_deg, 270)
        self.assertEqual(f2.pan_zero_dmx, 120)
        self.assertEqual(f2.tilt_zero_dmx, 130)

    def test_legacy_dict_gets_defaults(self):
        """Alt-Show ohne die Felder -> 540/270/128/128."""
        f = _patched_fixture_from_data(
            {"fid": 2, "address": 1, "channel_count": 1}, 2)
        self.assertEqual(f.pan_range_deg, 540)
        self.assertEqual(f.tilt_range_deg, 270)
        self.assertEqual(f.pan_zero_dmx, 128)
        self.assertEqual(f.tilt_zero_dmx, 128)


if __name__ == "__main__":
    unittest.main()
