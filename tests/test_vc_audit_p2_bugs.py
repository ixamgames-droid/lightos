"""VC-Code-Audit P2-Bugfixes (zweiter Batch, Stand 2026-06-30).

- VCB-11: VCXYPad._write_axis rundet 8-bit statt abzuschneiden (kein -0.5-LSB-Bias).
- VCB-12: VCSpeedDial persistiert min/max-BPM (kein Reset auf 20..600 beim Reload).
- VCB-13: VCSpeedDial._live_bpm_probe nutzt _effective_mult() (invert-bewusst) —
  die Anzeige stimmt mit dem geschriebenen tempo_multiplier ueberein.
- VCB-14: VCStepper._current_value nutzt den per-Fixture-Key (nicht den generischen).
- VCB-15: VCSlider.mouseMoveEvent crasht nicht bei Track-Hoehe <= 0 (ZeroDivision).
- VCB-16: VCColor ruft begin_live_edit fuer die EFFECT*-Pfade (wie VCEffectColors).
- VCB-17: VCColor._parse_function_id lehnt negative/leere IDs ab.
- VCB-20: VCSlider._effect_targets fuehrt function_id + function_ids zusammen.
"""
import os
import types
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QMouseEvent
from PySide6.QtCore import Qt, QPointF, QEvent

from src.core.app_state import get_state
from src.core.engine.function_manager import get_function_manager
from src.core.engine import effect_live
from src.ui.virtualconsole.vc_xypad import VCXYPad
from src.ui.virtualconsole.vc_speedial import VCSpeedDial, SpeedTarget
from src.ui.virtualconsole.vc_stepper import VCStepper
from src.ui.virtualconsole.vc_slider import VCSlider
from src.ui.virtualconsole.vc_color import VCColor, ColorTarget

_app = QApplication.instance() or QApplication([])


class VCB11XYPadRounding(unittest.TestCase):
    def test_write_axis_rounds_8bit(self):
        state = get_state()
        captured = []
        state.set_programmer_value = lambda fid, attr, v, **k: captured.append(v)
        try:
            pad = VCXYPad("xy")
            pad.bits16 = False
            pad._write_axis(state, 7001, "pan", 127.6 / 255.0)   # -> 127.6
        finally:
            # conftest._restore_app_state_singleton raeumt den Instanz-Patch ohnehin,
            # aber wir nehmen ihn hier defensiv selbst zurueck.
            try:
                del state.set_programmer_value
            except Exception:
                pass
        self.assertEqual(captured[0], 128, "VCB-11: 127.6 muss zu 128 gerundet werden")


class VCB12SpeedDialBpmRange(unittest.TestCase):
    def test_min_max_bpm_roundtrip(self):
        d = VCSpeedDial("sd")
        d._min_bpm = 60.0
        d._max_bpm = 200.0
        out = d.to_dict()
        self.assertEqual(out.get("min_bpm"), 60.0)
        self.assertEqual(out.get("max_bpm"), 200.0)
        d2 = VCSpeedDial("sd2")
        d2.apply_dict(out)
        self.assertEqual(d2._min_bpm, 60.0)
        self.assertEqual(d2._max_bpm, 200.0)

    def test_defaults_when_missing(self):
        d = VCSpeedDial("sd3")
        d.apply_dict({})
        self.assertEqual(d._min_bpm, 20.0)
        self.assertEqual(d._max_bpm, 600.0)


class VCB13SpeedDialProbeInvert(unittest.TestCase):
    def test_probe_uses_effective_mult(self):
        d = VCSpeedDial("sd")
        d.target_mode = SpeedTarget.TEMPO_BUS_MULT
        d._min_mult, d._max_mult = 0.1, 8.0
        d._mult = 2.0
        d._active_factor = 2.0
        d.invert = True
        d._mult_base_bus = lambda: types.SimpleNamespace(bpm=120.0)
        probe = d._live_bpm_probe()
        # _apply() schreibt _effective_mult() = 0.1+8.0-2.0 = 6.1 -> Anzeige 120*6.1.
        self.assertEqual(probe, round(120.0 * d._effective_mult(), 2))
        self.assertNotEqual(probe, round(120.0 * d._active_factor, 2),
                            "VCB-13: bei Invert darf die Anzeige nicht den rohen Faktor nutzen")


class VCB14StepperPerFixtureKey(unittest.TestCase):
    def test_current_value_uses_key_for(self):
        st = VCStepper("s")
        st.param_key = "generic"
        st._fid = lambda: 4242
        st._key_for = lambda fid: "perfid_key"
        captured = {}
        orig = effect_live.get_param
        effect_live.get_param = lambda key, fid: captured.setdefault("key", key)
        try:
            st._current_value()
        finally:
            effect_live.get_param = orig
        self.assertEqual(captured.get("key"), "perfid_key",
                         "VCB-14: _current_value muss den per-Fixture-Key nutzen")


class VCB15SliderTinyHeight(unittest.TestCase):
    def test_mouse_move_no_zerodiv_when_short(self):
        s = VCSlider("s")
        s.resize(60, 30)                 # _track_rect-Hoehe = 30 - 40 < 0
        s._drag_y = 100
        s._drag_start_val = 50
        ev = QMouseEvent(QEvent.Type.MouseMove, QPointF(30, 10),
                         Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.NoModifier)
        try:
            s.mouseMoveEvent(ev)
        except ZeroDivisionError:
            self.fail("VCB-15: mouseMoveEvent darf bei kleiner Hoehe nicht crashen")


class VCB16ColorBeginLiveEdit(unittest.TestCase):
    def _assert_begin_called(self, target):
        calls = []
        orig = effect_live.begin_live_edit
        effect_live.begin_live_edit = lambda fid=None: (calls.append(fid) or True)
        try:
            c = VCColor("c")
            c.target = target
            c.function_id = None          # Aktiv-Effekt-Modus
            c._apply()
        finally:
            effect_live.begin_live_edit = orig
        self.assertTrue(calls, f"VCB-16: begin_live_edit muss fuer {target!r} gerufen werden")

    def test_effect_paths_begin_live_edit(self):
        self._assert_begin_called(ColorTarget.EFFECT)
        self._assert_begin_called(ColorTarget.EFFECT_ADD)
        self._assert_begin_called(ColorTarget.EFFECT_C1)


class VCB17ParseFunctionId(unittest.TestCase):
    def test_parse_function_id(self):
        self.assertEqual(VCColor._parse_function_id("5"), 5)
        self.assertEqual(VCColor._parse_function_id("  7 "), 7)
        self.assertIsNone(VCColor._parse_function_id("-5"),
                          "VCB-17: negative IDs muessen abgelehnt werden")
        self.assertIsNone(VCColor._parse_function_id(""))
        self.assertIsNone(VCColor._parse_function_id("abc"))


class VCB20SliderEffectTargetsMerge(unittest.TestCase):
    def setUp(self):
        self.fm = get_function_manager()
        self.a = self.fm.new_rgb_matrix("VCB20a")
        self.b = self.fm.new_rgb_matrix("VCB20b")

    def tearDown(self):
        for f in (self.a, self.b):
            try:
                self.fm.remove(f.id)
            except Exception:
                pass

    def test_function_id_not_discarded(self):
        s = VCSlider("s")
        s.function_id = self.a.id
        s.function_ids = [self.b.id]
        ids = {getattr(t, "id", None) for t in s._effect_targets()}
        self.assertIn(self.a.id, ids, "VCB-20: function_id darf nicht verworfen werden")
        self.assertIn(self.b.id, ids)


if __name__ == "__main__":
    unittest.main()
