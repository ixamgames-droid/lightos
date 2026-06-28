"""MLV-01/02: Matrix-Live-Editor in der Virtual Console.

- effekt-gebundene Widgets melden is_effect_bound()/live_effect_function_id(),
- der Dialog listet Parameter (Fader) + Aktionen (Tasten) und gibt die Auswahl,
- VCCanvas.add_live_controls() erzeugt daraus korrekt gebundene VC-Bedienelemente.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.core.engine.function_manager import get_function_manager
from src.core.engine.rgb_matrix import RgbMatrixInstance, RgbAlgorithm
from src.ui.virtualconsole.vc_canvas import VCCanvas
from src.ui.virtualconsole.vc_button import VCButton, ButtonAction
from src.ui.virtualconsole.vc_slider import VCSlider, SliderMode
from src.ui.virtualconsole.vc_stepper import VCStepper
from src.ui.widgets.matrix_live_dialog import MatrixLiveDialog

_app = QApplication.instance() or QApplication([])


class _Base(unittest.TestCase):
    def setUp(self):
        self.fm = get_function_manager()
        self.fm.stop_all()
        self.m = RgbMatrixInstance(name="LiveMatrix", cols=4, rows=1,
                                   algorithm=RgbAlgorithm.CHASE, fixture_grid=[1, 2, 3, 4])
        self.fm.add(self.m)
        self.fid = self.m.id

    def tearDown(self):
        self.fm.stop_all()
        self.fm.remove(self.m.id)


class EffectBindingTest(_Base):
    def test_button_effect_bound(self):
        b = VCButton()
        b.action = ButtonAction.FUNCTION_TOGGLE
        b.function_id = self.fid
        self.assertTrue(b.is_effect_bound())
        self.assertEqual(b.live_effect_function_id(), self.fid)

    def test_button_non_effect_not_bound(self):
        b = VCButton()
        b.action = ButtonAction.BLACKOUT
        self.assertFalse(b.is_effect_bound())

    def test_slider_effect_bound(self):
        s = VCSlider()
        s.mode = SliderMode.EFFECT_PARAM
        s.function_id = self.fid
        self.assertTrue(s.is_effect_bound())
        self.assertEqual(s.live_effect_function_id(), self.fid)


class DialogTest(_Base):
    def test_dialog_lists_params_and_actions(self):
        dlg = MatrixLiveDialog(self.fid)
        param_keys = [k for _cb, k in dlg._param_boxes]
        action_keys = [k for _cb, k in dlg._action_boxes]
        self.assertIn("speed", param_keys)      # universeller Fader-Param
        self.assertIn("next_color", action_keys)
        # Nichts wird automatisch erzeugt: der Nutzer waehlt bewusst.
        self.assertEqual(dlg.selected_param_keys(), [])

    def test_dialog_selection_reflects_checkboxes(self):
        dlg = MatrixLiveDialog(self.fid)
        for cb, key in dlg._param_boxes:
            cb.setChecked(key == "runner_count")
        for cb, key in dlg._action_boxes:
            cb.setChecked(key == "reverse_direction")
        self.assertEqual(dlg.selected_param_keys(), ["runner_count"])
        self.assertEqual(dlg.selected_action_keys(), ["reverse_direction"])


class AddLiveControlsTest(_Base):
    def test_creates_bound_widgets(self):
        canvas = VCCanvas()
        created = canvas.add_live_controls(
            self.fid, ["speed", "runner_count"], ["next_color", "tap"])
        sliders = [w for w in created if isinstance(w, VCSlider)]
        steppers = [w for w in created if isinstance(w, VCStepper)]
        buttons = [w for w in created if isinstance(w, VCButton)]
        self.assertEqual(len(sliders), 1)
        self.assertEqual(len(steppers), 1)
        self.assertEqual(len(buttons), 2)
        for s in sliders:
            self.assertEqual(s.mode, SliderMode.EFFECT_PARAM)
            self.assertEqual(s.function_id, self.fid)
        self.assertEqual({s.param_key for s in sliders}, {"speed"})
        self.assertEqual(steppers[0].param_key, "runner_count")
        self.assertEqual(steppers[0].function_id, self.fid)
        for b in buttons:
            self.assertEqual(b.action, ButtonAction.EFFECT_ACTION)
            self.assertEqual(b.function_id, self.fid)
        self.assertEqual({b.effect_action_key for b in buttons}, {"next_color", "tap"})

    def test_created_sliders_actually_drive_effect(self):
        # End-to-end: ein erzeugter EFFECT_PARAM-Fader setzt den Parameter live.
        canvas = VCCanvas()
        created = canvas.add_live_controls(self.fid, ["runner_count"], [])
        slider = next(w for w in created if isinstance(w, VCStepper))
        from src.core.engine import effect_live
        effect_live.set_param_normalized(slider.param_key, 1.0, slider.function_id)
        self.assertEqual(self.m.params["runner_count"], 16)   # max der Spec


class ContextMenuFlowTest(_Base):
    def test_open_live_editor_creates_controls_on_canvas(self):
        # Voller Pfad: Widget-Kontextmenu -> Dialog -> Canvas.add_live_controls.
        import src.ui.widgets.matrix_live_dialog as MLD
        from PySide6.QtWidgets import QDialog
        from src.ui.virtualconsole.vc_canvas import VCCanvas as _C  # noqa

        canvas = VCCanvas()
        from PySide6.QtCore import QPoint
        btn = canvas._add_widget("VCButton", QPoint(20, 20))
        btn.action = ButtonAction.FUNCTION_TOGGLE
        btn.function_id = self.fid
        self.assertTrue(btn.is_effect_bound())

        class _FakeDlg:
            def __init__(self, fid, parent=None):
                pass
            def exec(self):
                return QDialog.DialogCode.Accepted
            def selected_param_keys(self):
                return ["speed"]
            def selected_action_keys(self):
                return ["tap"]

        orig = MLD.MatrixLiveDialog
        MLD.MatrixLiveDialog = _FakeDlg
        try:
            btn._open_live_editor(self.fid)
        finally:
            MLD.MatrixLiveDialog = orig

        sliders = [w for w in canvas.findChildren(VCSlider)
                   if w.mode == SliderMode.EFFECT_PARAM and w.param_key == "speed"]
        buttons = [w for w in canvas.findChildren(VCButton)
                   if w.action == ButtonAction.EFFECT_ACTION and w.effect_action_key == "tap"]
        self.assertEqual(len(sliders), 1)
        self.assertEqual(len(buttons), 1)
        self.assertEqual(sliders[0].function_id, self.fid)


if __name__ == "__main__":
    unittest.main()
