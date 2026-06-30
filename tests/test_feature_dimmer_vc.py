"""F-26b: VC-Bindung des Feature-Dimmer-Masters (SliderMode.FEATURE_DIMMER).

Das Backend (set_feature_dimmer + Render-Schritt 4b²) ist in test_feature_dimmer.py
abgedeckt; hier die VCSlider-Bindung: _apply, Serialisierung, Reapply-on-load,
Dialog-Slot-Sync (enter/leave) und die Capability-ComboBox-Quelle.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.core.app_state import get_state
from src.ui.virtualconsole.vc_slider import (
    VCSlider, SliderMode, _VALID_SLIDER_MODES, _clear_feature_dimmer_slot)

_app = QApplication.instance() or QApplication([])


class FeatureDimmerVCBinding(unittest.TestCase):
    def setUp(self):
        self.state = get_state()
        self.state.feature_dimmers.clear()

    def _make(self, feature="Color", group="G", value=128):
        s = VCSlider("fd")
        s.mode = SliderMode.FEATURE_DIMMER
        s.programmer_group = group
        s.feature_attr = feature
        s._group_fids = lambda st, name: [1, 2]
        s._value = value
        return s

    def test_mode_is_valid(self):
        self.assertIn(SliderMode.FEATURE_DIMMER, _VALID_SLIDER_MODES)

    def test_apply_sets_feature_dimmer_slot(self):
        s = self._make(feature="Color", value=128)
        s._apply()
        fd = self.state.feature_dimmers.get(id(s))
        self.assertIsNotNone(fd, "FEATURE_DIMMER _apply muss einen Slot setzen")
        self.assertEqual(set(fd.fids), {1, 2})
        self.assertEqual(set(fd.features), {"Color"})
        self.assertAlmostEqual(fd.level, 128 / 255.0, places=2)

    def test_intensity_means_default_feature(self):
        s = self._make(feature="Intensity", value=100)
        s._apply()
        fd = self.state.feature_dimmers.get(id(s))
        self.assertIsNotNone(fd)
        self.assertEqual(set(fd.features), set(),
                         "feature_attr=Intensity -> features leer (= Default Helligkeit)")

    def test_full_level_removes_slot(self):
        s = self._make(value=255)          # level 1.0 -> kein Dimmen -> Slot entfernt
        s._apply()
        self.assertNotIn(id(s), self.state.feature_dimmers)

    def test_roundtrip_feature_attr(self):
        s = VCSlider("fd")
        s.feature_attr = "Gobo"
        d = s.to_dict()
        self.assertEqual(d["feature_attr"], "Gobo")
        s2 = VCSlider("fd2")
        s2.apply_dict(d)
        self.assertEqual(s2.feature_attr, "Gobo")

    def test_reapplied_on_load(self):
        s = VCSlider("fd")
        s._group_fids = lambda st, name: [5]
        s.apply_dict({"mode": SliderMode.FEATURE_DIMMER, "programmer_group": "G",
                      "feature_attr": "Color", "value": 200})
        self.assertIn(id(s), self.state.feature_dimmers,
                      "F-26b/VCB-32: FEATURE_DIMMER muss beim Laden re-applied werden")

    def test_post_dialog_sync_enter_and_leave(self):
        s = self._make(value=128)
        s._post_dialog_mode_sync(SliderMode.LEVEL, "")     # neu -> FEATURE_DIMMER
        self.assertIn(id(s), self.state.feature_dimmers)
        s.mode = SliderMode.LEVEL                            # weg von FEATURE_DIMMER
        s._post_dialog_mode_sync(SliderMode.FEATURE_DIMMER, "G")
        self.assertNotIn(id(s), self.state.feature_dimmers,
                         "Verlassen des FEATURE_DIMMER muss den Slot raeumen")

    def test_clear_slot_helper(self):
        s = self._make(value=128)
        s._apply()
        self.assertIn(id(s), self.state.feature_dimmers)
        _clear_feature_dimmer_slot(id(s))
        self.assertNotIn(id(s), self.state.feature_dimmers)

    def test_available_feature_groups_fallback(self):
        groups = VCSlider._available_feature_groups("")     # keine Gruppe -> Standardliste
        self.assertIn("Intensity", groups)
        self.assertIn("Color", groups)


if __name__ == "__main__":
    unittest.main()
