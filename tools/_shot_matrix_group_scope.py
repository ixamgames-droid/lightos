"""Rendert die ECHTE RgbMatrixView (Programmer-Folgemodus) fuer beide Gruppen in
PNGs — visuelle Abnahme der Gruppen-Filterung OHNE die Live-App treiben zu muessen.

Laedt zuerst shows/Matrix_Gruppen_Test.lshow FRISCH (beweist: die Gruppen-Bindung
source_group uebersteht Show-Save/Load, weil per Name gebunden), waehlt dann je
Gruppe und greift das Widget per QWidget.grab().

Aufruf:  PYTHONPATH=<root> LIGHTOS_SHOW_DB=<temp> venv/Scripts/python.exe tools/_shot_matrix_group_scope.py
"""
from __future__ import annotations
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSize
_app = QApplication.instance() or QApplication([])

from sqlalchemy import select
from src.core.app_state import get_state
from src.core.database.models import FixtureGroup
from src.core.show.show_file import load_show
from src.ui.views.rgb_matrix_view import RgbMatrixView

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOW = os.path.join(_ROOT, "shows", "Matrix_Gruppen_Test.lshow")
OUT_DIR = os.path.join(_ROOT, "docs", "_verify")
os.makedirs(OUT_DIR, exist_ok=True)

# Frisch laden -> Round-Trip-Beweis (source_group ueberlebt Save/Load via Name).
load_show(SHOW)
state = get_state()

with state._session() as s:
    gid_strahler = s.execute(select(FixtureGroup.id).where(
        FixtureGroup.name == "Strahler")).scalar_one()
    gid_mh = s.execute(select(FixtureGroup.id).where(
        FixtureGroup.name == "Moving Heads")).scalar_one()

view = RgbMatrixView(follow_selection=True)
view.resize(QSize(1000, 600))


def shot(gid, fname, caption):
    state.set_selected_group_id(gid)
    view._sync_follow_selection()
    _app.processEvents()
    names = [view._list.item(i).text() for i in range(view._list.count())]
    header = view._group_header.text()
    path = os.path.join(OUT_DIR, fname)
    view.grab().save(path)
    print(f"[shot] {caption}")
    print(f"       Kopf:  {header}")
    print(f"       Liste: {names}")
    print(f"       -> {path}")
    return path


print(f"[load] {SHOW}")
p1 = shot(gid_strahler, "matrix_gruppe_strahler.png", "Gruppe »Strahler« aktiv")
p2 = shot(gid_mh, "matrix_gruppe_moving_heads.png", "Gruppe »Moving Heads« aktiv")
print("\nFERTIG. PNGs:")
print(f"  {p1}")
print(f"  {p2}")
