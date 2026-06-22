"""Live-Formen-Nachfahren in der Bridge: _build_trace_seqs + _trace_tick.
Fake-self-Muster (kein echtes VisualizerWindow/WebEngine).
"""
import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import src.ui.visualizer.visualizer_window as VW

_app = QApplication.instance() or QApplication([])


class TracePlayerTest(unittest.TestCase):
    def _fake(self, fixtures, positions, mh_fids):
        return SimpleNamespace(
            _state=SimpleNamespace(
                get_patched_fixtures=lambda: fixtures,
                visualizer_positions=dict(positions),
                visualizer_rotations={},
                set_programmer_value=MagicMock(),
            ),
            _is_moving_head=lambda f: f.fid in mh_fids,
        )

    def test_build_seqs_only_moving_heads(self):
        mh = SimpleNamespace(fid=1, invert_pan=False, invert_tilt=False, swap_pan_tilt=False)
        par = SimpleNamespace(fid=2)
        fake = self._fake([mh, par], {1: (-3.0, 5.0, 0.0), 2: (0.0, 3.0, 0.0)}, {1})
        seqs = VW.VisualizerBridge._build_trace_seqs(
            fake, "circle", (0.0, 3.0, -5.0), (0.0, 0.0, 1.0), 1.0, 24, [1, 2])
        self.assertIn(1, seqs)          # MH dabei
        self.assertNotIn(2, seqs)       # PAR nicht
        self.assertEqual(len(seqs[1]), 24)
        for pan, tilt in seqs[1]:
            self.assertTrue(0 <= pan <= 255 and 0 <= tilt <= 255)

    def test_tick_writes_and_advances(self):
        fake = self._fake([], {}, set())
        fake._trace_state = {"seqs": {7: [(10, 20), (30, 40), (50, 60)]}, "i": 0, "n": 3}
        VW.VisualizerBridge._trace_tick(fake)
        # erster Tick schreibt seq[0] = (10,20)
        calls = {(c.args[1]): c.args[2] for c in fake._state.set_programmer_value.call_args_list}
        self.assertEqual(calls.get("pan"), 10)
        self.assertEqual(calls.get("tilt"), 20)
        self.assertEqual(fake._trace_state["i"], 1)

    def test_tick_wraps_index(self):
        fake = self._fake([], {}, set())
        seq = [(1, 2), (3, 4)]
        fake._trace_state = {"seqs": {9: seq}, "i": 5, "n": 2}
        VW.VisualizerBridge._trace_tick(fake)  # 5 % 2 == 1 -> (3,4)
        calls = {(c.args[1]): c.args[2] for c in fake._state.set_programmer_value.call_args_list}
        self.assertEqual(calls.get("pan"), 3)
        self.assertEqual(calls.get("tilt"), 4)

    def test_line_and_rect_shapes_build(self):
        mh = SimpleNamespace(fid=1, invert_pan=False, invert_tilt=False, swap_pan_tilt=False)
        fake = self._fake([mh], {1: (0.0, 5.0, 0.0)}, {1})
        for shape in ("line", "rect", "circle"):
            seqs = VW.VisualizerBridge._build_trace_seqs(
                fake, shape, (0.0, 3.0, -5.0), (0.0, 0.0, 1.0), 1.5, 24, [1])
            self.assertIn(1, seqs)
            self.assertGreater(len(seqs[1]), 0)


class SaveTraceSequenceTest(unittest.TestCase):
    def _fake(self, fixtures, positions, mh_fids):
        import types
        fake = SimpleNamespace(
            _state=SimpleNamespace(
                get_patched_fixtures=lambda: fixtures,
                visualizer_positions=dict(positions),
                visualizer_rotations={},
            ),
            _is_moving_head=lambda f: f.fid in mh_fids,
            pyTraceSaved=MagicMock(),
        )
        # echte _build_trace_seqs an den Fake binden (nutzt fake._state/_is_moving_head)
        fake._build_trace_seqs = types.MethodType(
            VW.VisualizerBridge._build_trace_seqs, fake)
        return fake

    def test_builds_sequence_steps(self):
        mh = SimpleNamespace(fid=1, invert_pan=False, invert_tilt=False, swap_pan_tilt=False)
        fake = self._fake([mh], {1: (-3.0, 5.0, 0.0)}, {1})
        seq = SimpleNamespace(steps=[], name="x", bound_fixtures=[])
        fake_fm = SimpleNamespace(new_sequence=lambda name: (setattr(seq, "name", name) or seq))
        with patch("src.core.engine.function_manager.get_function_manager",
                   return_value=fake_fm):
            VW.VisualizerBridge.saveTraceSequence(fake, json.dumps({
                "shape": "circle", "x": 0, "y": 3, "z": -5,
                "nx": 0, "ny": 0, "nz": 1, "radius": 1.0,
                "count": 24, "intervalMs": 60, "fids": [1],
            }))
        self.assertEqual(len(seq.steps), 24)
        for st in seq.steps:
            self.assertIn("1", st.values)
            self.assertIn("pan", st.values["1"])
            self.assertIn("tilt", st.values["1"])
        self.assertEqual(seq.bound_fixtures, [1])
        self.assertTrue(seq.name.startswith("Trace"))
        fake.pyTraceSaved.emit.assert_called_once()

    def test_no_moving_heads_emits_empty(self):
        par = SimpleNamespace(fid=2)
        fake = self._fake([par], {2: (0.0, 3.0, 0.0)}, set())
        VW.VisualizerBridge.saveTraceSequence(fake, json.dumps({
            "shape": "circle", "x": 0, "y": 3, "z": -5,
            "nx": 0, "ny": 0, "nz": 1, "radius": 1.0, "fids": [2],
        }))
        fake.pyTraceSaved.emit.assert_called_once_with("", 0)


if __name__ == "__main__":
    unittest.main()
