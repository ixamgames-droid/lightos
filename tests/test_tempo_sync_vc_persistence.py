"""Tempo-Sync Phase 5 / WS3: VC-Layout-Roundtrip ueber alle neuen Widget-Typen.

Stellt sicher, dass die neuen VC-Widgets (VCBusSelector, VCEffectColors) und die
neuen Felder (tempo_bus_id auf Button/Slider/SpeedDial/BpmDisplay) den
to_dict/from_dict-Roundtrip des Canvas ueberstehen.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPoint


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


class VcLayoutRoundtripTest(unittest.TestCase):

    def setUp(self):
        _app()
        from src.ui.virtualconsole.vc_canvas import VCCanvas
        self.canvas = VCCanvas()
        self.canvas.set_edit_mode(True)

    def _first(self, canvas, cls):
        items = canvas.findChildren(cls)
        self.assertTrue(items, f"{cls.__name__} fehlt nach Roundtrip")
        return items[0]

    def _add(self, wtype, pos):
        w = self.canvas._add_widget(wtype, pos)
        assert w is not None
        return w

    def test_roundtrip_all_new_widgets(self):
        from src.ui.virtualconsole.vc_canvas import VCCanvas
        from src.ui.virtualconsole.vc_button import VCButton, ButtonAction
        from src.ui.virtualconsole.vc_slider import VCSlider, SliderMode
        from src.ui.virtualconsole.vc_speedial import VCSpeedDial, SpeedTarget
        from src.ui.virtualconsole.vc_bpm_display import VCBpmDisplay
        from src.ui.virtualconsole.vc_bus_selector import VCBusSelector
        from src.ui.virtualconsole.vc_effect_colors import VCEffectColors

        b = self._add("VCButton", QPoint(5, 5))
        b.action = ButtonAction.TAP_BUS
        b.tempo_bus_id = "A"
        s = self._add("VCSlider", QPoint(60, 5))
        s.mode = SliderMode.TEMPO_BUS
        s.tempo_bus_id = "B"
        sd = self._add("VCSpeedDial", QPoint(120, 5))
        sd.target_mode = SpeedTarget.TEMPO_BUS
        sd.tempo_bus_id = "C"
        bpm = self._add("VCBpmDisplay", QPoint(5, 90))
        bpm.tempo_bus_id = "D"
        bs = self._add("VCBusSelector", QPoint(120, 90))
        bs.buses = ["A", "B", "X"]
        ec = self._add("VCEffectColors", QPoint(60, 90))
        ec.function_id = 42
        ec.edit_slot = "MX"

        data = self.canvas.to_dict()

        c2 = VCCanvas()
        c2.set_edit_mode(True)
        c2.from_dict(data)

        self.assertEqual(self._first(c2, VCButton).action, ButtonAction.TAP_BUS)
        self.assertEqual(self._first(c2, VCButton).tempo_bus_id, "A")
        self.assertEqual(self._first(c2, VCSlider).mode, SliderMode.TEMPO_BUS)
        self.assertEqual(self._first(c2, VCSlider).tempo_bus_id, "B")
        self.assertEqual(self._first(c2, VCSpeedDial).target_mode, SpeedTarget.TEMPO_BUS)
        self.assertEqual(self._first(c2, VCSpeedDial).tempo_bus_id, "C")
        self.assertEqual(self._first(c2, VCBpmDisplay).tempo_bus_id, "D")
        self.assertEqual(self._first(c2, VCBusSelector).buses, ["A", "B", "X"])
        ec2 = self._first(c2, VCEffectColors)
        self.assertEqual(ec2.function_id, 42)
        self.assertEqual(ec2.edit_slot, "MX")


if __name__ == "__main__":
    unittest.main()
