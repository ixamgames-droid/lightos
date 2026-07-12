"""Snapshot.from_dict: ein einzelner kaputter Kanalwert darf nicht das ganze
Fixture verwerfen (STAB-18 Verlust-Amplifikation, Bug-Hunt 2026-07-12).

Vorher baute from_dict das Attribut-Dict eines Fixtures in EINER Comprehension
innerhalb eines einzigen try/except. Scheiterte ein int(av) (None/Liste/nicht-
numerisch aus hand-editiertem oder importiertem JSON), verwarf das except das
GANZE Fixture inkl. aller gueltigen Kanaele. Jetzt wird pro Wert isoliert — nur
der kaputte Kanal faellt weg, der Rest des Fixtures bleibt (analog zum Programmer-
Loader in show_file.py und snap_library._clean_values).
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.ui.views.snapshots_view import Snapshot


class SnapshotValueIsolationTest(unittest.TestCase):
    def test_bad_value_only_drops_that_channel(self):
        snap = Snapshot.from_dict({
            "name": "x",
            "values": {
                "1": {"intensity": 200, "color_r": None, "color_g": 120},
                "2": {"pan": 128},
            },
        })
        # Fixture 1 behaelt seine gueltigen Kanaele; nur color_r (None) faellt weg.
        self.assertEqual(snap.values, {1: {"intensity": 200, "color_g": 120},
                                       2: {"pan": 128}})

    def test_non_numeric_string_dropped_per_channel(self):
        snap = Snapshot.from_dict({
            "values": {"5": {"tilt": "abc", "gobo": 30}},
        })
        self.assertEqual(snap.values, {5: {"gobo": 30}})

    def test_bad_fid_skipped_others_kept(self):
        snap = Snapshot.from_dict({
            "values": {"nope": {"intensity": 10}, "3": {"intensity": 40}},
        })
        self.assertEqual(snap.values, {3: {"intensity": 40}})

    def test_non_dict_fixture_skipped(self):
        snap = Snapshot.from_dict({"values": {"1": "garbage", "2": {"pan": 7}}})
        self.assertEqual(snap.values, {2: {"pan": 7}})

    def test_clean_roundtrip_preserved(self):
        original = {1: {"intensity": 255, "color_b": 10}, 2: {"pan": 128, "tilt": 200}}
        snap = Snapshot(name="rt", values=original)
        restored = Snapshot.from_dict(snap.to_dict())
        self.assertEqual(restored.values, original)


if __name__ == "__main__":
    unittest.main()
