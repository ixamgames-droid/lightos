"""Verifikation: EFX-Effekte pro Gruppe gefiltert (Programmer-FX-Tab).

Stellt Davids Fall nach: 2 Gruppen Moving Heads + EFX, davon eine GEBUNDEN je
Gruppe und eine UNGEBUNDENE (= so liegen bestehende/alte EFX in echten Shows vor,
weil es keinen 'Speichern'-Button gibt). Treibt die ECHTE EfxView(follow_selection)
+ echten AppState + echte Gruppen-DB (kein Mock) und liest die wirkliche Liste.

Aufruf:  venv/Scripts/python.exe tools/verify_efx_group_scope.py
"""
from __future__ import annotations
import os, sys, json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("LIGHTOS_NO_OUTPUT_THREAD", "1")
os.environ.setdefault("LIGHTOS_NO_AUDIO_AUTOSTART", "1")

from PySide6.QtWidgets import QApplication
_app = QApplication.instance() or QApplication([])

from sqlalchemy import select, delete
from sqlalchemy.orm import Session
from src.core.app_state import get_state
from src.core.database.fixture_db import engine as fdb_engine
from src.core.database.models import PatchedFixture, FixtureProfile, FixtureGroup
from src.core.engine.function_manager import get_function_manager
from src.core.engine.efx import EfxFixture, EfxAlgorithm
from src.core.show.show_file import reset_show


def profile_id(short: str) -> int:
    with Session(fdb_engine()) as s:
        pid = s.execute(select(FixtureProfile.id).where(
            FixtureProfile.short_name == short)).scalar_one_or_none()
    if pid is None:
        raise SystemExit(f"Profil '{short}' fehlt — App einmal starten (ensure_builtins).")
    return int(pid)


reset_show()
state = get_state()
fm = get_function_manager()
MH_PID = profile_id("ZQ02001")

# 4 Moving Heads (pan+tilt) -> 2 Gruppen
addr = 1
for fid, lbl in ((1, "MH L1"), (2, "MH L2"), (3, "MH R1"), (4, "MH R2")):
    state.add_fixture(PatchedFixture(
        fid=fid, label=lbl, fixture_profile_id=MH_PID, mode_name="11-Kanal",
        universe=1, address=addr, channel_count=11, manufacturer_name="U King",
        fixture_name="ZQ02001 Mini Moving Head", fixture_type="moving_head"),
        undoable=False)
    addr += 11

with state._session() as s:
    s.execute(delete(FixtureGroup))
    s.add(FixtureGroup(name="MH-Links", cols=2, rows=1,
                       positions_json=json.dumps({"0,0": 1, "1,0": 2})))
    s.add(FixtureGroup(name="MH-Rechts", cols=2, rows=1,
                       positions_json=json.dumps({"0,0": 3, "1,0": 4})))
    s.commit()
try:
    state.notify_groups_changed()
except Exception:
    pass


def mk(name, group, fids, algo=EfxAlgorithm.CIRCLE):
    e = fm.new_efx(name=name)
    e.algorithm = algo
    e.source_group = group
    e.fixtures = [EfxFixture(fid=f) for f in fids]
    return e


# Gebunden je Gruppe + EINE ungebundene (so liegen Davids bestehende EFX vor)
mk("Links Kreis",  "MH-Links",  [1, 2])
mk("Rechts Acht",  "MH-Rechts", [3, 4], EfxAlgorithm.EIGHT)
mk("Alt-Effekt (ungebunden, Geraete L)", None, [1, 2])

with state._session() as s:
    gid_l = s.execute(select(FixtureGroup.id).where(FixtureGroup.name == "MH-Links")).scalar_one()
    gid_r = s.execute(select(FixtureGroup.id).where(FixtureGroup.name == "MH-Rechts")).scalar_one()

from src.ui.views.efx_view import EfxView
view = EfxView(follow_selection=True)


def listed_after_selecting(gid, fids):
    state.set_selected_group_id(gid)
    state.set_selected_fids(fids)
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


print("\n[E2E] EFX-Liste pro Gruppe (echte EfxView, echter AppState):")
l_list = listed_after_selecting(gid_l, [1, 2])
check("Gruppe »MH-Links« — David will NUR Links-Effekte",
      l_list, ["Links Kreis", "Alt-Effekt (ungebunden, Geraete L)"])

r_list = listed_after_selecting(gid_r, [3, 4])
check("Gruppe »MH-Rechts« — David will NUR Rechts-Effekte",
      r_list, ["Rechts Acht"])

print(f"\n  >> 'Alt-Effekt (ungebunden)' unter MH-Rechts sichtbar? "
      f"{'JA — BUG' if 'Alt-Effekt (ungebunden, Geraete L)' in r_list else 'nein — ok'}")
print(f"\n[E2E] {'ALLE CHECKS BESTANDEN' if fails == 0 else f'{fails} FEHLER (so wie David es erlebt)'}")
sys.exit(1 if fails else 0)
