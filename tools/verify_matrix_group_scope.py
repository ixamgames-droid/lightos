"""Verifikation: Matrix-Effekte pro Gruppe gefiltert (Programmer).

Baut eine kleine Show mit 2 Gruppen (»Strahler« = 4 PAR, »Moving Heads« = 2 MH)
und 4 Matrix-Effekten (2 an Strahler gebunden, 1 an Moving Heads, 1 ungebunden) und
fuehrt direkt einen END-TO-END-Test mit der ECHTEN RgbMatrixView (follow_selection)
+ echtem AppState + echter Gruppen-DB durch (keine Mocks):
  - Gruppe »Strahler« aktiv  -> Liste zeigt nur Strahler-Matrizen (+ ungebundene)
  - Gruppe »Moving Heads« aktiv -> nur MH-Matrizen (+ ungebundene); Strahler-Matrix WEG

Erzeugt zusaetzlich shows/Matrix_Gruppen_Test.lshow zum Live-Anschauen in der App.

Aufruf:  PYTHONPATH=<code-root> venv/Scripts/python.exe tools/verify_matrix_group_scope.py
"""
from __future__ import annotations
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
_app = QApplication.instance() or QApplication([])

from sqlalchemy import select, delete
from sqlalchemy.orm import Session
from src.core.app_state import get_state
from src.core.database.fixture_db import engine as fdb_engine
from src.core.database.models import PatchedFixture, FixtureProfile, FixtureGroup
from src.core.engine.function_manager import get_function_manager
from src.core.engine.rgb_matrix import RgbAlgorithm, grid_from_positions
from src.core.show.show_file import reset_show, save_show

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(_ROOT, "shows", "Matrix_Gruppen_Test.lshow")


def profile_id(short: str) -> int:
    with Session(fdb_engine()) as s:
        pid = s.execute(select(FixtureProfile.id).where(
            FixtureProfile.short_name == short)).scalar_one_or_none()
    if pid is None:
        raise SystemExit(f"Profil '{short}' fehlt — App einmal starten (ensure_builtins).")
    return int(pid)


# ── 0) Patch: 4 PAR + 2 MH ───────────────────────────────────────────────────
reset_show()
state = get_state()
fm = get_function_manager()
PAR_PID, MH_PID = profile_id("ZQ01424"), profile_id("ZQ02001")

addr = 1
par_fids = []
for i in range(4):
    fid = i + 1
    state.add_fixture(PatchedFixture(
        fid=fid, label=f"PAR {i + 1}", fixture_profile_id=PAR_PID,
        mode_name="8-Kanal RGBW", universe=1, address=addr, channel_count=8,
        manufacturer_name="Generic", fixture_name="Stage Light ZQ01424",
        fixture_type="par"), undoable=False)
    par_fids.append(fid)
    addr += 8

for fid, lbl, a in ((9, "MH Links", 65), (10, "MH Rechts", 76)):
    state.add_fixture(PatchedFixture(
        fid=fid, label=lbl, fixture_profile_id=MH_PID, mode_name="11-Kanal",
        universe=1, address=a, channel_count=11, manufacturer_name="U King",
        fixture_name="ZQ02001 Mini Moving Head", fixture_type="moving_head"), undoable=False)
mh_fids = [9, 10]

# ── 1) Zwei Gruppen ──────────────────────────────────────────────────────────
STRAHLER_POS = {f"{i},0": par_fids[i] for i in range(4)}
MH_POS = {"0,0": 9, "1,0": 10}
with state._session() as s:
    s.execute(delete(FixtureGroup))
    s.add(FixtureGroup(name="Strahler", cols=4, rows=1,
                       positions_json=json.dumps(STRAHLER_POS)))
    s.add(FixtureGroup(name="Moving Heads", cols=2, rows=1,
                       positions_json=json.dumps(MH_POS)))
    s.commit()
try:
    state.notify_groups_changed()
except Exception:
    pass


def mk(name, group, algo, pos=None, cols=1, rows=1):
    m = fm.new_rgb_matrix(name)
    m.algorithm = algo
    m.source_group = group           # Bindung per Gruppen-Name (None = ungebunden)
    if pos is not None:
        m.cols, m.rows = cols, rows
        m.fixture_grid = grid_from_positions(pos, cols, rows)
    return m


# ── 2) Vier Matrizen: 2x Strahler, 1x Moving Heads, 1x ungebunden ────────────
mk("Strahler Lauflicht", "Strahler", RgbAlgorithm.CHASE, STRAHLER_POS, 4, 1)
mk("Strahler Fuellung", "Strahler", RgbAlgorithm.FILL, STRAHLER_POS, 4, 1)
mk("MH Welle", "Moving Heads", RgbAlgorithm.WAVE, MH_POS, 2, 1)
mk("Global Rainbow (ungebunden)", None, RgbAlgorithm.RAINBOW)

save_show(OUT)
print(f"[build] gespeichert: {OUT}")

# ── 3) END-TO-END mit der ECHTEN View (kein Mock) ────────────────────────────
with state._session() as s:
    gid_strahler = s.execute(select(FixtureGroup.id).where(
        FixtureGroup.name == "Strahler")).scalar_one()
    gid_mh = s.execute(select(FixtureGroup.id).where(
        FixtureGroup.name == "Moving Heads")).scalar_one()

from src.ui.views.rgb_matrix_view import RgbMatrixView
view = RgbMatrixView(follow_selection=True)


def listed_after_selecting(gid):
    state.set_selected_group_id(gid)
    view._sync_follow_selection()
    return [view._list.item(i).text() for i in range(view._list.count())]


fails = 0


def check(label, got, expected):
    global fails
    ok = set(got) == set(expected)
    fails += 0 if ok else 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    print(f"         erwartet: {sorted(expected)}")
    print(f"         erhalten: {sorted(got)}")


print("\n[E2E] Liste pro Gruppe (echte RgbMatrixView, echter AppState):")
strahler_list = listed_after_selecting(gid_strahler)
check("Gruppe »Strahler«",
      strahler_list,
      ["Strahler Lauflicht", "Strahler Fuellung", "Global Rainbow (ungebunden)"])

mh_list = listed_after_selecting(gid_mh)
check("Gruppe »Moving Heads«",
      mh_list,
      ["MH Welle", "Global Rainbow (ungebunden)"])

# Strahler-Matrix darf unter Moving Heads NICHT auftauchen
hidden_ok = "Strahler Lauflicht" not in mh_list
fails += 0 if hidden_ok else 1
print(f"  [{'PASS' if hidden_ok else 'FAIL'}] »Strahler Lauflicht« ist unter »Moving Heads« ausgeblendet")

print(f"\n[E2E] {'ALLE CHECKS BESTANDEN' if fails == 0 else f'{fails} FEHLER'}")
sys.exit(1 if fails else 0)
