"""VIZ-FIX-DECIMAL: LocaleTolerantDoubleSpinBox akzeptiert Punkt UND Komma.

Der Bug tritt nur unter einem Locale auf, das das Komma als Dezimaltrenner
erwartet (z. B. Deutsch) — dort verwirft die Standard-QDoubleSpinBox eine
Eingabe mit Punkt ("5.7"). Die Tests erzwingen daher deutsches Locale.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDoubleSpinBox
from PySide6.QtCore import QLocale
from PySide6.QtGui import QValidator

from src.ui.widgets.decimal_spinbox import LocaleTolerantDoubleSpinBox

_app = QApplication.instance() or QApplication([])


class LocaleTolerantDoubleSpinBoxTest(unittest.TestCase):
    def setUp(self):
        self._orig_locale = QLocale()
        QLocale.setDefault(QLocale(QLocale.Language.German, QLocale.Country.Germany))

    def tearDown(self):
        QLocale.setDefault(self._orig_locale)

    def _spin(self):
        sb = LocaleTolerantDoubleSpinBox()
        sb.setRange(-50, 50)
        sb.setDecimals(2)
        return sb

    def test_dot_is_accepted(self):
        self.assertEqual(self._spin().valueFromText("5.7"), 5.7)

    def test_comma_is_accepted(self):
        self.assertEqual(self._spin().valueFromText("5,7"), 5.7)

    def test_negative_and_integer(self):
        sb = self._spin()
        self.assertEqual(sb.valueFromText("-3.25"), -3.25)
        self.assertEqual(sb.valueFromText("12"), 12.0)

    def test_validate_accepts_both_separators(self):
        sb = self._spin()
        for text in ("5.7", "5,7", "12", "-3.25"):
            state, _t, _p = sb.validate(text, len(text))
            self.assertEqual(state, QValidator.State.Acceptable, text)

    def test_regression_default_spinbox_loses_dot(self):
        # Beleg für den Bug: die STANDARD-QDoubleSpinBox verliert unter deutschem
        # Locale den Punkt-Wert — unser Widget behebt genau das.
        plain = QDoubleSpinBox()
        plain.setRange(-50, 50)
        plain.setDecimals(2)
        self.assertNotEqual(plain.valueFromText("5.7"), 5.7)          # kaputt
        self.assertEqual(self._spin().valueFromText("5.7"), 5.7)      # unser Fix


if __name__ == "__main__":
    unittest.main()
