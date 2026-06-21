"""Wegwerf-Launcher fuer die Doku-Captures: startet LightOS UND laedt direkt die
VC-Widgets-Showcase-Show (kein fragiles Menue-Klicken). Fenster-Titel bleibt
'LightOS ...' -> lo.ps1 findet es.

Aufruf:  venv/Scripts/python.exe tools/_run_showcase_app.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from src.ui.main_window import MainWindow
from src.core.show.show_file import load_show

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOW = os.path.join(_ROOT, "shows", "VC_Widgets_Showcase.lshow")

app = QApplication(sys.argv)
app.setApplicationName("LightOS")
app.setApplicationVersion("1.0.0")
app.setOrganizationName("LightOS")
win = MainWindow(kiosk=False, touch=False)
win.show()


def _load():
    try:
        ok, msg = load_show(SHOW)
        print("load_show:", ok, msg, flush=True)
    except Exception as e:
        print("load_show error:", e, flush=True)


QTimer.singleShot(900, _load)
sys.exit(app.exec())
