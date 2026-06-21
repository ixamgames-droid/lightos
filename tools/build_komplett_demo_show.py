"""KOMPLETT-DEMO-SHOW: alle Features der Software auf Davids realer Hardware.

Buehnenbild:
  * 4x  Generic "Stage Light ZQ01424" (8-Kanal RGBW)  = PARs in der Mitte
        -> Universe 1, DMX 1 / 9 / 17 / 25
  * 2x  U King "ZQ02001" (11-Kanal Moving Head)       = links (33) / rechts (44)
  * Akai APC mini (mk2) als Hardware-Controller der Virtual Console.

8 Seiten (APC-Scene-Tasten rechts = Seite 1-8):
  1 Farben       PAR-Farben, Looks, Bibliothek-Snaps, Farb-Chaser
  2 Dimmer-FX    Lauflicht/Strobe/Build/Pulse/Wave + Speed-/Level-Fader
  3 Matrix       13 RGB-Matrix-Algorithmen + Matrix-Master
  4 Moving Heads Pan/Tilt-EFX, Positionen, Farbrad, Gobos, Shutter, Reset
  5 Autoplay     AUTO-SHOW (Timeline, loopt die ganze Show) + Beat-Effekte
                 (laufen im BPM-Takt: Tap ODER Musik-BPM = Audio-Erkennung)
  6 Live-Matrix  Live Programming: Farben antippen -> Color-Chase live bauen,
                 Richtung/Freeze/Clear per Pad
  7 Mix          Farbe + Dimmer-FX + Matrix + MH-Bewegung frei kombinieren
  8 RGBW Hand    Fader = R/G/B/W/Intensitaet (Programmer) + Fixture-Makros

Universell auf JEDER Seite:
  * Track-Tasten unten: Clear / Stop All / Blackout / Tap / Musik-BPM
  * Fader: F6 Dimmer (Submaster) | F7 Speed global | F9 Grand Master

AUTOPLAY-Konzept:
  * "AUTO-SHOW" = Show-Timeline (72 s, Loop): faehrt Warm-Intro -> Farb-Chase ->
    Matrix-Regenbogen+Lauflicht -> Feuer+Pulse -> Plasma -> Party-Finale mit
    Strobe; Moving Heads parallel mit Kreis/Acht/Sweep/Bounce + Farbrad/Gobo.
  * "Beat-..."-Funktionen schalten NUR auf den globalen Beat weiter:
    Tap-Taste 4x druecken = manuelles Tempo, ODER "Musik-BPM" = BPM-Erkennung
    aus dem Audio-Eingang (Geraet im View "Audio-Eingang" waehlbar).

Aufruf:  venv/Scripts/python.exe tools/build_komplett_demo_show.py
Erzeugt: shows/Komplett_Demo.lshow
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
from src.core.engine.show_engine import ShowFunction
from src.core.engine.snap_library import get_snap_library
from src.core.show.show_file import reset_show, save_show, load_show
from src.ui.virtualconsole.vc_button import VCButton, ButtonAction
from src.ui.virtualconsole.vc_color import VCColor, ColorTarget
from src.ui.virtualconsole.vc_slider import VCSlider, SliderMode
from src.ui.virtualconsole.vc_label import VCLabel

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(_ROOT, "shows", "Komplett_Demo.lshow")

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
all_fids = [f.fid for f in fixtures]
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

# ── PAR: Farb-Looks (Farbe + Helligkeit, nur PARs) ──────────────────────────
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
lk_sunset = par_look("Sonnenuntergang", r=255, g=70, b=0, w=30)
lk_ocean = par_look("Ozean", g=120, b=255)
lk_party = par_look("Party", r=255, g=0, b=180, w=20)
lk_white = par_look("Vollweiß", r=255, g=255, b=255, w=255)
look_funcs = [lk_warm, lk_cold, lk_sunset, lk_ocean, lk_party, lk_white]

lk_red = par_look("Rot voll", r=255)
lk_grn = par_look("Grün voll", g=255)
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
dim_rand = chaser("Random", [st1.id, st2.id, st3.id, st4.id, st_all.id], hold=0.3, order=RunOrder.Random)

dim_pulse = fm.new_carousel("Pulse")
dim_pulse.pattern = CarouselPattern.PULSE; dim_pulse.fixture_ids = list(par_fids)
dim_pulse.sync_to_beat = False; dim_pulse.speed = 1.0
dim_wave = fm.new_carousel("Wave")
dim_wave.pattern = CarouselPattern.WAVE; dim_wave.fixture_ids = list(par_fids)
dim_wave.sync_to_beat = False; dim_wave.speed = 1.0

dim_full = par_look("Full (alle an)", r=0, g=0, b=0, w=0)   # nur Intensitaet
dimmer_funcs = [dim_run, dim_rev, dim_ping, dim_pairs, dim_strobe, dim_build,
                dim_rand, dim_pulse, dim_wave]

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
mx_spark = matrix("Mtx Sparkle", RgbAlgorithm.RANDOM, c1=(255, 255, 255), speed=6.0,
                  params={"mode": "sparkle", "count": 2, "rate": 3.0})
mx_breathe = matrix("Mtx Atmen", RgbAlgorithm.BREATHE, c1=(180, 0, 255), speed=1.0)
mx_fade = matrix("Mtx Color-Fade", RgbAlgorithm.COLORFADE, speed=1.0)
mx_plasma = matrix("Mtx Plasma", RgbAlgorithm.SINEPLASMA, speed=1.2)
mx_pin = matrix("Mtx Windrad", RgbAlgorithm.PINWHEEL, speed=2.0)
mx_strobe = matrix("Mtx Strobe", RgbAlgorithm.STROBE, c1=(255, 255, 255), speed=8.0)
matrix_funcs = [mx_rainbow, mx_chase, mx_wipe, mx_grad, mx_radar, mx_fire, mx_rain,
                mx_spark, mx_breathe, mx_fade, mx_plasma, mx_pin, mx_strobe]

# Live Color-Chase fuer Seite 6 (Farbliste wird LIVE per Pad aufgebaut).
live_chase = matrix("Live Color-Chase", RgbAlgorithm.COLORFADE, speed=2.0, params={"hold": 0.25})
live_chase.colors = ColorSequence([(255, 0, 0), (0, 255, 0), (0, 0, 255)])


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


efx_circle = mh_efx("MH Kreis (Fan)", EfxAlgorithm.CIRCLE, spread=0.5)
efx_eight = mh_efx("MH Acht", EfxAlgorithm.EIGHT, spread=0.0)
efx_sweep = mh_efx("MH Sweep gespiegelt", EfxAlgorithm.LINE, spread=0.0, mirror=True)
efx_bounce = mh_efx("MH Bounce", EfxAlgorithm.LINE, direction="bounce", spread=0.0)
mh_efx_funcs = [efx_circle, efx_eight, efx_sweep, efx_bounce]


# ── MOVING HEADS: Szenen (Position / Farbrad / Gobo / Shutter / Reset) ──────
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
pos_up = mh_scene("Pos Hoch", pan=128, tilt=60, intensity=255, shutter=4)
pos_cross = fm.new_scene("Pos Cross")
for fid, pan in ((mh_left, 180), (mh_right, 76)):
    cm = chan_of[fid]
    for attr, val in (("pan", pan), ("tilt", 150), ("intensity", 255), ("shutter", 4)):
        if attr in cm:
            pos_cross.set_value(fid, cm[attr], val)
mh_pos_funcs = [pos_center, pos_aud, pos_up, pos_cross]

# Farbrad: exakte ZQ02001-Slots (0-9 weiss, 10-19 rot, 20-29 gruen, 30-39 blau,
# 40-49 gelb, 50-59 orange, 60-69 hellblau, 70-79 rosa, 140-255 Farbwechsel).
cw_white = mh_scene("MH Weiß", color_wheel=4, intensity=255, shutter=4)
cw_red = mh_scene("MH Rot", color_wheel=14, intensity=255, shutter=4)
cw_green = mh_scene("MH Grün", color_wheel=24, intensity=255, shutter=4)
cw_blue = mh_scene("MH Blau", color_wheel=34, intensity=255, shutter=4)
cw_yellow = mh_scene("MH Gelb", color_wheel=44, intensity=255, shutter=4)
mh_color_funcs = [cw_white, cw_red, cw_green, cw_blue, cw_yellow]

# Gobos: 0-7 offen, 8-15 G1, 16-23 G2, 24-31 G3, 128-255 Gobo-Wechsel.
gb_open = mh_scene("Gobo Offen", gobo_wheel=3, intensity=255, shutter=4)
gb_1 = mh_scene("Gobo 1", gobo_wheel=11, intensity=255, shutter=4)
gb_2 = mh_scene("Gobo 2", gobo_wheel=19, intensity=255, shutter=4)
gb_3 = mh_scene("Gobo 3", gobo_wheel=27, intensity=255, shutter=4)
gb_spin = mh_scene("Gobo-Wechsel", gobo_wheel=190, intensity=255, shutter=4)
mh_gobo_funcs = [gb_open, gb_1, gb_2, gb_3, gb_spin]

# Shutter: 0-9 offen, 10-249 Strobe langsam->schnell.
sh_open = mh_scene("Shutter Auf", shutter=4, intensity=255)
sh_strobe = mh_scene("Shutter Strobe", shutter=130, intensity=255)

# Reset (150-255 = Reset/Rekalibrierung) — als FLASH-Taste belegt.
mh_reset = mh_scene("MH Reset", reset=200)

# PAR-Fixture-eigene Programme (Shutter-Strobe / Makro-Kanal).
sc_fstrobe = fm.new_scene("PAR Fixt-Strobe")
sc_macro = fm.new_scene("PAR Auto-Programm")
for fid in par_fids:
    cm = chan_of[fid]
    for attr, val in (("intensity", 255), ("color_r", 255), ("color_g", 255),
                      ("color_b", 255), ("shutter", 200)):
        if attr in cm:
            sc_fstrobe.set_value(fid, cm[attr], val)
    for attr, val in (("intensity", 255), ("macro", 200), ("speed", 160)):
        if attr in cm:
            sc_macro.set_value(fid, cm[attr], val)


# ── AUTOPLAY 1: Show-Timeline (72 s, Loop) ──────────────────────────────────
auto_show = fm.new_show("AUTO-SHOW (Timeline)")
auto_show.loop = True
auto_show.total_duration = 72.0

t_parfx = auto_show.add_track("PAR Farbe/Effekt")
for fn, t0, dur, col in [
        (lk_warm,    0.0, 10.0, "#aa7733"), (ch_color, 10.0, 12.0, "#3fb950"),
        (mx_rainbow, 22.0, 12.0, "#d4a017"), (mx_fire,  34.0, 12.0, "#e25822"),
        (mx_plasma,  46.0, 12.0, "#9b59b6"), (lk_party, 58.0, 8.0, "#ff00b4"),
        (ch_police,  66.0, 6.0, "#3060ff")]:
    t_parfx.add_function(ShowFunction(function_id=fn.id, start_time=t0, duration=dur, color=col))

t_pardim = auto_show.add_track("PAR Dimmer")
for fn, t0, dur in [(dim_run, 22.0, 12.0), (dim_pulse, 46.0, 12.0),
                    (dim_build, 58.0, 8.0), (dim_strobe, 66.0, 6.0)]:
    t_pardim.add_function(ShowFunction(function_id=fn.id, start_time=t0, duration=dur, color="#1f4a28"))

t_mhmove = auto_show.add_track("MH Bewegung")
for fn, t0, dur in [(pos_aud, 0.0, 10.0), (efx_circle, 10.0, 12.0),
                    (efx_eight, 22.0, 12.0), (efx_sweep, 34.0, 12.0),
                    (efx_bounce, 46.0, 12.0), (efx_circle, 58.0, 14.0)]:
    t_mhmove.add_function(ShowFunction(function_id=fn.id, start_time=t0, duration=dur, color="#1f3a6a"))

t_mhcol = auto_show.add_track("MH Farbe/Gobo")
for fn, t0, dur in [(cw_red, 0.0, 10.0), (cw_blue, 10.0, 12.0),
                    (cw_yellow, 22.0, 12.0), (gb_spin, 34.0, 12.0),
                    (cw_green, 46.0, 12.0), (cw_red, 58.0, 14.0)]:
    t_mhcol.add_function(ShowFunction(function_id=fn.id, start_time=t0, duration=dur, color="#3a2a5a"))


# ── AUTOPLAY 2: Beat-Funktionen (folgen dem globalen BPM: Tap ODER Musik) ───
def beat_look(name, r, g, b, w, wheel):
    """Kompletter Look: PAR-Farbe + MH-Farbrad (Dimmer/Shutter offen)."""
    sc = fm.new_scene(name)
    for fid in par_fids:
        cm = chan_of[fid]
        for attr, val in (("intensity", 255), ("color_r", r), ("color_g", g),
                          ("color_b", b), ("color_w", w)):
            if attr in cm:
                sc.set_value(fid, cm[attr], val)
    for fid in mh_fids:
        cm = chan_of[fid]
        for attr, val in (("color_wheel", wheel), ("intensity", 255), ("shutter", 4)):
            if attr in cm:
                sc.set_value(fid, cm[attr], val)
    return sc


bl_specs = [("Beat Rot", 255, 0, 0, 0, 14), ("Beat Grün", 0, 255, 0, 0, 24),
            ("Beat Blau", 0, 0, 255, 0, 34), ("Beat Gelb", 255, 220, 0, 0, 44),
            ("Beat Hellblau", 0, 160, 255, 0, 64), ("Beat Rosa", 255, 0, 120, 0, 74)]
beat_look_scenes = [beat_look(*sp) for sp in bl_specs]

bt_looks = chaser("Beat-Looks", [sc.id for sc in beat_look_scenes], hold=0.5, fade=0.15)
bt_looks.audio_triggered = True
bt_looks.beats_per_step = 4          # alle 4 Beats = 1 Takt -> naechster Look

bt_flash = chaser("Beat-Flash", [st_odd.id, st_even.id], hold=0.3, fade=0.04)
bt_flash.audio_triggered = True
bt_flash.beats_per_step = 1          # jeder Beat: 1+3 / 2+4 im Wechsel

bt_mh = chaser("MH Beat-Move", [pos_center.id, pos_cross.id, pos_aud.id, pos_up.id],
               hold=0.5, fade=0.1)
bt_mh.audio_triggered = True
bt_mh.beats_per_step = 4             # alle 4 Beats neue Position

bt_pulse = fm.new_carousel("Beat-Pulse")
bt_pulse.pattern = CarouselPattern.PULSE
bt_pulse.fixture_ids = list(par_fids)
bt_pulse.sync_to_beat = True         # pulsiert im Beat
beat_funcs = [bt_looks, bt_flash, bt_mh, bt_pulse]


# ════════════════════════════════════════════════════════════════════════════
#  4) BIBLIOTHEK (Snaps)
# ════════════════════════════════════════════════════════════════════════════
lib.clear()
lib.add_folder("Farben"); lib.add_folder("Looks"); lib.add_folder("MH-Positionen")
_COLORS = [("Rot", 255, 0, 0, 0), ("Grün", 0, 255, 0, 0), ("Blau", 0, 0, 255, 0),
           ("Weiß", 0, 0, 0, 255), ("Amber", 255, 140, 0, 0), ("Cyan", 0, 255, 255, 0),
           ("Magenta", 255, 0, 255, 0), ("Warmweiß", 255, 130, 40, 60),
           ("Pink", 255, 0, 120, 0), ("Türkis", 0, 220, 180, 0),
           ("Orange", 255, 80, 0, 0), ("Violett", 140, 0, 255, 0)]
for nm, r, g, b, w in _COLORS:
    values = {fid: {a: v for a, v in (("color_r", r), ("color_g", g),
                                      ("color_b", b), ("color_w", w)) if a in chan_of[fid]}
              for fid in par_fids}
    lib.add_snap(nm, "Farben", values)
_look_specs = [("Warm Wash", 255, 120, 20, 120), ("Cold Wash", 0, 60, 255, 80),
               ("Sonnenuntergang", 255, 70, 0, 30), ("Ozean", 0, 120, 255, 0),
               ("Party", 255, 0, 180, 20), ("Vollweiß", 255, 255, 255, 255)]
look_snaps = {}
for nm, r, g, b, w in _look_specs:
    values = {fid: {a: v for a, v in (("intensity", 255), ("color_r", r), ("color_g", g),
                                      ("color_b", b), ("color_w", w)) if a in chan_of[fid]}
              for fid in par_fids}
    look_snaps[nm] = lib.add_snap(nm, "Looks", values)
for nm, pan, tilt in [("Center", 128, 128), ("Publikum", 128, 180), ("Hoch", 128, 60)]:
    values = {fid: {a: v for a, v in (("pan", pan), ("tilt", tilt),
                                      ("intensity", 255), ("shutter", 4))
                    if a in chan_of[fid]} for fid in mh_fids}
    lib.add_snap(nm, "MH-Positionen", values)


# ════════════════════════════════════════════════════════════════════════════
#  5) VIRTUAL CONSOLE — APC mini, 8 Seiten
# ════════════════════════════════════════════════════════════════════════════
PAD, GAP, X0, Y0 = 60, 6, 20, 70
STEP = PAD + GAP
GRID_BOTTOM = Y0 + 8 * STEP
TY = GRID_BOTTOM + 4
Y_FAD = GRID_BOTTOM + 34
FAD_H = 142
widgets: list[dict] = []

BANK_ALL = -1
B_COLOR, B_DIM, B_MTX, B_MH, B_AUTO, B_LIVE, B_MIX, B_RGBW = range(8)
PAGE_NAMES = ["Farben", "Dimmer-FX", "Matrix", "Moving Heads",
              "Autoplay", "Live-Matrix", "Mix", "RGBW Hand"]


def pad_pos(note):
    row, col = note // 8, note % 8
    return X0 + col * STEP, Y0 + (7 - row) * STEP


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
    b.action = ButtonAction.LIBRARY_SNAP; b.snap_id = snap.id
    b.snap_mode = "toggle"; b.pad_style = "solid"
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

label("APC mini  -  8x8 Pads (Note 0 = unten links).  SCENE-Tasten rechts = Seite 1-8. "
      "TRACK-Tasten unten = Clear/Stop/Blackout/Tap/Musik-BPM (überall aktiv).",
      X0, 6, 1150, BANK_ALL, hh=18, fg="#88c0ff")
label("Fader F1-F9 = CC48-56.  F6 Dimmer | F7 Speed global | F9 Master immer aktiv, "
      "F1-F5/F8 je nach Seite.", X0, Y_FAD + FAD_H + 4, 1150, BANK_ALL, hh=18, fg="#88c0ff")
for i, nm in enumerate(PAGE_NAMES):
    label(f"Scene {i + 1}: {nm}", X0 + 8 * STEP + 16, Y0 + i * 26, 160, BANK_ALL, hh=22, fg="#7aa0c0")


# ── SEITE 1 — FARBEN & LOOKS ────────────────────────────────────────────────
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
func_btn(ch_color, 0, B_COLOR, "#3a2150")
func_btn(ch_police, 1, B_COLOR, "#3a2150")
label("SEITE 1  FARBEN & LOOKS  -  oben 2 Reihen Farben (nur Farbe, sofort sichtbar), "
      "darunter Looks + Bibliothek-Snaps, unten links Farb-Chaser.",
      X0, 28, 1100, B_COLOR, fg="#9DFF52")

# ── SEITE 2 — DIMMER-EFFEKTE ────────────────────────────────────────────────
for i, fn in enumerate([dim_run, dim_rev, dim_ping, dim_pairs, dim_strobe, dim_build,
                        dim_rand, dim_full]):
    func_btn(fn, i, B_DIM, "#1f4a28")
func_btn(dim_pulse, 8, B_DIM, "#1d3d24")
func_btn(dim_wave, 9, B_DIM, "#1d3d24")
for i, (nm, r, g, b, w) in enumerate(_row7[:6]):
    color_tile(nm, 56 + i, B_DIM, r, g, b, w)
fader("Sp Lauf", 0, B_DIM, SliderMode.EFFECT_SPEED, function_id=dim_run.id, midi_cc=48, value=64)
fader("Sp Pulse", 1, B_DIM, SliderMode.EFFECT_SPEED, function_id=dim_pulse.id, midi_cc=49, value=64)
fader("Sp Wave", 2, B_DIM, SliderMode.EFFECT_SPEED, function_id=dim_wave.id, midi_cc=50, value=64)
fader("Sp Strobe", 3, B_DIM, SliderMode.EFFECT_SPEED, function_id=dim_strobe.id, midi_cc=51, value=90)
fader("FX-Level", 4, B_DIM, SliderMode.EFFECT_INTENSITY,
      function_ids=[f.id for f in dimmer_funcs], midi_cc=52, value=255)
label("SEITE 2  DIMMER-EFFEKTE  -  ueberschreiben die Grundhelligkeit (echtes Lauflicht). "
      "Farbe oben wählen -> Effekt laeuft in dieser Farbe.  F1-F4 Speed, F5 FX-Level.",
      X0, 28, 1100, B_DIM, fg="#9DFF52")

# ── SEITE 3 — MATRIX ────────────────────────────────────────────────────────
for i, fn in enumerate(matrix_funcs[:8]):
    func_btn(fn, i, B_MTX, "#7a5b00")
for i, fn in enumerate(matrix_funcs[8:]):
    func_btn(fn, 8 + i, B_MTX, "#6a4f00")
fader("Mtx-Sp", 0, B_MTX, SliderMode.EFFECT_SPEED,
      function_ids=[m.id for m in matrix_funcs], midi_cc=48, value=64)
fader("Mtx-Mst", 7, B_MTX, SliderMode.EFFECT_INTENSITY,
      function_ids=[m.id for m in matrix_funcs], midi_cc=55, value=255)
label("SEITE 3  MATRIX-EFFEKTE  -  bringen ihre Farbe SELBST mit -> vorher 'Clear'! "
      "F1 = Matrix-Speed, F8 = Matrix-Master, F7 = Speed global.",
      X0, 28, 1100, B_MTX, fg="#9DFF52")

# ── SEITE 4 — MOVING HEADS ──────────────────────────────────────────────────
for i, fn in enumerate(mh_efx_funcs):
    func_btn(fn, 56 + i, B_MH, "#1f3a6a")
for i, fn in enumerate(mh_pos_funcs):
    func_btn(fn, 48 + i, B_MH, "#10503a", style="solid")
for i, fn in enumerate(mh_color_funcs):
    func_btn(fn, 40 + i, B_MH, "#3a2a5a", style="solid")
for i, fn in enumerate(mh_gobo_funcs):
    func_btn(fn, 32 + i, B_MH, "#5a3a10", style="solid")
func_btn(sh_open, 24, B_MH, "#503010", style="solid")
func_btn(sh_strobe, 25, B_MH, "#503010", style="solid")
func_btn(mh_reset, 27, B_MH, "#401010", style="solid", flash=True)
fader("EFX-Sp", 0, B_MH, SliderMode.EFFECT_SPEED,
      function_ids=[f.id for f in mh_efx_funcs], midi_cc=48, value=70)
fader("Pan", 1, B_MH, SliderMode.PROGRAMMER, programmer_attr="pan", midi_cc=49, value=128)
fader("Tilt", 2, B_MH, SliderMode.PROGRAMMER, programmer_attr="tilt", midi_cc=50, value=128)
label("SEITE 4  MOVING HEADS  -  Reihe 1 EFX (Kreis/Acht/Sweep/Bounce, öffnen den Beam), "
      "Reihe 2 Positionen, Reihe 3 Farbrad, Reihe 4 Gobos, Reihe 5 Shutter + Reset (halten!).",
      X0, 28, 1100, B_MH, fg="#9DFF52")
label("F1 = EFX-Speed, F2/F3 = Pan/Tilt von Hand (Programmer).",
      X0, 48, 1100, B_MH)

# ── SEITE 5 — AUTOPLAY (Timeline + Beat) ────────────────────────────────────
func_btn(auto_show, 56, B_AUTO, "#806000", exclusive=True, clear_prog=True)
func_btn(bt_looks, 58, B_AUTO, "#1f6a4a")
func_btn(bt_flash, 59, B_AUTO, "#1f6a4a")
func_btn(bt_mh, 60, B_AUTO, "#1f3a6a")
func_btn(bt_pulse, 61, B_AUTO, "#1f6a4a")
action_btn("Musik-BPM", ButtonAction.AUDIO_BPM, 62, B_AUTO, "#106a8a")
action_btn("Tap", ButtonAction.TAP, 63, B_AUTO, "#103a3a")
for i, (nm, r, g, b, w) in enumerate(_row7[:6]):
    color_tile(nm, 48 + i, B_AUTO, r, g, b, w)
fader("BPM", 0, B_AUTO, SliderMode.BPM, midi_cc=48, value=0)
fader("Beat-Lvl", 4, B_AUTO, SliderMode.EFFECT_INTENSITY,
      function_ids=[f.id for f in beat_funcs], midi_cc=52, value=255)
label("SEITE 5  AUTOPLAY  -  Pad 1 (oben links) = AUTO-SHOW: 72-s-Timeline, loopt die "
      "ganze Show (PARs + Moving Heads), stoppt alles andere beim Start.",
      X0, 28, 1100, B_AUTO, fg="#9DFF52")
label("Beat-Funktionen (Pads 3-6) schalten NUR im Beat weiter: Tempo per 'Tap' (4x "
      "drücken) ODER 'Musik-BPM' = automatische BPM-Erkennung vom Audio-Eingang.",
      X0, 48, 1100, B_AUTO)
label("F1 = BPM von Hand setzen, F5 = Level der Beat-Effekte. Audio-Gerät wählen: "
      "Ansicht 'Audio-Eingang' in der App.", X0, GRID_BOTTOM - 28, 1100, B_AUTO)

# ── SEITE 6 — LIVE-MATRIX (Live Programming) ────────────────────────────────
_chase_colors = [("Rot", 255, 0, 0, 0), ("Orange", 255, 90, 0, 0), ("Gelb", 255, 220, 0, 0),
                 ("Grün", 0, 255, 0, 0), ("Cyan", 0, 255, 255, 0), ("Blau", 0, 0, 255, 0),
                 ("Violett", 140, 0, 255, 0), ("Magenta", 255, 0, 255, 0)]
for i, (nm, r, g, b, w) in enumerate(_chase_colors):
    color_tile(nm, 56 + i, B_LIVE, r, g, b, w, target=ColorTarget.EFFECT_ADD,
               function_id=live_chase.id)
_chase_colors2 = [("Pink", 255, 0, 120, 0), ("Türkis", 0, 220, 180, 0),
                  ("Limette", 160, 255, 0, 0), ("Warmweiß", 255, 130, 40, 60),
                  ("Weiß", 255, 255, 255, 255)]
for i, (nm, r, g, b, w) in enumerate(_chase_colors2):
    color_tile(nm, 48 + i, B_LIVE, r, g, b, w, target=ColorTarget.EFFECT_ADD,
               function_id=live_chase.id)
func_btn(live_chase, 0, B_LIVE, "#1f6a4a")
effect_action_btn("Clear Chase", 1, B_LIVE, "#5a1010", "clear_colors", live_chase.id)
effect_action_btn("Farbe -", 2, B_LIVE, "#333355", "prev_color", live_chase.id)
effect_action_btn("Farbe +", 3, B_LIVE, "#333355", "next_color", live_chase.id)
effect_action_btn("Richtung", 4, B_LIVE, "#335533", "reverse_direction", live_chase.id)
effect_action_btn("Freeze", 5, B_LIVE, "#553333", "toggle_freeze", live_chase.id)
fader("Speed", 0, B_LIVE, SliderMode.EFFECT_SPEED, function_id=live_chase.id, midi_cc=48, value=70)
fader("Übergang", 1, B_LIVE, SliderMode.EFFECT_PARAM, function_id=live_chase.id,
      param_key="hold", midi_cc=49, value=64)
label("SEITE 6  LIVE-MATRIX  -  1) 'Clear Chase' leert die Farbliste  2) oben Farben "
      "antippen = der Reihe nach anhängen  3) Pad 1 = Start/Stop.",
      X0, 28, 1100, B_LIVE, fg="#9DFF52")
label("Pad 5 = Richtung umkehren, Pad 6 = Freeze (einfrieren/weiter). F1 = Speed, "
      "F2 = Übergang (0 = weich faden, hoch = hart halten).", X0, 48, 1100, B_LIVE)

# ── SEITE 7 — MIX (Ebenen kombinieren) ──────────────────────────────────────
for i, (nm, r, g, b, w) in enumerate(_row7[:6]):
    color_tile(nm, 56 + i, B_MIX, r, g, b, w)
for i, fn in enumerate(look_funcs[:4]):
    func_btn(fn, 48 + i, B_MIX, "#264a6a", style="solid")
for i, fn in enumerate([dim_run, dim_pulse, dim_wave, dim_strobe]):
    func_btn(fn, i, B_MIX, "#1f4a28")
for i, fn in enumerate([mx_rainbow, mx_chase, mx_fire, mx_radar]):
    func_btn(fn, 16 + i, B_MIX, "#7a5b00")
for i, fn in enumerate(mh_efx_funcs):
    func_btn(fn, 24 + i, B_MIX, "#1f3a6a")
for i, fn in enumerate([cw_red, cw_blue, cw_yellow, gb_spin]):
    func_btn(fn, 32 + i, B_MIX, "#3a2a5a", style="solid")
fader("Sp Lauf", 0, B_MIX, SliderMode.EFFECT_SPEED, function_id=dim_run.id, midi_cc=48, value=64)
fader("FX-Level", 4, B_MIX, SliderMode.EFFECT_INTENSITY,
      function_ids=[f.id for f in dimmer_funcs], midi_cc=52, value=255)
fader("Mtx-Mst", 7, B_MIX, SliderMode.EFFECT_INTENSITY,
      function_ids=[m.id for m in matrix_funcs], midi_cc=55, value=255)
label("SEITE 7  MIX  -  Farbe (oben) + Dimmer-FX (unten links) = farbiges Lauflicht. "
      "Matrix (Clear zuerst!) + MH-EFX + MH-Farbe/Gobo = komplette Bühne aus Ebenen.",
      X0, 28, 1100, B_MIX, fg="#9DFF52")

# ── SEITE 8 — RGBW VON HAND + FIXTURE-PROGRAMME ─────────────────────────────
for i, (nm, r, g, b, w) in enumerate(_row7):
    color_tile(nm, 56 + i, B_RGBW, r, g, b, w)
func_btn(sc_fstrobe, 0, B_RGBW, "#503010", style="solid")
func_btn(sc_macro, 1, B_RGBW, "#503010", style="solid")
func_btn(dim_full, 2, B_RGBW, "#3a3a14", style="solid")
func_btn(mh_reset, 3, B_RGBW, "#401010", style="solid", flash=True)
fader("Rot", 0, B_RGBW, SliderMode.PROGRAMMER, programmer_attr="color_r", midi_cc=48, value=0)
fader("Grün", 1, B_RGBW, SliderMode.PROGRAMMER, programmer_attr="color_g", midi_cc=49, value=0)
fader("Blau", 2, B_RGBW, SliderMode.PROGRAMMER, programmer_attr="color_b", midi_cc=50, value=0)
fader("Weiß", 3, B_RGBW, SliderMode.PROGRAMMER, programmer_attr="color_w", midi_cc=51, value=0)
fader("Intens.", 4, B_RGBW, SliderMode.PROGRAMMER, programmer_attr="intensity", midi_cc=52, value=255)
label("SEITE 8  RGBW VON HAND  -  F1-F5 = Rot/Grün/Blau/Weiß/Intensität (Programmer). "
      "Pad 1 = PAR Fixt-Strobe, Pad 2 = PAR Auto-Programm (Makro-Kanal), Pad 4 = MH Reset.",
      X0, 28, 1100, B_RGBW, fg="#9DFF52")

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

# ── 6) Speichern + Verifikation ─────────────────────────────────────────────
state.programmer = {}
state.show_name = "Komplett Demo"
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
by = {}
for f in fm.all():
    by.setdefault(f.function_type.value, []).append(f)
print(f"Funktionen gesamt: {len(fm.all())}")
for t, fns in sorted(by.items()):
    print(f"   {t:10} ({len(fns)})")

# AUTO-SHOW-Timeline ueberlebt den Roundtrip?
from src.core.engine.show_engine import Show
shows = [f for f in fm.all() if isinstance(f, Show)]
assert len(shows) == 1, f"1 Show erwartet, {len(shows)}"
sh = shows[0]
assert sh.loop is True and abs(sh.total_duration - 72.0) < 0.01, "Show Loop/Dauer falsch"
n_place = sum(len(t.show_functions) for t in sh.tracks)
assert len(sh.tracks) == 4 and n_place == 23, f"Tracks/Platzierungen: {len(sh.tracks)}/{n_place}"
reg = {f.id: f for f in fm.all()}
for t in sh.tracks:
    for sf in t.show_functions:
        assert sf.function_id in reg, f"Show-Referenz {sf.function_id} fehlt"
print(f"AUTO-SHOW OK: {len(sh.tracks)} Tracks, {n_place} Platzierungen, "
      f"{sh.total_duration:.0f}s Loop={sh.loop}")

# Beat-Funktionen: audio_triggered ueberlebt?
from src.core.engine.chaser import Chaser
beat_names = {"Beat-Looks": 4, "Beat-Flash": 1, "MH Beat-Move": 4}
found_beat = {f.name: f for f in fm.all() if isinstance(f, Chaser) and f.name in beat_names}
assert set(found_beat) == set(beat_names), f"Beat-Chaser fehlen: {set(beat_names) - set(found_beat)}"
for nm, bps in beat_names.items():
    f = found_beat[nm]
    assert f.audio_triggered is True and f.beats_per_step == bps, \
        f"{nm}: audio_triggered={f.audio_triggered} beats_per_step={f.beats_per_step}"
from src.core.engine.carousel import Carousel
caro = {f.name: f for f in fm.all() if isinstance(f, Carousel)}
assert caro["Beat-Pulse"].sync_to_beat is True, "Beat-Pulse sync_to_beat verloren"
print(f"Beat-Funktionen OK: {list(beat_names)} + Beat-Pulse (sync_to_beat)")

# EFX auf den MHs intakt?
from src.core.engine.efx import EfxInstance
efxs = [f for f in fm.all() if isinstance(f, EfxInstance)]
assert len(efxs) == 4, f"4 EFX erwartet, {len(efxs)}"
for e in efxs:
    assert {fx.fid for fx in e.fixtures} == {mh_left, mh_right} and e.open_beam, e.name
print(f"EFX OK: {[e.name for e in efxs]}")

# Gruppen persistiert?
with state._session() as s:
    gnames = sorted(g.name for g in s.execute(select(FixtureGroup)).scalars().all())
assert gnames == ["Moving Heads", "PAR-Reihe"], gnames
print(f"Gruppen persistiert: {gnames}")

# VC: Banks, Musik-BPM-Taste, Geometrie
vc = state._vc_layout.get("widgets", [])
from collections import Counter
banks = Counter(w.get("bank") for w in vc)
assert set(banks) == set(range(8)) | {-1}, f"Banks: {sorted(banks)}"
audio_btns = [w for w in vc if w.get("action") == "AudioBpm"]
assert len(audio_btns) == 2, f"2 Musik-BPM-Tasten erwartet, {len(audio_btns)}"
bpm_fader = [w for w in vc if w.get("mode") == "BPM"]
assert len(bpm_fader) == 1, "BPM-Fader fehlt"
maxy = max((w.get("y", 0) + w.get("h", 0)) for w in vc)
assert maxy < 800, f"Widgets ragen unter Canvas-Min: {maxy}"
print(f"VC-Widgets: {len(vc)}  Typen={dict(Counter(w['type'] for w in vc))}")
print(f"VC-Bank-Verteilung: {dict(sorted(banks.items()))}  Max-Y={maxy}")
print(f"Snaps: {len(lib.snaps())}")
print("FERTIG")
