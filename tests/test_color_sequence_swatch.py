"""MXP-04: Color-Sequence-Swatches sind einzeln anklickbar (Klick -> Color-Picker).

Testet (a) die Hit-Test-Logik der Swatch-Vorschau (Klick-X -> richtiger Index) und
(b) dass ein Klick die gewaehlte Farbe live in die Sequence uebernimmt (Picker
gemockt, da modal).
"""
import os
import types
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor

import src.ui.widgets.color_sequence_editor as CSE
from src.ui.widgets.color_sequence_editor import ColorSequenceField, _SwatchStrip
from src.core.engine.rgb_matrix import ColorSequence

_app = QApplication.instance() or QApplication([])


def _ev(x):
    """Minimaler Stub fuer QMouseEvent: nur position().x() wird genutzt."""
    return types.SimpleNamespace(position=lambda: types.SimpleNamespace(x=lambda: float(x)))


class SwatchHitTestTest(unittest.TestCase):
    def test_click_index(self):
        strip = _SwatchStrip()
        strip.set_sequence(ColorSequence([(255, 0, 0), (0, 255, 0), (0, 0, 255)]))
        strip.resize(120, 20)            # 3 Swatches a 40 px
        got = []
        strip.swatch_clicked.connect(got.append)
        strip.mousePressEvent(_ev(10))   # -> 0
        strip.mousePressEvent(_ev(50))   # -> 1
        strip.mousePressEvent(_ev(100))  # -> 2
        self.assertEqual(got, [0, 1, 2])

    def test_empty_sequence_no_emit(self):
        strip = _SwatchStrip()
        strip.set_sequence(ColorSequence([]))
        got = []
        strip.swatch_clicked.connect(got.append)
        strip.mousePressEvent(_ev(10))
        self.assertEqual(got, [])


class FieldPickColorTest(unittest.TestCase):
    def setUp(self):
        self._orig = CSE.QColorDialog.getColor

    def tearDown(self):
        CSE.QColorDialog.getColor = self._orig

    def test_pick_color_mutates_live(self):
        seq = ColorSequence([(255, 0, 0), (0, 255, 0), (0, 0, 255)])
        field = ColorSequenceField()
        field.set_sequence(seq)
        fired = []
        field.changed.connect(lambda: fired.append(True))
        CSE.QColorDialog.getColor = staticmethod(lambda *a, **k: QColor(10, 20, 30))
        field._pick_color(1)
        self.assertEqual(tuple(seq.color_at(1)), (10, 20, 30))
        self.assertEqual(seq.active_index, 1)
        self.assertTrue(fired)

    def test_pick_color_cancel_keeps_value(self):
        seq = ColorSequence([(255, 0, 0), (0, 255, 0)])
        field = ColorSequenceField()
        field.set_sequence(seq)
        CSE.QColorDialog.getColor = staticmethod(lambda *a, **k: QColor())  # invalid = Abbruch
        field._pick_color(0)
        self.assertEqual(tuple(seq.color_at(0)), (255, 0, 0))

    def test_pick_color_out_of_range_safe(self):
        seq = ColorSequence([(255, 0, 0)])
        field = ColorSequenceField()
        field.set_sequence(seq)
        field._pick_color(5)   # darf nicht crashen
        self.assertEqual(len(seq), 1)


if __name__ == "__main__":
    unittest.main()
