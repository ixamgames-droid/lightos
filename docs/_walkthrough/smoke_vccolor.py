"""Smoke-test the VCColor properties dialog builds without error.

The dialog uses exec() (modal/blocking), so we patch QDialog.exec to return
Rejected immediately and just confirm the grouped+scrolled dialog assembles.
"""
import sys
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from PySide6.QtWidgets import QApplication, QDialog


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    # don't actually block on a modal dialog
    QDialog.exec = lambda self: QDialog.DialogCode.Rejected
    from src.ui.virtualconsole.vc_color import VCColor
    vc = VCColor()
    try:
        vc._open_properties()
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"vccolor: FAIL ({e})")
        return 1
    print("vccolor: dialog built OK => PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
