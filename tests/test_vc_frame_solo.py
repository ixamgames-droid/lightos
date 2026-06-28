"""Regressionstests fuer die echte Exklusivitaet von VC-Solo-Frames."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.core.app_state import get_state
from src.core.engine.snap_library import get_snap_library
from src.ui.virtualconsole.vc_button import ButtonAction, VCButton
from src.ui.virtualconsole.vc_frame import VCFrame

_app = QApplication.instance() or QApplication([])


class SoloFrameFunctionButtonTest(unittest.TestCase):
    def setUp(self):
        self.fm = get_state().function_manager
        self.fm.stop_all()
        self.a = self.fm.new_efx("SoloFrame A")
        self.b = self.fm.new_efx("SoloFrame B")
        self.c = self.fm.new_efx("SoloFrame C")
        self.frame = VCFrame("Solo")
        self.frame.set_solo(True)
        self.btn_a = self._button("A", self.a.id)
        self.btn_a.function_ids = [self.c.id]
        self.btn_b = self._button("B", self.b.id)

    def tearDown(self):
        self.fm.stop_all()
        self.fm.remove(self.a.id)
        self.fm.remove(self.b.id)
        self.fm.remove(self.c.id)

    def _button(self, caption, fid):
        btn = VCButton(caption, parent=self.frame)
        btn.action = ButtonAction.FUNCTION_TOGGLE
        btn.function_id = fid
        return btn

    def test_new_button_stops_previous_running_function(self):
        self.btn_a._trigger(True)
        self.btn_a._trigger(False)
        self.assertTrue(self.fm.is_running(self.a.id))
        self.assertTrue(self.fm.is_running(self.c.id))
        self.assertTrue(self.btn_a._function_running())

        self.btn_b._trigger(True)

        self.assertFalse(self.fm.is_running(self.a.id))
        self.assertFalse(self.fm.is_running(self.c.id))
        self.assertTrue(self.fm.is_running(self.b.id))

    def test_active_button_can_still_toggle_itself_off(self):
        self.btn_a._trigger(True)
        self.assertTrue(self.fm.is_running(self.a.id))

        self.btn_a._trigger(True)

        self.assertFalse(self.fm.is_running(self.a.id))
        self.assertFalse(self.fm.is_running(self.c.id))
        self.assertFalse(self.fm.is_running(self.b.id))

    def test_non_solo_frame_keeps_both_functions_running(self):
        self.frame.set_solo(False)
        self.btn_a._trigger(True)
        self.btn_b._trigger(True)

        self.assertTrue(self.fm.is_running(self.a.id))
        self.assertTrue(self.fm.is_running(self.c.id))
        self.assertTrue(self.fm.is_running(self.b.id))


class SoloFrameLibrarySnapTest(unittest.TestCase):
    def setUp(self):
        self.state = get_state()
        self.state.clear_programmer()
        self.lib = get_snap_library()
        self.red = self.lib.add_snap(
            "Solo Rot", "", {1: {"color_r": 255, "color_g": 0}})
        self.green = self.lib.add_snap(
            "Solo Gruen", "", {1: {"color_r": 0, "color_g": 255}})
        self.frame = VCFrame("Farben")
        self.frame.set_solo(True)
        self.btn_red = self._button("Rot", self.red.id)
        self.btn_green = self._button("Gruen", self.green.id)

    def tearDown(self):
        self.state.clear_programmer()
        self.lib.remove_snap(self.red.id)
        self.lib.remove_snap(self.green.id)

    def _button(self, caption, snap_id):
        btn = VCButton(caption, parent=self.frame)
        btn.action = ButtonAction.LIBRARY_SNAP
        btn.snap_id = snap_id
        btn.snap_mode = "toggle"
        return btn

    def test_new_color_deactivates_previous_snap(self):
        self.btn_red._trigger(True)
        self.assertTrue(self.btn_red._snap_active)
        self.assertEqual(self.state.get_programmer_value(1, "color_r"), 255)

        self.btn_green._trigger(True)

        self.assertFalse(self.btn_red._snap_active)
        self.assertTrue(self.btn_green._snap_active)
        self.assertEqual(self.state.get_programmer_value(1, "color_r"), 0)
        self.assertEqual(self.state.get_programmer_value(1, "color_g"), 255)

    def test_active_color_can_toggle_itself_off(self):
        self.btn_red._trigger(True)
        self.btn_red._trigger(True)

        self.assertFalse(self.btn_red._snap_active)
        self.assertIsNone(self.state.get_programmer_value(1, "color_r"))
        self.assertIsNone(self.state.get_programmer_value(1, "color_g"))


if __name__ == "__main__":
    unittest.main()
