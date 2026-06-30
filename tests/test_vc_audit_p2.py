"""VC-Code-Audit P2-Robustheits-Fixes + UI-14b (Stand 2026-06-30).

- VCB-18: VCButton.apply_dict setzt den Snap-Toggle-Laufzeitzustand zurueck.
- VCB-21: apply_dict ignoriert korrupte Hex-Farben (isValid).
- VCB-22: apply_dict erzwingt MIN_SIZE (kein 0x0-Widget).
- VCB-23: VCSlider.apply_dict klemmt _value auf 0..255.
- VCB-27: VCSlider.apply_dict ueberlebt JSON-null bei range_min/max.
- UI-14b: VCCanvas.refresh_effect_badges loest die Badges gebundener Buttons neu auf.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPoint

from src.core.app_state import get_state
from src.core.engine.rgb_matrix import ColorSequence
from src.ui.virtualconsole.vc_button import VCButton, ButtonAction
from src.ui.virtualconsole.vc_slider import VCSlider
from src.ui.virtualconsole.vc_canvas import VCCanvas

_app = QApplication.instance() or QApplication([])


class ApplyDictRobustness(unittest.TestCase):
    def test_vcb21_invalid_hex_color_ignored(self):
        b = VCButton("x")
        orig = b._bg_color.name()
        b.apply_dict({"bg": "#zzzzzz"})          # ungueltig
        self.assertEqual(b._bg_color.name(), orig, "korrupte Farbe darf nicht greifen")
        b.apply_dict({"bg": "#ff0000"})          # gueltig
        self.assertEqual(b._bg_color.name().lower(), "#ff0000")

    def test_vcb22_zero_geometry_clamped_to_min_size(self):
        b = VCButton("x")
        b.apply_dict({"x": 0, "y": 0, "w": 0, "h": 0})
        mw, mh = VCButton.MIN_SIZE
        self.assertGreaterEqual(b.width(), mw)
        self.assertGreaterEqual(b.height(), mh)

    def test_vcb23_value_clamped(self):
        s = VCSlider("x")
        s.apply_dict({"value": 999})
        self.assertEqual(s._value, 255)
        s.apply_dict({"value": -5})
        self.assertEqual(s._value, 0)

    def test_vcb27_null_range_survives(self):
        s = VCSlider("x")
        try:
            s.apply_dict({"range_min": None, "range_max": None})   # JSON null
        except Exception as e:
            self.fail(f"apply_dict darf bei null-range nicht crashen: {e!r}")
        self.assertEqual(s.range_min, 0)
        self.assertEqual(s.range_max, 255)


class VCB18SnapStateReset(unittest.TestCase):
    def test_apply_dict_resets_snap_runtime_state(self):
        b = VCButton("x")
        b._snap_active = True
        b._snap_prev = {(1, "color_r"): 5}
        b.apply_dict({})
        self.assertFalse(b._snap_active)
        self.assertEqual(b._snap_prev, {})


class UI14bBadgeRepaintRefresh(unittest.TestCase):
    def setUp(self):
        self.fm = get_state().function_manager
        self.fn = self.fm.new_rgb_matrix("UI14bMatrix")

    def tearDown(self):
        try:
            self.fm.remove(self.fn.id)
        except Exception:
            pass

    def test_refresh_effect_badges_reresolves_bound_button(self):
        canvas = VCCanvas()
        b = canvas._add_widget("VCButton", QPoint(10, 10))
        b.action = ButtonAction.FUNCTION_TOGGLE
        b.function_id = self.fn.id
        first = b._color_badge_colors()
        self.assertEqual(len(first), 3, "frische Matrix -> 3 Default-Farben")
        # Live-Edit der Effekt-Sequence (ohne den Button anzufassen).
        self.fn.colors = ColorSequence([(10, 20, 30)])
        canvas.refresh_effect_badges(self.fn.id)
        self.assertEqual(len(b._badge_colors), 1,
                         "UI-14b: refresh_effect_badges muss das Badge des gebundenen "
                         "Buttons neu aufloesen (1 Farbe), nicht die 3 alten zeigen")

    def test_refresh_unrelated_fid_is_noop(self):
        canvas = VCCanvas()
        b = canvas._add_widget("VCButton", QPoint(10, 10))
        b.action = ButtonAction.FUNCTION_TOGGLE
        b.function_id = self.fn.id
        b._color_badge_colors()
        # Ein fremder fid darf den Button nicht anfassen (kein Crash, kein Effekt).
        canvas.refresh_effect_badges(999999)
        self.assertEqual(len(b._badge_colors), 3)


if __name__ == "__main__":
    unittest.main()
