"""Qt-Offscreen-Tests: VCEncoder steuert einen Effekt-Parameter RELATIV live.

Der Encoder nutzt denselben effect_live-Dispatcher wie die uebrigen
Live-Bedienelemente (adjust_param relativ / set_param_normalized absolut) und
zielt auf einen fest gebundenen ODER den aktiven Effekt.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.core.engine.function_manager import get_function_manager
from src.core.engine.rgb_matrix import RgbMatrixInstance, RgbAlgorithm
from src.core.midi.midi_manager import MidiMessage


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _cc(cc: int, value: int, channel: int = 1) -> MidiMessage:
    return MidiMessage(port_name="X", channel=channel, msg_type="cc", data1=cc, data2=value)


class VcEncoderTest(unittest.TestCase):

    def setUp(self):
        _app()
        self.fm = get_function_manager()
        self.fm.stop_all()
        self.m = RgbMatrixInstance(name="enc", cols=4, rows=1,
                                   algorithm=RgbAlgorithm.CHASE, fixture_grid=[1, 2, 3, 4])
        self.fm.add(self.m)

    def tearDown(self):
        self.fm.stop_all()
        self.fm.remove(self.m.id)

    def test_registered_in_widget_registry(self):
        from src.ui.virtualconsole.vc_canvas import WIDGET_REGISTRY
        from src.ui.virtualconsole.vc_encoder import VCEncoder
        self.assertIs(WIDGET_REGISTRY.get("VCEncoder"), VCEncoder)

    def test_relative_nudge_changes_param(self):
        from src.ui.virtualconsole.vc_encoder import VCEncoder
        e = VCEncoder("Speed")
        e.param_key = "speed"
        e.function_id = self.m.id
        self.m.matrix_speed = 5.0
        e.nudge(+1)
        self.assertGreater(self.m.matrix_speed, 5.0)   # rauf
        up = self.m.matrix_speed
        e.nudge(-1)
        self.assertLess(self.m.matrix_speed, up)       # runter

    def test_relative_nudge_clamped(self):
        from src.ui.virtualconsole.vc_encoder import VCEncoder
        e = VCEncoder("Speed")
        e.param_key, e.function_id = "speed", self.m.id
        for _ in range(200):
            e.nudge(-5)
        self.assertGreaterEqual(self.m.matrix_speed, 0.0)
        self.assertLessEqual(self.m.matrix_speed, 0.5)   # an der Untergrenze

    def test_active_effect_target(self):
        from src.ui.virtualconsole.vc_encoder import VCEncoder
        self.fm.start(self.m.id)
        self.m.matrix_speed = 4.0
        e = VCEncoder("Speed")
        e.param_key = "speed"
        e.function_id = None            # aktiver Effekt
        e.nudge(+2)
        self.assertGreater(self.m.matrix_speed, 4.0)

    def test_midi_relative_inc_dec(self):
        from src.ui.virtualconsole.vc_encoder import VCEncoder, EncoderMidiMode
        e = VCEncoder("Speed")
        e.param_key, e.function_id = "speed", self.m.id
        e.midi_mode = EncoderMidiMode.RELATIVE
        e.midi_cc, e.midi_ch = 20, 0
        self.m.matrix_speed = 6.0
        self.assertTrue(e.handle_midi(_cc(20, 1)))      # +1 Schritt
        self.assertGreater(self.m.matrix_speed, 6.0)
        up = self.m.matrix_speed
        self.assertTrue(e.handle_midi(_cc(20, 127)))    # −1 Schritt (Zweierkomplement)
        self.assertLess(self.m.matrix_speed, up)

    def test_midi_absolute(self):
        from src.ui.virtualconsole.vc_encoder import VCEncoder, EncoderMidiMode
        e = VCEncoder("Speed")
        e.param_key, e.function_id = "speed", self.m.id
        e.midi_mode = EncoderMidiMode.ABSOLUTE
        e.midi_cc, e.midi_ch = 21, 0
        e.handle_midi(_cc(21, 127))                     # voll → ~max
        self.assertGreater(self.m.matrix_speed, 15)

    def test_midi_ignores_other_cc(self):
        from src.ui.virtualconsole.vc_encoder import VCEncoder
        e = VCEncoder("Speed")
        e.param_key, e.function_id = "speed", self.m.id
        e.midi_cc = 20
        self.m.matrix_speed = 3.0
        self.assertFalse(e.handle_midi(_cc(21, 1)))     # falsche CC → nichts
        self.assertEqual(self.m.matrix_speed, 3.0)

    def test_serialization_roundtrip(self):
        from src.ui.virtualconsole.vc_encoder import VCEncoder, EncoderMidiMode
        e = VCEncoder("X")
        e.param_key = "level"
        e.function_id = 7
        e.step = 0.1
        e.midi_mode = EncoderMidiMode.ABSOLUTE
        e.midi_cc, e.midi_ch = 30, 2
        e2 = VCEncoder("Y")
        e2.apply_dict(e.to_dict())
        self.assertEqual(e2.param_key, "level")
        self.assertEqual(e2.function_id, 7)
        self.assertAlmostEqual(e2.step, 0.1)
        self.assertEqual(e2.midi_mode, EncoderMidiMode.ABSOLUTE)
        self.assertEqual(e2.midi_cc, 30)
        self.assertEqual(e2.midi_ch, 2)


if __name__ == "__main__":
    unittest.main()
