"""VC-Code-Audit P3-Bugfixes (Stand 2026-06-30).

- VCB-24: VCWidget._teach_midi raeumt mit Sentinel-msg_type "none" (statt None).
- VCB-25: effect_live._spec_for faengt list_params()-Exceptions ab (-> None).
- VCB-26: VCColorList._hit_swatch spiegelt das gerundete Paint-Layout.
- VCB-28: VCSpeedDial.apply_dict wandelt _bpm robust nach float (alte String-Shows).
- VCB-29: VCCanvas.add_live_controls legt die Button-Reihe dynamisch unter die Fader.
- VCB-30: VCCanvas.replace_widget_type pusht Undo erst nach erfolgreichem _add_widget.
- VCB-31: VCButton._snap_binding_for_action leert snap_id beim Wechsel weg von LIBRARY_SNAP.
"""
import os
import types
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPoint

from src.core.engine import effect_live
from src.ui.virtualconsole.vc_button import VCButton, ButtonAction
from src.ui.virtualconsole.vc_slider import VCSlider
from src.ui.virtualconsole.vc_color_list import VCColorList
from src.ui.virtualconsole.vc_speedial import VCSpeedDial
from src.ui.virtualconsole.vc_canvas import VCCanvas

_app = QApplication.instance() or QApplication([])


class VCB24TeachMidiSentinel(unittest.TestCase):
    def test_clear_with_sentinel_msg_type(self):
        b = VCButton("b")
        b.midi_data1 = 5
        b.apply_midi_binding("none", 0, -1)         # Clear-Pfad (data1<0)
        self.assertEqual(b.midi_data1, -1)
        s = VCSlider("s")
        s.midi_cc = 7
        s.apply_midi_binding("none", 0, -1)
        self.assertEqual(s.midi_cc, -1)


class VCB25SpecForGuard(unittest.TestCase):
    def test_returns_none_on_list_params_error(self):
        class _Boom:
            def list_params(self):
                raise RuntimeError("boom")
        self.assertIsNone(effect_live._spec_for(_Boom(), "x"))

    def test_returns_spec_normally(self):
        class _OK:
            def list_params(self):
                return [types.SimpleNamespace(key="x"), types.SimpleNamespace(key="y")]
        spec = effect_live._spec_for(_OK(), "y")
        self.assertIsNotNone(spec)
        self.assertEqual(spec.key, "y")


class VCB26HitSwatchMirrorsPaint(unittest.TestCase):
    def _make(self, n):
        cl = VCColorList("cl")
        cl.resize(100, 40)               # area = (4,18,92,18); sw = 88/3 = 29.333 (n=3)
        fake = types.SimpleNamespace(colors=types.SimpleNamespace(entries=list(range(n))))
        cl._target = lambda: fake
        return cl

    def test_boundary_matches_painted_swatch(self):
        cl = self._make(3)
        # starts (gerundet wie paint): [4, 35, 67] -> Grenzen 35/67
        self.assertEqual(cl._hit_swatch(QPoint(20, 20)), 0)
        self.assertEqual(cl._hit_swatch(QPoint(50, 20)), 1)
        self.assertEqual(cl._hit_swatch(QPoint(80, 20)), 2)
        # x=35 ist die GERUNDETE Grenze zu Swatch 1 (alte Float-Division ergab 0):
        self.assertEqual(cl._hit_swatch(QPoint(35, 20)), 1)


class VCB28SpeedDialBpmCoercion(unittest.TestCase):
    def test_string_bpm_coerced(self):
        d = VCSpeedDial("sd")
        d.apply_dict({"bpm": "150"})
        self.assertEqual(d._bpm, 150.0)

    def test_bad_bpm_falls_back(self):
        d = VCSpeedDial("sd")
        d.apply_dict({"bpm": None})
        self.assertEqual(d._bpm, 120.0)
        d.apply_dict({"bpm": "garbage"})
        self.assertEqual(d._bpm, 120.0)


class VCB29LiveControlsDynamicOffset(unittest.TestCase):
    def test_button_row_below_actual_controls(self):
        orig = effect_live.list_params
        effect_live.list_params = lambda fid: [
            types.SimpleNamespace(key="b", label="B", kind="bool")]
        try:
            canvas = VCCanvas()
            created = canvas.add_live_controls(999, ["b"], ["act"])
        finally:
            effect_live.list_params = orig
        controls = [w for w in created if not isinstance(w, VCButton)]
        buttons = [w for w in created if isinstance(w, VCButton)]
        self.assertTrue(controls and buttons, "Stepper + Button muessen erzeugt werden")
        row_h = max(c.height() for c in controls)        # Stepper = 72, nicht 200
        self.assertEqual(buttons[0].y(),
                         controls[0].y() + row_h + canvas.GRID,
                         "VCB-29: Button-Reihe muss unter der TATSAECHLICHEN Faderhoehe liegen")


class VCB30ReplaceWidgetUndoOnSuccess(unittest.TestCase):
    def test_no_phantom_undo_on_failed_add(self):
        canvas = VCCanvas()
        w = canvas._add_widget("VCButton", QPoint(10, 10))
        depth = len(canvas._undo_stack)
        canvas._add_widget = lambda *a, **k: None        # _add_widget schlaegt fehl
        result = canvas.replace_widget_type(w, "VCSlider")
        self.assertIsNone(result)
        self.assertEqual(len(canvas._undo_stack), depth,
                         "VCB-30: fehlgeschlagener Typ-Tausch darf keinen Undo-Schritt pushen")


class VCB31SnapBindingForAction(unittest.TestCase):
    def test_library_snap_keeps_snaps(self):
        self.assertEqual(
            VCButton._snap_binding_for_action(ButtonAction.LIBRARY_SNAP, [5, 6, 7]),
            (5, [6, 7]))
        self.assertEqual(
            VCButton._snap_binding_for_action(ButtonAction.LIBRARY_SNAP, []),
            (None, []))

    def test_non_snap_action_clears(self):
        self.assertEqual(
            VCButton._snap_binding_for_action(ButtonAction.FUNCTION_TOGGLE, [5, 6]),
            (None, []),
            "VCB-31: Wechsel weg von LIBRARY_SNAP muss snap_id/snap_ids leeren")


if __name__ == "__main__":
    unittest.main()
