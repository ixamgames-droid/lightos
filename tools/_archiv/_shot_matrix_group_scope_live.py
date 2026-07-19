"""Lesbare Screenshots der Gruppen-Filterung aus dem ECHTEN Hauptfenster.

Startet eine GEFENSTERTE MainWindow (echte Schriftarten), laedt
shows/Matrix_Gruppen_Test.lshow, navigiert programmatisch in den Programmer,
waehlt je Gruppe + den Matrix-Tab und greift das Fenster per QWidget.grab().
Kein Live-Klick-Raten, kein GDI noetig — und keine Hardware-Seiteneffekte
(Output/Audio per Env-Gate aus, Show-DB auf temp).

Aufruf:  PYTHONPATH=<root> venv/Scripts/python.exe tools/_shot_matrix_group_scope_live.py
"""
from __future__ import annotations
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# WICHTIG: NICHT offscreen -> echte Fonts. Hardware-Seiteneffekte abschalten.
os.environ["NO_OUTPUT_THREAD"] = "1"
os.environ["NO_AUDIO_AUTOSTART"] = "1"
os.environ.setdefault("LIGHTOS_SHOW_DB", os.path.join(
    os.environ.get("TEMP", "."), "lightos_shot_grpscope.db"))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QEventLoop, QTimer

app = QApplication.instance() or QApplication([])

from src.core.app_state import get_state
from src.core.show.show_file import load_show
from src.ui.main_window import MainWindow

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOW = os.path.join(_ROOT, "shows", "Matrix_Gruppen_Test.lshow")
OUT_DIR = os.path.join(_ROOT, "docs", "_verify")
os.makedirs(OUT_DIR, exist_ok=True)


def spin(ms: int):
    """Event-Loop kurz laufen lassen, damit Layout/deferred-singleShots greifen."""
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


mw = MainWindow()
mw.resize(1600, 980)
mw.show()
spin(700)

load_show(SHOW)
spin(600)

state = get_state()
mw._switch_section(2)              # Sektion 2 = Programmer
spin(250)

pv = mw._programmer_view
rgb = pv._embedded_rgb


def shot(group_name: str, fname: str):
    ok = state.select_group_by_name(group_name)
    pv._main_tabs.setCurrentIndex(pv._matrix_tab_index)
    rgb._sync_follow_selection()
    spin(450)
    names = [rgb._list.item(i).text() for i in range(rgb._list.count())]
    path = os.path.join(OUT_DIR, fname)
    mw.grab().save(path)
    print(f"[shot] Gruppe »{group_name}« (select_ok={ok})")
    print(f"       Kopf:  {rgb._group_header.text()}")
    print(f"       Liste: {names}")
    print(f"       -> {path}")


print(f"[load] {SHOW}")
shot("Strahler", "live_matrix_strahler.png")
shot("Moving Heads", "live_matrix_moving_heads.png")

spin(150)
app.quit()
print("FERTIG.")
