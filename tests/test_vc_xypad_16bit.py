"""VC-Erweiterung 2026-06-13 (F4): XY-Pad 16-bit Pan/Tilt.

Bei aktivem 16-bit schreibt das Pad zusätzlich die Fine-Kanäle (pan_fine/tilt_fine);
die Engine (app_state) wertet Coarse+Fine aus. Fixtures ohne Fine-Kanal ignorieren
den Extra-Wert. Aus = klassisch 8-bit.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.core.app_state import get_state
from src.ui.virtualconsole.vc_xypad import VCXYPad

_app = QApplication.instance() or QApplication([])


class XYPad16BitTest(unittest.TestCase):
    def setUp(self):
        self.state = get_state()
        self.state.programmer.clear()

    def tearDown(self):
        self.state.programmer.clear()

    def test_8bit_writes_only_coarse(self):
        pad = VCXYPad()
        pad.bits16 = False
        pad._fixture_ids = [1]
        pad._pan = 0.5
        pad._tilt = 1.0
        pad._apply()
        prog = self.state.programmer.get(1, {})
        self.assertEqual(prog.get("pan"), 127)
        self.assertEqual(prog.get("tilt"), 255)
        self.assertNotIn("pan_fine", prog)
        self.assertNotIn("tilt_fine", prog)

    def test_16bit_writes_coarse_and_fine(self):
        pad = VCXYPad()
        pad.bits16 = True
        pad._fixture_ids = [1]
        pad._pan = 0.5            # round(0.5*65535)=32768 -> coarse 128, fine 0
        pad._apply()
        prog = self.state.programmer.get(1, {})
        self.assertIn("pan_fine", prog)
        self.assertIn("tilt_fine", prog)
        v = prog.get("pan") * 256 + prog.get("pan_fine")
        # Kombinierter 16-bit-Wert nahe der Mitte (32767/32768)
        self.assertAlmostEqual(v, 32768, delta=2)

    def test_16bit_extremes(self):
        pad = VCXYPad()
        pad.bits16 = True
        pad._fixture_ids = [2]
        pad._pan = 1.0
        pad._tilt = 0.0
        pad._apply()
        prog = self.state.programmer.get(2, {})
        self.assertEqual(prog.get("pan"), 255)
        self.assertEqual(prog.get("pan_fine"), 255)
        self.assertEqual(prog.get("tilt"), 0)
        self.assertEqual(prog.get("tilt_fine"), 0)

    def test_roundtrip(self):
        pad = VCXYPad("XY")
        pad.bits16 = True
        pad2 = VCXYPad()
        pad2.apply_dict(pad.to_dict())
        self.assertTrue(pad2.bits16)


if __name__ == "__main__":
    unittest.main()
