"""Bus-synchrones Stepping von Chaser/Sequence — Tempo-Sync-Korrektheit (Bug-Hunt).

Drei bestaetigte Defekte im ``_advance_from_bus`` / ``_bus_steps_to_advance``-Pfad:
- F5: eine LIVE-Aenderung von tempo_multiplier ankerte nicht neu -> der neue Faktor
  skalierte die ganze seit dem Anker verstrichene Beat-Distanz rueckwirkend
  -> Step-Burst (Loop) bzw. vorzeitiger, stiller Stopp (SingleShot).
- F7: ein negativer tempo_multiplier (hand-editierte Show, umgeht den set_param-Clamp)
  liess das target monoton fallen -> der Effekt fror dauerhaft ein.
- F8: phase_offset ("Tempo-Versatz") floss NICHT in die target-Rechnung -> der
  beworbene Parameter war fuer Chaser/Sequence ein No-Op.

Getestet an der echten Engine (Bus + _advance_from_bus), Rendering ausgeklammert.
Jeder Test faellt auf dem alten Code durch.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.engine.chaser import Chaser, ChaserStep
from src.core.engine.function import RunOrder
from src.core.engine.tempo_bus import get_tempo_bus_manager, reset_tempo_bus_manager


class _BusChaserTest(unittest.TestCase):
    def setUp(self):
        reset_tempo_bus_manager()
        self.tbm = get_tempo_bus_manager()
        self.tbm.resolve("A").set_bpm(120)     # 120 BPM -> 2 Beats/s

    def tearDown(self):
        reset_tempo_bus_manager()

    def _chaser(self, run_order=RunOrder.Loop, n=8, phase_offset=0.0):
        c = Chaser("T")
        c.steps = [ChaserStep(function_id=i + 1) for i in range(n)]
        c.run_order = run_order
        c.tempo_bus_id = "A"
        c.phase_offset = phase_offset
        c.align_on_start = False               # auf aktuelle Bus-Position ankern (deterministisch)
        c._render_and_blend = lambda *a, **k: None
        c._elapsed = 0.0
        c._running = True
        c._on_start()
        return c

    def _drive(self, c, frames, dt):
        for _ in range(frames):
            self.tbm.advance_frame(dt)
            c._advance_from_bus(None, None, None, dt)


class LiveMultiplierReanchorTest(_BusChaserTest):
    def test_loop_no_step_burst_on_multiplier_raise(self):
        c = self._chaser(RunOrder.Loop, n=8)
        self._drive(c, frames=6, dt=0.25)      # 3 Beats -> step_idx = 3
        idx_before = c._step_idx
        self.assertGreater(idx_before, 0)      # der Chaser lief wirklich an
        c.set_param("tempo_multiplier", 2.0)   # LIVE-Rate-Aenderung -> re-ankern (F5)
        c._advance_from_bus(None, None, None, 0.01)   # KEIN Bus-Vorlauf -> kein Burst
        self.assertEqual(c._step_idx, idx_before)

    def test_singleshot_not_stopped_early_on_multiplier_raise(self):
        c = self._chaser(RunOrder.SingleShot, n=5)
        self._drive(c, frames=2, dt=0.25)      # 1 Beat -> step_idx = 1
        self.assertEqual(c._step_idx, 1)
        self.assertTrue(c._running)
        c.set_param("tempo_multiplier", 8.0)   # ohne Re-Anker haette das bis ans Ende gesprengt
        c._advance_from_bus(None, None, None, 0.01)
        self.assertTrue(c._running)            # NICHT vorzeitig gestoppt
        self.assertEqual(c._step_idx, 1)


class NegativeMultiplierTest(_BusChaserTest):
    def test_negative_multiplier_does_not_freeze(self):
        c = self._chaser(RunOrder.Loop, n=8)
        c.tempo_multiplier = -1.0              # korrupt/hand-editiert (umgeht set_param-Clamp)
        self._drive(c, frames=8, dt=0.25)      # 4 Beats
        self.assertGreater(c._step_idx, 0)     # laeuft weiter statt einzufrieren


class PhaseOffsetStaggerTest(_BusChaserTest):
    def test_phase_offset_staggers_stepping(self):
        cA = self._chaser(RunOrder.Loop, n=8, phase_offset=0.0)
        cB = self._chaser(RunOrder.Loop, n=8, phase_offset=0.5)
        hist = []
        for _ in range(8):
            self.tbm.advance_frame(0.1)        # 0.2 Beat/Frame
            cA._advance_from_bus(None, None, None, 0.1)
            cB._advance_from_bus(None, None, None, 0.1)
            hist.append((cA._step_idx, cB._step_idx))
        # Mit Versatz erreicht B seine Schritte frueher als A -> mind. 1 Frame b>a.
        self.assertTrue(any(b > a for a, b in hist),
                        f"phase_offset ohne Wirkung (No-Op): {hist}")


if __name__ == "__main__":
    unittest.main()
