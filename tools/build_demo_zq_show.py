"""Demo-/Bühnen-Show fuer Davids reale Hardware (DMO-01, Masterplan 2026-06-08):

  * 4x  U King "ZQ01424"  im 8-Kanal-RGBW-Mode (PAR/Strahler)
        Kanaele: 1 Dimmer, 2 R, 3 G, 4 B, 5 W, 6 Strobe, 7 Makro, 8 Funk.Speed
        -> Universe 1, Adressen 1 / 9 / 17 / 25
  * 2x  U King "ZQ02001"  im 11-Kanal-Mode (Mini Moving Head)
        Kanaele: 1 Pan, 2 Pan-fein, 3 Tilt, 4 Tilt-fein, 5 Farbrad, 6 Gobo,
                 7 Dimmer, 8 Strobe, 9 Pan/Tilt-Speed, 10 Auto/Sound, 11 Reset
        -> Universe 1, Adressen 33 / 44

Zeigt: Farben + Looks (PAR), Dimmer-Lauflicht, RGB-Matrix (4 PARs als 4x1),
Moving-Head-Positionen/Beam + Sweep-Chaser, einen Speed-Dial (Multiplikator),
zwei VC-Frames (PARs / Moving Heads) und einen Multi-Action-Button ("Showtime").

Aufruf:  venv/Scripts/python.exe tools/build_demo_zq_show.py
Erzeugt: shows/Demo_ZQ_Buehne.lshow
"""
from __future__ import annotations
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
_app = QApplication.instance() or QApplication([])

from src.core.app_state import get_state, get_channels_for_patched
from src.core.database.models import PatchedFixture
from src.core.engine.function_manager import get_function_manager
from src.core.engine.function import RunOrder, Direction
from src.core.engine.chaser import ChaserStep
from src.core.engine.rgb_matrix import RgbAlgorithm
from src.core.show.show_file import reset_show, save_show, load_show
from src.ui.virtualconsole.vc_button import VCButton, ButtonAction
from src.ui.virtualconsole.vc_color import VCColor, ColorTarget
from src.ui.virtualconsole.vc_slider import VCSlider, SliderMode
from src.ui.virtualconsole.vc_speedial import VCSpeedDial, SpeedTarget
from src.ui.virtualconsole.vc_frame import VCFrame
from src.ui.virtualconsole.vc_label import VCLabel

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(_ROOT, "shows", "Demo_ZQ_Buehne.lshow")

# ── 0) Leere Basis ──────────────────────────────────────────────────────────────
reset_show()
state = get_state()
fm = get_function_manager()

# ── 1) PATCH ────────────────────────────────────────────────────────────────────
PAR_PROFILE, PAR_MODE = 17, "8-Kanal RGBW"
MH_PROFILE, MH_MODE = 18, "11-Kanal"

par_fids: list[int] = []
addr = 1
for i in range(4):
    fid = i + 1
    state.add_fixture(PatchedFixture(
        fid=fid, label=f"PAR {i + 1}", fixture_profile_id=PAR_PROFILE, mode_name=PAR_MODE,
        universe=1, address=addr, channel_count=8,
        manufacturer_name="U King", fixture_name="Stage Light ZQ01424",
        fixture_type="color"), undoable=False)
    par_fids.append(fid)
    addr += 8

mh_fids: list[int] = []
for i in range(2):
    fid = 5 + i
    state.add_fixture(PatchedFixture(
        fid=fid, label=f"Moving Head {i + 1}", fixture_profile_id=MH_PROFILE, mode_name=MH_MODE,
        universe=1, address=addr, channel_count=11,
        manufacturer_name="U King", fixture_name="ZQ02001 Mini Moving Head",
        fixture_type="moving_head"), undoable=False)
    mh_fids.append(fid)
    addr += 11

fixtures = state.get_patched_fixtures()
chan_of = {f.fid: {c.attribute: c.channel_number
                   for c in get_channels_for_patched(f)} for f in fixtures}

# PARs: Grundhelligkeit an (Farbe sofort sichtbar). Moving Heads: zentriert, dunkel.
state.base_levels = {fid: {"intensity": 255} for fid in par_fids}
for fid in mh_fids:
    state.base_levels[fid] = {"pan": 128, "tilt": 128, "intensity": 0}
state._rebuild_render_plan()


# ── 2) FUNKTIONEN — PARs ─────────────────────────────────────────────────────────
def par_look(name, r=0, g=0, b=0, w=0, intensity=255):
    s = fm.new_scene(name)
    for fid in par_fids:
        cm = chan_of[fid]
        if "intensity" in cm:
            s.set_value(fid, cm["intensity"], intensity)
        for attr, val in (("color_r", r), ("color_g", g), ("color_b", b), ("color_w", w)):
            if attr in cm:
                s.set_value(fid, cm[attr], val)
    return s


lk_warm = par_look("Warm Wash", r=255, g=120, b=20, w=120)
lk_cold = par_look("Cold Wash", r=0, g=60, b=255, w=80)
lk_red = par_look("Rot", r=255)
lk_grn = par_look("Gruen", g=255)
lk_blu = par_look("Blau", b=255)
lk_white = par_look("Weiss", r=255, g=255, b=255, w=255)


def par_dim_step(name, on_fids):
    s = fm.new_scene(name)
    on = set(on_fids)
    for fid in par_fids:
        if "intensity" in chan_of[fid]:
            s.set_value(fid, chan_of[fid]["intensity"], 255 if fid in on else 0)
    return s


_d1 = par_dim_step("Dim P1", [1]); _d2 = par_dim_step("Dim P2", [2])
_d3 = par_dim_step("Dim P3", [3]); _d4 = par_dim_step("Dim P4", [4])

dim_run = fm.new_chaser("PAR Lauflicht")
dim_run.run_order, dim_run.direction, dim_run.speed = RunOrder.Loop, Direction.Forward, 1.0
for sid in (_d1.id, _d2.id, _d3.id, _d4.id):
    dim_run.steps.append(ChaserStep(function_id=sid, fade_in=0.08, hold=0.35, fade_out=0.0))

# RGB-Matrix auf den 4 PARs (4x1)
mx_rainbow = fm.new_rgb_matrix("PAR Matrix Regenbogen")
mx_rainbow.algorithm = RgbAlgorithm.RAINBOW
mx_rainbow.fixture_grid = list(par_fids); mx_rainbow.cols = 4; mx_rainbow.rows = 1
mx_rainbow.matrix_speed = 1.5

mx_chase = fm.new_rgb_matrix("PAR Matrix Lauflicht")
mx_chase.algorithm = RgbAlgorithm.CHASE
mx_chase.fixture_grid = list(par_fids); mx_chase.cols = 4; mx_chase.rows = 1
mx_chase.color1 = (255, 255, 255); mx_chase.matrix_speed = 3.0
mx_chase.params = {"axis": "H", "movement": "normal", "color_cycle": True, "color_interval": 2}


# ── 2b) FUNKTIONEN — Moving Heads ────────────────────────────────────────────────
def mh_scene(name, pan=None, tilt=None, intensity=None, color_wheel=None,
             gobo_wheel=None, shutter=None):
    s = fm.new_scene(name)
    spec = (("pan", pan), ("tilt", tilt), ("intensity", intensity),
            ("color_wheel", color_wheel), ("gobo_wheel", gobo_wheel), ("shutter", shutter))
    for fid in mh_fids:
        cm = chan_of[fid]
        for attr, val in spec:
            if val is not None and attr in cm:
                s.set_value(fid, cm[attr], val)
    return s


mh_center = mh_scene("MH Mitte", pan=128, tilt=110, intensity=255, color_wheel=0, gobo_wheel=0)
mh_left = mh_scene("MH Links", pan=70, tilt=110, intensity=255)
mh_right = mh_scene("MH Rechts", pan=186, tilt=110, intensity=255)
mh_up = mh_scene("MH Hoch", pan=128, tilt=60, intensity=255)
mh_color = mh_scene("MH Farbe", color_wheel=36, intensity=255)
mh_gobo = mh_scene("MH Gobo", gobo_wheel=40, intensity=255)
mh_beam = mh_scene("MH Beam offen", intensity=255, color_wheel=0, gobo_wheel=0)

mh_sweep = fm.new_chaser("MH Sweep")
mh_sweep.run_order, mh_sweep.direction, mh_sweep.speed = RunOrder.PingPong, Direction.Forward, 1.0
for sid in (mh_left.id, mh_center.id, mh_right.id, mh_up.id):
    mh_sweep.steps.append(ChaserStep(function_id=sid, fade_in=0.5, hold=0.6, fade_out=0.0))


# ════════════════════════════════════════════════════════════════════════════════
#  3) VIRTUAL CONSOLE — zwei Frames (PARs / Moving Heads) + Speed-Dial + Fader
# ════════════════════════════════════════════════════════════════════════════════
widgets: list[dict] = []


def _add(w, x, y, ww, hh):
    w.setGeometry(int(x), int(y), int(ww), int(hh))
    widgets.append(w.to_dict())


def _mk_func_btn(fn, accent="#264a6a"):
    b = VCButton(fn.name)
    b.action = ButtonAction.FUNCTION_TOGGLE
    b.function_id = fn.id
    b._bg_color.setNamedColor(accent)
    return b


def _mk_color_tile(name, r, g, b, w=0):
    c = VCColor(name)
    c.color_r, c.color_g, c.color_b, c.color_w = r, g, b, w
    c.with_intensity = False
    c.target = ColorTarget.ALL
    return c


def make_frame(caption, x, y, w, h, children):
    """Erzeugt einen VCFrame mit Kind-Widgets (FRM-Demo). children = Liste von
    (widget, breite, hoehe)."""
    fr = VCFrame(caption)
    fr.setGeometry(int(x), int(y), int(w), int(h))
    cx, cy = 8, fr._tab_height + 8
    rowh = 0
    for child, cw, ch in children:
        if cx + cw > w - 6:
            cx = 8
            cy += rowh + 6
            rowh = 0
        child.setParent(fr)
        child.setProperty("vc_page", 0)
        child.setGeometry(cx, cy, cw, ch)
        cx += cw + 6
        rowh = max(rowh, ch)
    widgets.append(fr.to_dict())


# Frame 1: PARs (Farben + Dimmer-Lauflicht + Matrix)
par_children = []
for nm, r, g, b, w in [("Rot", 255, 0, 0, 0), ("Gruen", 0, 255, 0, 0), ("Blau", 0, 0, 255, 0),
                       ("Weiss", 255, 255, 255, 255)]:
    par_children.append((_mk_color_tile(nm, r, g, b, w), 70, 50))
par_children.append((_mk_func_btn(lk_warm, "#264a6a"), 70, 44))
par_children.append((_mk_func_btn(lk_cold, "#264a6a"), 70, 44))
par_children.append((_mk_func_btn(dim_run, "#1f4a28"), 96, 44))
par_children.append((_mk_func_btn(mx_rainbow, "#7a5b00"), 110, 44))
par_children.append((_mk_func_btn(mx_chase, "#7a5b00"), 110, 44))
make_frame("PARs (ZQ01424)", 20, 70, 320, 260, par_children)

# Frame 2: Moving Heads (Positionen + Beam + Sweep + Farbe/Gobo)
mh_children = []
for fn, col in [(mh_center, "#26406a"), (mh_left, "#26406a"), (mh_right, "#26406a"),
                (mh_up, "#26406a"), (mh_beam, "#3a3a14"), (mh_color, "#5a2a5a"),
                (mh_gobo, "#2a5a5a"), (mh_sweep, "#1f4a28")]:
    mh_children.append((_mk_func_btn(fn, col), 96, 44))
make_frame("Moving Heads (ZQ02001)", 360, 70, 330, 260, mh_children)

# Multi-Action-Button "Showtime": startet Matrix + MH-Sweep + Dimmer-Lauflicht
show_btn = VCButton("▶ Showtime")
show_btn.action = ButtonAction.FUNCTION_TOGGLE
show_btn.function_id = mx_rainbow.id
show_btn.actions = [
    {"type": "function", "function_id": mh_sweep.id, "mode": "on"},
    {"type": "function", "function_id": dim_run.id, "mode": "on"},
]
show_btn._bg_color.setNamedColor("#6a1f5a")
_add(show_btn, 20, 350, 140, 54)

# Speed-Dial (Multiplikator) auf den MH-Sweep
dial = VCSpeedDial("MH Speed")
dial.target_mode = SpeedTarget.FUNCTION
dial.function_id = mh_sweep.id
dial.function_ids = [dim_run.id]      # wirkt zusaetzlich auf das PAR-Lauflicht
dial.multiplier_mode = True
dial._mult = 1.0
_add(dial, 180, 350, 120, 140)

# Fader: Master, Dimmer-Submaster, Matrix-Intensitaet
f_master = VCSlider("Master"); f_master.mode = SliderMode.GRANDMASTER; f_master._value = 255
_add(f_master, 320, 350, 56, 140)
f_dim = VCSlider("Dimmer"); f_dim.mode = SliderMode.SUBMASTER; f_dim.function_id = 0; f_dim._value = 255
_add(f_dim, 384, 350, 56, 140)
f_mtx = VCSlider("Matrix")
f_mtx.mode = SliderMode.EFFECT_INTENSITY
f_mtx.function_ids = [mx_rainbow.id, mx_chase.id]; f_mtx._value = 255
_add(f_mtx, 448, 350, 56, 140)

# Universelle Tasten
b_clear = VCButton("Clear"); b_clear.action = ButtonAction.CLEAR; b_clear._bg_color.setNamedColor("#4a3a10")
_add(b_clear, 520, 350, 80, 26)
b_black = VCButton("Blackout"); b_black.action = ButtonAction.BLACKOUT; b_black._bg_color.setNamedColor("#2a0000")
_add(b_black, 520, 382, 80, 26)
b_stop = VCButton("Stop All"); b_stop.action = ButtonAction.STOP_ALL; b_stop._bg_color.setNamedColor("#4a1010")
_add(b_stop, 520, 414, 80, 26)

_add(VCLabel("Demo-Show: 4x ZQ01424 (PAR) + 2x ZQ02001 (Moving Head). Frames gruppieren "
             "die Geraete; ▶ Showtime startet Matrix + MH-Sweep + Lauflicht; MH-Speed-Dial "
             "im Multiplikator-Modus."), 20, 40, 980, 22)

state._vc_layout = {"widgets": widgets}

# ── 4) Speichern + Verifikation ─────────────────────────────────────────────────
state.programmer = {}
state.show_name = "Demo ZQ Buehne"
save_show(OUT)
print(f"Gespeichert: {OUT}")

ok, msg = load_show(OUT)
print("Load:", ok, msg)
print(f"Funktionen: {len(fm.all())}")
print(f"Patch: {[(f.fid, f.label, f.address, f.channel_count) for f in state.get_patched_fixtures()]}")
vc = state._vc_layout.get("widgets", [])
from collections import Counter
print(f"VC-Widgets: {len(vc)}  Typen={dict(Counter(w['type'] for w in vc))}")
# Frames muessen Kinder enthalten
frames = [w for w in vc if w["type"] == "VCFrame"]
for fr in frames:
    print(f"   Frame '{fr.get('caption')}': {len(fr.get('children', []))} Kinder")
# Multi-Action + Speed-Dial-Multiplikator pruefen
sb = [w for w in vc if w.get("caption") == "▶ Showtime"]
print(f"Showtime actions: {len(sb[0].get('actions', [])) if sb else 'FEHLT'}")
sd = [w for w in vc if w["type"] == "VCSpeedDial"]
print(f"Speed-Dial multiplier_mode: {sd[0].get('multiplier_mode') if sd else 'FEHLT'}")
print("FERTIG")
