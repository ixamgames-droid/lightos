"""UI-13 — VC-Button-Politur: quadratische Default-Groesse, Farb-/Effekt-Vorschau-
Badge (oben rechts) und RGBW-Weiss-Erkennung.

David: Buttons sollen quadratisch (Pad-Look wie Demo-Show) angelegt werden; ein
Farb-Effekt/-Snap soll oben rechts eine kleine Farbvorschau zeigen (Farbwechsel =
animiertes Eck-Icon); und reines RGBW-Weiss (W=255, RGB=0) darf NICHT mehr als
schwarzer Knopf erscheinen.
"""
import os
import types
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.core import color_utils
from src.core.app_state import get_state
from src.ui.virtualconsole.vc_button import VCButton, ButtonAction, DEFAULT_BUTTON_SIZE
from src.ui.virtualconsole.vc_color import VCColor, ColorTarget

_app = QApplication.instance() or QApplication([])


class ColorUtilsDisplayTest(unittest.TestCase):
    """Der zentrale Qt-freie Helfer: W additiv zurueck in die Anzeige-RGB falten."""

    def test_pure_white_w_channel_is_white(self):
        self.assertEqual(color_utils.rgbw_to_display(0, 0, 0, 255), (255, 255, 255))

    def test_rgb_without_white_unchanged(self):
        self.assertEqual(color_utils.rgbw_to_display(255, 0, 0, 0), (255, 0, 0))

    def test_white_fold_clamps(self):
        self.assertEqual(color_utils.rgbw_to_display(200, 200, 200, 200), (255, 255, 255))

    def test_attrs_no_color_returns_default(self):
        self.assertIsNone(color_utils.display_rgb_from_attrs({"intensity": 255}))
        self.assertEqual(color_utils.display_rgb_from_attrs({}, default=(1, 2, 3)), (1, 2, 3))

    def test_attrs_white_only_is_white(self):
        self.assertEqual(
            color_utils.display_rgb_from_attrs({"color_r": 0, "color_g": 0,
                                                "color_b": 0, "color_w": 255}),
            (255, 255, 255))

    def test_attrs_plain_rgb(self):
        self.assertEqual(
            color_utils.display_rgb_from_attrs({"color_r": 255, "color_g": 0, "color_b": 0}),
            (255, 0, 0))


class DefaultSquareSizeTest(unittest.TestCase):
    """Neu angelegte Buttons sind quadratisch (Standard-Pad-Groesse)."""

    def test_new_button_is_square(self):
        b = VCButton("Pad")
        self.assertEqual(b.width(), b.height())
        self.assertEqual(b.width(), DEFAULT_BUTTON_SIZE)


class SnapSwatchWhiteTest(unittest.TestCase):
    """LIBRARY_SNAP-Swatch (unterer Farbbalken + Badge) faltet den Weiss-Kanal."""

    def _btn_with_snap(self, attrs):
        b = VCButton("Snap")
        b.action = ButtonAction.LIBRARY_SNAP
        b.snap_id = 1
        fake = types.SimpleNamespace(values={1: attrs})
        b._library_snaps = lambda: [fake]   # type: ignore[assignment]
        return b

    def test_white_snap_not_black(self):
        b = self._btn_with_snap({"color_r": 0, "color_g": 0, "color_b": 0, "color_w": 255})
        c = b._snap_swatch_color()
        self.assertIsNotNone(c)
        self.assertEqual((c.red(), c.green(), c.blue()), (255, 255, 255))

    def test_red_snap_unchanged(self):
        b = self._btn_with_snap({"color_r": 255, "color_g": 0, "color_b": 0})
        c = b._snap_swatch_color()
        self.assertEqual((c.red(), c.green(), c.blue()), (255, 0, 0))

    def test_badge_from_white_snap(self):
        b = self._btn_with_snap({"color_r": 0, "color_g": 0, "color_b": 0, "color_w": 255})
        cols = b._color_badge_colors()
        self.assertEqual(len(cols), 1)
        self.assertEqual((cols[0].red(), cols[0].green(), cols[0].blue()), (255, 255, 255))


class EffectColorBadgeTest(unittest.TestCase):
    """Farb-Badge aus der Color-Sequence eines gebundenen Farb-Effekts."""

    def setUp(self):
        self.fm = get_state().function_manager
        self.fn = self.fm.new_rgb_matrix("BadgeMatrix")

    def tearDown(self):
        try:
            self.fm.remove(self.fn.id)
        except Exception:
            pass

    def test_multi_color_effect_yields_all_colors(self):
        b = VCButton("FX")
        b.action = ButtonAction.FUNCTION_TOGGLE
        b.function_id = self.fn.id
        cols = b._color_badge_colors()
        # Frische Matrix hat 3 Default-Farben -> 3 Badge-Farben.
        self.assertEqual(len(cols), 3)

    def test_cycle_advances_and_wraps(self):
        b = VCButton("FX")
        b.action = ButtonAction.FUNCTION_TOGGLE
        b.function_id = self.fn.id
        b._color_badge_colors()
        self.assertEqual(b._badge_index, 0)
        b._advance_badge()
        self.assertEqual(b._badge_index, 1)
        b._advance_badge(); b._advance_badge()   # wrap 2 -> 0
        self.assertEqual(b._badge_index, 0)

    def test_single_color_does_not_cycle(self):
        # Sequence auf eine Farbe reduzieren -> kein Wechsel.
        from src.core.engine.rgb_matrix import ColorSequence
        self.fn.colors = ColorSequence([(10, 20, 30)])
        b = VCButton("FX")
        b.action = ButtonAction.FUNCTION_TOGGLE
        b.function_id = self.fn.id
        cols = b._color_badge_colors()
        self.assertEqual(len(cols), 1)
        b._advance_badge()
        self.assertEqual(b._badge_index, 0)

    def test_non_color_effect_has_no_badge(self):
        # has_colors=False (Dimmer-/Shutter-Style) -> kein Farb-Badge.
        import src.ui.virtualconsole.vc_button as vb
        orig = vb.VCButton._resolve_badge_colors
        try:
            import src.ui.virtualconsole.vc_effect_meta as vem
            orig_caps = vem.function_capabilities
            vem.function_capabilities = lambda fid: types.SimpleNamespace(has_colors=False)
            try:
                b = VCButton("FX")
                b.action = ButtonAction.FUNCTION_TOGGLE
                b.function_id = self.fn.id
                self.assertEqual(b._color_badge_colors(), [])
            finally:
                vem.function_capabilities = orig_caps
        finally:
            vb.VCButton._resolve_badge_colors = orig

    def test_plain_action_has_no_badge(self):
        b = VCButton("BO")
        b.action = ButtonAction.BLACKOUT
        self.assertEqual(b._color_badge_colors(), [])


class VCColorEffectWhiteFoldTest(unittest.TestCase):
    """Eine als RGBW-Weiss definierte Kachel sendet WEISS (nicht schwarz) an einen
    Effekt-Farb-Slot — sonst war der „Effekt mit Weiss" schwarz."""

    def _capture_setparam(self):
        captured = {}
        import src.core.engine.effect_live as el
        orig = el.set_param

        def fake(key, value, function_id=None):
            captured["key"] = key
            captured["value"] = value
            return True

        el.set_param = fake
        self.addCleanup(lambda: setattr(el, "set_param", orig))
        return captured

    def test_white_swatch_folds_to_white(self):
        captured = self._capture_setparam()
        cc = VCColor("Weiss")
        cc.color_r, cc.color_g, cc.color_b, cc.color_w = 0, 0, 0, 255
        cc.target = ColorTarget.EFFECT_C1
        cc._apply()
        self.assertEqual(captured.get("value"), (255, 255, 255))

    def test_red_swatch_unchanged(self):
        captured = self._capture_setparam()
        cc = VCColor("Rot")
        cc.color_r, cc.color_g, cc.color_b, cc.color_w = 255, 0, 0, 0
        cc.target = ColorTarget.EFFECT_C1
        cc._apply()
        self.assertEqual(captured.get("value"), (255, 0, 0))


if __name__ == "__main__":
    unittest.main()
