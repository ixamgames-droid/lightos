"""UI-Audit: verständliche Benennung der Aktions-/Modus-Auswahl (statt roher Codes)
und VCEncoder am Live-Edit-Slot.

Wichtig: die Label-Listen müssen ALLE Enum-Werte abdecken — sonst wäre eine
Aktion/ein Modus im Dropdown nicht mehr wählbar.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.ui.virtualconsole.vc_button import VCButton, ButtonAction, BUTTON_ACTION_LABELS
from src.ui.virtualconsole.vc_slider import VCSlider, SliderMode, SLIDER_MODE_LABELS
from src.ui.virtualconsole.vc_encoder import VCEncoder
from src.core.engine.function_manager import get_function_manager
from src.core.engine.rgb_matrix import RgbMatrixInstance, RgbAlgorithm
from src.core.engine import effect_live

_app = QApplication.instance() or QApplication([])


class LabelCoverageTest(unittest.TestCase):
    def test_all_button_actions_have_a_label(self):
        labeled = {v for v, _lbl in BUTTON_ACTION_LABELS}
        for a in ButtonAction:
            self.assertIn(a.value, labeled, f"Aktion ohne Label: {a.value}")
        # die meisten Labels sind echter Klartext (≠ roher Code); Eigennamen wie
        # „Blackout" dürfen identisch bleiben.
        relabeled = sum(1 for v, lbl in BUTTON_ACTION_LABELS if v != lbl)
        self.assertGreater(relabeled, len(BUTTON_ACTION_LABELS) // 2)

    def test_all_slider_modes_have_a_label(self):
        mode_values = {v for k, v in vars(SliderMode).items()
                       if not k.startswith("_") and isinstance(v, str)}
        labeled = {v for v, _lbl in SLIDER_MODE_LABELS}
        self.assertEqual(mode_values, labeled, "Slider-Modi und Labels weichen ab")

    def test_labels_are_german_readable(self):
        # Stichprobe: die früher kryptischen Codes haben jetzt Klartext.
        bl = dict(BUTTON_ACTION_LABELS)
        self.assertEqual(bl[ButtonAction.SELECT_GROUP], "Gruppe auswählen")
        ml = dict(SLIDER_MODE_LABELS)
        self.assertEqual(ml[SliderMode.GROUP_DIMMER], "Gruppen-Dimmer")


class EncoderEditSlotTest(unittest.TestCase):
    def setUp(self):
        self.fm = get_function_manager()
        self.fm.stop_all()
        effect_live.clear_edit_targets()
        self._pre = {f.id for f in self.fm.all()}
        self.m = RgbMatrixInstance(name="enc", algorithm=RgbAlgorithm.CHASE, fixture_grid=[1])
        self.fm.add(self.m)

    def tearDown(self):
        self.fm.stop_all()
        effect_live.clear_edit_targets()
        for f in list(self.fm.all()):
            if f.id not in self._pre:
                self.fm.remove(f.id)

    def test_encoder_resolves_slot_target(self):
        effect_live.set_edit_target("MX", self.m.id)
        e = VCEncoder("Speed")
        e.param_key = "speed"
        e.edit_slot = "MX"
        self.assertEqual(e._fid(), self.m.id)
        # nudge verstellt den Slot-Effekt
        self.m.matrix_speed = 1.0
        e.nudge(+5)
        self.assertGreater(self.m.matrix_speed, 1.0)

    def test_fixed_id_wins_over_slot(self):
        effect_live.set_edit_target("MX", 999)
        e = VCEncoder(); e.function_id = self.m.id; e.edit_slot = "MX"
        self.assertEqual(e._fid(), self.m.id)

    def test_serialization(self):
        e = VCEncoder(); e.edit_slot = "MX"; e.param_key = "size"
        e2 = VCEncoder(); e2.apply_dict(e.to_dict())
        self.assertEqual(e2.edit_slot, "MX")
        self.assertEqual(e2.param_key, "size")


if __name__ == "__main__":
    unittest.main()
