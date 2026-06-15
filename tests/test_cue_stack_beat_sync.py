"""Beat-Sync für Cuelisten: CueStack.on_beat schaltet taktgenau (alle N Beats),
unterdrückt den Zeit-Follow-Timer und serialisiert seine Felder. Alt-Shows = aus."""
import unittest

from src.core.engine.cue_stack import CueStack
from src.core.engine.cue import Cue


def _stack(n=3, beat_sync=True, per=2, mode="loop", follow=None):
    s = CueStack("t")
    s.mode = mode
    s.beat_sync = beat_sync
    s.beats_per_cue = per
    for i in range(n):
        s.add_cue(Cue(number=i + 1, follow=follow, values={1: {"intensity": 255}}))
    return s


class CueStackBeatSyncTest(unittest.TestCase):
    def test_advances_every_n_beats(self):
        s = _stack(n=3, per=2)
        s.go()                          # -> Cue 0
        self.assertEqual(s.current_index, 0)
        s.on_beat()                     # 1 < 2 -> hält
        self.assertEqual(s.current_index, 0)
        s.on_beat()                     # 2 -> weiter
        self.assertEqual(s.current_index, 1)
        s.on_beat(); s.on_beat()        # wieder 2 Beats -> weiter
        self.assertEqual(s.current_index, 2)
        s.stop()

    def test_noop_when_not_running(self):
        s = _stack()
        for _ in range(10):             # kein GO -> nichts passiert
            s.on_beat()
        self.assertEqual(s.current_index, -1)

    def test_noop_when_disabled(self):
        s = _stack(beat_sync=False, per=1)
        s.go()
        idx = s.current_index
        for _ in range(5):
            s.on_beat()
        self.assertEqual(s.current_index, idx)   # ohne beat_sync kein Advance
        s.stop()

    def test_beat_sync_suppresses_follow_timer(self):
        s = _stack(per=2, follow=0.01)
        s.go()
        self.assertIsNone(s._follow_timer)       # Beat treibt, kein Zeit-Follow
        s.stop()

    def test_time_follow_still_armed_without_beat_sync(self):
        s = _stack(beat_sync=False, follow=0.0)
        s.go()
        self.assertIsNotNone(s._follow_timer)    # Zeit-Follow weiterhin aktiv
        s._cancel_follow()
        s.stop()

    def test_serialization_roundtrip(self):
        s = _stack(per=4)
        d = s.to_dict()
        self.assertTrue(d["beat_sync"])
        self.assertEqual(d["beats_per_cue"], 4)
        s2 = CueStack.from_dict(d)
        self.assertTrue(s2.beat_sync)
        self.assertEqual(s2.beats_per_cue, 4)

    def test_legacy_defaults_off(self):
        s2 = CueStack.from_dict({"name": "x", "loop": True, "cues": []})
        self.assertFalse(s2.beat_sync)
        self.assertEqual(s2.beats_per_cue, 4)


if __name__ == "__main__":
    unittest.main()
