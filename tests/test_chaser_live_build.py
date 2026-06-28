"""APC-Probier To-Do #2: Chaser live zusammenstecken.

Der Chaser kann jetzt — wie Matrix/EFX — per do_action live bedient werden:
- capture_step: aktuellen Programmer als neue Scene aufnehmen + als Schritt anhaengen
- add_step / remove_last_step / clear_steps
- reverse_direction / toggle_bounce / restart / tap
- list_params/set_param (speed/direction/run_order) -> fader-/encoder-mappbar
"""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from src.core.engine.function_manager import get_function_manager
from src.core.engine.scene import Scene
from src.core.engine.function import RunOrder, Direction
from src.core.app_state import get_state


class _Ch:
    def __init__(self, attribute, channel_number):
        self.attribute = attribute
        self.channel_number = channel_number


class ChaserLiveBuildTest(unittest.TestCase):
    def setUp(self):
        self.fm = get_function_manager()
        self.fm.stop_all()
        self._pre_ids = {f.id for f in self.fm.all()}
        self.c = self.fm.new_chaser("LiveChaser")

    def tearDown(self):
        self.fm.stop_all()
        for f in list(self.fm.all()):
            if f.id not in self._pre_ids:
                self.fm.remove(f.id)
        get_state().programmer.clear()

    # ── add_step / clear / remove ────────────────────────────────────────────
    def test_add_step(self):
        sc = self.fm.new_scene("look")
        idx = self.c.add_step(sc.id, hold=2.0)
        self.assertEqual(idx, 0)
        self.assertEqual(self.c.steps[0].function_id, sc.id)
        self.assertEqual(self.c.steps[0].hold, 2.0)

    def test_clear_and_remove(self):
        a = self.fm.new_scene("a")
        b = self.fm.new_scene("b")
        self.c.add_step(a.id)
        self.c.add_step(b.id)
        self.assertTrue(self.c.do_action("remove_last_step"))
        self.assertEqual(len(self.c.steps), 1)
        self.assertTrue(self.c.do_action("clear_steps"))
        self.assertEqual(len(self.c.steps), 0)
        self.assertFalse(self.c.do_action("remove_last_step"))   # leer -> False

    # ── capture_step ─────────────────────────────────────────────────────────
    def test_capture_empty_programmer_returns_none(self):
        get_state().programmer.clear()
        self.assertIsNone(self.c.capture_step())
        self.assertFalse(self.c.do_action("capture_step"))

    def test_capture_step_creates_scene_and_step(self):
        state = get_state()
        state.programmer.clear()
        state.programmer[1] = {"color_r": 255, "intensity": 200}
        fake_fx = SimpleNamespace(fid=1, universe=1, address=1)
        chans = [_Ch("intensity", 1), _Ch("color_r", 2), _Ch("color_g", 3)]
        with patch.object(type(state), "get_patched_fixtures", return_value=[fake_fx]), \
             patch("src.core.app_state.get_channels_for_patched", return_value=chans):
            n_before = len(self.fm.all())
            idx = self.c.capture_step(hold=1.5)
        self.assertEqual(idx, 0)
        self.assertEqual(len(self.fm.all()), n_before + 1)   # neue Scene registriert
        step = self.c.steps[0]
        scene = self.fm.get(step.function_id)
        self.assertIsInstance(scene, Scene)
        self.assertEqual(scene.get_value(1, 2), 255)   # color_r -> Kanal 2
        self.assertEqual(scene.get_value(1, 1), 200)   # intensity -> Kanal 1
        self.assertIsNone(scene.get_value(1, 3))       # color_g war nicht im Programmer
        self.assertEqual(step.hold, 1.5)

    # ── Richtung / Modus ─────────────────────────────────────────────────────
    def test_direction_and_pingpong_actions(self):
        self.assertTrue(self.c.do_action("reverse_direction"))
        self.assertEqual(self.c.direction, Direction.Backward)
        self.assertTrue(self.c.do_action("toggle_bounce"))
        self.assertEqual(self.c.run_order, RunOrder.PingPong)
        self.assertTrue(self.c.do_action("toggle_bounce"))
        self.assertEqual(self.c.run_order, RunOrder.Loop)

    # ── Bindungs-API ─────────────────────────────────────────────────────────
    def test_list_actions_and_params(self):
        actions = dict(self.c.list_actions())
        self.assertIn("capture_step", actions)
        self.assertIn("clear_steps", actions)
        params = {s.key for s in self.c.list_params()}
        # Kern-Params muessen enthalten sein; Tempo-Bus-Params (tempo_bus_id/
        # tempo_multiplier/phase_offset) sind zusaetzlich erlaubt -> Subset-Check
        # statt exakter Menge (sonst bricht jede neue Param-Erweiterung diesen Test).
        self.assertTrue({"speed", "direction", "run_order",
                         "step_duration", "step_hold",
                         "step_fade", "step_fade_in", "step_fade_out"} <= params)

    def test_dispatcher_set_param_and_action(self):
        from src.core.engine import effect_live
        self.assertTrue(effect_live.set_param("speed", 2.0, function_id=self.c.id))
        self.assertEqual(self.c.speed, 2.0)
        self.assertEqual(effect_live.get_param("run_order", function_id=self.c.id),
                         RunOrder.Loop.value)
        actions = dict(effect_live.list_actions(function_id=self.c.id))
        self.assertIn("capture_step", actions)

    def test_step_timing_params_are_live_mappable(self):
        from src.core.engine import effect_live

        a = self.fm.new_scene("a")
        b = self.fm.new_scene("b")
        self.c.add_step(a.id, fade_in=0.1, hold=0.4, fade_out=0.2)
        self.c.add_step(b.id, fade_in=0.2, hold=0.6, fade_out=0.3)

        self.assertTrue(effect_live.set_param("step_fade_in", 1.25,
                                              function_id=self.c.id))
        self.assertTrue(all(abs(s.fade_in - 1.25) < 1e-9 for s in self.c.steps))

        self.assertTrue(effect_live.set_param("step_fade_out", 0.75,
                                              function_id=self.c.id))
        self.assertTrue(all(abs(s.fade_out - 0.75) < 1e-9 for s in self.c.steps))

        self.assertTrue(effect_live.set_param("step_hold", 2.0,
                                              function_id=self.c.id))
        self.assertTrue(all(abs(s.hold - 2.0) < 1e-9 for s in self.c.steps))
        self.assertAlmostEqual(effect_live.get_param("step_duration",
                                                     function_id=self.c.id),
                               4.0)

    def test_normalized_step_duration_scales_to_param_range(self):
        from src.core.engine import effect_live

        sc = self.fm.new_scene("look")
        self.c.add_step(sc.id, fade_in=0.5, hold=1.0, fade_out=0.5)

        self.assertTrue(effect_live.set_param_normalized("step_duration", 0.0,
                                                         function_id=self.c.id))
        self.assertAlmostEqual(self.c.steps[0].total_duration(), 0.05, places=6)
        self.assertAlmostEqual(self.c.steps[0].hold, 0.0, places=6)

        self.assertTrue(effect_live.set_param_normalized("step_fade", 0.5,
                                                         function_id=self.c.id))
        self.assertAlmostEqual(self.c.steps[0].fade_in, 5.0, places=6)
        self.assertAlmostEqual(self.c.steps[0].fade_out, 5.0, places=6)


if __name__ == "__main__":
    unittest.main()
