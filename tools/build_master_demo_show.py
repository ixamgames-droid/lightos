"""MASTER-DEMO-SHOW — „alles, was die Show jetzt kann", auf mehrere Banks verteilt.

Davids Setup: Akai APC mini (mk2) + 4× PAR (ZQ01424, 8ch RGBW) + 2× Moving Head
(ZQ02001, 11ch). Nutzt das Multi-Konsolen-/Bank-System (APC-SCENE-Tasten = Seiten)
und alle neuen Virtual-Console-Fenster-Widgets (Chase-Liste, Chase-Builder, XY-Pad).

  Seite 1  FARBEN & GRUPPEN   Farb-Kacheln (Programmer) · Gruppe-auswählen-Pads
                              (F-24) · Gruppen-Dimmer-Fader (F-25, PAR + MH).
  Seite 2  EFFEKTE            16 Effekte exklusiv: Dimmer-Chaser/Carousels,
                              Color-Chase, RGB-Matrix-Looks, MH-EFX inkl. Dreieck
                              & Random.
  Seite 3  MATRIX BUILDER     EINE Matrix + „Form ±" (alle Algorithmen) + Live-
                              Recolor (color1/2 + Sequence) + Feedback-Fenster.
  Seite 4  CHASE BUILDER      Das All-in-One-Chase-Builder-Fenster (Palette + Liste
                              + Aktionen + Speed/Hold).
  Seite 5  MOVING HEADS       XY-Pad zum Zielen, relative Acht, XY-Feld → Kreis.

Universell: Track-Tasten Clear/Stop All/Blackout/Tap; Fader F6 Dimmer, F7 Speed,
F9 Grand Master.

Aufruf:  venv/Scripts/python.exe tools/build_master_demo_show.py
Erzeugt: shows/Master_Demo.lshow
"""
from __future__ import annotations
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import _gen_env  # noqa: F401  # DEMO-02: spawn-sichere Env-Schalter vor src.core (tools/_gen_env.py)
from PySide6.QtWidgets import QApplication
_app = QApplication.instance() or QApplication([])

from sqlalchemy import select, delete
from sqlalchemy.orm import Session
from src.core.app_state import get_state, get_channels_for_patched
from src.core.database.fixture_db import engine as fdb_engine
from src.core.database.models import PatchedFixture, FixtureProfile, FixtureGroup
from src.core.engine.function_manager import get_function_manager
from src.core.engine.function import RunOrder, Direction
from src.core.engine.chaser import ChaserStep
from src.core.engine.rgb_matrix import RgbAlgorithm, ColorSequence
from src.core.engine.carousel import CarouselPattern
from src.core.engine.efx import EfxFixture, EfxAlgorithm
from src.core.show.show_file import reset_show, save_show, load_show
from src.ui.virtualconsole.vc_button import VCButton, ButtonAction
from src.ui.virtualconsole.vc_color import VCColor, ColorTarget
from src.ui.virtualconsole.vc_slider import VCSlider, SliderMode
from src.ui.virtualconsole.vc_label import VCLabel
from src.ui.virtualconsole.vc_color_list import VCColorList
from src.ui.virtualconsole.vc_xypad import VCXYPad

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(_ROOT, "shows", "Master_Demo.lshow")
TRACK0 = 100


def profile_id(short: str) -> int:
    with Session(fdb_engine()) as s:
        pid = s.execute(select(FixtureProfile.id).where(
            FixtureProfile.short_name == short)).scalar_one_or_none()
    if pid is None:
        raise SystemExit(f"Profil '{short}' fehlt — bitte App einmal starten.")
    return int(pid)


# ── 0) Basis + Patch ──────────────────────────────────────────────────────────
reset_show()
state = get_state()
fm = get_function_manager()
PAR_PID, MH_PID = profile_id("ZQ01424"), profile_id("ZQ02001")

par_fids: list[int] = []
addr = 1
for i in range(4):
    fid = i + 1
    state.add_fixture(PatchedFixture(
        fid=fid, label=f"PAR {i + 1}", fixture_profile_id=PAR_PID,
        mode_name="8-Kanal RGBW", universe=1, address=addr, channel_count=8,
        manufacturer_name="Generic", fixture_name="Stage Light ZQ01424",
        fixture_type="par"), undoable=False)
    par_fids.append(fid); addr += 8

mh_left, mh_right = 5, 6
for fid, lbl, a in ((mh_left, "MH Links", 33), (mh_right, "MH Rechts", 44)):
    state.add_fixture(PatchedFixture(
        fid=fid, label=lbl, fixture_profile_id=MH_PID, mode_name="11-Kanal",
        universe=1, address=a, channel_count=11, manufacturer_name="U King",
        fixture_name="ZQ02001 Mini Moving Head", fixture_type="moving_head"), undoable=False)
mh_fids = [mh_left, mh_right]

fixtures = state.get_patched_fixtures()
chan_of = {f.fid: {c.attribute: c.channel_number
                   for c in get_channels_for_patched(f)} for f in fixtures}
state.base_levels = {fid: {"intensity": 255} for fid in par_fids}
state._rebuild_render_plan()

with state._session() as s:
    s.execute(delete(FixtureGroup))
    s.add(FixtureGroup(name="PAR-Reihe", cols=4, rows=1,
                       positions_json=json.dumps({f"{i},0": par_fids[i] for i in range(4)})))
    s.add(FixtureGroup(name="Moving Heads", cols=2, rows=1,
                       positions_json=json.dumps({"0,0": mh_left, "1,0": mh_right})))
    s.add(FixtureGroup(name="Alle", cols=6, rows=1,
                       positions_json=json.dumps({f"{i},0": (par_fids + mh_fids)[i] for i in range(6)})))
    s.commit()


# ════════════════════════════════════════════════════════════════════════════
#  1) FUNKTIONEN
# ════════════════════════════════════════════════════════════════════════════
def par_dim(name, on_fids):
    sc = fm.new_scene(name); on = set(on_fids)
    for fid in par_fids:
        if "intensity" in chan_of[fid]:
            sc.set_value(fid, chan_of[fid]["intensity"], 255 if fid in on else 0)
    return sc


def par_look(name, r=0, g=0, b=0, w=0):
    sc = fm.new_scene(name)
    for fid in par_fids:
        cm = chan_of[fid]
        if "intensity" in cm:
            sc.set_value(fid, cm["intensity"], 255)
        for attr, val in (("color_r", r), ("color_g", g), ("color_b", b), ("color_w", w)):
            if attr in cm:
                sc.set_value(fid, cm[attr], val)
    return sc


def chaser(name, step_ids, hold=0.4, fade=0.0, speed=1.0):
    c = fm.new_chaser(name); c.run_order, c.direction, c.speed = RunOrder.Loop, Direction.Forward, speed
    for sid in step_ids:
        c.steps.append(ChaserStep(function_id=sid, fade_in=fade, hold=hold, fade_out=0.0))
    return c


def matrix(name, algo, speed=3.0, params=None, c1=(255, 0, 0), c2=(0, 0, 255), c3=(0, 255, 0)):
    m = fm.new_rgb_matrix(name)
    m.algorithm = algo; m.fixture_grid = list(par_fids); m.cols = len(par_fids); m.rows = 1
    m.color1, m.color2, m.color3 = c1, c2, c3; m.matrix_speed = speed
    if params:
        m.params = params
    return m


def mh_efx(name, algo, relative=False, spread=0.0):
    e = fm.new_efx(name); e.algorithm = algo
    e.fixtures = [EfxFixture(fid=mh_left), EfxFixture(fid=mh_right)]
    e.speed_hz = 0.4; e.spread = spread; e.open_beam = True; e.relative = relative
    e.width = e.height = 110.0
    return e


st = [par_dim(f"Dim P{i+1}", [par_fids[i]]) for i in range(4)]
st_all, st_off = par_dim("Dim alle", par_fids), par_dim("Dim aus", [])
st_odd, st_even = par_dim("Dim 1+3", [1, 3]), par_dim("Dim 2+4", [2, 4])
st_b = [par_dim(f"Build {i+1}", par_fids[:i+1]) for i in range(4)]
lk = [par_look("Rot", r=255), par_look("Grün", g=255), par_look("Blau", b=255),
      par_look("Amber", r=255, g=140), par_look("Cyan", g=255, b=255), par_look("Magenta", r=255, b=255)]

dim_run = chaser("Lauflicht", [st[0].id, st[1].id, st[2].id, st[3].id], hold=0.35, fade=0.08)
dim_ping = chaser("Ping-Pong", [st[0].id, st[1].id, st[2].id, st[3].id, st[2].id, st[1].id], hold=0.28, fade=0.06)
dim_pairs = chaser("2er-Chase", [st_odd.id, st_even.id], hold=0.4, fade=0.1)
dim_strobe = chaser("Strobe", [st_all.id, st_off.id], hold=0.04)
dim_build = chaser("Build-Up", [st_b[0].id, st_b[1].id, st_b[2].id, st_b[3].id, st_off.id], hold=0.3, fade=0.1)
dim_pulse = fm.new_carousel("Pulse"); dim_pulse.pattern = CarouselPattern.PULSE
dim_pulse.fixture_ids = list(par_fids); dim_pulse.speed = 1.0
dim_wave = fm.new_carousel("Wave"); dim_wave.pattern = CarouselPattern.WAVE
dim_wave.fixture_ids = list(par_fids); dim_wave.speed = 1.0
ch_color = chaser("Color-Chase", [lk[0].id, lk[1].id, lk[2].id, lk[3].id, lk[4].id, lk[5].id], hold=0.5, fade=0.25)

mx_rainbow = matrix("Mtx Regenbogen", RgbAlgorithm.RAINBOW, speed=1.5)
mx_fire = matrix("Mtx Feuer", RgbAlgorithm.FIRE, speed=2.0)
mx_plasma = matrix("Mtx Plasma", RgbAlgorithm.SINEPLASMA, speed=1.2)

efx_eight = mh_efx("MH Acht", EfxAlgorithm.EIGHT)
efx_circle = mh_efx("MH Kreis", EfxAlgorithm.CIRCLE)
efx_triangle = mh_efx("MH Dreieck", EfxAlgorithm.TRIANGLE)
efx_random = mh_efx("MH Random", EfxAlgorithm.RANDOM)

EFFECTS = [dim_run, dim_ping, dim_pairs, dim_strobe, dim_build, dim_pulse, dim_wave, ch_color,
           mx_rainbow, mx_fire, mx_plasma, efx_eight, efx_circle, efx_triangle, efx_random]
COLOR_FX_IDS = {ch_color.id, mx_rainbow.id, mx_fire.id, mx_plasma.id}

# Builder-Funktionen (Seite 3 + 4)
matrix_builder = matrix("Matrix-Builder", RgbAlgorithm.CHASE, speed=3.0, params={"axis": "H", "movement": "normal"})
matrix_builder.colors = ColorSequence([(255, 0, 0), (0, 0, 255), (0, 255, 0)])
chase_builder = matrix("Chase-Builder", RgbAlgorithm.COLORFADE, speed=2.0, params={"hold": 0.2})
chase_builder.colors = ColorSequence([(255, 0, 0), (0, 255, 0), (0, 0, 255)])
# Moving-Head-Effekte für Seite 5
efx_rel = mh_efx("MH Acht relativ", EfxAlgorithm.EIGHT, relative=True)
efx_area = mh_efx("MH Kreis Feld", EfxAlgorithm.CIRCLE, relative=False)


# ════════════════════════════════════════════════════════════════════════════
#  2) VIRTUAL CONSOLE
# ════════════════════════════════════════════════════════════════════════════
PAD, GAP, X0, Y0 = 60, 6, 20, 70
STEP = PAD + GAP
GRID_BOTTOM = Y0 + 8 * STEP
TY = GRID_BOTTOM + 4
Y_FAD = GRID_BOTTOM + 34
FAD_H = 142
RIGHT_X = X0 + 8 * STEP + 16
widgets: list[dict] = []
BANK_ALL = -1
B_COLOR, B_FX, B_MATRIX, B_CHASE, B_MH = range(5)
PAGE_NAMES = ["Farben & Gruppen", "Effekte", "Matrix Builder", "Chase Builder", "Moving Heads"]


def pad_pos(note):
    row, col = note // 8, note % 8
    return X0 + col * STEP, Y0 + (7 - row) * STEP


def slot_note(s):
    r, c = s // 8, s % 8
    return (7 - r) * 8 + c


def _add(w, x, y, ww, hh, bank):
    w.bank = bank; w.setGeometry(x, y, ww, hh); widgets.append(w.to_dict())


def func_btn(fn, note, bank, accent, exclusive=False, clear_prog=False):
    b = VCButton(fn.name)
    b.action = ButtonAction.FUNCTION_TOGGLE; b.function_id = fn.id; b.pad_style = "pulse"
    b.exclusive = exclusive; b.clear_programmer = clear_prog
    b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, note
    b._bg_color.setNamedColor(accent)
    x, y = pad_pos(note); _add(b, x, y, PAD, PAD, bank)


def action_btn(name, action, note, bank, accent):
    b = VCButton(name); b.action = action; b.pad_style = "solid"
    b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, note
    b._bg_color.setNamedColor(accent)
    x, y = pad_pos(note); _add(b, x, y, PAD, PAD, bank)


def effect_action_btn(name, note, bank, accent, key, function_id):
    b = VCButton(name); b.action = ButtonAction.EFFECT_ACTION; b.effect_action_key = key
    b.function_id = function_id; b.pad_style = "solid"
    b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, note
    b._bg_color.setNamedColor(accent)
    x, y = pad_pos(note); _add(b, x, y, PAD, PAD, bank)


def select_group_btn(name, group, note, bank, accent="#2a4a6a"):
    b = VCButton(name); b.action = ButtonAction.SELECT_GROUP; b.group_name = group
    b.pad_style = "solid"
    b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, note
    b._bg_color.setNamedColor(accent)
    x, y = pad_pos(note); _add(b, x, y, PAD, PAD, bank)


def color_tile(name, note, bank, r, g, b, w=0, target=ColorTarget.PROGRAMMER,
               function_id=None, with_intensity=True):
    c = VCColor(name); c.color_r, c.color_g, c.color_b, c.color_w = r, g, b, w
    c.with_intensity = with_intensity; c.target = target; c.function_id = function_id
    c.midi_type, c.midi_ch, c.midi_data1 = "note_on", 0, note
    x, y = pad_pos(note); _add(c, x, y, PAD, PAD, bank)


def fader(caption, col, bank, mode, function_ids=None, programmer_attr="intensity",
          programmer_scope="all", programmer_group="", param_key="speed",
          midi_cc=-1, value=0, submaster_slot=None, function_id=None):
    s = VCSlider(caption); s.mode = mode; s.function_id = function_id
    s.function_ids = list(function_ids or [])
    if submaster_slot is not None:
        s.function_id = submaster_slot
    s.programmer_attr = programmer_attr; s.programmer_scope = programmer_scope
    s.programmer_group = programmer_group; s.param_key = param_key
    s.midi_cc, s.midi_ch = midi_cc, 0; s._value = value
    x = X0 + col * STEP + 2; _add(s, x, Y_FAD, 56, FAD_H, bank)


def label(text, x, y, ww, bank, hh=18):
    _add(VCLabel(text), x, y, ww, hh, bank)


# ── Universell ────────────────────────────────────────────────────────────────
for i, (nm, act, col) in enumerate([
        ("Clear", ButtonAction.CLEAR, "#4a3a10"), ("Stop All", ButtonAction.STOP_ALL, "#4a1010"),
        ("Blackout", ButtonAction.BLACKOUT, "#2a0000"), ("Tap", ButtonAction.TAP, "#103a3a")]):
    b = VCButton(nm); b.action = act; b.pad_style = "solid"
    b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, TRACK0 + i
    b._bg_color.setNamedColor(col)
    _add(b, X0 + i * 64, TY, 60, 26, BANK_ALL)
fader("Dimmer", 5, BANK_ALL, SliderMode.SUBMASTER, submaster_slot=0, midi_cc=53, value=255)
fader("Speed", 6, BANK_ALL, SliderMode.SPEED, midi_cc=54, value=64)
fader("Master", 8, BANK_ALL, SliderMode.GRANDMASTER, midi_cc=56, value=255)
label("MASTER-DEMO  —  alles, was die Show kann.  SCENE-Tasten rechts = Seite 1-5.  "
      "Track unten: Clear/Stop/Blackout/Tap.  F6 Dimmer | F7 Speed | F9 Master.",
      X0, 6, 1150, BANK_ALL)
for i, nm in enumerate(PAGE_NAMES):
    label(f"Scene {i + 1}: {nm}", RIGHT_X, Y0 + i * 26, 200, BANK_ALL, hh=22)


# ── SEITE 1 — FARBEN & GRUPPEN (F-24 / F-25) ────────────────────────────────
COLORS8 = [("Rot", 255, 0, 0, 0), ("Grün", 0, 255, 0, 0), ("Blau", 0, 0, 255, 0),
           ("Weiß", 255, 255, 255, 255), ("Amber", 255, 140, 0, 0), ("Cyan", 0, 255, 255, 0),
           ("Magenta", 255, 0, 255, 0), ("Warm", 255, 130, 40, 60)]
for s, (nm, r, g, b, w) in enumerate(COLORS8):
    color_tile(nm, slot_note(s), B_COLOR, r, g, b, w)
# Gruppe-auswählen-Pads (F-24)
select_group_btn("Gr: PARs", "PAR-Reihe", slot_note(8), B_COLOR)
select_group_btn("Gr: MHs", "Moving Heads", slot_note(9), B_COLOR)
select_group_btn("Gr: Alle", "Alle", slot_note(10), B_COLOR)
action_btn("Clear", ButtonAction.CLEAR, slot_note(11), B_COLOR, "#4a3a10")
# Gruppen-Dimmer-Fader (F-25)
fader("PAR-Dim", 0, B_COLOR, SliderMode.GROUP_DIMMER, programmer_group="PAR-Reihe", midi_cc=48, value=255)
fader("MH-Dim", 1, B_COLOR, SliderMode.GROUP_DIMMER, programmer_group="Moving Heads", midi_cc=49, value=255)
label("SEITE 1  FARBEN & GRUPPEN  -  oben Farben (Programmer).  Pads 'Gr:' wählen eine "
      "Gruppe in den Programmer (F-24).  F1/F2 = Gruppen-Dimmer PARs/MHs (F-25).",
      X0, 28, 1100, B_COLOR)


# ── SEITE 2 — EFFEKTE (alle Typen, exklusiv) ────────────────────────────────
for i, fn in enumerate(EFFECTS):
    accent = ("#7a5b00" if fn.name.startswith("Mtx") else
              "#1f3a6a" if fn.name.startswith("MH") else
              "#3a2150" if fn.id in COLOR_FX_IDS else "#1f4a28")
    func_btn(fn, slot_note(i), B_FX, accent, exclusive=True, clear_prog=(fn.id in COLOR_FX_IDS))
label("SEITE 2  EFFEKTE  -  exklusiv (nur einer läuft): Dimmer-Chaser/Carousels, "
      "Color-Chase, RGB-Matrix, Moving-Head-EFX inkl. Dreieck & Random.",
      X0, 28, 1100, B_FX)


# ── SEITE 3 — MATRIX BUILDER (#3/#5/#6) ─────────────────────────────────────
MB = matrix_builder.id
func_btn(matrix_builder, 0, B_MATRIX, "#7a5b00", clear_prog=True)
effect_action_btn("Form -", 1, B_MATRIX, "#5a4a00", "prev_algorithm", MB)
effect_action_btn("Form +", 2, B_MATRIX, "#7a6500", "next_algorithm", MB)
effect_action_btn("Richtung", 3, B_MATRIX, "#335533", "reverse_direction", MB)
effect_action_btn("Freeze", 4, B_MATRIX, "#553333", "toggle_freeze", MB)
effect_action_btn("Commit", 5, B_MATRIX, "#1d4d2d", "commit_live", MB)
_RC = [("Rot", 255, 0, 0), ("Grün", 0, 255, 0), ("Blau", 0, 0, 255), ("Weiß", 255, 255, 255)]
for s, (nm, r, g, b) in enumerate(_RC):
    color_tile(f"C1 {nm}", slot_note(8 + s), B_MATRIX, r, g, b, target=ColorTarget.EFFECT_C1, function_id=MB, with_intensity=False)
for s, (nm, r, g, b) in enumerate(_RC):
    color_tile(f"Seq {nm}", slot_note(16 + s), B_MATRIX, r, g, b, target=ColorTarget.EFFECT, function_id=MB, with_intensity=False)
fader("Speed", 0, B_MATRIX, SliderMode.EFFECT_SPEED, function_ids=[MB], midi_cc=48, value=64)
fader("Master", 1, B_MATRIX, SliderMode.EFFECT_INTENSITY, function_ids=[MB], midi_cc=49, value=255)
_add(VCColorList("Matrix-Farben"), RIGHT_X, Y0 + 5 * 26 + 8, 210, 92, B_MATRIX)
widgets[-1]["function_id"] = MB  # VCColorList an den Matrix-Builder binden
label("SEITE 3  MATRIX BUILDER  -  Start + 'Form -/+' blättert durch ALLE Algorithmen. "
      "Reihe 2 = color1, Reihe 3 = Sequence-Farbe.  Rechts: Live-Feedback.",
      X0, 28, 1100, B_MATRIX)


# ── SEITE 4 — CHASE BUILDER (#1) ────────────────────────────────────────────
func_btn(chase_builder, slot_note(0), B_CHASE, "#1f6a4a", clear_prog=True)
label("SEITE 4  CHASE BUILDER  -  Start-Pad für den Chase-Builder-Effekt.",
      X0, 28, 1100, B_CHASE)


# ── SEITE 5 — MOVING HEADS (#7 relativ + #8 Feld) ───────────────────────────
REL, AREA = efx_rel.id, efx_area.id
xy_pos = VCXYPad("MH zielen"); xy_pos.mode = "position"; xy_pos._fixture_ids = list(mh_fids)
_add(xy_pos, X0, Y0, 230, 230, B_MH)
effect_action_btn("Relativ", slot_note(4), B_MH, "#7a6500", "toggle_relative", REL)
effect_action_btn("Neustart", slot_note(5), B_MH, "#5a3010", "restart", REL)
func_btn(efx_rel, slot_note(6), B_MH, "#1f3a6a")
func_btn(efx_area, slot_note(7), B_MH, "#1f3a6a")
xy_area = VCXYPad("Feld → Kreis"); xy_area.mode = "area"; xy_area.efx_function_id = AREA
_add(xy_area, RIGHT_X, Y0, 200, 200, B_MH)
label("SEITE 5  MOVING HEADS  -  LINKS zielen (XY) + 'Relativ' an + 'MH Acht relativ' "
      "starten → Acht um die gezielte Position (#7).",
      X0, 28, 1100, B_MH)
label("RECHTS 'Feld' aufziehen → 'MH Kreis Feld' fährt im markierten Bereich (#8). "
      "Nach neuem Zielen 'Neustart'.", X0, 48, 1100, B_MH)

state._vc_layout = {"widgets": widgets}

# ── Executor-Seiten benennen ────────────────────────────────────────────────
pe = getattr(state, "playback_engine", None)
if pe is not None:
    try:
        for idx, nm in enumerate(PAGE_NAMES):
            if 0 <= idx < len(pe.page_names):
                pe.page_names[idx] = nm
        pe.set_page(0)
    except Exception as e:
        print(f"[build] page name error: {e}")

# ── 3) Speichern + Verifikation ─────────────────────────────────────────────
state.programmer = {}
state.show_name = "Master Demo"
save_show(OUT)
print(f"Gespeichert: {OUT}")
ok, msg = load_show(OUT)
print("Load:", ok, msg)
assert ok, f"Show laedt nicht: {msg}"
assert len(state.get_patched_fixtures()) == 6

from collections import Counter
vc = state._vc_layout.get("widgets", [])
banks = Counter(w.get("bank") for w in vc)
assert set(banks) == {0, 1, 2, 3, 4, -1}, f"Banks: {sorted(banks)}"
types = Counter(w["type"] for w in vc)

# Neue VC-Fenster-Widgets vorhanden?
assert types.get("VCColorList", 0) == 1, "VCColorList fehlt"
assert types.get("VCXYPad", 0) == 2, f"VCXYPad: {types.get('VCXYPad', 0)}"
# F-24 SELECT_GROUP-Pads
sel = [w for w in vc if w.get("action") == "SelectGroup"]
assert len(sel) == 3 and {w["group_name"] for w in sel} == {"PAR-Reihe", "Moving Heads", "Alle"}, sel
# F-25 GROUP_DIMMER-Fader
gd = [w for w in vc if w.get("mode") == "GroupDimmer"]
assert len(gd) == 2, f"GroupDimmer-Fader: {len(gd)}"
# Effekte exklusiv inkl. Dreieck/Random
excl = [w for w in vc if w.get("bank") == B_FX and w.get("exclusive")]
assert len(excl) == len(EFFECTS), f"Effekte: {len(excl)}"
names = {f.name for f in EFFECTS}
assert {"MH Dreieck", "MH Random"} <= names
maxy = max((w.get("y", 0) + w.get("h", 0)) for w in vc)
assert maxy < 820, f"zu hoch: {maxy}"

print(f"Funktionen: {len(fm.all())}  VC-Widgets: {len(vc)}  Typen={dict(types)}")
print(f"Banks: {dict(sorted(banks.items()))}  Max-Y={maxy}")
print(f"  SELECT_GROUP={len(sel)}  GROUP_DIMMER={len(gd)}  Effekte(exkl)={len(excl)}")
print("  [OK] 5 Banks · APC mini · 4 PAR + 2 MH · VCColorList/VCXYPad · F-24/F-25")
print("FERTIG")
