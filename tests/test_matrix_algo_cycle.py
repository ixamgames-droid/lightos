"""APC-Probier To-Do #3: Live-Umschalten des Matrix-Algorithmus.

`RgbMatrixInstance` kann jetzt — wie EfxInstance — per do_action durch ihre
Algorithmen rotieren (next_algorithm / prev_algorithm) und den Algorithmus per
set_param("algorithm", …) absolut setzen. Damit reicht im "Matrix Builder" EINE
Matrix + ein "Form +/-"-Pad statt ein Pad je Algorithmus.
"""
import unittest

from src.core.engine.rgb_matrix import RgbMatrixInstance, RgbAlgorithm


class CycleAlgorithmTest(unittest.TestCase):
    def _matrix(self):
        return RgbMatrixInstance(name="M", cols=4, rows=1,
                                 algorithm=RgbAlgorithm.CHASE,
                                 fixture_grid=[1, 2, 3, 4])

    def test_next_then_prev_round_trips(self):
        m = self._matrix()
        first = m.algorithm
        self.assertTrue(m.do_action("next_algorithm"))
        self.assertNotEqual(m.algorithm, first)
        self.assertTrue(m.do_action("prev_algorithm"))
        self.assertEqual(m.algorithm, first)

    def test_next_wraps_through_all_algorithms(self):
        m = self._matrix()
        n = len(list(RgbAlgorithm))
        start = m.algorithm
        seen = {m.algorithm}
        for _ in range(n - 1):
            m.do_action("next_algorithm")
            seen.add(m.algorithm)
        # alle Algorithmen einmal gesehen, und nach n Schritten wieder am Anfang
        self.assertEqual(len(seen), n)
        m.do_action("next_algorithm")
        self.assertEqual(m.algorithm, start)

    def test_action_aliases(self):
        m = self._matrix()
        first = m.algorithm
        self.assertTrue(m.do_action("nextAlgorithm"))
        self.assertTrue(m.do_action("prevAlgorithm"))
        self.assertEqual(m.algorithm, first)

    def test_list_actions_includes_form_pair(self):
        actions = dict(self._matrix().list_actions())
        self.assertEqual(actions.get("next_algorithm"), "Form +")
        self.assertEqual(actions.get("prev_algorithm"), "Form −")


class AlgorithmParamTest(unittest.TestCase):
    def test_set_param_switches_algorithm(self):
        m = RgbMatrixInstance(name="M", algorithm=RgbAlgorithm.CHASE)
        self.assertTrue(m.set_param("algorithm", "Wave"))
        self.assertEqual(m.algorithm, RgbAlgorithm.WAVE)
        # vorher ein stiller Bug: landete nur in params, nie auf self.algorithm
        self.assertNotIn("algorithm", m.params)

    def test_get_param_returns_value(self):
        m = RgbMatrixInstance(name="M", algorithm=RgbAlgorithm.RAINBOW)
        self.assertEqual(m.get_param("algorithm"), RgbAlgorithm.RAINBOW.value)

    def test_set_param_unknown_value_returns_false(self):
        m = RgbMatrixInstance(name="M", algorithm=RgbAlgorithm.CHASE)
        self.assertFalse(m.set_param("algorithm", "Nope"))
        self.assertEqual(m.algorithm, RgbAlgorithm.CHASE)

    def test_set_param_migrates_legacy_name(self):
        m = RgbMatrixInstance(name="M", algorithm=RgbAlgorithm.PLAIN)
        self.assertTrue(m.set_param("algorithm", "Welle Horizontal"))
        self.assertEqual(m.algorithm, RgbAlgorithm.WAVE)
        self.assertEqual(m.params.get("origin"), "left")


class DispatcherTest(unittest.TestCase):
    def test_effect_live_cycles_algorithm(self):
        from src.core.engine import effect_live
        from src.core.engine.function_manager import get_function_manager
        fm = get_function_manager()
        m = RgbMatrixInstance(name="M", algorithm=RgbAlgorithm.CHASE,
                              fixture_grid=[1])
        fm.add(m)
        try:
            first = m.algorithm
            self.assertTrue(effect_live.do_action("next_algorithm", function_id=m.id))
            self.assertNotEqual(m.algorithm, first)
            actions = dict(effect_live.list_actions(function_id=m.id))
            self.assertIn("next_algorithm", actions)
            self.assertTrue(effect_live.set_param("algorithm", "Strobe", function_id=m.id))
            self.assertEqual(m.algorithm, RgbAlgorithm.STROBE)
        finally:
            fm.remove(m.id)


if __name__ == "__main__":
    unittest.main()
