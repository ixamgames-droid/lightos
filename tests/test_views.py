"""Quick smoke tests for key UI views/widgets."""
from __future__ import annotations

import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPoint


_APP = QApplication.instance() or QApplication(sys.argv)


class ViewSmokeTests(unittest.TestCase):
    def test_virtualconsole_widgets_import_and_init(self):
        from src.ui.virtualconsole import (
            VCButton, VCSlider, VCXYPad, VCLabel,
            VCCueList, VCSpeedDial, VCFrame, VCCanvas,
        )
        VCButton()
        VCSlider()
        VCXYPad()
        VCLabel()
        VCCueList()
        VCSpeedDial()
        VCFrame()
        VCCanvas()

    def test_vc_canvas_add_and_serialize(self):
        from src.ui.virtualconsole import VCCanvas
        canvas = VCCanvas()
        canvas._add_widget("VCButton", QPoint(10, 10))
        data = canvas.to_dict()
        self.assertEqual(len(data["widgets"]), 1)

    def test_virtual_console_view(self):
        from src.ui.views.virtual_console_view import VirtualConsoleView
        VirtualConsoleView()

    def test_simple_desk_view(self):
        from src.ui.views.simple_desk import SimpleDeskView
        desk = SimpleDeskView()
        self.assertEqual(len(desk._faders), 512)

    def test_efx_view(self):
        from src.ui.views.efx_view import EfxView
        efx = EfxView()
        efx._add_efx()
        self.assertEqual(len(efx._instances), 1)

    def test_rgb_matrix_view(self):
        from src.ui.views.rgb_matrix_view import RgbMatrixView
        rgb = RgbMatrixView()
        rgb._add()
        self.assertEqual(len(rgb._instances), 1)

    def test_qxf_import_dialog(self):
        from src.ui.widgets.qxf_import_dialog import QxfImportDialog
        QxfImportDialog()


if __name__ == "__main__":
    unittest.main()
