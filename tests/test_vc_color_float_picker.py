"""VC-Audit 2026-06-13 (B): VCColor schwebender, nicht-modaler Farb-Picker.

Doppelklick auf die Farbkachel öffnet einen NICHT-modalen QColorDialog; Farb-
änderungen wirken live (currentColorChanged → _on_live_color). Vorher war Farbe
nur über den modalen Dialog tief in den Einstellungen änderbar.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor

from src.ui.virtualconsole.vc_color import VCColor

_app = QApplication.instance() or QApplication([])


class FloatingPickerTest(unittest.TestCase):
    def test_live_color_updates_tile(self):
        t = VCColor("Rot")
        t._edit_mode = True                  # kein _apply auf Fixtures im Edit-Mode
        t._on_live_color(QColor(10, 20, 30))
        self.assertEqual((t.color_r, t.color_g, t.color_b), (10, 20, 30))

    def test_invalid_color_ignored(self):
        t = VCColor("X")
        t._edit_mode = True
        before = (t.color_r, t.color_g, t.color_b)
        t._on_live_color(QColor())           # ungültig
        self.assertEqual((t.color_r, t.color_g, t.color_b), before)

    def test_picker_is_non_modal(self):
        t = VCColor("X")
        t._open_color_picker()
        self.assertIsNotNone(t._color_picker)
        self.assertFalse(t._color_picker.isModal())
        t._color_picker.close()

    def test_reopen_does_not_crash(self):
        t = VCColor("X")
        t._open_color_picker()
        first = t._color_picker
        t._open_color_picker()               # bringt nur nach vorn
        self.assertIs(t._color_picker, first)
        t._color_picker.close()


if __name__ == "__main__":
    unittest.main()
