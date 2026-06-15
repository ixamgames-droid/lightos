"""Qt-Offscreen-Tests: VC-Bedienelemente steuern Effekt-Parameter/-Aktionen live (Phase 6).

VCSlider (EFFECT_PARAM), VCButton (EFFECT_ACTION) und VCColor (Ziel=Effekt)
greifen ueber denselben effect_live-Dispatcher in den laufenden Effekt ein.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.core.engine.function_manager import get_function_manager
from src.core.engine.rgb_matrix import RgbMatrixInstance, RgbAlgorithm, ColorSequence


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


class VcEffectLiveTest(unittest.TestCase):

    def setUp(self):
        _app()
        self.fm = get_function_manager()
        self.fm.stop_all()
        self.m = RgbMatrixInstance(name="vc", cols=4, rows=1,
                                   algorithm=RgbAlgorithm.CHASE, fixture_grid=[1, 2, 3, 4])
        self.fm.add(self.m)

    def tearDown(self):
        self.fm.stop_all()
        self.fm.remove(self.m.id)

    def test_slider_effect_param_live(self):
        from src.ui.virtualconsole.vc_slider import VCSlider, SliderMode
        s = VCSlider("Speed")
        s.mode = SliderMode.EFFECT_PARAM
        s.param_key = "speed"
        s.function_id = self.m.id
        s.value = 255
        self.assertGreater(self.m.matrix_speed, 15)   # Fader oben → ~max
        s.value = 0
        self.assertLess(self.m.matrix_speed, 1.0)      # Fader unten → ~min

    def test_slider_effect_param_fill_speed(self):
        from src.ui.virtualconsole.vc_slider import VCSlider, SliderMode
        self.m.algorithm = RgbAlgorithm.FILL
        s = VCSlider("Fill")
        s.mode = SliderMode.EFFECT_PARAM
        s.param_key = "fill_speed"        # WP-3: Fill ist zeitbasiert (kein 'level' mehr)
        s.function_id = self.m.id
        s.value = 128
        self.assertTrue(4.5 <= self.m.params.get("fill_speed", 0) <= 5.5)

    def test_button_effect_action(self):
        from src.ui.virtualconsole.vc_button import VCButton, ButtonAction
        self.m.colors = ColorSequence([(255, 0, 0)])
        b = VCButton("Add")
        b.action = ButtonAction.EFFECT_ACTION
        b.effect_action_key = "add_color"
        b.function_id = self.m.id
        b._trigger(True)
        self.assertEqual(len(self.m.colors), 2)

    def test_color_target_effect(self):
        from src.ui.virtualconsole.vc_color import VCColor, ColorTarget
        self.m.colors = ColorSequence([(255, 0, 0), (0, 0, 255)])
        self.m.colors.active_index = 0
        c = VCColor("Pick")
        c.target = ColorTarget.EFFECT
        c.function_id = self.m.id
        c.color_r, c.color_g, c.color_b = 1, 2, 3
        c._apply()
        self.assertEqual(self.m.colors.color_at(0), (1, 2, 3))

    def test_color_target_effect_add(self):
        """ColorTarget.EFFECT_ADD haengt die Farbe an die Sequence an (Live-Color-Chase):
        mehrere Farb-Pads nacheinander druecken -> Farbliste waechst in Reihenfolge."""
        from src.ui.virtualconsole.vc_color import VCColor, ColorTarget
        self.m.colors = ColorSequence([(255, 0, 0)])
        c = VCColor("Add")
        c.target = ColorTarget.EFFECT_ADD
        c.function_id = self.m.id
        c.color_r, c.color_g, c.color_b = 0, 255, 0
        c._apply()
        c.color_r, c.color_g, c.color_b = 0, 0, 255
        c._apply()
        self.assertEqual(self.m.colors.all_colors(),
                         [(255, 0, 0), (0, 255, 0), (0, 0, 255)])

    def test_color_target_effect_slots(self):
        """To-Do #5: ColorTarget.EFFECT_C1/C2/C3 setzen gezielt color1/2/3 des
        Effekts — fuer Algorithmen, die feste Farben lesen (Feuer/Plasma/Windrad),
        wo die Color-Sequence-Variante (EFFECT) nichts bewirkt."""
        from src.ui.virtualconsole.vc_color import VCColor, ColorTarget
        self.m.algorithm = RgbAlgorithm.FIRE
        for tgt, slot in ((ColorTarget.EFFECT_C1, "color1"),
                          (ColorTarget.EFFECT_C2, "color2"),
                          (ColorTarget.EFFECT_C3, "color3")):
            c = VCColor("Slot")
            c.target = tgt
            c.function_id = self.m.id
            c.color_r, c.color_g, c.color_b = 11, 22, 33
            c._apply()
            self.assertEqual(getattr(self.m, slot), (11, 22, 33))

    def test_color_slot_serialization_roundtrip(self):
        from src.ui.virtualconsole.vc_color import VCColor, ColorTarget
        c = VCColor("X")
        c.target = ColorTarget.EFFECT_C2
        c.function_id = 7
        c2 = VCColor("Y")
        c2.apply_dict(c.to_dict())
        self.assertEqual(c2.target, ColorTarget.EFFECT_C2)
        self.assertEqual(c2.function_id, 7)

    def test_slider_serialization_roundtrip(self):
        from src.ui.virtualconsole.vc_slider import VCSlider, SliderMode
        s = VCSlider("X")
        s.mode = SliderMode.EFFECT_PARAM
        s.param_key = "level"
        s2 = VCSlider("Y")
        s2.apply_dict(s.to_dict())
        self.assertEqual(s2.mode, SliderMode.EFFECT_PARAM)
        self.assertEqual(s2.param_key, "level")

    def test_button_serialization_roundtrip(self):
        from src.ui.virtualconsole.vc_button import VCButton, ButtonAction
        b = VCButton("X")
        b.action = ButtonAction.EFFECT_ACTION
        b.effect_action_key = "toggle_freeze"
        b2 = VCButton("Y")
        b2.apply_dict(b.to_dict())
        self.assertEqual(b2.action, ButtonAction.EFFECT_ACTION)
        self.assertEqual(b2.effect_action_key, "toggle_freeze")

    def test_slider_autostart_starts_and_stops_effect(self):
        """effect_autostart=True: Fader > 0 startet den Effekt, Fader 0 stoppt ihn."""
        from src.ui.virtualconsole.vc_slider import VCSlider, SliderMode
        s = VCSlider("Master")
        s.mode = SliderMode.EFFECT_INTENSITY
        s.function_id = self.m.id
        s.effect_autostart = True
        self.assertFalse(self.fm.is_running(self.m.id))
        s.value = 200                       # > 0 -> startet den Effekt
        self.assertTrue(self.fm.is_running(self.m.id))
        s.value = 0                         # 0 -> stoppt den Effekt wirklich
        self.assertFalse(self.fm.is_running(self.m.id))

    def test_slider_without_autostart_only_regulates(self):
        """Default (effect_autostart=False): Fader regelt nur, stoppt bei 0 NICHT."""
        from src.ui.virtualconsole.vc_slider import VCSlider, SliderMode
        s = VCSlider("Master")
        s.mode = SliderMode.EFFECT_INTENSITY
        s.function_id = self.m.id
        s.effect_autostart = False
        s.value = 200
        self.assertFalse(self.fm.is_running(self.m.id))  # startet NICHT von allein
        self.fm.start(self.m.id)
        s.value = 0
        self.assertTrue(self.fm.is_running(self.m.id))    # bei 0 NICHT gestoppt

    def test_autostart_serialization_roundtrip(self):
        from src.ui.virtualconsole.vc_slider import VCSlider, SliderMode
        s = VCSlider("X")
        s.mode = SliderMode.EFFECT_INTENSITY
        s.effect_autostart = True
        s2 = VCSlider("Y")
        s2.apply_dict(s.to_dict())
        self.assertTrue(s2.effect_autostart)


if __name__ == "__main__":
    unittest.main()
