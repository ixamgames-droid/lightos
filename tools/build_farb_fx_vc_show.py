"""FARB-/EFFEKT-VC-SHOW — 4-Seiten Virtual Console fuer Davids Rig.

Seiten (Baenke):
  1 FARBE   — pro Gruppe (PAR/MH/Spider) Farbauswahl + Farbeffekt (Solid/Wechsel/
              Lauflicht/Farbwechsel), single-select, nur RGB/RGBW (Dimmer/Shutter
              ausgeblendet), je Effekt eigener BPM-Multiplikator + Fade-Fader.
  2 DIMMER & GOBO — pro Gruppe Dimmer-Effekte (Lauflicht/Blink/Aufbau) + MH-Gobo-
              Auswahl + Gobo-Wechsel, alle BPM-gekoppelt.
  3 BEWEGUNG — MH-Formen (Kreis/Acht/welliger Kreis/Dreieck/Quadrat/Herz) + XY-Feld
              (Bereich aufziehen) + XY-Pfad (Bahn zeichnen) + Spider-Bewegungen.
  4 UEBERSICHT/STROBE/MASTER — Speed-Uebersicht (synchron mit S.1-3), Strobe-Wahl
              (Alle/PAR/MH/Spider), All-White, Blackout, Effekt-Stop, Pause, Freeze,
              4 Master-Dimmer (Grand/PAR/MH/Spider).

Master-BPM = globale BPM (Tempo-Bus "Global"). Jeder Effekt haengt daran und hat
seinen eigenen tempo_multiplier (Faktor-Gitter ¼ ½ 1 2 3 4 am Speed-Dial).

Aufruf:  venv/Scripts/python.exe tools/build_farb_fx_vc_show.py
Erzeugt: shows/Farb_FX_VC_Show.lshow  (selbst-verifizierend, headless)
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
from src.core.show.show_file import reset_show, save_show, load_show
from src.ui.virtualconsole.vc_button import VCButton, ButtonAction
from src.ui.virtualconsole.vc_color import VCColor, ColorTarget
from src.ui.virtualconsole.vc_label import VCLabel
from src.ui.virtualconsole.vc_slider import VCSlider, SliderMode
from src.ui.virtualconsole.vc_speedial import VCSpeedDial, SpeedTarget
from src.ui.virtualconsole.vc_bpm_display import VCBpmDisplay
from src.ui.virtualconsole.vc_effect_colors import VCEffectColors
from src.ui.virtualconsole.vc_xypad import VCXYPad

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(_ROOT, "shows", "Farb_FX_VC_Show.lshow")
BUS = "Global"   # alle Effekte folgen dem Master (globale BPM) mit eigenem Multiplikator


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


# Grundhelligkeit: PAR + Spider leuchten (Farb-Matrix ohne Dimmer sichtbar).
# Strikte Trennung Farbe <-> Dimmer (Davids Wunsch): KEINE Grund-Helligkeit. Reine
# Farb-Effekte (Seite 1) lassen den Dimmer in Ruhe -> die Lampen bleiben dunkel, bis
# Helligkeit von Seite 2 (Dimmer-Effekt/„Dimmer Voll") oder den Master-Fadern kommt.
# Nur den Shutter von MH/Spider offen halten (Rig-Default), damit sie emittieren,
# sobald die Intensitaet hochkommt. implicit_brightness=False schaltet das implizite
# „Farbe heisst sichtbar" (4a²) ab -> reine Farbe leuchtet NICHT von allein.
state.base_levels = {fid: {"shutter": open_value_for(fx_of[fid], "shutter")}
                     for fid in (spider_fids + mh_fids) if attr_chs(fid, "shutter")}
state.implicit_brightness = False
state._rebuild_render_plan()

# ── Positionen (Live View + 3D), wie Davids reales Rig ──────────────────────
PX = {par_fids[i]: 230.0 + i * 105.0 for i in range(8)}
lv = {fid: (PX[fid], 420.0) for fid in par_fids}
lv[9] = (PX[par_fids[0]], 250.0); lv[10] = (PX[par_fids[7]], 250.0)     # MH hinten
lv[11] = (PX[par_fids[0]], 600.0); lv[12] = (PX[par_fids[7]], 600.0)    # Spider vorne
state.live_view_positions = {fid: list(p) for fid, p in lv.items()}
state.live_view_meta = {"zoom": 1.0, "grid_size": 20, "snap": True,
                        "grid_visible": True, "world_w": 1200, "world_h": 800}
vz = {fid: ((PX[fid] - 600.0) / 80.0, 0.0, 0.0) for fid in par_fids}
vz[9] = (vz[par_fids[0]][0], 6.0, -1.8); vz[10] = (vz[par_fids[7]][0], 6.0, -1.8)
vz[11] = (vz[par_fids[0]][0], 0.6, 1.8); vz[12] = (vz[par_fids[7]][0], 0.6, 1.8)
state.visualizer_positions = {fid: tuple(p) for fid, p in vz.items()}
state.active_stage_name = "simple"

# ── Fixture-Gruppen ─────────────────────────────────────────────────────────
with state._session() as s:
    s.execute(delete(FixtureGroup))
    s.add(FixtureGroup(name="Alle PAR", cols=8, rows=1,
                       positions_json=json.dumps({f"{i},0": par_fids[i] for i in range(8)})))
    s.add(FixtureGroup(name="Moving Heads", cols=2, rows=1,
                       positions_json=json.dumps({"0,0": 9, "1,0": 10})))
    s.add(FixtureGroup(name="Spider", cols=2, rows=1,
                       positions_json=json.dumps({"0,0": 11, "1,0": 12})))
    s.add(FixtureGroup(name="Alle Mover", cols=4, rows=1,
                       positions_json=json.dumps({f"{i},0": mover_fids[i] for i in range(4)})))
    s.add(FixtureGroup(name="Alles", cols=12, rows=1,
                       positions_json=json.dumps({f"{i},0": all_fids[i] for i in range(12)})))
    s.commit()

# ── Tempo: Default-Bus ("Global") wird lazy benutzt. Keine festen A-D noetig. ──
get_tempo_bus_manager()   # Singleton anlegen (Default-Bus existiert)

# Farben (RGBW) + MH-Farbrad/Gobo/Shutter-Slots --------------------------------
RED, GREEN, BLUE = (255, 0, 0, 0), (0, 255, 0, 0), (0, 0, 255, 0)
YELLOW, MAGENTA, WHITE = (255, 220, 0, 0), (255, 0, 255, 0), (255, 255, 255, 255)
OFF = (0, 0, 0, 0)
RGB = lambda t: (t[0], t[1], t[2])
MHCOL = {"weiss": 4, "rot": 14, "gruen": 24, "blau": 34, "gelb": 44, "rosa": 74}
MHGOBO = {"offen": 3, "g1": 11, "g3": 27, "g5": 43, "g7": 59, "rotation": 190}
MH_OPEN, MH_STROBE = 4, 130
SP_OPEN, SP_STROBE = 8, 70


def bind_tempo(fn, group: str, mult: float = 1.0):
    """Effekt an den Master (globale BPM) koppeln, mit eigenem Multiplikator."""
    fn.tempo_bus_id = BUS
    fn.tempo_multiplier = mult
    fn.sync_group = group
    return fn


# ════════════════════════════════════════════════════════════════════════════
#  SEITE 1 — FARBE  (RGB-only Matrizen fuer PAR/Spider; Farbrad-Szenen fuer MH)
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
    # Strikt: NUR das Farbrad setzen (kein Dimmer/Shutter) — wie die PAR/Spider-Farb-
    # Matrizen. Helligkeit/Shutter kommen aus der Dimmer-Seite bzw. dem Rig-Default.
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
#  SEITE 2 — DIMMER & GOBO  (DIMMER-Style Matrizen + MH-Gobo-Szenen/Chaser)
# ════════════════════════════════════════════════════════════════════════════
def dimmer_matrix(name, fids, algo, params=None, speed=2.0, imin=0, imax=255, group=""):
    m = fm.new_rgb_matrix(name)
    m.algorithm = algo
    m.fixture_grid = list(fids)
    m.cols, m.rows = len(fids), 1
    m.colors = ColorSequence([(255, 255, 255)])
    m.style = MatrixStyle.DIMMER        # nur Dimmer — Farbe bleibt frei
    m.drive_intensity = False
    m.intensity_min, m.intensity_max = imin, imax
    m.matrix_speed = speed
    if params:
        m.params = dict(params)
    if group:
        bind_tempo(m, group)
    return m


def dimmer_effects(prefix, fids, group):
    # "Dimmer Voll" = stetig volle Helligkeit (PLAIN/Dimmer): die Grundhelligkeit, mit der
    # die Farbe sichtbar wird (per Master-Fader dimmbar). Dann die animierten Dimmer-Effekte.
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


mh_gobo = {nm: mh_gobo_scene(f"Gobo {nm}", MHGOBO[nm])
           for nm in ("offen", "g1", "g3", "g5", "g7")}
# Gobo-Wechsel: 2 feste Gobos abwechselnd (BPM-gekoppelt)
gobo_wechsel = fm.new_chaser("Gobo-Wechsel")
gobo_wechsel.run_order, gobo_wechsel.direction = RunOrder.Loop, Direction.Forward
gobo_wechsel.beats_per_step = 1
for sid in (mh_gobo["g1"].id, mh_gobo["g5"].id):
    gobo_wechsel.steps.append(ChaserStep(function_id=sid, fade_in=0.0, hold=0.4, fade_out=0.0))
bind_tempo(gobo_wechsel, "gobo_mh")


# ════════════════════════════════════════════════════════════════════════════
#  SEITE 3 — BEWEGUNG  (MH-Formen + XY-Feld/Pfad + Spider-Bewegungen)
# ════════════════════════════════════════════════════════════════════════════
def efx(name, algo, fids, group, phase_mode="sync", counter=False, size=140.0,
        speed_hz=0.5, x=128.0, y=128.0, mult=1.0):
    e = fm.new_efx(name)
    e.algorithm = algo
    e.fixtures = [EfxFixture(fid=f) for f in fids]
    e.speed_hz, e.open_beam = speed_hz, True
    e.x_offset, e.y_offset = x, y
    e.width = e.height = size
    e.phase_mode, e.counter_rotate = phase_mode, counter
    bind_tempo(e, group, mult)
    return e


# Custom-Paths: Herz + welliger Kreis (F6 — nur Daten, kein Engine-Code)
def _heart_pts(n=40):
    import math
    pts = []
    for i in range(n):
        t = 2 * math.pi * i / n
        x = 16 * (math.sin(t) ** 3)
        yv = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        pts.append((x / 34.0 + 0.5, 0.5 - yv / 34.0))
    return [(round(max(0.0, min(1.0, a)), 4), round(max(0.0, min(1.0, b)), 4)) for a, b in pts]


def _wavy_circle_pts(n=48, lobes=6, amp=0.12):
    import math
    pts = []
    for i in range(n):
        t = 2 * math.pi * i / n
        r = 0.36 + amp * math.cos(lobes * t)
        pts.append((0.5 + r * math.cos(t), 0.5 + r * math.sin(t)))
    return [(round(a, 4), round(b, 4)) for a, b in pts]


paths = get_efx_path_library()
heart_path = paths.add(EfxPath("Herz", _heart_pts(), mode="spline", closed=True))
wavy_path = paths.add(EfxPath("Welliger Kreis", _wavy_circle_pts(), mode="spline", closed=True))

mh_circle = efx("MH Kreis", EfxAlgorithm.CIRCLE, mh_fids, "mv_mh", phase_mode="sync", size=130)
mh_eight = efx("MH Acht", EfxAlgorithm.EIGHT, mh_fids, "mv_mh", phase_mode="sync", size=150)
mh_tri = efx("MH Dreieck", EfxAlgorithm.TRIANGLE, mh_fids, "mv_mh", phase_mode="sync", size=150)
mh_square = efx("MH Quadrat", EfxAlgorithm.SQUARE, mh_fids, "mv_mh", phase_mode="sync", size=150)
mh_wavy = efx("MH Welliger Kreis", EfxAlgorithm.CIRCLE, mh_fids, "mv_mh", size=170)
mh_wavy.set_custom_path(wavy_path); mh_wavy.open_beam = True
mh_heart = efx("MH Herz", EfxAlgorithm.CIRCLE, mh_fids, "mv_mh", size=170)
mh_heart.set_custom_path(heart_path); mh_heart.open_beam = True
# "MH Eigener Pfad" = der selbst gezeichnete Pfad (XY-Feld „Bahn zeichnen" schreibt hierauf).
# Eigener Knopf wie Kreis/Acht -> waehlt ihn aus, faehrt ihn im Loop (loop=True per Default).
userpath0 = paths.add(EfxPath("Eigener Pfad", [(0.2, 0.25), (0.8, 0.25), (0.8, 0.75), (0.2, 0.75)],
                              mode="linear", closed=True))
mh_userpath = efx("MH Eigener Pfad", EfxAlgorithm.CIRCLE, mh_fids, "mv_mh", size=200)
mh_userpath.set_custom_path(userpath0); mh_userpath.open_beam = True
MH_SHAPES = [mh_circle, mh_eight, mh_wavy, mh_tri, mh_square, mh_heart, mh_userpath]

# Spider-Bewegung: Tilt (2 Koepfe automatisch gegenphasig in write())
sp_converge = efx("Spider Ineinander", EfxAlgorithm.LINE, spider_fids, "mv_sp",
                  phase_mode="sync", size=200, speed_hz=0.6)
sp_diverge = efx("Spider Auseinander", EfxAlgorithm.LINE, spider_fids, "mv_sp",
                 phase_mode="offset", size=200, speed_hz=0.6)
sp_wiggle = efx("Spider Wackeln", EfxAlgorithm.LINE, spider_fids, "mv_sp",
                phase_mode="sync", size=70, speed_hz=4.0, mult=2.0)


def spider_pose(name, tilt_l, tilt_r):
    """Feste Spider-Position: beide Tilt-Kanaele (Kopf 0/1) je Spider setzen."""
    sc = fm.new_scene(name)
    for fid in spider_fids:
        tilts = attr_chs(fid, "tilt")        # 2 Tilt-Kanaele je Spider
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
# Zufalls-3-Positionen (Chaser mit Random-Reihenfolge, BPM-gekoppelt)
sp_random3 = fm.new_chaser("Spider Zufall 3")
sp_random3.run_order, sp_random3.direction = RunOrder.Random, Direction.Forward
sp_random3.beats_per_step = 2
for sid in (sp_p1.id, sp_p2.id, sp_p3.id):
    sp_random3.steps.append(ChaserStep(function_id=sid, fade_in=0.1, hold=0.6, fade_out=0.0))
bind_tempo(sp_random3, "mv_sp")
SP_MOVES = [sp_converge, sp_diverge, sp_wiggle, sp_out, sp_in, sp_random3]


# ════════════════════════════════════════════════════════════════════════════
#  SEITE 4 — STROBE + ALL-WHITE
# ════════════════════════════════════════════════════════════════════════════
def strobe_fn(name, fids):
    m = fm.new_rgb_matrix(name)
    m.algorithm = RgbAlgorithm.STROBE
    m.fixture_grid = list(fids)
    m.cols, m.rows = len(fids), 1
    m.colors = ColorSequence([(255, 255, 255)])
    m.style = MatrixStyle.DIMMER         # blitzt Dimmer (ueber der Farbe)
    m.drive_intensity = False
    m.matrix_speed = 8.0
    m.priority = 50
    bind_tempo(m, "strobe")
    return m


strobe_all = strobe_fn("Strobe Alle", all_fids)
strobe_par = strobe_fn("Strobe PAR", par_fids)
strobe_mh = strobe_fn("Strobe MH", mh_fids)
strobe_sp = strobe_fn("Strobe Spider", spider_fids)

# All-White: hochpriore Szene (PAR/Spider RGBW=255, MH Farbrad weiss) — Moment-Override
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
    if "gobo_wheel" in cm:
        all_white.set_value(fid, cm["gobo_wheel"], MHGOBO["offen"])


# ════════════════════════════════════════════════════════════════════════════
#  VIRTUAL CONSOLE
# ════════════════════════════════════════════════════════════════════════════
PAD, GAP, X0, Y0 = 56, 6, 16, 112
STEP = PAD + GAP
RX = 470                       # rechte Spalte; y<108 ist die universelle Kopfzeile
widgets: list[dict] = []
BANK_ALL = -1
B_COLOR, B_DIM, B_MOVE, B_OVER = 0, 1, 2, 3


def note_rc(r, c):   # APC-mk2-Note aus Zeile/Spalte (0=oben)
    return (7 - r) * 8 + c


def pad_xy(r, c):
    return X0 + c * STEP, Y0 + r * STEP


def _add(w, x, y, ww, hh, bank):
    w.bank = bank
    w.setGeometry(x, y, ww, hh)
    widgets.append(w.to_dict())


def fx_btn(fn, r, c, bank, accent, edit_slot, note=None):
    b = VCButton(fn.name)
    b.action = ButtonAction.FUNCTION_TOGGLE
    b.function_id = fn.id
    b.edit_slot = edit_slot
    b.pad_style = "pulse"
    b._bg_color.setNamedColor(accent)
    if note is not None:
        b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, note
    x, y = pad_xy(r, c)
    _add(b, x, y, PAD, PAD, bank)


def swatch(name, r, c, bank, rgbw, edit_slot, note=None):
    cc = VCColor(name)
    cc.color_r, cc.color_g, cc.color_b, cc.color_w = rgbw
    cc.with_intensity = False           # NUR Farbe (kein Dimmer) — Farb-Seite
    cc.target = ColorTarget.EFFECT_C1
    cc.edit_slot = edit_slot
    if note is not None:
        cc.midi_type, cc.midi_ch, cc.midi_data1 = "note_on", 0, note
    x, y = pad_xy(r, c)
    _add(cc, x, y, PAD, PAD, bank)


def action_btn(name, action, r, c, bank, accent, function_id=None, group=None, note=None,
               tempo_bus_id=None):
    b = VCButton(name)
    b.action = action
    if function_id is not None:
        b.function_id = function_id
    if group is not None:
        b.group_name = group
    if tempo_bus_id is not None:
        b.tempo_bus_id = tempo_bus_id
    b.pad_style = "solid"
    b._bg_color.setNamedColor(accent)
    if note is not None:
        b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, note
    x, y = pad_xy(r, c)
    _add(b, x, y, PAD, PAD, bank)


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
    w.show_bpm = True       # zeigt effektive BPM = Master × Faktor
    _add(w, x, y, ww, hh, bank)


def fade_fader(caption, x, y, bank, function_ids, key="env_fade", value=0, midi_cc=-1):
    s = VCSlider(caption)
    s.mode = SliderMode.EFFECT_PARAM
    s.function_ids = [f.id for f in function_ids]
    s.param_key = key
    s.midi_cc, s.midi_ch = midi_cc, 0
    s._value = value
    _add(s, x, y, 54, 140, bank)


def master_fader(caption, x, y, bank, mode, group="", slot=None, value=255, midi_cc=-1):
    s = VCSlider(caption)
    s.mode = mode
    s.programmer_group = group
    if slot is not None:
        s.function_id = slot
    s.midi_cc, s.midi_ch = midi_cc, 0
    s._value = value
    _add(s, x, y, 50, 150, bank)


def eff_colors(caption, x, y, bank, edit_slot, ww=290, hh=80):
    w = VCEffectColors(caption)
    w.edit_slot = edit_slot
    _add(w, x, y, ww, hh, bank)


def bpm_display(caption, x, y, bank, tempo_bus_id="", ww=180, hh=92):
    w = VCBpmDisplay(caption)
    w.tempo_bus_id = tempo_bus_id
    _add(w, x, y, ww, hh, bank)


def xy_pad(caption, x, y, bank, fids, mode, efx_function_id=None, ww=190, hh=190):
    w = VCXYPad(caption)
    w.mode = mode
    w._fixture_ids = list(fids)
    w.bits16 = True
    if efx_function_id is not None:
        w.efx_function_id = efx_function_id
    _add(w, x, y, ww, hh, bank)


def label(text, x, y, ww, bank, hh=18):
    _add(VCLabel(text), x, y, ww, hh, bank)


# ── Universell (alle Baenke): Master-BPM + Tap/Musik-BPM in der Kopfzeile (y<108) ──
bpm_display("MASTER BPM", RX, 8, BANK_ALL, tempo_bus_id="", ww=180, hh=90)
_tap = VCButton("Tap")
_tap.action = ButtonAction.TAP
_tap.pad_style = "solid"
_tap._bg_color.setNamedColor("#103a3a")
_add(_tap, RX + 188, 8, 86, 28, BANK_ALL)
_abpm = VCButton("Musik-BPM")
_abpm.action = ButtonAction.AUDIO_BPM
_abpm.pad_style = "solid"
_abpm._bg_color.setNamedColor("#103a4a")
_add(_abpm, RX + 188, 42, 100, 28, BANK_ALL)
# SYNC: alle laufenden Effekte auf denselben Schlag re-ankern (auch bei verschiedenen
# Multiplikatoren). AUTO-SYNC: neu gestartete Effekte uebernehmen automatisch das Raster.
_sync = VCButton("◆ SYNC")
_sync.action = ButtonAction.SYNC_BUS
_sync.tempo_bus_id = "Global"
_sync.pad_style = "solid"
_sync._bg_color.setNamedColor("#1f6a5a")
_add(_sync, RX + 296, 8, 92, 28, BANK_ALL)
_asy = VCButton("Auto-Sync")
_asy.action = ButtonAction.AUTO_SYNC
_asy.pad_style = "solid"
_asy._bg_color.setNamedColor("#3a5a1f")
_add(_asy, RX + 296, 42, 92, 28, BANK_ALL)
label("Farb-/Effekt-VC — SCENE 1-4: Farbe · Dimmer&Gobo · Bewegung · Übersicht/Strobe/Master. "
      "Effekte folgen der MASTER-BPM (oben) mit eigenem Multiplikator (Speed-Dials ¼…4×).",
      X0, 8, 440, BANK_ALL)

CA, CB = RX, RX + 162    # rechte Spalten: A = Dials (470-620), B = Editor/Fader (632-856)

# ── BANK 1 — FARBE ──────────────────────────────────────────────────────────
ACC_FX = ["#1f5a3a", "#5a3a1f", "#1f3a6a", "#5a1f6a"]   # Solid/Wechsel/Lauf/Fade
for i, fn in enumerate(par_color):                       # R0: PAR-Effekte
    fx_btn(fn, 0, i, B_COLOR, ACC_FX[i], "col_par", note=note_rc(0, i))
PAR_SW = [("Rot", RED), ("Grün", GREEN), ("Blau", BLUE), ("Gelb", YELLOW), ("Magenta", MAGENTA), ("Weiß", WHITE)]
for i, (nm, c) in enumerate(PAR_SW):                     # R1: PAR-Farbkacheln
    swatch(nm, 1, i, B_COLOR, c, "col_par", note=note_rc(1, i))
for i, nm in enumerate(("rot", "gruen", "blau", "gelb", "weiss", "rosa")):  # R2: MH-Solid/Farbe
    fx_btn(mh_solid[nm], 2, i, B_COLOR, "#3a5a1f", "col_mh", note=note_rc(2, i))
fx_btn(mh_wechsel, 3, 0, B_COLOR, "#5a3a1f", "col_mh", note=note_rc(3, 0))    # R3: MH-Effekte
fx_btn(mh_farbwechsel, 3, 1, B_COLOR, "#5a1f6a", "col_mh", note=note_rc(3, 1))
for i, fn in enumerate(spider_color):                    # R4: Spider-Effekte
    fx_btn(fn, 4, i, B_COLOR, ACC_FX[i], "col_spider", note=note_rc(4, i))
for i, (nm, c) in enumerate(PAR_SW):                     # R5: Spider-Farbkacheln
    swatch(nm, 5, i, B_COLOR, c, "col_spider", note=note_rc(5, i))
label("PAR", X0, Y0 - 14, 60, B_COLOR); label("MH", X0, pad_xy(2, 0)[1] - 14, 60, B_COLOR)
label("Spider", X0, pad_xy(4, 0)[1] - 14, 60, B_COLOR)
speed_dial("PAR ×", CA, Y0, B_COLOR, par_color)
speed_dial("MH ×", CA, Y0 + 150, B_COLOR, [mh_wechsel, mh_farbwechsel])
speed_dial("Spider ×", CA, Y0 + 300, B_COLOR, spider_color)
eff_colors("PAR Farben (Wechsel/Farbwechsel)", CB, Y0, B_COLOR, "col_par", ww=224, hh=74)
eff_colors("Spider Farben", CB, Y0 + 78, B_COLOR, "col_spider", ww=224, hh=74)
fade_fader("PAR Fade", CB, Y0 + 160, B_COLOR, par_color, midi_cc=48)
fade_fader("Spider Fade", CB + 60, Y0 + 160, B_COLOR, spider_color, midi_cc=49)
label("BANK 1 FARBE — R0 PAR-Effekte · R1 PAR-Farben · R2 MH-Farbe · R3 MH-Effekte · "
      "R4 Spider-Effekte · R5 Spider-Farben. Nur RGB — Dimmer/Shutter bleiben frei (Seite 2).",
      X0, Y0 + 6 * STEP + 4, 440, B_COLOR)

# ── BANK 2 — DIMMER & GOBO ──────────────────────────────────────────────────
for grp_i, (lbl, effs, slot) in enumerate([("PAR", par_dim, "dim_par"),
                                           ("MH", mh_dim, "dim_mh"),
                                           ("Spider", spider_dim, "dim_spider")]):
    for i, fn in enumerate(effs):
        fx_btn(fn, grp_i, i, B_DIM, "#1f3a6a", slot, note=note_rc(grp_i, i))
    label(lbl, X0, pad_xy(grp_i, 0)[1] - 14, 60, B_DIM)
    speed_dial(f"{lbl} ×", CA, Y0 + grp_i * 150, B_DIM, effs)
for i, nm in enumerate(("offen", "g1", "g3", "g5", "g7")):    # R4: MH-Gobos
    fx_btn(mh_gobo[nm], 4, i, B_DIM, "#5a3a1f", "gobo_mh", note=note_rc(4, i))
fx_btn(gobo_wechsel, 4, 5, B_DIM, "#7a6500", "gobo_mh", note=note_rc(4, 5))   # Gobo-Wechsel
label("MH-Gobo", X0, pad_xy(4, 0)[1] - 14, 90, B_DIM)
speed_dial("Gobo ×", CB, Y0, B_DIM, [gobo_wechsel])
fade_fader("PAR Dim-Fade", CB, Y0 + 154, B_DIM, par_dim, midi_cc=48)
label("BANK 2 DIMMER & GOBO — R0-2 Dimmer-Effekte (Lauflicht/Blink/Aufbau) je Gruppe "
      "(nur Dimmer, ueber der Farbe). R4 MH-Gobo-Auswahl + Gobo-Wechsel.",
      X0, Y0 + 6 * STEP + 4, 440, B_DIM)

# ── BANK 3 — BEWEGUNG ───────────────────────────────────────────────────────
SHP = ["#1f3a6a", "#1f4a6a", "#1f5a6a", "#3a1f6a", "#5a1f6a", "#6a1f4a", "#1f6a4a"]
for i, fn in enumerate(MH_SHAPES):                       # R0-1: MH-Formen
    fx_btn(fn, i // 3, i % 3, B_MOVE, SHP[i], "mv_mh", note=note_rc(i // 3, i % 3))
label("MH-Form", X0, Y0 - 14, 80, B_MOVE)
for i, fn in enumerate(SP_MOVES):                        # R3-4: Spider-Bewegung
    fx_btn(fn, 3 + i // 3, i % 3, B_MOVE, "#1f5a5a", "mv_sp", note=note_rc(3 + i // 3, i % 3))
label("Spider-Bewegung", X0, pad_xy(3, 0)[1] - 14, 140, B_MOVE)
xy_pad("MH Bereich (Box aufziehen)", CA, Y0, B_MOVE, mh_fids, "area", efx_function_id=mh_circle.id, ww=180, hh=180)
xy_pad("MH Bahn zeichnen", CA + 186, Y0, B_MOVE, mh_fids, "path", efx_function_id=mh_userpath.id, ww=180, hh=180)
speed_dial("MH ×", CA, Y0 + 188, B_MOVE, MH_SHAPES)
speed_dial("Spider ×", CA + 162, Y0 + 188, B_MOVE, [sp_converge, sp_diverge, sp_wiggle, sp_random3])
label("BANK 3 BEWEGUNG — R0-1 MH-Formen (Kreis/Acht/welliger Kreis/Dreieck/Quadrat/Herz). "
      "R3-4 Spider (Ineinander/Auseinander/Wackeln/Aussen/Innen/Zufall). Nur Pan/Tilt.",
      X0, Y0 + 6 * STEP + 4, 440, B_MOVE)

# ── BANK 4 — UEBERSICHT / STROBE / MASTER ───────────────────────────────────
# Strobe-Wahl (gehalten = Strobe an)
flash_btn(strobe_all, 0, 0, B_OVER, "#551111", note=note_rc(0, 0))
flash_btn(strobe_par, 0, 1, B_OVER, "#552222", note=note_rc(0, 1))
flash_btn(strobe_mh, 0, 2, B_OVER, "#553333", note=note_rc(0, 2))
flash_btn(strobe_sp, 0, 3, B_OVER, "#554444", note=note_rc(0, 3))
label("Strobe: Alle/PAR/MH/Spider (halten)", X0, Y0 - 14, 300, B_OVER)
# Globale Aktionen
action_btn("All White", ButtonAction.ALL_WHITE, 2, 0, B_OVER, "#888888", function_id=all_white.id, note=note_rc(2, 0))
action_btn("Blackout", ButtonAction.BLACKOUT, 2, 1, B_OVER, "#2a0000", note=note_rc(2, 1))
action_btn("Effekt-Stop", ButtonAction.STOP_EFFECTS, 2, 2, B_OVER, "#4a1010", note=note_rc(2, 2))
action_btn("Pause", ButtonAction.STOP_EFFECTS, 2, 3, B_OVER, "#3a2a10", note=note_rc(2, 3))
action_btn("Freeze", ButtonAction.FREEZE, 2, 4, B_OVER, "#103a4a", note=note_rc(2, 4))
label("Aktionen: All White (halten) · Blackout · Effekt-Stop · Pause · Freeze (BPM=0)",
      X0, pad_xy(2, 0)[1] - 14, 420, B_OVER)
# Uebersicht: dieselben Multiplikatoren wie S.1-3 (synchron, da gleiche function_ids)
bpm_display("MASTER", CA, Y0, B_OVER, tempo_bus_id="", ww=150, hh=82)
speed_dial("Farbe ×", CA, Y0 + 90, B_OVER, par_color + spider_color)
speed_dial("Bewegung ×", CA, Y0 + 240, B_OVER, MH_SHAPES + [sp_converge, sp_diverge, sp_wiggle, sp_random3])
# 4 Master-Dimmer ganz rechts: Spider / MH / PAR / GRAND
MFX = CB
master_fader("Spider M", MFX, Y0, B_OVER, SliderMode.GROUP_DIMMER, group="Spider", midi_cc=53)
master_fader("MH M", MFX + 54, Y0, B_OVER, SliderMode.GROUP_DIMMER, group="Moving Heads", midi_cc=54)
master_fader("PAR M", MFX + 108, Y0, B_OVER, SliderMode.GROUP_DIMMER, group="Alle PAR", midi_cc=55)
master_fader("GRAND", MFX + 162, Y0, B_OVER, SliderMode.GRANDMASTER, midi_cc=56)
label("BANK 4 — R0 Strobe-Wahl · R2 All White/Blackout/Effekt-Stop/Pause/Freeze. Rechts: "
      "Speed-Uebersicht (synchron mit S.1-3) + 4 Master-Dimmer (Spider/MH/PAR/GRAND).",
      X0, Y0 + 6 * STEP + 4, 440, B_OVER)


state._vc_layout = {"widgets": widgets}
state.programmer = {}
state.show_name = "Farb FX VC Show"
# Auto-Sync standardmaessig AN: neu gestartete bus-gekoppelte Effekte uebernehmen den
# gemeinsamen Beat-Raster-Ursprung -> ×1/×0.5/… beginnen phasengleich. ◆ SYNC re-basiert.
get_tempo_bus_manager().set_auto_sync(True)
save_show(OUT)
print(f"Gespeichert: {OUT}")

# ════════════════════════════════════════════════════════════════════════════
#  VERIFIKATION (Round-Trip + Inhalt)
# ════════════════════════════════════════════════════════════════════════════
ok, msg = load_show(OUT)
print("Load:", ok, msg)
assert ok, f"Show laedt nicht: {msg}"
state = get_state()
fm = get_function_manager()

from collections import Counter
from src.core.engine.rgb_matrix import RgbMatrixInstance, MatrixStyle as MS
from src.core.engine.efx import EfxInstance
from src.core.engine.scene import Scene
from src.core.engine.chaser import Chaser

fx = state.get_patched_fixtures()
assert len(fx) == 12, f"Fixtures: {len(fx)}"

mats = [f for f in fm.all() if isinstance(f, RgbMatrixInstance)]
color_m = [m for m in mats if m.style == MS.RGB and not m.drive_intensity]
dim_m = [m for m in mats if m.style == MS.DIMMER]
assert len(color_m) >= 8, f"Farb-Matrizen (RGB): {len(color_m)}"     # PAR4 + Spider4
assert len(dim_m) >= 9, f"Dimmer-Matrizen: {len(dim_m)}"             # 3x3 + 4 strobe
checker = [m for m in color_m if m.algorithm == RgbAlgorithm.CHECKER]
assert checker, "kein CHECKER-Farbeffekt"
# Farb-Matrix masked: schreibt nur Farbe, nicht intensity
assert all(not m.drive_intensity for m in color_m), "Farb-Matrix treibt Dimmer (kein Masking)"

efxs = [f for f in fm.all() if isinstance(f, EfxInstance)]
assert len(efxs) >= 9, f"EFX: {len(efxs)}"
custom = [e for e in efxs if e.algorithm == EfxAlgorithm.CUSTOM and e.path_data]
assert len(custom) >= 2, f"Custom-Path-EFX (Herz/welliger Kreis): {len(custom)}"

# Tempo-Kopplung: viele Effekte auf "Global" mit Multiplikator
bound = [f for f in fm.all() if getattr(f, "tempo_bus_id", "") == BUS]
assert len(bound) >= 20, f"an Master gekoppelte Effekte: {len(bound)}"

# Auto-Sync persistiert + SYNC/Auto-Sync-Knopf vorhanden
assert get_tempo_bus_manager().auto_sync is True, "Auto-Sync nicht persistiert"
assert state.implicit_brightness is False, "implicit_brightness nicht persistiert (strikte Trennung)"
vcw = state._vc_layout.get("widgets", [])
acts = {w.get("action") for w in vcw if w.get("type") == "VCButton"}
assert "SyncBus" in acts, "kein SYNC-Knopf"
assert "AutoSync" in acts, "kein Auto-Sync-Knopf"
_syncbtn = next(w for w in vcw if w.get("action") == "SyncBus")
assert _syncbtn.get("tempo_bus_id") == "Global", "SYNC nicht auf Global-Bus"

# MH-Farb-/Gobo-Szenen schreiben color_wheel/gobo_wheel
cw = chan_of[9]["color_wheel"]; gw = chan_of[9]["gobo_wheel"]
sc_rot = next(f for f in fm.all() if isinstance(f, Scene) and f.name == "MH Rot")
assert sc_rot.get_value(9, cw) == MHCOL["rot"], "MH Rot Farbrad falsch"
sc_g1 = next(f for f in fm.all() if isinstance(f, Scene) and f.name == "Gobo g1")
assert sc_g1.get_value(9, gw) == MHGOBO["g1"], "Gobo g1 falsch"

# All-White hochprior + weiss
aw = next(f for f in fm.all() if isinstance(f, Scene) and f.name == "All White")
assert aw.priority >= 9999, "All-White nicht hochprior"
assert aw.get_value(1, chan_of[1]["color_r"]) == 255, "All-White PAR nicht weiss"

# Spider-Random-3 = Chaser Random
r3 = next(f for f in fm.all() if isinstance(f, Chaser) and f.name == "Spider Zufall 3")
assert r3.run_order == RunOrder.Random and len(r3.steps) == 3, "Zufall-3 falsch"

# VC: 4 Baenke, neue Widget-Typen, keine Ueberlappung
vc = state._vc_layout.get("widgets", [])
banks = Counter(w.get("bank") for w in vc)
assert set(banks) >= {0, 1, 2, 3, -1}, f"Banks: {sorted(banks)}"
types = Counter(w["type"] for w in vc)
for t in ("VCSpeedDial", "VCBpmDisplay", "VCEffectColors", "VCXYPad", "VCColor", "VCSlider"):
    assert types.get(t, 0) >= 1, f"Widget fehlt: {t} ({dict(types)})"
# XY-Pad path-Modus vorhanden
assert any(w["type"] == "VCXYPad" and w.get("mode") == "path" for w in vc), "kein Pfad-XY-Pad"
# 4 Master-Fader (1 GrandMaster + 3 GroupDimmer) auf Bank 4
gm = [w for w in vc if w["type"] == "VCSlider" and w.get("mode") == "GrandMaster"]
gd = [w for w in vc if w["type"] == "VCSlider" and w.get("mode") == "GroupDimmer"]
assert len(gm) >= 1 and len(gd) >= 3, f"Master-Fader: GM={len(gm)} GroupDim={len(gd)}"

_INTER = {"VCButton", "VCSlider", "VCColor", "VCXYPad", "VCSpeedDial", "VCBpmDisplay",
          "VCEffectColors"}


def _rect(w):
    return (w.get("x", 0), w.get("y", 0), w.get("x", 0) + w.get("w", 0), w.get("y", 0) + w.get("h", 0))


def _ov(a, b):
    ax0, ay0, ax1, ay1 = _rect(a); bx0, by0, bx1, by1 = _rect(b)
    return not (ax1 <= bx0 or bx1 <= ax0 or ay1 <= by0 or by1 <= ay0)


for bk in range(4):
    layer = [w for w in vc if w.get("bank") in (bk, -1) and w["type"] in _INTER]
    for a in range(len(layer)):
        for b in range(a + 1, len(layer)):
            assert not _ov(layer[a], layer[b]), (
                f"Overlap Bank {bk}: {layer[a]['type']}@{_rect(layer[a])} "
                f"vs {layer[b]['type']}@{_rect(layer[b])}")

maxy = max((w.get("y", 0) + w.get("h", 0)) for w in vc)
print(f"Funktionen: {len(fm.all())}  VC-Widgets: {len(vc)}  Max-Y={maxy}")
print(f"  Farb-Matrizen={len(color_m)} (Checker={len(checker)})  Dimmer-Matrizen={len(dim_m)}  "
      f"EFX={len(efxs)} (Custom={len(custom)})  an Master gekoppelt={len(bound)}")
print(f"  Widget-Typen={dict(types)}")
print("  [OK] 4 Baenke — Farbe(masked) · Dimmer&Gobo · Bewegung · Übersicht/Strobe/Master")
print("FERTIG")
