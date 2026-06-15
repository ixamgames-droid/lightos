"""APC-PROBIER-SHOW — Testfeld fuer Davids reales Setup (4 PAR + 2 MH + APC mini).

Ziel: ausprobieren, ob sich die Befehle so auf dem APC bauen lassen, wie wir uns
das mit der UI vorstellen — und wo es noch hakt (-> docs/APC_PROBIER.md, Abschnitt
"Offene Punkte"). Bewusst nur 4 Banks, jede mit EINEM klaren Test-Schwerpunkt:

  Bank 1  ALLE EFFEKTE   Alle Effekte hintereinander auf die Pads gelegt
                         (Farben oben, darunter Dimmer-FX, Matrix, MH-EFX) —
                         Ueberblick: "geht jeder Effekt einzeln per Pad?".
  Bank 2  EFX + FADER    Weniger Effekte, dafuer unten die Fader, mit denen man
                         die PARs (Strahler) live anpasst: R/G/B/W + PAR-Dim +
                         FX-Level. Test: "Effekt laeuft, Strahler per Fader formen".
  Bank 3  CHASE BUILDER  Live einen Farb-Chase bauen: oben Farben antippen ->
                         haengen der Reihe nach an, Pad-Aktionen Clear/Farbe±/
                         Richtung/Bounce/Freeze/Commit, Fader Speed/Uebergang.
  Bank 4  MATRIX BUILDER Matrix-Algorithmen aus der "Bibliothek" antippen
                         (exklusiv) + live formen: Speed/Master/Parameter-Fader,
                         Live-Farbe (Color-Fade), Freeze/Richtung/Reset/Commit.

Universell auf JEDER Seite:
  * Track-Tasten unten: Clear / Stop All / Blackout / Tap / Musik-BPM
  * Fader F6 Dimmer (Submaster) | F7 Speed global | F9 Grand Master

Aufruf:  venv/Scripts/python.exe tools/build_apc_probier_show.py
Erzeugt: shows/APC_Probier.lshow
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
from src.core.engine.rgb_matrix import RgbAlgorithm, ColorSequence
from src.core.engine.carousel import CarouselPattern
from src.core.engine.efx import EfxFixture, EfxAlgorithm
from src.core.engine.snap_library import get_snap_library
from src.core.show.show_file import reset_show, save_show, load_show
from src.ui.virtualconsole.vc_button import VCButton, ButtonAction
from src.ui.virtualconsole.vc_color import VCColor, ColorTarget
from src.ui.virtualconsole.vc_slider import VCSlider, SliderMode
from src.ui.virtualconsole.vc_label import VCLabel
from src.ui.virtualconsole.vc_color_list import VCColorList
from src.ui.virtualconsole.vc_chase_builder import VCChaseBuilder

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(_ROOT, "shows", "APC_Probier.lshow")

DEVICE = "mk2"                       # Davids APC mini meldet sich als mk2
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
chan_of = {f.fid: {c.attribute: c.channel_number
                   for c in get_channels_for_patched(f)} for f in fixtures}

# PARs "scharf": Grundhelligkeit -> Farbe sofort sichtbar.
state.base_levels = {fid: {"intensity": 255} for fid in par_fids}
state._rebuild_render_plan()

# ── 2) GRUPPEN (persistiert in der .lshow) ──────────────────────────────────
with state._session() as s:
    s.execute(delete(FixtureGroup))
    s.add(FixtureGroup(name="PAR-Reihe", cols=4, rows=1,
                       positions_json=json.dumps({f"{i},0": par_fids[i] for i in range(4)})))
    s.add(FixtureGroup(name="Moving Heads", cols=2, rows=1,
                       positions_json=json.dumps({"0,0": mh_left, "1,0": mh_right})))
    s.commit()


# ════════════════════════════════════════════════════════════════════════════
#  3) FUNKTIONEN
# ════════════════════════════════════════════════════════════════════════════

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


# Farb-Looks (Farbe) fuer den Color-Chase.
lk_red = par_look("Rot voll", r=255)
lk_grn = par_look("Gruen voll", g=255)
lk_blu = par_look("Blau voll", b=255)
lk_amb = par_look("Amber voll", r=255, g=140)
lk_cya = par_look("Cyan voll", g=255, b=255)
lk_mag = par_look("Magenta voll", r=255, b=255)


# ── PAR: Dimmer-Szenen + Chaser ─────────────────────────────────────────────
def par_dim(name, on_fids):
    sc = fm.new_scene(name)
    on = set(on_fids)
    for fid in par_fids:
        if "intensity" in chan_of[fid]:
            sc.set_value(fid, chan_of[fid]["intensity"], 255 if fid in on else 0)
    return sc


st1 = par_dim("Dim P1", [1]); st2 = par_dim("Dim P2", [2])
st3 = par_dim("Dim P3", [3]); st4 = par_dim("Dim P4", [4])
st_all = par_dim("Dim alle", par_fids); st_off = par_dim("Dim aus", [])
st_odd = par_dim("Dim 1+3", [1, 3]); st_even = par_dim("Dim 2+4", [2, 4])
st_b1 = par_dim("Build 1", [1]); st_b2 = par_dim("Build 2", [1, 2])
st_b3 = par_dim("Build 3", [1, 2, 3]); st_b4 = par_dim("Build 4", par_fids)


def chaser(name, step_ids, hold=0.4, fade=0.0, order=RunOrder.Loop, speed=1.0):
    c = fm.new_chaser(name)
    c.run_order, c.direction, c.speed = order, Direction.Forward, speed
    for sid in step_ids:
        c.steps.append(ChaserStep(function_id=sid, fade_in=fade, hold=hold, fade_out=0.0))
    return c


dim_run = chaser("Lauflicht >", [st1.id, st2.id, st3.id, st4.id], hold=0.35, fade=0.08)
dim_rev = chaser("Lauflicht <", [st4.id, st3.id, st2.id, st1.id], hold=0.35, fade=0.08)
dim_ping = chaser("Ping-Pong", [st1.id, st2.id, st3.id, st4.id, st3.id, st2.id], hold=0.28, fade=0.06)
dim_pairs = chaser("2er-Chase", [st_odd.id, st_even.id], hold=0.4, fade=0.1)
dim_strobe = chaser("Strobe", [st_all.id, st_off.id], hold=0.04, fade=0.0)
dim_build = chaser("Build-Up", [st_b1.id, st_b2.id, st_b3.id, st_b4.id, st_off.id], hold=0.32, fade=0.1)

dim_pulse = fm.new_carousel("Pulse")
dim_pulse.pattern = CarouselPattern.PULSE; dim_pulse.fixture_ids = list(par_fids)
dim_pulse.sync_to_beat = False; dim_pulse.speed = 1.0
dim_wave = fm.new_carousel("Wave")
dim_wave.pattern = CarouselPattern.WAVE; dim_wave.fixture_ids = list(par_fids)
dim_wave.sync_to_beat = False; dim_wave.speed = 1.0

dim_funcs = [dim_run, dim_rev, dim_ping, dim_pairs, dim_strobe, dim_build, dim_pulse, dim_wave]

ch_color = chaser("Color-Chase", [lk_red.id, lk_grn.id, lk_blu.id, lk_amb.id,
                                  lk_cya.id, lk_mag.id], hold=0.55, fade=0.25)
ch_police = chaser("Police", [lk_red.id, lk_blu.id], hold=0.16)


# ── PAR: RGB-Matrix (auf der PAR-Reihe) ─────────────────────────────────────
def matrix(name, algo, c1=(255, 0, 0), c2=(0, 0, 255), c3=(0, 255, 0), speed=3.0, params=None):
    m = fm.new_rgb_matrix(name)
    m.algorithm = algo; m.fixture_grid = list(par_fids); m.cols = len(par_fids); m.rows = 1
    m.color1, m.color2, m.color3 = c1, c2, c3; m.matrix_speed = speed
    if params:
        m.params = params
    return m


mx_rainbow = matrix("Mtx Regenbogen", RgbAlgorithm.RAINBOW, speed=1.5)
mx_chase = matrix("Mtx Lauflicht", RgbAlgorithm.CHASE, c1=(255, 255, 255), speed=4.0,
                  params={"axis": "H", "movement": "normal"})
mx_wipe = matrix("Mtx Wipe", RgbAlgorithm.WIPE, c1=(0, 200, 255), c2=(255, 0, 120), speed=1.2)
mx_grad = matrix("Mtx Gradient", RgbAlgorithm.GRADIENT, speed=2.0, params={"axis": "H"})
mx_radar = matrix("Mtx Radar", RgbAlgorithm.RADAR, c1=(255, 160, 0), speed=2.0)
mx_fire = matrix("Mtx Feuer", RgbAlgorithm.FIRE, speed=2.0)
mx_rain = matrix("Mtx Regen", RgbAlgorithm.RAIN, c1=(0, 120, 255), speed=2.5)
mx_breathe = matrix("Mtx Atmen", RgbAlgorithm.BREATHE, c1=(180, 0, 255), speed=1.0)
mx_fade = matrix("Mtx Color-Fade", RgbAlgorithm.COLORFADE, speed=1.0)
mx_plasma = matrix("Mtx Plasma", RgbAlgorithm.SINEPLASMA, speed=1.2)
mx_pin = matrix("Mtx Windrad", RgbAlgorithm.PINWHEEL, speed=2.0)
mx_strobe = matrix("Mtx Strobe", RgbAlgorithm.STROBE, c1=(255, 255, 255), speed=8.0)
matrix_funcs = [mx_rainbow, mx_chase, mx_wipe, mx_grad, mx_radar, mx_fire, mx_rain,
                mx_breathe, mx_fade, mx_plasma, mx_pin, mx_strobe]

# Farb-PRODUZIERENDE Effekte: bringen ihre Farbe selbst mit -> beim Start den
# Programmer leeren, sonst bleibt eine vorher gewaehlte Farbe (Programmer = LTP)
# als Rest stehen und mischt sich dazu (z. B. Police -> Lila statt reinem Blau,
# weil der blaue Step color_r=0 setzt = Default, also NICHT effekt-geschuetzt).
# Dimmer-/Intensitaets-Effekte (Lauflicht, Pulse, Wave...) bleiben dagegen
# bewusst kombinierbar: Farbe waehlen + Dimmer-FX = farbiges Lauflicht.
COLOR_FX_IDS = {ch_color.id, ch_police.id} | {m.id for m in matrix_funcs}


# ── CHASE BUILDER: Color-Fade-Matrix, deren Farbliste man LIVE per Pad baut ──
chase_builder = matrix("Chase-Builder", RgbAlgorithm.COLORFADE, speed=2.0, params={"hold": 0.2})
chase_builder.colors = ColorSequence([(255, 0, 0), (0, 255, 0), (0, 0, 255)])

# ── MATRIX BUILDER: EINE Matrix, durch deren Algorithmen man live blaettert ──
# Loest To-Do #3/#5 ab: statt 12 Algorithmus-Pads gibt es genau EINE Matrix mit
# "Form -/+"-Pads (next_algorithm/prev_algorithm) und Live-Recolor-Kacheln, die
# wahlweise die aktive Sequence-Farbe (EFFECT) oder die festen color1/2/3
# (EFFECT_C1/C2/C3) setzen — letztere greifen auch bei Feuer/Plasma/Windrad.
matrix_builder = matrix("Matrix-Builder", RgbAlgorithm.CHASE, speed=3.0,
                        params={"axis": "H", "movement": "normal"})
matrix_builder.colors = ColorSequence([(255, 0, 0), (0, 0, 255), (0, 255, 0)])


# ── MOVING HEADS: Pan/Tilt-EFX ──────────────────────────────────────────────
def mh_efx(name, algo, speed_hz=0.35, spread=1.0, mirror=False,
           direction="forward", width=170.0, height=150.0):
    e = fm.new_efx(name)
    e.algorithm = algo
    e.fixtures = [EfxFixture(fid=mh_left), EfxFixture(fid=mh_right)]
    e.speed_hz = speed_hz; e.spread = spread; e.mirror = mirror
    e.direction = direction
    e.open_beam = True
    e.width, e.height = width, height
    e.x_offset, e.y_offset = 128.0, 128.0
    return e


efx_circle = mh_efx("MH Kreis", EfxAlgorithm.CIRCLE, spread=0.0)
efx_eight = mh_efx("MH Acht", EfxAlgorithm.EIGHT, spread=0.0)
efx_sweep = mh_efx("MH Sweep gespiegelt", EfxAlgorithm.LINE, spread=0.0, mirror=True)
efx_bounce = mh_efx("MH Bounce", EfxAlgorithm.LINE, direction="bounce", spread=0.0)
mh_efx_funcs = [efx_circle, efx_eight, efx_sweep, efx_bounce]


# ── MOVING HEADS: Szenen (Position / Farbrad / Gobo) — fuer die Uebersicht ──
def mh_scene(name, **attrs):
    sc = fm.new_scene(name)
    for fid in mh_fids:
        cm = chan_of[fid]
        for attr, val in attrs.items():
            if attr in cm:
                sc.set_value(fid, cm[attr], val)
    return sc


pos_center = mh_scene("Pos Center", pan=128, tilt=128, intensity=255, shutter=4)
pos_aud = mh_scene("Pos Publikum", pan=128, tilt=180, intensity=255, shutter=4)
cw_red = mh_scene("MH Rot", color_wheel=14, intensity=255, shutter=4)
cw_blue = mh_scene("MH Blau", color_wheel=34, intensity=255, shutter=4)
gb_spin = mh_scene("Gobo-Wechsel", gobo_wheel=190, intensity=255, shutter=4)
mh_scene_funcs = [pos_center, pos_aud, cw_red, cw_blue, gb_spin]


# ════════════════════════════════════════════════════════════════════════════
#  4) VIRTUAL CONSOLE — APC mini, 4 Banks
# ════════════════════════════════════════════════════════════════════════════
PAD, GAP, X0, Y0 = 60, 6, 20, 70
STEP = PAD + GAP
GRID_BOTTOM = Y0 + 8 * STEP
TY = GRID_BOTTOM + 4
Y_FAD = GRID_BOTTOM + 34
FAD_H = 142
widgets: list[dict] = []

BANK_ALL = -1
B_ALL, B_FADER, B_CHASE, B_MATRIX = range(4)
PAGE_NAMES = ["Alle Effekte", "Effekte + Fader", "Chase Builder", "Matrix Builder"]


def pad_pos(note):
    row, col = note // 8, note % 8
    return X0 + col * STEP, Y0 + (7 - row) * STEP


def slot_note(s: int) -> int:
    """Visueller Slot 0 = oben links, dann zeilenweise nach unten -> APC-Note."""
    r, c = s // 8, s % 8
    return (7 - r) * 8 + c


def _add(w, x, y, ww, hh, bank):
    w.bank = bank
    w.setGeometry(x, y, ww, hh)
    widgets.append(w.to_dict())


def func_btn(fn, note, bank, accent, style="pulse", flash=False,
             exclusive=False, clear_prog=False):
    b = VCButton(fn.name)
    b.action = ButtonAction.FUNCTION_FLASH if flash else ButtonAction.FUNCTION_TOGGLE
    b.function_id = fn.id
    b.pad_style = style
    b.exclusive = exclusive
    b.clear_programmer = clear_prog
    b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, note
    b._bg_color.setNamedColor(accent)
    x, y = pad_pos(note); _add(b, x, y, PAD, PAD, bank)


def action_btn(name, action, note, bank, accent):
    b = VCButton(name)
    b.action = action; b.pad_style = "solid"
    b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, note
    b._bg_color.setNamedColor(accent)
    x, y = pad_pos(note); _add(b, x, y, PAD, PAD, bank)


def color_tile(name, note, bank, r, g, b, w=0, target=ColorTarget.ALL,
               function_id=None, with_intensity=False):
    c = VCColor(name)
    c.color_r, c.color_g, c.color_b, c.color_w = r, g, b, w
    c.with_intensity = with_intensity
    c.target = target
    c.function_id = function_id
    c.midi_type, c.midi_ch, c.midi_data1 = "note_on", 0, note
    x, y = pad_pos(note); _add(c, x, y, PAD, PAD, bank)


def effect_action_btn(name, note, bank, accent, key, function_id):
    b = VCButton(name)
    b.action = ButtonAction.EFFECT_ACTION; b.effect_action_key = key
    b.function_id = function_id; b.pad_style = "solid"
    b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, note
    b._bg_color.setNamedColor(accent)
    x, y = pad_pos(note); _add(b, x, y, PAD, PAD, bank)


def fader(caption, col, bank, mode, function_id=None, function_ids=None,
          programmer_attr="intensity", programmer_scope="all", programmer_group="",
          param_key="speed", midi_cc=-1, value=0, submaster_slot=None):
    s = VCSlider(caption)
    s.mode = mode; s.function_id = function_id; s.function_ids = list(function_ids or [])
    if submaster_slot is not None:
        s.function_id = submaster_slot
    s.programmer_attr = programmer_attr; s.programmer_scope = programmer_scope
    s.programmer_group = programmer_group
    s.param_key = param_key
    s.midi_cc, s.midi_ch = midi_cc, 0; s._value = value
    x = X0 + col * STEP + 2; _add(s, x, Y_FAD, 56, FAD_H, bank)


def label(text, x, y, ww, bank, hh=20, fg="#cfcfcf"):
    lab = VCLabel(text)
    _add(lab, x, y, ww, hh, bank)


def color_list(name, x, y, ww, hh, bank, function_id):
    """To-Do #6: Live-Feedback-Fenster der gebauten Farbliste eines Effekts."""
    cl = VCColorList(name)
    cl.function_id = function_id
    _add(cl, x, y, ww, hh, bank)


def chase_builder_widget(name, x, y, ww, hh, bank, function_id):
    """To-Do #1: All-in-One-Builder (Palette + Liste + Aktionen + Speed/Hold)."""
    cb = VCChaseBuilder(name)
    cb.function_id = function_id
    _add(cb, x, y, ww, hh, bank)


# ── Universell: Track-Tasten (auf JEDER Seite) ──────────────────────────────
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

# Universelle Fader: F6 Dimmer, F7 Speed global, F9 Grand Master.
fader("Dimmer", 5, BANK_ALL, SliderMode.SUBMASTER, submaster_slot=0, midi_cc=53, value=255)
fader("Speed", 6, BANK_ALL, SliderMode.SPEED, midi_cc=54, value=64)
fader("Master", 8, BANK_ALL, SliderMode.GRANDMASTER, midi_cc=56, value=255)

label("APC mini  -  8x8 Pads (Note 0 = unten links).  SCENE-Tasten rechts = Seite 1-4. "
      "TRACK-Tasten unten = Clear/Stop/Blackout/Tap/Musik-BPM (ueberall aktiv).",
      X0, 6, 1150, BANK_ALL, hh=18, fg="#88c0ff")
label("Fader F1-F9 = CC48-56.  F6 Dimmer | F7 Speed global | F9 Master immer aktiv, "
      "F1-F5/F8 je nach Seite.", X0, Y_FAD + FAD_H + 4, 1150, BANK_ALL, hh=18, fg="#88c0ff")
for i, nm in enumerate(PAGE_NAMES):
    label(f"Scene {i + 1}: {nm}", X0 + 8 * STEP + 16, Y0 + i * 26, 180, BANK_ALL, hh=22, fg="#7aa0c0")


# ── BANK 1 — ALLE EFFEKTE (alles hintereinander) ────────────────────────────
COLORS8 = [("Rot", 255, 0, 0, 0), ("Gruen", 0, 255, 0, 0), ("Blau", 0, 0, 255, 0),
           ("Weiss", 255, 255, 255, 255), ("Amber", 255, 140, 0, 0), ("Cyan", 0, 255, 255, 0),
           ("Magenta", 255, 0, 255, 0), ("Warmweiss", 255, 130, 40, 60)]
# Slots 0-7: Farben (nur Farbe -> sofort sichtbar, Effekt darunter modelliert Helligkeit)
for s, (nm, r, g, b, w) in enumerate(COLORS8):
    color_tile(nm, slot_note(s), B_ALL, r, g, b, w)
# Ab Slot 8: einfach alle Effekte der Reihe nach.
_all_fx = (
    [(fn, "#1f4a28") for fn in dim_funcs] +          # Dimmer-FX (8)
    [(ch_color, "#3a2150"), (ch_police, "#3a2150")] +  # Farb-Chaser (2)
    [(fn, "#7a5b00") for fn in matrix_funcs] +        # Matrix (12)
    [(fn, "#1f3a6a") for fn in mh_efx_funcs] +        # MH-EFX (4)
    [(fn, "#3a2a5a") for fn in mh_scene_funcs]        # MH-Szenen (5)
)
for i, (fn, accent) in enumerate(_all_fx):
    func_btn(fn, slot_note(8 + i), B_ALL, accent,
             style="solid" if accent == "#3a2a5a" else "pulse",
             clear_prog=(fn.id in COLOR_FX_IDS))
label("SEITE 1  ALLE EFFEKTE  -  Reihe 1 Farben (fuer Dimmer-FX: erst Farbe waehlen). "
      "Farb-Chaser/Police/Matrix bringen Farbe selbst mit + leeren den Programmer.",
      X0, 28, 1100, B_ALL, fg="#9DFF52")


# ── BANK 2 — EFFEKTE + PAR-FADER ────────────────────────────────────────────
for s, (nm, r, g, b, w) in enumerate(COLORS8):
    color_tile(nm, slot_note(s), B_FADER, r, g, b, w)
_fader_fx = [dim_run, dim_ping, dim_pairs, dim_strobe, dim_build, dim_pulse,
             ch_color, mx_rainbow]
for i, fn in enumerate(_fader_fx):
    accent = "#7a5b00" if fn is mx_rainbow else ("#3a2150" if fn is ch_color else "#1f4a28")
    func_btn(fn, slot_note(8 + i), B_FADER, accent, clear_prog=(fn.id in COLOR_FX_IDS))
# Fader: PARs live formen.  F1-F4 RGBW (nur PARs haben diese Kanaele),
# F5 PAR-Dim (nur Auswahl -> erst PAR-Gruppe waehlen), F8 FX-Level des Effekts.
fader("Rot", 0, B_FADER, SliderMode.PROGRAMMER, programmer_attr="color_r", midi_cc=48, value=0)
fader("Gruen", 1, B_FADER, SliderMode.PROGRAMMER, programmer_attr="color_g", midi_cc=49, value=0)
fader("Blau", 2, B_FADER, SliderMode.PROGRAMMER, programmer_attr="color_b", midi_cc=50, value=0)
fader("Weiss", 3, B_FADER, SliderMode.PROGRAMMER, programmer_attr="color_w", midi_cc=51, value=0)
fader("PAR-Dim", 4, B_FADER, SliderMode.PROGRAMMER, programmer_attr="intensity",
      programmer_scope="group", programmer_group="PAR-Reihe", midi_cc=52, value=255)
fader("FX-Level", 7, B_FADER, SliderMode.EFFECT_INTENSITY,
      function_ids=[f.id for f in dim_funcs], midi_cc=55, value=255)
label("SEITE 2  EFFEKTE + PAR-FADER  -  Effekt starten, dann die PARs live formen: "
      "F1-F4 = R/G/B/W (nur PARs), F8 = FX-Level.  F5 = PAR-Dim trifft fest die "
      "PAR-Gruppe (To-Do #4: keine Vorauswahl mehr nötig).",
      X0, 28, 1100, B_FADER, fg="#9DFF52")


# ── BANK 3 — CHASE BUILDER (Farb-Chase live bauen) ──────────────────────────
_chase_colors = [("Rot", 255, 0, 0, 0), ("Orange", 255, 90, 0, 0), ("Gelb", 255, 220, 0, 0),
                 ("Gruen", 0, 255, 0, 0), ("Cyan", 0, 255, 255, 0), ("Blau", 0, 0, 255, 0),
                 ("Violett", 140, 0, 255, 0), ("Magenta", 255, 0, 255, 0),
                 ("Pink", 255, 0, 120, 0), ("Tuerkis", 0, 220, 180, 0),
                 ("Limette", 160, 255, 0, 0), ("Warmweiss", 255, 130, 40, 60),
                 ("Weiss", 255, 255, 255, 255)]
for s, (nm, r, g, b, w) in enumerate(_chase_colors):
    color_tile(nm, slot_note(s), B_CHASE, r, g, b, w,
               target=ColorTarget.EFFECT_ADD, function_id=chase_builder.id)
# Untere Reihe (Slots 56-63 = Note 0-7): Builder-Steuerung.
func_btn(chase_builder, 0, B_CHASE, "#1f6a4a", clear_prog=True)
effect_action_btn("Clear", 1, B_CHASE, "#5a1010", "clear_colors", chase_builder.id)
effect_action_btn("Farbe -", 2, B_CHASE, "#333355", "prev_color", chase_builder.id)
effect_action_btn("Farbe +", 3, B_CHASE, "#333355", "next_color", chase_builder.id)
effect_action_btn("Richtung", 4, B_CHASE, "#335533", "reverse_direction", chase_builder.id)
effect_action_btn("Bounce", 5, B_CHASE, "#335533", "toggle_bounce", chase_builder.id)
effect_action_btn("Freeze", 6, B_CHASE, "#553333", "toggle_freeze", chase_builder.id)
effect_action_btn("Commit", 7, B_CHASE, "#1d4d2d", "commit_live", chase_builder.id)
fader("Speed", 0, B_CHASE, SliderMode.EFFECT_SPEED, function_id=chase_builder.id, midi_cc=48, value=80)
fader("Uebergang", 1, B_CHASE, SliderMode.EFFECT_PARAM, function_id=chase_builder.id,
      param_key="hold", midi_cc=49, value=64)
label("SEITE 3  CHASE BUILDER  -  1) Pad unten links = Start  2) oben Farben "
      "antippen = der Reihe nach an die Liste anhaengen  3) Clear leert die Liste.",
      X0, 28, 1100, B_CHASE, fg="#9DFF52")
label("Untere Reihe: Start/Stop | Clear | Farbe -/+ | Richtung | Bounce | Freeze | "
      "Commit (Live als Preset uebernehmen).  F1 Speed, F2 Uebergang (0 weich..hart).",
      X0, 48, 1100, B_CHASE)
# To-Do #1: All-in-One-Builder-Widget rechts neben dem Pad-Grid — bündelt Palette
# (antippen = anhängen), gebaute Liste (Feedback #6), Aktionen und Speed/Hold in
# EINEM Element. Alternative/Ergänzung zu den verstreuten Pads links.
RIGHT_X = X0 + 8 * STEP + 16
chase_builder_widget("Chase Builder", RIGHT_X, Y0 + 4 * 26 + 6, 210, 250, B_CHASE,
                     chase_builder.id)


# ── BANK 4 — MATRIX BUILDER (EINE Matrix + Form-Blaettern + Live-Recolor) ────
# Recolor-Block oben: 3 Reihen fuer die FESTEN Farben color1/2/3 (greifen bei
# Feuer/Plasma/Windrad/Lauflicht), 1 Reihe fuer die aktive Sequence-Farbe
# (greift bei Color-Fade/Gradient). Alle binden fest auf den Matrix-Builder.
MB = matrix_builder.id
RECOLOR = [("Rot", 255, 0, 0), ("Gruen", 0, 255, 0), ("Blau", 0, 0, 255), ("Weiss", 255, 255, 255)]
SEQCOL = [("Rot", 255, 0, 0), ("Gruen", 0, 255, 0), ("Blau", 0, 0, 255), ("Gelb", 255, 220, 0)]
for s, (nm, r, g, b) in enumerate(RECOLOR):          # Reihe 1, Slots 0-3: color1
    color_tile(f"C1 {nm}", slot_note(s), B_MATRIX, r, g, b,
               target=ColorTarget.EFFECT_C1, function_id=MB)
for s, (nm, r, g, b) in enumerate(SEQCOL):           # Reihe 1, Slots 4-7: Sequence
    color_tile(f"Seq {nm}", slot_note(4 + s), B_MATRIX, r, g, b,
               target=ColorTarget.EFFECT, function_id=MB)
for s, (nm, r, g, b) in enumerate(RECOLOR):          # Reihe 2, Slots 8-11: color2
    color_tile(f"C2 {nm}", slot_note(8 + s), B_MATRIX, r, g, b,
               target=ColorTarget.EFFECT_C2, function_id=MB)
for s, (nm, r, g, b) in enumerate(RECOLOR):          # Reihe 3, Slots 16-19: color3
    color_tile(f"C3 {nm}", slot_note(16 + s), B_MATRIX, r, g, b,
               target=ColorTarget.EFFECT_C3, function_id=MB)
# Untere Reihe (Note 0-7): Builder-Steuerung. EINE Matrix -> "Form -/+" blaettert
# durch ALLE Algorithmen (To-Do #3), kein Pad-pro-Algorithmus mehr.
func_btn(matrix_builder, 0, B_MATRIX, "#7a5b00", clear_prog=True)
effect_action_btn("Form -", 1, B_MATRIX, "#5a4a00", "prev_algorithm", MB)
effect_action_btn("Form +", 2, B_MATRIX, "#7a6500", "next_algorithm", MB)
effect_action_btn("Richtung", 3, B_MATRIX, "#335533", "reverse_direction", MB)
effect_action_btn("Bounce", 4, B_MATRIX, "#335533", "toggle_bounce", MB)
effect_action_btn("Freeze", 5, B_MATRIX, "#553333", "toggle_freeze", MB)
effect_action_btn("Reset Live", 6, B_MATRIX, "#5a3010", "clear_live_override", MB)
effect_action_btn("Commit", 7, B_MATRIX, "#1d4d2d", "commit_live", MB)
fader("Mtx-Sp", 0, B_MATRIX, SliderMode.EFFECT_SPEED, function_ids=[MB], midi_cc=48, value=64)
fader("Mtx-Mst", 1, B_MATRIX, SliderMode.EFFECT_INTENSITY, function_ids=[MB], midi_cc=49, value=255)
fader("Param", 2, B_MATRIX, SliderMode.EFFECT_PARAM, function_id=MB,
      param_key="white_amount", midi_cc=50, value=0)
label("SEITE 4  MATRIX BUILDER  -  Pad unten links startet EINE Matrix; 'Form -/+' "
      "blaettert durch ALLE Algorithmen.  Unten tunen: Richtung/Bounce/Freeze/Reset/Commit.",
      X0, 28, 1100, B_MATRIX, fg="#9DFF52")
label("Recolor oben: Reihe 1 = color1 (+ Sequence-Farbe rechts), Reihe 2 = color2, "
      "Reihe 3 = color3.  C1/2/3 greifen bei Feuer/Plasma/Windrad; Seq-Farbe bei Color-Fade.",
      X0, 48, 1100, B_MATRIX)
# To-Do #6: Feedback-Fenster der Matrix-Color-Sequence (rechts neben dem Grid).
color_list("Matrix-Farben", X0 + 8 * STEP + 16, Y0 + 4 * 26 + 8, 210, 96, B_MATRIX,
           matrix_builder.id)

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

# ── 5) Speichern + Verifikation ─────────────────────────────────────────────
state.programmer = {}
state.show_name = "APC Probier"
save_show(OUT)
print(f"Gespeichert: {OUT}")

ok, msg = load_show(OUT)
print("Load:", ok, msg)
assert ok, f"Show laedt nicht: {msg}"

# Patch
fixtures2 = state.get_patched_fixtures()
print(f"Patch ({len(fixtures2)}): " +
      ", ".join(f"[{f.fid}]{f.label}@{f.address}({f.channel_count}ch)" for f in fixtures2))
assert len(fixtures2) == 6, "6 Fixtures erwartet"

# Funktionen nach Typ
by: dict[str, list] = {}
for f in fm.all():
    by.setdefault(f.function_type.value, []).append(f)
print(f"Funktionen gesamt: {len(fm.all())}")
for t, fns in sorted(by.items()):
    print(f"   {t:10} ({len(fns)})")

# Chase-Builder ueberlebt den Roundtrip + ist eine Color-Fade-Matrix?
from src.core.engine.rgb_matrix import RgbMatrixInstance
builders = [f for f in fm.all() if isinstance(f, RgbMatrixInstance) and f.name == "Chase-Builder"]
assert len(builders) == 1, "Chase-Builder fehlt nach dem Laden"
assert builders[0].algorithm == RgbAlgorithm.COLORFADE, builders[0].algorithm
print(f"Chase-Builder OK: {builders[0].name} ({builders[0].algorithm.value}), "
      f"{len(builders[0].colors)} Seed-Farben")

# EFX auf den MHs intakt?
from src.core.engine.efx import EfxInstance
efxs = [f for f in fm.all() if isinstance(f, EfxInstance)]
assert len(efxs) == 4, f"4 EFX erwartet, {len(efxs)}"
for e in efxs:
    assert {fx.fid for fx in e.fixtures} == {mh_left, mh_right} and e.open_beam, e.name

# Gruppen persistiert?
with state._session() as s:
    gnames = sorted(g.name for g in s.execute(select(FixtureGroup)).scalars().all())
assert gnames == ["Moving Heads", "PAR-Reihe"], gnames
print(f"Gruppen persistiert: {gnames}")

# VC: Banks + Widget-Inventar je Bank
from collections import Counter
vc = state._vc_layout.get("widgets", [])
banks = Counter(w.get("bank") for w in vc)
assert set(banks) == {0, 1, 2, 3, -1}, f"Banks: {sorted(banks)}"

# Bank 2: 4 Programmer-RGBW-Fader vorhanden?
prog_faders = [w for w in vc if w.get("bank") == B_FADER and w.get("mode") == "Programmer"]
assert len(prog_faders) >= 4, f"PAR-Fader fehlen: {len(prog_faders)}"

# Bank 3: EFFECT_ADD-Farbkacheln (Chase Builder) + Effekt-Aktionen?
add_tiles = [w for w in vc if w.get("bank") == B_CHASE
             and w.get("target") == ColorTarget.EFFECT_ADD]
assert len(add_tiles) == len(_chase_colors), f"EFFECT_ADD-Kacheln: {len(add_tiles)}"
chase_actions = [w for w in vc if w.get("bank") == B_CHASE and w.get("action") == "EffectAction"]
assert len(chase_actions) == 7, f"Chase-Builder-Aktionen: {len(chase_actions)}"

# Bank 4: EINE Builder-Matrix (Toggle) + "Form -/+" + color1/2/3-Recolor-Kacheln.
mtx_toggle = [w for w in vc if w.get("bank") == B_MATRIX and w.get("action") == "FunctionToggle"]
assert len(mtx_toggle) == 1, f"Matrix-Builder-Toggle: {len(mtx_toggle)}"
mtx_action_keys = {w.get("effect_action_key") for w in vc
                   if w.get("bank") == B_MATRIX and w.get("action") == "EffectAction"}
assert {"next_algorithm", "prev_algorithm"} <= mtx_action_keys, mtx_action_keys
slot_tiles = [w for w in vc if w.get("bank") == B_MATRIX
              and w.get("target") in (ColorTarget.EFFECT_C1, ColorTarget.EFFECT_C2,
                                       ColorTarget.EFFECT_C3)]
assert len(slot_tiles) == 12, f"color1/2/3-Recolor-Kacheln: {len(slot_tiles)}"

# To-Do #6: Feedback-Fenster (VCColorList) auf Bank 4 (Matrix).
color_lists = [w for w in vc if w.get("type") == "VCColorList"]
assert len(color_lists) == 1, f"VCColorList-Feedbackfenster: {len(color_lists)}"
assert color_lists[0].get("function_id") == matrix_builder.id
# To-Do #1: All-in-One Chase-Builder-Widget auf Bank 3.
builders = [w for w in vc if w.get("type") == "VCChaseBuilder"]
assert len(builders) == 1, f"VCChaseBuilder: {len(builders)}"
assert builders[0].get("function_id") == chase_builder.id

maxy = max((w.get("y", 0) + w.get("h", 0)) for w in vc)
assert maxy < 800, f"Widgets ragen unter Canvas-Min: {maxy}"

print(f"VC-Widgets: {len(vc)}  Typen={dict(Counter(w['type'] for w in vc))}")
print(f"VC-Bank-Verteilung: {dict(sorted(banks.items()))}  Max-Y={maxy}")
print(f"  Bank 2 Programmer-Fader: {len(prog_faders)}")
print(f"  Bank 3 EFFECT_ADD-Farben: {len(add_tiles)}, Aktionen: {len(chase_actions)}")
print(f"  Bank 4 Matrix-Builder: Toggle={len(mtx_toggle)}, "
      f"Aktionen inkl. Form-/+ ({sorted(mtx_action_keys)}), Recolor-Kacheln={len(slot_tiles)}")
print("FERTIG")
