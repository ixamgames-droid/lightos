"""VC-Audit 2026-06-13 (A2): Button-Felder exclusive / clear_programmer / pad_color2.

Diese Felder werden vom Properties-Dialog jetzt editiert (Checkboxen + Farbwähler).
Der Test sichert die Serialisierung ab, auf der die UI aufbaut.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.ui.virtualconsole.vc_button import VCButton, ButtonAction

_app = QApplication.instance() or QApplication([])


class ButtonFieldRoundtripTest(unittest.TestCase):
    def test_exclusive_clear_pad2_roundtrip(self):
        b = VCButton("Solo")
        b.action = ButtonAction.FUNCTION_TOGGLE
        b.exclusive = True
        b.clear_programmer = True
        b.pad_color2 = (12, 34, 56)
        b2 = VCButton("X")
        b2.apply_dict(b.to_dict())
        self.assertTrue(b2.exclusive)
        self.assertTrue(b2.clear_programmer)
        self.assertEqual(b2.pad_color2, (12, 34, 56))

    def test_pad_color2_malformed_falls_back(self):
        b = VCButton("X")
        b.apply_dict({"type": "VCButton", "action": "Toggle", "pad_color2": [1, 2]})
        self.assertEqual(b.pad_color2, (0, 0, 255))

    def test_defaults(self):
        b = VCButton("X")
        self.assertFalse(b.exclusive)
        self.assertFalse(b.clear_programmer)
        self.assertEqual(b.pad_color2, (0, 0, 255))


if __name__ == "__main__":
    unittest.main()
