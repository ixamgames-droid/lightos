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
        """★★ QA-52: Dieser Test war gruen, auch OHNE den Fix — gemessen.

        Die alte Fassung fragte ``minimumWidth() >= label_w ODER
        sizeHint().width() >= label_w``. Der zweite Zweig ist bei einem
        ``QPushButton`` **per Definition** erfuellt: Qt berechnet den sizeHint
        aus genau diesem Text. Die Bedingung war damit immer wahr, und der
        eigentliche Fix (``setMinimumWidth``) ungeprueft.

        **Der Fehler entstand aber gar nicht am sizeHint, sondern am Layout:**
        das stretchende Combo daneben quetschte die Buttons zusammen, bis nur
        noch „eich"/„beit" zu lesen war. Deshalb misst dieser Test jetzt die
        Breite, die der Button im ECHTEN Layout bei schmalem Fenster bekommt.

        Nachgemessen bei 360 px Fensterbreite: mit Fix 94 px bei 74 px
        Textbreite, ohne Fix **28 px** — der Test ist ohne den Fix rot.
        """
        self.v.resize(360, 700)      # schmal genug, dass das Combo quetscht
        self.v.show()
        QApplication.processEvents()
        self.addCleanup(self.v.hide)
        for btn in (self.v._btn_path_new, self.v._btn_path_edit):
            label_w = self._label_width(btn)
            self.assertGreaterEqual(
                btn.width(), label_w,
                f"Button {btn.text()!r} ist im Layout auf {btn.width()} px "
                f"gequetscht, die Beschriftung braucht {label_w} px — der "
                f"Text wird abgeschnitten.")


if __name__ == "__main__":
    unittest.main()
