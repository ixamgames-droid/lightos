"""Batch 2026-06-12: F-24 (SELECT_GROUP), F-25 (GROUP_DIMMER), B-8 (running_ids),
T-6 (matches_midi zentral)."""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.core.app_state import get_state
from src.core.engine.function_manager import get_function_manager
from src.core.engine.rgb_matrix import RgbMatrixInstance, RgbAlgorithm
from src.ui.virtualconsole.vc_button import VCButton, ButtonAction
from src.ui.virtualconsole.vc_color import VCColor
from src.ui.virtualconsole.vc_slider import VCSlider, SliderMode

_app = QApplication.instance() or QApplication([])


class _FakeSession:
    def __init__(self, group):
        self._g = group
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False
    def execute(self, _q):
        return SimpleNamespace(scalar_one_or_none=lambda: self._g)


class GroupResolutionTest(unittest.TestCase):
    def test_group_lookup_and_select(self):
        state = get_state()
        group = SimpleNamespace(id=7, positions_json='{"0,0": 2, "1,0": 4, "2,0": 9}')
        with patch.object(type(state), "_session", lambda self: _FakeSession(group)):
            self.assertEqual(state.group_fids_by_name("X"), [2, 4, 9])
            ok = state.select_group_by_name("X")
        self.assertTrue(ok)
        self.assertEqual(state.get_selected_fids(), [2, 4, 9])
        self.assertEqual(state.get_selected_group_id(), 7)

    def test_select_missing_group_returns_false(self):
        state = get_state()
        with patch.object(type(state), "_session", lambda self: _FakeSession(None)):
            self.assertFalse(state.select_group_by_name("Nope"))
            self.assertEqual(state.group_fids_by_name("Nope"), [])


class SelectGroupButtonTest(unittest.TestCase):
    def test_button_calls_select_group(self):
        state = get_state()
        b = VCButton("Sel")
        b.action = ButtonAction.SELECT_GROUP
        b.group_name = "PAR-Reihe"
        with patch.object(type(state), "select_group_by_name") as sel:
            b._trigger(True)
        sel.assert_called_once_with("PAR-Reihe")

    def test_serialization_roundtrip(self):
        b = VCButton("Sel")
        b.action = ButtonAction.SELECT_GROUP
        b.group_name = "Moving Heads"
        b2 = VCButton()
        b2.apply_dict(b.to_dict())
        self.assertEqual(b2.action, ButtonAction.SELECT_GROUP)
        self.assertEqual(b2.group_name, "Moving Heads")


class GroupDimmerSliderTest(unittest.TestCase):
    def test_group_dimmer_applies(self):
        state = get_state()
        s = VCSlider("GrpDim")
        s.mode = SliderMode.GROUP_DIMMER
        s.programmer_group = "PAR-Reihe"
        with patch.object(VCSlider, "_group_fids", return_value=[2, 4]), \
             patch.object(type(state), "set_group_dimmer") as gd:
            s.value = 128
        gd.assert_called_once()
        args = gd.call_args[0]
        self.assertEqual(args[0], [2, 4])
        self.assertAlmostEqual(args[1], 128 / 255.0, places=3)

    def test_mode_serialization(self):
        s = VCSlider("X")
        s.mode = SliderMode.GROUP_DIMMER
        s.programmer_group = "G"
        s2 = VCSlider()
        s2.apply_dict(s.to_dict())
        self.assertEqual(s2.mode, SliderMode.GROUP_DIMMER)
        self.assertEqual(s2.programmer_group, "G")


class RunningIdsSnapshotTest(unittest.TestCase):
    def setUp(self):
        self.fm = get_function_manager()
        self.fm.stop_all()
        self._pre = {f.id for f in self.fm.all()}
        self.m = RgbMatrixInstance(name="r", algorithm=RgbAlgorithm.CHASE, fixture_grid=[1])
        self.fm.add(self.m)

    def tearDown(self):
        self.fm.stop_all()
        for f in list(self.fm.all()):
            if f.id not in self._pre:
                self.fm.remove(f.id)

    def test_running_ids_snapshot(self):
        self.assertNotIn(self.m.id, self.fm.running_ids())
        self.fm.start(self.m.id)
        ids = self.fm.running_ids()
        self.assertIn(self.m.id, ids)
        self.assertIsInstance(ids, list)        # Kopie, kein internes Set
        ids.clear()                              # darf das Original nicht beeinflussen
        self.assertIn(self.m.id, self.fm.running_ids())
        self.fm.stop(self.m.id)
        self.assertNotIn(self.m.id, self.fm.running_ids())


class MatchesMidiSharedTest(unittest.TestCase):
    def _msg(self, **kw):
        d = {"msg_type": "note_on", "channel": 1, "data1": 40, "data2": 127}
        d.update(kw)
        return SimpleNamespace(**d)

    def test_button_and_color_use_same_logic(self):
        for w in (VCButton(), VCColor()):
            w.midi_type, w.midi_ch, w.midi_data1 = "note_on", 0, 40
            self.assertTrue(w.matches_midi(self._msg()))
            self.assertTrue(w.matches_midi(self._msg(msg_type="note_off")))  # note_on bindet note_off
            self.assertFalse(w.matches_midi(self._msg(data1=41)))
            w.midi_ch = 2
            self.assertFalse(w.matches_midi(self._msg(channel=1)))           # falscher Kanal
            w.midi_data1 = -1
            self.assertFalse(w.matches_midi(self._msg()))                    # keine Bindung


if __name__ == "__main__":
    unittest.main()
