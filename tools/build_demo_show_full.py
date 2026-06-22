"""DEMO SHOW FULL — komplette, nach ZWECK organisierte Show auf Davids realem Rig.

Neu aufgebaut nach dem bewaehrten Muster von build_farb_fx_vc_show.py (das David
mag), mit sauberem LAYERING (edit_slot pro Kategorie statt globalem exclusive →
Effekte verschiedener Kategorien bleiben beim Seitenwechsel an) und korrigierter
Editor-Box (echte Geraetegroesse + einstellbare Regler).

Seiten (APC-Baenke; Bank N = Playback-Seite N):
  0 FARBE   — pro Gruppe (PAR/MH/Spider): Solid · Wechsel · Lauflicht · Farbwechsel.
  1 DIMMER  — pro Gruppe Dimmer-Effekte (Voll/Lauflicht/Blink/Aufbau) + MH-Gobo.
  2 STROBE  — Alle/PAR/MH/Spider-Strobe (halten ODER toggeln) + All-White + Rate.
  3 BEWEGUNG— MH-Formen (Kreis/Acht/Welle/Dreieck/Quadrat/Herz/Eigener Pfad) +
              XY-Bereich + XY-Pfad; Spider-Tilt (Ineinander/Auseinander/Wackeln/Posen/Zufall).
  4 UEBERSICHT — Master-BPM, alle Speeds (Faktor ¼…4×), Master-Dimmer, Auto-Show.

Alle Effekte folgen dem Master (Bus „Global" = globale BPM, FOLGT der Musik/Tap/
Audio-Erkennung) mit eigenem tempo_multiplier (Speed-Dials ¼ ½ 1 2 3 4).

Aufruf:  venv/Scripts/python.exe tools/build_demo_show_full.py
Erzeugt: shows/Demo_Show_Full.lshow  (selbst-verifizierend, headless)
"""
from __future__ import annotations
import os
import sys
import glob
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

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
from src.core.engine.rgb_matrix import RgbAlgorithm, MatrixStyle, ColorSequence
from src.core.engine.efx import EfxFixture, EfxAlgorithm
from src.core.engine.efx_path import EfxPath, get_efx_path_library
from src.core.engine.tempo_bus import get_tempo_bus_manager
from src.core.engine.show_engine import ShowFunction
from src.core.show.show_file import reset_show, save_show, load_show
from src.core.audio.media_player import clean_title, guess_genre_bpm
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
OUT = os.path.join(_ROOT, "shows", "Demo_Show_Full.lshow")
MUSIC_DIR = r"C:/Users/David/Desktop/Musik/BP Party"
BUS = "Global"          # alle Effekte folgen diesem Master-Bus (= globale Musik-BPM)
PLAYLIST_MAX = 16


def profile_id(short: str) -> int:
    with Session(fdb_engine()) as s:
        pid = s.execute(select(FixtureProfile.id).where(
            FixtureProfile.short_name == short)).scalar_one_or_none()
    if pid is None:
        raise SystemExit(f"Profil '{short}' fehlt — App einmal starten (ensure_builtins).")
    return int(pid)


# ════════════════════════════════════════════════════════════════════════════
#  0) BASIS + PATCH  (8 PAR @1-64, 2 MH @65/76, 2 Spider @87/101)
# ════════════════════════════════════════════════════════════════════════════
reset_show()
state = get_state()
fm = get_function_manager()
PAR_PID, MH_PID, SPIDER_PID = profile_id("ZQ01424"), profile_id("ZQ02001"), profile_id("SPIDER14")

par_fids: list[int] = []
addr = 1
for i in range(8):
    fid = i + 1
    state.add_fixture(PatchedFixture(
        fid=fid, label=f"PAR {i + 1}", fixture_profile_id=PAR_PID,
        mode_name="8-Kanal RGBW", universe=1, address=addr, channel_count=8,
        manufacturer_name="Generic", fixture_name="Stage Light ZQ01424",
        fixture_type="par"), undoable=False)
    par_fids.append(fid)
    addr += 8

for fid, lbl, a in ((9, "MH Links", 65), (10, "MH Rechts", 76)):
    state.add_fixture(PatchedFixture(
        fid=fid, label=lbl, fixture_profile_id=MH_PID, mode_name="11-Kanal",
        universe=1, address=a, channel_count=11, manufacturer_name="U King",
        fixture_name="ZQ02001 Mini Moving Head", fixture_type="moving_head"), undoable=False)
mh_fids = [9, 10]

for fid, lbl, a in ((11, "Spider Links", 87), (12, "Spider Rechts", 101)):
    state.add_fixture(PatchedFixture(
        fid=fid, label=lbl, fixture_profile_id=SPIDER_PID, mode_name="14-Kanal",
        universe=1, address=a, channel_count=14, manufacturer_name="U King",
        fixture_name="Spider 14ch", fixture_type="moving_head"), undoable=False)
spider_fids = [11, 12]

mover_fids = mh_fids + spider_fids
color_fids = par_fids + spider_fids          # echtes RGB(W)
all_fids = par_fids + mh_fids + spider_fids

fixtures = state.get_patched_fixtures()
fx_of = {f.fid: f for f in fixtures}
chans_full = {f.fid: get_channels_for_patched(f) for f in fixtures}
chan_of = {f.fid: {c.attribute: c.channel_number for c in chans_full[f.fid]} for f in fixtures}


def attr_chs(fid: int, attr: str) -> list[int]:
    """ALLE Kanalnummern eines Attributs (Spider color_r/g/b/w + tilt doppelt)."""
    return [c.channel_number for c in chans_full[fid] if (c.attribute or "").lower() == attr]


# Strikte Trennung Farbe <-> Dimmer (wie Davids Farb_FX_VC_Show): KEINE implizite
# Grundhelligkeit. Reine Farb-Effekte (Seite 0) lassen den Dimmer in Ruhe -> Licht
# kommt erst von der Dimmer-Seite, „Licht An" oder den Master-Fadern. Shutter der
# Mover offen halten (Rig-Default), damit sie emittieren, sobald Intensitaet kommt.
state.base_levels = {fid: {"shutter": open_value_for(fx_of[fid], "shutter")}
                     for fid in (spider_fids + mh_fids) if attr_chs(fid, "shutter")}
state.implicit_brightness = False
state._rebuild_render_plan()

# ── 2D-Live-View + 3D-Positionen (MH hinten hoch, Spider vorne tief) ──────────
PX = {par_fids[i]: 230.0 + i * 105.0 for i in range(8)}
lv = {fid: (PX[fid], 420.0) for fid in par_fids}
lv[9] = (PX[par_fids[0]], 250.0); lv[10] = (PX[par_fids[7]], 250.0)
lv[11] = (PX[par_fids[0]], 600.0); lv[12] = (PX[par_fids[7]], 600.0)
state.live_view_positions = {fid: list(p) for fid, p in lv.items()}
state.live_view_meta = {"zoom": 1.0, "grid_size": 20, "snap": True,
                        "grid_visible": True, "world_w": 1200, "world_h": 800}
vz = {fid: ((PX[fid] - 600.0) / 80.0, 0.0, 0.0) for fid in par_fids}
vz[9] = (vz[par_fids[0]][0], 6.0, -1.8); vz[10] = (vz[par_fids[7]][0], 6.0, -1.8)
vz[11] = (vz[par_fids[0]][0], 0.6, 1.8); vz[12] = (vz[par_fids[7]][0], 0.6, 1.8)
state.visualizer_positions = {fid: tuple(p) for fid, p in vz.items()}
state.active_stage_name = "simple"

# ── Fixture-Gruppen (Effekt-Areale) ──────────────────────────────────────────
with state._session() as s:
    s.execute(delete(FixtureGroup))
    s.add(FixtureGroup(name="Alle PAR", cols=8, rows=1,
                       positions_json=json.dumps({f"{i},0": par_fids[i] for i in range(8)})))
    s.add(FixtureGroup(name="PAR Links", cols=4, rows=1,
                       positions_json=json.dumps({f"{i},0": par_fids[i] for i in range(4)})))
    s.add(FixtureGroup(name="PAR Rechts", cols=4, rows=1,
                       positions_json=json.dumps({f"{i},0": par_fids[4 + i] for i in range(4)})))
    s.add(FixtureGroup(name="Moving Heads", cols=2, rows=1,
                       positions_json=json.dumps({"0,0": 9, "1,0": 10})))
    s.add(FixtureGroup(name="Spider", cols=2, rows=1,
                       positions_json=json.dumps({"0,0": 11, "1,0": 12})))
    s.add(FixtureGroup(name="Alle Mover", cols=4, rows=1,
                       positions_json=json.dumps({f"{i},0": mover_fids[i] for i in range(4)})))
    s.add(FixtureGroup(name="Alles", cols=12, rows=1,
                       positions_json=json.dumps({f"{i},0": all_fids[i] for i in range(12)})))
    s.commit()

# ── Tempo: Master-Bus „Global" FOLGT dem Leader (Musik-BPM/Tap/Audio) ─────────
tbm = get_tempo_bus_manager()
tbm.ensure_bus(BUS, source="bpm_global")     # bpm_global -> spiegelt die globale (Musik-)BPM

# Farben (RGBW) + MH-Farbrad/Gobo/Shutter-Slots --------------------------------
RED, GREEN, BLUE = (255, 0, 0, 0), (0, 255, 0, 0), (0, 0, 255, 0)
YELLOW, MAGENTA, WHITE = (255, 220, 0, 0), (255, 0, 255, 0), (255, 255, 255, 255)
CYAN = (0, 255, 255, 0)
RGB = lambda t: (t[0], t[1], t[2])
MHCOL = {"weiss": 4, "rot": 14, "gruen": 24, "blau": 34, "gelb": 44, "rosa": 74}
MHGOBO = {"offen": 3, "g1": 11, "g3": 27, "g5": 43, "g7": 59, "rotation": 190}
MH_OPEN, MH_STROBE = 4, 130
SP_OPEN, SP_STROBE = 8, 70


def bind_tempo(fn, group: str, mult: float = 1.0):
    """Effekt an den Master (globale Musik-BPM) koppeln, mit eigenem Multiplikator."""
    fn.tempo_bus_id = BUS
    fn.tempo_multiplier = mult
    fn.sync_group = group
    return fn


# ════════════════════════════════════════════════════════════════════════════
#  SEITE 0 — FARBE  (RGB-only Matrizen PAR/Spider; Farbrad-Szenen/Chaser MH)
# ════════════════════════════════════════════════════════════════════════════
def color_matrix(name, fids, algo, colors, params=None, speed=1.0, group=""):
    m = fm.new_rgb_matrix(name)
    m.algorithm = algo
    m.fixture_grid = list(fids)
    m.cols, m.rows = len(fids), 1
    m.colors = ColorSequence([tuple(RGB(c)) if len(c) == 4 else tuple(c) for c in colors])
    m.style = MatrixStyle.RGB           # nur Farbe — Dimmer/Shutter bleiben frei
    m.drive_intensity = False
    m.matrix_speed = speed
    if params:
        m.params = dict(params)
    if group:
        bind_tempo(m, group)
    return m


def color_effects(prefix, fids, group):
    """4 Farbeffekte je Gruppe: Solid · Wechsel(Schachbrett) · Lauflicht · Farbwechsel."""
    solid = color_matrix(f"{prefix} Solid", fids, RgbAlgorithm.PLAIN, [RED], group=group)
    wechsel = color_matrix(f"{prefix} Wechsel", fids, RgbAlgorithm.CHECKER, [RED, BLUE],
                           params={"tile": 1, "blink": True}, speed=2.0, group=group)
    lauf = color_matrix(f"{prefix} Lauflicht", fids, RgbAlgorithm.CHASE, [RED],
                        params={"axis": "H", "movement": "normal", "runner_count": 1,
                                "runner_width": 1, "after_fade": 20.0}, speed=3.0, group=group)
    fade = color_matrix(f"{prefix} Farbwechsel", fids, RgbAlgorithm.COLORFADE,
                        [RED, GREEN, BLUE], params={"hold": 0.1}, speed=1.0, group=group)
    return [solid, wechsel, lauf, fade]


par_color = color_effects("PAR", par_fids, "col_par")
spider_color = color_effects("Spider", spider_fids, "col_spider")


def mh_color_scene(name, slot):
    sc = fm.new_scene(name)
    for fid in mh_fids:
        cm = chan_of[fid]
        if "color_wheel" in cm:
            sc.set_value(fid, cm["color_wheel"], slot)
    return sc


mh_solid = {nm: mh_color_scene(f"MH {nm.capitalize()}", MHCOL[nm])
            for nm in ("rot", "gruen", "blau", "gelb", "weiss", "rosa")}


def mh_color_chaser(name, scene_ids, hold_beats=1, mult=1.0):
    c = fm.new_chaser(name)
    c.run_order, c.direction = RunOrder.Loop, Direction.Forward
    c.beats_per_step = hold_beats
    for sid in scene_ids:
        c.steps.append(ChaserStep(function_id=sid, fade_in=0.0, hold=0.4, fade_out=0.0))
    bind_tempo(c, "col_mh", mult)
    return c


mh_wechsel = mh_color_chaser("MH Wechsel", [mh_solid["rot"].id, mh_solid["blau"].id])
mh_farbwechsel = mh_color_chaser("MH Farbwechsel",
                                 [mh_solid["rot"].id, mh_solid["gruen"].id,
                                  mh_solid["blau"].id, mh_solid["gelb"].id])


# ════════════════════════════════════════════════════════════════════════════
#  SEITE 1 — DIMMER & GOBO  (DIMMER-Style Matrizen + MH-Gobo)
# ════════════════════════════════════════════════════════════════════════════
def dimmer_matrix(name, fids, algo, params=None, speed=2.0, imin=0, imax=255, group="", prio=0):
    m = fm.new_rgb_matrix(name)
    m.algorithm = algo
    m.fixture_grid = list(fids)
    m.cols, m.rows = len(fids), 1
    m.colors = ColorSequence([(255, 255, 255)])
    m.style = MatrixStyle.DIMMER        # nur Dimmer — Farbe bleibt frei
    m.drive_intensity = False
    m.intensity_min, m.intensity_max = imin, imax
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
mh_dim = dimmer_effects("MH", mh_fids, "dim_mh")
spider_dim = dimmer_effects("Spider", spider_fids, "dim_spider")
# „Licht An": die drei „Dimmer Voll" gemeinsam (sofort volle Helligkeit -> Farbe sichtbar).
voll_all_ids = [par_dim[0].id, mh_dim[0].id, spider_dim[0].id]


def mh_gobo_scene(name, gobo_slot, col_slot=MHCOL["weiss"]):
    sc = fm.new_scene(name)
    for fid in mh_fids:
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
#  SEITE 3 — BEWEGUNG  (MH-Formen + XY-Feld/Pfad + Spider-Tilt)
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
    import math
    pts = []
    for i in range(n):
        t = 2 * math.pi * i / n
        r = 0.36 + amp * math.cos(lobes * t)
        pts.append((0.5 + r * math.cos(t), 0.5 + r * math.sin(t)))
    return [(round(a, 4), round(b, 4)) for a, b in pts]


def _heart_pts(n=40):
    import math
    pts = []
    for i in range(n):
        t = 2 * math.pi * i / n
        x = 16 * (math.sin(t) ** 3)
        yv = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        pts.append((x / 34.0 + 0.5, 0.5 - yv / 34.0))
    return [(round(max(0.0, min(1.0, a)), 4), round(max(0.0, min(1.0, b)), 4)) for a, b in pts]


paths = get_efx_path_library()
wavy_path = paths.add(EfxPath("Welliger Kreis", _wavy_circle_pts(), mode="spline", closed=True))
heart_path = paths.add(EfxPath("Herz", _heart_pts(), mode="spline", closed=True))
userpath0 = paths.add(EfxPath("Eigener Pfad", [(0.2, 0.25), (0.8, 0.25), (0.8, 0.75), (0.2, 0.75)],
                              mode="linear", closed=True))

mh_circle = efx("MH Kreis", EfxAlgorithm.CIRCLE, mh_fids, "mv_mh", phase_mode="sync", size=130)
mh_eight = efx("MH Acht", EfxAlgorithm.EIGHT, mh_fids, "mv_mh", phase_mode="sync", size=150)
mh_wavy = efx("MH Welliger Kreis", EfxAlgorithm.CIRCLE, mh_fids, "mv_mh", size=170)
mh_wavy.set_custom_path(wavy_path); mh_wavy.open_beam = True
mh_tri = efx("MH Dreieck", EfxAlgorithm.TRIANGLE, mh_fids, "mv_mh", phase_mode="sync", size=150)
mh_square = efx("MH Quadrat", EfxAlgorithm.SQUARE, mh_fids, "mv_mh", phase_mode="sync", size=150)
mh_heart = efx("MH Herz", EfxAlgorithm.CIRCLE, mh_fids, "mv_mh", size=170)
mh_heart.set_custom_path(heart_path); mh_heart.open_beam = True
mh_random = efx("MH Random", EfxAlgorithm.RANDOM, mh_fids, "mv_mh", size=160, speed_hz=0.7)
mh_userpath = efx("MH Eigener Pfad", EfxAlgorithm.CIRCLE, mh_fids, "mv_mh", size=200)
mh_userpath.set_custom_path(userpath0); mh_userpath.open_beam = True
MH_SHAPES = [mh_circle, mh_eight, mh_wavy, mh_tri, mh_square, mh_heart, mh_random, mh_userpath]

# Spider-Bewegung: NUR Tilt (kein Pan). WICHTIG: LINE braucht rotation=90 (vertikal),
# sonst laeuft sie auf der nicht vorhandenen Pan-Achse -> Tilt bleibt statisch (verifiziert).
# Innerhalb EINES Spiders laufen die zwei Bars automatisch gegenphasig (write() X-6).
sp_converge = efx("Spider Schere", EfxAlgorithm.LINE, spider_fids, "mv_sp",
                  phase_mode="sync", size=210, speed_hz=0.6, rotation=90.0)
sp_diverge = efx("Spider Welle", EfxAlgorithm.CIRCLE, spider_fids, "mv_sp",
                 phase_mode="offset", size=180, speed_hz=0.5)
sp_wiggle = efx("Spider Wackeln", EfxAlgorithm.LINE, spider_fids, "mv_sp",
                phase_mode="sync", size=90, speed_hz=4.0, mult=2.0, rotation=90.0)


def spider_pose(name, tilt_l, tilt_r):
    sc = fm.new_scene(name)
    for fid in spider_fids:
        tilts = attr_chs(fid, "tilt")
        if len(tilts) >= 1:
            sc.set_value(fid, tilts[0], tilt_l)
        if len(tilts) >= 2:
            sc.set_value(fid, tilts[1], tilt_r)
        for ch in attr_chs(fid, "intensity"):
            sc.set_value(fid, ch, 255)
        for ch in attr_chs(fid, "shutter"):
            sc.set_value(fid, ch, SP_OPEN)
    return sc


sp_out = spider_pose("Spider Aussen", 0, 255)
sp_in = spider_pose("Spider Innen", 128, 128)
sp_p1 = spider_pose("Spider Pos 1", 40, 210)
sp_p2 = spider_pose("Spider Pos 2", 200, 60)
sp_p3 = spider_pose("Spider Pos 3", 128, 200)
sp_random3 = fm.new_chaser("Spider Zufall 3")
sp_random3.run_order, sp_random3.direction = RunOrder.Random, Direction.Forward
sp_random3.beats_per_step = 2
for sid in (sp_p1.id, sp_p2.id, sp_p3.id):
    sp_random3.steps.append(ChaserStep(function_id=sid, fade_in=0.1, hold=0.6, fade_out=0.0))
bind_tempo(sp_random3, "mv_sp")
SP_MOVES = [sp_converge, sp_diverge, sp_wiggle, sp_out, sp_in, sp_random3]
SP_MULT_FX = [sp_converge, sp_diverge, sp_wiggle, sp_random3]   # bus-gekoppelte (fuer Speed-Dial)


# ════════════════════════════════════════════════════════════════════════════
#  SEITE 2 — STROBE + ALL-WHITE
# ════════════════════════════════════════════════════════════════════════════
def strobe_fn(name, fids):
    m = fm.new_rgb_matrix(name)
    m.algorithm = RgbAlgorithm.STROBE
    m.fixture_grid = list(fids)
    m.cols, m.rows = len(fids), 1
    m.colors = ColorSequence([(255, 255, 255)])
    m.style = MatrixStyle.DIMMER
    m.drive_intensity = False
    m.matrix_speed = 8.0
    m.priority = 50
    bind_tempo(m, "strobe")
    return m


strobe_all = strobe_fn("Strobe Alle", all_fids)
strobe_par = strobe_fn("Strobe PAR", par_fids)
strobe_mh = strobe_fn("Strobe MH", mh_fids)
strobe_sp = strobe_fn("Strobe Spider", spider_fids)
STROBES = [strobe_all, strobe_par, strobe_mh, strobe_sp]

all_white = fm.new_scene("All White")
all_white.priority = 9999
for fid in color_fids:
    for ch in attr_chs(fid, "intensity"):
        all_white.set_value(fid, ch, 255)
    for attr, v in (("color_r", 255), ("color_g", 255), ("color_b", 255), ("color_w", 255)):
        for ch in attr_chs(fid, attr):
            all_white.set_value(fid, ch, v)
    for ch in attr_chs(fid, "shutter"):
        all_white.set_value(fid, ch, open_value_for(fx_of[fid], "shutter"))
for fid in mh_fids:
    cm = chan_of[fid]
    if "intensity" in cm:
        all_white.set_value(fid, cm["intensity"], 255)
    if "shutter" in cm:
        all_white.set_value(fid, cm["shutter"], MH_OPEN)
    if "color_wheel" in cm:
        all_white.set_value(fid, cm["color_wheel"], MHCOL["weiss"])


# ════════════════════════════════════════════════════════════════════════════
#  MUSIK-PLAYLIST + AUTO-SHOW-KOPPLUNG
# ════════════════════════════════════════════════════════════════════════════
def _dup_score(p):
    return (p.lower().count("kopie"), len(p))


def build_playlist():
    seen: dict[str, str] = {}
    for p in sorted(glob.glob(os.path.join(MUSIC_DIR, "*.mp3"))):
        key = clean_title(p).lower()
        if key not in seen or _dup_score(p) < _dup_score(seen[key]):
            seen[key] = p
    uniq = sorted(seen.values(), key=lambda p: clean_title(p).lower())[:PLAYLIST_MAX]
    if uniq:
        pl = []
        for p in uniq:
            genre, bpm = guess_genre_bpm(os.path.basename(p))
            pl.append({"path": p, "title": clean_title(p), "genre": genre, "bpm": float(bpm)})
        return pl, True
    fb = [("Bounce Anthem", "Bounce", 150.0), ("Hardstyle Hero", "Hardstyle", 150.0),
          ("Hypertechno Drop", "Hypertechno", 150.0), ("Phonk Cruise", "Bounce", 145.0)]
    return [{"path": os.path.join(MUSIC_DIR, t + ".mp3"), "title": t, "genre": g, "bpm": b}
            for t, g, b in fb], False


playlist, _real_tracks = build_playlist()
state.playlist = playlist
print(f"[build] Playlist: {len(playlist)} Tracks "
      f"({'echte Dateien aus MUSIC_DIR' if _real_tracks else 'Platzhalter — Ordner leer/fehlt'}).")

# Beim ▶ im Player automatisch: Farbe + Licht + MH-Bewegung (folgt der Musik-BPM).
state.music_autoshow = {
    "enabled": True,
    "function_ids": [par_color[3].id, par_dim[0].id, mh_circle.id, spider_color[3].id],
    "bank": 0,
    "slots": {par_color[3].id: "col_par", par_dim[0].id: "dim_par",
              mh_circle.id: "mv_mh", spider_color[3].id: "col_spider"},
}

# AUTO-SHOW-Timeline (64 s, Loop) — haendefreies „volles Programm" als eigener Pad.
auto_show = fm.new_show("AUTO-SHOW (64s Loop)")
auto_show.loop = True
auto_show.total_duration = 64.0


def _sf(fn, t0, dur, col="#4A90D9"):
    return ShowFunction(function_id=fn.id, start_time=t0, duration=dur, color=col)


t_col = auto_show.add_track("Farbe")
for fn, t0, dur in [(par_color[3], 0.0, 16.0), (par_color[2], 16.0, 16.0),
                    (par_color[1], 32.0, 16.0), (par_color[3], 48.0, 16.0)]:
    t_col.add_function(_sf(fn, t0, dur, "#3fb950"))
for fn, t0, dur in [(spider_color[3], 0.0, 32.0), (spider_color[2], 32.0, 32.0)]:
    t_col.add_function(_sf(fn, t0, dur, "#2e7d46"))
t_dim = auto_show.add_track("Dimmer")
t_dim.add_function(_sf(par_dim[0], 0.0, 48.0, "#1f4a28"))         # PAR sichtbar
t_dim.add_function(_sf(par_dim[2], 48.0, 16.0, "#5a1f1f"))        # Drop: Blink
t_move = auto_show.add_track("MH Bewegung")
for fn, t0, dur in [(mh_circle, 0.0, 16.0), (mh_eight, 16.0, 16.0),
                    (mh_wavy, 32.0, 16.0), (mh_heart, 48.0, 16.0)]:
    t_move.add_function(_sf(fn, t0, dur, "#1f3a6a"))
t_sp = auto_show.add_track("Spider")
for fn, t0, dur in [(sp_converge, 0.0, 32.0), (sp_random3, 32.0, 32.0)]:
    t_sp.add_function(_sf(fn, t0, dur, "#1f5a5a"))
auto_show.recalc_duration()


# ════════════════════════════════════════════════════════════════════════════
#  VIRTUAL CONSOLE  (5 Zweck-Baenke + universelle Kopfzeile)
# ════════════════════════════════════════════════════════════════════════════
PAD, GAP, X0, Y0 = 56, 6, 16, 150
STEP = PAD + GAP
RX = 470
widgets: list[dict] = []
BANK_ALL = -1
B_COLOR, B_DIM, B_STROBE, B_MOVE, B_OVER = 0, 1, 2, 3, 4
PAGE_NAMES = ["Farbe", "Dimmer & Gobo", "Strobe", "Bewegung", "Übersicht/Master"]


def note_rc(r, c):
    return (7 - r) * 8 + c


def pad_xy(r, c):
    return X0 + c * STEP, Y0 + r * STEP


def _add(w, x, y, ww, hh, bank):
    w.bank = bank
    w.setGeometry(x, y, ww, hh)
    widgets.append(w.to_dict())


def fx_btn(fn, r, c, bank, accent, slot, note=None):
    """Effekt-Pad: edit_slot = Kategorie -> pro Kategorie EIN aktiver Effekt, aber
    verschiedene Kategorien LAYERN (kein globales exclusive/stop_all)."""
    b = VCButton(fn.name)
    b.action = ButtonAction.FUNCTION_TOGGLE
    b.function_id = fn.id
    b.edit_slot = slot
    b.pad_style = "pulse"
    b._bg_color.setNamedColor(accent)
    if note is not None:
        b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, note
    x, y = pad_xy(r, c)
    _add(b, x, y, PAD, PAD, bank)


def swatch(name, r, c, bank, rgbw, slot, note=None):
    cc = VCColor(name)
    cc.color_r, cc.color_g, cc.color_b, cc.color_w = rgbw
    cc.with_intensity = False
    cc.target = ColorTarget.EFFECT_C1
    cc.edit_slot = slot
    if note is not None:
        cc.midi_type, cc.midi_ch, cc.midi_data1 = "note_on", 0, note
    x, y = pad_xy(r, c)
    _add(cc, x, y, PAD, PAD, bank)


def action_btn(name, action, x, y, bank, accent, ww=64, hh=26, function_id=None,
               function_ids=None, group=None, tempo_bus_id=None, note=None, style="solid"):
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
    if note is not None:
        b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, note
    _add(b, x, y, ww, hh, bank)


def pad_action(name, action, r, c, bank, accent, function_id=None, function_ids=None,
               group=None, note=None, style="solid"):
    x, y = pad_xy(r, c)
    action_btn(name, action, x, y, bank, accent, ww=PAD, hh=PAD, function_id=function_id,
               function_ids=function_ids, group=group, note=note, style=style)


def flash_btn(fn, r, c, bank, accent, note=None):
    b = VCButton(fn.name)
    b.action = ButtonAction.FUNCTION_FLASH
    b.function_id = fn.id
    b.pad_style = "solid"
    b._bg_color.setNamedColor(accent)
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


def master_fader(caption, x, y, bank, mode, group="", slot=None, value=255, midi_cc=-1):
    s = VCSlider(caption)
    s.mode = mode
    s.programmer_group = group
    if slot is not None:
        s.function_id = slot
    s.midi_cc, s.midi_ch = midi_cc, 0
    s._value = value
    _add(s, x, y, 50, 150, bank)


def eff_colors(caption, x, y, bank, slot, ww=290, hh=80):
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


def effect_editor_box(caption, x, y, bank, function_id, ww=300, hh=200):
    """On-Canvas Editor-Box: an einen echten Effekt gebunden (Header + echte
    Geraetegroesse-Vorschau) + ein sinnvoller Standard-Satz Bedien-Regler
    (Tempo/Helligkeit) als serialisierte Kinder. Im neuen Modell baut die Box
    keine Auto-Regler mehr beim Laden — der Generator legt sie daher explizit an
    (``build_default_controls``); im Live-App betrieb waehlt der Nutzer per ⚙."""
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
HBTN = [("Programmer leeren", ButtonAction.CLEAR, "#4a3a10", 100),
        ("Effekt-Stop", ButtonAction.STOP_EFFECTS, "#4a1010", 101),
        ("Blackout", ButtonAction.BLACKOUT, "#2a0000", 102),
        ("Licht An", None, "#2a4a2a", 103)]   # Licht An = Sonderfall (function_ids)
hx = X0
for nm, act, col, nt in HBTN:
    if nm == "Licht An":
        action_btn("Licht An", ButtonAction.FUNCTION_TOGGLE, hx, HZ1, BANK_ALL, col, ww=92,
                   function_ids=voll_all_ids, note=nt)
        hx += 98
    else:
        action_btn(nm, act, hx, HZ1, BANK_ALL, col, ww=92, note=nt)
        hx += 98
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
label("DEMO SHOW FULL — SCENE 1-5: Farbe · Dimmer · Strobe · Bewegung · Übersicht. Effekte "
      "folgen der MASTER-BPM (Musik-BPM/Tap) mit eigenem Multiplikator (Speed-Dials ¼…4×). "
      "Kategorien layern (Seitenwechsel laesst Effekte AN). Licht An = sofort hell.",
      X0, 124, 940, BANK_ALL)

CA, CB = RX, RX + 162    # rechte Spalten

# ── BANK 0 — FARBE ───────────────────────────────────────────────────────────
ACC = ["#1f5a3a", "#5a3a1f", "#1f3a6a", "#5a1f6a"]    # Solid/Wechsel/Lauf/Fade
for i, fn in enumerate(par_color):
    fx_btn(fn, 0, i, B_COLOR, ACC[i], "col_par", note=note_rc(0, i))
PAR_SW = [("Rot", RED), ("Grün", GREEN), ("Blau", BLUE), ("Gelb", YELLOW), ("Magenta", MAGENTA), ("Weiß", WHITE)]
for i, (nm, c) in enumerate(PAR_SW):
    swatch(nm, 1, i, B_COLOR, c, "col_par", note=note_rc(1, i))
for i, nm in enumerate(("rot", "gruen", "blau", "gelb", "weiss", "rosa")):
    fx_btn(mh_solid[nm], 2, i, B_COLOR, "#3a5a1f", "col_mh", note=note_rc(2, i))
fx_btn(mh_wechsel, 3, 0, B_COLOR, "#5a3a1f", "col_mh", note=note_rc(3, 0))
fx_btn(mh_farbwechsel, 3, 1, B_COLOR, "#5a1f6a", "col_mh", note=note_rc(3, 1))
for i, fn in enumerate(spider_color):
    fx_btn(fn, 4, i, B_COLOR, ACC[i], "col_spider", note=note_rc(4, i))
for i, (nm, c) in enumerate(PAR_SW):
    swatch(nm, 5, i, B_COLOR, c, "col_spider", note=note_rc(5, i))
label("PAR", X0, Y0 - 16, 60, B_COLOR); label("MH", X0, pad_xy(2, 0)[1] - 16, 60, B_COLOR)
label("Spider", X0, pad_xy(4, 0)[1] - 16, 60, B_COLOR)
speed_dial("PAR ×", CA, Y0, B_COLOR, par_color)
speed_dial("MH ×", CA, Y0 + 150, B_COLOR, [mh_wechsel, mh_farbwechsel])
speed_dial("Spider ×", CA, Y0 + 300, B_COLOR, spider_color)
eff_colors("PAR Farben", CB, Y0, B_COLOR, "col_par", ww=224, hh=70)
eff_colors("Spider Farben", CB, Y0 + 74, B_COLOR, "col_spider", ww=224, hh=70)
effect_editor_box("Editor: aktiver PAR-Farbeffekt", CB, Y0 + 150, B_COLOR, par_color[2].id, ww=224, hh=180)
label("BANK 1 FARBE — R0 PAR-Effekte · R1 PAR-Farben · R2 MH-Farbe · R3 MH-Effekte · "
      "R4 Spider-Effekte · R5 Spider-Farben. Nur RGB (Helligkeit von Seite 2 / Licht An).",
      X0, Y0 + 6 * STEP, 440, B_COLOR)

# ── BANK 1 — DIMMER & GOBO ───────────────────────────────────────────────────
for grp_i, (lbl, effs, slot) in enumerate([("PAR", par_dim, "dim_par"),
                                           ("MH", mh_dim, "dim_mh"),
                                           ("Spider", spider_dim, "dim_spider")]):
    for i, fn in enumerate(effs):
        fx_btn(fn, grp_i, i, B_DIM, "#1f3a6a", slot, note=note_rc(grp_i, i))
    label(lbl, X0, pad_xy(grp_i, 0)[1] - 16, 60, B_DIM)
    speed_dial(f"{lbl} ×", CA, Y0 + grp_i * 150, B_DIM, effs)
for i, nm in enumerate(("offen", "g1", "g3", "g5", "g7")):
    fx_btn(mh_gobo[nm], 4, i, B_DIM, "#5a3a1f", "gobo_mh", note=note_rc(4, i))
fx_btn(gobo_wechsel, 4, 5, B_DIM, "#7a6500", "gobo_mh", note=note_rc(4, 5))
label("MH-Gobo", X0, pad_xy(4, 0)[1] - 16, 90, B_DIM)
effect_editor_box("Editor: aktive PAR-Dimmer-Matrix", CB, Y0, B_DIM, par_dim[1].id, ww=224, hh=190)
label("BANK 2 DIMMER & GOBO — R0-2 Dimmer-Effekte (Voll/Lauflicht/Blink/Aufbau) je Gruppe "
      "(nur Dimmer, ueber der Farbe). R4 MH-Gobos. Rechts: Speed ×  +  Editor.",
      X0, Y0 + 6 * STEP, 440, B_DIM)

# ── BANK 2 — STROBE ──────────────────────────────────────────────────────────
SNAMES = ["Strobe Alle", "Strobe PAR", "Strobe MH", "Strobe Spider"]
for i, fn in enumerate(STROBES):                         # R0: halten (flash)
    flash_btn(fn, 0, i, B_STROBE, "#551111", note=note_rc(0, i))
for i, fn in enumerate(STROBES):                         # R1: toggeln (edit_slot strobe)
    fx_btn(fn, 1, i, B_STROBE, "#7a2222", "strobe", note=note_rc(1, i))
pad_action("All White", ButtonAction.ALL_WHITE, 3, 0, B_STROBE, "#888888",
           function_id=all_white.id, note=note_rc(3, 0))
label("R0 Strobe HALTEN · R1 Strobe TOGGLE · R3 All White (halten)", X0, Y0 - 16, 360, B_STROBE)
speed_dial("Strobe-Rate ×", CA, Y0, B_STROBE, STROBES)
effect_editor_box("Editor: Strobe Alle", CB, Y0, B_STROBE, strobe_all.id, ww=224, hh=190)
label("BANK 3 STROBE — R0 Strobe halten (Alle/PAR/MH/Spider), R1 Strobe toggeln, "
      "R3 All White. Rechts: Strobe-Rate (Multiplikator) + Editor.",
      X0, Y0 + 6 * STEP, 440, B_STROBE)

# ── BANK 3 — BEWEGUNG (MH + Spider) ──────────────────────────────────────────
SHP = ["#1f3a6a", "#1f4a6a", "#1f5a6a", "#3a1f6a", "#5a1f6a", "#6a1f4a", "#2a6a2a", "#1f6a4a"]
for i, fn in enumerate(MH_SHAPES):                       # R0-2: MH-Formen (8)
    fx_btn(fn, i // 3, i % 3, B_MOVE, SHP[i], "mv_mh", note=note_rc(i // 3, i % 3))
label("MH-Form", X0, Y0 - 16, 80, B_MOVE)
for i, fn in enumerate(SP_MOVES):                        # R3-4: Spider (6)
    fx_btn(fn, 3 + i // 3, i % 3, B_MOVE, "#1f5a5a", "mv_sp", note=note_rc(3 + i // 3, i % 3))
label("Spider-Bewegung (nur Tilt)", X0, pad_xy(3, 0)[1] - 16, 200, B_MOVE)
xy_pad("MH Bereich (Box aufziehen)", CA, Y0, B_MOVE, mh_fids, "area", efx_function_id=mh_circle.id)
xy_pad("MH Bahn zeichnen", CA + 186, Y0, B_MOVE, mh_fids, "path", efx_function_id=mh_userpath.id)
speed_dial("MH ×", CA, Y0 + 188, B_MOVE, MH_SHAPES)
speed_dial("Spider ×", CA + 162, Y0 + 188, B_MOVE, SP_MULT_FX)
label("BANK 4 BEWEGUNG — R0-2 MH-Formen (Kreis/Acht/Welle/Dreieck/Quadrat/Herz/Random/Pfad). "
      "R3-4 Spider-Tilt (Schere/Welle/Wackeln/Aussen/Innen/Zufall). Rechts: XY-Bereich + Bahn + Speed.",
      X0, Y0 + 6 * STEP, 440, B_MOVE)

# ── BANK 4 — UEBERSICHT / SPEEDS / MASTER ────────────────────────────────────
bpm_display("MASTER", CA, Y0, B_OVER, tempo_bus_id="", ww=150, hh=82)
speed_dial("Farbe ×", CA, Y0 + 88, B_OVER, par_color + spider_color)
speed_dial("Dimmer ×", CA + 158, Y0 + 88, B_OVER, par_dim + mh_dim + spider_dim)
speed_dial("Bewegung ×", CA, Y0 + 238, B_OVER, MH_SHAPES + SP_MULT_FX)
speed_dial("Strobe ×", CA + 158, Y0 + 238, B_OVER, STROBES)
# Auto-Show-Pad + 4 Master-Dimmer
pad_action("AUTO-SHOW", ButtonAction.FUNCTION_TOGGLE, 0, 0, B_OVER, "#b8860b",
           function_id=auto_show.id, note=note_rc(0, 0))
pad_action("Licht An", ButtonAction.FUNCTION_TOGGLE, 0, 1, B_OVER, "#2a4a2a",
           function_ids=voll_all_ids, note=note_rc(0, 1))
label("AUTO-SHOW (Loop) · Licht An", X0, Y0 - 16, 300, B_OVER)
MFX = CB + 240
master_fader("Spider M", MFX, Y0, B_OVER, SliderMode.GROUP_DIMMER, group="Spider", midi_cc=53)
master_fader("MH M", MFX + 54, Y0, B_OVER, SliderMode.GROUP_DIMMER, group="Moving Heads", midi_cc=54)
master_fader("PAR M", MFX + 108, Y0, B_OVER, SliderMode.GROUP_DIMMER, group="Alle PAR", midi_cc=55)
master_fader("GRAND", MFX + 162, Y0, B_OVER, SliderMode.GRANDMASTER, midi_cc=56)
label("BANK 5 UEBERSICHT — Master-BPM + alle Speeds (Farbe/Dimmer/Bewegung/Strobe ×¼…4×, "
      "synchron mit S.1-4). AUTO-SHOW + Licht An. Rechts: 4 Master-Dimmer (Spider/MH/PAR/GRAND).",
      X0, Y0 + 6 * STEP, 440, B_OVER)


state._vc_layout = {"widgets": widgets}
state.programmer = {}
state.show_name = "Demo Show Full"
get_tempo_bus_manager().set_auto_sync(True)

# Executor-Seiten benennen
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

# Show-Validierung: nur ECHTE Bausteine? (macht halluzinierte Widgets/Algos/
# Params/Styles laut, BEVOR die Show als fertig gilt — statt sie still inert zu
# laden). Siehe src/core/capability + SecondBrain entry_show_validation.
from src.core.capability.validate import assert_lshow
assert_lshow(OUT)
print("Lint: OK (nur echte Bausteine)")

# ════════════════════════════════════════════════════════════════════════════
#  VERIFIKATION (Round-Trip + Inhalt + Layering-Struktur)
# ════════════════════════════════════════════════════════════════════════════
ok, msg = load_show(OUT)
print("Load:", ok, msg)
assert ok, f"Show laedt nicht: {msg}"
state = get_state()
fm = get_function_manager()

# Bindungs-bewusste Live-Validierung (param_key/effect_action_key gegen die
# ECHTEN list_params/list_actions der gebundenen Funktion) — fängt, was der
# statische Lint nicht sieht. Demo ist live-sauber; bricht laut bei Drift.
from src.core.capability.validate import validate_show_live, ERROR as _LINT_ERR
_live = validate_show_live(state)
assert not [x for x in _live if x.severity == _LINT_ERR], \
    "Live-Lint-Fehler:\n" + "\n".join(str(x) for x in _live)
print(f"Live-Lint: OK ({len(_live)} Hinweise)")

from collections import Counter
from src.core.engine.rgb_matrix import RgbMatrixInstance, MatrixStyle as MS
from src.core.engine.efx import EfxInstance
from src.core.engine.scene import Scene
from src.core.engine.chaser import Chaser
from src.core.engine.show_engine import Show

fx = state.get_patched_fixtures()
assert len(fx) == 12, f"Fixtures: {len(fx)}"

mats = [f for f in fm.all() if isinstance(f, RgbMatrixInstance)]
color_m = [m for m in mats if m.style == MS.RGB and not m.drive_intensity]
dim_m = [m for m in mats if m.style == MS.DIMMER]
assert len(color_m) >= 8, f"Farb-Matrizen: {len(color_m)}"
assert len(dim_m) >= 12, f"Dimmer-/Strobe-Matrizen: {len(dim_m)}"

efxs = [f for f in fm.all() if isinstance(f, EfxInstance)]
assert len(efxs) >= 11, f"EFX: {len(efxs)}"
custom = [e for e in efxs if e.algorithm == EfxAlgorithm.CUSTOM and e.path_data]
assert len(custom) >= 2, f"Custom-Path-EFX: {len(custom)}"

# Tempo: alle Effekte folgen dem Master „Global" (der wiederum der Musik folgt)
bound = [f for f in fm.all() if getattr(f, "tempo_bus_id", "") == BUS]
assert len(bound) >= 25, f"an Master gekoppelt: {len(bound)}"
named = {b.bus_id: b for b in get_tempo_bus_manager().named_buses()}
assert BUS in named, f"Global-Bus fehlt: {list(named)}"
assert named[BUS].source == "bpm_global", f"Global folgt nicht der Musik: {named[BUS].source}"
assert get_tempo_bus_manager().auto_sync is True, "Auto-Sync nicht persistiert"
assert state.implicit_brightness is False, "strikte Farbe/Dimmer-Trennung nicht persistiert"

vc = state._vc_layout.get("widgets", [])
banks = Counter(w.get("bank") for w in vc)
assert set(banks) == {0, 1, 2, 3, 4, -1}, f"Banks: {sorted(banks)}"
types = Counter(w["type"] for w in vc)

# LAYERING-Fix strukturell: KEIN Button global-exklusiv; Kategorien via edit_slot getrennt
buttons = [w for w in vc if w["type"] == "VCButton"]
assert not any(w.get("exclusive") for w in buttons), "es gibt noch global-exklusive Buttons (stop_all)"
slots = {w.get("edit_slot") for w in vc if w.get("edit_slot")}
for need in ("col_par", "col_mh", "col_spider", "dim_par", "dim_mh", "dim_spider",
             "strobe", "mv_mh", "mv_sp"):
    assert need in slots, f"edit_slot fehlt: {need} ({sorted(slots)})"

# Korrigierte Editor-Boxen: an echte Matrix-/EFX-Effekte gebunden
editor_boxes = [w for w in vc if w["type"] == "VCEffectEditor"]
fn_ids = {f.id for f in fm.all()}
assert len(editor_boxes) >= 3, f"Editor-Boxen: {len(editor_boxes)}"
assert all(isinstance(w.get("effect_id"), int) and w["effect_id"] in fn_ids for w in editor_boxes), \
    "Editor-Box ohne gueltige effect_id"

# Speed-Dials (Pro-Effekt-Multiplikator) + neue Widget-Typen vorhanden
for t in ("VCSpeedDial", "VCBpmDisplay", "VCEffectColors", "VCXYPad", "VCColor", "VCSlider",
          "VCSongInfo", "VCEffectEditor"):
    assert types.get(t, 0) >= 1, f"Widget fehlt: {t} ({dict(types)})"
assert any(w["type"] == "VCXYPad" and w.get("mode") == "path" for w in vc), "kein Pfad-XY-Pad"
gm = [w for w in vc if w["type"] == "VCSlider" and w.get("mode") == "GrandMaster"]
gd = [w for w in vc if w["type"] == "VCSlider" and w.get("mode") == "GroupDimmer"]
assert len(gm) >= 1 and len(gd) >= 3, f"Master-Fader: GM={len(gm)} GroupDim={len(gd)}"

# Musik + Auto-Show
assert 1 <= len(state.playlist) <= PLAYLIST_MAX, f"Playlist: {len(state.playlist)}"
ma = state.music_autoshow
assert ma.get("enabled") and all(fid in fn_ids for fid in ma.get("function_ids", [])), ma
shows = [f for f in fm.all() if isinstance(f, Show)]
assert shows and shows[0].loop and len(shows[0].tracks) >= 4, "AUTO-SHOW-Timeline fehlt/zu klein"

# Keine Ueberlappung interaktiver Widgets je Bank
_INTER = {"VCButton", "VCSlider", "VCColor", "VCXYPad", "VCSpeedDial", "VCBpmDisplay",
          "VCEffectColors", "VCSongInfo", "VCEffectEditor"}


def _rect(w):
    return (w.get("x", 0), w.get("y", 0), w.get("x", 0) + w.get("w", 0), w.get("y", 0) + w.get("h", 0))


def _ov(a, b):
    ax0, ay0, ax1, ay1 = _rect(a); bx0, by0, bx1, by1 = _rect(b)
    return not (ax1 <= bx0 or bx1 <= ax0 or ay1 <= by0 or by1 <= ay0)


for bk in range(5):
    layer = [w for w in vc if w.get("bank") in (bk, -1) and w["type"] in _INTER]
    for a in range(len(layer)):
        for b in range(a + 1, len(layer)):
            assert not _ov(layer[a], layer[b]), (
                f"Overlap Bank {bk}: {layer[a]['type']}@{_rect(layer[a])} "
                f"vs {layer[b]['type']}@{_rect(layer[b])}")

maxy = max((w.get("y", 0) + w.get("h", 0)) for w in vc)
assert maxy < 820, f"zu hoch: {maxy}"

# Render-Sanity: gelayerte Effekte erzeugen echtes, SICH BEWEGENDES DMX (faengt z.B.
# statische Spider-EFX ab). Farbe + Dimmer-Voll + MH-Kreis + Spider-Schere.
from src.core.engine.bpm_manager import get_bpm_manager
get_bpm_manager().request_bpm(150.0, "diag")
_bn = {f.name: f for f in fm.all()}
for nm in ("PAR Farbwechsel", "PAR Dimmer Voll", "MH Kreis", "Spider Schere"):
    fm.start(_bn[nm].id)


def _snap():
    u = state.universes.get(1)
    return [int(u.get_channel(c)) if u else 0 for c in range(1, 131)]


for _ in range(3):
    state._render_frame(1 / 44.0)
_a = _snap()
for _ in range(30):
    state._render_frame(1 / 44.0)
_b = _snap()
assert max(_b[0:8]) > 0, "PAR leuchtet nicht (Dimmer-Voll wirkt nicht)"
assert _a[64] != _b[64], "MH bewegt sich nicht (pan @65 statisch)"
assert _a[86] != _b[86], "Spider-Tilt bewegt sich nicht (LINE braucht rotation=90!)"

print(f"Funktionen: {len(fm.all())}  VC-Widgets: {len(vc)}  Max-Y={maxy}")
print(f"  Farb-Matrizen={len(color_m)}  Dimmer/Strobe={len(dim_m)}  EFX={len(efxs)} (Custom={len(custom)})")
print(f"  an Master(Global={named[BUS].source}) gekoppelt={len(bound)}  edit_slots={len(slots)}  "
      f"Editor-Boxen={len(editor_boxes)}  Playlist={len(state.playlist)}")
print(f"  Widget-Typen={dict(types)}")
print("  [OK] 5 Zweck-Baenke · edit_slot-Layering (kein stop_all) · Pro-Effekt-Multiplikator · "
      "korrigierte Editoren · Bus folgt Musik · Strobe-Seite · Auto-Show · Musik+APC")
print("FERTIG")
