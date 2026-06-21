"""WS3: VCEffectColors — Farb-Editor fuer die ColorSequence eines Matrix-Effekts.

Das Widget spiegelt die lebende ColorSequence (effect_live.get_param("colors")):
Umfaerben (Picker) und An/Aus (Rechtsklick) wirken sofort auf den Effekt; die
Farben selbst gehoeren dem Effekt und werden NICHT im Widget serialisiert.
"""
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor

from src.core.engine.function_manager import get_function_manager
from src.core.engine.rgb_matrix import RgbMatrixInstance, RgbAlgorithm, ColorSequence


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


class VcEffectColorsTest(unittest.TestCase):

    def setUp(self):
        _app()
        self.fm = get_function_manager()
        self.fm.stop_all()
        self.m = RgbMatrixInstance(name="ec", cols=4, rows=1,
                                   algorithm=RgbAlgorithm.CHASE, fixture_grid=[1, 2, 3, 4])
        self.m.colors = ColorSequence([(255, 0, 0), (0, 255, 0), (0, 0, 255)])
        self.fm.add(self.m)

    def tearDown(self):
        self.fm.stop_all()
        self.fm.remove(self.m.id)

    def _widget(self):
        from src.ui.virtualconsole.vc_effect_colors import VCEffectColors
        w = VCEffectColors()
        w.function_id = self.m.id
        w.resize(220, 80)
        return w

    def test_seq_reads_matrix_colors(self):
        w = self._widget()
        seq = w._seq()
        self.assertIsNotNone(seq)
        self.assertEqual(len(seq), 3)
        self.assertEqual(seq.color_at(1), (0, 255, 0))

    def test_recolor_via_picker(self):
        w = self._widget()
        seq = w._seq()
        with patch("src.ui.virtualconsole.vc_effect_colors.QColorDialog.getColor",
                   return_value=QColor(10, 20, 30)):
            w._pick_color(1, seq)
        self.assertEqual(self.m.colors.color_at(1), (10, 20, 30))
        self.assertEqual(self.m.colors.active_index, 1)

    def test_right_click_toggles_enabled(self):
        from PySide6.QtGui import QMouseEvent
        from PySide6.QtCore import Qt, QPointF, QEvent
        w = self._widget()
        before = self.m.colors.entries[0][1]
        ev = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(15, 45),
                         Qt.MouseButton.RightButton, Qt.MouseButton.RightButton,
                         Qt.KeyboardModifier.NoModifier)
        w.mousePressEvent(ev)
        self.assertNotEqual(self.m.colors.entries[0][1], before)

    def test_no_target_no_crash(self):
        from src.ui.virtualconsole.vc_effect_colors import VCEffectColors
        w = VCEffectColors()        # keine Bindung
        w.resize(220, 80)
        self.assertIsNone(w._seq())
        w.grab()                    # paintEvent ausloesen -> kein Crash bei leerem Ziel

    def test_paint_with_colors_no_crash(self):
        w = self._widget()
        w.grab()

    def test_roundtrip_no_colors_in_dict(self):
        w = self._widget()
        w.edit_slot = "MX"
        d = w.to_dict()
        self.assertEqual(d.get("function_id"), self.m.id)
        self.assertEqual(d.get("edit_slot"), "MX")
        self.assertNotIn("colors", d)
        from src.ui.virtualconsole.vc_effect_colors import VCEffectColors
        w2 = VCEffectColors()
        w2.apply_dict(d)
        self.assertEqual(w2.function_id, self.m.id)
        self.assertEqual(w2.edit_slot, "MX")


if __name__ == "__main__":
    unittest.main()
