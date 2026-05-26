"""Headless smoke tests for key UI views/widgets."""
from __future__ import annotations
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_virtualconsole_widgets_and_canvas():
    _app()
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
    canvas = VCCanvas()

    canvas._add_widget("VCButton", QPoint(10, 10))
    dumped = canvas.to_dict()
    assert len(dumped["widgets"]) == 1


def test_core_views_smoke():
    _app()
    from src.ui.views.virtual_console_view import VirtualConsoleView
    from src.ui.views.simple_desk import SimpleDeskView
    from src.ui.views.efx_view import EfxView
    from src.ui.views.rgb_matrix_view import RgbMatrixView

    VirtualConsoleView()

    desk = SimpleDeskView()
    assert len(desk._faders) == 512

    efx = EfxView()
    efx._add_efx()
    assert len(efx._instances) == 1

    rgb = RgbMatrixView()
    rgb._add()
    assert len(rgb._instances) == 1


def test_qxf_import_dialog_smoke():
    _app()
    from src.ui.widgets.qxf_import_dialog import QxfImportDialog

    QxfImportDialog()
