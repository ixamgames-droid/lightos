"""F-7: CueStack-Ablauf-Modi (Einzel/Loop/Bounce/Ping-Pong)."""
import unittest

from src.core.engine.cue_stack import CueStack
from src.core.engine.cue import Cue


def _stack(mode, n=3):
    s = CueStack("t")
    s.mode = mode
    for i in range(n):
        s.add_cue(Cue(number=i + 1, values={1: {"intensity": 255}}))
    return s


def _seq(stack, steps):
    out = []
    for _ in range(steps):
        stack.go()
        out.append(stack.current_index)
    return out


class CueStackModeTest(unittest.TestCase):
    def test_single_stops_at_end(self):
        s = _stack("single")
        self.assertEqual(_seq(s, 5), [0, 1, 2, 2, 2])   # bleibt am Ende stehen

    def test_loop_wraps(self):
        s = _stack("loop")
        self.assertEqual(_seq(s, 5), [0, 1, 2, 0, 1])

    def test_bounce_reflects(self):
        s = _stack("bounce")
        # 0,1,2 -> umkehren -> 1,0 -> umkehren -> 1,2 ...
        self.assertEqual(_seq(s, 7), [0, 1, 2, 1, 0, 1, 2])

    def test_pingpong_like_bounce(self):
        s = _stack("pingpong")
        self.assertEqual(_seq(s, 5), [0, 1, 2, 1, 0])

    def test_loop_property_backcompat(self):
        s = _stack("single")
        self.assertFalse(s.loop)
        s.loop = True
        self.assertEqual(s.mode, "loop")
        self.assertTrue(s.loop)
        s.loop = False
        self.assertEqual(s.mode, "single")
        # loop=True überschreibt bounce NICHT
        s.mode = "bounce"
        s.loop = True
        self.assertEqual(s.mode, "bounce")

    def test_serialization_roundtrip(self):
        s = _stack("bounce")
        d = s.to_dict()
        self.assertEqual(d["mode"], "bounce")
        self.assertTrue(d["loop"])                      # Alt-Leser-Kompatibilität
        s2 = CueStack.from_dict(d)
        self.assertEqual(s2.mode, "bounce")

    def test_from_dict_legacy_loop_only(self):
        s = CueStack.from_dict({"name": "x", "loop": True, "cues": []})
        self.assertEqual(s.mode, "loop")
        s2 = CueStack.from_dict({"name": "x", "loop": False, "cues": []})
        self.assertEqual(s2.mode, "single")

    def test_stop_resets_direction(self):
        s = _stack("bounce")
        _seq(s, 4)                # bis zur Umkehr
        s.stop()
        self.assertEqual(s.current_index, -1)
        self.assertEqual(_seq(s, 3), [0, 1, 2])   # nach stop wieder vorwärts


if __name__ == "__main__":
    unittest.main()
