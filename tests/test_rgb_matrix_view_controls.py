"""Schliesst die Alt-Bugs B-2/B-3 (RGB-Matrix-Vorschau / Start-Stopp) ab.

Beide stammen aus der Zeit VOR dem Function-Umbau (TODO P-02/P-03). Seitdem:
- Start/Stopp wirken auf die echte Instanz im FunctionManager (B-3),
- die Vorschau treibt ihre Phase per QTimer selbst und liest live aus der Matrix,
  spiegelt also Parameteraenderungen sofort (B-2).
Dieser Test verifiziert das und hält es als Regression fest.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.core.engine.function_manager import get_function_manager
from src.ui.views.rgb_matrix_view import RgbMatrixView

_app = QApplication.instance() or QApplication([])


class MatrixViewControlsTest(unittest.TestCase):
    def setUp(self):
        self.fm = get_function_manager()
        self.fm.stop_all()
        self._pre = {f.id for f in self.fm.all()}
        self.view = RgbMatrixView()

    def tearDown(self):
        self.fm.stop_all()
        for f in list(self.fm.all()):
            if f.id not in self._pre:
                self.fm.remove(f.id)

    def test_start_stop_buttons_control_function(self):   # B-3
        self.view._add()
        self.assertIsNotNone(self.view._saved)
        fid = self.view._saved.id
        self.view._start()
        self.assertTrue(self.fm.is_running(fid))
        self.view._stop()
        self.assertFalse(self.fm.is_running(fid))

    def test_preview_tick_advances_and_populates(self):    # B-2
        self.view._add()
        self.view._preview.set_matrix(self.view._current)
        self.view._current.matrix_speed = 2.0
        step0 = self.view._current._step
        self.view._preview._tick()
        self.assertGreater(self.view._current._step, step0)
        self.assertTrue(self.view._preview._grid)          # Vorschau live gefuellt

    def test_start_without_selection_is_noop(self):
        self.view._select(-1)
        self.assertIsNone(self.view._saved)
        self.view._start()      # darf nicht crashen
        self.view._stop()


if __name__ == "__main__":
    unittest.main()
