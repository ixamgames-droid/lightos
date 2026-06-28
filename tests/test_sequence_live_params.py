import unittest

from src.core.engine.function_manager import get_function_manager


class SequenceLiveParamTest(unittest.TestCase):
    def setUp(self):
        self.fm = get_function_manager()
        self.fm.stop_all()
        self._pre_ids = {f.id for f in self.fm.all()}
        self.seq = self.fm.new_sequence("Live Sequence")

    def tearDown(self):
        self.fm.stop_all()
        for f in list(self.fm.all()):
            if f.id not in self._pre_ids:
                self.fm.remove(f.id)

    def test_step_timing_params_are_live_mappable(self):
        from src.core.engine import effect_live
        from src.core.engine.sequence import SequenceStep

        self.seq.steps.append(SequenceStep({"1": {"pan": 10}}, fade_in=0.2,
                                           hold=0.8, fade_out=0.1))
        self.seq.steps.append(SequenceStep({"1": {"pan": 20}}, fade_in=0.3,
                                           hold=0.7, fade_out=0.2))

        params = {s.key for s in effect_live.list_params(function_id=self.seq.id)}
        self.assertTrue({"speed", "step_duration", "step_hold", "step_fade",
                         "step_fade_in", "step_fade_out"} <= params)

        self.assertTrue(effect_live.set_param("step_fade_in", 1.0,
                                              function_id=self.seq.id))
        self.assertTrue(all(abs(s.fade_in - 1.0) < 1e-9 for s in self.seq.steps))

        self.assertTrue(effect_live.set_param("step_fade_out", 0.5,
                                              function_id=self.seq.id))
        self.assertTrue(all(abs(s.fade_out - 0.5) < 1e-9 for s in self.seq.steps))

        self.assertTrue(effect_live.set_param("step_duration", 3.0,
                                              function_id=self.seq.id))
        self.assertTrue(all(abs(s.total_duration() - 3.0) < 1e-9
                            for s in self.seq.steps))

    def test_normalized_step_hold_uses_param_range(self):
        from src.core.engine import effect_live
        from src.core.engine.sequence import SequenceStep

        self.seq.steps.append(SequenceStep({"1": {"tilt": 20}}))

        self.assertTrue(effect_live.set_param_normalized("step_hold", 0.5,
                                                         function_id=self.seq.id))
        self.assertAlmostEqual(self.seq.steps[0].hold, 30.0, places=6)


if __name__ == "__main__":
    unittest.main()
