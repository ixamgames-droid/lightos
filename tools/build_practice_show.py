"""PRAXIS-DEMO-SHOW (P13): Praxisvalidierung aller neuen Funktionen der
Umsetzungsrunde 2026-06-10 auf Davids realer Hardware.

Buehnenbild (wie Komplett-Demo):
  * 4x ZQ01424 (8ch RGBW)  — PARs, Adressen via state.suggest_address (P1!)
  * 2x ZQ02001 (11ch MH)   — links/rechts
  * Akai APC mini: 8 Seiten nach dem P13-Schema.

Dogfooding der neuen Features:
  * P1  suggest_address vergibt die Patch-Adressen (erwartet 1/9/17/25/33/44)
  * P4  state.live_view_meta (Zoom/Grid/Snap/Welt) wandert mit der Show
  * P5  Gruppen MIT Ordnern ("Buehne", "Spezial") -> Programmer zeigt Ordner
  * P6  "Weiss (W-Kanal)"-Szene nutzt color_w=255 + RGB=0 (vs. "Weiss (RGB)")
  * P10 MH-Farbrad-Szenen inkl. 2 Split-Farben (aus den ECHTEN Profil-Ranges)
  * P11 EFX inkl. Bounce (frischer Bounce-Fix) fuer die neue Visualisierung

8 Seiten (APC-Scene-Tasten rechts):
  1 GRUPPEN    Gruppen-Looks an/aus + Flash (PARs / MHs / Alle)
  2 FARBEN     Grundfarben, Weiss-W vs. Weiss-RGB, MH-Farbrad inkl. Splits
  3 INTENSITY  Dimmer-Szenen/-Chaser, Strobe, Full On/Off + Speed-Fader
  4 MH POS     5 feste Positionen + Pan/Tilt-Fader + Stop
  5 EFX        Kreis/Sweep/Acht/Bounce + EFX-Speed-Fader
  6 LOOKS      Ambient/Party/Festival/Highlight + Matrix-Effekte
  7 SPECIALS   Blackout/Stop/Clear/Tap/Musik-BPM + Beat-Chaser + MH-Reset
  8 TEST       White-Kanal-Vergleich, Slider-Sync-, Live-View-, Ordner-Tests

Aufruf:  venv/Scripts/python.exe tools/build_practice_show.py
Erzeugt: shows/Praxis_Demo.lshow + Selbstverifikation (Exit != 0 bei Fehler).
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
from src.core.app_state import get_state, get_channels_for_patched
from src.core.database.fixture_db import engine as fdb_engine
from src.core.database.models import PatchedFixture, FixtureProfile, FixtureGroup
from src.core.engine.function_manager import get_function_manager
from src.core.engine.function import RunOrder, Direction
from src.core.engine.chaser import ChaserStep
from src.core.engine.rgb_matrix import RgbAlgorithm
from src.core.engine.efx import EfxFixture, EfxAlgorithm
from src.core.show.show_file import reset_show, save_show, load_show
from src.ui.virtualconsole.vc_button import VCButton, ButtonAction
from src.ui.virtualconsole.vc_color import VCColor, ColorTarget
from src.ui.virtualconsole.vc_slider import VCSlider, SliderMode
from src.ui.virtualconsole.vc_label import VCLabel

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(_ROOT, "shows", "Praxis_Demo.lshow")

DEVICE = "mk2"
TRACK0 = 64 if DEVICE == "original" else 100

LV_META = {"zoom": 1.0, "grid_size": 20, "snap": True,
           "grid_visible": True, "world_w": 1200, "world_h": 800}


def profile_id(short: str) -> int:
    with Session(fdb_engine()) as s:
        pid = s.execute(
            select(FixtureProfile.id).where(FixtureProfile.short_name == short)
        ).scalar_one_or_none()
    if pid is None:
        raise SystemExit(f"Profil '{short}' fehlt — bitte App einmal starten.")
    return int(pid)


# ── 0) Leere Basis ──────────────────────────────────────────────────────────
reset_show()
state = get_state()
fm = get_function_manager()

PAR_PID = profile_id("ZQ01424")
MH_PID = profile_id("ZQ02001")

# ── 1) PATCH — Adressen ueber suggest_address (P1-Dogfooding) ───────────────
par_fids: list[int] = []
for i in range(4):
    fid = i + 1
    addr = state.suggest_address(1, 8)
    assert addr is not None, "suggest_address fand keinen Platz fuer PAR"
    state.add_fixture(PatchedFixture(
        fid=fid, label=f"PAR {i + 1}", fixture_profile_id=PAR_PID,
        mode_name="8-Kanal RGBW", universe=1, address=addr, channel_count=8,
        manufacturer_name="Generic", fixture_name="Stage Light ZQ01424",
        fixture_type="par"), undoable=False)
    par_fids.append(fid)

mh_left, mh_right = 5, 6
mh_fids = [mh_left, mh_right]
for fid, mh_label in ((mh_left, "MH Links"), (mh_right, "MH Rechts")):
    addr = state.suggest_address(1, 11)
    assert addr is not None, "suggest_address fand keinen Platz fuer MH"
    state.add_fixture(PatchedFixture(
        fid=fid, label=mh_label, fixture_profile_id=MH_PID,
        mode_name="11-Kanal", universe=1, address=addr, channel_count=11,
        manufacturer_name="U King", fixture_name="ZQ02001 Mini Moving Head",
        fixture_type="moving_head"), undoable=False)

fixtures = state.get_patched_fixtures()
ADDRS = sorted(f.address for f in fixtures)
assert ADDRS == [1, 9, 17, 25, 33, 44], f"suggest_address-Adressen: {ADDRS}"
chan_of = {f.fid: {c.attribute: c.channel_number
                   for c in get_channels_for_patched(f)} for f in fixtures}

state.base_levels = {fid: {"intensity": 255} for fid in par_fids}
state._rebuild_render_plan()

# ── 2) GRUPPEN MIT ORDNERN (P5-Dogfooding) ──────────────────────────────────
with state._session() as s:
    s.execute(delete(FixtureGroup))
    s.add(FixtureGroup(name="PARs", cols=4, rows=1, folder="Bühne",
                       positions_json=json.dumps({f"{i},0": par_fids[i] for i in range(4)})))
    s.add(FixtureGroup(name="Moving Heads", cols=2, rows=1, folder="Bühne",
                       positions_json=json.dumps({"0,0": mh_left, "1,0": mh_right})))
    s.add(FixtureGroup(name="Alle", cols=6, rows=1, folder="Spezial",
                       positions_json=json.dumps({f"{i},0": fid for i, fid in
                                                  enumerate(par_fids + mh_fids)})))
    s.commit()

# ── 3) LIVE VIEW: Positionen + Meta (P4-Dogfooding) ─────────────────────────
state.live_view_positions = {
    1: (300.0, 600.0), 2: (480.0, 600.0), 3: (660.0, 600.0), 4: (840.0, 600.0),
    mh_left: (220.0, 200.0), mh_right: (920.0, 200.0),
}
state.live_view_meta = dict(LV_META)


# ════════════════════════════════════════════════════════════════════════════
#  4) FUNKTIONEN
# ════════════════════════════════════════════════════════════════════════════
def par_scene(name, attrs_per_fid=None, **attrs):
    sc = fm.new_scene(name)
    for fid in par_fids:
        cm = chan_of[fid]
        use = (attrs_per_fid or {}).get(fid, attrs)
        for attr, val in use.items():
            if attr in cm:
                sc.set_value(fid, cm[attr], val)
    return sc


def mh_scene(name, **attrs):
    sc = fm.new_scene(name)
    for fid in mh_fids:
        cm = chan_of[fid]
        for attr, val in attrs.items():
            if attr in cm:
                sc.set_value(fid, cm[attr], val)
    return sc


def chaser(name, step_ids, hold=0.4, fade=0.0, order=RunOrder.Loop):
    c = fm.new_chaser(name)
    c.run_order, c.direction = order, Direction.Forward
    for sid in step_ids:
        c.steps.append(ChaserStep(function_id=sid, fade_in=fade, hold=hold, fade_out=0.0))
    return c


# Farben (PARs) — Weiss-Vergleich ist der P6-Praxistest:
sc_white_w = par_scene("Weiß (W-Kanal)", intensity=255,
                       color_r=0, color_g=0, color_b=0, color_w=255)
sc_white_rgb = par_scene("Weiß (RGB)", intensity=255,
                         color_r=255, color_g=255, color_b=255, color_w=0)
sc_red = par_scene("Rot", intensity=255, color_r=255, color_g=0, color_b=0, color_w=0)
sc_grn = par_scene("Grün", intensity=255, color_g=255, color_r=0, color_b=0, color_w=0)
sc_blu = par_scene("Blau", intensity=255, color_b=255, color_r=0, color_g=0, color_w=0)
sc_amb = par_scene("Amber", intensity=255, color_r=255, color_g=140, color_b=0, color_w=0)
sc_cya = par_scene("Cyan", intensity=255, color_g=255, color_b=255, color_r=0, color_w=0)
sc_mag = par_scene("Magenta", intensity=255, color_r=255, color_b=255, color_g=0, color_w=0)
color_scenes = [sc_red, sc_grn, sc_blu, sc_amb, sc_cya, sc_mag]

# Looks (PARs + MH-Farbrad wo sinnvoll):
lk_ambient = par_scene("Ambient Ruhig", intensity=110, color_r=255, color_g=120,
                       color_b=20, color_w=80)
lk_party = par_scene("Party", intensity=255, color_r=255, color_g=0,
                     color_b=180, color_w=20)
lk_festival = par_scene("Festival", intensity=255, color_r=255, color_g=80,
                        color_b=0, color_w=0)
lk_highlight = par_scene("Highlight", attrs_per_fid={
    1: {"intensity": 60, "color_r": 40, "color_g": 40, "color_b": 80},
    2: {"intensity": 255, "color_r": 0, "color_g": 0, "color_b": 0, "color_w": 255},
    3: {"intensity": 255, "color_r": 0, "color_g": 0, "color_b": 0, "color_w": 255},
    4: {"intensity": 60, "color_r": 40, "color_g": 40, "color_b": 80},
})
look_funcs = [lk_ambient, lk_party, lk_festival, lk_highlight]

# Dimmer:
def par_dim(name, on_fids, level=255):
    return par_scene(name, attrs_per_fid={
        fid: {"intensity": (level if fid in set(on_fids) else 0)} for fid in par_fids})


st1 = par_dim("Dim P1", [1]); st2 = par_dim("Dim P2", [2])
st3 = par_dim("Dim P3", [3]); st4 = par_dim("Dim P4", [4])
st_all = par_dim("Full On", par_fids)
st_half = par_dim("Dim 50%", par_fids, level=128)
st_off = par_dim("All Off", [])

ch_run = chaser("Lauflicht >", [st1.id, st2.id, st3.id, st4.id], hold=0.35, fade=0.08)
ch_ping = chaser("Ping-Pong", [st1.id, st2.id, st3.id, st4.id, st3.id, st2.id],
                 hold=0.28, fade=0.06)
ch_strobe = chaser("Strobe-Chase", [st_all.id, st_off.id], hold=0.05)
ch_color = chaser("Color-Chase", [s.id for s in color_scenes], hold=0.5, fade=0.2)
dim_funcs = [ch_run, ch_ping, ch_strobe]

# MH-Positionen:
pos_center = mh_scene("Pos Center", pan=128, tilt=128, intensity=255, shutter=4)
pos_aud = mh_scene("Pos Publikum", pan=128, tilt=70, intensity=255, shutter=4)
pos_stage = mh_scene("Pos Bühne", pan=128, tilt=180, intensity=255, shutter=4)
pos_left = mh_scene("Pos Links", pan=60, tilt=128, intensity=255, shutter=4)
pos_right = mh_scene("Pos Rechts", pan=196, tilt=128, intensity=255, shutter=4)
mh_pos_funcs = [pos_center, pos_aud, pos_stage, pos_left, pos_right]

# MH-Farbrad aus den ECHTEN Profil-Ranges: Vollfarben + Split-Farben (P10).
_mh_fx = next(f for f in fixtures if f.fid == mh_left)
_cw_chan = next(c for c in get_channels_for_patched(_mh_fx)
                if c.attribute == "color_wheel")
_full_slots, _split_slots = [], []
for r in (getattr(_cw_chan, "ranges", None) or []):
    if (getattr(r, "kind", "") or "") != "color":
        continue
    mid = (int(r.range_from) + int(r.range_to)) // 2
    name = getattr(r, "name", "") or "?"
    (_split_slots if "/" in name else _full_slots).append((name, mid))
assert len(_full_slots) >= 3, f"Zu wenige Vollfarben-Slots: {_full_slots}"
assert len(_split_slots) >= 2, f"Zu wenige Split-Slots: {_split_slots}"

mh_cw_funcs = [mh_scene(f"MH {nm}", color_wheel=val, intensity=255, shutter=4)
               for nm, val in _full_slots[:3]]
mh_split_funcs = [mh_scene(f"MH Split {nm}", color_wheel=val, intensity=255, shutter=4)
                  for nm, val in _split_slots[:2]]

mh_reset = mh_scene("MH Reset", reset=200)

# EFX (P11-Dogfooding inkl. Bounce-Fix):
def mh_efx(name, algo, speed_hz=0.35, spread=0.0, mirror=False, direction="forward"):
    e = fm.new_efx(name)
    e.algorithm = algo
    e.fixtures = [EfxFixture(fid=mh_left), EfxFixture(fid=mh_right)]
    e.speed_hz, e.spread, e.mirror, e.direction = speed_hz, spread, mirror, direction
    e.open_beam = True
    e.width, e.height = 170.0, 150.0
    e.x_offset, e.y_offset = 128.0, 128.0
    return e


efx_circle = mh_efx("EFX Kreis", EfxAlgorithm.CIRCLE, spread=0.5)
efx_sweep = mh_efx("EFX Sweep", EfxAlgorithm.LINE, mirror=True)
efx_eight = mh_efx("EFX Acht", EfxAlgorithm.EIGHT)
efx_bounce = mh_efx("EFX Bounce", EfxAlgorithm.LINE, direction="bounce")
efx_funcs = [efx_circle, efx_sweep, efx_eight, efx_bounce]

# Matrix (auf der PAR-Reihe):
def matrix(name, algo, c1=(255, 0, 0), c2=(0, 0, 255), speed=2.0, params=None):
    m = fm.new_rgb_matrix(name)
    m.algorithm = algo
    m.fixture_grid = list(par_fids); m.cols = len(par_fids); m.rows = 1
    m.color1, m.color2 = c1, c2
    m.matrix_speed = speed
    if params:
        m.params = params
    return m


mx_rainbow = matrix("Mtx Rainbow", RgbAlgorithm.RAINBOW, speed=1.5)
mx_chase = matrix("Mtx Lauflicht", RgbAlgorithm.CHASE, c1=(255, 255, 255), speed=4.0,
                  params={"axis": "H", "movement": "normal"})
mx_fire = matrix("Mtx Fire", RgbAlgorithm.FIRE, speed=2.0)
mx_funcs = [mx_rainbow, mx_chase, mx_fire]

# Beat:
bt_a = par_scene("Beat A", intensity=255, color_r=255, color_g=0, color_b=60, color_w=0)
bt_b = par_scene("Beat B", intensity=255, color_r=0, color_g=120, color_b=255, color_w=0)
bt_chaser = chaser("Beat-Looks", [bt_a.id, bt_b.id], hold=0.5, fade=0.1)
bt_chaser.audio_triggered = True
bt_chaser.beats_per_step = 2


# ════════════════════════════════════════════════════════════════════════════
#  5) VIRTUAL CONSOLE — APC mini, 8 Banken nach P13-Schema
# ════════════════════════════════════════════════════════════════════════════
PAD, GAP, X0, Y0 = 60, 6, 20, 70
STEP = PAD + GAP
GRID_BOTTOM = Y0 + 8 * STEP
TY = GRID_BOTTOM + 4
Y_FAD = GRID_BOTTOM + 34
FAD_H = 142
widgets: list[dict] = []

BANK_ALL = -1
B_GRP, B_COL, B_INT, B_POS, B_EFX, B_LOOK, B_SPC, B_TEST = range(8)
PAGE_NAMES = ["GRUPPEN", "FARBEN", "INTENSITY", "MH POSITION",
              "EFX", "LOOKS", "SPECIALS", "TEST"]


def pad_pos(note):
    row, col = note // 8, note % 8
    return X0 + col * STEP, Y0 + (7 - row) * STEP


def _add(w, x, y, ww, hh, bank):
    w.bank = bank
    w.setGeometry(x, y, ww, hh)
    widgets.append(w.to_dict())


def func_btn(fn, note, bank, accent, style="pulse", flash=False):
    b = VCButton(fn.name)
    b.action = ButtonAction.FUNCTION_FLASH if flash else ButtonAction.FUNCTION_TOGGLE
    b.function_id = fn.id
    b.pad_style = style
    b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, note
    b._bg_color.setNamedColor(accent)
    x, y = pad_pos(note); _add(b, x, y, PAD, PAD, bank)


def action_btn(name, action, note, bank, accent):
    b = VCButton(name)
    b.action = action; b.pad_style = "solid"
    b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, note
    b._bg_color.setNamedColor(accent)
    x, y = pad_pos(note); _add(b, x, y, PAD, PAD, bank)


def color_tile(name, note, bank, r, g, b, w=0):
    c = VCColor(name)
    c.color_r, c.color_g, c.color_b, c.color_w = r, g, b, w
    c.with_intensity = False
    c.target = ColorTarget.ALL
    c.midi_type, c.midi_ch, c.midi_data1 = "note_on", 0, note
    x, y = pad_pos(note); _add(c, x, y, PAD, PAD, bank)


def fader(caption, col, bank, mode, function_id=None, function_ids=None,
          programmer_attr="intensity", param_key="speed", midi_cc=-1, value=0,
          submaster_slot=None):
    s = VCSlider(caption)
    s.mode = mode; s.function_id = function_id; s.function_ids = list(function_ids or [])
    if submaster_slot is not None:
        s.function_id = submaster_slot
    s.programmer_attr = programmer_attr; s.param_key = param_key
    s.midi_cc, s.midi_ch = midi_cc, 0; s._value = value
    x = X0 + col * STEP + 2; _add(s, x, Y_FAD, 56, FAD_H, bank)


def label(text, x, y, ww, bank, hh=20, fg="#cfcfcf"):
    _add(VCLabel(text), x, y, ww, hh, bank)


# Universell (alle Seiten): Track-Tasten + Fader F6/F7/F9
for i, (nm, act, col) in enumerate([
        ("Clear", ButtonAction.CLEAR, "#4a3a10"),
        ("Stop All", ButtonAction.STOP_ALL, "#4a1010"),
        ("Blackout", ButtonAction.BLACKOUT, "#2a0000"),
        ("Tap", ButtonAction.TAP, "#103a3a"),
        ("Musik-BPM", ButtonAction.AUDIO_BPM, "#103a4a")]):
    b = VCButton(nm); b.action = act; b.pad_style = "solid"
    b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, TRACK0 + i
    b._bg_color.setNamedColor(col)
    _add(b, X0 + i * 64, TY, 60, 26, BANK_ALL)

fader("Dimmer", 5, BANK_ALL, SliderMode.SUBMASTER, submaster_slot=0, midi_cc=53, value=255)
fader("Speed", 6, BANK_ALL, SliderMode.SPEED, midi_cc=54, value=64)
fader("Master", 8, BANK_ALL, SliderMode.GRANDMASTER, midi_cc=56, value=255)
for i, nm in enumerate(PAGE_NAMES):
    label(f"Scene {i + 1}: {nm}", X0 + 8 * STEP + 16, Y0 + i * 26, 160, BANK_ALL,
          hh=22, fg="#7aa0c0")

# ── BANK 1 — GRUPPEN ────────────────────────────────────────────────────────
func_btn(st_all, 56, B_GRP, "#264a6a", style="solid")          # PARs an
func_btn(pos_center, 57, B_GRP, "#1f3a6a", style="solid")      # MHs Beam auf
func_btn(lk_festival, 58, B_GRP, "#3a2a5a", style="solid")     # Alle (Look)
func_btn(st_all, 48, B_GRP, "#264a6a", flash=True)             # PARs Flash
func_btn(pos_center, 49, B_GRP, "#1f3a6a", flash=True)         # MHs Flash
func_btn(st_off, 40, B_GRP, "#3a1010", style="solid")          # PARs aus
label("BANK 1  GRUPPEN  -  Reihe 1: PARs an / MHs Beam auf / Alle (Look). "
      "Reihe 2: Flash-Varianten (nur solange gedrueckt). Hinweis: ECHTE "
      "Gruppen-AUSWAHL (Programmer) geht ueber Live View/Programmer, nicht per Pad.",
      X0, 28, 1100, B_GRP, fg="#9DFF52")

# ── BANK 2 — FARBEN ─────────────────────────────────────────────────────────
_grund = [("Rot", 255, 0, 0, 0), ("Grün", 0, 255, 0, 0), ("Blau", 0, 0, 255, 0),
          ("Amber", 255, 140, 0, 0), ("Cyan", 0, 255, 255, 0), ("Magenta", 255, 0, 255, 0),
          ("Orange", 255, 80, 0, 0), ("Pink", 255, 0, 120, 0)]
for i, (nm, r, g, b, w) in enumerate(_grund):
    color_tile(nm, 56 + i, B_COL, r, g, b, w)
# Weiss-Vergleich (P6): Kachel "Weiss (W)" nutzt NUR den W-Kanal.
color_tile("Weiß (W)", 48, B_COL, 0, 0, 0, w=255)
color_tile("Weiß (RGB)", 49, B_COL, 255, 255, 255, w=0)
color_tile("Warmweiß", 50, B_COL, 255, 130, 40, w=60)
color_tile("Kaltweiss", 51, B_COL, 180, 200, 255, w=120)
for i, fn in enumerate(mh_cw_funcs):
    func_btn(fn, 40 + i, B_COL, "#3a2a5a", style="solid")
for i, fn in enumerate(mh_split_funcs):
    func_btn(fn, 43 + i, B_COL, "#5a2a5a", style="solid")
func_btn(ch_color, 32, B_COL, "#3a2150")
label("BANK 2  FARBEN  -  oben Grundfarben (PARs), Reihe 2: Weiß-Test "
      "(W-Kanal vs. RGB!), Reihe 3: MH-Farbrad inkl. 2 SPLIT-Farben, "
      "links unten Farb-Chaser.", X0, 28, 1100, B_COL, fg="#9DFF52")

# ── BANK 3 — INTENSITY ──────────────────────────────────────────────────────
for i, fn in enumerate([st_all, st_half, st_off, ch_run, ch_ping, ch_strobe]):
    func_btn(fn, 56 + i, B_INT, "#1f4a28")
fader("Sp Lauf", 0, B_INT, SliderMode.EFFECT_SPEED, function_id=ch_run.id, midi_cc=48, value=64)
fader("Sp Strobe", 1, B_INT, SliderMode.EFFECT_SPEED, function_id=ch_strobe.id, midi_cc=49, value=90)
fader("FX-Level", 4, B_INT, SliderMode.EFFECT_INTENSITY,
      function_ids=[f.id for f in dim_funcs], midi_cc=52, value=255)
label("BANK 3  INTENSITY  -  Full On / 50% / Off, Lauflicht, Ping-Pong, Strobe. "
      "F1/F2 Speed, F5 FX-Level, F6 Dimmer, F9 Grand Master.",
      X0, 28, 1100, B_INT, fg="#9DFF52")

# ── BANK 4 — MH POSITION ────────────────────────────────────────────────────
for i, fn in enumerate(mh_pos_funcs):
    func_btn(fn, 56 + i, B_POS, "#10503a", style="solid")
action_btn("Stop All", ButtonAction.STOP_ALL, 63, B_POS, "#4a1010")
fader("Pan", 0, B_POS, SliderMode.PROGRAMMER, programmer_attr="pan", midi_cc=48, value=128)
fader("Tilt", 1, B_POS, SliderMode.PROGRAMMER, programmer_attr="tilt", midi_cc=49, value=128)
label("BANK 4  MH POSITION  -  Center/Publikum/Bühne/Links/Rechts. "
      "F1/F2 = Pan/Tilt von Hand (Programmer; MHs vorher im Programmer wählen).",
      X0, 28, 1100, B_POS, fg="#9DFF52")

# ── BANK 5 — EFX ────────────────────────────────────────────────────────────
for i, fn in enumerate(efx_funcs):
    func_btn(fn, 56 + i, B_EFX, "#1f3a6a")
fader("EFX-Sp", 0, B_EFX, SliderMode.EFFECT_SPEED,
      function_ids=[f.id for f in efx_funcs], midi_cc=48, value=70)
label("BANK 5  EFX  -  Kreis (Fan 50%) / Sweep (gespiegelt) / Acht / Bounce. "
      "Alle öffnen den Beam automatisch. F1 = EFX-Speed.",
      X0, 28, 1100, B_EFX, fg="#9DFF52")

# ── BANK 6 — LOOKS ──────────────────────────────────────────────────────────
for i, fn in enumerate(look_funcs):
    func_btn(fn, 56 + i, B_LOOK, "#264a6a", style="solid")
for i, fn in enumerate(mx_funcs):
    func_btn(fn, 48 + i, B_LOOK, "#7a5b00")
label("BANK 6  LOOKS  -  Ambient/Party/Festival/Highlight (Szenen), darunter "
      "Matrix-Effekte (bringen eigene Farbe mit -> vorher Clear).",
      X0, 28, 1100, B_LOOK, fg="#9DFF52")

# ── BANK 7 — SPECIALS ───────────────────────────────────────────────────────
action_btn("Blackout", ButtonAction.BLACKOUT, 56, B_SPC, "#2a0000")
action_btn("Stop All", ButtonAction.STOP_ALL, 57, B_SPC, "#4a1010")
action_btn("Clear", ButtonAction.CLEAR, 58, B_SPC, "#4a3a10")
action_btn("Tap", ButtonAction.TAP, 59, B_SPC, "#103a3a")
action_btn("Musik-BPM", ButtonAction.AUDIO_BPM, 60, B_SPC, "#103a4a")
func_btn(bt_chaser, 48, B_SPC, "#1f6a4a")
func_btn(ch_strobe, 49, B_SPC, "#4a1030")
func_btn(st_off, 50, B_SPC, "#3a1010", style="solid")      # All Dimmer Off
func_btn(mh_reset, 51, B_SPC, "#401010", style="solid", flash=True)
label("BANK 7  SPECIALS  -  Blackout/Stop/Clear/Tap/Musik-BPM, Beat-Chaser "
      "(folgt Tap- oder Musik-BPM), Strobe, All Off, MH-Reset (halten!).",
      X0, 28, 1100, B_SPC, fg="#9DFF52")

# ── BANK 8 — TEST / DEBUG ───────────────────────────────────────────────────
func_btn(sc_white_w, 56, B_TEST, "#666688", style="solid")
func_btn(sc_white_rgb, 57, B_TEST, "#888866", style="solid")
func_btn(mx_rainbow, 58, B_TEST, "#7a5b00")
func_btn(efx_circle, 59, B_TEST, "#1f3a6a")
func_btn(ch_run, 60, B_TEST, "#1f4a28")
fader("Rot", 0, B_TEST, SliderMode.PROGRAMMER, programmer_attr="color_r", midi_cc=48, value=0)
fader("Weiß", 1, B_TEST, SliderMode.PROGRAMMER, programmer_attr="color_w", midi_cc=49, value=0)
label("BANK 8  TEST  -  Pad 1/2: Weiß ueber W-KANAL vs. RGB (am Gerät vergleichen!). "
      "Slider-Sync-Test: Farbe klicken -> Programmer-Slider müssen folgen.",
      X0, 28, 1100, B_TEST, fg="#9DFF52")
label("Weitere Tests: Live View Fixture verschieben -> Auto-Save (5 min) sichert; "
      "Patch->Gruppen: Ordner 'Bühne'/'Spezial' müssen im Programmer erscheinen.",
      X0, 48, 1100, B_TEST)

state._vc_layout = {"widgets": widgets}

pe = getattr(state, "playback_engine", None)
if pe is not None:
    try:
        for idx, nm in enumerate(PAGE_NAMES):
            if 0 <= idx < len(pe.page_names):
                pe.page_names[idx] = nm
        pe.set_page(0)
    except Exception as e:
        print(f"[build] page name error: {e}")

# ════════════════════════════════════════════════════════════════════════════
#  6) Speichern + Selbstverifikation (Save/Reload-Roundtrip)
# ════════════════════════════════════════════════════════════════════════════
state.programmer = {}
state.show_name = "Praxis Demo"
save_show(OUT)
print(f"Gespeichert: {OUT}")

ok, msg = load_show(OUT)
assert ok, f"Show laedt nicht: {msg}"

# Patch + suggest_address-Ergebnis
fx2 = state.get_patched_fixtures()
assert len(fx2) == 6, f"6 Fixtures erwartet, {len(fx2)}"
assert sorted(f.address for f in fx2) == [1, 9, 17, 25, 33, 44]
print("Patch OK: " + ", ".join(f"[{f.fid}]{f.label}@{f.address}" for f in fx2))

# Gruppen + Ordner (P5)
with state._session() as s:
    groups = list(s.execute(select(FixtureGroup)).scalars().all())
folders = {g.name: g.folder for g in groups}
assert folders == {"PARs": "Bühne", "Moving Heads": "Bühne", "Alle": "Spezial"}, folders
print(f"Gruppen+Ordner OK: {folders}")

# Live-View-Meta (P4)
assert state.live_view_meta == LV_META, f"live_view_meta: {state.live_view_meta}"
assert len(state.live_view_positions) == 6
print(f"Live-View OK: 6 Positionen + Meta {state.live_view_meta}")

# Weiss-Szenen (P6): W-Kanal-Szene hat color_w=255 und RGB=0
from src.core.engine.scene import Scene
scenes = {f.name: f for f in fm.all() if isinstance(f, Scene)}
ww = scenes["Weiß (W-Kanal)"]
cm1 = chan_of[1]
vals = {(v.fixture_id, v.channel): v.value for v in ww._values}
w_val = vals.get((1, cm1["color_w"]))
r_val = vals.get((1, cm1["color_r"]))
assert w_val == 255 and r_val == 0, f"Weiß (W-Kanal): w={w_val} r={r_val}"
print("Weiß-Test OK: 'Weiß (W-Kanal)' nutzt color_w=255, RGB=0")

# Split-Farben (P10)
split_names = [n for n in scenes if n.startswith("MH Split ")]
assert len(split_names) == 2, f"2 Split-Szenen erwartet: {split_names}"
print(f"Split-Farben OK: {split_names}")

# EFX inkl. Bounce (P11)
from src.core.engine.efx import EfxInstance
efxs = {f.name: f for f in fm.all() if isinstance(f, EfxInstance)}
assert set(efxs) == {"EFX Kreis", "EFX Sweep", "EFX Acht", "EFX Bounce"}, set(efxs)
assert efxs["EFX Bounce"].direction == "bounce"
assert all(e.open_beam for e in efxs.values())
print(f"EFX OK: {sorted(efxs)} (Bounce-Richtung persistiert)")

# VC: 8 Banken + Universal-Widgets
from collections import Counter
vc = state._vc_layout.get("widgets", [])
banks = Counter(w.get("bank") for w in vc)
assert set(banks) == set(range(8)) | {-1}, f"Banken: {sorted(banks)}"
assert any(w.get("action") == "Blackout" for w in vc)
print(f"VC OK: {len(vc)} Widgets, Bank-Verteilung {dict(sorted(banks.items()))}")

# Beat-Chaser
from src.core.engine.chaser import Chaser
bt = next(f for f in fm.all() if isinstance(f, Chaser) and f.name == "Beat-Looks")
assert bt.audio_triggered is True and bt.beats_per_step == 2
print("Beat-Chaser OK (audio_triggered, 2 Beats/Step)")

print("FERTIG — Praxis_Demo.lshow vollstaendig verifiziert.")
