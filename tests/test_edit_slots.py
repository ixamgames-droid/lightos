"""Live-Bearbeitung via Edit-Slots: ein Effekt-Pad macht seinen Effekt zum aktiven
Bearbeitungsziel eines benannten Slots; Fader/Farb-Kacheln mit gleichem Slot
bearbeiten GENAU diesen Effekt — pro Quadrant/Slot unabhängig.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.core.app_state import get_state
from src.core.engine.rgb_matrix import RgbMatrixInstance, RgbAlgorithm
from src.core.engine import effect_live
from src.ui.virtualconsole.vc_button import VCButton, ButtonAction
from src.ui.virtualconsole.vc_slider import VCSlider, SliderMode
from src.ui.virtualconsole.vc_color import VCColor, ColorTarget

_app = QApplication.instance() or QApplication([])


class _Base(unittest.TestCase):
    def setUp(self):
        self.state = get_state()
        self.fm = self.state.function_manager
        self.fm.stop_all()
        effect_live.clear_edit_targets()
        self._pre = {f.id for f in self.fm.all()}
        self.m1 = RgbMatrixInstance(name="m1", algorithm=RgbAlgorithm.CHASE, fixture_grid=[1])
        self.m2 = RgbMatrixInstance(name="m2", algorithm=RgbAlgorithm.CHASE, fixture_grid=[2])
        self.m3 = RgbMatrixInstance(name="m3", algorithm=RgbAlgorithm.FIRE, fixture_grid=[3])
        for m in (self.m1, self.m2, self.m3):
            self.fm.add(m)

    def tearDown(self):
        self.fm.stop_all()
        effect_live.clear_edit_targets()
        for f in list(self.fm.all()):
            if f.id not in self._pre:
                self.fm.remove(f.id)

    def _toggle(self, fn, slot):
        b = VCButton(fn.name)
        b.action = ButtonAction.FUNCTION_TOGGLE
        b.function_id = fn.id
        b.edit_slot = slot
        return b


class EditTargetRegistryTest(_Base):
    def test_set_get_clear(self):
        effect_live.set_edit_target("MH", self.m1.id)
        self.assertEqual(effect_live.get_edit_target("MH"), self.m1.id)
        effect_live.set_edit_target("MH", None)
        self.assertIsNone(effect_live.get_edit_target("MH"))
        effect_live.set_edit_target("MX", self.m2.id)
        effect_live.clear_edit_targets()
        self.assertIsNone(effect_live.get_edit_target("MX"))


class ButtonSetsTargetAndPerSlotExclusiveTest(_Base):
    def test_button_sets_edit_target(self):
        self._toggle(self.m1, "MH")._trigger(True)
        self.assertTrue(self.fm.is_running(self.m1.id))
        self.assertEqual(effect_live.get_edit_target("MH"), self.m1.id)

    def test_per_slot_exclusive_stops_previous_same_slot(self):
        self._toggle(self.m1, "MH")._trigger(True)
        self._toggle(self.m2, "MH")._trigger(True)
        self.assertFalse(self.fm.is_running(self.m1.id))   # voriges Slot-Ziel gestoppt
        self.assertTrue(self.fm.is_running(self.m2.id))
        self.assertEqual(effect_live.get_edit_target("MH"), self.m2.id)

    def test_other_slot_keeps_running(self):
        self._toggle(self.m2, "MH")._trigger(True)
        self._toggle(self.m3, "MX")._trigger(True)        # anderer Slot
        self.assertTrue(self.fm.is_running(self.m2.id))    # MH bleibt laufen
        self.assertTrue(self.fm.is_running(self.m3.id))
        self.assertEqual(effect_live.get_edit_target("MH"), self.m2.id)
        self.assertEqual(effect_live.get_edit_target("MX"), self.m3.id)

    def test_serialization(self):
        b = self._toggle(self.m1, "MH")
        b2 = VCButton()
        b2.apply_dict(b.to_dict())
        self.assertEqual(b2.edit_slot, "MH")


class SliderEditsSlotTargetTest(_Base):
    def test_effect_speed_edits_slot_target(self):
        effect_live.set_edit_target("MH", self.m1.id)
        s = VCSlider("Speed")
        s.mode = SliderMode.EFFECT_SPEED
        s.edit_slot = "MH"
        s.value = 255
        self.assertGreater(self.m1.speed, 1.0)            # Slot-Ziel beschleunigt
        self.assertEqual(self.m2.speed, 1.0)              # anderer Effekt unberührt

    def test_effect_param_edits_slot_target(self):
        effect_live.set_edit_target("MX", self.m2.id)
        s = VCSlider("Sp")
        s.mode = SliderMode.EFFECT_PARAM
        s.param_key = "speed"
        s.edit_slot = "MX"
        s.value = 255
        self.assertGreater(self.m2.matrix_speed, 15)      # ~max der speed-Spec
        self.assertEqual(self.m1.matrix_speed, 1.0)

    def test_serialization(self):
        s = VCSlider("x"); s.mode = SliderMode.EFFECT_SPEED; s.edit_slot = "Q1"
        s2 = VCSlider(); s2.apply_dict(s.to_dict())
        self.assertEqual(s2.edit_slot, "Q1")


class ColorEditsSlotTargetTest(_Base):
    def test_color_slot_recolors_slot_target(self):
        effect_live.set_edit_target("MX", self.m3.id)
        c = VCColor("C1")
        c.target = ColorTarget.EFFECT_C1
        c.edit_slot = "MX"
        c.color_r, c.color_g, c.color_b = 7, 8, 9
        c._apply()
        self.assertEqual(self.m3.color1, (7, 8, 9))

    def test_serialization(self):
        c = VCColor("x"); c.target = ColorTarget.EFFECT_C1; c.edit_slot = "MX"
        c2 = VCColor(); c2.apply_dict(c.to_dict())
        self.assertEqual(c2.edit_slot, "MX")


if __name__ == "__main__":
    unittest.main()
