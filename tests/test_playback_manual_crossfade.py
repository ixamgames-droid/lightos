"""Manueller Crossfade auf CueStack (Playback-Tab Slider / Executor-Fader).

Der Slider scrubbt den Übergang von der aktiven zur nächsten Cue von Hand;
bei pos>=1.0 wird der Übergang übernommen (Zielcue wird aktiv) und True
zurückgegeben, damit die UI ihren Fader auf 0 zurücksetzen kann.
"""
import unittest

from src.core.engine.cue_stack import CueStack
from src.core.engine.cue import Cue


def _stack(n=3, mode="single"):
    s = CueStack("t")
    s.mode = mode
    vals = [0, 255, 100]
    for i in range(n):
        s.add_cue(Cue(number=i + 1, values={1: {"intensity": vals[i % len(vals)]}}))
    return s


class ManualCrossfadeTest(unittest.TestCase):
    def setUp(self):
        self.s = _stack()
        self.s.go()          # Cue 1 aktiv
        # Output materialisieren (sonst from_vals leer)
        for _ in range(60):
            self.s.tick()

    def test_halfway_blends(self):
        self.assertFalse(self.s.manual_crossfade(0.5))   # noch nicht übernommen
        self.assertEqual(self.s.get_output()[1]["intensity"], 127)
        # aktive Cue darf sich erst beim Übernehmen ändern
        self.assertEqual(self.s.current_index, 0)

    def test_scrub_back_and_forth(self):
        self.s.manual_crossfade(0.9)
        self.s.manual_crossfade(0.1)
        self.assertLess(self.s.get_output()[1]["intensity"], 60)
        self.assertEqual(self.s.current_index, 0)

    def test_commit_advances_and_returns_true(self):
        self.assertTrue(self.s.manual_crossfade(1.0))
        self.assertEqual(self.s.current_index, 1)
        self.assertEqual(self.s.get_output()[1]["intensity"], 255)

    def test_pos_zero_does_not_arm(self):
        # Fader bei 0 darf keinen Fade armieren
        self.assertFalse(self.s.manual_crossfade(0.0))
        self.assertEqual(self.s.current_index, 0)

    def test_tick_does_not_autoadvance_manual(self):
        self.s.manual_crossfade(0.4)
        before = self.s.get_output()[1]["intensity"]
        for _ in range(60):
            self.s.tick()        # Zeit vergeht – manueller Fade darf NICHT laufen
        self.assertEqual(self.s.get_output()[1]["intensity"], before)
        self.assertEqual(self.s.current_index, 0)

    def test_empty_stack_safe(self):
        s = CueStack("leer")
        self.assertFalse(s.manual_crossfade(0.5))
        self.assertFalse(s.manual_crossfade(1.0))

    def test_single_mode_at_end_no_target(self):
        # Bis ans Ende gehen, dann kann kein manueller Crossfade mehr armieren.
        self.s.go(); self.s.go()                 # auf letzte Cue
        self.assertEqual(self.s.current_index, 2)
        self.assertFalse(self.s.manual_crossfade(0.5))

    def test_loop_mode_wraps_via_crossfade(self):
        s = _stack(mode="loop")
        s.go(); s.go(); s.go()                    # auf letzte Cue (idx 2)
        self.assertEqual(s.current_index, 2)
        for _ in range(60):
            s.tick()
        self.assertTrue(s.manual_crossfade(1.0))  # wrap -> Cue 1
        self.assertEqual(s.current_index, 0)

    def test_go_sequences_unchanged(self):
        # Sicherheitsnetz: der _peek_next-Helfer darf go() nicht verändert haben.
        s = _stack(mode="bounce")
        seq = []
        for _ in range(7):
            s.go(); seq.append(s.current_index)
        self.assertEqual(seq, [0, 1, 2, 1, 0, 1, 2])


if __name__ == "__main__":
    unittest.main()
