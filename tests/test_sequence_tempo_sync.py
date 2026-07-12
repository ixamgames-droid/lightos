"""Bus-synchrones Stepping der Sequence — Tempo-Sync-Korrektheit (Bug-Hunt).

Spiegelt tests/test_chaser_tempo_sync.py: dieselben drei Defekte (F5 Re-Anker bei
Live-tempo_multiplier, F7 negativer Multiplier friert ein, F8 phase_offset-No-Op)
existierten identisch in Sequence._bus_steps_to_advance. Getestet ueber die reine
Advance-Zaehlung (ohne Rendering).
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.engine.sequence import Sequence, SequenceStep
from src.core.engine.function import RunOrder
from src.core.engine.tempo_bus import get_tempo_bus_manager, reset_tempo_bus_manager


class _BusSeqTest(unittest.TestCase):
    def setUp(self):
        reset_tempo_bus_manager()
        self.tbm = get_tempo_bus_manager()
        self.tbm.resolve("A").set_bpm(120)

    def tearDown(self):
        reset_tempo_bus_manager()

    def _seq(self, n=8, phase_offset=0.0):
        s = Sequence("T")
        s.steps = [SequenceStep(values={}) for _ in range(n)]
        s.run_order = RunOrder.Loop
        s.tempo_bus_id = "A"
        s.phase_offset = phase_offset
        s.align_on_start = False
        s._running = True
        s._on_start()
        return s

    def _advance_total(self, s, frames, dt):
        total = 0
        for _ in range(frames):
            self.tbm.advance_frame(dt)
            total += (s._bus_steps_to_advance() or 0)
        return total

    def test_no_step_burst_on_multiplier_raise(self):
        s = self._seq(n=8)
        self.assertGreater(self._advance_total(s, 6, 0.25), 0)   # 3 Beats gelaufen
        s.set_param("tempo_multiplier", 2.0)                     # re-ankern (F5)
        self.assertEqual(s._bus_steps_to_advance() or 0, 0)      # kein Burst ohne Bus-Vorlauf

    def test_negative_multiplier_does_not_freeze(self):
        s = self._seq(n=8)
        s.tempo_multiplier = -1.0                               # umgeht set_param-Clamp
        self.assertGreater(self._advance_total(s, 8, 0.25), 0)  # laeuft (F7)

    def test_phase_offset_staggers_stepping(self):
        sA = self._seq(n=8, phase_offset=0.0)
        sB = self._seq(n=8, phase_offset=0.5)
        idx_a = idx_b = 0
        staggered = False
        for _ in range(8):
            self.tbm.advance_frame(0.1)
            idx_a += (sA._bus_steps_to_advance() or 0)
            idx_b += (sB._bus_steps_to_advance() or 0)
            if idx_b > idx_a:
                staggered = True
        self.assertTrue(staggered, "phase_offset ohne Wirkung (No-Op)")


if __name__ == "__main__":
    unittest.main()
