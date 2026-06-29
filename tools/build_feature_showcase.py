"""FEATURE-SHOWCASE — die "alles drin"-Test-/Demo-Show.

Ziel: JEDES programmierbare Feature von LightOS einmal anfassbar machen UND
maschinell verifizieren, dass es sich auch wirklich aufbauen/speichern/laden
laesst. Der Generator baut die Show und prueft am Ende selbst, dass jeder
Enum-Wert (alle Button-Aktionen, Slider-Modi, Color-Targets, Carousel-Pattern
und Matrix-Algorithmen) mindestens einmal verwendet wurde -> faellt etwas
durch, schlaegt der Build fehl.

RIG (Universe 1):
  * 4x  Generic "Stage Light ZQ01424"  (8-Kanal RGBW)  FID 1-4  @ 1 / 9 / 17 / 25
        Kanaele: 1 Dimmer, 2 R, 3 G, 4 B, 5 W, 6 Strobe, 7 Makro, 8 Funk.Speed
  * 2x  Generic "Moving Head Wash RGB 7ch"             FID 5-6  @ 33 / 40
        Kanaele: 1 Pan, 2 Tilt, 3 Dimmer, 4 R, 5 G, 6 B, 7 Strobe
        -> bringt Pan/Tilt, Positionen und CIRCLE/SWEEP-Carousels ins Spiel.
  Die 2 Moving Heads sind OPTIONAL: hast du keine, ignoriere die Mover-Seite —
  der Patch stoert nichts (es sendet nur ins Leere).

Aufruf:  venv/Scripts/python.exe tools/build_feature_showcase.py
Erzeugt: shows/Feature_Showcase.lshow
"""
from __future__ import annotations
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import _gen_env  # noqa: F401  # DEMO-02: spawn-sichere Env-Schalter vor src.core (tools/_gen_env.py)
from PySide6.QtWidgets import QApplication
_app = QApplication.instance() or QApplication([])

from src.core.app_state import get_state, get_channels_for_patched
from src.core.database.models import PatchedFixture
from src.core.engine.function_manager import get_function_manager
from src.core.engine.function import RunOrder, Direction
from src.core.engine.chaser import ChaserStep
from src.core.engine.rgb_matrix import RgbAlgorithm, ColorSequence
from src.core.engine.carousel import CarouselPattern
from src.core.engine.snap_library import get_snap_library
from src.core.engine.palette import get_palette_manager, Palette, PaletteType
from src.core.show.show_file import reset_show, save_show, load_show
from src.ui.virtualconsole.vc_button import VCButton, ButtonAction
from src.ui.virtualconsole.vc_color import VCColor, ColorTarget
from src.ui.virtualconsole.vc_slider import VCSlider, SliderMode
from src.ui.virtualconsole.vc_label import VCLabel

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(_ROOT, "shows", "Feature_Showcase.lshow")

DEVICE = "mk2"                                   # "original" (APCmini) oder "mk2"
TRACK0 = 64 if DEVICE == "original" else 100     # erste Track-Taste (unten)

# ── Coverage-Tracker: jeder benutzte Enum-Wert wird hier vermerkt ───────────────
USED = {"button": set(), "slider": set(), "color": set(), "carousel": set(), "matrix": set()}

# ════════════════════════════════════════════════════════════════════════════════
#  0) KOMPLETT LEERE BASIS
# ════════════════════════════════════════════════════════════════════════════════
reset_show()
state = get_state()
fm = get_function_manager()
lib = get_snap_library()
pm = get_palette_manager()

# ════════════════════════════════════════════════════════════════════════════════
#  1) PATCH
# ════════════════════════════════════════════════════════════════════════════════
PAR_PROFILE, PAR_MODE = 17, "8-Kanal RGBW"        # Stage Light ZQ01424
MH_PROFILE, MH_MODE = 10, "7-Kanal"               # Moving Head Wash RGB 7ch

par_fids: list[int] = []
addr = 1
for i in range(4):
    fid = i + 1
    state.add_fixture(PatchedFixture(
        fid=fid, label=f"PAR {i + 1}", fixture_profile_id=PAR_PROFILE, mode_name=PAR_MODE,
        universe=1, address=addr, channel_count=8,
        manufacturer_name="Generic", fixture_name="Stage Light ZQ01424",
        fixture_type="color"), undoable=False)
    par_fids.append(fid)
    addr += 8

mover_fids: list[int] = []
for i in range(2):
    fid = 5 + i
    state.add_fixture(PatchedFixture(
        fid=fid, label=f"Mover {i + 1}", fixture_profile_id=MH_PROFILE, mode_name=MH_MODE,
        universe=1, address=addr, channel_count=7,
        manufacturer_name="Generic", fixture_name="Moving Head Wash RGB 7ch",
        fixture_type="moving_head"), undoable=False)
    mover_fids.append(fid)
    addr += 7

fixtures = state.get_patched_fixtures()
all_fids = [f.fid for f in fixtures]
rgb_fids = par_fids + mover_fids                  # alle RGB-faehigen Geraete
chan_of = {f.fid: {c.attribute: c.channel_number
                   for c in get_channels_for_patched(f)} for f in fixtures}

# Grundhelligkeit: PARs + Mover Dimmer auf 255 -> Farbe sofort sichtbar.
state.base_levels = {fid: {"intensity": 255} for fid in par_fids + mover_fids}
state._rebuild_render_plan()

# Live-View-2D-Anordnung (Arbeitsflaeche): PARs in einer Reihe, Mover darueber.
state.live_view_positions = {
    1: (0.20, 0.62), 2: (0.40, 0.62), 3: (0.60, 0.62), 4: (0.80, 0.62),
    5: (0.33, 0.28), 6: (0.66, 0.28),
}


def has(fid, attr):
    return attr in chan_of[fid]


def setv(scene, fid, attr, val):
    if has(fid, attr):
        scene.set_value(fid, chan_of[fid][attr], val)


# ════════════════════════════════════════════════════════════════════════════════
#  2) PALETTEN (Farbe / Position / Beam) — erscheinen im Paletten-Panel
# ════════════════════════════════════════════════════════════════════════════════
for nm, r, g, b in [("Rot", 255, 0, 0), ("Blau", 0, 0, 255),
                    ("Amber", 255, 140, 0), ("Magenta", 255, 0, 255)]:
    pm.add(Palette(nm, PaletteType.COLOR, {"color_r": r, "color_g": g, "color_b": b}))
for nm, pan, tilt in [("Center", 128, 128), ("Publikum", 128, 70),
                      ("Boden", 128, 210), ("Weit Links", 40, 128), ("Weit Rechts", 215, 128)]:
    pm.add(Palette(nm, PaletteType.POSITION, {"pan": pan, "tilt": tilt}))
pm.add(Palette("Beam offen", PaletteType.BEAM, {"shutter": 0}))
pm.add(Palette("Beam Strobe", PaletteType.BEAM, {"shutter": 200}))


# ════════════════════════════════════════════════════════════════════════════════
#  3) FUNKTIONEN
# ════════════════════════════════════════════════════════════════════════════════
# ── Dimmer-Schritte (PARs) ──────────────────────────────────────────────────────
def dim_step(name, on_fids):
    s = fm.new_scene(name)
    on = set(on_fids)
    for fid in par_fids:
        setv(s, fid, "intensity", 255 if fid in on else 0)
    return s


st1 = dim_step("Dim P1", [1]); st2 = dim_step("Dim P2", [2])
st3 = dim_step("Dim P3", [3]); st4 = dim_step("Dim P4", [4])
st_all = dim_step("Dim alle", par_fids); st_off = dim_step("Dim aus", [])
st_odd = dim_step("Dim 1+3", [1, 3]); st_even = dim_step("Dim 2+4", [2, 4])
st_b1 = dim_step("Build 1", [1]); st_b2 = dim_step("Build 2", [1, 2])
st_b3 = dim_step("Build 3", [1, 2, 3]); st_b4 = dim_step("Build 4", par_fids)


def chaser(name, step_ids, hold=0.4, fade=0.0, order=RunOrder.Loop,
           direction=Direction.Forward, speed=1.0):
    c = fm.new_chaser(name)
    c.run_order, c.direction, c.speed = order, direction, speed
    for sid in step_ids:
        c.steps.append(ChaserStep(function_id=sid, fade_in=fade, hold=hold, fade_out=0.0))
    return c


dim_run = chaser("Lauflicht >", [st1.id, st2.id, st3.id, st4.id], hold=0.35, fade=0.08)
dim_rev = chaser("Lauflicht <", [st4.id, st3.id, st2.id, st1.id], hold=0.35, fade=0.08)
dim_ping = chaser("Ping-Pong", [st1.id, st2.id, st3.id, st4.id, st3.id, st2.id], hold=0.28, fade=0.06)
dim_pairs = chaser("2er-Chase", [st_odd.id, st_even.id], hold=0.4, fade=0.1)
dim_strobe = chaser("Strobe", [st_all.id, st_off.id], hold=0.04, fade=0.0)
dim_build = chaser("Build-Up", [st_b1.id, st_b2.id, st_b3.id, st_b4.id, st_off.id], hold=0.32, fade=0.1)
dim_rand = chaser("Random", [st1.id, st2.id, st3.id, st4.id, st_all.id], hold=0.3, fade=0.0, order=RunOrder.Random)
chaser_funcs = [dim_run, dim_rev, dim_ping, dim_pairs, dim_strobe, dim_build, dim_rand]

# ── Carousels (EFX): ALLE 5 Pattern ─────────────────────────────────────────────
def carousel(name, pattern, fids, speed=1.0, sync=False, r=255, g=255, b=255):
    c = fm.new_carousel(name)
    c.pattern = pattern; c.fixture_ids = list(fids)
    c.sync_to_beat = sync; c.speed = speed
    c.color_r, c.color_g, c.color_b = r, g, b
    USED["carousel"].add(pattern.value)
    return c


cz_pulse = carousel("Pulse", CarouselPattern.PULSE, par_fids, speed=1.0)
cz_wave = carousel("Wave", CarouselPattern.WAVE, par_fids, speed=1.0)
cz_chase = carousel("EFX-Chase", CarouselPattern.CHASE, par_fids, speed=1.5)
cz_circle = carousel("Mover Kreis", CarouselPattern.CIRCLE, mover_fids, speed=0.6, r=0, g=180, b=255)
cz_sweep = carousel("Mover Sweep", CarouselPattern.SWEEP, mover_fids, speed=0.8, r=255, g=120, b=0)
carousel_funcs = [cz_pulse, cz_wave, cz_chase, cz_circle, cz_sweep]
dimmer_funcs = chaser_funcs + [cz_pulse, cz_wave, cz_chase]

dim_full = fm.new_scene("Full (alle an)")
for fid in par_fids + mover_fids:
    setv(dim_full, fid, "intensity", 255)

# ── RGB-Matrix: ALLE Algorithmen ────────────────────────────────────────────────
def matrix(name, algo, grid=None, cols=None, rows=1, c1=(255, 0, 0), c2=(0, 0, 255),
           c3=(0, 255, 0), speed=2.0, params=None, colors=None):
    g = list(grid if grid is not None else rgb_fids)
    m = fm.new_rgb_matrix(name)
    m.algorithm = algo; m.fixture_grid = g
    m.cols = cols if cols is not None else len(g); m.rows = rows
    m.color1, m.color2, m.color3 = c1, c2, c3; m.matrix_speed = speed
    if params:
        m.params.update(params)
    if colors:
        m.colors = ColorSequence(list(colors))
    USED["matrix"].add(algo.value)
    return m


mx_plain = matrix("Mtx Plain", RgbAlgorithm.PLAIN, c1=(255, 0, 90))
mx_rainbow = matrix("Mtx Regenbogen", RgbAlgorithm.RAINBOW, speed=1.5, params={"spread": 2.0})
mx_chase = matrix("Mtx Lauflicht", RgbAlgorithm.CHASE, c1=(255, 255, 255), speed=4.0, params={"axis": "H", "movement": "normal"})
mx_wipe = matrix("Mtx Wipe", RgbAlgorithm.WIPE, c1=(0, 200, 255), c2=(255, 0, 120), speed=1.2, params={"axis": "H"})
mx_wave = matrix("Mtx Welle", RgbAlgorithm.WAVE, c1=(0, 255, 160), c2=(120, 0, 255), speed=1.4, params={"origin": "left"})
mx_grad = matrix("Mtx Gradient", RgbAlgorithm.GRADIENT, speed=2.0, params={"axis": "H", "blend": "smooth"},
                 colors=[(255, 0, 0), (0, 255, 0), (0, 0, 255)])
mx_fill = matrix("Mtx Fill", RgbAlgorithm.FILL, c1=(255, 200, 0), speed=1.5, params={"level": 70})
mx_rand = matrix("Mtx Sparkle", RgbAlgorithm.RANDOM, c1=(255, 255, 255), speed=6.0,
                 params={"mode": "sparkle", "count": 2, "rate": 3.0})
mx_fade = matrix("Mtx Color-Fade", RgbAlgorithm.COLORFADE, speed=1.0, params={"hold": 0.25},
                 colors=[(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)])
mx_strobe = matrix("Mtx Strobe", RgbAlgorithm.STROBE, c1=(255, 255, 255), speed=8.0)
mx_radar = matrix("Mtx Radar", RgbAlgorithm.RADAR, grid=par_fids, cols=2, rows=2, c1=(255, 160, 0), speed=2.0)
mx_spiral = matrix("Mtx Spirale", RgbAlgorithm.SPIRAL, grid=par_fids, cols=2, rows=2, c1=(255, 0, 200), speed=1.5)
mx_plasma = matrix("Mtx Plasma", RgbAlgorithm.SINEPLASMA, grid=par_fids, cols=2, rows=2, speed=1.2)
mx_pin = matrix("Mtx Windrad", RgbAlgorithm.PINWHEEL, grid=par_fids, cols=2, rows=2, c1=(255, 0, 0), c2=(0, 0, 255), speed=2.0)
mx_breathe = matrix("Mtx Atmen", RgbAlgorithm.BREATHE, c1=(180, 0, 255), speed=1.0)
mx_fire = matrix("Mtx Feuer", RgbAlgorithm.FIRE, speed=2.0)
mx_rain = matrix("Mtx Regen", RgbAlgorithm.RAIN, c1=(0, 120, 255), speed=2.5)
matrix_funcs = [mx_plain, mx_rainbow, mx_chase, mx_wipe, mx_wave, mx_grad, mx_fill, mx_rand,
                mx_fade, mx_strobe, mx_radar, mx_spiral, mx_plasma, mx_pin, mx_breathe, mx_fire, mx_rain]

# ── LIVE COLOR-CHASE: COLORFADE-Matrix mit live wachsender Farbliste ────────────
live_chase = matrix("Live Color-Chase", RgbAlgorithm.COLORFADE, speed=2.0, params={"hold": 0.25},
                    colors=[(255, 0, 0), (0, 255, 0), (0, 0, 255)])


# ── Farb-Looks (Farbe + Helligkeit, alle Geraete) ───────────────────────────────
def look(name, r=0, g=0, b=0, w=0, intensity=255):
    s = fm.new_scene(name)
    for fid in all_fids:
        setv(s, fid, "intensity", intensity)
        setv(s, fid, "color_r", r); setv(s, fid, "color_g", g)
        setv(s, fid, "color_b", b); setv(s, fid, "color_w", w)
    return s


lk_warm = look("Warm Wash", r=255, g=120, b=20, w=120)
lk_cold = look("Cold Wash", r=0, g=60, b=255, w=80)
lk_sunset = look("Sonnenuntergang", r=255, g=70, b=0, w=30)
lk_ocean = look("Ozean", g=120, b=255)
lk_forest = look("Wald", r=20, g=255, b=40)
lk_party = look("Party", r=255, g=0, b=180, w=20)
lk_candle = look("Kerzenlicht", r=255, g=90, b=10, w=40, intensity=160)
lk_white = look("Vollweiß", r=255, g=255, b=255, w=255)
look_funcs = [lk_warm, lk_cold, lk_sunset, lk_ocean, lk_forest, lk_party, lk_candle, lk_white]

lk_red = look("Rot voll", r=255); lk_grn = look("Grün voll", g=255); lk_blu = look("Blau voll", b=255)
lk_amb = look("Amber voll", r=255, g=140); lk_cya = look("Cyan voll", g=255, b=255); lk_mag = look("Magenta voll", r=255, b=255)
ch_color = chaser("Color-Chase", [lk_red.id, lk_grn.id, lk_blu.id, lk_amb.id, lk_cya.id, lk_mag.id], hold=0.55, fade=0.25)
ch_police = chaser("Police", [lk_red.id, lk_blu.id], hold=0.16, fade=0.0)


# ── Positions-Szenen (Mover) ────────────────────────────────────────────────────
def pos_scene(name, pan, tilt, r=255, g=255, b=255):
    s = fm.new_scene(name)
    for fid in mover_fids:
        setv(s, fid, "intensity", 255)
        setv(s, fid, "pan", pan); setv(s, fid, "tilt", tilt)
        setv(s, fid, "color_r", r); setv(s, fid, "color_g", g); setv(s, fid, "color_b", b)
    return s


ps_center = pos_scene("Pos Center", 128, 128, r=255, g=255, b=255)
ps_aud = pos_scene("Pos Publikum", 128, 70, r=255, g=120, b=0)
ps_floor = pos_scene("Pos Boden", 128, 210, r=0, g=120, b=255)
ps_left = pos_scene("Pos Links", 40, 128, r=255, g=0, b=200)
ps_right = pos_scene("Pos Rechts", 215, 128, r=0, g=255, b=120)
pos_funcs = [ps_center, ps_aud, ps_floor, ps_left, ps_right]
pos_chase = chaser("Mover Pos-Chase", [ps_left.id, ps_center.id, ps_right.id, ps_aud.id], hold=0.8, fade=0.4)


# ── Fixture-eigene Programme (Shutter/Makro) ────────────────────────────────────
def macro_scene(name, intensity=255, r=0, g=0, b=0, w=0, shutter=0, macro=0, fspeed=0):
    s = fm.new_scene(name)
    for fid in all_fids:
        setv(s, fid, "intensity", intensity)
        setv(s, fid, "color_r", r); setv(s, fid, "color_g", g)
        setv(s, fid, "color_b", b); setv(s, fid, "color_w", w)
        setv(s, fid, "shutter", shutter); setv(s, fid, "macro", macro); setv(s, fid, "speed", fspeed)
    return s


sc_fstrobe = macro_scene("Fixt-Strobe", r=255, g=255, b=255, shutter=200)
sc_macro = macro_scene("Auto-Programm", macro=200, fspeed=160)


# ════════════════════════════════════════════════════════════════════════════════
#  4) BIBLIOTHEK (Snaps): Farben / Looks / Positionen
# ════════════════════════════════════════════════════════════════════════════════
lib.clear()
lib.add_folder("Farben"); lib.add_folder("Looks"); lib.add_folder("Positionen")
_COLORS = [("Rot", 255, 0, 0, 0), ("Grün", 0, 255, 0, 0), ("Blau", 0, 0, 255, 0),
           ("Weiß", 0, 0, 0, 255), ("Amber", 255, 140, 0, 0), ("Cyan", 0, 255, 255, 0),
           ("Magenta", 255, 0, 255, 0), ("Warmweiß", 255, 130, 40, 60),
           ("Pink", 255, 0, 120, 0), ("Türkis", 0, 220, 180, 0),
           ("Orange", 255, 80, 0, 0), ("Violett", 140, 0, 255, 0)]
for nm, r, g, b, w in _COLORS:
    values = {fid: {a: v for a, v in (("color_r", r), ("color_g", g), ("color_b", b), ("color_w", w)) if has(fid, a)}
              for fid in all_fids}
    lib.add_snap(nm, "Farben", values)
_look_specs = [("Warm Wash", 255, 120, 20, 120), ("Cold Wash", 0, 60, 255, 80),
               ("Sonnenuntergang", 255, 70, 0, 30), ("Ozean", 0, 120, 255, 0),
               ("Wald", 20, 255, 40, 0), ("Party", 255, 0, 180, 20)]
look_snaps = {}
for nm, r, g, b, w in _look_specs:
    values = {fid: {a: v for a, v in (("intensity", 255), ("color_r", r), ("color_g", g), ("color_b", b), ("color_w", w)) if has(fid, a)}
              for fid in all_fids}
    look_snaps[nm] = lib.add_snap(nm, "Looks", values)
_pos_specs = [("Pos Center", 128, 128), ("Pos Publikum", 128, 70), ("Pos Weit", 40, 128)]
for nm, pan, tilt in _pos_specs:
    values = {fid: {a: v for a, v in (("pan", pan), ("tilt", tilt), ("intensity", 255)) if has(fid, a)}
              for fid in mover_fids}
    lib.add_snap(nm, "Positionen", values)


# ════════════════════════════════════════════════════════════════════════════════
#  5) VIRTUAL CONSOLE — 8 Seiten (Banks), APC-maszstaeblich
# ════════════════════════════════════════════════════════════════════════════════
PAD, GAP, X0, Y0 = 60, 6, 20, 70
STEP = PAD + GAP
GRID_BOTTOM = Y0 + 8 * STEP
TY = GRID_BOTTOM + 4
Y_FAD = GRID_BOTTOM + 34
FAD_H = 142
widgets: list[dict] = []

BANK_ALL = -1
(B_COLOR, B_DIM, B_MTXA, B_MTXB, B_MOVER, B_HAND, B_MIX, B_CHASE) = range(8)
PAGE_NAMES = ["Farben", "Dimmer", "Matrix A", "Matrix B", "Mover", "Hand", "Mix", "Chase"]


def pad_pos(note):
    row, col = note // 8, note % 8
    return X0 + col * STEP, Y0 + (7 - row) * STEP


def _add(w, x, y, ww, hh, bank):
    w.bank = bank
    w.setGeometry(x, y, ww, hh)
    widgets.append(w.to_dict())


def func_btn(fn, note, bank, accent, style="pulse", exclusive=False, clear_prog=False, midi=True):
    b = VCButton(fn.name)
    b.action = ButtonAction.FUNCTION_TOGGLE; b.function_id = fn.id; b.pad_style = style
    b.exclusive = exclusive; b.clear_programmer = clear_prog
    if midi:
        b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, note
    b._bg_color.setNamedColor(accent)
    x, y = pad_pos(note); _add(b, x, y, PAD, PAD, bank)
    USED["button"].add(ButtonAction.FUNCTION_TOGGLE.value)


def func_flash_btn(fn, note, bank, accent):
    b = VCButton(fn.name + " (Flash)")
    b.action = ButtonAction.FUNCTION_FLASH; b.function_id = fn.id; b.pad_style = "solid"
    b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, note
    b._bg_color.setNamedColor(accent)
    x, y = pad_pos(note); _add(b, x, y, PAD, PAD, bank)
    USED["button"].add(ButtonAction.FUNCTION_FLASH.value)


def exec_btn(name, note, bank, accent, action, slot=0):
    """TOGGLE / FLASH wirken auf einen Playback-Executor-Slot."""
    b = VCButton(name)
    b.action = action; b.function_id = slot; b.pad_style = "solid"
    b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, note
    b._bg_color.setNamedColor(accent)
    x, y = pad_pos(note); _add(b, x, y, PAD, PAD, bank)
    USED["button"].add(action.value)


def snapshot_btn(name, note, bank, accent, index=0):
    b = VCButton(name)
    b.action = ButtonAction.SNAPSHOT; b.snapshot_index = index; b.pad_style = "solid"
    b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, note
    b._bg_color.setNamedColor(accent)
    x, y = pad_pos(note); _add(b, x, y, PAD, PAD, bank)
    USED["button"].add(ButtonAction.SNAPSHOT.value)


def color_tile(name, note, bank, r, g, b, w=0, target=ColorTarget.ALL, function_id=None, with_intensity=False):
    c = VCColor(name)
    c.color_r, c.color_g, c.color_b, c.color_w = r, g, b, w
    c.with_intensity = with_intensity
    c.target = target
    c.function_id = function_id
    c.midi_type, c.midi_ch, c.midi_data1 = "note_on", 0, note
    x, y = pad_pos(note); _add(c, x, y, PAD, PAD, bank)
    USED["color"].add(target)


def snap_btn(snap, note, bank, accent, mode="toggle"):
    b = VCButton(snap.name)
    b.action = ButtonAction.LIBRARY_SNAP; b.snap_id = snap.id; b.snap_mode = mode; b.pad_style = "solid"
    b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, note
    b._bg_color.setNamedColor(accent)
    x, y = pad_pos(note); _add(b, x, y, PAD, PAD, bank)
    USED["button"].add(ButtonAction.LIBRARY_SNAP.value)


def effect_action_btn(name, note, bank, accent, key, function_id):
    b = VCButton(name)
    b.action = ButtonAction.EFFECT_ACTION; b.effect_action_key = key
    b.function_id = function_id; b.pad_style = "solid"
    b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, note
    b._bg_color.setNamedColor(accent)
    x, y = pad_pos(note); _add(b, x, y, PAD, PAD, bank)
    USED["button"].add(ButtonAction.EFFECT_ACTION.value)


def fader(caption, col, bank, mode, function_id=None, function_ids=None,
          programmer_attr="intensity", param_key="speed", midi_cc=-1, value=0, slot=None):
    s = VCSlider(caption)
    s.mode = mode; s.function_id = function_id; s.function_ids = list(function_ids or [])
    if slot is not None:
        s.function_id = slot
    s.programmer_attr = programmer_attr; s.param_key = param_key
    s.midi_cc, s.midi_ch = midi_cc, 0; s._value = value
    x = X0 + col * STEP + 2; _add(s, x, Y_FAD, 56, FAD_H, bank)
    USED["slider"].add(mode)


def label(text, x, y, ww, bank, hh=20, fg="#cfcfcf"):
    _add(VCLabel(text), x, y, ww, hh, bank)


# ── Universelle Track-Tasten: Clear/Stop/Blackout/Tap + Snapshot ────────────────
for i, (nm, act, col) in enumerate([
        ("Clear", ButtonAction.CLEAR, "#4a3a10"), ("Stop All", ButtonAction.STOP_ALL, "#4a1010"),
        ("Blackout", ButtonAction.BLACKOUT, "#2a0000"), ("Tap", ButtonAction.TAP, "#103a3a")]):
    b = VCButton(nm); b.action = act; b.pad_style = "solid"
    b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, TRACK0 + i
    b._bg_color.setNamedColor(col)
    _add(b, X0 + i * 64, TY, 60, 26, BANK_ALL)
    USED["button"].add(act.value)
# Snapshot-Taste (Track 5) — speichert/ruft einen Snapshot ab (live aufnehmen)
_snap = VCButton("Snapshot"); _snap.action = ButtonAction.SNAPSHOT; _snap.snapshot_index = 0
_snap.pad_style = "solid"; _snap.midi_type, _snap.midi_ch, _snap.midi_data1 = "note_on", 0, TRACK0 + 4
_snap._bg_color.setNamedColor("#2a2a4a")
_add(_snap, X0 + 4 * 64, TY, 60, 26, BANK_ALL)
USED["button"].add(ButtonAction.SNAPSHOT.value)

# ── Universelle Fader: F6 Dimmer, F7 Speed global, F9 Master ────────────────────
fader("Dimmer", 5, BANK_ALL, SliderMode.SUBMASTER, slot=0, midi_cc=53, value=255)
fader("Speed", 6, BANK_ALL, SliderMode.SPEED, midi_cc=54, value=64)
fader("Master", 8, BANK_ALL, SliderMode.GRANDMASTER, midi_cc=56, value=255)

# ── Controller-Map (immer sichtbar) + Scene-Legende rechts ──────────────────────
label("APC mini  -  8x8 Pad-Grid (Note 0 = unten links).   SCENE-Tasten rechts = "
      "Seite 1-8 wechseln.   TRACK-Tasten unten = Clear/Stop/Blackout/Tap/Snapshot.",
      X0, 6, 1150, BANK_ALL, hh=18, fg="#88c0ff")
label("Fader unten = F1-F9 (CC48-56).   F6 Dimmer | F7 Speed global | F9 Master sind "
      "immer aktiv; F1-F5/F8 je nach Seite.", X0, Y_FAD + FAD_H + 4, 1150, BANK_ALL, hh=18, fg="#88c0ff")
for i, nm in enumerate(PAGE_NAMES):
    label(f"Scene {i + 1}: {nm}", X0 + 8 * STEP + 16, Y0 + i * 26, 150, BANK_ALL, hh=22, fg="#7aa0c0")


# ════════════════════════════════════════════════════════════════════════════════
#  SEITE 1 (Bank 0) — FARBEN & LOOKS
# ════════════════════════════════════════════════════════════════════════════════
_row7 = [("Rot", 255, 0, 0, 0), ("Grün", 0, 255, 0, 0), ("Blau", 0, 0, 255, 0),
         ("Weiß", 255, 255, 255, 255), ("Amber", 255, 140, 0, 0), ("Cyan", 0, 255, 255, 0),
         ("Magenta", 255, 0, 255, 0), ("Warmweiß", 255, 130, 40, 60)]
for i, (nm, r, g, b, w) in enumerate(_row7):
    color_tile(nm, 56 + i, B_COLOR, r, g, b, w)                       # ColorTarget.ALL
_row6 = [("Orange", 255, 80, 0, 0), ("Pink", 255, 0, 120, 0), ("Türkis", 0, 220, 180, 0),
         ("Violett", 140, 0, 255, 0), ("Hellblau", 0, 160, 255, 0), ("Limette", 160, 255, 0, 0),
         ("Rosa", 255, 80, 120, 0), ("Gelb", 255, 220, 0, 0)]
for i, (nm, r, g, b, w) in enumerate(_row6):
    color_tile(nm, 48 + i, B_COLOR, r, g, b, w)
for i, fn in enumerate(look_funcs):
    func_btn(fn, 40 + i, B_COLOR, "#264a6a", style="solid")
for i, (nm, snp) in enumerate(look_snaps.items()):
    snap_btn(snp, 32 + i, B_COLOR, "#3a2a5a")
# Untere Reihe: Farb-Chaser + eine "nur in den Programmer"-Farbe (ColorTarget.PROGRAMMER)
func_btn(ch_color, 0, B_COLOR, "#3a2150"); func_btn(ch_police, 1, B_COLOR, "#3a2150")
color_tile("In Programmer", 2, B_COLOR, 255, 120, 0, with_intensity=True, target=ColorTarget.PROGRAMMER)
label("SEITE 1  FARBEN & LOOKS  -  oben Farben (ColorTarget=Alle, nur Farbe), darunter Looks + "
      "Bibliotheks-Snaps, unten Farb-Chaser + 'In Programmer' (ColorTarget=Programmer).",
      X0, 28, 1100, B_COLOR, fg="#9DFF52")

# ════════════════════════════════════════════════════════════════════════════════
#  SEITE 2 (Bank 1) — DIMMER-EFFEKTE & CAROUSELS
# ════════════════════════════════════════════════════════════════════════════════
for i, fn in enumerate([dim_run, dim_rev, cz_pulse, cz_wave, dim_strobe, dim_build, dim_rand, dim_full]):
    func_btn(fn, i, B_DIM, "#1f4a28")
func_btn(dim_ping, 8, B_DIM, "#1d3d24"); func_btn(dim_pairs, 9, B_DIM, "#1d3d24")
func_btn(cz_chase, 10, B_DIM, "#1d3d24")
# FUNCTION_FLASH-Beispiel (nur solange gehalten)
func_flash_btn(dim_strobe, 11, B_DIM, "#3a1d1d")
for i, (nm, r, g, b, w) in enumerate(_row7[:6]):
    color_tile(nm, 56 + i, B_DIM, r, g, b, w)
fader("Sp Lauf", 0, B_DIM, SliderMode.EFFECT_SPEED, function_id=dim_run.id, midi_cc=48, value=64)
fader("Sp Pulse", 1, B_DIM, SliderMode.EFFECT_SPEED, function_id=cz_pulse.id, midi_cc=49, value=64)
fader("Sp Wave", 2, B_DIM, SliderMode.EFFECT_SPEED, function_id=cz_wave.id, midi_cc=50, value=64)
fader("Sp Strobe", 3, B_DIM, SliderMode.EFFECT_SPEED, function_id=dim_strobe.id, midi_cc=51, value=90)
fader("FX-Level", 4, B_DIM, SliderMode.EFFECT_INTENSITY, function_ids=[f.id for f in dimmer_funcs], midi_cc=52, value=255)
label("SEITE 2  DIMMER-EFFEKTE & CAROUSELS  -  Chaser + Pulse/Wave/Chase (EFX). "
      "Pad 12 = FUNCTION_FLASH (nur gehalten).   F1-F4 Speed, F5 FX-Level.",
      X0, 28, 1100, B_DIM, fg="#9DFF52")

# ════════════════════════════════════════════════════════════════════════════════
#  SEITE 3 (Bank 2) — MATRIX A (clear_programmer aktiv -> auto-Clear)
# ════════════════════════════════════════════════════════════════════════════════
_mtx_a = [mx_plain, mx_rainbow, mx_chase, mx_wipe, mx_wave, mx_grad, mx_fill, mx_rand]
for i, fn in enumerate(_mtx_a):
    func_btn(fn, i, B_MTXA, "#7a5b00", clear_prog=True)
_mtx_a2 = [mx_fade, mx_strobe]
for i, fn in enumerate(_mtx_a2):
    func_btn(fn, 8 + i, B_MTXA, "#6a4f00", clear_prog=True)
fader("Mtx-Mst", 7, B_MTXA, SliderMode.EFFECT_INTENSITY, function_ids=[m.id for m in matrix_funcs], midi_cc=55, value=255)
fader("Mtx Spread", 6, B_MTXA, SliderMode.EFFECT_PARAM, function_id=mx_rainbow.id, param_key="saturation", midi_cc=54, value=200)
label("SEITE 3  MATRIX A  -  Plain/Regenbogen/Lauflicht/Wipe/Welle/Gradient/Fill/Sparkle/"
      "Color-Fade/Strobe. Buttons haben clear_programmer -> Farb-Ebene wird automatisch frei.",
      X0, 28, 1100, B_MTXA, fg="#9DFF52")

# ════════════════════════════════════════════════════════════════════════════════
#  SEITE 4 (Bank 3) — MATRIX B (2D-Algos) + EFFEKT-AKTIONEN
# ════════════════════════════════════════════════════════════════════════════════
_mtx_b = [mx_radar, mx_spiral, mx_plasma, mx_pin, mx_breathe, mx_fire, mx_rain]
for i, fn in enumerate(_mtx_b):
    func_btn(fn, i, B_MTXB, "#6a4f00", clear_prog=True)
# Effekt-Aktionen auf die aktuell laufende/gebundene Matrix
effect_action_btn("Bounce", 16, B_MTXB, "#334", "toggle_bounce", mx_chase.id)
effect_action_btn("Reverse", 17, B_MTXB, "#334", "reverse_direction", mx_chase.id)
effect_action_btn("Freeze", 18, B_MTXB, "#433", "toggle_freeze", mx_plasma.id)
effect_action_btn("Live-Reset", 19, B_MTXB, "#343", "clear_live_override", mx_chase.id)
effect_action_btn("Commit Live", 20, B_MTXB, "#345", "commit_live", mx_chase.id)
# EFFECT-Color (setzt die aktive Farbe der gebundenen Matrix-Sequence live)
color_tile("Aktive Farbe", 8, B_MTXB, 0, 255, 255, target=ColorTarget.EFFECT, function_id=mx_fade.id)
fader("Mtx Speed", 7, B_MTXB, SliderMode.EFFECT_SPEED, function_id=mx_plasma.id, midi_cc=55, value=80)
label("SEITE 4  MATRIX B (2D)  -  Radar/Spirale/Plasma/Windrad/Atmen/Feuer/Regen (2x2-Grid). "
      "Reihe 2: EffectAction Bounce/Reverse/Freeze/Live-Reset/Commit + 'Aktive Farbe' (ColorTarget=Effekt).",
      X0, 28, 1100, B_MTXB, fg="#9DFF52")

# ════════════════════════════════════════════════════════════════════════════════
#  SEITE 5 (Bank 4) — MOVER: POSITIONEN, CIRCLE/SWEEP, PAN/TILT
# ════════════════════════════════════════════════════════════════════════════════
for i, fn in enumerate(pos_funcs):
    func_btn(fn, 56 + i, B_MOVER, "#3a2a5a", style="solid", exclusive=False)
func_btn(cz_circle, 0, B_MOVER, "#1f4a5a"); func_btn(cz_sweep, 1, B_MOVER, "#1f4a5a")
func_btn(pos_chase, 2, B_MOVER, "#2a3a5a")
fader("Pan", 0, B_MOVER, SliderMode.PROGRAMMER, programmer_attr="pan", midi_cc=48, value=128)
fader("Tilt", 1, B_MOVER, SliderMode.PROGRAMMER, programmer_attr="tilt", midi_cc=49, value=128)
fader("Sp Kreis", 2, B_MOVER, SliderMode.EFFECT_SPEED, function_id=cz_circle.id, midi_cc=50, value=50)
fader("BPM", 3, B_MOVER, SliderMode.BPM, midi_cc=51, value=120)
label("SEITE 5  MOVER  -  oben 5 Positions-Szenen, unten links Kreis/Sweep (Carousel CIRCLE/SWEEP) "
      "+ Pos-Chase.   F1 Pan, F2 Tilt (Programmer), F3 Kreis-Speed, F4 BPM (Tap-Tempo).",
      X0, 28, 1100, B_MOVER, fg="#9DFF52")

# ════════════════════════════════════════════════════════════════════════════════
#  SEITE 6 (Bank 5) — RGBW + PAN/TILT VON HAND, FIXTURE-PROGRAMME
# ════════════════════════════════════════════════════════════════════════════════
for i, (nm, r, g, b, w) in enumerate(_row7):
    color_tile(nm, 56 + i, B_HAND, r, g, b, w)
func_btn(sc_fstrobe, 0, B_HAND, "#503010", style="solid")
func_btn(sc_macro, 1, B_HAND, "#503010", style="solid")
func_btn(dim_full, 2, B_HAND, "#3a3a14", style="solid")
fader("Rot", 0, B_HAND, SliderMode.PROGRAMMER, programmer_attr="color_r", midi_cc=48, value=0)
fader("Grün", 1, B_HAND, SliderMode.PROGRAMMER, programmer_attr="color_g", midi_cc=49, value=0)
fader("Blau", 2, B_HAND, SliderMode.PROGRAMMER, programmer_attr="color_b", midi_cc=50, value=0)
fader("Weiß", 3, B_HAND, SliderMode.PROGRAMMER, programmer_attr="color_w", midi_cc=51, value=0)
fader("Level", 4, B_HAND, SliderMode.LEVEL, midi_cc=52, value=255)
label("SEITE 6  HAND  -  Fader F1-F4 = Rot/Grün/Blau/Weiß (Programmer), F5 = Level. "
      "Pad 1 Fixt-Strobe (Shutter), Pad 2 Auto-Programm (Makro), Pad 3 Full.",
      X0, 28, 1100, B_HAND, fg="#9DFF52")

# ════════════════════════════════════════════════════════════════════════════════
#  SEITE 7 (Bank 6) — MIX & PLAYBACK
# ════════════════════════════════════════════════════════════════════════════════
for i, (nm, r, g, b, w) in enumerate(_row7[:6]):
    color_tile(nm, 56 + i, B_MIX, r, g, b, w)
for i, fn in enumerate([dim_run, cz_pulse, cz_wave, dim_strobe]):
    func_btn(fn, i, B_MIX, "#1f4a28")
for i, fn in enumerate([mx_rainbow, mx_chase, mx_fire, mx_radar]):
    func_btn(fn, 16 + i, B_MIX, "#7a5b00", clear_prog=True)
for i, fn in enumerate(look_funcs[:4]):
    func_btn(fn, 8 + i, B_MIX, "#264a6a", style="solid")
# Playback-Executoren (Slot 0/1): TOGGLE = Go, FLASH = Flash, PLAYBACK-Fader = Pegel
exec_btn("Exec Go", 24, B_MIX, "#244", ButtonAction.TOGGLE, slot=0)
exec_btn("Exec Flash", 25, B_MIX, "#242", ButtonAction.FLASH, slot=0)
snapshot_btn("Snapshot 1", 26, B_MIX, "#224", index=0)
fader("Sp Lauf", 0, B_MIX, SliderMode.EFFECT_SPEED, function_id=dim_run.id, midi_cc=48, value=64)
fader("FX-Level", 4, B_MIX, SliderMode.EFFECT_INTENSITY, function_ids=[f.id for f in dimmer_funcs], midi_cc=52, value=255)
fader("Mtx-Mst", 7, B_MIX, SliderMode.EFFECT_INTENSITY, function_ids=[m.id for m in matrix_funcs], midi_cc=55, value=255)
fader("Playback", 3, B_MIX, SliderMode.PLAYBACK, slot=0, midi_cc=51, value=200)
label("SEITE 7  MIX & PLAYBACK  -  Farbe + Dimmer-/Matrix-Effekt frei kombinieren. "
      "Reihe 3: Exec Go (TOGGLE) / Exec Flash (FLASH) / Snapshot.   F4 = Playback-Fader (Slot 0).",
      X0, 28, 1100, B_MIX, fg="#9DFF52")

# ════════════════════════════════════════════════════════════════════════════════
#  SEITE 8 (Bank 7) — LIVE COLOR-CHASE
# ════════════════════════════════════════════════════════════════════════════════
_chase_colors = [("Rot", 255, 0, 0, 0), ("Orange", 255, 90, 0, 0), ("Gelb", 255, 220, 0, 0),
                 ("Grün", 0, 255, 0, 0), ("Cyan", 0, 255, 255, 0), ("Blau", 0, 0, 255, 0),
                 ("Violett", 140, 0, 255, 0), ("Magenta", 255, 0, 255, 0)]
for i, (nm, r, g, b, w) in enumerate(_chase_colors):
    color_tile(nm, 56 + i, B_CHASE, r, g, b, w, target=ColorTarget.EFFECT_ADD, function_id=live_chase.id)
_chase_colors2 = [("Pink", 255, 0, 120, 0), ("Türkis", 0, 220, 180, 0), ("Limette", 160, 255, 0, 0),
                  ("Warmweiß", 255, 130, 40, 60), ("Weiß", 255, 255, 255, 255)]
for i, (nm, r, g, b, w) in enumerate(_chase_colors2):
    color_tile(nm, 48 + i, B_CHASE, r, g, b, w, target=ColorTarget.EFFECT_ADD, function_id=live_chase.id)
func_btn(live_chase, 0, B_CHASE, "#1f6a4a", style="pulse")
effect_action_btn("Clear Chase", 1, B_CHASE, "#5a1010", "clear_colors", live_chase.id)
effect_action_btn("Farbe -", 2, B_CHASE, "#333355", "prev_color", live_chase.id)
effect_action_btn("Farbe +", 3, B_CHASE, "#333355", "next_color", live_chase.id)
effect_action_btn("Letzte weg", 4, B_CHASE, "#553311", "remove_color", live_chase.id)
fader("Speed", 0, B_CHASE, SliderMode.EFFECT_SPEED, function_id=live_chase.id, midi_cc=48, value=70)
fader("Übergang", 1, B_CHASE, SliderMode.EFFECT_PARAM, function_id=live_chase.id, param_key="hold", midi_cc=49, value=64)
label("SEITE 8  LIVE COLOR-CHASE  -  1) 'Clear Chase' leert die Liste  2) oben Farben antippen "
      "(ColorTarget=Effekt-Hinzufügen)  3) Pad 1 Start.   F1 Speed, F2 Übergang (hold).",
      X0, 28, 1100, B_CHASE, fg="#9DFF52")

state._vc_layout = {"widgets": widgets}

# Executor-Seiten benennen (falls Playback-Engine laeuft)
pe = getattr(state, "playback_engine", None)
if pe is not None:
    try:
        for idx, nm in enumerate(PAGE_NAMES):
            if 0 <= idx < len(pe.page_names):
                pe.page_names[idx] = nm
        pe.set_page(0)
    except Exception as e:
        print(f"[build] page name error: {e}")


# ════════════════════════════════════════════════════════════════════════════════
#  6) SPEICHERN + VERIFIKATION (inkl. Feature-Coverage-Check)
# ════════════════════════════════════════════════════════════════════════════════
state.programmer = {}
state.show_name = "Feature Showcase"
save_show(OUT)
print(f"Gespeichert: {OUT}")

ok, msg = load_show(OUT)
print("Load:", ok, msg)

by = {}
for f in fm.all():
    by.setdefault(f.function_type.value, []).append(f.name)
print(f"\nFunktionen gesamt: {len(fm.all())}")
for t, names in sorted(by.items()):
    print(f"   {t:10} ({len(names)}): {', '.join(names)}")
print(f"Patch: {[(f.fid, f.label, f.address, f.channel_count) for f in state.get_patched_fixtures()]}")
print(f"Snaps: {len(lib.snaps())}   Paletten: {len(pm.get_all())}")
vc = state._vc_layout.get("widgets", [])
from collections import Counter
print(f"VC-Widgets: {len(vc)}  Typen={dict(Counter(w['type'] for w in vc))}")
print(f"VC-Bank-Verteilung: {dict(sorted(Counter(w.get('bank') for w in vc).items()))}")
maxy = max((w.get('y', 0) + w.get('h', 0)) for w in vc)
print(f"Max-Y der Widgets: {maxy}  (Canvas-Min-Höhe 800)")

# ── Feature-Coverage: jeder Enum-Wert MUSS verwendet worden sein ────────────────
print("\n=== FEATURE-COVERAGE ===")
EXPECTED = {
    "button": {a.value for a in ButtonAction},
    "slider": {getattr(SliderMode, k) for k in dir(SliderMode) if k.isupper()},
    "color": {getattr(ColorTarget, k) for k in dir(ColorTarget) if k.isupper()},
    "carousel": {p.value for p in CarouselPattern},
    "matrix": {a.value for a in RgbAlgorithm},
}
all_ok = True
for cat, expected in EXPECTED.items():
    missing = expected - USED[cat]
    status = "OK " if not missing else "FEHLT"
    if missing:
        all_ok = False
    print(f"  [{status}] {cat:9}: {len(USED[cat])}/{len(expected)} genutzt"
          + (f"   -> NICHT abgedeckt: {sorted(missing)}" if missing else ""))

assert ok, f"Show konnte nicht wieder geladen werden: {msg}"
assert all_ok, "Nicht alle Features wurden abgedeckt — siehe oben."
print("\nFERTIG — alle Features programmierbar, Show gespeichert & wieder geladen.")
