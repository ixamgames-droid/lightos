"""Phase E: mehrere Effekte an EINEN VC-Regler koppeln + je Effekt den
gesteuerten Parameter waehlen (wie die „Funktionen"-Tabelle in QLC+).

Deckt ab:
  (a) Drop auf bestehendes SpeedDial/Slider HAENGT AN statt zu ersetzen.
  (b) function_ids-Roundtrip fuer VCButton/VCEncoder (+ Slider/SpeedDial).
  (c) param_keys_per_id-Roundtrip + dass _apply den per-Effekt-Parameter nutzt.
  (d) leeres/legacy dict -> Defaults (rueckwaerts-kompatibel).

Headless, Qt offscreen — Stil von tests/test_vc_speed_node.py.
"""
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPoint

from src.core.engine.function_manager import get_function_manager
from src.core.engine.rgb_matrix import RgbMatrixInstance, RgbAlgorithm

from src.ui.virtualconsole.vc_slider import VCSlider, SliderMode
from src.ui.virtualconsole.vc_speedial import VCSpeedDial, SpeedTarget
from src.ui.virtualconsole.vc_encoder import VCEncoder
from src.ui.virtualconsole.vc_button import VCButton, ButtonAction


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _matrix(name: str) -> RgbMatrixInstance:
    return RgbMatrixInstance(name=name, cols=4, rows=1,
                             algorithm=RgbAlgorithm.CHASE, fixture_grid=[1, 2, 3, 4])


# ── (a) Append-on-Drop ───────────────────────────────────────────────────────

class AppendOnDropTest(unittest.TestCase):

    def setUp(self):
        _app()
        self.fm = get_function_manager()
        self.fm.stop_all()
        self.m1 = _matrix("drop-1")
        self.m2 = _matrix("drop-2")
        self.fm.add(self.m1)
        self.fm.add(self.m2)
        from src.ui.virtualconsole.vc_canvas import VCCanvas
        self.canvas = VCCanvas()
        self.canvas.set_edit_mode(True)

    def tearDown(self):
        self.fm.stop_all()
        self.fm.remove(self.m1.id)
        self.fm.remove(self.m2.id)

    def test_slider_append_not_replace(self):
        sl = VCSlider("F", parent=self.canvas)
        sl.mode = SliderMode.EFFECT_PARAM
        sl.function_id = self.m1.id
        # Zweiten Effekt drauf droppen -> wird gekoppelt, nicht ersetzt.
        self.canvas.apply_drop(function_id=self.m2.id, target=sl)
        self.assertEqual(sl.function_id, self.m1.id)          # Primaer bleibt
        self.assertIn(self.m2.id, sl.function_ids)            # neuer angehaengt
        # Erneut den GLEICHEN -> kein Duplikat.
        self.canvas.apply_drop(function_id=self.m2.id, target=sl)
        self.assertEqual(sl.function_ids.count(self.m2.id), 1)

    def test_slider_empty_target_binds_as_before(self):
        sl = VCSlider("F", parent=self.canvas)            # leer (keine Bindung)
        self.canvas.apply_drop(function_id=self.m1.id, target=sl)
        self.assertEqual(sl.function_id, self.m1.id)
        self.assertEqual(sl.function_ids, [])             # NICHT angehaengt
        self.assertEqual(sl.mode, SliderMode.EFFECT_PARAM)

    def test_speeddial_append_not_replace(self):
        sd = VCSpeedDial("S", parent=self.canvas)
        sd.target_mode = SpeedTarget.FUNCTION
        sd.function_id = self.m1.id
        handled = self.canvas._apply_function_to_special(sd, self.m2.id, "drop-2")
        self.assertTrue(handled)
        self.assertEqual(sd.function_id, self.m1.id)
        self.assertIn(self.m2.id, sd.function_ids)

    def test_speeddial_empty_target_binds_as_before(self):
        sd = VCSpeedDial("S", parent=self.canvas)
        handled = self.canvas._apply_function_to_special(sd, self.m1.id, "drop-1")
        self.assertTrue(handled)
        self.assertEqual(sd.function_id, self.m1.id)
        self.assertEqual(sd.function_ids, [])
        self.assertEqual(sd.target_mode, SpeedTarget.FUNCTION)

    def test_button_append_not_replace(self):
        btn = VCButton("B", parent=self.canvas)
        btn.action = ButtonAction.FUNCTION_TOGGLE
        btn.function_id = self.m1.id
        self.canvas.apply_drop(function_id=self.m2.id, target=btn)
        self.assertEqual(btn.function_id, self.m1.id)
        self.assertIn(self.m2.id, btn.function_ids)

        # Der gekoppelte Button schaltet anschließend beide Funktionen gemeinsam.
        btn._trigger(True)
        self.assertTrue(self.fm.is_running(self.m1.id))
        self.assertTrue(self.fm.is_running(self.m2.id))
        btn._trigger(True)
        self.assertFalse(self.fm.is_running(self.m1.id))
        self.assertFalse(self.fm.is_running(self.m2.id))

        # Gleiche Funktion erneut droppen -> kein Duplikat.
        self.canvas.apply_drop(function_id=self.m2.id, target=btn)
        self.assertEqual(btn.function_ids.count(self.m2.id), 1)

    def test_empty_button_binds_as_before(self):
        btn = VCButton("B", parent=self.canvas)
        self.canvas.apply_drop(function_id=self.m1.id, target=btn)
        self.assertEqual(btn.action, ButtonAction.FUNCTION_TOGGLE)
        self.assertEqual(btn.function_id, self.m1.id)
        self.assertEqual(btn.function_ids, [])

    def test_button_group_with_edit_slot_keeps_all_effects_running(self):
        from src.core.engine import effect_live
        effect_live.clear_edit_targets()
        btn = VCButton("Gruppe")
        btn.action = ButtonAction.FUNCTION_TOGGLE
        btn.function_id = self.m1.id
        btn.function_ids = [self.m2.id]
        btn.edit_slot = "MX"

        btn._trigger(True)

        self.assertTrue(self.fm.is_running(self.m1.id))
        self.assertTrue(self.fm.is_running(self.m2.id))
        self.assertEqual(effect_live.get_edit_target("MX"), self.m1.id)
        effect_live.clear_edit_targets()

    def test_button_group_exclusive_starts_whole_group(self):
        outsider = _matrix("exclusive-outsider")
        self.fm.add(outsider)
        try:
            self.fm.start(outsider.id)
            btn = VCButton("Gruppe")
            btn.action = ButtonAction.FUNCTION_TOGGLE
            btn.function_id = self.m1.id
            btn.function_ids = [self.m2.id]
            btn.exclusive = True

            btn._trigger(True)

            self.assertFalse(self.fm.is_running(outsider.id))
            self.assertTrue(self.fm.is_running(self.m1.id))
            self.assertTrue(self.fm.is_running(self.m2.id))
        finally:
            self.fm.stop(outsider.id)
            self.fm.remove(outsider.id)

    def test_button_group_fixture_solo_protects_group_members(self):
        outsider = _matrix("solo-outsider")
        self.fm.add(outsider)
        try:
            self.fm.start(outsider.id)
            btn = VCButton("Gruppe")
            btn.action = ButtonAction.FUNCTION_TOGGLE
            btn.function_id = self.m1.id
            btn.function_ids = [self.m2.id]
            btn.solo_fixtures = True

            btn._trigger(True)

            self.assertFalse(self.fm.is_running(outsider.id))
            self.assertTrue(self.fm.is_running(self.m1.id))
            self.assertTrue(self.fm.is_running(self.m2.id))
        finally:
            self.fm.stop(outsider.id)
            self.fm.remove(outsider.id)

    def test_button_effect_action_runs_for_all_targets(self):
        from src.core.engine import effect_live
        calls = []
        orig = effect_live.do_action

        def _spy(key, function_id=None):
            calls.append((key, function_id))
            return True

        effect_live.do_action = _spy
        try:
            btn = VCButton("Aktion")
            btn.action = ButtonAction.EFFECT_ACTION
            btn.function_id = self.m1.id
            btn.function_ids = [self.m2.id]
            btn.effect_action_key = "toggle_freeze"

            btn._trigger(True)

            self.assertEqual(calls, [
                ("toggle_freeze", self.m1.id),
                ("toggle_freeze", self.m2.id),
            ])
        finally:
            effect_live.do_action = orig


# ── (b) function_ids-Roundtrip fuer Button/Encoder ───────────────────────────

class FunctionIdsRoundtripTest(unittest.TestCase):

    def setUp(self):
        _app()

    def test_button_roundtrip(self):
        b = VCButton("B")
        b.action = ButtonAction.FUNCTION_TOGGLE
        b.function_id = 5
        b.function_ids = [6, 7]
        d = b.to_dict()
        b2 = VCButton("x")
        b2.apply_dict(d)
        self.assertEqual(b2.function_id, 5)
        self.assertEqual(b2.function_ids, [6, 7])

    def test_encoder_roundtrip(self):
        e = VCEncoder("E")
        e.function_id = 5
        e.function_ids = [6, 7]
        e.param_key = "speed"
        d = e.to_dict()
        e2 = VCEncoder("x")
        e2.apply_dict(d)
        self.assertEqual(e2.function_id, 5)
        self.assertEqual(e2.function_ids, [6, 7])

    def test_slider_speeddial_roundtrip(self):
        sl = VCSlider("F")
        sl.function_id = 1
        sl.function_ids = [2, 3]
        sl2 = VCSlider("x")
        sl2.apply_dict(sl.to_dict())
        self.assertEqual(sl2.function_ids, [2, 3])

        sd = VCSpeedDial("S")
        sd.function_id = 1
        sd.function_ids = [2, 3]
        sd2 = VCSpeedDial("x")
        sd2.apply_dict(sd.to_dict())
        self.assertEqual(sd2.function_ids, [2, 3])


# ── (c) param_keys_per_id-Roundtrip + Wirkung ────────────────────────────────

class ParamKeysPerIdTest(unittest.TestCase):

    def setUp(self):
        _app()
        self.fm = get_function_manager()
        self.fm.stop_all()
        self.m1 = _matrix("pk-1")
        self.m2 = _matrix("pk-2")
        self.fm.add(self.m1)
        self.fm.add(self.m2)

    def tearDown(self):
        self.fm.stop_all()
        self.fm.remove(self.m1.id)
        self.fm.remove(self.m2.id)

    def test_slider_roundtrip(self):
        sl = VCSlider("F")
        sl.function_id = self.m1.id
        sl.function_ids = [self.m2.id]
        sl.param_keys_per_id = {self.m1.id: "speed", self.m2.id: "intensity"}
        sl2 = VCSlider("x")
        sl2.apply_dict(sl.to_dict())
        self.assertEqual(sl2.param_keys_per_id,
                         {self.m1.id: "speed", self.m2.id: "intensity"})

    def test_encoder_roundtrip(self):
        e = VCEncoder("E")
        e.function_id = self.m1.id
        e.function_ids = [self.m2.id]
        e.param_keys_per_id = {self.m2.id: "intensity"}
        e2 = VCEncoder("x")
        e2.apply_dict(e.to_dict())
        self.assertEqual(e2.param_keys_per_id, {self.m2.id: "intensity"})

    def test_speeddial_roundtrip(self):
        sd = VCSpeedDial("S")
        sd.function_id = self.m1.id
        sd.function_ids = [self.m2.id]
        sd.param_keys_per_id = {self.m1.id: "speed"}
        sd2 = VCSpeedDial("x")
        sd2.apply_dict(sd.to_dict())
        self.assertEqual(sd2.param_keys_per_id, {self.m1.id: "speed"})

    def test_slider_apply_uses_per_effect_param(self):
        """_apply soll bei EFFECT_PARAM je Effekt den eigenen Key setzen:
        m1 -> 'intensity', m2 -> (Default) 'speed'."""
        sl = VCSlider("F")
        sl.mode = SliderMode.EFFECT_PARAM
        sl.function_id = self.m1.id
        sl.function_ids = [self.m2.id]
        sl.param_key = "speed"                              # Default fuer m2
        sl.param_keys_per_id = {self.m1.id: "intensity"}   # m1 abweichend
        sl.range_min, sl.range_max = 0, 255

        from src.core.engine import effect_live
        calls: list[tuple[str, float, "int | None"]] = []
        orig = effect_live.set_param_normalized

        def _spy(key, norm, function_id=None):
            calls.append((key, norm, function_id))
            return orig(key, norm, function_id)

        effect_live.set_param_normalized = _spy
        try:
            sl.value = 255                                  # Setter -> _apply
        finally:
            effect_live.set_param_normalized = orig

        keys_by_fid = {fid: key for key, _, fid in calls}
        self.assertEqual(keys_by_fid.get(self.m1.id), "intensity")
        self.assertEqual(keys_by_fid.get(self.m2.id), "speed")

    def test_encoder_nudge_iterates_all_targets(self):
        e = VCEncoder("E")
        e.function_id = self.m1.id
        e.function_ids = [self.m2.id]
        e.param_key = "speed"
        e.param_keys_per_id = {self.m2.id: "intensity"}

        from src.core.engine import effect_live
        calls: list[tuple[str, float, "int | None"]] = []
        orig = effect_live.adjust_param

        def _spy(key, delta, function_id=None):
            calls.append((key, delta, function_id))
            return orig(key, delta, function_id)

        effect_live.adjust_param = _spy
        try:
            e.nudge(1.0)
        finally:
            effect_live.adjust_param = orig

        keys_by_fid = {fid: key for key, _, fid in calls}
        self.assertEqual(keys_by_fid.get(self.m1.id), "speed")
        self.assertEqual(keys_by_fid.get(self.m2.id), "intensity")


# ── (d) Legacy / leeres dict -> Defaults ─────────────────────────────────────

class LegacyDefaultsTest(unittest.TestCase):

    def setUp(self):
        _app()

    def test_slider_legacy(self):
        sl = VCSlider("x")
        sl.apply_dict({"mode": SliderMode.EFFECT_PARAM, "function_id": 9})
        self.assertEqual(sl.function_id, 9)
        self.assertEqual(sl.function_ids, [])
        self.assertEqual(sl.param_keys_per_id, {})

    def test_speeddial_legacy(self):
        sd = VCSpeedDial("x")
        sd.apply_dict({"bpm": 120.0, "target_mode": SpeedTarget.FUNCTION})
        self.assertEqual(sd.function_ids, [])
        self.assertEqual(sd.param_keys_per_id, {})

    def test_encoder_legacy(self):
        e = VCEncoder("x")
        e.apply_dict({"param_key": "rate", "function_id": 3})
        self.assertEqual(e.function_ids, [])
        self.assertEqual(e.param_keys_per_id, {})

    def test_button_legacy(self):
        b = VCButton("x")
        b.apply_dict({"action": "FunctionToggle", "function_id": 4})
        self.assertEqual(b.function_id, 4)
        self.assertEqual(b.function_ids, [])


# ── SmartDropResult: optionale Multi-Effekt-Felder ───────────────────────────

class SmartDropMultiTest(unittest.TestCase):

    def setUp(self):
        _app()
        self.fm = get_function_manager()
        self.fm.stop_all()
        self.m1 = _matrix("sd-1")
        self.m2 = _matrix("sd-2")
        self.fm.add(self.m1)
        self.fm.add(self.m2)
        from src.ui.virtualconsole.vc_canvas import VCCanvas
        self.canvas = VCCanvas()
        self.canvas.set_edit_mode(True)

    def tearDown(self):
        self.fm.stop_all()
        self.fm.remove(self.m1.id)
        self.fm.remove(self.m2.id)

    def test_build_applies_multi_fields(self):
        from src.ui.virtualconsole.smart_drop_dialog import SmartDropResult
        res = SmartDropResult(
            widget_type="VCSlider", function_id=self.m1.id,
            slider_mode=SliderMode.EFFECT_PARAM,
            function_ids=[self.m2.id],
            param_keys_per_id={self.m2.id: "intensity"})
        self.canvas._build_from_smart_result(res, QPoint(10, 10))
        sliders = self.canvas.findChildren(VCSlider)
        self.assertEqual(len(sliders), 1)
        w = sliders[0]
        self.assertEqual(w.function_id, self.m1.id)
        self.assertIn(self.m2.id, w.function_ids)
        self.assertEqual(w.param_keys_per_id, {self.m2.id: "intensity"})

    def test_build_single_effect_unchanged(self):
        from src.ui.virtualconsole.smart_drop_dialog import SmartDropResult
        res = SmartDropResult(widget_type="VCSlider", function_id=self.m1.id,
                              slider_mode=SliderMode.EFFECT_SPEED)
        self.canvas._build_from_smart_result(res, QPoint(10, 10))
        w = self.canvas.findChildren(VCSlider)[0]
        self.assertEqual(w.function_id, self.m1.id)
        self.assertEqual(w.function_ids, [])
        self.assertEqual(w.param_keys_per_id, {})


if __name__ == "__main__":
    unittest.main()
