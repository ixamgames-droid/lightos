"""Phase 2 des VC Smart-Build-Umbaus (Qt offscreen, headless):

  - effect_binding_owners: Doppelbelegungs-Scan (welcher Effekt-Aspekt liegt schon
    auf welchem Widget).
  - _resolve_coupling_conflict: couple/replace/new/cancel statt stummem Koppeln.
  - replace_widget_type: bindungserhaltender Widget-Typ-Tausch (Galerie / „Widget
    aendern").
  - build_from_smart_results: mehrere Aspekt-Widgets in EINEM Undo-Schritt.

Stil wie tests/test_vc_multi_effect.py.
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
from src.ui.virtualconsole.vc_effect_colors import VCEffectColors


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _matrix(name: str) -> RgbMatrixInstance:
    return RgbMatrixInstance(name=name, cols=4, rows=1,
                             algorithm=RgbAlgorithm.CHASE, fixture_grid=[1, 2, 3, 4])


class _CanvasCase(unittest.TestCase):
    def setUp(self):
        _app()
        self.fm = get_function_manager()
        self.fm.stop_all()
        self.m1 = _matrix("p2-1")
        self.m2 = _matrix("p2-2")
        self.fm.add(self.m1)
        self.fm.add(self.m2)
        from src.ui.virtualconsole.vc_canvas import VCCanvas
        self.canvas = VCCanvas()
        self.canvas.set_edit_mode(True)

    def tearDown(self):
        self.fm.stop_all()
        self.fm.remove(self.m1.id)
        self.fm.remove(self.m2.id)


# ── effect_binding_owners ────────────────────────────────────────────────────

class EffectBindingOwnersTest(_CanvasCase):

    def _speed_slider(self, caption, fid):
        sl = VCSlider(caption, parent=self.canvas)
        sl.mode = SliderMode.EFFECT_SPEED
        sl.function_id = fid
        return sl

    def test_owner_found_by_effect(self):
        sl = self._speed_slider("Speed1", self.m1.id)
        self.assertEqual(self.canvas.effect_binding_owners(self.m1.id), ["Speed1"])
        self.assertEqual(self.canvas.effect_binding_owners(self.m2.id), [])

    def test_owner_filtered_by_aspect(self):
        self._speed_slider("Speed1", self.m1.id)
        self.assertEqual(
            self.canvas.effect_binding_owners(self.m1.id, aspect="tempo"), ["Speed1"])
        self.assertEqual(
            self.canvas.effect_binding_owners(self.m1.id, aspect="intensity"), [])

    def test_exclude(self):
        sl = self._speed_slider("Speed1", self.m1.id)
        self.assertEqual(self.canvas.effect_binding_owners(self.m1.id, exclude=sl), [])

    def test_coupled_id_counts_as_owner(self):
        sl = VCSlider("Group", parent=self.canvas)
        sl.mode = SliderMode.EFFECT_SPEED
        sl.function_id = self.m1.id
        sl.function_ids = [self.m1.id, self.m2.id]
        self.assertIn("Group", self.canvas.effect_binding_owners(self.m2.id))

    def test_bad_id(self):
        self.assertEqual(self.canvas.effect_binding_owners(None), [])


# ── _resolve_coupling_conflict ───────────────────────────────────────────────

class ResolveCouplingConflictTest(_CanvasCase):

    def _bound_slider(self):
        sl = VCSlider("F", parent=self.canvas)
        sl.mode = SliderMode.EFFECT_SPEED
        sl.function_id = self.m1.id
        return sl

    def test_default_is_couple(self):
        sl = self._bound_slider()
        self.assertTrue(self.canvas._resolve_coupling_conflict(sl, self.m2.id))
        self.assertEqual(sl.function_id, self.m1.id)
        self.assertIn(self.m2.id, sl.function_ids)

    def test_couple_duplicate_is_noop(self):
        sl = self._bound_slider()
        sl.function_ids = [self.m2.id]
        self.assertFalse(
            self.canvas._resolve_coupling_conflict(sl, self.m2.id, resolution="couple"))

    def test_replace(self):
        sl = self._bound_slider()
        sl.function_ids = [self.m2.id]
        sl.param_keys_per_id = {self.m1.id: "speed"}
        self.assertTrue(
            self.canvas._resolve_coupling_conflict(sl, self.m2.id, resolution="replace"))
        self.assertEqual(sl.function_id, self.m2.id)
        self.assertEqual(sl.function_ids, [])
        self.assertEqual(sl.param_keys_per_id, {})

    def test_new_and_cancel_are_noop(self):
        for res in ("new", "cancel"):
            sl = self._bound_slider()
            self.assertFalse(
                self.canvas._resolve_coupling_conflict(sl, self.m2.id, resolution=res))
            self.assertEqual(sl.function_id, self.m1.id)
            self.assertEqual(sl.function_ids, [])


# ── replace_widget_type ──────────────────────────────────────────────────────

class ReplaceWidgetTypeTest(_CanvasCase):

    def test_speeddial_to_slider_keeps_binding(self):
        sd = VCSpeedDial("Tempo", parent=self.canvas)
        sd.target_mode = SpeedTarget.FUNCTION
        sd.function_id = self.m1.id
        new = self.canvas.replace_widget_type(sd, "VCSlider")
        self.assertIsInstance(new, VCSlider)
        self.assertEqual(new.function_id, self.m1.id)
        self.assertEqual(new.mode, SliderMode.EFFECT_SPEED)   # aspect 'tempo'
        self.assertEqual(new.caption, "Tempo")
        # altes SpeedDial ist weg, genau ein Slider da
        self.assertEqual(len(self.canvas.findChildren(VCSpeedDial)), 0)
        self.assertEqual(len(self.canvas.findChildren(VCSlider)), 1)

    def test_swap_is_one_undo_step(self):
        sd = VCSpeedDial("Tempo", parent=self.canvas)
        sd.target_mode = SpeedTarget.FUNCTION
        sd.function_id = self.m1.id
        self.assertTrue(self.canvas.replace_widget_type(sd, "VCSlider"))
        self.assertTrue(self.canvas.can_undo())
        self.canvas.undo()
        # nach dem Undo wieder das SpeedDial, kein Slider
        self.assertEqual(len(self.canvas.findChildren(VCSpeedDial)), 1)
        self.assertEqual(len(self.canvas.findChildren(VCSlider)), 0)

    def test_same_type_noop(self):
        sl = VCSlider("F", parent=self.canvas)
        sl.function_id = self.m1.id
        self.assertIs(self.canvas.replace_widget_type(sl, "VCSlider"), sl)

    def test_unknown_type_returns_none(self):
        sl = VCSlider("F", parent=self.canvas)
        self.assertIsNone(self.canvas.replace_widget_type(sl, "NopeWidget"))

    def test_multi_effect_carried_over(self):
        sl = VCSlider("Group", parent=self.canvas)
        sl.mode = SliderMode.EFFECT_INTENSITY
        sl.function_id = self.m1.id
        sl.function_ids = [self.m1.id, self.m2.id]
        new = self.canvas.replace_widget_type(sl, "VCEncoder")
        self.assertEqual(new.function_id, self.m1.id)
        self.assertEqual(new.function_ids, [self.m1.id, self.m2.id])


# ── build_from_smart_results ─────────────────────────────────────────────────

class BuildFromSmartResultsTest(_CanvasCase):

    def _results(self):
        from src.ui.virtualconsole.smart_drop_dialog import SmartDropResult
        return [
            SmartDropResult(widget_type="VCSlider", function_id=self.m1.id,
                            slider_mode=SliderMode.EFFECT_SPEED),
            SmartDropResult(widget_type="VCEffectColors", function_id=self.m1.id),
        ]

    def test_creates_one_widget_per_result(self):
        created = self.canvas.build_from_smart_results(self._results(), pos=QPoint(10, 10))
        self.assertEqual(len(created), 2)
        self.assertEqual(len(self.canvas.findChildren(VCSlider)), 1)
        self.assertEqual(len(self.canvas.findChildren(VCEffectColors)), 1)

    def test_one_undo_removes_all(self):
        self.canvas.build_from_smart_results(self._results(), pos=QPoint(10, 10))
        self.assertTrue(self.canvas.can_undo())
        self.canvas.undo()
        self.assertEqual(len(self.canvas.findChildren(VCSlider)), 0)
        self.assertEqual(len(self.canvas.findChildren(VCEffectColors)), 0)

    def test_empty_results_noop(self):
        self.assertEqual(self.canvas.build_from_smart_results([]), [])
        self.assertFalse(self.canvas.can_undo())


# ── Effekt-Gruppen-Hervorhebung (Feature C) ──────────────────────────────────

class EffectHighlightTest(_CanvasCase):

    def _build(self):
        from src.ui.virtualconsole.vc_button import VCButton, ButtonAction
        s1 = VCSlider("S1", parent=self.canvas)
        s1.mode = SliderMode.EFFECT_SPEED
        s1.function_id = self.m1.id
        b1 = VCButton("B1", parent=self.canvas)
        b1.action = ButtonAction.FUNCTION_TOGGLE
        b1.function_id = self.m1.id
        s2 = VCSlider("S2", parent=self.canvas)
        s2.mode = SliderMode.EFFECT_SPEED
        s2.function_id = self.m2.id
        return s1, b1, s2

    def test_highlight_by_effect(self):
        s1, b1, s2 = self._build()
        self.canvas.highlight_effects([self.m1.id])
        self.assertTrue(s1._effect_highlight)
        self.assertTrue(b1._effect_highlight)
        self.assertFalse(s2._effect_highlight)   # anderer Effekt -> kein Glow

    def test_exclude_source(self):
        s1, b1, s2 = self._build()
        self.canvas.highlight_effects([self.m1.id], exclude=s1)
        self.assertFalse(s1._effect_highlight)   # Quelle selbst nicht
        self.assertTrue(b1._effect_highlight)

    def test_clear(self):
        s1, b1, s2 = self._build()
        self.canvas.highlight_effects([self.m1.id])
        self.canvas.clear_effect_highlight()
        self.assertFalse(s1._effect_highlight)
        self.assertFalse(b1._effect_highlight)

    def test_only_in_edit_mode(self):
        s1, b1, s2 = self._build()
        self.canvas.set_edit_mode(False)
        self.canvas.highlight_effects([self.m1.id])
        self.assertFalse(s1._effect_highlight)   # im Betrieb kein Glow
        self.assertFalse(b1._effect_highlight)

    def test_notify_from_widget_highlights_group(self):
        s1, b1, s2 = self._build()
        s1._notify_effect_highlight()            # S1 angetippt -> Gruppe leuchtet
        self.assertFalse(s1._effect_highlight)   # Quelle ausgeschlossen
        self.assertTrue(b1._effect_highlight)    # selber Effekt -> Glow
        self.assertFalse(s2._effect_highlight)


if __name__ == "__main__":
    unittest.main()
