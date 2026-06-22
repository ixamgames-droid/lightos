"""Bridge-Routing fuers Aim-Werkzeug (VisualizerBridge.aimFixturesAt):
Moving Heads -> Pan/Tilt in den Programmer, statische Fixtures -> Ausrichtung.
Ohne echte VisualizerWindow (Fake-self-Muster wie test_visualizer_controls).
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


class AimRoutingTest(unittest.TestCase):
    def _fake_bridge(self, fixtures, positions):
        st = SimpleNamespace(
            get_patched_fixtures=lambda: fixtures,
            visualizer_positions=dict(positions),
            visualizer_rotations={},
            set_programmer_value=MagicMock(),
        )
        return SimpleNamespace(
            _state=st,
            _is_moving_head=lambda f: bool(getattr(f, "_is_mh", False)),
            push_apply_fixture_transform=MagicMock(),
            pyFixtureRotated=MagicMock(),
            pyAimApplied=MagicMock(),
        )

    def test_moving_head_writes_programmer_pan_tilt(self):
        mh = SimpleNamespace(fid=1, _is_mh=True, invert_pan=False,
                             invert_tilt=False, swap_pan_tilt=False)
        fake = self._fake_bridge([mh], {1: (-3.0, 5.0, 0.0)})
        VW.VisualizerBridge.aimFixturesAt(
            fake, json.dumps({"x": 0, "y": 0, "z": 0, "fids": [1]}))
        # pan + tilt + pan_fine + tilt_fine geschrieben
        attrs = [c.args[1] for c in fake._state.set_programmer_value.call_args_list]
        self.assertIn("pan", attrs)
        self.assertIn("tilt", attrs)
        self.assertIn("pan_fine", attrs)
        self.assertIn("tilt_fine", attrs)
        # statische Ausrichtung NICHT angefasst
        self.assertEqual(fake._state.visualizer_rotations, {})

    def test_static_fixture_sets_orientation(self):
        par = SimpleNamespace(fid=2, _is_mh=False)
        fake = self._fake_bridge([par], {2: (0.0, 3.0, 0.0)})
        VW.VisualizerBridge.aimFixturesAt(
            fake, json.dumps({"x": 0, "y": 0, "z": -4, "fids": [2]}))
        # Ausrichtung gesetzt (3-Tupel) + an JS gepusht + gemeldet
        self.assertIn(2, fake._state.visualizer_rotations)
        self.assertEqual(len(fake._state.visualizer_rotations[2]), 3)
        fake.push_apply_fixture_transform.assert_called_once()
        fake.pyFixtureRotated.emit.assert_called_once()
        fake._state.set_programmer_value.assert_not_called()

    def test_two_moving_heads_get_different_pan(self):
        a = SimpleNamespace(fid=1, _is_mh=True, invert_pan=False, invert_tilt=False, swap_pan_tilt=False)
        b = SimpleNamespace(fid=2, _is_mh=True, invert_pan=False, invert_tilt=False, swap_pan_tilt=False)
        fake = self._fake_bridge([a, b], {1: (-4.0, 5.0, 0.0), 2: (4.0, 5.0, 0.0)})
        VW.VisualizerBridge.aimFixturesAt(
            fake, json.dumps({"x": 0, "y": 0, "z": 0, "fids": [1, 2]}))
        pans = {}
        for c in fake._state.set_programmer_value.call_args_list:
            fid, attr, val = c.args[0], c.args[1], c.args[2]
            if attr == "pan":
                pans[fid] = val
        self.assertIn(1, pans); self.assertIn(2, pans)
        self.assertNotEqual(pans[1], pans[2])   # verschiedene Standorte -> verschiedenes Pan

    def test_empty_fids_noop(self):
        fake = self._fake_bridge([], {})
        VW.VisualizerBridge.aimFixturesAt(fake, json.dumps({"x": 0, "y": 0, "z": 0, "fids": []}))
        fake._state.set_programmer_value.assert_not_called()
        fake.pyAimApplied.emit.assert_not_called()


class IsMovingHeadTest(unittest.TestCase):
    def test_pan_tilt_is_moving_head(self):
        f = SimpleNamespace(fid=1)
        chans = [SimpleNamespace(attribute="pan"), SimpleNamespace(attribute="tilt"),
                 SimpleNamespace(attribute="dimmer")]
        with patch.object(VW, "is_spider_fixture", return_value=False), \
             patch.object(VW, "get_channels_for_patched", return_value=chans):
            self.assertTrue(VW.VisualizerBridge._is_moving_head(SimpleNamespace(), f))

    def test_spider_is_not_moving_head(self):
        f = SimpleNamespace(fid=1)
        with patch.object(VW, "is_spider_fixture", return_value=True), \
             patch.object(VW, "get_channels_for_patched", return_value=[]):
            self.assertFalse(VW.VisualizerBridge._is_moving_head(SimpleNamespace(), f))

    def test_par_is_not_moving_head(self):
        f = SimpleNamespace(fid=1)
        chans = [SimpleNamespace(attribute="dimmer"), SimpleNamespace(attribute="color_r")]
        with patch.object(VW, "is_spider_fixture", return_value=False), \
             patch.object(VW, "get_channels_for_patched", return_value=chans):
            self.assertFalse(VW.VisualizerBridge._is_moving_head(SimpleNamespace(), f))


if __name__ == "__main__":
    unittest.main()
