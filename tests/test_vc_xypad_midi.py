"""AUDIT-NIEDRIG-VCXYPad-MIDI: VCXYPad reagiert jetzt auf zwei CC-Bindungen
(Pan/Tilt, absolut) — analog zu Slider/Encoder/Button/Color."""
import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.ui.virtualconsole.vc_xypad import VCXYPad

_app = QApplication.instance() or QApplication([])


def _cc(data1, data2, channel=0):
    return SimpleNamespace(msg_type="cc", channel=channel, data1=data1, data2=data2)


class VCXYPadMidiTest(unittest.TestCase):
    def _pad(self):
        p = VCXYPad("XY")
        p.mode = "position"
        p.midi_cc_pan = 10
        p.midi_cc_tilt = 11
        p.midi_ch = 0
        return p

    def test_pan_cc_sets_pan(self):
        p = self._pad()
        self.assertTrue(p.handle_midi(_cc(10, 127)))
        self.assertAlmostEqual(p._pan, 1.0, places=2)

    def test_tilt_cc_sets_tilt(self):
        p = self._pad()
        p._tilt = 0.5
        self.assertTrue(p.handle_midi(_cc(11, 0)))
        self.assertAlmostEqual(p._tilt, 0.0, places=2)

    def test_unbound_cc_ignored(self):
        p = self._pad()
        before = (p._pan, p._tilt)
        self.assertFalse(p.handle_midi(_cc(99, 64)))
        self.assertEqual((p._pan, p._tilt), before)

    def test_non_cc_ignored(self):
        p = self._pad()
        msg = SimpleNamespace(msg_type="note_on", channel=0, data1=10, data2=127)
        self.assertFalse(p.handle_midi(msg))

    def test_channel_filter(self):
        p = self._pad()
        p.midi_ch = 5
        before = p._pan
        self.assertFalse(p.handle_midi(_cc(10, 127, channel=6)))
        self.assertEqual(p._pan, before)
        self.assertTrue(p.handle_midi(_cc(10, 127, channel=5)))
        self.assertAlmostEqual(p._pan, 1.0, places=2)

    def test_area_mode_does_not_move_axes(self):
        p = self._pad()
        p.mode = "area"
        before = (p._pan, p._tilt)
        p.handle_midi(_cc(10, 127))     # im Feld-Modus sind Pan/Tilt nicht das Ziel
        self.assertEqual((p._pan, p._tilt), before)

    def test_persistence_roundtrip(self):
        p = self._pad()
        p.midi_cc_pan, p.midi_cc_tilt, p.midi_ch = 7, 8, 3
        q = VCXYPad("XY2")
        q.apply_dict(p.to_dict())
        self.assertEqual((q.midi_cc_pan, q.midi_cc_tilt, q.midi_ch), (7, 8, 3))

    def test_defaults_when_missing(self):
        q = VCXYPad("XY3")
        q.apply_dict({})                # Alt-Show ohne MIDI-Keys
        self.assertEqual((q.midi_cc_pan, q.midi_cc_tilt, q.midi_ch), (-1, -1, 0))


if __name__ == "__main__":
    unittest.main()
