"""PROFI-MODUS-SHOW — sektioniertes Quadranten-Layout (APC-Probier To-Do #11).

Die APC mini (8x8) wird in vier 4x4-Quadranten aufgeteilt, „einfach für Laien,
beliebig komplex für Profis":

  ┌───────────────┬───────────────┐
  │  FARBEN 4x4   │  EFFEKTE 4x4  │   oben
  │ (Programmer)  │ (exklusiv:    │
  │               │  nur einer)   │
  ├───────────────┼───────────────┤
  │ ATTRIBUTE 4x4 │ SONSTIGES 4x4 │   unten
  │ (aktiver Efx: │ (Clear/Stop/  │
  │  Form/Farbe/  │  Blackout/Tap/│
  │  Richtung…)   │  BPM/Looks)   │
  └───────────────┴───────────────┘

- **Laien:** oben links Farbe tippen + oben rechts Effekt tippen → läuft.
- **Profis:** unten links die Attribute des gerade aktiven Effekts live formen;
  die **Fader unten passen sich automatisch dem aktiven Effekt an** (Speed/Master/
  Parameter wirken auf den zuletzt gestarteten Effekt, function_id=None).

Setup: APC mini mk2 + 4 PAR (ZQ01424) + 2 MH (ZQ02001).
Aufruf:  venv/Scripts/python.exe tools/build_profi_show.py
Erzeugt: shows/Profi_Modus.lshow
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
from src.core.engine.carousel import CarouselPattern
from src.core.engine.efx import EfxFixture, EfxAlgorithm
from src.core.show.show_file import reset_show, save_show, load_show
from src.ui.virtualconsole.vc_button import VCButton, ButtonAction
from src.ui.virtualconsole.vc_color import VCColor, ColorTarget
from src.ui.virtualconsole.vc_slider import VCSlider, SliderMode
from src.ui.virtualconsole.vc_label import VCLabel

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(_ROOT, "shows", "Profi_Modus.lshow")
TRACK0 = 100


def profile_id(short: str) -> int:
    with Session(fdb_engine()) as s:
        pid = s.execute(
            select(FixtureProfile.id).where(FixtureProfile.short_name == short)
        ).scalar_one_or_none()
    if pid is None:
        raise SystemExit(f"Profil '{short}' fehlt — bitte App einmal starten.")
    return int(pid)


# ── 0) Basis + Patch ──────────────────────────────────────────────────────────
reset_show()
state = get_state()
fm = get_function_manager()
PAR_PID = profile_id("ZQ01424")
MH_PID = profile_id("ZQ02001")

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
for fid, lbl, a in ((mh_left, "MH Links", 33), (mh_right, "MH Rechts", 44)):
    state.add_fixture(PatchedFixture(
        fid=fid, label=lbl, fixture_profile_id=MH_PID,
        mode_name="11-Kanal", universe=1, address=a, channel_count=11,
        manufacturer_name="U King", fixture_name="ZQ02001 Mini Moving Head",
        fixture_type="moving_head"), undoable=False)
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
    s.commit()


# ════════════════════════════════════════════════════════════════════════════
#  1) FUNKTIONEN (füllen den Effekte-Quadranten)
# ════════════════════════════════════════════════════════════════════════════
def par_dim(name, on_fids):
    sc = fm.new_scene(name)
    on = set(on_fids)
    for fid in par_fids:
        if "intensity" in chan_of[fid]:
            sc.set_value(fid, chan_of[fid]["intensity"], 255 if fid in on else 0)
    return sc


st = [par_dim(f"Dim P{i+1}", [par_fids[i]]) for i in range(4)]
st_all, st_off = par_dim("Dim alle", par_fids), par_dim("Dim aus", [])
st_odd, st_even = par_dim("Dim 1+3", [1, 3]), par_dim("Dim 2+4", [2, 4])
st_b = [par_dim(f"Build {i+1}", par_fids[:i+1]) for i in range(4)]


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


lk_red, lk_grn, lk_blu = par_look("Rot", r=255), par_look("Grün", g=255), par_look("Blau", b=255)
lk_amb, lk_cya, lk_mag = par_look("Amber", r=255, g=140), par_look("Cyan", g=255, b=255), par_look("Magenta", r=255, b=255)


def chaser(name, step_ids, hold=0.4, fade=0.0, order=RunOrder.Loop, speed=1.0):
    c = fm.new_chaser(name)
    c.run_order, c.direction, c.speed = order, Direction.Forward, speed
    for sid in step_ids:
        c.steps.append(ChaserStep(function_id=sid, fade_in=fade, hold=hold, fade_out=0.0))
    return c


def matrix(name, algo, c1=(255, 0, 0), c2=(0, 0, 255), c3=(0, 255, 0), speed=3.0, params=None):
    m = fm.new_rgb_matrix(name)
    m.algorithm = algo; m.fixture_grid = list(par_fids); m.cols = len(par_fids); m.rows = 1
    m.color1, m.color2, m.color3 = c1, c2, c3; m.matrix_speed = speed
    if params:
        m.params = params
    return m


def mh_efx(name, algo, spread=0.0, mirror=False, direction="forward"):
    e = fm.new_efx(name)
    e.algorithm = algo
    e.fixtures = [EfxFixture(fid=mh_left), EfxFixture(fid=mh_right)]
    e.speed_hz = 0.4; e.spread = spread; e.mirror = mirror; e.direction = direction
    e.open_beam = True; e.width = e.height = 140.0
    return e


# Dimmer-/Helligkeits-Effekte (kombinierbar mit Farbe -> kein clear_programmer)
dim_run = chaser("Lauflicht", [st[0].id, st[1].id, st[2].id, st[3].id], hold=0.35, fade=0.08)
dim_ping = chaser("Ping-Pong", [st[0].id, st[1].id, st[2].id, st[3].id, st[2].id, st[1].id], hold=0.28, fade=0.06)
dim_pairs = chaser("2er-Chase", [st_odd.id, st_even.id], hold=0.4, fade=0.1)
dim_strobe = chaser("Strobe", [st_all.id, st_off.id], hold=0.04)
dim_build = chaser("Build-Up", [st_b[0].id, st_b[1].id, st_b[2].id, st_b[3].id, st_off.id], hold=0.3, fade=0.1)
dim_pulse = fm.new_carousel("Pulse"); dim_pulse.pattern = CarouselPattern.PULSE
dim_pulse.fixture_ids = list(par_fids); dim_pulse.speed = 1.0
dim_wave = fm.new_carousel("Wave"); dim_wave.pattern = CarouselPattern.WAVE
dim_wave.fixture_ids = list(par_fids); dim_wave.speed = 1.0

# Farb-PRODUZIERENDE Effekte (bringen Farbe selbst mit -> clear_programmer)
ch_color = chaser("Color-Chase", [lk_red.id, lk_grn.id, lk_blu.id, lk_amb.id, lk_cya.id, lk_mag.id], hold=0.5, fade=0.25)
mx_rainbow = matrix("Mtx Regenbogen", RgbAlgorithm.RAINBOW, speed=1.5)
mx_fade = matrix("Mtx Color-Fade", RgbAlgorithm.COLORFADE, speed=1.0)
mx_fire = matrix("Mtx Feuer", RgbAlgorithm.FIRE, speed=2.0)
mx_plasma = matrix("Mtx Plasma", RgbAlgorithm.SINEPLASMA, speed=1.2)

# Moving-Head-Effekte
efx_eight = mh_efx("MH Acht", EfxAlgorithm.EIGHT)
efx_circle = mh_efx("MH Kreis", EfxAlgorithm.CIRCLE)
efx_triangle = mh_efx("MH Dreieck", EfxAlgorithm.TRIANGLE)   # echtes Dreieck (Fix 2026-06-12)
efx_random = mh_efx("MH Random", EfxAlgorithm.RANDOM)        # echte Zufallsbahnen im Feld

# Reihenfolge im Effekte-Quadranten (16 Slots, row-major im 4x4).
EFFECTS = [dim_run, dim_ping, dim_pairs, dim_strobe,
           dim_build, dim_pulse, dim_wave, ch_color,
           mx_rainbow, mx_fade, mx_fire, mx_plasma,
           efx_eight, efx_circle, efx_triangle, efx_random]
COLOR_FX_IDS = {ch_color.id, mx_rainbow.id, mx_fade.id, mx_fire.id, mx_plasma.id}

# Looks für den Sonstiges-Quadranten (Schnell-Szenen).
look_warm = par_look("Warmweiß", r=255, g=130, b=40, w=60)
look_white = par_look("Weiß", r=255, g=255, b=255, w=255)


# ════════════════════════════════════════════════════════════════════════════
#  2) VIRTUAL CONSOLE — Quadranten
# ════════════════════════════════════════════════════════════════════════════
PAD, GAP, X0, Y0 = 60, 6, 20, 70
STEP = PAD + GAP
GRID_BOTTOM = Y0 + 8 * STEP
Y_FAD = GRID_BOTTOM + 30
FAD_H = 150
widgets: list[dict] = []
BANK_ALL = -1


def qnote(quadrant: str, qr: int, qc: int) -> int:
    """APC-Note für (Quadrant, Zeile 0..3, Spalte 0..3). Visuell 0 = oben links."""
    r = qr + (4 if quadrant in ("BL", "BR") else 0)
    c = qc + (4 if quadrant in ("TR", "BR") else 0)
    return (7 - r) * 8 + c   # APC: Note-Reihe 0 = unten


def pad_xy(note):
    row, col = note // 8, note % 8
    return X0 + col * STEP, Y0 + (7 - row) * STEP


def _add(w, x, y, ww, hh):
    w.bank = BANK_ALL
    w.setGeometry(x, y, ww, hh)
    widgets.append(w.to_dict())


def color_tile(name, note, r, g, b, w=0):
    c = VCColor(name)
    c.color_r, c.color_g, c.color_b, c.color_w = r, g, b, w
    c.with_intensity = True; c.target = ColorTarget.PROGRAMMER
    c.midi_type, c.midi_ch, c.midi_data1 = "note_on", 0, note
    x, y = pad_xy(note); _add(c, x, y, PAD, PAD)


def fx_tile(fn, note, accent, clear_prog=False):
    b = VCButton(fn.name)
    b.action = ButtonAction.FUNCTION_TOGGLE; b.function_id = fn.id
    b.pad_style = "pulse"; b.exclusive = True; b.clear_programmer = clear_prog
    b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, note
    b._bg_color.setNamedColor(accent)
    x, y = pad_xy(note); _add(b, x, y, PAD, PAD)


def action_tile(name, note, accent, key=None, std_action=None, function_id=None):
    b = VCButton(name)
    if std_action is not None:
        b.action = std_action
    else:
        b.action = ButtonAction.EFFECT_ACTION; b.effect_action_key = key
        b.function_id = function_id     # None = aktiver Effekt
    b.pad_style = "solid"
    b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, note
    b._bg_color.setNamedColor(accent)
    x, y = pad_xy(note); _add(b, x, y, PAD, PAD)


def func_flash(fn, note, accent):
    b = VCButton(fn.name)
    b.action = ButtonAction.FUNCTION_FLASH; b.function_id = fn.id; b.pad_style = "solid"
    b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, note
    b._bg_color.setNamedColor(accent)
    x, y = pad_xy(note); _add(b, x, y, PAD, PAD)


def fader(caption, col, mode, function_ids=None, programmer_attr="intensity",
          programmer_scope="all", programmer_group="", param_key="speed",
          midi_cc=-1, value=0, submaster_slot=None):
    s = VCSlider(caption)
    s.mode = mode; s.function_ids = list(function_ids or [])
    if submaster_slot is not None:
        s.function_id = submaster_slot
    s.programmer_attr = programmer_attr; s.programmer_scope = programmer_scope
    s.programmer_group = programmer_group; s.param_key = param_key
    s.midi_cc, s.midi_ch = midi_cc, 0; s._value = value
    x = X0 + col * STEP + 2; _add(s, x, Y_FAD, 56, FAD_H)


def label(text, x, y, ww, hh=18):
    _add(VCLabel(text), x, y, ww, hh)


# ── Quadrant FARBEN (oben links) — 16 Farb-Kacheln ─────────────────────────
COLORS16 = [
    ("Rot", 255, 0, 0, 0), ("Orange", 255, 90, 0, 0), ("Amber", 255, 160, 0, 0), ("Gelb", 255, 220, 0, 0),
    ("Limette", 160, 255, 0, 0), ("Grün", 0, 255, 0, 0), ("Türkis", 0, 230, 150, 0), ("Cyan", 0, 255, 255, 0),
    ("Hellblau", 0, 140, 255, 0), ("Blau", 0, 0, 255, 0), ("Violett", 140, 0, 255, 0), ("Magenta", 255, 0, 255, 0),
    ("Pink", 255, 0, 120, 0), ("Warmweiß", 255, 130, 40, 60), ("Weiß", 255, 255, 255, 255), ("Aus", 0, 0, 0, 0),
]
for i, (nm, r, g, b, w) in enumerate(COLORS16):
    color_tile(nm, qnote("TL", i // 4, i % 4), r, g, b, w)

# ── Quadrant EFFEKTE (oben rechts) — bis 16 Effekte, exklusiv ──────────────
for i, fn in enumerate(EFFECTS):
    accent = "#7a5b00" if fn.name.startswith("Mtx") else (
        "#1f3a6a" if fn.name.startswith("MH") else (
            "#3a2150" if fn.id in COLOR_FX_IDS else "#1f4a28"))
    fx_tile(fn, qnote("TR", i // 4, i % 4), accent, clear_prog=(fn.id in COLOR_FX_IDS))

# ── Quadrant ATTRIBUTE (unten links) — wirken auf den AKTIVEN Effekt ───────
ATTR = [
    ("Form -", "prev_algorithm", "#5a4a00"), ("Form +", "next_algorithm", "#7a6500"),
    ("Farbe -", "prev_color", "#334"), ("Farbe +", "next_color", "#334"),
    ("Richtung", "reverse_direction", "#353"), ("Bounce", "toggle_bounce", "#353"),
    ("Freeze", "toggle_freeze", "#533"), ("Neustart", "restart", "#530"),
    ("Spiegeln", "toggle_mirror", "#345"), ("Relativ", "toggle_relative", "#356"),
    ("+ Farbe", "add_color", "#243"), ("Farbe an/aus", "toggle_color", "#243"),
    ("Reset Live", "clear_live_override", "#530"), ("Commit", "commit_live", "#1d4d2d"),
    ("Loop", "toggle_loop", "#345"), ("Tap", "tap", "#0a3a3a"),
]
for i, (nm, key, accent) in enumerate(ATTR):
    action_tile(nm, qnote("BL", i // 4, i % 4), accent, key=key, function_id=None)

# ── Quadrant SONSTIGES (unten rechts) — global + Looks ─────────────────────
action_tile("Clear", qnote("BR", 0, 0), "#4a3a10", std_action=ButtonAction.CLEAR)
action_tile("Stop All", qnote("BR", 0, 1), "#4a1010", std_action=ButtonAction.STOP_ALL)
action_tile("Blackout", qnote("BR", 0, 2), "#2a0000", std_action=ButtonAction.BLACKOUT)
action_tile("Tap", qnote("BR", 0, 3), "#103a3a", std_action=ButtonAction.TAP)
action_tile("Musik-BPM", qnote("BR", 1, 0), "#103a4a", std_action=ButtonAction.AUDIO_BPM)
func_flash(dim_strobe, qnote("BR", 1, 1), "#511")
func_flash(look_white, qnote("BR", 1, 2), "#555")
func_flash(look_warm, qnote("BR", 1, 3), "#530")
# untere zwei Reihen des Sonstiges-Quadranten: Schnell-Looks (Toggle-Szenen)
for i, lk in enumerate([lk_red, lk_grn, lk_blu, lk_amb, lk_cya, lk_mag, look_warm, look_white]):
    b = VCButton(lk.name)
    b.action = ButtonAction.FUNCTION_TOGGLE; b.function_id = lk.id; b.pad_style = "solid"
    b.exclusive = False
    note = qnote("BR", 2 + i // 4, i % 4)
    b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, note
    b._bg_color.setNamedColor("#222")
    x, y = pad_xy(note); _add(b, x, y, PAD, PAD)

# ── Fader: passen sich dem AKTIVEN Effekt an (function_ids leer = aktiv) ────
fader("FX-Speed", 0, SliderMode.EFFECT_SPEED, midi_cc=48, value=64)
fader("FX-Master", 1, SliderMode.EFFECT_INTENSITY, midi_cc=49, value=255)
fader("FX-Param", 2, SliderMode.EFFECT_PARAM, param_key="white_amount", midi_cc=50, value=0)
fader("PAR-Dim", 3, SliderMode.PROGRAMMER, programmer_attr="intensity",
      programmer_scope="group", programmer_group="PAR-Reihe", midi_cc=51, value=255)
fader("Dimmer", 5, SliderMode.SUBMASTER, submaster_slot=0, midi_cc=53, value=255)
fader("Speed", 6, SliderMode.SPEED, midi_cc=54, value=64)
fader("Master", 8, SliderMode.GRANDMASTER, midi_cc=56, value=255)

# ── Beschriftung der Quadranten ────────────────────────────────────────────
label("PROFI-MODUS  -  4 Quadranten:  oben-links FARBEN (Programmer)  |  oben-rechts "
      "EFFEKTE (exklusiv, nur einer)  |  unten-links ATTRIBUTE des aktiven Effekts  |  "
      "unten-rechts SONSTIGES.", X0, 6, 1150)
label("Laien: Farbe + Effekt tippen.  Profis: Attribute live formen; die Fader unten "
      "(FX-Speed/Master/Param) wirken auf den zuletzt gestarteten Effekt.",
      X0, 28, 1150)
label("◄ FARBEN", X0 + STEP * 0, 50, 120)
label("EFFEKTE ►", X0 + STEP * 5, 50, 160)
label("◄ ATTRIBUTE (aktiver Effekt)", X0, Y0 + 4 * STEP - 18, 250)
label("SONSTIGES ►", X0 + STEP * 5, Y0 + 4 * STEP - 18, 160)

state._vc_layout = {"widgets": widgets}

# ── 3) Speichern + Verifikation ─────────────────────────────────────────────
state.programmer = {}
state.show_name = "Profi Modus"
save_show(OUT)
print(f"Gespeichert: {OUT}")
ok, msg = load_show(OUT)
print("Load:", ok, msg)
assert ok, f"Show laedt nicht: {msg}"

from collections import Counter
vc = state._vc_layout.get("widgets", [])
types = Counter(w["type"] for w in vc)

# 16 Farb-Kacheln (Programmer)
prog_colors = [w for w in vc if w.get("type") == "VCColor" and w.get("target") == ColorTarget.PROGRAMMER]
assert len(prog_colors) == 16, f"Farben-Quadrant: {len(prog_colors)}"
# Effekte exklusiv
excl = [w for w in vc if w.get("type") == "VCButton" and w.get("action") == "FunctionToggle" and w.get("exclusive")]
assert len(excl) == len(EFFECTS), f"Effekte-Quadrant exklusiv: {len(excl)} != {len(EFFECTS)}"
# Attribute = EFFECT_ACTION auf aktiven Effekt (function_id None)
attr_active = [w for w in vc if w.get("action") == "EffectAction" and w.get("function_id") is None]
assert len(attr_active) == 16, f"Attribute-Quadrant: {len(attr_active)}"
# Kontext-adaptive Fader (EFFECT_* ohne feste Bindung)
adaptive = [w for w in vc if w.get("mode") in ("EffectSpeed", "EffectIntensity", "EffectParam")
            and not w.get("function_ids") and w.get("function_id") is None]
assert len(adaptive) == 3, f"adaptive Fader: {len(adaptive)}"
# #4 Gruppen-Dimmer
grp = [w for w in vc if w.get("mode") == "Programmer" and w.get("programmer_scope") == "group"]
assert len(grp) == 1, "Gruppen-Dimmer fehlt"
maxy = max((w.get("y", 0) + w.get("h", 0)) for w in vc)
assert maxy < 820, f"zu hoch: {maxy}"

print(f"Funktionen: {len(fm.all())}  VC-Widgets: {len(vc)}  Typen={dict(types)}")
print(f"  Farben={len(prog_colors)}  Effekte(exkl)={len(excl)}  Attribute={len(attr_active)}  "
      f"adaptive Fader={len(adaptive)}  Max-Y={maxy}")
print("FERTIG")
