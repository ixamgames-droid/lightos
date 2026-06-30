"""NEUE DEMO 2026 — Quadranten-Layout + echtes PLAYBACK, alles auf einer Show.

Davids Setup: Akai APC mini (mk2) + 4× PAR (ZQ01424, 8ch RGBW) + 2× Moving Head
(ZQ02001, 11ch).  Nutzt ALLE neuen Features und verteilt sie auf 5 Banks
(APC-SCENE-Tasten = Bank/Seite, gekoppelt an die Playback-Seite!):

  Bank 1  QUADRANTEN     Das „Vier-Quadranten-Ding":
                         ┌ FARBEN 4x4 (Programmer) ┬ EFFEKTE 4x4 (exklusiv) ┐
                         └ ATTRIBUTE 4x4 (aktiver  ┴ SONSTIGES 4x4 (Clear/   ┘
                           Effekt: Form/Farbe/…)     Stop/Blackout/BPM/Looks)
                         Fader unten passen sich dem AKTIVEN Effekt an.
  Bank 2  MATRIX-LOOKS   Alle 16 RGB-Matrix-Algorithmen als Einzel-Pads.
  Bank 3  BUILDER        Live-Programming: Chase-Builder-Fenster + Matrix-
                         Builder (Form ±/Commit) + Farb-Sequenz-Liste.
  Bank 4  MOVING HEADS   XY-Pad zielen, alle 8 EFX-Formen (Kreis/Acht/Dreieck/
                         Zufall/…), relative Bewegung, „Feld → Kreis".
  Bank 5  PLAYBACK       3 gespeicherte Playbacks (Cuelisten) auf Executoren:
                         „Show-Timeline" (auto-Follow), „Farb-Stimmungen"
                         (Loop), „Bewegung" (Bounce).  Cue-Listen-Fenster mit
                         GO/BACK/STOP, GO-Pads, Dimmer-Fader, Speed-Dial.
                         Dieselben Playbacks erscheinen im Playback-Tab (Seite 5).

Universell (alle Banks): Track Clear/Stop/Blackout/Tap; Fader Dimmer/Speed/Master.

Aufruf:  venv/Scripts/python.exe tools/build_neue_demo_show.py
Erzeugt: shows/Neue_Demo_2026.lshow
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
from src.core.app_state import get_state, get_channels_for_patched, open_value_for
from src.core.database.fixture_db import engine as fdb_engine
from src.core.database.models import PatchedFixture, FixtureProfile, FixtureGroup
from src.core.engine.function_manager import get_function_manager
from src.core.engine.function import RunOrder, Direction
from src.core.engine.chaser import ChaserStep
from src.core.engine.rgb_matrix import RgbAlgorithm, ColorSequence
from src.core.engine.carousel import CarouselPattern
from src.core.engine.efx import EfxFixture, EfxAlgorithm
from src.core.engine.cue import Cue
from src.core.show.show_file import reset_show, save_show, load_show
from src.ui.virtualconsole.vc_button import VCButton, ButtonAction
from src.ui.virtualconsole.vc_color import VCColor, ColorTarget
from src.ui.virtualconsole.vc_slider import VCSlider, SliderMode
from src.ui.virtualconsole.vc_label import VCLabel
from src.ui.virtualconsole.vc_color_list import VCColorList
from src.ui.virtualconsole.vc_xypad import VCXYPad
from src.ui.virtualconsole.vc_cuelist import VCCueList
from src.ui.virtualconsole.vc_speedial import VCSpeedDial, SpeedTarget

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(_ROOT, "shows", "Neue_Demo_2026.lshow")
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
fx_of = {f.fid: f for f in fixtures}
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

SHUT_OPEN = open_value_for(fx_of[mh_left], "shutter")   # offener Shutter (ZQ02001 = 4)


# ════════════════════════════════════════════════════════════════════════════
#  1) FUNKTIONS-BIBLIOTHEK (wird über mehrere Banks referenziert)
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
    c = fm.new_chaser(name)
    c.run_order, c.direction, c.speed = RunOrder.Loop, Direction.Forward, speed
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


# Dimmer-/Helligkeits-Effekte (mit Farbe kombinierbar -> kein clear_programmer)
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

# ALLE 16 RGB-Matrix-Algorithmen (Bank 2 — je ein Pad).  clear_programmer, da
# sie ihre Farbe selbst mitbringen.
MTX_SPECS = [
    ("Mtx Regenbogen", RgbAlgorithm.RAINBOW, 1.5), ("Mtx Feuer", RgbAlgorithm.FIRE, 2.0),
    ("Mtx Plasma", RgbAlgorithm.SINEPLASMA, 1.2), ("Mtx Regen", RgbAlgorithm.RAIN, 1.6),
    ("Mtx Pinwheel", RgbAlgorithm.PINWHEEL, 1.4), ("Mtx Atem", RgbAlgorithm.BREATHE, 1.0),
    ("Mtx Spirale", RgbAlgorithm.SPIRAL, 1.5), ("Mtx Radar", RgbAlgorithm.RADAR, 1.5),
    ("Mtx Wipe", RgbAlgorithm.WIPE, 2.0), ("Mtx Welle", RgbAlgorithm.WAVE, 1.8),
    ("Mtx Gradient", RgbAlgorithm.GRADIENT, 1.2), ("Mtx Color-Fade", RgbAlgorithm.COLORFADE, 1.0),
    ("Mtx Chase", RgbAlgorithm.CHASE, 3.0), ("Mtx Fill", RgbAlgorithm.FILL, 2.0),
    ("Mtx Strobe", RgbAlgorithm.STROBE, 6.0), ("Mtx Zufall", RgbAlgorithm.RANDOM, 2.0),
]
mtx = [matrix(nm, algo, speed=sp) for nm, algo, sp in MTX_SPECS]

# ALLE EFX-Formen für Moving Heads (Bank 4).
EFX_SPECS = [
    ("MH Kreis", EfxAlgorithm.CIRCLE), ("MH Acht", EfxAlgorithm.EIGHT),
    ("MH Dreieck", EfxAlgorithm.TRIANGLE), ("MH Zufall", EfxAlgorithm.RANDOM),
    ("MH Linie", EfxAlgorithm.LINE), ("MH Raute", EfxAlgorithm.DIAMOND),
    ("MH Quadrat", EfxAlgorithm.SQUARE), ("MH Lissajous", EfxAlgorithm.LISSAJOUS),
]
efx = [mh_efx(nm, algo) for nm, algo in EFX_SPECS]
efx_rel = mh_efx("MH Acht relativ", EfxAlgorithm.EIGHT, relative=True)
efx_area = mh_efx("MH Kreis Feld", EfxAlgorithm.CIRCLE)

# Builder-Funktionen (Bank 3).
matrix_builder = matrix("Matrix-Builder", RgbAlgorithm.CHASE, speed=3.0,
                        params={"axis": "H", "movement": "normal"})
matrix_builder.colors = ColorSequence([(255, 0, 0), (0, 0, 255), (0, 255, 0)])
chase_builder = matrix("Chase-Builder", RgbAlgorithm.COLORFADE, speed=2.0, params={"hold": 0.2})
chase_builder.colors = ColorSequence([(255, 0, 0), (0, 255, 0), (0, 0, 255)])

# Schnell-Looks (Bank 1, Sonstiges-Quadrant).
look_warm = par_look("Warmweiß", r=255, g=130, b=40, w=60)
look_white = par_look("Weiß", r=255, g=255, b=255, w=255)

# Effekt-Mix für den Quadranten (Bank 1, 16 Slots) — referenziert vorhandene Fkt.
by_name = {f.name: f for f in fm.all()}
QUAD_FX = [dim_run, dim_ping, dim_pairs, dim_strobe,
           dim_build, dim_pulse, dim_wave, ch_color,
           by_name["Mtx Regenbogen"], by_name["Mtx Feuer"],
           by_name["Mtx Plasma"], by_name["Mtx Atem"],
           by_name["MH Acht"], by_name["MH Kreis"],
           by_name["MH Dreieck"], by_name["MH Zufall"]]
COLOR_FX_IDS = {ch_color.id} | {m.id for m in mtx}


# ════════════════════════════════════════════════════════════════════════════
#  2) PLAYBACKS — echte Cuelisten auf Executoren (Bank 5 + Playback-Tab)
# ════════════════════════════════════════════════════════════════════════════
def par_vals(r, g, b, w=0, inten=255):
    out = {}
    for fid in par_fids:
        cm = chan_of[fid]; v = {}
        if "intensity" in cm:
            v["intensity"] = inten
        for a, val in (("color_r", r), ("color_g", g), ("color_b", b), ("color_w", w)):
            if a in cm:
                v[a] = val
        out[fid] = v
    return out


def mh_vals(pan, tilt, inten=255):
    out = {}
    for fid in mh_fids:
        cm = chan_of[fid]; v = {}
        if "pan" in cm:
            v["pan"] = pan
        if "tilt" in cm:
            v["tilt"] = tilt
        if "intensity" in cm:
            v["intensity"] = inten
        if "shutter" in cm:
            v["shutter"] = SHUT_OPEN
        out[fid] = v
    return out


def merge(*dicts):
    res: dict[int, dict] = {}
    for d in dicts:
        for fid, v in d.items():
            res.setdefault(fid, {}).update(v)
    return res


# Playback 1 — Show-Timeline: einmal GO drücken, läuft per Auto-Follow durch.
pb_timeline = state.new_cue_stack("Show-Timeline")
pb_timeline.mode = "single"
for num, lbl, vals, fin, fol in [
    (1.0, "Intro",     merge(par_vals(255, 120, 30, 40, inten=90),  mh_vals(128, 90, 120)),  3.0, 4.0),
    (2.0, "Aufbau",    merge(par_vals(0, 40, 255, 0, inten=200),    mh_vals(80, 60, 200)),   2.5, 4.0),
    (3.0, "Farbe",     merge(par_vals(255, 0, 180, 0, inten=255),   mh_vals(180, 150, 255)), 2.0, 3.5),
    (4.0, "Hoehepunkt", merge(par_vals(255, 255, 255, 255, inten=255), mh_vals(40, 200, 255)), 1.0, 3.0),
    (5.0, "Ausklang",  merge(par_vals(255, 120, 30, 40, inten=60),  mh_vals(128, 128, 0)),   4.0, None),
]:
    pb_timeline.add_cue(Cue(number=num, label=lbl, fade_in=fin, follow=fol, values=vals))

# Playback 2 — Farb-Stimmungen: per GO schrittweise, Loop wickelt 5→1.
pb_moods = state.new_cue_stack("Farb-Stimmungen")
pb_moods.mode = "loop"
for num, lbl, (r, g, b) in [
    (1.0, "Rot", (255, 0, 0)), (2.0, "Bernstein", (255, 140, 0)),
    (3.0, "Magenta", (255, 0, 200)), (4.0, "Cyan", (0, 255, 200)),
    (5.0, "Blau", (0, 40, 255)),
]:
    pb_moods.add_cue(Cue(number=num, label=lbl, fade_in=2.5, values=par_vals(r, g, b)))

# Playback 3 — Bewegung: MH-Sweep, Bounce + Auto-Follow (fährt hin und zurück).
pb_move = state.new_cue_stack("Bewegung")
pb_move.mode = "bounce"
_blue = par_vals(0, 30, 120, inten=120)
for num, lbl, (pan, tilt) in [
    (1.0, "Mitte", (128, 128)), (2.0, "Links unten", (60, 200)),
    (3.0, "Rechts oben", (200, 60)), (4.0, "Weit", (220, 220)),
]:
    pb_move.add_cue(Cue(number=num, label=lbl, fade_in=1.5, follow=1.5,
                        values=merge(_blue, mh_vals(pan, tilt))))

PLAYBACKS = [pb_timeline, pb_moods, pb_move]
PB_PAGE = 4   # Bank/Seite 5 (0-basiert) — Bank-Index = Playback-Seite (gekoppelt!)
pe = state.playback_engine
for slot, pb in enumerate(PLAYBACKS, start=1):
    ex = pe.get_executor(slot, page=PB_PAGE)
    ex.stack = pb
    ex.label = pb.name
    ex.fader_function = "volume"   # VC-Playback-Fader dimmt das Playback


# ════════════════════════════════════════════════════════════════════════════
#  3) VIRTUAL CONSOLE
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
B_QUAD, B_MTX, B_BUILD, B_MH, B_PLAY = range(5)
PAGE_NAMES = ["Quadranten", "Matrix-Looks", "Builder", "Moving Heads", "Playback"]


def pad_pos(note):
    row, col = note // 8, note % 8
    return X0 + col * STEP, Y0 + (7 - row) * STEP


def note_rc(r, c):
    """APC-Note für visuelle (Zeile 0=oben, Spalte 0=links)."""
    return (7 - r) * 8 + c


def slot_note(s):
    return note_rc(s // 8, s % 8)


def qnote(quadrant, qr, qc):
    """APC-Note für (Quadrant TL/TR/BL/BR, Zeile 0..3, Spalte 0..3)."""
    r = qr + (4 if quadrant in ("BL", "BR") else 0)
    c = qc + (4 if quadrant in ("TR", "BR") else 0)
    return note_rc(r, c)


def _add(w, x, y, ww, hh, bank):
    w.bank = bank; w.setGeometry(x, y, ww, hh); widgets.append(w.to_dict())


def func_btn(fn, note, bank, accent, exclusive=False, clear_prog=False, style="pulse"):
    b = VCButton(fn.name)
    b.action = ButtonAction.FUNCTION_TOGGLE; b.function_id = fn.id; b.pad_style = style
    b.exclusive = exclusive; b.clear_programmer = clear_prog
    b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, note
    b._bg_color.setNamedColor(accent)
    x, y = pad_pos(note); _add(b, x, y, PAD, PAD, bank)


def func_flash(fn, note, bank, accent):
    b = VCButton(fn.name); b.action = ButtonAction.FUNCTION_FLASH
    b.function_id = fn.id; b.pad_style = "solid"
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


def exec_go_btn(name, slot, note, bank, accent="#0d4f8b"):
    """Pad, das ein Playback startet/weiterschaltet (Executor GO)."""
    b = VCButton(name); b.action = ButtonAction.TOGGLE; b.function_id = slot
    b.pad_style = "solid"
    b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, note
    b._bg_color.setNamedColor(accent)
    x, y = pad_pos(note); _add(b, x, y, PAD, PAD, bank)


def exec_flash_btn(name, slot, note, bank, accent="#3a2150"):
    b = VCButton(name); b.action = ButtonAction.FLASH; b.function_id = slot
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


def pb_fader(caption, col, bank, slot, midi_cc, value=255):
    s = VCSlider(caption); s.mode = SliderMode.PLAYBACK; s.function_id = slot
    s.midi_cc, s.midi_ch = midi_cc, 0; s._value = value
    x = X0 + col * STEP + 2; _add(s, x, Y_FAD, 56, FAD_H, bank)


def label(text, x, y, ww, bank, hh=18):
    _add(VCLabel(text), x, y, ww, hh, bank)


# ── Universell (BANK_ALL) — Track-Tasten + Master-Fader + Kopf/Scene-Labels ──
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
label("NEUE DEMO 2026  —  4 PAR + 2 MH + APC mini.  Track unten: Clear/Stop/Blackout/Tap.  "
      "F6 Dimmer | F7 Speed | F9 Master.", X0, 6, 1150, BANK_ALL)
label("SCENE-Tasten = Bank 1-5 (= Playback-Seite):  1 Quadranten · 2 Matrix-Looks · 3 Builder · "
      "4 Moving Heads · 5 Playback", X0, Y_FAD + FAD_H + 6, 1000, BANK_ALL)


# ── BANK 1 — QUADRANTEN ──────────────────────────────────────────────────────
COLORS16 = [
    ("Rot", 255, 0, 0, 0), ("Orange", 255, 90, 0, 0), ("Amber", 255, 160, 0, 0), ("Gelb", 255, 220, 0, 0),
    ("Limette", 160, 255, 0, 0), ("Grün", 0, 255, 0, 0), ("Türkis", 0, 230, 150, 0), ("Cyan", 0, 255, 255, 0),
    ("Hellblau", 0, 140, 255, 0), ("Blau", 0, 0, 255, 0), ("Violett", 140, 0, 255, 0), ("Magenta", 255, 0, 255, 0),
    ("Pink", 255, 0, 120, 0), ("Warmweiß", 255, 130, 40, 60), ("Weiß", 255, 255, 255, 255), ("Aus", 0, 0, 0, 0),
]
for i, (nm, r, g, b, w) in enumerate(COLORS16):
    color_tile(nm, qnote("TL", i // 4, i % 4), B_QUAD, r, g, b, w)
for i, fn in enumerate(QUAD_FX):
    accent = ("#7a5b00" if fn.name.startswith("Mtx") else
              "#1f3a6a" if fn.name.startswith("MH") else
              "#3a2150" if fn.id in COLOR_FX_IDS else "#1f4a28")
    func_btn(fn, qnote("TR", i // 4, i % 4), B_QUAD, accent,
             exclusive=True, clear_prog=(fn.id in COLOR_FX_IDS))
ATTR = [
    ("Form -", "prev_algorithm", "#5a4a00"), ("Form +", "next_algorithm", "#7a6500"),
    ("Farbe -", "prev_color", "#334455"), ("Farbe +", "next_color", "#334455"),
    ("Richtung", "reverse_direction", "#335533"), ("Bounce", "toggle_bounce", "#335533"),
    ("Freeze", "toggle_freeze", "#553333"), ("Neustart", "restart", "#553010"),
    ("Spiegeln", "toggle_mirror", "#334455"), ("Relativ", "toggle_relative", "#335566"),
    ("+ Farbe", "add_color", "#224433"), ("Farbe an/aus", "toggle_color", "#224433"),
    ("Reset Live", "clear_live_override", "#553010"), ("Commit", "commit_live", "#1d4d2d"),
    ("Loop", "toggle_loop", "#334455"), ("Tap", "tap", "#0a3a3a"),
]
for i, (nm, key, accent) in enumerate(ATTR):
    effect_action_btn(nm, qnote("BL", i // 4, i % 4), B_QUAD, accent, key, function_id=None)
action_btn("Clear", ButtonAction.CLEAR, qnote("BR", 0, 0), B_QUAD, "#4a3a10")
action_btn("Stop All", ButtonAction.STOP_ALL, qnote("BR", 0, 1), B_QUAD, "#4a1010")
action_btn("Blackout", ButtonAction.BLACKOUT, qnote("BR", 0, 2), B_QUAD, "#2a0000")
action_btn("Tap", ButtonAction.TAP, qnote("BR", 0, 3), B_QUAD, "#103a3a")
action_btn("Musik-BPM", ButtonAction.AUDIO_BPM, qnote("BR", 1, 0), B_QUAD, "#103a4a")
func_flash(dim_strobe, qnote("BR", 1, 1), B_QUAD, "#551111")
func_flash(look_white, qnote("BR", 1, 2), B_QUAD, "#555555")
func_flash(look_warm, qnote("BR", 1, 3), B_QUAD, "#553010")
for i, sc in enumerate([lk[0], lk[1], lk[2], lk[3], lk[4], lk[5], look_warm, look_white]):
    func_btn(sc, qnote("BR", 2 + i // 4, i % 4), B_QUAD, "#222222", exclusive=False, style="solid")
# Adaptive Fader (wirken auf den AKTIVEN Effekt) + Gruppen-Dimmer.
fader("FX-Speed", 0, B_QUAD, SliderMode.EFFECT_SPEED, midi_cc=48, value=64)
fader("FX-Master", 1, B_QUAD, SliderMode.EFFECT_INTENSITY, midi_cc=49, value=255)
fader("FX-Param", 2, B_QUAD, SliderMode.EFFECT_PARAM, param_key="white_amount", midi_cc=50, value=0)
fader("PAR-Dim", 3, B_QUAD, SliderMode.GROUP_DIMMER, programmer_group="PAR-Reihe", midi_cc=51, value=255)
fader("MH-Dim", 4, B_QUAD, SliderMode.GROUP_DIMMER, programmer_group="Moving Heads", midi_cc=52, value=255)
label("BANK 1  QUADRANTEN  —  oben-links FARBEN (Programmer) · oben-rechts EFFEKTE (exklusiv) · "
      "unten-links ATTRIBUTE des aktiven Effekts · unten-rechts SONSTIGES/Looks.", X0, 28, 1100, B_QUAD)
label("◄ FARBEN", X0, 50, 120, B_QUAD)
label("EFFEKTE ►", X0 + STEP * 5, 50, 160, B_QUAD)
label("◄ ATTRIBUTE (aktiver Effekt)", X0, Y0 + 4 * STEP - 18, 250, B_QUAD)
label("SONSTIGES ►", X0 + STEP * 5, Y0 + 4 * STEP - 18, 160, B_QUAD)


# ── BANK 2 — MATRIX-LOOKS (alle 16 Algorithmen) ─────────────────────────────
for i, m in enumerate(mtx):
    func_btn(m, slot_note(i), B_MTX, "#7a5b00", exclusive=True, clear_prog=True)
fader("FX-Speed", 0, B_MTX, SliderMode.EFFECT_SPEED, midi_cc=48, value=64)
fader("FX-Master", 1, B_MTX, SliderMode.EFFECT_INTENSITY, midi_cc=49, value=255)
fader("PAR-Dim", 3, B_MTX, SliderMode.GROUP_DIMMER, programmer_group="PAR-Reihe", midi_cc=51, value=255)
label("BANK 2  MATRIX-LOOKS  —  alle 16 RGB-Matrix-Algorithmen auf den 4 PARs, exklusiv. "
      "FX-Speed/FX-Master wirken auf den laufenden Look.", X0, 28, 1100, B_MTX)


# ── BANK 3 — BUILDER (Live-Programming) ─────────────────────────────────────
MB = matrix_builder.id
func_btn(matrix_builder, note_rc(0, 5), B_BUILD, "#7a5b00", clear_prog=True)
effect_action_btn("Form -", note_rc(0, 6), B_BUILD, "#5a4a00", "prev_algorithm", MB)
effect_action_btn("Form +", note_rc(0, 7), B_BUILD, "#7a6500", "next_algorithm", MB)
effect_action_btn("Richtung", note_rc(1, 5), B_BUILD, "#335533", "reverse_direction", MB)
effect_action_btn("Freeze", note_rc(1, 6), B_BUILD, "#553333", "toggle_freeze", MB)
effect_action_btn("Commit", note_rc(1, 7), B_BUILD, "#1d4d2d", "commit_live", MB)
_RC = [("Rot", 255, 0, 0), ("Grün", 0, 255, 0), ("Blau", 0, 0, 255)]
for s, (nm, r, g, b) in enumerate(_RC):
    color_tile(f"C1 {nm}", note_rc(2, 5 + s), B_BUILD, r, g, b,
               target=ColorTarget.EFFECT_C1, function_id=MB, with_intensity=False)
for s, (nm, r, g, b) in enumerate(_RC):
    color_tile(f"Seq {nm}", note_rc(3, 5 + s), B_BUILD, r, g, b,
               target=ColorTarget.EFFECT, function_id=MB, with_intensity=False)
clw = VCColorList("Matrix-Farben")
_add(clw, RIGHT_X, Y0, 210, 100, B_BUILD)
widgets[-1]["function_id"] = MB
fader("MB-Speed", 0, B_BUILD, SliderMode.EFFECT_SPEED, function_ids=[MB], midi_cc=48, value=64)
fader("MB-Master", 1, B_BUILD, SliderMode.EFFECT_INTENSITY, function_ids=[MB], midi_cc=49, value=255)
label("BANK 3  BUILDER  —  Matrix-Builder: Start + 'Form ±' blättert ALLE Algorithmen, C1/Seq-Farben live, Commit.",
      X0, 28, 1100, B_BUILD)


# ── BANK 4 — MOVING HEADS ───────────────────────────────────────────────────
xy_pos = VCXYPad("MH zielen"); xy_pos.mode = "position"; xy_pos._fixture_ids = list(mh_fids)
xy_pos.bits16 = True
_add(xy_pos, X0, Y0, 224, 224, B_MH)
for i, e in enumerate(efx):
    func_btn(e, note_rc(0, 4 + i % 4) if i < 4 else note_rc(1, 4 + (i - 4)), B_MH, "#1f3a6a", exclusive=True)
effect_action_btn("Relativ", note_rc(2, 4), B_MH, "#7a6500", "toggle_relative", efx_rel.id)
effect_action_btn("Neustart", note_rc(2, 5), B_MH, "#553010", "restart", None)
effect_action_btn("Spiegeln", note_rc(2, 6), B_MH, "#334455", "toggle_mirror", None)
func_btn(efx_rel, note_rc(2, 7), B_MH, "#1f6a4a", exclusive=False)
func_btn(efx_area, note_rc(3, 4), B_MH, "#1f6a4a", exclusive=False)
xy_area = VCXYPad("Feld → Kreis"); xy_area.mode = "area"; xy_area.efx_function_id = efx_area.id
_add(xy_area, RIGHT_X, Y0, 196, 196, B_MH)
fader("EFX-Speed", 0, B_MH, SliderMode.EFFECT_SPEED, midi_cc=48, value=64)
fader("EFX-Größe", 1, B_MH, SliderMode.EFFECT_PARAM, param_key="size", midi_cc=49, value=110)
fader("MH-Dim", 3, B_MH, SliderMode.GROUP_DIMMER, programmer_group="Moving Heads", midi_cc=51, value=255)
label("BANK 4  MOVING HEADS  —  LINKS zielen (16-bit XY).  Rechts oben: 8 EFX-Formen (Kreis/Acht/"
      "Dreieck/Zufall/Linie/Raute/Quadrat/Lissajous), 'Relativ'/'Spiegeln'/'Neustart'.",
      X0, 28, 1100, B_MH)
label("RECHTS 'Feld' aufziehen → 'MH Kreis Feld' fährt im markierten Bereich.", X0, 48, 1100, B_MH)


# ── BANK 5 — PLAYBACK ───────────────────────────────────────────────────────
# Drei Cue-Listen-Fenster nebeneinander (obere Bildschirmhälfte).
for i, pb in enumerate(PLAYBACKS):
    cl = VCCueList(pb.name); cl.stack_slot = i
    _add(cl, X0 + i * 250, Y0, 240, 196, B_PLAY)
# GO-/Flash-Pads in den unteren Reihen des 8x8-Grids (Visual-Reihe 4 + 5).
PB_ACCENT = ["#0d4f8b", "#3a2150", "#1f4a28"]
for i, pb in enumerate(PLAYBACKS):
    exec_go_btn(f"GO {pb.name[:6]}", i, note_rc(4, i), B_PLAY, PB_ACCENT[i])
    exec_flash_btn(f"Flash {i+1}", i, note_rc(5, i), B_PLAY, "#333355")
# Speed-Dial (Rate) für die Timeline + Dimmer-Fader je Playback.
sd = VCSpeedDial("Timeline-Rate"); sd.target_mode = SpeedTarget.EXECUTOR
sd.function_id = 0; sd.multiplier_mode = True
_add(sd, X0 + 3 * 250 + 20, Y0, 150, 110, B_PLAY)
for i, pb in enumerate(PLAYBACKS):
    pb_fader(f"Dim {i+1}", i, B_PLAY, slot=i, midi_cc=48 + i, value=255)
label("BANK 5  PLAYBACK  —  drei gespeicherte Playbacks (Cuelisten).  Im Fenster GO►/◄◄/■, "
      "Pads Reihe 5 = GO, Reihe 6 = Flash, Fader F1-F3 = Dimmer je Playback.", X0, 28, 1100, B_PLAY)
label("Auch im PLAYBACK-TAB auf Seite 5 spielbar (gleiche Executoren).  'Show-Timeline': "
      "einmal GO drücken — läuft per Auto-Follow durch.", X0, 48, 1100, B_PLAY)


state._vc_layout = {"widgets": widgets}

# ── Executor-Seiten benennen ────────────────────────────────────────────────
try:
    for idx, nm in enumerate(PAGE_NAMES):
        if 0 <= idx < len(pe.page_names):
            pe.page_names[idx] = nm
    pe.set_page(0)
except Exception as e:
    print(f"[build] page name error: {e}")


# ════════════════════════════════════════════════════════════════════════════
#  4) Speichern + Verifikation
# ════════════════════════════════════════════════════════════════════════════
state.programmer = {}
state.show_name = "Neue Demo 2026"
save_show(OUT)
print(f"Gespeichert: {OUT}")
ok, msg = load_show(OUT)
print("Load:", ok, msg)
assert ok, f"Show laedt nicht: {msg}"
state = get_state()
assert len(state.get_patched_fixtures()) == 6

from collections import Counter
vc = state._vc_layout.get("widgets", [])
banks = Counter(w.get("bank") for w in vc)
assert set(banks) == {0, 1, 2, 3, 4, -1}, f"Banks: {sorted(banks)}"
types = Counter(w["type"] for w in vc)

# Playbacks erhalten?
assert len(state.cue_stacks) == 3, f"Cue-Stacks: {len(state.cue_stacks)}"
names = {s.name for s in state.cue_stacks}
assert names == {"Show-Timeline", "Farb-Stimmungen", "Bewegung"}, names
by = {s.name: s for s in state.cue_stacks}
assert len(by["Show-Timeline"].cues) == 5 and by["Show-Timeline"].mode == "single"
assert len(by["Farb-Stimmungen"].cues) == 5 and by["Farb-Stimmungen"].mode == "loop"
assert len(by["Bewegung"].cues) == 4 and by["Bewegung"].mode == "bounce"
# Executor-Bindung auf der Playback-Seite wiederhergestellt?
pe2 = state.playback_engine
bound = [pe2.get_executor(s, page=PB_PAGE).stack for s in (1, 2, 3)]
assert all(b is not None for b in bound), f"Executoren ungebunden: {bound}"
assert {b.name for b in bound} == names, [b.name for b in bound]

# VC-Fenster-Widgets vorhanden?
assert types.get("VCCueList", 0) == 3, f"VCCueList: {types.get('VCCueList')}"
assert types.get("VCXYPad", 0) == 2, f"VCXYPad: {types.get('VCXYPad')}"
assert types.get("VCColorList", 0) == 1, "VCColorList fehlt"
assert types.get("VCSpeedDial", 0) == 1, "VCSpeedDial fehlt"
# Quadranten-Bank: 16 Programmer-Farben + 16 exklusive Effekte + 16 Attribute (aktiv)
prog_colors = [w for w in vc if w.get("bank") == B_QUAD and w.get("type") == "VCColor"
               and w.get("target") == ColorTarget.PROGRAMMER]
assert len(prog_colors) == 16, f"Quadrant-Farben: {len(prog_colors)}"
attr_active = [w for w in vc if w.get("bank") == B_QUAD and w.get("action") == "EffectAction"
               and w.get("function_id") is None]
assert len(attr_active) == 16, f"Attribute (aktiv): {len(attr_active)}"
# Matrix-Bank: 16 exklusive Looks
mtx_pads = [w for w in vc if w.get("bank") == B_MTX and w.get("action") == "FunctionToggle"
            and w.get("exclusive")]
assert len(mtx_pads) == 16, f"Matrix-Looks: {len(mtx_pads)}"
# Playback-GO-Pads (TOGGLE = Executor GO)
go_pads = [w for w in vc if w.get("bank") == B_PLAY and w.get("action") == "Toggle"]
assert len(go_pads) == 3, f"GO-Pads: {len(go_pads)}"
maxy = max((w.get("y", 0) + w.get("h", 0)) for w in vc)
assert maxy < 820, f"zu hoch: {maxy}"

# Keine Überlappung interaktiver Widgets je Bank (Bank-Layer + BANK_ALL).
_INTER = {"VCButton", "VCSlider", "VCColor", "VCXYPad", "VCCueList",
          "VCColorList", "VCSpeedDial"}


def _rect(w):
    return (w.get("x", 0), w.get("y", 0), w.get("x", 0) + w.get("w", 0), w.get("y", 0) + w.get("h", 0))


def _overlap(a, b):
    ax0, ay0, ax1, ay1 = _rect(a); bx0, by0, bx1, by1 = _rect(b)
    return not (ax1 <= bx0 or bx1 <= ax0 or ay1 <= by0 or by1 <= ay0)


for bk in (0, 1, 2, 3, 4):
    layer = [w for w in vc if w.get("bank") in (bk, -1) and w["type"] in _INTER]
    for a in range(len(layer)):
        for b in range(a + 1, len(layer)):
            assert not _overlap(layer[a], layer[b]), (
                f"Overlap Bank {bk}: {layer[a]['type']}@{_rect(layer[a])} "
                f"vs {layer[b]['type']}@{_rect(layer[b])}")

print(f"Funktionen: {len(get_function_manager().all())}  VC-Widgets: {len(vc)}  Typen={dict(types)}")
print(f"Banks: {dict(sorted(banks.items()))}  Max-Y={maxy}")
print(f"  Playbacks={len(state.cue_stacks)} {sorted(names)}  Quadrant-Farben={len(prog_colors)}  "
      f"Attribute={len(attr_active)}  Matrix-Looks={len(mtx_pads)}  GO-Pads={len(go_pads)}")
print("  [OK] 5 Banks · APC mini · 4 PAR + 2 MH · Quadranten + Playback (Cuelisten/Executoren)")
print("FERTIG")
