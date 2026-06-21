"""Smart-Drop: Fundament-Tests (Faehigkeiten + Optionen, Qt-frei).

Die reine Logik in ``vc_effect_meta`` (classify_drop / function_capabilities /
control_options / widget_choices) wird ohne Qt getestet. Dialog- und
Canvas-Verdrahtungstests folgen in WS1.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.engine.function_manager import get_function_manager
from src.core.engine.rgb_matrix import RgbMatrixInstance, RgbAlgorithm, MatrixStyle
from src.core.engine.efx import EfxInstance
from src.core.engine.scene import Scene

from src.ui.virtualconsole.vc_effect_meta import (
    DropKind, classify_drop, function_capabilities,
    control_options, widget_choices, recommended_widget, ControlKind, ControlOption,
)

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPoint


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


class ClassifyDropTest(unittest.TestCase):

    def test_classify(self):
        self.assertEqual(classify_drop(function_id=5), DropKind.FUNCTION)
        self.assertEqual(classify_drop(snapshot_index=2), DropKind.SNAPSHOT)
        self.assertEqual(classify_drop(snap_id=7), DropKind.SNAP)
        self.assertEqual(classify_drop(), DropKind.UNKNOWN)


class CapabilitiesTest(unittest.TestCase):

    def setUp(self):
        self.fm = get_function_manager()
        self.fm.stop_all()
        self.m = RgbMatrixInstance(name="cap-matrix", cols=4, rows=1,
                                   algorithm=RgbAlgorithm.CHASE, fixture_grid=[1, 2, 3, 4])
        self.fm.add(self.m)
        self.sc = Scene("cap-scene")
        self.fm.add(self.sc)

    def tearDown(self):
        self.fm.stop_all()
        self.fm.remove(self.m.id)
        self.fm.remove(self.sc.id)

    def test_matrix_caps(self):
        caps = function_capabilities(self.m.id)
        self.assertEqual(caps.function_id, self.m.id)
        self.assertEqual(caps.function_type, "RGBMatrix")
        self.assertTrue(caps.has_params)
        self.assertTrue(caps.has_speed)
        self.assertTrue(caps.has_intensity)
        self.assertTrue(caps.has_colors)          # CHASE nutzt die Farbliste
        self.assertTrue(caps.is_tempo_syncable)   # tempo_bus_id-Param vorhanden
        self.assertTrue(caps.actions)             # next_color etc.

    def test_scene_caps(self):
        caps = function_capabilities(self.sc.id)
        self.assertEqual(caps.function_type, "Scene")
        self.assertFalse(caps.has_params)
        self.assertFalse(caps.has_colors)
        self.assertFalse(caps.is_tempo_syncable)

    def test_bad_id(self):
        caps = function_capabilities(None)
        self.assertIsNone(caps.function_id)
        self.assertFalse(caps.has_params)


class ControlOptionsTest(unittest.TestCase):

    def setUp(self):
        self.fm = get_function_manager()
        self.fm.stop_all()
        self.m = RgbMatrixInstance(name="opt-matrix", cols=4, rows=1,
                                   algorithm=RgbAlgorithm.CHASE, fixture_grid=[1, 2, 3, 4])
        self.fm.add(self.m)
        self.sc = Scene("opt-scene")
        self.fm.add(self.sc)

    def tearDown(self):
        self.fm.stop_all()
        self.fm.remove(self.m.id)
        self.fm.remove(self.sc.id)

    def test_matrix_options(self):
        opts = control_options(function_capabilities(self.m.id))
        kinds = {o.kind for o in opts}
        self.assertIn(ControlKind.TOGGLE, kinds)
        self.assertIn(ControlKind.FLASH, kinds)
        self.assertIn(ControlKind.TEMPO, kinds)
        self.assertIn(ControlKind.INTENSITY, kinds)
        self.assertIn(ControlKind.COLORS, kinds)
        self.assertIn(ControlKind.TEMPO_BUS, kinds)
        self.assertIn(ControlKind.PARAM, kinds)
        self.assertIn(ControlKind.ACTION, kinds)
        self.assertIn(ControlKind.BULK, kinds)
        # Jede PARAM-Option traegt einen konkreten param_key.
        for o in opts:
            if o.kind == ControlKind.PARAM:
                self.assertTrue(o.param_key)
            if o.kind == ControlKind.ACTION:
                self.assertTrue(o.action_key)

    def test_scene_options_only_toggle_flash(self):
        opts = control_options(function_capabilities(self.sc.id))
        kinds = [o.kind for o in opts]
        self.assertEqual(kinds, [ControlKind.TOGGLE, ControlKind.FLASH])

    def test_widget_choices(self):
        self.assertEqual(widget_choices(_opt(ControlKind.TEMPO)), ["VCSpeedDial", "VCSlider"])
        self.assertEqual(widget_choices(_opt(ControlKind.INTENSITY)), ["VCSlider", "VCEncoder"])
        self.assertEqual(widget_choices(_opt(ControlKind.PARAM)), ["VCSlider", "VCEncoder"])
        self.assertEqual(widget_choices(_opt(ControlKind.COLORS)), ["VCEffectColors"])
        self.assertEqual(widget_choices(_opt(ControlKind.TEMPO_BUS)), ["VCBusSelector"])
        self.assertEqual(widget_choices(_opt(ControlKind.TOGGLE)), ["VCButton"])
        self.assertEqual(widget_choices(_opt(ControlKind.ACTION)), ["VCButton"])
        self.assertEqual(widget_choices(_opt(ControlKind.BULK)), [])

    def test_widget_choices_param_kind_aware(self):
        """H/„vom Widget": die Param-Art bestimmt die angebotenen Widgets."""
        from src.ui.virtualconsole.vc_effect_meta import (
            ControlOption, ControlKind, recommended_widget)
        small_int = ControlOption(ControlKind.PARAM, "P", param_key="runner_count",
                                  param_kind="int", param_small_int=True)
        big_int = ControlOption(ControlKind.PARAM, "P", param_key="level",
                                param_kind="int", param_small_int=False)
        flt = ControlOption(ControlKind.PARAM, "P", param_key="density", param_kind="float")
        # Zähler (kleiner int): Stepper als Default
        self.assertEqual(widget_choices(small_int), ["VCStepper", "VCEncoder", "VCSlider"])
        self.assertEqual(recommended_widget(small_int), "VCStepper")
        # großer int: Slider-Default, Stepper als Alternative
        self.assertEqual(widget_choices(big_int), ["VCSlider", "VCEncoder", "VCStepper"])
        # float: KEIN Stepper
        self.assertEqual(widget_choices(flt), ["VCSlider", "VCEncoder"])
        self.assertEqual(recommended_widget(flt), "VCSlider")


def _opt(kind):
    from src.ui.virtualconsole.vc_effect_meta import ControlOption
    return ControlOption(kind, kind)


class SmartResultMappingTest(unittest.TestCase):
    """SmartDropDialog._result_for: Option+Widget-Typ -> SmartDropResult (ohne GUI)."""

    def setUp(self):
        _app()
        self.fm = get_function_manager()
        self.fm.stop_all()
        self.m = RgbMatrixInstance(name="map", cols=4, rows=1,
                                   algorithm=RgbAlgorithm.CHASE, fixture_grid=[1, 2, 3, 4])
        self.fm.add(self.m)

    def tearDown(self):
        self.fm.stop_all()
        self.fm.remove(self.m.id)

    def _dlg(self):
        from src.ui.virtualconsole.smart_drop_dialog import SmartDropDialog
        return SmartDropDialog(self.m.id)

    def test_tempo_slider(self):
        from src.ui.virtualconsole.vc_slider import SliderMode
        r = self._dlg()._result_for(ControlOption(ControlKind.TEMPO, "Tempo"), "VCSlider", "x")
        self.assertEqual(r.widget_type, "VCSlider")
        self.assertEqual(r.slider_mode, SliderMode.EFFECT_SPEED)

    def test_tempo_speeddial(self):
        r = self._dlg()._result_for(ControlOption(ControlKind.TEMPO, "Tempo"), "VCSpeedDial", "x")
        self.assertEqual(r.widget_type, "VCSpeedDial")

    def test_colors_maps_to_effect_colors(self):
        r = self._dlg()._result_for(ControlOption(ControlKind.COLORS, "Farben"), "VCEffectColors", "x")
        self.assertEqual(r.widget_type, "VCEffectColors")

    def test_tempo_bus_maps_to_selector(self):
        r = self._dlg()._result_for(ControlOption(ControlKind.TEMPO_BUS, "Bus"), "VCBusSelector", "x")
        self.assertEqual(r.widget_type, "VCBusSelector")

    def test_action_maps(self):
        from src.ui.virtualconsole.vc_button import ButtonAction
        r = self._dlg()._result_for(
            ControlOption(ControlKind.ACTION, "Aktion", action_key="next_color"), "VCButton", "x")
        self.assertEqual(r.action, ButtonAction.EFFECT_ACTION)
        self.assertEqual(r.effect_action_key, "next_color")

    def test_param_encoder(self):
        r = self._dlg()._result_for(
            ControlOption(ControlKind.PARAM, "Parameter: X", param_key="offset"), "VCEncoder", "x")
        self.assertEqual(r.widget_type, "VCEncoder")
        self.assertEqual(r.param_key, "offset")

    def test_movement_maps_to_xypad(self):
        r = self._dlg()._result_for(
            ControlOption(ControlKind.MOVEMENT, "Bewegung"), "VCXYPad", "x")
        self.assertEqual(r.widget_type, "VCXYPad")


class SmartDropBuildTest(unittest.TestCase):
    """VCCanvas._build_from_smart_result erzeugt vorverdrahtete Widgets."""

    def setUp(self):
        _app()
        self.fm = get_function_manager()
        self.fm.stop_all()
        self.m = RgbMatrixInstance(name="build", cols=4, rows=1,
                                   algorithm=RgbAlgorithm.CHASE, fixture_grid=[1, 2, 3, 4])
        self.fm.add(self.m)
        from src.ui.virtualconsole.vc_canvas import VCCanvas
        self.canvas = VCCanvas()
        self.canvas.set_edit_mode(True)

    def tearDown(self):
        self.fm.stop_all()
        self.fm.remove(self.m.id)

    def _res(self, **kw):
        from src.ui.virtualconsole.smart_drop_dialog import SmartDropResult
        kw.setdefault("function_id", self.m.id)
        return SmartDropResult(**kw)

    def test_build_button(self):
        from src.ui.virtualconsole.vc_button import VCButton, ButtonAction
        self.canvas._build_from_smart_result(
            self._res(widget_type="VCButton", action=ButtonAction.FUNCTION_TOGGLE), QPoint(10, 10))
        btns = self.canvas.findChildren(VCButton)
        self.assertEqual(len(btns), 1)
        self.assertEqual(btns[0].action, ButtonAction.FUNCTION_TOGGLE)
        self.assertEqual(btns[0].function_id, self.m.id)

    def test_build_slider(self):
        from src.ui.virtualconsole.vc_slider import VCSlider, SliderMode
        self.canvas._build_from_smart_result(
            self._res(widget_type="VCSlider", slider_mode=SliderMode.EFFECT_SPEED), QPoint(10, 10))
        sl = self.canvas.findChildren(VCSlider)
        self.assertEqual(len(sl), 1)
        self.assertEqual(sl[0].mode, SliderMode.EFFECT_SPEED)
        self.assertEqual(sl[0].function_id, self.m.id)

    def test_build_effect_colors(self):
        from src.ui.virtualconsole.vc_effect_colors import VCEffectColors
        self.canvas._build_from_smart_result(self._res(widget_type="VCEffectColors"), QPoint(10, 10))
        w = self.canvas.findChildren(VCEffectColors)
        self.assertEqual(len(w), 1)
        self.assertEqual(w[0].function_id, self.m.id)

    def test_build_bus_selector(self):
        from src.ui.virtualconsole.vc_bus_selector import VCBusSelector
        self.canvas._build_from_smart_result(self._res(widget_type="VCBusSelector"), QPoint(10, 10))
        self.assertEqual(len(self.canvas.findChildren(VCBusSelector)), 1)

    def test_build_bulk_creates_controls(self):
        from src.ui.virtualconsole.vc_slider import VCSlider
        self.canvas._build_from_smart_result(self._res(widget_type="BULK"), QPoint(10, 10))
        self.assertGreaterEqual(len(self.canvas.findChildren(VCSlider)), 1)

    def test_apply_drop_non_interactive_regression(self):
        from src.ui.virtualconsole.vc_button import VCButton, ButtonAction
        self.canvas.apply_drop(function_id=self.m.id, pos=QPoint(20, 20), target=None)
        btns = self.canvas.findChildren(VCButton)
        self.assertEqual(len(btns), 1)
        self.assertEqual(btns[0].action, ButtonAction.FUNCTION_TOGGLE)

    def test_build_xypad_movement(self):
        from src.ui.virtualconsole.vc_xypad import VCXYPad
        self.canvas._build_from_smart_result(self._res(widget_type="VCXYPad"), QPoint(10, 10))
        pads = self.canvas.findChildren(VCXYPad)
        self.assertEqual(len(pads), 1)
        self.assertEqual(pads[0].mode, "area")
        self.assertEqual(pads[0].efx_function_id, self.m.id)


class StyleAwareColorsTest(unittest.TestCase):
    """Style-Korrektheit: Dimmer/Shutter-Matrix bietet KEINEN Farb-Aspekt mehr
    (auch wenn der Algorithmus colors>0 meldet) — sie behandelt die Farbliste als
    reine Intensitaet. RGB/RGBW behalten den Farb-Aspekt."""

    def setUp(self):
        self.fm = get_function_manager()
        self.fm.stop_all()
        self.m = RgbMatrixInstance(name="style-matrix", cols=4, rows=1,
                                   algorithm=RgbAlgorithm.CHASE, fixture_grid=[1, 2, 3, 4])
        self.fm.add(self.m)

    def tearDown(self):
        self.fm.stop_all()
        self.fm.remove(self.m.id)

    def test_rgb_style_has_colors(self):
        self.m.style = MatrixStyle.RGB
        caps = function_capabilities(self.m.id)
        self.assertTrue(caps.has_colors)
        self.assertIn(ControlKind.COLORS, {o.kind for o in control_options(caps)})

    def test_dimmer_style_no_colors(self):
        self.m.style = MatrixStyle.DIMMER
        caps = function_capabilities(self.m.id)
        self.assertFalse(caps.has_colors)
        self.assertNotIn(ControlKind.COLORS, {o.kind for o in control_options(caps)})
        self.assertTrue(caps.has_speed)   # Tempo bleibt — nur "Farben" faellt weg

    def test_shutter_style_no_colors(self):
        self.m.style = MatrixStyle.SHUTTER
        self.assertFalse(function_capabilities(self.m.id).has_colors)


class MovementAspectTest(unittest.TestCase):
    """EFX exponiert Pan/Tilt-Bewegung -> MOVEMENT-Aspekt + XY-Feld; andere
    Funktionstypen (Matrix) bieten keine Bewegung."""

    def setUp(self):
        self.fm = get_function_manager()
        self.fm.stop_all()
        self.efx = EfxInstance("move-efx")
        self.fm.add(self.efx)
        self.m = RgbMatrixInstance(name="move-matrix", cols=4, rows=1,
                                   algorithm=RgbAlgorithm.CHASE, fixture_grid=[1, 2, 3, 4])
        self.fm.add(self.m)

    def tearDown(self):
        self.fm.stop_all()
        self.fm.remove(self.efx.id)
        self.fm.remove(self.m.id)

    def test_efx_has_movement(self):
        caps = function_capabilities(self.efx.id)
        self.assertEqual(caps.function_type, "EFX")
        self.assertTrue(caps.has_movement)
        self.assertIn(ControlKind.MOVEMENT, {o.kind for o in control_options(caps)})

    def test_matrix_no_movement(self):
        caps = function_capabilities(self.m.id)
        self.assertFalse(caps.has_movement)
        self.assertNotIn(ControlKind.MOVEMENT, {o.kind for o in control_options(caps)})

    def test_movement_widget_choice(self):
        self.assertEqual(widget_choices(_opt(ControlKind.MOVEMENT)), ["VCXYPad"])


class TempoSubFormTest(unittest.TestCase):
    """Tempo-Unterformen als eigene Auswahl: Tempo / Tempo-Bus / Tempo-Multiplikator
    sind getrennte Optionen; der Multiplikator baut ein vorkonfiguriertes Speed-Rad
    (SpeedTarget.TEMPO_BUS_MULT) ohne Nach-Umstellen."""

    def setUp(self):
        _app()
        self.fm = get_function_manager()
        self.fm.stop_all()
        self.m = RgbMatrixInstance(name="mult", cols=4, rows=1,
                                   algorithm=RgbAlgorithm.CHASE, fixture_grid=[1, 2, 3, 4])
        self.fm.add(self.m)

    def tearDown(self):
        self.fm.stop_all()
        self.fm.remove(self.m.id)

    def test_mult_is_its_own_option(self):
        kinds = {o.kind for o in control_options(function_capabilities(self.m.id))}
        self.assertIn(ControlKind.TEMPO, kinds)
        self.assertIn(ControlKind.TEMPO_BUS, kinds)
        self.assertIn(ControlKind.TEMPO_MULT, kinds)

    def test_mult_widget_is_speeddial(self):
        self.assertEqual(widget_choices(_opt(ControlKind.TEMPO_MULT)), ["VCSpeedDial"])
        self.assertEqual(recommended_widget(_opt(ControlKind.TEMPO_MULT)), "VCSpeedDial")

    def test_mult_result_preconfigured(self):
        from src.ui.virtualconsole.smart_drop_dialog import SmartDropDialog
        from src.ui.virtualconsole.vc_speedial import SpeedTarget
        r = SmartDropDialog(self.m.id)._result_for(
            ControlOption(ControlKind.TEMPO_MULT, "Mult"), "VCSpeedDial", "x")
        self.assertEqual(r.widget_type, "VCSpeedDial")
        self.assertEqual(r.speed_target, SpeedTarget.TEMPO_BUS_MULT)

    def test_mult_builds_speeddial_in_mult_mode(self):
        from src.ui.virtualconsole.smart_drop_dialog import SmartDropResult
        from src.ui.virtualconsole.vc_speedial import VCSpeedDial, SpeedTarget
        from src.ui.virtualconsole.vc_canvas import VCCanvas
        canvas = VCCanvas()
        canvas.set_edit_mode(True)
        canvas._build_from_smart_result(
            SmartDropResult(widget_type="VCSpeedDial", function_id=self.m.id,
                            speed_target=SpeedTarget.TEMPO_BUS_MULT), QPoint(10, 10))
        dials = canvas.findChildren(VCSpeedDial)
        self.assertEqual(len(dials), 1)
        self.assertEqual(dials[0].target_mode, SpeedTarget.TEMPO_BUS_MULT)
        self.assertEqual(dials[0].function_id, self.m.id)


class RecommendedWidgetTest(unittest.TestCase):
    """recommended_widget = erster Vorschlag aus widget_choices (Default fuer die
    Drop-Karte); BULK hat keinen Einzel-Typ."""

    def test_defaults(self):
        self.assertEqual(recommended_widget(_opt(ControlKind.TEMPO)), "VCSpeedDial")
        self.assertEqual(recommended_widget(_opt(ControlKind.INTENSITY)), "VCSlider")
        self.assertEqual(recommended_widget(_opt(ControlKind.PARAM)), "VCSlider")
        self.assertEqual(recommended_widget(_opt(ControlKind.COLORS)), "VCEffectColors")
        self.assertEqual(recommended_widget(_opt(ControlKind.MOVEMENT)), "VCXYPad")
        self.assertEqual(recommended_widget(_opt(ControlKind.TEMPO_BUS)), "VCBusSelector")
        self.assertEqual(recommended_widget(_opt(ControlKind.TOGGLE)), "VCButton")
        self.assertEqual(recommended_widget(_opt(ControlKind.BULK)), "BULK")


if __name__ == "__main__":
    unittest.main()
