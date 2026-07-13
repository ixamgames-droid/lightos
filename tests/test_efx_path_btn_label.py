"""EFX-PATH-BTN-LABEL: Die Custom-Path-Buttons ("+ Aufzeichnen…" / "Bearbeiten…")
im EFX-Editor duerfen nicht abgeschnitten werden ("eich"/"beit").

Regression: der stretchende Pfad-Combo darf die beschrifteten Buttons nicht unter
ihre Label-Breite quetschen — sie brauchen eine ausreichende Mindestbreite, damit
die Beschriftung vollstaendig sichtbar bleibt.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont, QFontMetrics

_app = QApplication.instance() or QApplication([])

from src.ui.views.efx_view import EfxView


class EfxPathButtonLabelTest(unittest.TestCase):
    def setUp(self):
        self.v = EfxView()

    def _label_width(self, btn):
        # Buttons rendern per StyleSheet mit 10px-Font — genau diese Breite messen.
        f = QFont(btn.font())
        f.setPixelSize(10)
        return QFontMetrics(f).horizontalAdvance(btn.text())

    def test_path_buttons_wide_enough_for_label(self):
        for btn in (self.v._btn_path_new, self.v._btn_path_edit):
            label_w = self._label_width(btn)
            # Mindestbreite ODER sizeHint muessen die Beschriftung vollstaendig fassen.
            fits = (btn.minimumWidth() >= label_w
                    or btn.sizeHint().width() >= label_w)
            self.assertTrue(
                fits,
                f"Button {btn.text()!r}: minimumWidth={btn.minimumWidth()} "
                f"sizeHint.w={btn.sizeHint().width()} < label_w={label_w}",
            )


if __name__ == "__main__":
    unittest.main()
