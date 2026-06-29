r"""VC-TEST-SHOW 2026 — Rig-Positionen + Gruppen + sofort leuchtende Test-Effekte
+ eine VC-Seite mit den NEUEN Widgets (Farb-Editor, Bus-Selektor, BPM-Anzeige)
und APC-Pad-Bindung.

Davids Layout-Wunsch (Live-View 2D, 1550x800; oben=Buehne, unten=Publikum):
  - 8 PAR nebeneinander in der Mitte (eine Reihe).
  - MH Links/Rechts links/rechts HINTER dem ersten/letzten PAR (aus der Reihe).
  - 2 Spider VOR dem 3. und 6. PAR.

Effekte leuchten standalone (drive_intensity=True) -> kein Dimmer-Gefummel noetig.

Aufruf (headless, eigene Test-DB, ruehrt current_show.db NICHT an):
  set LIGHTOS_SHOW_DB=%TEMP%\lightos_vctest.db
  venv\Scripts\python.exe tools\build_vc_test_2026.py
Erzeugt: shows/VC_Test_2026.lshow
"""
from __future__ import annotations
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# Eigene Test-DB, damit der Build die laufende App / current_show.db nicht stoert.
os.environ.setdefault("LIGHTOS_SHOW_DB",
                      os.path.join(os.environ.get("TEMP", "."), "lightos_vctest.db"))
os.environ.setdefault("LIGHTOS_NO_OUTPUT_THREAD", "1")
os.environ.setdefault("LIGHTOS_NO_AUDIO_AUTOSTART", "1")

import json
import _gen_env  # noqa: F401  # DEMO-02: spawn-sichere Env-Schalter vor src.core (tools/_gen_env.py)
from PySide6.QtWidgets import QApplication
_app = QApplication.instance() or QApplication([])

from sqlalchemy import select, delete
from sqlalchemy.orm import Session
from src.core.app_state import get_state
from src.core.database.fixture_db import engine as fdb_engine
from src.core.database.models import PatchedFixture, FixtureProfile, FixtureGroup
from src.core.engine.function_manager import get_function_manager
from src.core.engine.rgb_matrix import RgbAlgorithm, MatrixStyle, ColorSequence, RgbMatrixInstance
from src.core.engine.efx import EfxFixture, EfxAlgorithm, EfxInstance
from src.core.show.show_file import reset_show, save_show, load_show
from src.ui.virtualconsole.vc_button import VCButton, ButtonAction
from src.ui.virtualconsole.vc_slider import VCSlider, SliderMode
from src.ui.virtualconsole.vc_effect_colors import VCEffectColors
from src.ui.virtualconsole.vc_bus_selector import VCBusSelector
from src.ui.virtualconsole.vc_bpm_display import VCBpmDisplay

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(_ROOT, "shows", "VC_Test_2026.lshow")


def profile_id(short: str) -> int:
    with Session(fdb_engine()) as s:
        pid = s.execute(select(FixtureProfile.id).where(
            FixtureProfile.short_name == short)).scalar_one_or_none()
    if pid is None:
        raise SystemExit(f"Profil '{short}' fehlt — App einmal starten (ensure_builtins).")
    return int(pid)


# ── 0) Patch (identische Adressen wie Davids Rig) ────────────────────────────
reset_show()
state = get_state()
fm = get_function_manager()
PAR_PID, MH_PID, SPIDER_PID = profile_id("ZQ01424"), profile_id("ZQ02001"), profile_id("SPIDER14")

par_fids = list(range(1, 9))
addr = 1
for i in range(8):
    state.add_fixture(PatchedFixture(
        fid=i + 1, label=f"PAR {i + 1}", fixture_profile_id=PAR_PID,
        mode_name="8-Kanal RGBW", universe=1, address=addr, channel_count=8,
        manufacturer_name="Generic", fixture_name="Stage Light ZQ01424",
        fixture_type="par"), undoable=False)
    addr += 8
for fid, lbl, a in ((9, "MH Links", 65), (10, "MH Rechts", 76)):
    state.add_fixture(PatchedFixture(
        fid=fid, label=lbl, fixture_profile_id=MH_PID, mode_name="11-Kanal",
        universe=1, address=a, channel_count=11, manufacturer_name="U King",
        fixture_name="ZQ02001 Mini Moving Head", fixture_type="moving_head"), undoable=False)
for fid, lbl, a in ((11, "Spider Links", 87), (12, "Spider Rechts", 101)):
    state.add_fixture(PatchedFixture(
        fid=fid, label=lbl, fixture_profile_id=SPIDER_PID, mode_name="14-Kanal",
        universe=1, address=a, channel_count=14, manufacturer_name="U King",
        fixture_name="Spider 14ch", fixture_type="moving_head"), undoable=False)

mh_fids, spider_fids = [9, 10], [11, 12]
mover_fids = mh_fids + spider_fids
color_fids = par_fids + spider_fids
state._rebuild_render_plan()


# ── 1) Positionen (Live-View 2D + 3D-Visualizer) ─────────────────────────────
# Live-View-Welt 1550x800: PAR-Reihe Mitte (y=400), MH hinten aussen (y=230),
# Spider vorne vor PAR3/PAR6 (y=600).
PX = {i + 1: 350 + i * 120 for i in range(8)}          # PAR x: 350..1190 (zentriert)
lv = {fid: (float(PX[fid]), 400.0) for fid in par_fids}
lv[9] = (230.0, 230.0)                                  # MH Links: hinter+links von PAR1
lv[10] = (1310.0, 230.0)                                # MH Rechts: hinter+rechts von PAR8
lv[11] = (float(PX[3]), 600.0)                          # Spider1: vor PAR3
lv[12] = (float(PX[6]), 600.0)                          # Spider2: vor PAR6
state.live_view_positions = dict(lv)
# 3D-Visualizer (Meter, Boden y=0): gleiche Anordnung, zentriert um 0.
vz = {fid: ((PX[fid] - 770) / 110.0, 0.0, 0.0) for fid in par_fids}
vz[9] = (-5.0, 0.0, -1.6); vz[10] = (5.0, 0.0, -1.6)
vz[11] = ((PX[3] - 770) / 110.0, 0.0, 1.6)
vz[12] = ((PX[6] - 770) / 110.0, 0.0, 1.6)
state.visualizer_positions = dict(vz)


# ── 2) Gruppen ───────────────────────────────────────────────────────────────
with state._session() as s:
    s.execute(delete(FixtureGroup))
    s.add(FixtureGroup(name="Alle PAR", cols=8, rows=1,
                       positions_json=json.dumps({f"{i},0": par_fids[i] for i in range(8)})))
    s.add(FixtureGroup(name="PAR Links", cols=4, rows=1,
                       positions_json=json.dumps({f"{i},0": par_fids[i] for i in range(4)})))
    s.add(FixtureGroup(name="PAR Rechts", cols=4, rows=1,
                       positions_json=json.dumps({f"{i},0": par_fids[4 + i] for i in range(4)})))
    s.add(FixtureGroup(name="Moving Heads", cols=2, rows=1,
                       positions_json=json.dumps({"0,0": 9, "1,0": 10})))
    s.add(FixtureGroup(name="Spider", cols=2, rows=1,
                       positions_json=json.dumps({"0,0": 11, "1,0": 12})))
    s.add(FixtureGroup(name="Alle Mover", cols=4, rows=1,
                       positions_json=json.dumps({f"{i},0": mover_fids[i] for i in range(4)})))
    s.commit()


# ── 3) Test-Effekte (leuchten sofort: drive_intensity=True) ──────────────────
RED, GREEN, BLUE, WHITE, MAGENTA, CYAN = (255, 0, 0), (0, 255, 0), (0, 0, 255), \
    (255, 255, 255), (255, 0, 255), (0, 255, 255)


def matrix(name, algo, grid, colors=None, style=MatrixStyle.RGB, drive=True,
           speed=1.0, params=None, bus="", mult=1.0):
    m = fm.new_rgb_matrix(name)
    m.algorithm = algo
    m.fixture_grid = list(grid)
    m.cols, m.rows = len(grid), 1
    if colors:
        m.colors = ColorSequence([tuple(c) for c in colors])
    m.style = style
    m.drive_intensity = drive          # True -> Matrix steuert auch die Helligkeit
    m.matrix_speed = speed
    if params:
        m.params = dict(params)
    if bus:
        m.tempo_bus_id = bus
        m.tempo_multiplier = mult
    return m


m_rainbow = matrix("Regenbogen", RgbAlgorithm.RAINBOW, par_fids, speed=0.8, bus="A")
m_rg = matrix("Rot-Gruen Lauf", RgbAlgorithm.CHASE, par_fids, colors=[RED, GREEN],
              params={"axis": "H", "movement": "normal", "color_cycle": True}, speed=1.2, bus="A")
m_grad = matrix("Farbverlauf Blau-Pink", RgbAlgorithm.GRADIENT, par_fids, colors=[BLUE, MAGENTA],
                params={"axis": "H", "blend": "smooth"}, speed=0.6)
m_fade = matrix("Farbwechsel", RgbAlgorithm.COLORFADE, color_fids,
                colors=[RED, GREEN, BLUE, WHITE], speed=0.8)
m_strobe = matrix("Weiss-Blitz", RgbAlgorithm.STROBE, color_fids, colors=[WHITE], speed=6.0,
                  bus="B", mult=2.0)
MATRICES = [m_rainbow, m_rg, m_grad, m_fade, m_strobe]


def efx(name, algo, fids, phase_mode="sync", spread=1.0, counter=False, size=120.0, speed_hz=0.5):
    e = fm.new_efx(name)
    e.algorithm = algo
    e.fixtures = [EfxFixture(fid=f) for f in fids]
    e.speed_hz, e.spread, e.open_beam = speed_hz, spread, True
    e.x_offset = e.y_offset = 128.0
    e.width = e.height = size
    e.phase_mode, e.counter_rotate = phase_mode, counter
    return e


e_mh = efx("MH Kreis", EfxAlgorithm.CIRCLE, mh_fids, phase_mode="fan", size=130, speed_hz=0.45)
e_spider = efx("Spider Kreis", EfxAlgorithm.CIRCLE, spider_fids, phase_mode="offset",
               counter=True, size=130, speed_hz=0.6)
EFX_FUNCS = [e_mh, e_spider]


# ── 4) Virtual Console — neue Widgets + APC-Pads ─────────────────────────────
widgets: list[dict] = []


def _add(w, x, y, ww, hh, bank=0):
    w.bank = bank
    w.setGeometry(x, y, ww, hh)
    widgets.append(w.to_dict())


# Reihe oben: An/Aus-Buttons fuer alle Effekte (APC-Pads Note 0..6, unten links beginnend).
ALL_FUNCS = MATRICES + EFX_FUNCS
ACCENT = ["#7a3030", "#307a40", "#30407a", "#7a6530", "#555555", "#305a7a", "#5a307a"]
for i, fn in enumerate(ALL_FUNCS):
    b = VCButton(fn.name)
    b.action = ButtonAction.FUNCTION_TOGGLE
    b.function_id = fn.id
    b.exclusive = isinstance(fn, RgbMatrixInstance)   # nur eine Matrix gleichzeitig
    b.solo_fixtures = True
    b.pad_style = "pulse"
    b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, i   # APC-Pad Note 0..6
    b._bg_color.setNamedColor(ACCENT[i % len(ACCENT)])
    _add(b, 20 + i * 124, 70, 116, 52)

# Farb-Editor (NEU) — an "Rot-Gruen Lauf" gebunden: Farben live umfaerben.
ec = VCEffectColors("Farben: Rot-Gruen")
ec.function_id = m_rg.id
_add(ec, 20, 140, 380, 92)

# Bus-Selektor (NEU) — A/B/C/D scharf schalten.
bsel = VCBusSelector("Tempo-Bus")
_add(bsel, 420, 140, 250, 92)

# BPM-Anzeige (NEU) — Bus A.
bpm = VCBpmDisplay("BPM Bus A")
bpm.tempo_bus_id = "A"
_add(bpm, 690, 140, 180, 96)

# Tempo-Bus-Bedienung: Tap / Sync / Tempo-Fader fuer Bus A (NEU).
btap = VCButton("Tap A"); btap.action = ButtonAction.TAP_BUS; btap.tempo_bus_id = "A"
btap.midi_type, btap.midi_ch, btap.midi_data1 = "note_on", 0, 7
_add(btap, 20, 250, 116, 46)
bsync = VCButton("Sync A"); bsync.action = ButtonAction.SYNC_BUS; bsync.tempo_bus_id = "A"
bsync.midi_type, bsync.midi_ch, bsync.midi_data1 = "note_on", 0, 8
_add(bsync, 144, 250, 116, 46)
tbf = VCSlider("Tempo Bus A"); tbf.mode = SliderMode.TEMPO_BUS; tbf.tempo_bus_id = "A"
tbf._value = 128; tbf.midi_cc, tbf.midi_ch = 48, 0
_add(tbf, 270, 250, 56, 150)
master = VCSlider("Master"); master.mode = SliderMode.GRANDMASTER
master._value = 255; master.midi_cc, master.midi_ch = 56, 0
_add(master, 340, 250, 56, 150)

# Universell (alle Banks): Clear / Stop All / Blackout (APC-Track-Tasten 100..102).
for i, (nm, act, col) in enumerate([("Clear", ButtonAction.CLEAR, "#4a3a10"),
                                    ("Stop All", ButtonAction.STOP_ALL, "#4a1010"),
                                    ("Blackout", ButtonAction.BLACKOUT, "#2a0000")]):
    b = VCButton(nm); b.action = act; b.pad_style = "solid"
    b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, 100 + i
    b._bg_color.setNamedColor(col)
    _add(b, 20 + i * 124, 430, 116, 40, bank=-1)

state._vc_layout = {"widgets": widgets}


# ── 5) Speichern + Verifikation ──────────────────────────────────────────────
state.programmer = {}
state.show_name = "VC-Test 2026"
save_show(OUT)
print("Gespeichert:", OUT)
ok, msg = load_show(OUT)
assert ok, f"Show laedt nicht: {msg}"
state = get_state()

fx = state.get_patched_fixtures()
assert len(fx) == 12, f"Fixtures: {len(fx)}"
assert len(state.live_view_positions) == 12, state.live_view_positions
# Layout-Plausibilitaet: MH hinter (kleineres y) der PAR-Reihe, Spider davor (groesseres y).
assert state.live_view_positions[9][1] < state.live_view_positions[1][1], "MH nicht hinten"
assert state.live_view_positions[11][1] > state.live_view_positions[1][1], "Spider nicht vorne"

mats = [f for f in fm.all() if isinstance(f, RgbMatrixInstance)]
efxs = [f for f in fm.all() if isinstance(f, EfxInstance)]
assert len(mats) >= 5, f"Matrizen: {len(mats)}"
assert len(efxs) >= 2, f"EFX: {len(efxs)}"
assert all(m.drive_intensity for m in mats), "Matrix ohne drive_intensity (wuerde dunkel bleiben)"
# Tempo-Bus an Effekten gesetzt?
by_name = {m.name: m for m in mats}
assert by_name["Regenbogen"].tempo_bus_id == "A" and by_name["Rot-Gruen Lauf"].tempo_bus_id == "A"
assert by_name["Weiss-Blitz"].tempo_bus_id == "B" and abs(by_name["Weiss-Blitz"].tempo_multiplier - 2.0) < 1e-6

vc = state._vc_layout.get("widgets", [])
types = {}
for w in vc:
    types[w["type"]] = types.get(w["type"], 0) + 1
assert types.get("VCEffectColors", 0) == 1, types
assert types.get("VCBusSelector", 0) == 1, types
assert types.get("VCBpmDisplay", 0) == 1, types
# Smart-Drop/APC: An/Aus-Buttons fuer alle 7 Effekte auf Pads 0..6.
toggle_btns = [w for w in vc if w.get("action") == "FunctionToggle"]
assert len(toggle_btns) == 7, f"Toggle-Buttons: {len(toggle_btns)}"
tap_bus = [w for w in vc if w.get("action") == "TapBus"]
sync_bus = [w for w in vc if w.get("action") == "SyncBus"]
assert tap_bus and sync_bus, "TAP_BUS/SYNC_BUS fehlen"
tempo_fader = [w for w in vc if w.get("type") == "VCSlider" and w.get("mode") == "TempoBus"]
assert tempo_fader, "TEMPO_BUS-Fader fehlt"

print(f"  Fixtures=12  Matrizen={len(mats)}  EFX={len(efxs)}  VC-Widgets={len(vc)}  Typen={types}")
print(f"  Positionen: PAR1={state.live_view_positions[1]} MHLinks={state.live_view_positions[9]} "
      f"Spider1={state.live_view_positions[11]}")
print("FERTIG")
