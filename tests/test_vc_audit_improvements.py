"""VC-Code-Audit Verbesserungen (VCI, Stand 2026-06-30).

Umgesetzt: VCI-01..08, VCI-10, VCI-11, VCI-12, VCI-14.
NICHT umgesetzt: VCI-09 (False-Positive — kein Loop/Closure in set_param_normalized),
VCI-13 (bewusst ausgelassen: _result_for ist Instanz-Methode mit vielen Callern;
ein statischer Umbau bricht den internen Caller + ~10 Tests fuer eine vernachlaessigbare
Einsparung einer Dialog-Konstruktion auf dem User-Drop-Pfad).
"""
import os
import types
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPoint

from src.core.engine import effect_live
from src.ui.virtualconsole import vc_effect_meta
from src.ui.virtualconsole.vc_color import VCColor, normalize_color_target, ColorTarget
from src.ui.virtualconsole.vc_slider import VCSlider, SliderMode
from src.ui.virtualconsole.vc_encoder import VCEncoder, EncoderMidiMode
from src.ui.virtualconsole.vc_button import VCButton, ButtonAction
from src.ui.virtualconsole.vc_canvas import VCCanvas
from src.ui.virtualconsole.vc_effect_meta import aspect_caption, ControlOption, ControlKind

_app = QApplication.instance() or QApplication([])


class VCI03ColorTargetWarn(unittest.TestCase):
    def test_unknown_returns_unchanged(self):
        self.assertEqual(normalize_color_target("Voellig Unbekannt"), "Voellig Unbekannt")

    def test_known_passthrough(self):
        self.assertEqual(normalize_color_target(ColorTarget.EFFECT), ColorTarget.EFFECT)


class VCI04EncoderMidiMode(unittest.TestCase):
    def test_invalid_mode_falls_back(self):
        e = VCEncoder("e")
        e.apply_dict({"midi_mode": "Quatsch"})
        self.assertEqual(e.midi_mode, EncoderMidiMode.RELATIVE)

    def test_valid_mode_kept(self):
        e = VCEncoder("e")
        e.apply_dict({"midi_mode": EncoderMidiMode.ABSOLUTE})
        self.assertEqual(e.midi_mode, EncoderMidiMode.ABSOLUTE)


class VCI05SliderUnknownMode(unittest.TestCase):
    def test_unknown_mode_falls_back_to_level(self):
        s = VCSlider("s")
        s.apply_dict({"mode": "BogusMode"})
        self.assertEqual(s.mode, SliderMode.LEVEL)

    def test_valid_mode_kept(self):
        s = VCSlider("s")
        s.apply_dict({"mode": SliderMode.GROUP_DIMMER})
        self.assertEqual(s.mode, SliderMode.GROUP_DIMMER)


class VCI06MappableParamChoices(unittest.TestCase):
    def test_excludes_tempo_internal_params(self):
        orig = effect_live.list_params
        effect_live.list_params = lambda fid: [
            types.SimpleNamespace(key="speed_hz", label="Speed", kind="float"),
            types.SimpleNamespace(key="tempo_multiplier", label="Mult", kind="float"),
            types.SimpleNamespace(key="phase_offset", label="Phase", kind="float"),
        ]
        try:
            keys = [k for k, _ in vc_effect_meta.mappable_param_choices(1)]
        finally:
            effect_live.list_params = orig
        self.assertIn("speed_hz", keys)
        self.assertNotIn("tempo_multiplier", keys)
        self.assertNotIn("phase_offset", keys)


class VCI07LpFiredRemoved(unittest.TestCase):
    def test_dead_attr_gone(self):
        b = VCButton("b")
        self.assertFalse(hasattr(b, "_lp_fired"),
                         "VCI-07: totes _lp_fired darf nicht mehr existieren")


class VCI08AspectCaption(unittest.TestCase):
    def test_param_label_stripped(self):
        opt = ControlOption(ControlKind.PARAM, "Parameter: Speed")
        self.assertEqual(aspect_caption(opt, "Matrix 1"), "Speed")

    def test_action_label_stripped(self):
        opt = ControlOption(ControlKind.ACTION, "Aktion: Nächste Farbe")
        self.assertEqual(aspect_caption(opt, "Matrix 1"), "Nächste Farbe")


class VCI10ColorFoldsWhite(unittest.TestCase):
    def test_rgbw_white_not_black(self):
        c = VCColor("c")
        c.color_r = c.color_g = c.color_b = 0
        c.color_w = 255
        col = c.color()
        self.assertGreater(col.red() + col.green() + col.blue(), 0,
                           "VCI-10: reines RGBW-Weiss darf im Swatch nicht schwarz sein")


class VCI14SnapIdsDedupOnSave(unittest.TestCase):
    def test_to_dict_dedups_snap_ids(self):
        b = VCButton("b")
        b.snap_id = 5
        b.snap_ids = [5, 6, 6, 7]      # Duplikate + snap_id selbst
        d = b.to_dict()
        self.assertEqual(d["snap_ids"], [6, 7])


class VCI01And02PaintSmoke(unittest.TestCase):
    def test_tempo_toggle_buttons_paint(self):
        # VCI-01: Lit-Indikator-Pfad fuer FREEZE/AUTO_SYNC/BPM_MODE_TOGGLE darf nicht
        # crashen (Zustands-Queries in paintEvent).
        for act in (ButtonAction.FREEZE, ButtonAction.AUTO_SYNC,
                    ButtonAction.BPM_MODE_TOGGLE):
            b = VCButton("t")
            b.action = act
            try:
                b.grab()                # rendert -> paintEvent
            except Exception as e:
                self.fail(f"VCI-01: paint fuer {act} crasht: {e!r}")

    def test_canvas_assign_hint_paints(self):
        # VCI-02: Overlay-Hint fuer function/library_snap-Assign darf nicht crashen.
        canvas = VCCanvas()
        canvas.resize(200, 120)
        for starter in (lambda: canvas.start_function_assign(1),
                        lambda: canvas.start_snap_assign(1)):
            starter()
            try:
                canvas.grab()
            except Exception as e:
                self.fail(f"VCI-02: canvas assign-hint paint crasht: {e!r}")


if __name__ == "__main__":
    unittest.main()
