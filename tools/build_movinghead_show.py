"""LEIT-DEMO-SHOW: Moving Heads + PARs + APC mini (Moving-Head-Initiative).

Bühnenbild (wie vom Nutzer beschrieben):
  * 4x  Generic "Stage Light ZQ01424" (8-Kanal RGBW)  = PARs in der MITTE
        -> Universe 1, DMX 1 / 9 / 17 / 25
  * 2x  U King "ZQ02001" (11-Kanal Moving Head)        = je 1 MH LINKS und RECHTS
        -> Universe 1, DMX 33 (links) und 44 (rechts)
  * Akai APC mini als Hardware-Controller der Virtual Console.

Zeigt ALLE neuen Moving-Head-Features:
  - Pan/Tilt-EFX auf der MH-Gruppe (Kreis/Acht/Sweep) mit Fan (spread) + Spiegeln,
    open_beam macht die Strahler sichtbar (Dimmer/Shutter offen).
  - Farbrad- und Gobo-Schnellwahl-Szenen (color_wheel / gobo_wheel der ZQ02001).
  - Shutter Open/Strobe (Shutter-Schnellwahl-Werte aus den Capability-Ranges).
  - Position-Presets (Center / Audience / Wide / Cross).
  - PAR-Farben, Dimmer-Lauflicht und RGB-Matrix auf der PAR-Reihe.
  - Echte Fixture-Gruppen ("PAR-Reihe", "Moving Heads"), persistiert in der .lshow.

Aufruf:  venv/Scripts/python.exe tools/build_movinghead_show.py
Erzeugt: shows/MovingHead_Demo.lshow
"""
from __future__ import annotations
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
_app = QApplication.instance() or QApplication([])

from sqlalchemy import select
from sqlalchemy.orm import Session
from src.core.app_state import get_state, get_channels_for_patched
from src.core.database.fixture_db import engine as fdb_engine
from src.core.database.models import PatchedFixture, FixtureProfile, FixtureGroup
from src.core.engine.function_manager import get_function_manager
from src.core.engine.function import RunOrder, Direction
from src.core.engine.chaser import ChaserStep
from src.core.engine.rgb_matrix import RgbAlgorithm
from src.core.engine.efx import EfxFixture, EfxAlgorithm
from src.core.engine.snap_library import get_snap_library
from src.core.show.show_file import reset_show, save_show, load_show
from src.ui.virtualconsole.vc_button import VCButton, ButtonAction
from src.ui.virtualconsole.vc_color import VCColor, ColorTarget
from src.ui.virtualconsole.vc_slider import VCSlider, SliderMode
from src.ui.virtualconsole.vc_label import VCLabel

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(_ROOT, "shows", "MovingHead_Demo.lshow")

DEVICE = "mk2"
TRACK0 = 64 if DEVICE == "original" else 100


def profile_id(short: str) -> int:
    with Session(fdb_engine()) as s:
        pid = s.execute(
            select(FixtureProfile.id).where(FixtureProfile.short_name == short)
        ).scalar_one_or_none()
    if pid is None:
        raise SystemExit(f"Profil '{short}' fehlt in der Fixture-DB — bitte App einmal starten.")
    return int(pid)


# ── 0) Leere Basis ──────────────────────────────────────────────────────────
reset_show()
state = get_state()
fm = get_function_manager()
lib = get_snap_library()

PAR_PID = profile_id("ZQ01424")
MH_PID = profile_id("ZQ02001")

# ── 1) PATCH: 4 PAR (Mitte) + 2 MH (links/rechts) ───────────────────────────
par_fids: list[int] = []
addr = 1
for i in range(4):
    fid = i + 1
    state.add_fixture(PatchedFixture(
        fid=fid, label=f"PAR {i + 1}", fixture_profile_id=PAR_PID,
        mode_name="8-Kanal RGBW", universe=1, address=addr, channel_count=8,
        manufacturer_name="Generic", fixture_name="Stage Light ZQ01424",
        fixture_type="par"), undoable=False)
    par_fids.append(fid)
    addr += 8

mh_left, mh_right = 5, 6
for fid, label, a in ((mh_left, "MH Links", 33), (mh_right, "MH Rechts", 44)):
    state.add_fixture(PatchedFixture(
        fid=fid, label=label, fixture_profile_id=MH_PID,
        mode_name="11-Kanal", universe=1, address=a, channel_count=11,
        manufacturer_name="U King", fixture_name="ZQ02001 Mini Moving Head",
        fixture_type="moving_head"), undoable=False)
mh_fids = [mh_left, mh_right]

fixtures = state.get_patched_fixtures()
all_fids = [f.fid for f in fixtures]
chan_of = {f.fid: {c.attribute: c.channel_number
                   for c in get_channels_for_patched(f)} for f in fixtures}

# PARs "scharf": Grundhelligkeit -> Farbe sofort sichtbar.
state.base_levels = {fid: {"intensity": 255} for fid in par_fids}
state._rebuild_render_plan()

# ── 2) GRUPPEN (persistiert in der .lshow) ──────────────────────────────────
with state._session() as s:
    from sqlalchemy import delete
    s.execute(delete(FixtureGroup))
    s.add(FixtureGroup(name="PAR-Reihe", cols=4, rows=1,
                       positions_json=json.dumps({f"{i},0": par_fids[i] for i in range(4)})))
    s.add(FixtureGroup(name="Moving Heads", cols=2, rows=1,
                       positions_json=json.dumps({"0,0": mh_left, "1,0": mh_right})))
    s.commit()

# ════════════════════════════════════════════════════════════════════════════
#  3) FUNKTIONEN
# ════════════════════════════════════════════════════════════════════════════

# ── PAR: Farb-Looks ─────────────────────────────────────────────────────────
def par_look(name, r=0, g=0, b=0, w=0, intensity=255):
    sc = fm.new_scene(name)
    for fid in par_fids:
        cm = chan_of[fid]
        if "intensity" in cm:
            sc.set_value(fid, cm["intensity"], intensity)
        for attr, val in (("color_r", r), ("color_g", g), ("color_b", b), ("color_w", w)):
            if attr in cm:
                sc.set_value(fid, cm[attr], val)
    return sc


lk_warm = par_look("Warm Wash", r=255, g=120, b=20, w=120)
lk_cold = par_look("Cold Wash", r=0, g=60, b=255, w=80)
lk_party = par_look("Party", r=255, g=0, b=180)
lk_white = par_look("Vollweiss", r=255, g=255, b=255, w=255)


def par_dim(name, on_fids):
    sc = fm.new_scene(name)
    on = set(on_fids)
    for fid in par_fids:
        if "intensity" in chan_of[fid]:
            sc.set_value(fid, chan_of[fid]["intensity"], 255 if fid in on else 0)
    return sc


pd = [par_dim(f"Dim {i+1}", [par_fids[i]]) for i in range(4)]
dim_run = fm.new_chaser("PAR Lauflicht")
dim_run.run_order, dim_run.direction, dim_run.speed = RunOrder.Loop, Direction.Forward, 1.0
for sc in pd:
    dim_run.steps.append(ChaserStep(function_id=sc.id, fade_in=0.08, hold=0.35, fade_out=0.0))

# ── PAR: RGB-Matrix auf der PAR-Reihe ───────────────────────────────────────
def par_matrix(name, algo, c1=(255, 0, 0), c2=(0, 0, 255), speed=2.0):
    m = fm.new_rgb_matrix(name)
    m.algorithm = algo
    m.fixture_grid = list(par_fids)
    m.cols, m.rows = len(par_fids), 1
    m.color1, m.color2 = c1, c2
    m.matrix_speed = speed
    return m


mx_rainbow = par_matrix("Mtx Regenbogen", RgbAlgorithm.RAINBOW, speed=1.5)
mx_chase = par_matrix("Mtx Lauflicht", RgbAlgorithm.CHASE, c1=(255, 255, 255), speed=4.0)

# ── MOVING HEADS: Pan/Tilt-EFX auf der MH-Gruppe ────────────────────────────
def mh_efx(name, algo, speed_hz=0.35, spread=1.0, mirror=False,
           direction="forward", width=170.0, height=150.0):
    e = fm.new_efx(name)
    e.algorithm = algo
    e.fixtures = [EfxFixture(fid=mh_left), EfxFixture(fid=mh_right)]
    e.speed_hz = speed_hz
    e.spread = spread
    e.mirror = mirror
    e.direction = direction
    e.open_beam = True        # Dimmer + Shutter offen -> sichtbar
    e.width, e.height = width, height
    e.x_offset, e.y_offset = 128.0, 128.0
    return e


efx_circle = mh_efx("MH Kreis (Fan)", EfxAlgorithm.CIRCLE, spread=0.5)
efx_eight = mh_efx("MH Acht", EfxAlgorithm.EIGHT, spread=0.0)
efx_sweep = mh_efx("MH Sweep gespiegelt", EfxAlgorithm.LINE, spread=0.0, mirror=True)
efx_bounce = mh_efx("MH Bounce", EfxAlgorithm.LINE, direction="bounce", spread=0.0)
mh_efx_funcs = [efx_circle, efx_eight, efx_sweep, efx_bounce]

# ── MOVING HEADS: Position-Presets (Pan/Tilt + Dimmer + Shutter offen) ───────
def mh_pos(name, pan, tilt, intensity=255):
    sc = fm.new_scene(name)
    for fid in mh_fids:
        cm = chan_of[fid]
        for attr, val in (("pan", pan), ("tilt", tilt),
                          ("intensity", intensity), ("shutter", 4)):
            if attr in cm:
                sc.set_value(fid, cm[attr], val)
    return sc


pos_center = mh_pos("Pos Center", 128, 128)
pos_aud = mh_pos("Pos Publikum", 128, 180)
pos_up = mh_pos("Pos Hoch", 128, 60)
# "Cross": links zeigt nach rechts, rechts nach links — eigener Pan je Gerät.
pos_cross = fm.new_scene("Pos Cross")
for fid, pan in ((mh_left, 180), (mh_right, 76)):
    cm = chan_of[fid]
    for attr, val in (("pan", pan), ("tilt", 150), ("intensity", 255), ("shutter", 4)):
        if attr in cm:
            pos_cross.set_value(fid, cm[attr], val)
mh_pos_funcs = [pos_center, pos_aud, pos_up, pos_cross]

# ── MOVING HEADS: Farbrad-Schnellwahl (color_wheel) ─────────────────────────
def mh_colorwheel(name, wheel_val):
    sc = fm.new_scene(name)
    for fid in mh_fids:
        cm = chan_of[fid]
        for attr, val in (("color_wheel", wheel_val), ("intensity", 255), ("shutter", 4)):
            if attr in cm:
                sc.set_value(fid, cm[attr], val)
    return sc


# Exakte ZQ02001-Werte (reale Geraetedaten, docs/MOVING_HEADS.md):
# 0-9 weiss/offen, 10-19 rot, 20-29 gruen, 30-39 blau, 40-49 gelb.
cw_white = mh_colorwheel("Farbe Weiss", 4)
cw_red = mh_colorwheel("Farbe Rot", 14)
cw_green = mh_colorwheel("Farbe Gruen", 24)
cw_blue = mh_colorwheel("Farbe Blau", 34)
cw_yellow = mh_colorwheel("Farbe Gelb", 44)
mh_color_funcs = [cw_white, cw_red, cw_green, cw_blue, cw_yellow]

# ── MOVING HEADS: Gobo-Schnellwahl (gobo_wheel) ─────────────────────────────
def mh_gobo(name, gobo_val):
    sc = fm.new_scene(name)
    for fid in mh_fids:
        cm = chan_of[fid]
        for attr, val in (("gobo_wheel", gobo_val), ("intensity", 255), ("shutter", 4)):
            if attr in cm:
                sc.set_value(fid, cm[attr], val)
    return sc


# Exakte ZQ02001-Werte: 0-7 offen, 8-15 Gobo 1, 16-23 Gobo 2, 24-31 Gobo 3,
# 128-255 Gobo-Wechsel (langsam → schnell).
gb_open = mh_gobo("Gobo Offen", 3)
gb_1 = mh_gobo("Gobo 1", 11)
gb_2 = mh_gobo("Gobo 2", 19)
gb_3 = mh_gobo("Gobo 3", 27)
gb_spin = mh_gobo("Gobo Rotation", 190)   # 128-255 = Gobo-Wechsel
mh_gobo_funcs = [gb_open, gb_1, gb_2, gb_3, gb_spin]

# ── MOVING HEADS: Shutter Open / Strobe ─────────────────────────────────────
def mh_shutter(name, shutter_val):
    sc = fm.new_scene(name)
    for fid in mh_fids:
        cm = chan_of[fid]
        for attr, val in (("shutter", shutter_val), ("intensity", 255)):
            if attr in cm:
                sc.set_value(fid, cm[attr], val)
    return sc


sh_open = mh_shutter("Shutter Auf", 4)       # 0-9 = offen
sh_strobe = mh_shutter("Shutter Strobe", 130)  # 10-255 = Strobe
mh_shutter_funcs = [sh_open, sh_strobe]

# ════════════════════════════════════════════════════════════════════════════
#  4) BIBLIOTHEK (Snaps)
# ════════════════════════════════════════════════════════════════════════════
lib.clear()
lib.add_folder("PAR-Farben")
lib.add_folder("MH-Positionen")
for nm, r, g, b, w in [("Rot", 255, 0, 0, 0), ("Gruen", 0, 255, 0, 0),
                       ("Blau", 0, 0, 255, 0), ("Weiss", 0, 0, 0, 255),
                       ("Warm", 255, 130, 40, 60), ("Pink", 255, 0, 120, 0)]:
    values = {fid: {a: v for a, v in (("color_r", r), ("color_g", g),
                                      ("color_b", b), ("color_w", w))
                    if a in chan_of[fid]} for fid in par_fids}
    lib.add_snap(nm, "PAR-Farben", values)
for nm, pan, tilt in [("Center", 128, 128), ("Publikum", 128, 180), ("Hoch", 128, 60)]:
    values = {fid: {a: v for a, v in (("pan", pan), ("tilt", tilt),
                                      ("intensity", 255), ("shutter", 4))
                    if a in chan_of[fid]} for fid in mh_fids}
    lib.add_snap(nm, "MH-Positionen", values)

# ════════════════════════════════════════════════════════════════════════════
#  5) VIRTUAL CONSOLE (APC mini, 5 Seiten)
# ════════════════════════════════════════════════════════════════════════════
PAD, GAP, X0, Y0 = 60, 6, 20, 70
STEP = PAD + GAP
GRID_BOTTOM = Y0 + 8 * STEP
TY = GRID_BOTTOM + 4
Y_FAD = GRID_BOTTOM + 34
FAD_H = 142
widgets: list[dict] = []

BANK_ALL = -1
B_PAR, B_DIMMTX, B_MOVE, B_GOBO, B_POS = 0, 1, 2, 3, 4
PAGE_NAMES = ["PAR-Farben", "Dimmer/Matrix", "MH-Bewegung", "MH Gobo/Farbe", "MH Position"]


def pad_pos(note):
    row, col = note // 8, note % 8
    return X0 + col * STEP, Y0 + (7 - row) * STEP


def _add(w, x, y, ww, hh, bank):
    w.bank = bank
    w.setGeometry(x, y, ww, hh)
    widgets.append(w.to_dict())


def func_btn(fn, note, bank, accent, style="pulse"):
    b = VCButton(fn.name)
    b.action = ButtonAction.FUNCTION_TOGGLE
    b.function_id = fn.id
    b.pad_style = style
    b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, note
    b._bg_color.setNamedColor(accent)
    x, y = pad_pos(note)
    _add(b, x, y, PAD, PAD, bank)


def color_tile(name, note, bank, r, g, b, w=0):
    c = VCColor(name)
    c.color_r, c.color_g, c.color_b, c.color_w = r, g, b, w
    c.with_intensity = False
    c.target = ColorTarget.ALL
    c.midi_type, c.midi_ch, c.midi_data1 = "note_on", 0, note
    x, y = pad_pos(note)
    _add(c, x, y, PAD, PAD, bank)


def fader(caption, col, bank, mode, function_id=None, function_ids=None,
          programmer_attr="intensity", param_key="speed", midi_cc=-1, value=0,
          submaster_slot=None):
    sld = VCSlider(caption)
    sld.mode = mode
    sld.function_id = function_id
    sld.function_ids = list(function_ids or [])
    if submaster_slot is not None:
        sld.function_id = submaster_slot
    sld.programmer_attr = programmer_attr
    sld.param_key = param_key
    sld.midi_cc, sld.midi_ch = midi_cc, 0
    sld._value = value
    x = X0 + col * STEP + 2
    _add(sld, x, Y_FAD, 56, FAD_H, bank)


def label(text, x, y, ww, bank, hh=20, fg="#cfcfcf"):
    _add(VCLabel(text), x, y, ww, hh, bank)


# Universelle Track-Tasten + Master-Fader auf jeder Seite.
for i, (nm, act, col) in enumerate([
        ("Clear", ButtonAction.CLEAR, "#4a3a10"), ("Stop All", ButtonAction.STOP_ALL, "#4a1010"),
        ("Blackout", ButtonAction.BLACKOUT, "#2a0000"), ("Tap", ButtonAction.TAP, "#103a3a")]):
    b = VCButton(nm)
    b.action = act
    b.pad_style = "solid"
    b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, TRACK0 + i
    b._bg_color.setNamedColor(col)
    _add(b, X0 + i * 64, TY, 60, 26, BANK_ALL)

fader("Dimmer", 5, BANK_ALL, SliderMode.SUBMASTER, submaster_slot=0, midi_cc=53, value=255)
fader("Speed", 6, BANK_ALL, SliderMode.SPEED, midi_cc=54, value=64)
fader("Master", 8, BANK_ALL, SliderMode.GRANDMASTER, midi_cc=56, value=255)

for i, nm in enumerate(PAGE_NAMES):
    label(f"Scene {i + 1}: {nm}", X0 + 8 * STEP + 16, Y0 + i * 26, 160, BANK_ALL, hh=22, fg="#7aa0c0")

# ── SEITE 1: PAR-Farben + Looks ─────────────────────────────────────────────
_cols = [("Rot", 255, 0, 0, 0), ("Gruen", 0, 255, 0, 0), ("Blau", 0, 0, 255, 0),
         ("Weiss", 255, 255, 255, 255), ("Amber", 255, 140, 0, 0), ("Cyan", 0, 255, 255, 0),
         ("Magenta", 255, 0, 255, 0), ("Warm", 255, 130, 40, 60)]
for i, (nm, r, g, b, w) in enumerate(_cols):
    color_tile(nm, 56 + i, B_PAR, r, g, b, w)
for i, fn in enumerate([lk_warm, lk_cold, lk_party, lk_white]):
    func_btn(fn, 48 + i, B_PAR, "#264a6a", style="solid")
label("SEITE 1  PAR-FARBEN  -  obere Reihe = Farben (sofort sichtbar), darunter Looks.",
      X0, 28, 1100, B_PAR, fg="#9DFF52")

# ── SEITE 2: PAR Dimmer + Matrix ────────────────────────────────────────────
func_btn(dim_run, 0, B_DIMMTX, "#1f4a28")
func_btn(mx_rainbow, 8, B_DIMMTX, "#7a5b00")
func_btn(mx_chase, 9, B_DIMMTX, "#7a5b00")
fader("FX-Speed", 0, B_DIMMTX, SliderMode.EFFECT_SPEED, function_id=dim_run.id, midi_cc=48, value=64)
fader("Mtx-Mst", 7, B_DIMMTX, SliderMode.EFFECT_INTENSITY,
      function_ids=[mx_rainbow.id, mx_chase.id], midi_cc=55, value=255)
label("SEITE 2  DIMMER & MATRIX (PARs)  -  Pad 1 Lauflicht, oben Matrix (Clear zuerst).",
      X0, 28, 1100, B_DIMMTX, fg="#9DFF52")

# ── SEITE 3: MH-Bewegung (Pan/Tilt-EFX) ─────────────────────────────────────
for i, fn in enumerate(mh_efx_funcs):
    func_btn(fn, i, B_MOVE, "#1f3a6a")
fader("EFX-Speed", 0, B_MOVE, SliderMode.EFFECT_SPEED,
      function_ids=[f.id for f in mh_efx_funcs], midi_cc=48, value=70)
fader("MH-Dimmer", 5, B_MOVE, SliderMode.SUBMASTER, submaster_slot=0, midi_cc=53, value=255)
label("SEITE 3  MH-BEWEGUNG  -  Pad 1 Kreis(Fan), 2 Acht, 3 Sweep gespiegelt, 4 Bounce. "
      "EFX oeffnet Dimmer/Shutter selbst -> Strahler sind sichtbar.", X0, 28, 1100, B_MOVE, fg="#9DFF52")

# ── SEITE 4: MH Gobo + Farbrad ──────────────────────────────────────────────
for i, fn in enumerate(mh_gobo_funcs):
    func_btn(fn, 56 + i, B_GOBO, "#5a3a10", style="solid")
for i, fn in enumerate(mh_color_funcs):
    func_btn(fn, 48 + i, B_GOBO, "#3a2a5a", style="solid")
label("SEITE 4  MH GOBO & FARBE  -  obere Reihe Gobos (offen/1-3/Rotation), darunter Farbrad.",
      X0, 28, 1100, B_GOBO, fg="#9DFF52")

# ── SEITE 5: MH Position + Shutter ──────────────────────────────────────────
for i, fn in enumerate(mh_pos_funcs):
    func_btn(fn, 56 + i, B_POS, "#10503a", style="solid")
for i, fn in enumerate(mh_shutter_funcs):
    func_btn(fn, 48 + i, B_POS, "#503010", style="solid")
label("SEITE 5  MH POSITION & SHUTTER  -  Center/Publikum/Hoch/Cross, dazu Shutter Auf/Strobe.",
      X0, 28, 1100, B_POS, fg="#9DFF52")

state._vc_layout = {"widgets": widgets}

# Executor-Seiten benennen.
pe = getattr(state, "playback_engine", None)
if pe is not None:
    try:
        for idx, nm in enumerate(PAGE_NAMES):
            if 0 <= idx < len(pe.page_names):
                pe.page_names[idx] = nm
        pe.set_page(0)
    except Exception as e:
        print(f"[build] page name error: {e}")

# ── 6) Speichern + Verifikation ─────────────────────────────────────────────
state.programmer = {}
state.show_name = "Moving Head Demo"
save_show(OUT)
print(f"Gespeichert: {OUT}")

ok, msg = load_show(OUT)
print("Load:", ok, msg)

# Verifikation
fixtures2 = state.get_patched_fixtures()
print(f"Patch ({len(fixtures2)}): " +
      ", ".join(f"[{f.fid}]{f.label}@{f.address}({f.channel_count}ch)" for f in fixtures2))
assert len(fixtures2) == 6, "6 Fixtures erwartet"

by = {}
for f in fm.all():
    by.setdefault(f.function_type.value, []).append(f)
print(f"Funktionen gesamt: {len(fm.all())}")
for t, fns in sorted(by.items()):
    print(f"   {t:10} ({len(fns)})")

# EFX auf den Moving Heads vorhanden + Felder erhalten?
from src.core.engine.efx import EfxInstance
efxs = [f for f in fm.all() if isinstance(f, EfxInstance)]
assert len(efxs) == 4, f"4 EFX erwartet, {len(efxs)}"
for e in efxs:
    fids = [fx.fid for fx in e.fixtures]
    assert set(fids) == {mh_left, mh_right}, f"EFX {e.name}: MH-Zuweisung {fids}"
    assert e.open_beam is True, f"EFX {e.name}: open_beam verloren"
print(f"EFX auf MH-Gruppe OK: {[e.name for e in efxs]}")

# Gruppen persistiert?
with state._session() as s:
    groups = s.execute(select(FixtureGroup)).scalars().all()
    gnames = sorted(g.name for g in groups)
assert gnames == ["Moving Heads", "PAR-Reihe"], gnames
print(f"Gruppen persistiert: {gnames}")

vc = state._vc_layout.get("widgets", [])
from collections import Counter
maxy = max((w.get("y", 0) + w.get("h", 0)) for w in vc)
print(f"VC-Widgets: {len(vc)}  Typen={dict(Counter(w['type'] for w in vc))}  Max-Y={maxy}")
print(f"Snaps: {len(lib.snaps())}")
print("FERTIG")
