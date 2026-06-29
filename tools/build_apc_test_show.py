"""KOMPLETTE Test-/Demo-Show fuer Davids reale Hardware:

  * 4x  Generic "Stage Light ZQ01424"  im  8-Kanal-RGBW-Mode
        (Kanaele: 1 Dimmer, 2 Rot, 3 Gruen, 4 Blau, 5 Weiss,
                  6 Strobe/Shutter, 7 Funktion/Makro, 8 Funk.Speed)
        -> Universe 1, Adressen 1 / 9 / 17 / 25
  * Akai APC mini als Hardware-Controller der Virtual Console.

Ziel: ALLE Programmier-Stile einmal anfassbar machen und mischbar:
  Farben, Dimmer-Effekte, RGB-Matrix, fertige Looks, manuelles RGBW-Mischen,
  fixture-eigene Auto-Programme UND ein LIVE-COLOR-CHASE (Farben live anwählen
  -> durch genau diese Farben chasen, mit Speed-/Fade-Fader). Aufgeteilt auf
  6 umschaltbare Seiten (VC-Banks), Umschaltung per APC-Scene-Tasten rechts.

APC-mini-Layout (Original, "APCmini"):
  * 8x8 Pad-Grid           = Notes 0..63 (Note 0 = unten links, 56 = oben links)
  * 9 Fader                = CC 48..56  (F1..F9)
  * 8 Track-Tasten (unten) = Notes 64..71  -> universelle Steuerung
  * 8 Scene-Tasten (rechts)= Notes 82..89  -> Seite 1..8 (page_select, global)
  Hinweis APC mini mk2: dort sind Track-Tasten 100..107 und Scene 112..119.
  Falls Tasten nicht reagieren -> in der App per "MIDI lernen" neu zuweisen,
  oder DEVICE unten auf "mk2" stellen.

GRUNDPRINZIP (Layering): base_levels gibt den PARs Dimmer=255 -> Farbe sofort
sichtbar. Dimmer-Effekte ueberschreiben die Helligkeit (echtes Lauflicht).
Farb-Kacheln setzen nur Farbe. Matrix bringt Farbe selbst mit (-> Clear zuerst).

Aufruf:  venv/Scripts/python.exe tools/build_apc_test_show.py
Erzeugt: shows/APC_Test_Komplett.lshow   (eigenstaendige, in sich saubere Show)
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
from src.core.engine.rgb_matrix import RgbAlgorithm
from src.core.engine.carousel import CarouselPattern
from src.core.engine.snap_library import get_snap_library
from src.core.show.show_file import reset_show, save_show, load_show
from src.ui.virtualconsole.vc_button import VCButton, ButtonAction
from src.ui.virtualconsole.vc_color import VCColor, ColorTarget
from src.ui.virtualconsole.vc_slider import VCSlider, SliderMode
from src.ui.virtualconsole.vc_label import VCLabel

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(_ROOT, "shows", "APC_Test_Komplett.lshow")

# Track-/Scene-Tasten-Notennummern je Geraet (Grid 0-63 + Fader CC48-56 sind gleich).
# Davids Geraet meldet sich als "APC mini mk2" -> Track 100-107, Scene 112-119.
DEVICE = "mk2"              # "original" (APCmini) oder "mk2"
TRACK0 = 64 if DEVICE == "original" else 100     # erste Track-Taste (unten)

# ── 0) KOMPLETT LEERE BASIS (keine Artefakte aus alter Show) ────────────────────
reset_show()
state = get_state()
fm = get_function_manager()
lib = get_snap_library()

# ── 1) PATCH: 4x ZQ01424 (8-Kanal RGBW) ab DMX 1 ────────────────────────────────
PROFILE_ID, MODE = 17, "8-Kanal RGBW"
par_fids: list[int] = []
addr = 1
for i in range(4):
    fid = i + 1
    state.add_fixture(PatchedFixture(
        fid=fid, label=f"PAR {i + 1}", fixture_profile_id=PROFILE_ID, mode_name=MODE,
        universe=1, address=addr, channel_count=8,
        manufacturer_name="Generic", fixture_name="Stage Light ZQ01424",
        fixture_type="color"), undoable=False)
    par_fids.append(fid)
    addr += 8

fixtures = state.get_patched_fixtures()
all_fids = [f.fid for f in fixtures]
chan_of = {f.fid: {c.attribute: c.channel_number
                   for c in get_channels_for_patched(f)} for f in fixtures}

state.base_levels = {fid: {"intensity": 255} for fid in par_fids}
state._rebuild_render_plan()


# ════════════════════════════════════════════════════════════════════════════════
#  2) FUNKTIONEN
# ════════════════════════════════════════════════════════════════════════════════
def dim_step(name, on_fids):
    s = fm.new_scene(name)
    on = set(on_fids)
    for fid in par_fids:
        if "intensity" in chan_of[fid]:
            s.set_value(fid, chan_of[fid]["intensity"], 255 if fid in on else 0)
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

dim_pulse = fm.new_carousel("Pulse")
dim_pulse.pattern = CarouselPattern.PULSE; dim_pulse.fixture_ids = list(par_fids)
dim_pulse.sync_to_beat = False; dim_pulse.speed = 1.0
dim_wave = fm.new_carousel("Wave")
dim_wave.pattern = CarouselPattern.WAVE; dim_wave.fixture_ids = list(par_fids)
dim_wave.sync_to_beat = False; dim_wave.speed = 1.0

dim_full = fm.new_scene("Full (alle an)")
for fid in par_fids:
    if "intensity" in chan_of[fid]:
        dim_full.set_value(fid, chan_of[fid]["intensity"], 255)

speed_targets = [dim_run, dim_pulse, dim_wave, dim_strobe]
dimmer_funcs = [dim_run, dim_rev, dim_ping, dim_pairs, dim_strobe, dim_build, dim_rand, dim_pulse, dim_wave]

# ── Matrix-Effekte ──────────────────────────────────────────────────────────────
group = list(all_fids)


def matrix(name, algo, c1=(255, 0, 0), c2=(0, 0, 255), c3=(0, 255, 0), speed=3.0, params=None):
    m = fm.new_rgb_matrix(name)
    m.algorithm = algo; m.fixture_grid = list(group); m.cols = len(group); m.rows = 1
    m.color1, m.color2, m.color3 = c1, c2, c3; m.matrix_speed = speed
    if params:
        m.params = params
    return m


mx_rainbow = matrix("Mtx Regenbogen", RgbAlgorithm.RAINBOW, speed=1.5)
mx_chase = matrix("Mtx Lauflicht", RgbAlgorithm.CHASE, c1=(255, 255, 255), speed=4.0, params={"axis": "H", "movement": "normal"})
mx_wipe = matrix("Mtx Wipe", RgbAlgorithm.WIPE, c1=(0, 200, 255), c2=(255, 0, 120), speed=1.2)
mx_grad = matrix("Mtx Gradient", RgbAlgorithm.GRADIENT, c1=(255, 0, 0), c2=(0, 255, 0), c3=(0, 0, 255), speed=2.0, params={"axis": "H"})
mx_radar = matrix("Mtx Radar", RgbAlgorithm.RADAR, c1=(255, 160, 0), speed=2.0)
mx_fire = matrix("Mtx Feuer", RgbAlgorithm.FIRE, speed=2.0)
mx_rain = matrix("Mtx Regen", RgbAlgorithm.RAIN, c1=(0, 120, 255), speed=2.5)
mx_spark = matrix("Mtx Sparkle", RgbAlgorithm.RANDOM, c1=(255, 255, 255), speed=6.0, params={"mode": "sparkle", "count": 2, "rate": 3.0})
mx_breathe = matrix("Mtx Atmen", RgbAlgorithm.BREATHE, c1=(180, 0, 255), speed=1.0)
mx_fade = matrix("Mtx Color-Fade", RgbAlgorithm.COLORFADE, speed=1.0)
mx_plasma = matrix("Mtx Plasma", RgbAlgorithm.SINEPLASMA, speed=1.2)
mx_pin = matrix("Mtx Windrad", RgbAlgorithm.PINWHEEL, c1=(255, 0, 0), c2=(0, 0, 255), speed=2.0)
mx_strobe = matrix("Mtx Strobe", RgbAlgorithm.STROBE, c1=(255, 255, 255), speed=8.0)
matrix_funcs = [mx_rainbow, mx_chase, mx_wipe, mx_grad, mx_radar, mx_fire, mx_rain,
                mx_spark, mx_breathe, mx_fade, mx_plasma, mx_pin, mx_strobe]

# ── LIVE COLOR-CHASE: COLORFADE-Matrix, deren Farbliste man LIVE baut ────────────
live_chase = matrix("Live Color-Chase", RgbAlgorithm.COLORFADE, speed=2.0, params={"hold": 0.25})
# Startfarben (per 'Clear Chase' leerbar, dann mit den Pads neu aufbauen):
from src.core.engine.rgb_matrix import ColorSequence
live_chase.colors = ColorSequence([(255, 0, 0), (0, 255, 0), (0, 0, 255)])


# ── Farb-Looks (Farbe + Helligkeit) ─────────────────────────────────────────────
def look(name, r=0, g=0, b=0, w=0, intensity=255):
    s = fm.new_scene(name)
    for fid in all_fids:
        cm = chan_of[fid]
        if "intensity" in cm:
            s.set_value(fid, cm["intensity"], intensity)
        for attr, val in (("color_r", r), ("color_g", g), ("color_b", b), ("color_w", w)):
            if attr in cm:
                s.set_value(fid, cm[attr], val)
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


# ── Fixture-eigene Programme (Shutter/Makro) ────────────────────────────────────
def macro_scene(name, intensity=255, r=0, g=0, b=0, w=0, shutter=0, macro=0, fspeed=0):
    s = fm.new_scene(name)
    for fid in all_fids:
        cm = chan_of[fid]
        for attr, val in (("intensity", intensity), ("color_r", r), ("color_g", g),
                          ("color_b", b), ("color_w", w), ("shutter", shutter),
                          ("macro", macro), ("speed", fspeed)):
            if attr in cm:
                s.set_value(fid, cm[attr], val)
    return s


sc_fstrobe = macro_scene("Fixt-Strobe", r=255, g=255, b=255, shutter=200)
sc_macro = macro_scene("Auto-Programm", macro=200, fspeed=160)


# ════════════════════════════════════════════════════════════════════════════════
#  3) BIBLIOTHEK (Snaps)
# ════════════════════════════════════════════════════════════════════════════════
lib.clear()
lib.add_folder("Farben"); lib.add_folder("Looks")
_COLORS = [("Rot", 255, 0, 0, 0), ("Grün", 0, 255, 0, 0), ("Blau", 0, 0, 255, 0),
           ("Weiß", 0, 0, 0, 255), ("Amber", 255, 140, 0, 0), ("Cyan", 0, 255, 255, 0),
           ("Magenta", 255, 0, 255, 0), ("Warmweiß", 255, 130, 40, 60),
           ("Pink", 255, 0, 120, 0), ("Türkis", 0, 220, 180, 0),
           ("Orange", 255, 80, 0, 0), ("Violett", 140, 0, 255, 0)]
for nm, r, g, b, w in _COLORS:
    values = {fid: {a: v for a, v in (("color_r", r), ("color_g", g), ("color_b", b), ("color_w", w)) if a in chan_of[fid]}
              for fid in all_fids}
    lib.add_snap(nm, "Farben", values)
_look_specs = [("Warm Wash", 255, 120, 20, 120), ("Cold Wash", 0, 60, 255, 80),
               ("Sonnenuntergang", 255, 70, 0, 30), ("Ozean", 0, 120, 255, 0),
               ("Wald", 20, 255, 40, 0), ("Party", 255, 0, 180, 20)]
look_snaps = {}
for nm, r, g, b, w in _look_specs:
    values = {fid: {a: v for a, v in (("intensity", 255), ("color_r", r), ("color_g", g), ("color_b", b), ("color_w", w)) if a in chan_of[fid]}
              for fid in all_fids}
    look_snaps[nm] = lib.add_snap(nm, "Looks", values)


# ════════════════════════════════════════════════════════════════════════════════
#  4) VIRTUAL CONSOLE — kompaktes APC-Layout, 6 Seiten + universelle Steuerung
# ════════════════════════════════════════════════════════════════════════════════
PAD, GAP, X0, Y0 = 60, 6, 20, 70          # kompakt -> alles < 800px (Canvas-Min)
STEP = PAD + GAP
GRID_BOTTOM = Y0 + 8 * STEP                # 598
TY = GRID_BOTTOM + 4                       # Track-Tasten-Reihe
Y_FAD = GRID_BOTTOM + 34                   # Fader direkt darunter, voll sichtbar
FAD_H = 142                                # Fader + Fusszeile bleiben < 800 (Canvas-Min)
widgets: list[dict] = []

BANK_ALL = -1
B_COLOR, B_DIM, B_MTX, B_MIX, B_RGBW, B_CHASE = 0, 1, 2, 3, 4, 5
PAGE_NAMES = ["Farben", "Dimmer", "Matrix", "Mix", "RGBW", "Color-Chase"]


def pad_pos(note):
    row, col = note // 8, note % 8
    return X0 + col * STEP, Y0 + (7 - row) * STEP


def _add(w, x, y, ww, hh, bank):
    w.bank = bank
    w.setGeometry(x, y, ww, hh)
    widgets.append(w.to_dict())


def func_btn(fn, note, bank, accent, style="pulse"):
    b = VCButton(fn.name)
    b.action = ButtonAction.FUNCTION_TOGGLE; b.function_id = fn.id; b.pad_style = style
    b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, note
    b._bg_color.setNamedColor(accent)
    x, y = pad_pos(note); _add(b, x, y, PAD, PAD, bank)


def color_tile(name, note, bank, r, g, b, w=0, target=ColorTarget.ALL, function_id=None):
    c = VCColor(name)
    c.color_r, c.color_g, c.color_b, c.color_w = r, g, b, w
    c.with_intensity = False
    c.target = target
    c.function_id = function_id
    c.midi_type, c.midi_ch, c.midi_data1 = "note_on", 0, note
    x, y = pad_pos(note); _add(c, x, y, PAD, PAD, bank)


def snap_btn(snap, note, bank, accent):
    b = VCButton(snap.name)
    b.action = ButtonAction.LIBRARY_SNAP; b.snap_id = snap.id; b.snap_mode = "toggle"; b.pad_style = "solid"
    b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, note
    b._bg_color.setNamedColor(accent)
    x, y = pad_pos(note); _add(b, x, y, PAD, PAD, bank)


def effect_action_btn(name, note, bank, accent, key, function_id):
    b = VCButton(name)
    b.action = ButtonAction.EFFECT_ACTION; b.effect_action_key = key
    b.function_id = function_id; b.pad_style = "solid"
    b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, note
    b._bg_color.setNamedColor(accent)
    x, y = pad_pos(note); _add(b, x, y, PAD, PAD, bank)


def fader(caption, col, bank, mode, function_id=None, function_ids=None,
          programmer_attr="intensity", param_key="speed", midi_cc=-1, value=0, submaster_slot=None):
    s = VCSlider(caption)
    s.mode = mode; s.function_id = function_id; s.function_ids = list(function_ids or [])
    if submaster_slot is not None:
        s.function_id = submaster_slot
    s.programmer_attr = programmer_attr; s.param_key = param_key
    s.midi_cc, s.midi_ch = midi_cc, 0; s._value = value
    x = X0 + col * STEP + 2; _add(s, x, Y_FAD, 56, FAD_H, bank)


def label(text, x, y, ww, bank, hh=20, fg="#cfcfcf"):
    _add(VCLabel(text), x, y, ww, hh, bank)


# ── Universelle Track-Tasten (Clear/Stop/Blackout/Tap) auf JEDER Seite ──────────
for i, (nm, act, col) in enumerate([
        ("Clear", ButtonAction.CLEAR, "#4a3a10"), ("Stop All", ButtonAction.STOP_ALL, "#4a1010"),
        ("Blackout", ButtonAction.BLACKOUT, "#2a0000"), ("Tap", ButtonAction.TAP, "#103a3a")]):
    b = VCButton(nm); b.action = act; b.pad_style = "solid"
    b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, TRACK0 + i
    b._bg_color.setNamedColor(col)
    _add(b, X0 + i * 64, TY, 60, 26, BANK_ALL)

# ── Universelle Fader: F6 Dimmer, F7 Speed global, F9 Master ────────────────────
fader("Dimmer", 5, BANK_ALL, SliderMode.SUBMASTER, submaster_slot=0, midi_cc=53, value=255)
fader("Speed", 6, BANK_ALL, SliderMode.SPEED, midi_cc=54, value=64)
fader("Master", 8, BANK_ALL, SliderMode.GRANDMASTER, midi_cc=56, value=255)

# ── Controller-Map: Beschriftung wie auf dem APC mini (immer sichtbar) ──────────
label("APC mini  -  8x8 Pad-Grid (Note 0 = unten links).   SCENE-Tasten rechts = "
      "Seite 1-6 wechseln (auf VC + APC).   TRACK-Tasten unten = Clear/Stop/Blackout/Tap.",
      X0, 6, 1150, BANK_ALL, hh=18, fg="#88c0ff")
label("Fader unten = F1-F9 (CC48-56).   F6 Dimmer | F7 Speed global | F9 Master sind "
      "immer aktiv; F1-F5/F8 je nach Seite (siehe Seiten-Text).",
      X0, Y_FAD + FAD_H + 4, 1150, BANK_ALL, hh=18, fg="#88c0ff")
# Scene-Spalte rechts als Mini-Legende (wo am APC die Seiten-Tasten sind)
for i, nm in enumerate(PAGE_NAMES):
    label(f"Scene {i + 1}: {nm}", X0 + 8 * STEP + 16, Y0 + i * 26, 150, BANK_ALL, hh=22, fg="#7aa0c0")


# ── SEITE 1 (Bank 0) — FARBEN & LOOKS ───────────────────────────────────────────
_row7 = [("Rot", 255, 0, 0, 0), ("Grün", 0, 255, 0, 0), ("Blau", 0, 0, 255, 0),
         ("Weiß", 255, 255, 255, 255), ("Amber", 255, 140, 0, 0), ("Cyan", 0, 255, 255, 0),
         ("Magenta", 255, 0, 255, 0), ("Warmweiß", 255, 130, 40, 60)]
for i, (nm, r, g, b, w) in enumerate(_row7):
    color_tile(nm, 56 + i, B_COLOR, r, g, b, w)
_row6 = [("Orange", 255, 80, 0, 0), ("Pink", 255, 0, 120, 0), ("Türkis", 0, 220, 180, 0),
         ("Violett", 140, 0, 255, 0), ("Hellblau", 0, 160, 255, 0), ("Limette", 160, 255, 0, 0),
         ("Rosa", 255, 80, 120, 0), ("Gelb", 255, 220, 0, 0)]
for i, (nm, r, g, b, w) in enumerate(_row6):
    color_tile(nm, 48 + i, B_COLOR, r, g, b, w)
for i, fn in enumerate(look_funcs):
    func_btn(fn, 40 + i, B_COLOR, "#264a6a", style="solid")
for i, (nm, snp) in enumerate(look_snaps.items()):
    snap_btn(snp, 32 + i, B_COLOR, "#3a2a5a")
func_btn(ch_color, 0, B_COLOR, "#3a2150"); func_btn(ch_police, 1, B_COLOR, "#3a2150")
label("SEITE 1  FARBEN & LOOKS  -  oben 2 Reihen Farben (nur Farbe, sofort sichtbar), "
      "darunter Looks + Bibliotheks-Snaps, unten links Farb-Chaser.", X0, 28, 1100, B_COLOR, fg="#9DFF52")

# ── SEITE 2 (Bank 1) — DIMMER-EFFEKTE ───────────────────────────────────────────
for i, fn in enumerate([dim_run, dim_rev, dim_pulse, dim_wave, dim_strobe, dim_build, dim_rand, dim_full]):
    func_btn(fn, i, B_DIM, "#1f4a28")
func_btn(dim_ping, 8, B_DIM, "#1d3d24"); func_btn(dim_pairs, 9, B_DIM, "#1d3d24")
for i, (nm, r, g, b, w) in enumerate(_row7[:6]):
    color_tile(nm, 56 + i, B_DIM, r, g, b, w)
fader("Sp Lauf", 0, B_DIM, SliderMode.EFFECT_SPEED, function_id=dim_run.id, midi_cc=48, value=64)
fader("Sp Pulse", 1, B_DIM, SliderMode.EFFECT_SPEED, function_id=dim_pulse.id, midi_cc=49, value=64)
fader("Sp Wave", 2, B_DIM, SliderMode.EFFECT_SPEED, function_id=dim_wave.id, midi_cc=50, value=64)
fader("Sp Strobe", 3, B_DIM, SliderMode.EFFECT_SPEED, function_id=dim_strobe.id, midi_cc=51, value=90)
fader("FX-Level", 4, B_DIM, SliderMode.EFFECT_INTENSITY, function_ids=[f.id for f in dimmer_funcs], midi_cc=52, value=255)
label("SEITE 2  DIMMER-EFFEKTE  -  ueberschreiben die Grundhelligkeit (echtes Lauflicht). "
      "Farbe oben wählen -> Effekt laeuft in dieser Farbe.   F1-F4 Speed, F5 FX-Level.", X0, 28, 1100, B_DIM, fg="#9DFF52")

# ── SEITE 3 (Bank 2) — MATRIX ───────────────────────────────────────────────────
for i, fn in enumerate(matrix_funcs[:8]):
    func_btn(fn, i, B_MTX, "#7a5b00")
for i, fn in enumerate(matrix_funcs[8:]):
    func_btn(fn, 8 + i, B_MTX, "#6a4f00")
fader("Mtx-Mst", 7, B_MTX, SliderMode.EFFECT_INTENSITY, function_ids=[m.id for m in matrix_funcs], midi_cc=55, value=255)
label("SEITE 3  MATRIX-EFFEKTE  -  bringen ihre Farbe SELBST mit -> vorher 'Clear' drücken! "
      "F8 = Matrix-Master, F7 = Speed global.", X0, 28, 1100, B_MTX, fg="#9DFF52")

# ── SEITE 4 (Bank 3) — MIX ──────────────────────────────────────────────────────
for i, (nm, r, g, b, w) in enumerate(_row7[:6]):
    color_tile(nm, 56 + i, B_MIX, r, g, b, w)
for i, fn in enumerate([dim_run, dim_pulse, dim_wave, dim_strobe]):
    func_btn(fn, i, B_MIX, "#1f4a28")
for i, fn in enumerate([mx_rainbow, mx_chase, mx_fire, mx_radar]):
    func_btn(fn, 16 + i, B_MIX, "#7a5b00")
for i, fn in enumerate(look_funcs[:4]):
    func_btn(fn, 8 + i, B_MIX, "#264a6a", style="solid")
fader("Sp Lauf", 0, B_MIX, SliderMode.EFFECT_SPEED, function_id=dim_run.id, midi_cc=48, value=64)
fader("FX-Level", 4, B_MIX, SliderMode.EFFECT_INTENSITY, function_ids=[f.id for f in dimmer_funcs], midi_cc=52, value=255)
fader("Mtx-Mst", 7, B_MIX, SliderMode.EFFECT_INTENSITY, function_ids=[m.id for m in matrix_funcs], midi_cc=55, value=255)
label("SEITE 4  MIX  -  Farbe (oben) + Dimmer-Effekt (links unten) = farbiges Lauflicht. "
      "Matrix (Clear zuerst) + Dimmer-Effekt = bewegtes Farbmuster mit Helligkeits-Chase.", X0, 28, 1100, B_MIX, fg="#9DFF52")

# ── SEITE 5 (Bank 4) — RGBW VON HAND + FIXTURE-PROGRAMME ─────────────────────────
for i, (nm, r, g, b, w) in enumerate(_row7):
    color_tile(nm, 56 + i, B_RGBW, r, g, b, w)
func_btn(sc_fstrobe, 0, B_RGBW, "#503010", style="solid")
func_btn(sc_macro, 1, B_RGBW, "#503010", style="solid")
func_btn(dim_full, 2, B_RGBW, "#3a3a14", style="solid")
fader("Rot", 0, B_RGBW, SliderMode.PROGRAMMER, programmer_attr="color_r", midi_cc=48, value=0)
fader("Grün", 1, B_RGBW, SliderMode.PROGRAMMER, programmer_attr="color_g", midi_cc=49, value=0)
fader("Blau", 2, B_RGBW, SliderMode.PROGRAMMER, programmer_attr="color_b", midi_cc=50, value=0)
fader("Weiß", 3, B_RGBW, SliderMode.PROGRAMMER, programmer_attr="color_w", midi_cc=51, value=0)
fader("Intens.", 4, B_RGBW, SliderMode.PROGRAMMER, programmer_attr="intensity", midi_cc=52, value=255)
label("SEITE 5  RGBW VON HAND  -  Fader F1-F4 = Rot/Grün/Blau/Weiß, F5 = Intensität "
      "(Programmer). Pad 1 = Fixt-Strobe (Shutter), Pad 2 = Auto-Programm (Makro).", X0, 28, 1100, B_RGBW, fg="#9DFF52")

# ── SEITE 6 (Bank 5) — LIVE COLOR-CHASE (Farben live anwaehlen -> durchchasen) ───
# Farb-Pads im 'Farbe hinzufuegen'-Modus: jeder Druck haengt die Farbe an die
# Sequence des COLORFADE-Effekts 'Live Color-Chase' an.
_chase_colors = [("Rot", 255, 0, 0, 0), ("Orange", 255, 90, 0, 0), ("Gelb", 255, 220, 0, 0),
                 ("Grün", 0, 255, 0, 0), ("Cyan", 0, 255, 255, 0), ("Blau", 0, 0, 255, 0),
                 ("Violett", 140, 0, 255, 0), ("Magenta", 255, 0, 255, 0)]
for i, (nm, r, g, b, w) in enumerate(_chase_colors):
    color_tile(nm, 56 + i, B_CHASE, r, g, b, w, target=ColorTarget.EFFECT_ADD, function_id=live_chase.id)
_chase_colors2 = [("Pink", 255, 0, 120, 0), ("Türkis", 0, 220, 180, 0), ("Limette", 160, 255, 0, 0),
                  ("Warmweiß", 255, 130, 40, 60), ("Weiß", 255, 255, 255, 255)]
for i, (nm, r, g, b, w) in enumerate(_chase_colors2):
    color_tile(nm, 48 + i, B_CHASE, r, g, b, w, target=ColorTarget.EFFECT_ADD, function_id=live_chase.id)
# Steuer-Pads unten: Start/Stop, Clear, naechste/vorige Farbe
func_btn(live_chase, 0, B_CHASE, "#1f6a4a", style="pulse")          # Start/Stop
effect_action_btn("Clear Chase", 1, B_CHASE, "#5a1010", "clear_colors", live_chase.id)
effect_action_btn("Farbe -", 2, B_CHASE, "#333355", "prev_color", live_chase.id)
effect_action_btn("Farbe +", 3, B_CHASE, "#333355", "next_color", live_chase.id)
# Fader: F1 = Speed (Wechselrate), F2 = Uebergang (hold; hoch = haerter/laenger halten)
fader("Speed", 0, B_CHASE, SliderMode.EFFECT_SPEED, function_id=live_chase.id, midi_cc=48, value=70)
fader("Übergang", 1, B_CHASE, SliderMode.EFFECT_PARAM, function_id=live_chase.id, param_key="hold", midi_cc=49, value=64)
label("SEITE 6  LIVE COLOR-CHASE  -  1) 'Clear Chase' (Pad 2) leert die Farbliste  "
      "2) oben Farben antippen = der Reihe nach hinzufügen  3) Pad 1 = Start.", X0, 28, 1100, B_CHASE, fg="#9DFF52")
label("F1 = Speed (wie schnell die Farben wechseln) - F2 = Übergang (0 = weiches Faden, "
      "hoch = Farbe haelt, dann schneller Wechsel). 'Farbe +/-' springt manuell.", X0, 48, 1100, B_CHASE)

state._vc_layout = {"widgets": widgets}

# ── 5) Executor-Seiten benennen ─────────────────────────────────────────────────
pe = getattr(state, "playback_engine", None)
if pe is not None:
    try:
        for idx, nm in enumerate(PAGE_NAMES):
            if 0 <= idx < len(pe.page_names):
                pe.page_names[idx] = nm
        pe.set_page(0)
    except Exception as e:
        print(f"[build] page name error: {e}")

# ── 6) Speichern + Verifikation ─────────────────────────────────────────────────
state.programmer = {}
state.show_name = "APC Test Komplett"
save_show(OUT)
print(f"Gespeichert: {OUT}")

ok, msg = load_show(OUT)
print("Load:", ok, msg)
by = {}
for f in fm.all():
    by.setdefault(f.function_type.value, []).append(f.name)
print(f"Funktionen gesamt: {len(fm.all())}")
for t, names in sorted(by.items()):
    print(f"   {t:10} ({len(names)}): {', '.join(names)}")
print(f"Patch: {[(f.fid, f.label, f.address, f.channel_count) for f in state.get_patched_fixtures()]}")
print(f"Snaps: {len(lib.snaps())}")
vc = state._vc_layout.get("widgets", [])
from collections import Counter
print(f"VC-Widgets: {len(vc)}  Typen={dict(Counter(w['type'] for w in vc))}")
print(f"VC-Bank-Verteilung: {dict(sorted(Counter(w.get('bank') for w in vc).items()))}")
# Max-Y der sichtbaren Elemente (muss < 800 = Canvas-Min sein)
maxy = max((w.get('y', 0) + w.get('h', 0)) for w in vc)
print(f"Max-Y der Widgets: {maxy}  (Canvas-Min-Höhe 800)")
print("FERTIG")
