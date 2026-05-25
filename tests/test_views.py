"""Quick smoke test for new views (headless — checks imports and init)."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from PySide6.QtWidgets import QApplication
app = QApplication.instance() or QApplication(sys.argv)

errors = []

# VC widgets
try:
    from src.ui.virtualconsole import (VCButton, VCSlider, VCXYPad, VCLabel,
                                        VCCueList, VCSpeedDial, VCFrame, VCCanvas)
    b = VCButton(); s = VCSlider(); x = VCXYPad(); l = VCLabel()
    c = VCCueList(); d = VCSpeedDial(); f = VCFrame(); canvas = VCCanvas()
    print("OK  virtualconsole widgets")
except Exception as e:
    print(f"ERR virtualconsole: {e}")
    errors.append("vc")

# VC canvas: add/serialize
try:
    from PySide6.QtCore import QPoint
    w = canvas._add_widget("VCButton", QPoint(10, 10))
    d2 = canvas.to_dict()
    assert len(d2["widgets"]) == 1
    print("OK  VCCanvas add/serialize")
except Exception as e:
    print(f"ERR VCCanvas: {e}")
    errors.append("canvas")

# VirtualConsoleView
try:
    from src.ui.views.virtual_console_view import VirtualConsoleView
    vc_view = VirtualConsoleView()
    print("OK  VirtualConsoleView")
except Exception as e:
    print(f"ERR VirtualConsoleView: {e}")
    errors.append("vc_view")

# SimpleDeskView
try:
    from src.ui.views.simple_desk import SimpleDeskView
    desk = SimpleDeskView()
    assert len(desk._faders) == 512
    print("OK  SimpleDeskView (512 faders)")
except Exception as e:
    print(f"ERR SimpleDeskView: {e}")
    errors.append("simple_desk")

# EfxView
try:
    from src.ui.views.efx_view import EfxView
    efx = EfxView()
    efx._add_efx()
    assert len(efx._instances) == 1
    print("OK  EfxView")
except Exception as e:
    print(f"ERR EfxView: {e}")
    errors.append("efx")

# RgbMatrixView
try:
    from src.ui.views.rgb_matrix_view import RgbMatrixView
    rgb = RgbMatrixView()
    rgb._add()
    assert len(rgb._instances) == 1
    print("OK  RgbMatrixView")
except Exception as e:
    print(f"ERR RgbMatrixView: {e}")
    errors.append("rgb")

# QxfImportDialog
try:
    from src.ui.widgets.qxf_import_dialog import QxfImportDialog
    dlg = QxfImportDialog()
    print("OK  QxfImportDialog")
except Exception as e:
    print(f"ERR QxfImportDialog: {e}")
    errors.append("qxf_dlg")

print()
if errors:
    print(f"FAILED: {errors}")
    sys.exit(1)
else:
    print("All views OK!")
