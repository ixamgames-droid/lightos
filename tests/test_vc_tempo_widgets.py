"""Tempo-Sync Phase 5: VC-Bedienung der Tempo-Buses.

VCButton (TAP_BUS/SYNC_BUS/ARM_BUS) und VCSlider (TEMPO_BUS) wirken ueber
get_tempo_bus_manager().resolve(bus) auf die benannten Tempo-Buses (A/B/C/D),
unabhaengig vom globalen BPM-Leader.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.core.engine.tempo_bus import get_tempo_bus_manager, reset_tempo_bus_manager


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


class VcTempoButtonTest(unittest.TestCase):

    def setUp(self):
        _app()
        reset_tempo_bus_manager()           # frische Buses pro Test
        self.mgr = get_tempo_bus_manager()

    def tearDown(self):
        reset_tempo_bus_manager()

    def test_tap_bus_sets_bpm(self):
        from src.ui.virtualconsole.vc_button import VCButton, ButtonAction
        b = VCButton("Tap A")
        b.action = ButtonAction.TAP_BUS
        b.tempo_bus_id = "A"
        b._trigger(True)        # 1. Tap -> nur Historie
        b._trigger(True)        # 2. Tap -> BPM berechnet (geklemmt)
        bus = self.mgr.resolve("A")
        assert bus is not None
        self.assertGreater(bus.bpm, 0.0)

    def test_arm_bus_sets_armed(self):
        from src.ui.virtualconsole.vc_button import VCButton, ButtonAction
        b = VCButton("Arm B")
        b.action = ButtonAction.ARM_BUS
        b.tempo_bus_id = "B"
        b._trigger(True)
        self.assertEqual(self.mgr.armed_bus_id, "B")

    def test_sync_bus_resets_position(self):
        from src.ui.virtualconsole.vc_button import VCButton, ButtonAction
        bus = self.mgr.resolve("A")
        assert bus is not None
        bus.set_bpm(120.0)
        bus.advance_frame(1.0)              # ~2 Beats weiter
        bus.advance_frame(1.0)
        self.assertGreater(bus.position(), 0.0)
        b = VCButton("Sync A")
        b.action = ButtonAction.SYNC_BUS
        b.tempo_bus_id = "A"
        b._trigger(True)
        self.assertAlmostEqual(bus.position(), 0.0, places=6)

    def test_button_bus_roundtrip(self):
        from src.ui.virtualconsole.vc_button import VCButton, ButtonAction
        b = VCButton("x")
        b.action = ButtonAction.TAP_BUS
        b.tempo_bus_id = "C"
        d = b.to_dict()
        b2 = VCButton("y")
        b2.apply_dict(d)
        self.assertEqual(b2.tempo_bus_id, "C")
        self.assertEqual(b2.action, ButtonAction.TAP_BUS)


class VcTempoSliderTest(unittest.TestCase):

    def setUp(self):
        _app()
        reset_tempo_bus_manager()
        self.mgr = get_tempo_bus_manager()

    def tearDown(self):
        reset_tempo_bus_manager()

    def test_slider_sets_bus_bpm(self):
        from src.ui.virtualconsole.vc_slider import VCSlider, SliderMode
        s = VCSlider("Tempo A")
        s.mode = SliderMode.TEMPO_BUS
        s.tempo_bus_id = "A"
        s.value = 128                       # ~ 30 + 0.5*270 = 165 BPM
        bus = self.mgr.resolve("A")
        assert bus is not None
        self.assertTrue(150.0 <= bus.bpm <= 180.0, f"bpm={bus.bpm}")
        s.value = 0                          # 30 BPM (untere Leitplanke)
        self.assertAlmostEqual(bus.bpm, 30.0, delta=2.0)

    def test_slider_bus_roundtrip(self):
        from src.ui.virtualconsole.vc_slider import VCSlider, SliderMode
        s = VCSlider("x")
        s.mode = SliderMode.TEMPO_BUS
        s.tempo_bus_id = "D"
        d = s.to_dict()
        s2 = VCSlider("y")
        s2.apply_dict(d)
        self.assertEqual(s2.tempo_bus_id, "D")
        self.assertEqual(s2.mode, SliderMode.TEMPO_BUS)


class VcBusSelectorTest(unittest.TestCase):

    def setUp(self):
        _app()
        reset_tempo_bus_manager()
        self.mgr = get_tempo_bus_manager()

    def tearDown(self):
        reset_tempo_bus_manager()

    def test_click_arms_bus(self):
        from src.ui.virtualconsole.vc_bus_selector import VCBusSelector
        from PySide6.QtGui import QMouseEvent
        from PySide6.QtCore import Qt, QPointF, QEvent
        w = VCBusSelector()
        w.resize(220, 84)
        x = int(220 / 4 * 1) + 10            # Chip-Index 1 = "B"
        ev = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(x, 40),
                         Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.NoModifier)
        w.mousePressEvent(ev)
        self.assertEqual(self.mgr.armed_bus_id, "B")

    def test_roundtrip(self):
        from src.ui.virtualconsole.vc_bus_selector import VCBusSelector
        w = VCBusSelector()
        w.buses = ["A", "B", "X"]
        w.function_id = 42
        d = w.to_dict()
        w2 = VCBusSelector()
        w2.apply_dict(d)
        self.assertEqual(w2.buses, ["A", "B", "X"])
        self.assertEqual(w2.function_id, 42)

    def test_bound_selector_changes_only_effect_bus(self):
        from src.ui.virtualconsole.vc_bus_selector import VCBusSelector
        from src.core.engine.function_manager import get_function_manager
        from src.core.engine.rgb_matrix import RgbMatrixInstance
        from PySide6.QtGui import QMouseEvent
        from PySide6.QtCore import Qt, QPointF, QEvent

        fm = get_function_manager()
        matrix = RgbMatrixInstance("Bus target")
        fm.add(matrix)
        try:
            self.mgr.armed_bus_id = "A"
            widget = VCBusSelector()
            widget.function_id = matrix.id
            widget.resize(220, 84)
            x = int(220 / 4 * 2) + 10
            event = QMouseEvent(
                QEvent.Type.MouseButtonPress, QPointF(x, 40),
                Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            )
            widget.mousePressEvent(event)
            self.assertEqual(matrix.tempo_bus_id, "C")
            self.assertEqual(self.mgr.armed_bus_id, "A")
        finally:
            fm.remove(matrix.id)


class VcBpmDisplayBusTest(unittest.TestCase):

    def setUp(self):
        _app()
        reset_tempo_bus_manager()
        self.mgr = get_tempo_bus_manager()

    def tearDown(self):
        reset_tempo_bus_manager()

    def test_bus_mode_shows_bus_bpm(self):
        from src.ui.virtualconsole.vc_bpm_display import VCBpmDisplay
        bus = self.mgr.resolve("A")
        assert bus is not None
        bus.set_bpm(140.0)
        d = VCBpmDisplay()
        d.tempo_bus_id = "A"
        d._poll_bus()
        self.assertAlmostEqual(d._bpm, 140.0, delta=1.0)

    def test_roundtrip(self):
        from src.ui.virtualconsole.vc_bpm_display import VCBpmDisplay
        d = VCBpmDisplay()
        d.tempo_bus_id = "C"
        dd = d.to_dict()
        d2 = VCBpmDisplay()
        d2.apply_dict(dd)
        self.assertEqual(d2.tempo_bus_id, "C")


class VcSpeedDialBusTest(unittest.TestCase):

    def setUp(self):
        _app()
        reset_tempo_bus_manager()
        self.mgr = get_tempo_bus_manager()
        from src.core.engine.function_manager import get_function_manager
        from src.core.engine.rgb_matrix import RgbMatrixInstance, RgbAlgorithm
        self.fm = get_function_manager()
        self.fm.stop_all()
        self.m = RgbMatrixInstance(name="sd", cols=4, rows=1,
                                   algorithm=RgbAlgorithm.CHASE, fixture_grid=[1, 2, 3, 4])
        self.fm.add(self.m)

    def tearDown(self):
        self.fm.stop_all()
        self.fm.remove(self.m.id)
        reset_tempo_bus_manager()

    def test_tempo_bus_sets_bpm(self):
        from src.ui.virtualconsole.vc_speedial import VCSpeedDial, SpeedTarget
        dial = VCSpeedDial()
        dial.target_mode = SpeedTarget.TEMPO_BUS
        dial.tempo_bus_id = "A"
        dial.bpm = 150.0                     # Setter ruft _apply -> bus.set_bpm
        bus = self.mgr.resolve("A")
        assert bus is not None
        self.assertAlmostEqual(bus.bpm, 150.0, delta=2.0)

    def test_mult_sets_tempo_multiplier(self):
        from src.ui.virtualconsole.vc_speedial import VCSpeedDial, SpeedTarget
        from src.core.engine import effect_live
        dial = VCSpeedDial()
        dial.target_mode = SpeedTarget.TEMPO_BUS_MULT
        dial.function_id = self.m.id
        dial.mult = 0.5                      # Half -> tempo_multiplier 0.5
        self.assertAlmostEqual(
            float(effect_live.get_param("tempo_multiplier", self.m.id)), 0.5, delta=0.001)

    def test_roundtrip(self):
        from src.ui.virtualconsole.vc_speedial import VCSpeedDial, SpeedTarget
        dial = VCSpeedDial()
        dial.target_mode = SpeedTarget.TEMPO_BUS
        dial.tempo_bus_id = "B"
        d = dial.to_dict()
        d2 = VCSpeedDial()
        d2.apply_dict(d)
        self.assertEqual(d2.tempo_bus_id, "B")
        self.assertEqual(d2.target_mode, SpeedTarget.TEMPO_BUS)


if __name__ == "__main__":
    unittest.main()
