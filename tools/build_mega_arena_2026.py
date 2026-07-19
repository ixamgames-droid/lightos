"""MEGA ARENA SHOW 2026 — die grosse Hardstyle-Arena-Demo auf einem 4-Trassen-Rig.

Baut Davids Wunsch-Show: ALLE Feature-Familien, die zusammenpassen, auf einem
erweiterten 32-Fixture-Rig ueber VIER Trassen-Ebenen — zwei ueber der Buehne
(Front/Back), zwei SEITLICH ins Publikum leuchtend. Nebel steht VOR dem Publikum
am Boden. Steuerung ueber eine reiche Virtuelle Konsole (6 Zweck-Baenke + APC-Mini-
Belegung 8x8). Auto-Show + echte Hardstyle-/Frenchcore-Tracks (music-sync).

RIG (32 Fixtures):
    U1  12x PAR RGBW    ZQ01424  ( 8ch) — 8 am Boden (Publikums-Wash) + 4 Front-Truss
    U1   6x Moving Head  MH16    (16ch) — 2 Back-Truss (Beam/Gobo) + 4 Seiten (Publikum)
    U1   2x Moving Head  ZQ02001 (11ch) — Davids reale MHs, Back-Truss
    U1   4x Spider       SPIDER14(14ch) — Front-Truss, NUR Tilt (kein Pan!), Derby-Faecher
    U1   2x LED-Bar      BAR12   (12ch) — Front-Truss, 4x RGB, Publikums-Farbe
    U2   4x Laser        L2600LASER(6ch)— Back-/Seiten-Truss, Arm/Estop-Safety
    U2   2x Nebel/Hazer  EURON10 ( 1ch) — Boden VOR dem Publikum

VC-BAENKE (APC-Seiten):
    0 FARBE     — PAR/LED/Spider-Farbmatrizen + Swatches + MH-Farbrad
    1 DIMMER    — Dimmer-Effekte je Gruppe + MH-Gobo
    2 BEWEGUNG  — MH-Formen + Publikums-Sweep + Spider-Tilt + XY-Pad
    3 STROBE    — Strobe je Gruppe + All-White-Blinder (Publikum)
    4 LASER+NEBEL — Laser-Muster/Arm/Not-Aus + Nebel + Laser-Farbe
    5 HARDSTYLE — BPM/Tap, Beat-Blink RRRW/RWRW, Speeds, Auto-Show, Media, Master

Alle Effekte folgen dem Master-Bus "Global" (= globale Musik-BPM via Tap/Audio)
mit eigenem tempo_multiplier (Speed-Dials 1/4..4x). Kategorien LAYERN (edit_slot
statt globalem stop_all/exclusive). Safety: Mover-Shutter offen, Laser bleibt aus
bis Arm/Muster, base_levels ohne implizite Grundhelligkeit.

Aufruf:  venv/Scripts/python.exe tools/build_mega_arena_2026.py
Erzeugt: shows/Mega_Arena_2026.lshow  (selbst-verifizierend, headless)
"""
from __future__ import annotations
import os
import sys
import glob
import json
import math
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# ISO: eigene Show-Cache-DB — NICHT Davids laufende data/current_show.db anfassen
# (sonst Race/Desync mit der Live-App). Muss VOR dem app_state-Import gesetzt sein
# (SHOW_DB_PATH liest die Env beim Import). Siehe Audit-Fund 2026-07-17.
os.environ.setdefault("LIGHTOS_SHOW_DB",
                      os.path.join(tempfile.gettempdir(), "lightos_mega_arena_build.db"))

import _gen_env  # noqa: F401  # DEMO-02: spawn-sichere Env-Schalter vor src.core
from PySide6.QtWidgets import QApplication
_app = QApplication.instance() or QApplication([])

from sqlalchemy import select, delete
from sqlalchemy.orm import Session
from src.core.app_state import get_state, get_channels_for_patched, open_value_for
from src.core.database.fixture_db import engine as fdb_engine, ensure_builtins
from src.core.database.models import PatchedFixture, FixtureProfile, FixtureGroup
from src.core.engine.function_manager import get_function_manager
from src.core.engine.function import RunOrder, Direction
from src.core.engine.chaser import ChaserStep
from src.core.engine.rgb_matrix import RgbAlgorithm, MatrixStyle, ColorSequence
from src.core.engine.efx import EfxFixture, EfxAlgorithm
from src.core.engine.efx_path import EfxPath, get_efx_path_library
from src.core.engine.tempo_bus import get_tempo_bus_manager
from src.core.engine.show_engine import ShowFunction
from src.core.show.show_file import reset_show, save_show, load_show
from src.core.show import vc_gallery
from src.core.audio.media_player import clean_title, guess_genre_bpm
from src.core.stage.stage_definition import StageDefinition, save_stage
from src.core.stage.scene_graph import NodeKind, SceneNode, Transform
from src.ui.virtualconsole.vc_button import VCButton, ButtonAction
from src.ui.virtualconsole.vc_color import VCColor, ColorTarget
from src.ui.virtualconsole.vc_label import VCLabel
from src.ui.virtualconsole.vc_slider import VCSlider, SliderMode
from src.ui.virtualconsole.vc_speedial import VCSpeedDial, SpeedTarget
from src.ui.virtualconsole.vc_bpm_display import VCBpmDisplay
from src.ui.virtualconsole.vc_effect_colors import VCEffectColors
from src.ui.virtualconsole.vc_xypad import VCXYPad
from src.ui.virtualconsole.vc_song_info import VCSongInfo
from src.ui.virtualconsole.vc_effect_editor import VCEffectEditor

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(_ROOT, "shows", "Mega_Arena_2026.lshow")
STAGE_NAME = "MegaArena2026"
MUSIC_DIR = os.environ.get("LIGHTOS_MEGA_MUSIC_DIR", r"C:/Users/David/Desktop/Musik/BP Party")
BUS = "Global"            # Master: folgt der globalen Musik-BPM (Tap/Audio)
PLAYLIST_MAX = 16


def profile_id(short: str) -> int:
    with Session(fdb_engine()) as s:
        pid = s.execute(select(FixtureProfile.id).where(
            FixtureProfile.short_name == short)).scalar_one_or_none()
    if pid is None:
        raise SystemExit(f"Profil '{short}' fehlt — App einmal starten (ensure_builtins).")
    return int(pid)


# ════════════════════════════════════════════════════════════════════════════
#  0) PATCH — 32 Fixtures ueber 2 Universen
# ════════════════════════════════════════════════════════════════════════════
ensure_builtins()
reset_show()
state = get_state()
fm = get_function_manager()

PID = {sn: profile_id(sn) for sn in
       ("ZQ01424", "MH16", "ZQ02001", "SPIDER14", "BAR12", "L2600LASER", "EURON10")}

_next_fid = 1


def patch(short, count, ch, mode, universe, addr, label, ftype):
    global _next_fid
    fids = []
    for i in range(count):
        fid = _next_fid
        _next_fid += 1
        state.add_fixture(PatchedFixture(
            fid=fid, label=f"{label} {i + 1}", fixture_profile_id=PID[short],
            mode_name=mode, universe=universe, address=addr, channel_count=ch,
            fixture_type=ftype), undoable=False)
        fids.append(fid)
        addr += ch
    return fids


par_fids    = patch("ZQ01424", 12, 8,  "8-Kanal RGBW",         1, 1,   "PAR",    "par")
mh16_fids   = patch("MH16",    6,  16, "16-Kanal",             1, 97,  "MH",     "moving_head")
mhz_fids    = patch("ZQ02001", 2,  11, "11-Kanal",             1, 193, "MH-ZQ",  "moving_head")
spider_fids = patch("SPIDER14",4,  14, "14-Kanal",             1, 215, "Spider", "moving_head")
led_fids    = patch("BAR12",   2,  12, "12-Kanal (4x RGB)",    1, 271, "LED-Bar","led_bar")
laser_fids  = patch("L2600LASER", 4, 6, "6-Kanal (Simple DMX)", 2, 1,  "Laser",  "laser")
fog_fids    = patch("EURON10", 2,  1,  "1-Kanal (Nebel)",      2, 25,  "Nebel",  "hazer")

# Rollen der Moving Heads: 2 auf der Back-Truss (Buehne), 4 seitlich (ins Publikum)
mh_stage = mh16_fids[:2] + mhz_fids            # Back-Truss (Beams ueber Buehne)
mh_crowd = mh16_fids[2:]                        # 4 Seiten-Truss-MH (ins Publikum)
all_mh   = mh16_fids + mhz_fids
mover_fids = all_mh + spider_fids
color_fids = par_fids + spider_fids + led_fids  # echtes RGB(W)
all_fids   = par_fids + all_mh + spider_fids + led_fids + laser_fids + fog_fids
print(f"[patch] {len(all_fids)} Fixtures — PAR={len(par_fids)} MH16={len(mh16_fids)} "
      f"ZQ02001={len(mhz_fids)} Spider={len(spider_fids)} LED={len(led_fids)} "
      f"Laser={len(laser_fids)} Fog={len(fog_fids)}")

fixtures = state.get_patched_fixtures()
fx_of = {f.fid: f for f in fixtures}
chans_full = {f.fid: get_channels_for_patched(f) for f in fixtures}
chan_of = {f.fid: {c.attribute: c.channel_number for c in chans_full[f.fid]} for f in fixtures}


def attr_chs(fid, attr):
    return [c.channel_number for c in chans_full[fid] if (c.attribute or "").lower() == attr]


def dim_ch(fid):
    return chan_of[fid].get("intensity") or chan_of[fid].get("dimmer")


# ── Safety-Defaults: Mover-Shutter offen (emittieren, sobald Intensitaet kommt),
#    LASER bleibt aus (Shutter 0 = Rig-Safety-Default) bis Arm/Muster. Keine
#    implizite Grundhelligkeit (strikte Farbe/Dimmer-Trennung wie Davids Shows). ──
state.base_levels = {fid: {"shutter": open_value_for(fx_of[fid], "shutter")}
                     for fid in mover_fids if attr_chs(fid, "shutter")}
state.implicit_brightness = False
state._rebuild_render_plan()

# ── Fixture-Gruppen (Effekt-Areale + Master-Dimmer) ──────────────────────────
def _grp(s, name, fids, cols=None):
    cols = cols or len(fids)
    s.add(FixtureGroup(name=name, cols=cols, rows=1,
                       positions_json=json.dumps({f"{i},0": fids[i] for i in range(len(fids))})))


with state._session() as s:
    s.execute(delete(FixtureGroup))
    _grp(s, "Alle PAR", par_fids)
    _grp(s, "PAR Boden", par_fids[:8])
    _grp(s, "PAR Truss", par_fids[8:])
    _grp(s, "Moving Heads", all_mh)
    _grp(s, "MH Buehne", mh_stage)
    _grp(s, "MH Publikum", mh_crowd)
    _grp(s, "Spider", spider_fids)
    _grp(s, "LED Bars", led_fids)
    _grp(s, "Laser", laser_fids)
    _grp(s, "Nebel", fog_fids)
    _grp(s, "Alle Mover", mover_fids)
    _grp(s, "Alles", all_fids)
    s.commit()

# ── Tempo: Master-Bus "Global" FOLGT dem Leader (Musik-BPM/Tap/Audio) ─────────
tbm = get_tempo_bus_manager()
tbm.ensure_bus(BUS, source="bpm_global")

# Farben
RED, GREEN, BLUE = (255, 0, 0), (0, 255, 0), (0, 0, 255)
YELLOW, MAGENTA, CYAN, WHITE = (255, 200, 0), (255, 0, 255), (0, 255, 255), (255, 255, 255)
ORANGE, PINK = (255, 90, 0), (255, 0, 120)
MHCOL = {"weiss": 4, "rot": 14, "gruen": 24, "blau": 34, "gelb": 44, "rosa": 74}
MHGOBO = {"offen": 3, "g1": 11, "g3": 27, "g5": 43, "g7": 59, "rotation": 190}
MH_OPEN = 4
SP_OPEN = 8


def bind_tempo(fn, group, mult=1.0):
    fn.tempo_bus_id = BUS
    fn.tempo_multiplier = mult
    fn.sync_group = group
    return fn


def bgimg(name):
    """Eingebaute Galerie-Grafik/GIF -> Content-Hash-Key (portabel eingebettet)."""
    return vc_gallery.import_to_cache(name)


# ════════════════════════════════════════════════════════════════════════════
#  1) FARBE — RGB-Matrizen (PAR/LED/Spider) + MH-Farbrad-Szenen/Chaser
# ════════════════════════════════════════════════════════════════════════════
def color_matrix(name, fids, algo, colors, params=None, speed=1.0, group="", style=MatrixStyle.RGB):
    m = fm.new_rgb_matrix(name)
    m.algorithm = algo
    m.fixture_grid = list(fids)
    m.cols, m.rows = len(fids), 1
    m.colors = ColorSequence([tuple(c) for c in colors]) if colors else ColorSequence([WHITE])
    m.style = style
    m.drive_intensity = False       # nur Farbe — Dimmer/Helligkeit bleibt frei
    m.matrix_speed = speed
    if params:
        m.params = dict(params)
    if group:
        bind_tempo(m, group)
    return m


def color_effects(prefix, fids, group):
    solid = color_matrix(f"{prefix} Solid", fids, RgbAlgorithm.PLAIN, [RED], group=group)
    rainbow = color_matrix(f"{prefix} Regenbogen", fids, RgbAlgorithm.RAINBOW, [],
                           params={"rainbow_movement": "linear", "hue_spread": 1.0,
                                   "saturation": 1.0, "value": 1.0}, speed=1.0, group=group)
    lauf = color_matrix(f"{prefix} Lauflicht", fids, RgbAlgorithm.CHASE, [RED, BLUE],
                        params={"axis": "H", "movement": "normal", "runner_count": 1,
                                "runner_width": 1, "after_fade": 20.0, "color_cycle": True},
                        speed=3.0, group=group)
    fade = color_matrix(f"{prefix} Farbwechsel", fids, RgbAlgorithm.COLORFADE,
                        [RED, GREEN, BLUE, MAGENTA], params={"hold": 0.1}, speed=1.0, group=group)
    return [solid, rainbow, lauf, fade]


par_color = color_effects("PAR", par_fids, "col_par")
led_color = color_effects("LED", led_fids, "col_led")
spider_color = color_effects("Spider", spider_fids, "col_spider")

# Extra Eyecandy-Farbmatrizen (Publikum): Plasma ueber alle RGB, Feuer auf den PARs
plasma_all = color_matrix("Plasma Publikum", color_fids, RgbAlgorithm.SINEPLASMA,
                          [MAGENTA, CYAN], speed=0.8, group="col_par")
fire_par = color_matrix("Feuer PAR", par_fids, RgbAlgorithm.FIRE, [ORANGE, RED],
                        speed=1.2, group="col_par")


def mh_color_scene(name, slot):
    sc = fm.new_scene(name)
    for fid in all_mh:
        cm = chan_of[fid]
        if "color_wheel" in cm:
            sc.set_value(fid, cm["color_wheel"], slot)
    return sc


mh_solid = {nm: mh_color_scene(f"MH {nm.capitalize()}", MHCOL[nm])
            for nm in ("rot", "gruen", "blau", "gelb", "weiss", "rosa")}


def mh_color_chaser(name, scene_ids, mult=1.0):
    c = fm.new_chaser(name)
    c.run_order, c.direction = RunOrder.Loop, Direction.Forward
    c.beats_per_step = 1
    for sid in scene_ids:
        c.steps.append(ChaserStep(function_id=sid, fade_in=0.0, hold=0.4, fade_out=0.0))
    bind_tempo(c, "col_mh", mult)
    return c


mh_farbwechsel = mh_color_chaser("MH Farbwechsel",
                                 [mh_solid["rot"].id, mh_solid["gruen"].id,
                                  mh_solid["blau"].id, mh_solid["gelb"].id])


# ════════════════════════════════════════════════════════════════════════════
#  2) DIMMER & GOBO
# ════════════════════════════════════════════════════════════════════════════
def dimmer_matrix(name, fids, algo, params=None, speed=2.0, group="", prio=0):
    m = fm.new_rgb_matrix(name)
    m.algorithm = algo
    m.fixture_grid = list(fids)
    m.cols, m.rows = len(fids), 1
    m.colors = ColorSequence([WHITE])
    m.style = MatrixStyle.DIMMER    # nur Dimmer — Farbe bleibt frei
    m.drive_intensity = False
    m.matrix_speed = speed
    m.priority = prio
    if params:
        m.params = dict(params)
    if group:
        bind_tempo(m, group)
    return m


def dimmer_effects(prefix, fids, group):
    voll = dimmer_matrix(f"{prefix} Dimmer Voll", fids, RgbAlgorithm.PLAIN, speed=1.0, group=group)
    lauf = dimmer_matrix(f"{prefix} Dim-Lauflicht", fids, RgbAlgorithm.CHASE,
                         params={"axis": "H", "movement": "normal", "runner_count": 1,
                                 "runner_width": 1, "after_fade": 0.0}, speed=3.0, group=group)
    blink = dimmer_matrix(f"{prefix} Dim-Blink", fids, RgbAlgorithm.STROBE, speed=4.0, group=group)
    aufbau = dimmer_matrix(f"{prefix} Dim-Aufbau", fids, RgbAlgorithm.FILL,
                           params={"fill_mode": "up", "fill_dir": "left",
                                   "loop_mode": "reverse"}, speed=2.0, group=group)
    return [voll, lauf, blink, aufbau]


par_dim = dimmer_effects("PAR", par_fids, "dim_par")
led_dim = dimmer_effects("LED", led_fids, "dim_led")
mh_dim = dimmer_effects("MH", all_mh, "dim_mh")
spider_dim = dimmer_effects("Spider", spider_fids, "dim_spider")
# "Licht An": alle Dimmer-Voll gemeinsam (sofort volle Helligkeit -> Farbe sichtbar)
voll_all_ids = [par_dim[0].id, led_dim[0].id, mh_dim[0].id, spider_dim[0].id]


def mh_gobo_scene(name, gobo_slot, col_slot=MHCOL["weiss"]):
    sc = fm.new_scene(name)
    for fid in all_mh:
        cm = chan_of[fid]
        if "intensity" in cm:
            sc.set_value(fid, cm["intensity"], 255)
        if "shutter" in cm:
            sc.set_value(fid, cm["shutter"], MH_OPEN)
        if "color_wheel" in cm:
            sc.set_value(fid, cm["color_wheel"], col_slot)
        if "gobo_wheel" in cm:
            sc.set_value(fid, cm["gobo_wheel"], gobo_slot)
    return sc


mh_gobo = {nm: mh_gobo_scene(f"Gobo {nm}", MHGOBO[nm]) for nm in ("offen", "g1", "g3", "g5", "g7")}
gobo_wechsel = fm.new_chaser("Gobo-Wechsel")
gobo_wechsel.run_order, gobo_wechsel.direction = RunOrder.Loop, Direction.Forward
gobo_wechsel.beats_per_step = 1
for sid in (mh_gobo["g1"].id, mh_gobo["g5"].id):
    gobo_wechsel.steps.append(ChaserStep(function_id=sid, fade_in=0.0, hold=0.4, fade_out=0.0))
bind_tempo(gobo_wechsel, "gobo_mh")


# ════════════════════════════════════════════════════════════════════════════
#  3) BEWEGUNG — MH-Formen + Publikums-Sweep + Spider-Tilt (kein Pan!)
# ════════════════════════════════════════════════════════════════════════════
def efx(name, algo, fids, group, phase_mode="sync", counter=False, size=140.0,
        speed_hz=0.5, x=128.0, y=128.0, mult=1.0, rotation=0.0):
    e = fm.new_efx(name)
    e.algorithm = algo
    e.fixtures = [EfxFixture(fid=f) for f in fids]
    e.speed_hz, e.open_beam = speed_hz, True
    e.x_offset, e.y_offset = x, y
    e.width = e.height = size
    e.rotation = rotation
    e.phase_mode, e.counter_rotate = phase_mode, counter
    bind_tempo(e, group, mult)
    return e


def _wavy_circle_pts(n=48, lobes=6, amp=0.12):
    pts = []
    for i in range(n):
        t = 2 * math.pi * i / n
        r = 0.36 + amp * math.cos(lobes * t)
        pts.append((round(0.5 + r * math.cos(t), 4), round(0.5 + r * math.sin(t), 4)))
    return pts


def _heart_pts(n=40):
    pts = []
    for i in range(n):
        t = 2 * math.pi * i / n
        x = 16 * (math.sin(t) ** 3)
        yv = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        pts.append((round(max(0.0, min(1.0, x / 34.0 + 0.5)), 4),
                    round(max(0.0, min(1.0, 0.5 - yv / 34.0)), 4)))
    return pts


paths = get_efx_path_library()
wavy_path = paths.add(EfxPath("Welliger Kreis", _wavy_circle_pts(), mode="spline", closed=True))
heart_path = paths.add(EfxPath("Herz", _heart_pts(), mode="spline", closed=True))

# MH-Formen (Buehne + Publikum bewegen gemeinsam als Beam-Feld)
mh_circle = efx("MH Kreis", EfxAlgorithm.CIRCLE, all_mh, "mv_mh", phase_mode="sync", size=130)
mh_eight = efx("MH Acht", EfxAlgorithm.EIGHT, all_mh, "mv_mh", phase_mode="sync", size=150)
mh_wavy = efx("MH Welliger Kreis", EfxAlgorithm.CIRCLE, all_mh, "mv_mh", size=170)
mh_wavy.set_custom_path(wavy_path); mh_wavy.open_beam = True
mh_square = efx("MH Quadrat", EfxAlgorithm.SQUARE, all_mh, "mv_mh", phase_mode="sync", size=150)
mh_heart = efx("MH Herz", EfxAlgorithm.CIRCLE, all_mh, "mv_mh", size=170)
mh_heart.set_custom_path(heart_path); mh_heart.open_beam = True
mh_random = efx("MH Random", EfxAlgorithm.RANDOM, all_mh, "mv_mh", size=160, speed_hz=0.7)
# Publikums-Sweep: breiter horizontaler Faecher NUR ueber die 4 Seiten-MH (ins Publikum)
crowd_sweep = efx("Publikums-Sweep", EfxAlgorithm.LINE, mh_crowd, "mv_crowd",
                  phase_mode="offset", size=230, speed_hz=0.4)
MH_SHAPES = [mh_circle, mh_eight, mh_wavy, mh_square, mh_heart, mh_random]

# Spider (SPIDER14): NUR Tilt (kein Pan). LINE braucht rotation=90 (sonst statisch!).
sp_scissor = efx("Spider Schere", EfxAlgorithm.LINE, spider_fids, "mv_sp",
                 phase_mode="sync", size=210, speed_hz=0.6, rotation=90.0)
sp_wave = efx("Spider Welle", EfxAlgorithm.CIRCLE, spider_fids, "mv_sp",
              phase_mode="offset", size=180, speed_hz=0.5)
sp_wiggle = efx("Spider Wackeln", EfxAlgorithm.LINE, spider_fids, "mv_sp",
                phase_mode="sync", size=90, speed_hz=4.0, mult=2.0, rotation=90.0)


def spider_pose(name, tl, tr):
    sc = fm.new_scene(name)
    for fid in spider_fids:
        tilts = attr_chs(fid, "tilt")
        if len(tilts) >= 1:
            sc.set_value(fid, tilts[0], tl)
        if len(tilts) >= 2:
            sc.set_value(fid, tilts[1], tr)
        for ch in attr_chs(fid, "intensity"):
            sc.set_value(fid, ch, 255)
        for ch in attr_chs(fid, "shutter"):
            sc.set_value(fid, ch, SP_OPEN)
    return sc


sp_out = spider_pose("Spider Aussen", 0, 255)
sp_in = spider_pose("Spider Innen", 128, 128)
SP_MOVES = [sp_scissor, sp_wave, sp_wiggle, crowd_sweep]
SP_MULT_FX = [sp_scissor, sp_wave, sp_wiggle]


# ════════════════════════════════════════════════════════════════════════════
#  4) STROBE + ALL-WHITE-BLINDER (Publikum)
# ════════════════════════════════════════════════════════════════════════════
def strobe_fn(name, fids, prio=50):
    m = fm.new_rgb_matrix(name)
    m.algorithm = RgbAlgorithm.STROBE
    m.fixture_grid = list(fids)
    m.cols, m.rows = len(fids), 1
    m.colors = ColorSequence([WHITE])
    m.style = MatrixStyle.DIMMER
    m.drive_intensity = False
    m.matrix_speed = 8.0
    m.priority = prio
    bind_tempo(m, "strobe")
    return m


strobe_all = strobe_fn("Strobe Alle", par_fids + led_fids + all_mh + spider_fids)
strobe_par = strobe_fn("Strobe PAR", par_fids)
strobe_led = strobe_fn("Strobe LED", led_fids)
strobe_mh = strobe_fn("Strobe MH", all_mh)
STROBES = [strobe_all, strobe_par, strobe_led, strobe_mh]

# All-White Blinder (Publikum): PAR+LED voll weiss, hoechste Prioritaet.
all_white = fm.new_scene("All-White Blinder")
all_white.priority = 9999
for fid in par_fids + led_fids:
    for ch in attr_chs(fid, "intensity"):
        all_white.set_value(fid, ch, 255)
    for attr, v in (("color_r", 255), ("color_g", 255), ("color_b", 255), ("color_w", 255)):
        for ch in attr_chs(fid, attr):
            all_white.set_value(fid, ch, v)


# ════════════════════════════════════════════════════════════════════════════
#  5) LASER + NEBEL  (Safety: Arm/Estop-Tasten, Shutter aus by default)
# ════════════════════════════════════════════════════════════════════════════
# L2600 6ch: rel 1=shutter, 2=macro, 3=laser_bank, 4=color_wheel, 5=raw, 6=speed
def laser_scene(name, shutter, bank, macro=40, cw=50):
    sc = fm.new_scene(name)
    for fid in laser_fids:
        cm = chan_of[fid]
        if "shutter" in cm:
            sc.set_value(fid, cm["shutter"], shutter)
        if "laser_bank" in cm:
            sc.set_value(fid, cm["laser_bank"], bank)
        if "macro" in cm:
            sc.set_value(fid, cm["macro"], macro)
        if "color_wheel" in cm:
            sc.set_value(fid, cm["color_wheel"], cw)
    return sc


laser_pattern = laser_scene("Laser Muster", shutter=120, bank=60)
laser_beams = laser_scene("Laser Faecher", shutter=120, bank=140, macro=90, cw=90)
laser_off = laser_scene("Laser Aus", shutter=0, bank=0, macro=0, cw=0)

# Laser-Muster-Wechsel (Chaser ueber die beiden Muster-Szenen, am Master gekoppelt)
laser_chase = fm.new_chaser("Laser Muster-Wechsel")
laser_chase.run_order, laser_chase.direction = RunOrder.Loop, Direction.Forward
laser_chase.beats_per_step = 2
for sid in (laser_pattern.id, laser_beams.id):
    laser_chase.steps.append(ChaserStep(function_id=sid, fade_in=0.0, hold=0.6, fade_out=0.0))
bind_tempo(laser_chase, "laser")

# Nebel: Puff (kurz), Dauer-Haze (an), Aus.
def fog_scene(name, value):
    sc = fm.new_scene(name)
    for fid in fog_fids:
        d = dim_ch(fid)
        if d is not None:
            sc.set_value(fid, d, value)
    return sc


fog_blast = fog_scene("Nebel-Stoss", 255)
fog_haze = fog_scene("Nebel-Haze", 120)
fog_off = fog_scene("Nebel Aus", 0)


# ════════════════════════════════════════════════════════════════════════════
#  6) HARDSTYLE — Beat-Blink (Farbe pro Beat, Tempo-Bus x1)
# ════════════════════════════════════════════════════════════════════════════
def beat_blink(name, colors, prio=5):
    m = fm.new_rgb_matrix(name)
    m.algorithm = RgbAlgorithm.COLORFADE
    m.fixture_grid = list(par_fids + led_fids + spider_fids)
    m.cols, m.rows = len(m.fixture_grid), 1
    m.colors = ColorSequence([tuple(c) for c in colors])
    m.style = MatrixStyle.RGBW
    m.drive_intensity = True        # leuchtet selbst (Beat-Blitz)
    m.matrix_speed = 1.0
    m.priority = prio
    m.params = {"hold": 0.82}
    bind_tempo(m, "blink", 1.0)
    return m


blink_rrrw = beat_blink("Beat-Blink RRRW", [RED, RED, RED, WHITE])
blink_rwrw = beat_blink("Beat-Blink RWRW", [RED, WHITE, RED, WHITE])
# Dimmer-Blink (An/Aus-Puls pro Beat, Bus x2) — ueber den Farb-Blink legbar.
dim_blink = dimmer_matrix("Dimmer-Blink", par_fids + led_fids, RgbAlgorithm.STROBE,
                          speed=4.0, group="blink", prio=6)
dim_blink.tempo_multiplier = 2.0


# ════════════════════════════════════════════════════════════════════════════
#  7) AUTO-SHOW-TIMELINE (64 s Loop) — haendefreies Hardstyle-Programm
# ════════════════════════════════════════════════════════════════════════════
auto_show = fm.new_show("AUTO-SHOW Hardstyle (64s)")
auto_show.loop = True
auto_show.total_duration = 64.0


def _sf(fn, t0, dur, col="#4A90D9"):
    return ShowFunction(function_id=fn.id, start_time=t0, duration=dur, color=col)


t_col = auto_show.add_track("Farbe")
for fn, t0, dur in [(par_color[3], 0.0, 16.0), (par_color[1], 16.0, 16.0),
                    (plasma_all, 32.0, 16.0), (blink_rrrw, 48.0, 16.0)]:
    t_col.add_function(_sf(fn, t0, dur, "#3fb950"))
t_led = auto_show.add_track("LED")
t_led.add_function(_sf(led_color[1], 0.0, 32.0, "#2e7d46"))
t_led.add_function(_sf(led_color[2], 32.0, 32.0, "#2e7d46"))
t_dim = auto_show.add_track("Dimmer")
t_dim.add_function(_sf(par_dim[0], 0.0, 48.0, "#1f4a28"))
t_dim.add_function(_sf(dim_blink, 48.0, 16.0, "#5a1f1f"))
t_move = auto_show.add_track("Bewegung")
for fn, t0, dur in [(mh_circle, 0.0, 16.0), (mh_eight, 16.0, 16.0),
                    (crowd_sweep, 32.0, 16.0), (mh_heart, 48.0, 16.0)]:
    t_move.add_function(_sf(fn, t0, dur, "#1f3a6a"))
t_sp = auto_show.add_track("Spider")
t_sp.add_function(_sf(sp_scissor, 0.0, 32.0, "#1f5a5a"))
t_sp.add_function(_sf(sp_wave, 32.0, 32.0, "#1f5a5a"))
t_las = auto_show.add_track("Laser & Nebel")
t_las.add_function(_sf(laser_chase, 0.0, 64.0, "#6a1f6a"))
t_las.add_function(_sf(fog_haze, 0.0, 64.0, "#3a3a3a"))
auto_show.recalc_duration()


# ════════════════════════════════════════════════════════════════════════════
#  8) MUSIK-PLAYLIST (echte Hardstyle-/Frenchcore-Tracks) + AUTO-SHOW-KOPPLUNG
# ════════════════════════════════════════════════════════════════════════════
_HARD_GENRES = ("hardstyle", "frenchcore", "psy", "bounce", "rave", "hardtechno")


def _dup_score(p):
    return (p.lower().count("kopie"), len(p))


def _genre_rank(genre):
    """0 = Hardstyle/Frenchcore/Bounce/Psy (nach vorne), 1 = Rest."""
    g = (genre or "").lower()
    return 0 if any(k in g for k in _HARD_GENRES) else 1


def build_playlist():
    """Nur ECHTE Dateien aus MUSIC_DIR; nach dem ECHTEN Genre (guess_genre_bpm)
    sortiert — Hardstyle/Frenchcore/Bounce/Psy ZUERST, dann alphabetisch. Pfade
    mit Forward-Slashes normalisiert (Audit-Fund 2026-07-17)."""
    seen = {}
    for p in sorted(glob.glob(os.path.join(MUSIC_DIR, "*.mp3"))):
        key = clean_title(p).lower()
        if key not in seen or _dup_score(p) < _dup_score(seen[key]):
            seen[key] = p
    tracks = []
    for p in seen.values():
        genre, bpm = guess_genre_bpm(os.path.basename(p))
        tracks.append((p.replace("\\", "/"), clean_title(p), genre, float(bpm)))
    tracks.sort(key=lambda t: (_genre_rank(t[2]), t[1].lower()))
    chosen = tracks[:PLAYLIST_MAX]
    if chosen:
        return [{"path": p, "title": ti, "genre": g, "bpm": b} for p, ti, g, b in chosen], True
    fb = [("Hardstyle Hero", "Hardstyle", 150.0), ("Frenchcore Drop", "Frenchcore", 200.0),
          ("Psy-Bounce Anthem", "Bounce", 150.0), ("Rave Rush", "Hardstyle", 155.0)]
    return [{"path": MUSIC_DIR + "/" + t + ".mp3", "title": t, "genre": g, "bpm": b}
            for t, g, b in fb], False


playlist, _real = build_playlist()
state.playlist = playlist
print(f"[build] Playlist: {len(playlist)} Tracks "
      f"({'echte Dateien' if _real else 'Platzhalter — Ordner leer/fehlt'}); "
      f"Genres: {sorted({p['genre'] for p in playlist})}")

# Beim ▶ im Player: kompletter Hardstyle-Look (Farbe + Licht + Bewegung + Nebel).
state.music_autoshow = {
    "enabled": True,
    "function_ids": [par_color[3].id, par_dim[0].id, mh_circle.id, spider_color[3].id,
                     led_color[1].id, fog_haze.id],
    "bank": 5,
    "slots": {par_color[3].id: "col_par", par_dim[0].id: "dim_par",
              mh_circle.id: "mv_mh", spider_color[3].id: "col_spider",
              led_color[1].id: "col_led", fog_haze.id: "nebel"},
}


# ════════════════════════════════════════════════════════════════════════════
#  9) VIRTUELLE KONSOLE — 6 Zweck-Baenke + universelle Kopfzeile (APC 8x8)
# ════════════════════════════════════════════════════════════════════════════
PAD, GAP, X0, Y0 = 56, 6, 16, 150
STEP = PAD + GAP
RX = 470
widgets = []
BANK_ALL = -1
B_COLOR, B_DIM, B_MOVE, B_STROBE, B_LASER, B_HARD = 0, 1, 2, 3, 4, 5
PAGE_NAMES = ["Farbe", "Dimmer & Gobo", "Bewegung", "Strobe/Blinder", "Laser & Nebel", "Hardstyle/Auto"]


def note_rc(r, c):
    return (7 - r) * 8 + c


def pad_xy(r, c):
    return X0 + c * STEP, Y0 + r * STEP


def _add(w, x, y, ww, hh, bank):
    w.bank = bank
    w.setGeometry(x, y, ww, hh)
    widgets.append(w.to_dict())


def fx_btn(fn, r, c, bank, accent, slot, note=None, bg=None):
    b = VCButton(fn.name)
    b.action = ButtonAction.FUNCTION_TOGGLE
    b.function_id = fn.id
    b.edit_slot = slot
    b.pad_style = "pulse"
    b._bg_color.setNamedColor(accent)
    if bg:
        b.bg_image = bgimg(bg)
    if note is not None:
        b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, note
    x, y = pad_xy(r, c)
    _add(b, x, y, PAD, PAD, bank)


def swatch(name, r, c, bank, rgb, slot, note=None):
    cc = VCColor(name)
    cc.color_r, cc.color_g, cc.color_b = rgb
    cc.color_w = 0
    cc.with_intensity = False
    cc.target = ColorTarget.EFFECT_C1
    cc.edit_slot = slot
    if note is not None:
        cc.midi_type, cc.midi_ch, cc.midi_data1 = "note_on", 0, note
    x, y = pad_xy(r, c)
    _add(cc, x, y, PAD, PAD, bank)


def action_btn(name, action, x, y, bank, accent, ww=64, hh=26, function_id=None,
               function_ids=None, group=None, tempo_bus_id=None, note=None, style="solid", bg=None):
    b = VCButton(name)
    b.action = action
    if function_id is not None:
        b.function_id = function_id
    if function_ids is not None:
        b.function_ids = list(function_ids)
    if group is not None:
        b.group_name = group
    if tempo_bus_id is not None:
        b.tempo_bus_id = tempo_bus_id
    b.pad_style = style
    b._bg_color.setNamedColor(accent)
    if bg:
        b.bg_image = bgimg(bg)
    if note is not None:
        b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, note
    _add(b, x, y, ww, hh, bank)


def pad_action(name, action, r, c, bank, accent, function_id=None, function_ids=None,
               group=None, note=None, style="solid", bg=None):
    x, y = pad_xy(r, c)
    action_btn(name, action, x, y, bank, accent, ww=PAD, hh=PAD, function_id=function_id,
               function_ids=function_ids, group=group, note=note, style=style, bg=bg)


def flash_btn(fn, r, c, bank, accent, note=None, bg=None):
    b = VCButton(fn.name)
    b.action = ButtonAction.FUNCTION_FLASH
    b.function_id = fn.id
    b.pad_style = "solid"
    b._bg_color.setNamedColor(accent)
    if bg:
        b.bg_image = bgimg(bg)
    if note is not None:
        b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, note
    x, y = pad_xy(r, c)
    _add(b, x, y, PAD, PAD, bank)


def speed_dial(caption, x, y, bank, function_ids, ww=150, hh=146):
    w = VCSpeedDial(caption)
    w.target_mode = SpeedTarget.TEMPO_BUS_MULT
    w.function_ids = [f.id for f in function_ids]
    w.factor_buttons = [0.25, 0.5, 1.0, 2.0, 3.0, 4.0]
    w.show_dial = False
    w.show_tap = False
    w.show_sync = False
    w.show_factors = True
    w.show_bpm = True
    _add(w, x, y, ww, hh, bank)


def master_fader(caption, x, y, bank, mode, group="", value=255, midi_cc=-1):
    s = VCSlider(caption)
    s.mode = mode
    s.programmer_group = group
    s.midi_cc, s.midi_ch = midi_cc, 0
    s._value = value
    _add(s, x, y, 50, 150, bank)


def eff_colors(caption, x, y, bank, slot, ww=224, hh=70):
    w = VCEffectColors(caption)
    w.edit_slot = slot
    _add(w, x, y, ww, hh, bank)


def bpm_display(caption, x, y, bank, tempo_bus_id="", ww=180, hh=92):
    w = VCBpmDisplay(caption)
    w.tempo_bus_id = tempo_bus_id
    _add(w, x, y, ww, hh, bank)


def xy_pad(caption, x, y, bank, fids, mode, efx_function_id=None, ww=180, hh=180):
    w = VCXYPad(caption)
    w.mode = mode
    w._fixture_ids = list(fids)
    w.bits16 = True
    if efx_function_id is not None:
        w.efx_function_id = efx_function_id
    _add(w, x, y, ww, hh, bank)


def effect_editor_box(caption, x, y, bank, function_id, ww=224, hh=180):
    w = VCEffectEditor(caption)
    w.set_effect(int(function_id))
    w.build_default_controls()
    _add(w, x, y, ww, hh, bank)


def song_info(x, y, bank, ww=200, hh=58, caption="Aktuelles Lied"):
    _add(VCSongInfo(caption), x, y, ww, hh, bank)


def label(text, x, y, ww, bank, hh=18):
    _add(VCLabel(text), x, y, ww, hh, bank)


# ── Universelle Kopfzeile (alle Baenke, y<140) ───────────────────────────────
HZ1, HZ2 = 8, 40
action_btn("Programmer leeren", ButtonAction.CLEAR, X0, HZ1, BANK_ALL, "#4a3a10", ww=92, note=100)
action_btn("Effekt-Stop", ButtonAction.STOP_EFFECTS, X0 + 98, HZ1, BANK_ALL, "#4a1010", ww=92, note=101)
action_btn("BLACKOUT", ButtonAction.BLACKOUT, X0 + 196, HZ1, BANK_ALL, "#2a0000", ww=92, note=102)
action_btn("Licht An", ButtonAction.FUNCTION_TOGGLE, X0 + 294, HZ1, BANK_ALL, "#2a4a2a", ww=92,
           function_ids=voll_all_ids, note=103, bg="hot_white")
action_btn("Tap", ButtonAction.TAP, X0, HZ2, BANK_ALL, "#103a3a", ww=70, note=104)
action_btn("Musik-BPM", ButtonAction.AUDIO_BPM, X0 + 76, HZ2, BANK_ALL, "#103a4a", ww=92, note=105)
action_btn("◀ Lied", ButtonAction.MEDIA_PREV, X0 + 174, HZ2, BANK_ALL, "#3a2150", ww=70, note=106)
action_btn("▶/||", ButtonAction.MEDIA_PLAY_PAUSE, X0 + 248, HZ2, BANK_ALL, "#5a2080", ww=64, note=107)
action_btn("Lied ▶", ButtonAction.MEDIA_NEXT, X0 + 316, HZ2, BANK_ALL, "#3a2150", ww=70, note=108)
bpm_display("MASTER BPM", RX, HZ1, BANK_ALL, tempo_bus_id="", ww=170, hh=88)
action_btn("◆ SYNC", ButtonAction.SYNC_BUS, RX + 178, HZ1, BANK_ALL, "#1f6a5a", ww=92, tempo_bus_id=BUS)
action_btn("Auto-Sync", ButtonAction.AUTO_SYNC, RX + 178, HZ1 + 32, BANK_ALL, "#3a5a1f", ww=92)
action_btn("Freeze", ButtonAction.FREEZE, RX + 274, HZ1, BANK_ALL, "#103a4a", ww=92)
song_info(RX + 274, HZ2, BANK_ALL, ww=210, hh=64)
label("MEGA ARENA 2026 — Farbe · Dimmer · Bewegung · Strobe · Laser+Nebel · Hardstyle. "
      "Effekte folgen der MASTER-BPM (Musik/Tap) mit eigenem Multiplikator (¼…4×). "
      "Kategorien layern. Licht An = sofort hell. 4 Trassen: Front/Back + Seiten ins Publikum.",
      X0, 124, 940, BANK_ALL)

CA, CB = RX, RX + 162

# ── BANK 0 — FARBE ───────────────────────────────────────────────────────────
ACC = ["#1f5a3a", "#5a3a1f", "#1f3a6a", "#5a1f6a"]
CBG = ["hot_white", "rainbow_scroll", "color_chase", "breathe_rgb"]
for i, fn in enumerate(par_color):
    fx_btn(fn, 0, i, B_COLOR, ACC[i], "col_par", note=note_rc(0, i), bg=CBG[i])
for i, fn in enumerate(led_color):
    fx_btn(fn, 1, i, B_COLOR, ACC[i], "col_led", note=note_rc(1, i))
fx_btn(plasma_all, 0, 5, B_COLOR, "#6a1f6a", "col_par", note=note_rc(0, 5), bg="spectrum")
fx_btn(fire_par, 1, 5, B_COLOR, "#7a2a00", "col_par", note=note_rc(1, 5), bg="strobe")
PAR_SW = [("Rot", RED), ("Grün", GREEN), ("Blau", BLUE), ("Gelb", YELLOW), ("Magenta", MAGENTA), ("Cyan", CYAN)]
for i, (nm, c) in enumerate(PAR_SW):
    swatch(nm, 2, i, B_COLOR, c, "col_par", note=note_rc(2, i))
for i, nm in enumerate(("rot", "gruen", "blau", "gelb", "weiss", "rosa")):
    fx_btn(mh_solid[nm], 3, i, B_COLOR, "#3a5a1f", "col_mh", note=note_rc(3, i))
fx_btn(mh_farbwechsel, 4, 0, B_COLOR, "#5a1f6a", "col_mh", note=note_rc(4, 0), bg="color_wheel")
for i, fn in enumerate(spider_color):
    fx_btn(fn, 5, i, B_COLOR, ACC[i], "col_spider", note=note_rc(5, i))
label("PAR", X0, Y0 - 16, 60, B_COLOR); label("LED", X0, pad_xy(1, 0)[1] - 16, 60, B_COLOR)
label("PAR-Farben", X0, pad_xy(2, 0)[1] - 16, 120, B_COLOR)
label("MH-Farbe", X0, pad_xy(3, 0)[1] - 16, 90, B_COLOR)
label("Spider", X0, pad_xy(5, 0)[1] - 16, 60, B_COLOR)
speed_dial("PAR ×", CA, Y0, B_COLOR, par_color)
speed_dial("LED ×", CA, Y0 + 150, B_COLOR, led_color)
speed_dial("Spider ×", CA, Y0 + 300, B_COLOR, spider_color)
eff_colors("PAR Farben", CB, Y0, B_COLOR, "col_par")
eff_colors("Spider Farben", CB, Y0 + 74, B_COLOR, "col_spider")
effect_editor_box("Editor: aktiver PAR-Farbeffekt", CB, Y0 + 150, B_COLOR, par_color[2].id)
label("BANK 1 FARBE — R0 PAR · R1 LED · R2 PAR-Farben · R3 MH-Farbe · R4 MH-Wechsel · R5 Spider. "
      "Nur RGB (Helligkeit von Bank Dimmer / Licht An).", X0, Y0 + 6 * STEP, 440, B_COLOR)

# ── BANK 1 — DIMMER & GOBO ───────────────────────────────────────────────────
for gi, (lbl, effs, slot) in enumerate([("PAR", par_dim, "dim_par"), ("LED", led_dim, "dim_led"),
                                        ("MH", mh_dim, "dim_mh"), ("Spider", spider_dim, "dim_spider")]):
    for i, fn in enumerate(effs):
        fx_btn(fn, gi, i, B_DIM, "#1f3a6a", slot, note=note_rc(gi, i))
    label(lbl, X0, pad_xy(gi, 0)[1] - 16, 60, B_DIM)
    speed_dial(f"{lbl} ×", CA, Y0 + (gi % 3) * 150, B_DIM, effs) if gi < 3 else None
for i, nm in enumerate(("offen", "g1", "g3", "g5", "g7")):
    fx_btn(mh_gobo[nm], 4, i, B_DIM, "#5a3a1f", "gobo_mh", note=note_rc(4, i), bg="gobo_spin" if i == 1 else None)
fx_btn(gobo_wechsel, 4, 5, B_DIM, "#7a6500", "gobo_mh", note=note_rc(4, 5), bg="gobo_spin")
label("MH-Gobo", X0, pad_xy(4, 0)[1] - 16, 90, B_DIM)
effect_editor_box("Editor: aktive PAR-Dimmer-Matrix", CB, Y0 + 300, B_DIM, par_dim[1].id)
label("BANK 2 DIMMER & GOBO — R0-3 Dimmer (Voll/Lauflicht/Blink/Aufbau) je Gruppe (nur Dimmer). "
      "R4 MH-Gobos. Rechts: Speed × + Editor.", X0, Y0 + 6 * STEP, 440, B_DIM)

# ── BANK 2 — BEWEGUNG ────────────────────────────────────────────────────────
SHP = ["#1f3a6a", "#1f4a6a", "#1f5a6a", "#3a1f6a", "#6a1f4a", "#2a6a2a"]
for i, fn in enumerate(MH_SHAPES):
    fx_btn(fn, i // 3, i % 3, B_MOVE, SHP[i], "mv_mh", note=note_rc(i // 3, i % 3),
           bg="beam_sweep" if i == 0 else None)
label("MH-Form (Buehne + Publikum)", X0, Y0 - 16, 220, B_MOVE)
fx_btn(crowd_sweep, 2, 0, B_MOVE, "#8a5a00", "mv_crowd", note=note_rc(2, 0), bg="beam_sweep")
label("Publikums-Sweep (Seiten-MH)", X0, pad_xy(2, 0)[1] - 16, 220, B_MOVE)
for i, fn in enumerate(SP_MOVES):
    fx_btn(fn, 3 + i // 3, i % 3, B_MOVE, "#1f5a5a", "mv_sp", note=note_rc(3 + i // 3, i % 3),
           bg="sparkle" if i == 0 else None)
for i, sc in enumerate((sp_out, sp_in)):
    fx_btn(sc, 4, 3 + i, B_MOVE, "#2a4a4a", "mv_sp", note=note_rc(4, 3 + i))
label("Spider-Tilt (kein Pan!) + Posen", X0, pad_xy(3, 0)[1] - 16, 240, B_MOVE)
xy_pad("MH Bereich (Box aufziehen)", CA, Y0, B_MOVE, all_mh, "area", efx_function_id=mh_circle.id)
speed_dial("MH ×", CA, Y0 + 188, B_MOVE, MH_SHAPES + [crowd_sweep])
speed_dial("Spider ×", CA + 162, Y0 + 188, B_MOVE, SP_MULT_FX)
label("BANK 3 BEWEGUNG — R0-1 MH-Formen · R2 Publikums-Sweep (Seiten) · R3-4 Spider-Tilt + Posen. "
      "Rechts: XY-Bereich + Speeds.", X0, Y0 + 6 * STEP, 440, B_MOVE)

# ── BANK 3 — STROBE / BLINDER ────────────────────────────────────────────────
SNAMES_BG = ["strobe", "strobe", "strobe", "strobe"]
for i, fn in enumerate(STROBES):
    flash_btn(fn, 0, i, B_STROBE, "#551111", note=note_rc(0, i), bg="strobe" if i == 0 else None)
for i, fn in enumerate(STROBES):
    fx_btn(fn, 1, i, B_STROBE, "#7a2222", "strobe", note=note_rc(1, i))
pad_action("All-White Blinder", ButtonAction.ALL_WHITE, 3, 0, B_STROBE, "#888888",
           function_id=all_white.id, note=note_rc(3, 0), bg="hot_white")
label("R0 Strobe HALTEN · R1 Strobe TOGGLE · R3 All-White-Blinder (Publikum, halten)",
      X0, Y0 - 16, 420, B_STROBE)
speed_dial("Strobe-Rate ×", CA, Y0, B_STROBE, STROBES)
effect_editor_box("Editor: Strobe Alle", CB, Y0, B_STROBE, strobe_all.id, ww=224, hh=190)
label("BANK 4 STROBE — R0 halten · R1 toggeln (Alle/PAR/LED/MH) · R3 All-White-Blinder. "
      "Rechts: Rate + Editor.", X0, Y0 + 6 * STEP, 440, B_STROBE)

# ── BANK 4 — LASER & NEBEL ───────────────────────────────────────────────────
fx_btn(laser_pattern, 0, 0, B_LASER, "#6a1f6a", "laser", note=note_rc(0, 0), bg="beam_sweep")
fx_btn(laser_beams, 0, 1, B_LASER, "#8a1f8a", "laser", note=note_rc(0, 1), bg="beam_sweep")
fx_btn(laser_chase, 0, 2, B_LASER, "#7a2a7a", "laser", note=note_rc(0, 2))
pad_action("Laser AUS", ButtonAction.FUNCTION_TOGGLE, 0, 3, B_LASER, "#333333", function_id=laser_off.id)
label("LASER-MUSTER (Bank/Fächer/Wechsel/Aus)", X0, Y0 - 16, 320, B_LASER)
action_btn("⚡ Laser ARM", ButtonAction.LASER_ARM, X0, pad_xy(2, 0)[1], B_LASER, "#1f5a1f", ww=150, hh=48, note=note_rc(2, 0))
action_btn("■ Laser NOT-AUS", ButtonAction.LASER_ESTOP, X0 + 158, pad_xy(2, 0)[1], B_LASER, "#7a0000", ww=170, hh=48, note=note_rc(2, 1))
label("LASER-SAFETY: erst ARM, dann Muster. NOT-AUS = harter Latch (alle Laser auf 0).",
      X0, pad_xy(2, 0)[1] + 54, 440, B_LASER)
fx_btn(fog_blast, 4, 0, B_LASER, "#3a5a5a", "nebel", note=note_rc(4, 0), bg="vu_meter")
fx_btn(fog_haze, 4, 1, B_LASER, "#2a4a4a", "nebel", note=note_rc(4, 1))
pad_action("Nebel Aus", ButtonAction.FUNCTION_TOGGLE, 4, 2, B_LASER, "#222222", function_id=fog_off.id)
label("NEBEL (Boden vor dem Publikum): Stoß / Haze / Aus", X0, pad_xy(4, 0)[1] - 16, 360, B_LASER)
c_laser = VCColor("Laser Farbe (Programmer)")
c_laser.target = ColorTarget.PROGRAMMER
_add(c_laser, CA, Y0, 220, 180, B_LASER)
label("BANK 5 LASER & NEBEL — R0 Laser-Muster · ARM/NOT-AUS-Safety · R4 Nebel. Rechts: Farbe.",
      X0, Y0 + 6 * STEP, 440, B_LASER)

# ── BANK 5 — HARDSTYLE / AUTO / MASTER ───────────────────────────────────────
bpm_display("MASTER", CA, Y0, B_HARD, tempo_bus_id="", ww=150, hh=82)
action_btn("TAP", ButtonAction.TAP, CA, Y0 + 90, B_HARD, "#103a3a", ww=72, hh=40)
action_btn("AUTO/MAN", ButtonAction.BPM_MODE_TOGGLE, CA + 78, Y0 + 90, B_HARD, "#22324a", ww=72, hh=40)
action_btn("BPM -", ButtonAction.BPM_NUDGE_DOWN, CA, Y0 + 138, B_HARD, "#22324a", ww=72, hh=34)
action_btn("BPM +", ButtonAction.BPM_NUDGE_UP, CA + 78, Y0 + 138, B_HARD, "#22324a", ww=72, hh=34)
# Beat-Blink RRRW / RWRW (exklusiv gegeneinander via actions) + Dimmer-Blink drueber
b_rrrw = VCButton("RRRW"); b_rrrw.action = ButtonAction.FUNCTION_TOGGLE
b_rrrw.function_id = blink_rrrw.id; b_rrrw.edit_slot = "blink"; b_rrrw._bg_color.setNamedColor("#4a1530")
b_rrrw.bg_image = bgimg("strobe"); b_rrrw.midi_type, b_rrrw.midi_ch, b_rrrw.midi_data1 = "note_on", 0, note_rc(0, 0)
_add(b_rrrw, *pad_xy(0, 0), PAD, PAD, B_HARD)
b_rwrw = VCButton("RWRW"); b_rwrw.action = ButtonAction.FUNCTION_TOGGLE
b_rwrw.function_id = blink_rwrw.id; b_rwrw.edit_slot = "blink"; b_rwrw._bg_color.setNamedColor("#4a1530")
b_rwrw.midi_type, b_rwrw.midi_ch, b_rwrw.midi_data1 = "note_on", 0, note_rc(0, 1)
_add(b_rwrw, *pad_xy(0, 1), PAD, PAD, B_HARD)
fx_btn(dim_blink, 0, 2, B_HARD, "#5a1f1f", "blink2", note=note_rc(0, 2), bg="pulse")
label("BEAT-BLINK (Farbe pro Beat) + Dimmer-Blink", X0, Y0 - 16, 320, B_HARD)
eff_colors("RRRW Farben (umfärbbar)", X0, pad_xy(1, 0)[1], B_HARD, "blink", ww=300, hh=84)
# Auto-Show + Licht An
pad_action("AUTO-SHOW", ButtonAction.FUNCTION_TOGGLE, 3, 0, B_HARD, "#b8860b",
           function_id=auto_show.id, note=note_rc(3, 0), bg="spectrum")
pad_action("Licht An", ButtonAction.FUNCTION_TOGGLE, 3, 1, B_HARD, "#2a4a2a",
           function_ids=voll_all_ids, note=note_rc(3, 1), bg="hot_white")
pad_action("Nebel-Haze", ButtonAction.FUNCTION_TOGGLE, 3, 2, B_HARD, "#2a4a4a",
           function_id=fog_haze.id, note=note_rc(3, 2))
label("AUTO-SHOW (Loop) · Licht An · Nebel", X0, pad_xy(3, 0)[1] - 16, 320, B_HARD)
song_info(X0, pad_xy(4, 0)[1], B_HARD, ww=300, hh=64)
# Speeds + Master-Dimmer
speed_dial("Farbe ×", CA, Y0 + 190, B_HARD, par_color + led_color + spider_color)
speed_dial("Bewegung ×", CA + 162, Y0 + 190, B_HARD, MH_SHAPES + SP_MULT_FX + [crowd_sweep])
MFX = CB + 250
master_fader("Spider", MFX, Y0, B_HARD, SliderMode.GROUP_DIMMER, group="Spider", midi_cc=52)
master_fader("MH", MFX + 54, Y0, B_HARD, SliderMode.GROUP_DIMMER, group="Moving Heads", midi_cc=53)
master_fader("LED", MFX + 108, Y0, B_HARD, SliderMode.GROUP_DIMMER, group="LED Bars", midi_cc=54)
master_fader("PAR", MFX + 162, Y0, B_HARD, SliderMode.GROUP_DIMMER, group="Alle PAR", midi_cc=55)
master_fader("GRAND", MFX + 216, Y0, B_HARD, SliderMode.GRANDMASTER, midi_cc=56)
label("BANK 6 HARDSTYLE — BPM/Tap · Beat-Blink RRRW/RWRW + Dimmer-Blink · AUTO-SHOW · "
      "Speeds · 5 Master-Dimmer (Spider/MH/LED/PAR/GRAND).", X0, Y0 + 6 * STEP, 440, B_HARD)


# ════════════════════════════════════════════════════════════════════════════
#  10) STAGE — 4 Trassen (Front/Back ueber Buehne, Seiten ins Publikum) + Docks
# ════════════════════════════════════════════════════════════════════════════
sd = StageDefinition(name=STAGE_NAME)
front = sd.add("truss_h", x=0, y=5.5, z=2.6,  w=16, h=0.3, d=0.3, name="Front-Traverse (Buehne)")
back  = sd.add("truss_h", x=0, y=5.8, z=-2.6, w=16, h=0.3, d=0.3, name="Back-Traverse (Buehne)")
sideL = sd.add("truss_h", x=-8.5, y=5.0, z=3.5, w=0.3, h=0.3, d=10, name="Seiten-Traverse Links (Publikum)")
sideR = sd.add("truss_h", x=8.5,  y=5.0, z=3.5, w=0.3, h=0.3, d=10, name="Seiten-Traverse Rechts (Publikum)")
for sx in (-8, 8):
    for sz in (2.6, -2.6):
        sd.add("truss_v", x=sx, y=2.75, z=sz, w=0.3, h=5.5, d=0.3, name=f"Stuetze {sx},{sz}")
sd.add("platform", x=0, y=0.3, z=-0.5, w=18, h=0.6, d=6, name="Buehne")
save_stage(sd)
state.active_stage_name = STAGE_NAME

scene = state._scene
for el in sd.elements:
    try:
        kind = NodeKind(el.type)
    except ValueError:
        kind = NodeKind.PLATFORM
    scene.add(SceneNode(
        id=el.id, kind=kind,
        transform=Transform(pos_m=(float(el.x), float(el.y), float(el.z)),
                            rot_deg=(0.0, math.degrees(el.rotation), 0.0)),
        parent_id=None, size_m=(float(el.w), float(el.h), float(el.d)),
        color=el.color, name=el.name))
state._notify_scene_changed()

# ── Fixtures anordnen (3D + 2D) + an Trassen haengen ─────────────────────────
def _spread(n, lo, hi):
    if n == 1:
        return [(lo + hi) / 2]
    return [lo + (hi - lo) * i / (n - 1) for i in range(n)]


pos = state.visualizer_positions
dock = state.visualizer_docks

# 8 PAR am Boden vorne (Publikums-Wash), 4 PAR an der Front-Truss
for fid, x in zip(par_fids[:8], _spread(8, -7.0, 7.0)):
    pos[fid] = (x, 0.3, 3.4)
for fid, x in zip(par_fids[8:], _spread(4, -6.0, 6.0)):
    pos[fid] = (x, 5.2, 2.6); dock[fid] = front.id
# 4 Spider + 2 LED an der Front-Truss
for fid, x in zip(spider_fids, _spread(4, -5.0, 5.0)):
    pos[fid] = (x, 5.2, 2.6); dock[fid] = front.id
for fid, x in zip(led_fids, (-7.5, 7.5)):
    pos[fid] = (x, 5.2, 2.6); dock[fid] = front.id
# 2 MH16(Buehne) + 2 ZQ02001 an der Back-Truss
for fid, x in zip(mh_stage, _spread(4, -6.0, 6.0)):
    pos[fid] = (x, 5.4, -2.6); dock[fid] = back.id
# 4 Publikums-MH an den Seiten-Trussen (2 links, 2 rechts), zeigen ins Publikum (+z)
for fid, z in zip(mh_crowd[:2], (1.0, 6.0)):
    pos[fid] = (-8.5, 4.8, z); dock[fid] = sideL.id
for fid, z in zip(mh_crowd[2:], (1.0, 6.0)):
    pos[fid] = (8.5, 4.8, z); dock[fid] = sideR.id
# 4 Laser: 2 hoch auf der Back-Truss, je 1 auf den Seiten-Trussen
for fid, x in zip(laser_fids[:2], (-3.0, 3.0)):
    pos[fid] = (x, 6.1, -2.6); dock[fid] = back.id
pos[laser_fids[2]] = (-8.5, 5.2, 3.5); dock[laser_fids[2]] = sideL.id
pos[laser_fids[3]] = (8.5, 5.2, 3.5); dock[laser_fids[3]] = sideR.id
# 2 Nebel am Boden VOR dem Publikum (grosses +z, tief)
for fid, x in zip(fog_fids, (-5.0, 5.0)):
    pos[fid] = (x, 0.2, 5.5)

# Ausrichtung (Montage-Rotation, Euler XYZ Grad): die 4 Publikums-MH auf den
# Seiten-Trussen nach VORNE ins Publikum kippen. rx<0 -> Ruhestrahl (0,-1,0) zeigt
# nach unten+vorne (+z, ins Publikum); leichte Gegen-Gierung -> Konvergenz Mitte.
rot = state.visualizer_rotations
for fid in mh_crowd[:2]:      # Links-Truss (x=-8.5) -> nach rechts+vorne
    rot[fid] = (-55.0, 22.0, 0.0)
for fid in mh_crowd[2:]:      # Rechts-Truss (x=+8.5) -> nach links+vorne
    rot[fid] = (-55.0, -22.0, 0.0)
# BEWUSST KEIN state.live_view_positions: eine 2D-Live-View-Position wuerde die
# expliziten 3D-Truss-Positionen via live_to_world3d ueberschreiben (Audit-Fund
# 2026-07-17 — Mover landeten sonst bei z=20 m / falschem x). Die 2D-View leitet
# sich bei Bedarf aus dem 3D ab (world3d_to_live).


# ════════════════════════════════════════════════════════════════════════════
#  11) FINALISIEREN + SPEICHERN
# ════════════════════════════════════════════════════════════════════════════
state._vc_layout = {"widgets": widgets}
state.programmer = {}
state.show_name = "Mega Arena 2026"
get_tempo_bus_manager().set_auto_sync(True)
# Hardstyle-Grundtempo seeden (Global folgt zur Laufzeit der Musik-BPM/Tap).
from src.core.engine.bpm_manager import get_bpm_manager as _gbm
_gbm().request_bpm(150.0, "seed")

pe = state.playback_engine
try:
    for idx, nm in enumerate(PAGE_NAMES):
        if 0 <= idx < len(pe.page_names):
            pe.page_names[idx] = nm
    pe.set_page(0)
except Exception as e:
    print(f"[build] page name error: {e}")

save_show(OUT)
print(f"Gespeichert: {OUT}")

# ── Lint (nur ECHTE Bausteine?) ──────────────────────────────────────────────
from src.core.capability.validate import assert_lshow, validate_show_live, ERROR as _LINT_ERR
assert_lshow(OUT)
print("Lint (statisch): OK")

ok, msg = load_show(OUT)
assert ok, f"Show laedt nicht: {msg}"
state = get_state()
fm = get_function_manager()
_live = validate_show_live(state)
assert not [x for x in _live if x.severity == _LINT_ERR], \
    "Live-Lint-Fehler:\n" + "\n".join(str(x) for x in _live)
print(f"Lint (live): OK ({len(_live)} Hinweise)")


# ════════════════════════════════════════════════════════════════════════════
#  12) VERIFIKATION — Struktur + bewegtes DMX
# ════════════════════════════════════════════════════════════════════════════
from collections import Counter
from src.core.engine.rgb_matrix import RgbMatrixInstance, MatrixStyle as MS
from src.core.engine.efx import EfxInstance
from src.core.engine.show_engine import Show
from src.core.engine.bpm_manager import get_bpm_manager

fx = state.get_patched_fixtures()
assert len(fx) == 32, f"Fixtures: {len(fx)}"
by_type = Counter(f.fixture_type for f in fx)
# Spider (SPIDER14) tragen selbst den Typ 'moving_head' -> 8 echte MH + 4 Spider = 12.
for t, n in (("par", 12), ("moving_head", 12), ("led_bar", 2), ("laser", 4), ("hazer", 2)):
    assert by_type.get(t, 0) == n, f"{t}: {by_type.get(t)} != {n}"
assert len(spider_fids) == 4 and len(all_mh) == 8, "Spider/MH-Aufteilung driftet"

# ── Geometrie-Beweis: 4 Trassen korrekt bestueckt (Audit-Fix 2026-07-17) ──────
vpos = state.visualizer_positions
vrot = state.visualizer_rotations
for fid in mh_crowd:
    assert abs(vpos[fid][0]) > 7.5, f"Publikums-MH {fid} nicht seitlich (x=+-8.5): {vpos[fid]}"
    assert vpos[fid][2] > 0, f"Publikums-MH {fid} zeigt nicht Richtung Publikum (+z): {vpos[fid]}"
for fid in mh_stage:
    assert vpos[fid][2] < 0, f"Buehnen-MH {fid} nicht hinten (Back-Truss z<0): {vpos[fid]}"
for fid in spider_fids:
    assert 2.0 < vpos[fid][2] < 4.0, f"Spider {fid} nicht an Front-Truss (z~2.6): {vpos[fid]}"
for fid in fog_fids:
    assert vpos[fid][1] < 1.0 and vpos[fid][2] > 4.0, f"Nebel {fid} nicht Boden-vorne: {vpos[fid]}"
assert all(tuple(vrot.get(fid) or (0, 0, 0)) != (0, 0, 0) for fid in mh_crowd), \
    "Publikums-MH ohne Montage-Ausrichtung (rotations leer)"
try:
    _ndock = sum(1 for f in state.get_patched_fixtures() if state.visualizer_docks.get(f.fid))
except Exception:
    _ndock = -1
print(f"  [OK] Geometrie: Publikums-MH x=+-8.5 ins Publikum (+z), Buehnen-MH hinten (z<0), "
      f"Spider Front (z~2.6), Nebel Boden-vorne; Docks={_ndock}")

vc = state._vc_layout.get("widgets", [])
types = Counter(w["type"] for w in vc)
banks = Counter(w.get("bank") for w in vc)
assert set(banks) == {0, 1, 2, 3, 4, 5, -1}, f"Banks: {sorted(banks)}"
# LAYERING: KEIN global-exklusiver Button (kein stop_all-Muster)
assert not any(w.get("exclusive") for w in vc if w["type"] == "VCButton"), "global-exklusive Buttons!"
slots = {w.get("edit_slot") for w in vc if w.get("edit_slot")}
for need in ("col_par", "col_led", "col_mh", "col_spider", "dim_par", "dim_led", "dim_mh",
             "dim_spider", "mv_mh", "mv_crowd", "mv_sp", "strobe", "laser", "nebel", "blink"):
    assert need in slots, f"edit_slot fehlt: {need} ({sorted(slots)})"
for t in ("VCButton", "VCSlider", "VCColor", "VCSpeedDial", "VCBpmDisplay", "VCEffectColors",
          "VCXYPad", "VCSongInfo", "VCEffectEditor", "VCLabel"):
    assert types.get(t, 0) >= 1, f"Widget-Typ fehlt: {t} ({dict(types)})"
# Laser-Safety-Tasten vorhanden
acts = Counter(w.get("action") for w in vc if w["type"] == "VCButton")
assert acts.get("LaserArm", 0) >= 1 and acts.get("LaserEstop", 0) >= 1, f"Laser-Safety fehlt: {dict(acts)}"
assert acts.get("Blackout", 0) >= 1, "BLACKOUT fehlt"

# bg_image portabel eingebettet?
imgs = [w for w in vc if w["type"] == "VCButton" and w.get("bg_image")]
assert len(imgs) >= 8, f"zu wenige Galerie-Buttons: {len(imgs)}"

# Master-Kopplung
bound = [f for f in fm.all() if getattr(f, "tempo_bus_id", "") == BUS]
assert len(bound) >= 25, f"an Master gekoppelt: {len(bound)}"
named = {b.bus_id: b for b in get_tempo_bus_manager().named_buses()}
assert named[BUS].source == "bpm_global", f"Global folgt nicht der Musik: {named[BUS].source}"
assert get_tempo_bus_manager().auto_sync is True, "Auto-Sync nicht persistiert"
assert state.implicit_brightness is False, "strikte Farbe/Dimmer-Trennung nicht persistiert"

# Musik + Auto-Show
assert 1 <= len(state.playlist) <= PLAYLIST_MAX, f"Playlist: {len(state.playlist)}"
ma = state.music_autoshow
fn_ids = {f.id for f in fm.all()}
assert ma.get("enabled") and all(fid in fn_ids for fid in ma.get("function_ids", [])), ma
shows = [f for f in fm.all() if isinstance(f, Show)]
assert shows and shows[0].loop and len(shows[0].tracks) >= 5, "AUTO-SHOW-Timeline fehlt/zu klein"

# Keine Overlaps interaktiver Widgets je Bank
_INTER = {"VCButton", "VCSlider", "VCColor", "VCXYPad", "VCSpeedDial", "VCBpmDisplay",
          "VCEffectColors", "VCSongInfo", "VCEffectEditor"}


def _rect(w):
    return (w.get("x", 0), w.get("y", 0), w.get("x", 0) + w.get("w", 0), w.get("y", 0) + w.get("h", 0))


def _ov(a, b):
    ax0, ay0, ax1, ay1 = _rect(a); bx0, by0, bx1, by1 = _rect(b)
    return not (ax1 <= bx0 or bx1 <= ax0 or ay1 <= by0 or by1 <= ay0)


for bk in range(6):
    layer = [w for w in vc if w.get("bank") in (bk, -1) and w["type"] in _INTER]
    for a in range(len(layer)):
        for b2 in range(a + 1, len(layer)):
            assert not _ov(layer[a], layer[b2]), (
                f"Overlap Bank {bk}: {layer[a]['type']}@{_rect(layer[a])} vs "
                f"{layer[b2]['type']}@{_rect(layer[b2])}")

# ── Render-Sanity: gelayerte Effekte -> echtes, SICH BEWEGENDES DMX ──────────
get_bpm_manager().request_bpm(150.0, "diag")
_bn = {f.name: f for f in fm.all()}
for nm in ("PAR Farbwechsel", "PAR Dimmer Voll", "MH Kreis", "Spider Schere",
           "Publikums-Sweep", "Nebel-Haze"):
    fm.start(_bn[nm].id)

u = state.universes.get(1)
u2 = state.universes.get(2)


def d1(ch):
    return int(u.get_channel(ch)) if u else 0


def d2(ch):
    return int(u2.get_channel(ch)) if u2 else 0


# Repraesentative Adressen: PAR1 intensity @1, MH16-1 pan @97, Spider1 tilt @215, Fog1 @25(U2)
mh_pan_abs = fx_of[mh16_fids[0]].address           # rel1 pan
sp_tilt_abs = fx_of[spider_fids[0]].address        # rel1 tilt
crowd_pan_abs = fx_of[mh_crowd[0]].address         # rel1 pan (Seiten-MH)
fog_abs = fx_of[fog_fids[0]].address               # U2

for _ in range(3):
    state._render_frame(1 / 44.0)
a_par, a_mh, a_sp, a_crowd, a_fog = d1(1), d1(mh_pan_abs), d1(sp_tilt_abs), d1(crowd_pan_abs), d2(fog_abs)
for _ in range(30):
    state._render_frame(1 / 44.0)
b_par, b_mh, b_sp, b_crowd, b_fog = d1(1), d1(mh_pan_abs), d1(sp_tilt_abs), d1(crowd_pan_abs), d2(fog_abs)

assert max(d1(c) for c in range(1, 9)) > 0, "PAR leuchtet nicht (Dimmer-Voll wirkt nicht)"
assert a_mh != b_mh, "MH bewegt sich nicht (pan statisch)"
assert a_sp != b_sp, "Spider-Tilt bewegt sich nicht (LINE braucht rotation=90!)"
assert a_crowd != b_crowd, "Publikums-Sweep bewegt die Seiten-MH nicht"
assert b_fog > 0, "Nebel-Haze erzeugt keinen Output"

# Render-Diff-Zaehler (Beweis fuer bewegtes Licht)
moved = sum(1 for c in range(1, 295) if d1(c) != a_par)  # grober Bewegungsindikator

print("═" * 70)
print(f"FERTIG — {OUT}")
print(f"  Fixtures: {len(fx)} ({dict(by_type)})")
print(f"  Funktionen: {len(fm.all())}  VC-Widgets: {len(vc)}  Banks: {sorted(banks)}")
print(f"  Widget-Typen: {dict(types)}")
print(f"  edit_slots: {len(slots)}  Galerie-Buttons: {len(imgs)}  an Master gekoppelt: {len(bound)}")
print(f"  Playlist: {len(state.playlist)} Tracks  Auto-Show-Tracks: {len(shows[0].tracks)}")
print(f"  Render bewegt DMX: PAR>{max(d1(c) for c in range(1,9))} MH:{a_mh}->{b_mh} "
      f"Spider:{a_sp}->{b_sp} Crowd:{a_crowd}->{b_crowd} Fog:{b_fog}")
print("  [OK] 4 Trassen · Laser-Safety (ARM/NOT-AUS) · Nebel am Boden · edit_slot-Layering · "
      "Hardstyle-Auto-Show · Musik+APC · bg_image-Galerie")
