"""EVENT-DEMO 2026 — grosse, vollstaendige Demo-Show fuer ein Event.

Zeigt ALLE neuen LightOS-Features auf Davids realem Rig:
  * Farb-Matrizen, Dimmer-Matrizen, Matrix-Effekte (Feuer/Regen/Radar/Spirale/Wipe)
  * Chases (Matrix-Chase, Beat-Sync-Cuelisten, Auto-Farbschema)
  * Moving Heads mit Farbrad + Gobo + Bewegung (EFX)
  * Spider mit Tilt-Bewegung + Farb-Themes (pro Bar)
  * BPM-Erkennung + Tempo-Sync-Buses + Master/Sub-Geschwindigkeiten
  * APC-mini-Layout (SCENE = Bank/Seite), gut bedienbare VC
  * Misch-Ablaeufe (Farbe x Bewegung x Strobo) als Collections + Live-Chase

Rig (Adressierung, Universe 1, 114 Kanaele):
  8x RGBW-PAR (ZQ01424, 8ch) @ DMX 1-64  ->  in EINER Reihe.
  2x Moving Head (ZQ02001, 11ch) @ 65 / 76  ->  HINTER PAR 1 und PAR 8.
  2x Spider (SPIDER14, 14ch) @ 87 / 101  ->  VOR PAR 1 und PAR 8.

Aufruf:  venv/Scripts/python.exe tools/build_event_demo_2026.py
Erzeugt: shows/Event_Demo_2026.lshow
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
from src.core.engine.cue import Cue
from src.core.engine.tempo_bus import get_tempo_bus_manager
from src.core.show.show_file import reset_show, save_show, load_show
from src.core.audio.media_player import clean_title, guess_genre_bpm
from src.ui.virtualconsole.vc_button import VCButton, ButtonAction
from src.ui.virtualconsole.vc_color import VCColor, ColorTarget
from src.ui.virtualconsole.vc_label import VCLabel
from src.ui.virtualconsole.vc_cuelist import VCCueList
from src.ui.virtualconsole.vc_song_info import VCSongInfo
from src.ui.virtualconsole.vc_slider import VCSlider, SliderMode
from src.ui.virtualconsole.vc_speedial import VCSpeedDial, SpeedTarget
from src.ui.virtualconsole.vc_bpm_display import VCBpmDisplay
from src.ui.virtualconsole.vc_bus_selector import VCBusSelector
from src.ui.virtualconsole.vc_effect_colors import VCEffectColors
from src.ui.virtualconsole.vc_color_list import VCColorList
from src.ui.virtualconsole.vc_chase_builder import VCChaseBuilder
from src.ui.virtualconsole.vc_xypad import VCXYPad

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(_ROOT, "shows", "Event_Demo_2026.lshow")
MUSIC_DIR = r"C:/Users/David/Desktop/Musik/BP Party"

BPM = 150.0
BEAT = 60.0 / BPM          # 0.40 s
BAR = 4 * BEAT             # 1.60 s
PHRASE = 8 * BEAT          # 3.20 s


def profile_id(short: str) -> int:
    with Session(fdb_engine()) as s:
        pid = s.execute(select(FixtureProfile.id).where(
            FixtureProfile.short_name == short)).scalar_one_or_none()
    if pid is None:
        raise SystemExit(f"Profil '{short}' fehlt — bitte App einmal starten (ensure_builtins).")
    return int(pid)


# ════════════════════════════════════════════════════════════════════════════════
#  0) BASIS + PATCH
# ════════════════════════════════════════════════════════════════════════════════
reset_show()
state = get_state()
fm = get_function_manager()
PAR_PID = profile_id("ZQ01424")
MH_PID = profile_id("ZQ02001")
SPIDER_PID = profile_id("SPIDER14")

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

mover_fids = mh_fids + spider_fids          # alle mit Pan/Tilt-Bewegung (EFX)
color_fids = par_fids + spider_fids         # alle mit RGB(W) (Farb-Matrix/-Szenen)
rgb_fids = par_fids + spider_fids           # Matrix-Raster (Matrix schreibt pro Kanal)
all_fids = par_fids + mh_fids + spider_fids

fixtures = state.get_patched_fixtures()
fx_of = {f.fid: f for f in fixtures}
chans_full = {f.fid: get_channels_for_patched(f) for f in fixtures}
# Eindeutige Attribut->Kanalnummer-Map (fuer MH; bei doppelten Attributen = letztes Vorkommen).
chan_of = {f.fid: {c.attribute: c.channel_number for c in chans_full[f.fid]} for f in fixtures}


def attr_chs(fid: int, attr: str) -> list[int]:
    """ALLE Kanalnummern eines Attributs (Spider: color_r/g/b/w doppelt -> beide Baenke)."""
    return [c.channel_number for c in chans_full[fid] if (c.attribute or "").lower() == attr]


# Grundhelligkeit: PAR + Spider leuchten standardmaessig (Farb-Matrix ohne Dimmer sichtbar).
state.base_levels = {fid: {"intensity": 255} for fid in color_fids}
state._rebuild_render_plan()

# ── 2D-Live-View + 3D-Positionen (Buehne oben/klein-y, Publikum unten/gross-y) ──────
PX = {par_fids[i]: 230.0 + i * 105.0 for i in range(8)}     # PAR-Reihe x: 230..965
lv = {fid: (PX[fid], 420.0) for fid in par_fids}            # PAR-Reihe Mitte
lv[9] = (PX[par_fids[0]], 250.0)     # MH Links  HINTER PAR 1 (kleines y = hinten)
lv[10] = (PX[par_fids[7]], 250.0)    # MH Rechts HINTER PAR 8
lv[11] = (PX[par_fids[0]], 600.0)    # Spider Links  VOR PAR 1 (grosses y = vorne)
lv[12] = (PX[par_fids[7]], 600.0)    # Spider Rechts VOR PAR 8
state.live_view_positions = {fid: list(p) for fid, p in lv.items()}
state.live_view_meta = {"zoom": 1.0, "grid_size": 20, "snap": True,
                        "grid_visible": True, "world_w": 1200, "world_h": 800}
vz = {fid: ((PX[fid] - 600.0) / 80.0, 0.0, 0.0) for fid in par_fids}   # Reihe am Boden
vz[9] = (vz[par_fids[0]][0], 6.0, -1.8)    # MH hoch montiert, hinten (neg. z)
vz[10] = (vz[par_fids[7]][0], 6.0, -1.8)
vz[11] = (vz[par_fids[0]][0], 0.6, 1.8)    # Spider tief, vorne (pos. z)
vz[12] = (vz[par_fids[7]][0], 0.6, 1.8)
state.visualizer_positions = {fid: tuple(p) for fid, p in vz.items()}
state.active_stage_name = "simple"

# ── Fixture-Gruppen ────────────────────────────────────────────────────────────
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


# ════════════════════════════════════════════════════════════════════════════════
#  1) MUSIK-PLAYLIST
# ════════════════════════════════════════════════════════════════════════════════
CURATED = [
    ("mr. brightside", "Bounce", 150), ("angels (jesse bloch", "Bounce", 150),
    ("i need a hero", None, None), ("africa (rayvolt", None, None),
    ("major tom", None, None), ("gym hardstyle", None, None),
]


def resolve_track(keyword: str) -> str | None:
    hits = [p for p in glob.glob(os.path.join(MUSIC_DIR, "*.mp3"))
            if keyword in os.path.basename(p).lower()]
    if not hits:
        return None
    return sorted(hits, key=lambda p: ("kopie" in p.lower(), len(p)))[0]


playlist: list[dict] = []
missing = 0
for kw, g_over, b_over in CURATED:
    p = resolve_track(kw)
    if p is None:
        missing += 1
        p = os.path.join(MUSIC_DIR, kw + ".mp3")
    name = os.path.basename(p)
    genre, bpm = guess_genre_bpm(name)
    playlist.append({"path": p, "title": clean_title(p), "genre": g_over or genre,
                     "bpm": float(b_over if b_over is not None else bpm)})
state.playlist = playlist
if missing:
    print(f"[build] WARNUNG: {missing} Track(s) nicht gefunden — Platzhalter eingetragen.")


# ════════════════════════════════════════════════════════════════════════════════
#  2) TEMPO-BUSES + GRAND-MASTER  (Master/Sub-Geschwindigkeiten)
# ════════════════════════════════════════════════════════════════════════════════
tbm = get_tempo_bus_manager()
tbm.load_dict([])                          # frischer Stand
bus_a = tbm.ensure_bus("A"); bus_a.set_role("master"); bus_a.set_bpm(BPM)        # Haupttakt
bus_b = tbm.ensure_bus("B"); bus_b.set_role("sub"); bus_b.set_parent("A"); bus_b.set_bus_multiplier(0.5)   # halb
bus_c = tbm.ensure_bus("C"); bus_c.set_role("sub"); bus_c.set_parent("A"); bus_c.set_bus_multiplier(2.0)   # doppelt
bus_d = tbm.ensure_bus("D"); bus_d.set_role("master"); bus_d.set_bpm(128.0)      # zweiter freier Master
tbm.set_grandmaster_bpm(BPM)
tbm.set_grandmaster_armed(False)           # bereit, aber nicht scharf (per VC scharf schalten)


# ════════════════════════════════════════════════════════════════════════════════
#  3) FUNKTIONS-BIBLIOTHEK
# ════════════════════════════════════════════════════════════════════════════════
# RGBW-Tupel (PAR/Spider) ----------------------------------------------------------
RED, GREEN, BLUE = (255, 0, 0, 0), (0, 255, 0, 0), (0, 0, 255, 0)
YELLOW, CYAN, MAGENTA = (255, 220, 0, 0), (0, 255, 255, 0), (255, 0, 255, 0)
WHITE, AMBER, PINK = (255, 255, 255, 255), (255, 120, 0, 0), (255, 0, 120, 0)
RGB = lambda t: (t[0], t[1], t[2])

# MH-Farbrad / Gobo / Shutter (echte ZQ02001-Slots) --------------------------------
MHCOL = {"weiss": 4, "rot": 14, "gruen": 24, "blau": 34, "gelb": 44,
         "orange": 54, "hellblau": 64, "rosa": 74, "rotation": 150}
MHGOBO = {"offen": 3, "g1": 11, "g2": 19, "g3": 27, "g4": 35, "g5": 43,
          "g6": 51, "g7": 59, "rotation": 190}
MH_OPEN, MH_STROBE = 4, 130          # shutter
SP_OPEN, SP_STROBE = 8, 70           # spider shutter (0-7 zu!)


def scene_color(sc, fids, rgbw, inten=255):
    """Farbe+Intensitaet+offener Shutter auf PAR/Spider (alle Kanalnummern -> beide Spider-Baenke)."""
    r, g, b, w = rgbw
    for fid in fids:
        for ch in attr_chs(fid, "intensity"):
            sc.set_value(fid, ch, inten)
        for attr, val in (("color_r", r), ("color_g", g), ("color_b", b), ("color_w", w)):
            for ch in attr_chs(fid, attr):
                sc.set_value(fid, ch, val)
        for ch in attr_chs(fid, "shutter"):
            sc.set_value(fid, ch, open_value_for(fx_of[fid], "shutter"))


def look(name, rgbw, fids=None):
    sc = fm.new_scene(name)
    scene_color(sc, fids if fids is not None else color_fids, rgbw)
    return sc


def mh_scene(name, col=None, gobo=None, strobe=False, inten=255):
    """Moving-Head-Look: Farbrad + optional Gobo (+ Strobe/Shutter offen + Dimmer)."""
    sc = fm.new_scene(name)
    for fid in mh_fids:
        cm = chan_of[fid]
        if "intensity" in cm:
            sc.set_value(fid, cm["intensity"], inten)
        if "shutter" in cm:
            sc.set_value(fid, cm["shutter"], MH_STROBE if strobe else MH_OPEN)
        if col is not None and "color_wheel" in cm:
            sc.set_value(fid, cm["color_wheel"], col)
        if gobo is not None and "gobo_wheel" in cm:
            sc.set_value(fid, cm["gobo_wheel"], gobo)
    return sc


def spider_theme(name, rgbw_l, rgbw_r, inten=255):
    """Spider-Theme: linke Bar (Bank 1) Farbe A, rechte Bar (Bank 2) Farbe B — beide Spider."""
    sc = fm.new_scene(name)
    for fid in spider_fids:
        cols = [c for c in chans_full[fid]
                if (c.attribute or "") in ("color_r", "color_g", "color_b", "color_w")]
        bank1, bank2 = cols[:4], cols[4:]
        for c, v in zip(bank1, rgbw_l):
            sc.set_value(fid, c.channel_number, v)
        for c, v in zip(bank2, rgbw_r):
            sc.set_value(fid, c.channel_number, v)
        for ch in attr_chs(fid, "intensity"):
            sc.set_value(fid, ch, inten)
        for ch in attr_chs(fid, "shutter"):
            sc.set_value(fid, ch, SP_OPEN)
    return sc


def dim_scene(name, on_fids):
    sc = fm.new_scene(name)
    on = set(on_fids)
    for fid in color_fids:
        for ch in attr_chs(fid, "intensity"):
            sc.set_value(fid, ch, 255 if fid in on else 0)
    return sc


# ── Farb-Matrizen (RGB, drive_intensity=False -> reine Farbebene) ───────────────────
def color_matrix(name, algo, colors, params=None, speed=1.2, bus="", mult=1.0, prio=0):
    m = fm.new_rgb_matrix(name)
    m.algorithm = algo
    m.fixture_grid = list(rgb_fids)
    m.cols, m.rows = len(rgb_fids), 1
    m.colors = ColorSequence([tuple(c) for c in colors])
    m.style = MatrixStyle.RGB
    m.drive_intensity = False
    m.matrix_speed = speed
    m.priority = prio
    if bus:
        m.tempo_bus_id = bus
        m.tempo_multiplier = mult
        m.sync_group = "event"
    if params:
        m.params = dict(params)
    return m


mtx_rainbow = color_matrix("Farbe Regenbogen", RgbAlgorithm.RAINBOW, [(255, 0, 0)],
                           params={"movement": "linear", "spread": 1.0, "saturation": 1.0, "value": 1.0})
mtx_gradient = color_matrix("Farbe Verlauf", RgbAlgorithm.GRADIENT, [RGB(BLUE), RGB(MAGENTA), RGB(CYAN)],
                            params={"axis": "H", "blend": "smooth"}, speed=0.6)
mtx_chase = color_matrix("Farb-Chase", RgbAlgorithm.CHASE, [RGB(BLUE), RGB(WHITE)],
                         params={"axis": "H", "movement": "normal", "runner_count": 1,
                                 "runner_width": 1, "after_fade": 35.0}, speed=3.0)
mtx_fade = color_matrix("Farb-Fade", RgbAlgorithm.COLORFADE, [RGB(RED), RGB(GREEN), RGB(BLUE)],
                        params={"hold": 0.2}, speed=0.8)
mtx_plasma = color_matrix("Farb-Plasma", RgbAlgorithm.SINEPLASMA, [RGB(MAGENTA), RGB(CYAN)], speed=0.5)
mtx_pin = color_matrix("Farb-Windrad", RgbAlgorithm.PINWHEEL, [RGB(RED), RGB(BLUE)],
                       params={"runner_count": 2}, speed=1.0)
COLOR_MATRICES = [mtx_rainbow, mtx_gradient, mtx_chase, mtx_fade, mtx_plasma, mtx_pin]


# ── Dimmer-Matrizen (DIMMER-Style -> nur Dimmer-Kanal, ueber Farbe legbar) ──────────
def dimmer_matrix(name, algo, params=None, speed=1.5, imin=0, imax=255, prio=1, bus="", mult=1.0):
    m = fm.new_rgb_matrix(name)
    m.algorithm = algo
    m.fixture_grid = list(rgb_fids)
    m.cols, m.rows = len(rgb_fids), 1
    m.colors = ColorSequence([(255, 255, 255)])
    m.style = MatrixStyle.DIMMER
    m.drive_intensity = False
    m.intensity_min, m.intensity_max = imin, imax
    m.matrix_speed = speed
    m.priority = prio
    if bus:
        m.tempo_bus_id = bus
        m.tempo_multiplier = mult
        m.sync_group = "event"
    if params:
        m.params = dict(params)
    return m


dim_breathe = dimmer_matrix("Dimmer Atmen", RgbAlgorithm.BREATHE, speed=0.8)
dim_wave = dimmer_matrix("Dimmer Welle", RgbAlgorithm.WAVE,
                         params={"origin": "left", "density": 1.0, "spread": 1.0}, speed=1.5)
dim_fill = dimmer_matrix("Dimmer Aufbau", RgbAlgorithm.FILL,
                         params={"fill_mode": "up", "fill_dir": "left", "loop_mode": "reverse"}, speed=1.5)
dim_strobe = dimmer_matrix("Dimmer Blitz", RgbAlgorithm.STROBE, speed=6.0)
dim_spark = dimmer_matrix("Dimmer Funkeln", RgbAlgorithm.RANDOM,
                          params={"mode": "sparkle", "count": 3, "rate": 4.0}, speed=2.0)
DIMMER_MATRICES = [dim_breathe, dim_wave, dim_fill, dim_strobe, dim_spark]


# ── Matrix-Effekte (RGB-Style, ausgefallene Algorithmen) ────────────────────────────
def fx_matrix(name, algo, colors, params=None, speed=1.0):
    m = fm.new_rgb_matrix(name)
    m.algorithm = algo
    m.fixture_grid = list(rgb_fids)
    m.cols, m.rows = len(rgb_fids), 1
    m.colors = ColorSequence([tuple(c) for c in colors])
    m.style = MatrixStyle.RGB
    m.drive_intensity = False
    m.matrix_speed = speed
    if params:
        m.params = dict(params)
    return m


fx_fire = fx_matrix("Effekt Feuer", RgbAlgorithm.FIRE, [RGB(RED), RGB(YELLOW)], speed=1.4)
fx_rain = fx_matrix("Effekt Regen", RgbAlgorithm.RAIN, [RGB(CYAN)], params={"fade": 0.4}, speed=1.6)
fx_radar = fx_matrix("Effekt Radar", RgbAlgorithm.RADAR, [RGB(GREEN)],
                     params={"beam_width": 0.15, "fade": 0.3}, speed=1.0)
fx_spiral = fx_matrix("Effekt Spirale", RgbAlgorithm.SPIRAL, [RGB(MAGENTA)],
                      params={"turns": 2.0, "beam_width": 0.15}, speed=1.0)
fx_wipe = fx_matrix("Effekt Wisch", RgbAlgorithm.WIPE, [RGB(WHITE), RGB(BLUE)],
                    params={"axis": "H", "movement": "bounce", "edge_fade": 0.2}, speed=1.2)
fx_wave = fx_matrix("Effekt Welle", RgbAlgorithm.WAVE, [RGB(BLUE), RGB(WHITE)],
                    params={"origin": "radial", "density": 1.0, "spread": 1.0}, speed=1.2)
FX_MATRICES = [fx_fire, fx_rain, fx_radar, fx_spiral, fx_wipe, fx_wave]


# ── EFX (Bewegung) ──────────────────────────────────────────────────────────────────
def efx(name, algo, fids, phase_mode="fan", spread=1.0, counter=False, mirror=False,
        x=128.0, y=128.0, size=150.0, speed_hz=0.45, xf=3.0, yf=2.0, direction="forward",
        bus="", mult=1.0):
    e = fm.new_efx(name)
    e.algorithm = algo
    e.fixtures = [EfxFixture(fid=f) for f in fids]
    e.speed_hz, e.spread, e.open_beam = speed_hz, spread, True
    e.x_offset, e.y_offset = x, y
    e.width = e.height = size
    e.phase_mode, e.counter_rotate, e.mirror = phase_mode, counter, mirror
    e.x_freq, e.y_freq = xf, yf
    e.direction = direction
    if bus:
        e.tempo_bus_id = bus
        e.tempo_multiplier = mult
        e.sync_group = "event"
    return e


efx_mh_circle = efx("MH Kreis", EfxAlgorithm.CIRCLE, mh_fids, phase_mode="sync", size=120, speed_hz=0.5)
efx_mh_fan = efx("MH Fächer", EfxAlgorithm.CIRCLE, mh_fids, phase_mode="fan", counter=True, size=160, speed_hz=0.45)
efx_mh_eight = efx("MH Acht", EfxAlgorithm.EIGHT, mh_fids, phase_mode="sync", size=130, speed_hz=0.4)
efx_mh_lissa = efx("MH Lissajous", EfxAlgorithm.LISSAJOUS, mh_fids, phase_mode="fan", size=170, speed_hz=0.4, xf=3.0, yf=2.0)
efx_mh_square = efx("MH Rechteck", EfxAlgorithm.SQUARE, mh_fids, phase_mode="sync", size=150, speed_hz=0.35)
efx_spider_scissor = efx("Spider Schere", EfxAlgorithm.CIRCLE, spider_fids, phase_mode="sync", size=200, speed_hz=0.6)
efx_spider_line = efx("Spider Wippe", EfxAlgorithm.LINE, spider_fids, phase_mode="offset", size=220, speed_hz=0.7)
efx_all = efx("Alle Mover Fächer", EfxAlgorithm.CIRCLE, mover_fids, phase_mode="fan", counter=True, size=150, speed_hz=0.5)
EFX_MH = [efx_mh_circle, efx_mh_fan, efx_mh_eight, efx_mh_lissa, efx_mh_square]
EFX_SPIDER = [efx_spider_scissor, efx_spider_line]

# Custom-Path-EFX (selbst gezeichnete Bahn) — Showcase.
try:
    paths = get_efx_path_library()
    zig = paths.add(EfxPath("Zickzack", [(0.1, 0.3), (0.35, 0.75), (0.6, 0.3), (0.9, 0.75)],
                            mode="linear", closed=False))
    efx_mh_custom = fm.new_efx("MH Zickzack (Pfad)")
    efx_mh_custom.fixtures = [EfxFixture(fid=f) for f in mh_fids]
    efx_mh_custom.set_custom_path(zig)
    efx_mh_custom.open_beam = True
    efx_mh_custom.width = efx_mh_custom.height = 170.0
    EFX_MH.append(efx_mh_custom)
except Exception as e:  # pragma: no cover
    print(f"[build] Custom-Path uebersprungen: {e}")
    efx_mh_custom = None


# ── MH-Farb-/Gobo-/Strobe-Szenen ────────────────────────────────────────────────────
mh_red = mh_scene("MH Rot", col=MHCOL["rot"])
mh_green = mh_scene("MH Grün", col=MHCOL["gruen"])
mh_blue = mh_scene("MH Blau", col=MHCOL["blau"])
mh_yellow = mh_scene("MH Gelb", col=MHCOL["gelb"])
mh_white = mh_scene("MH Weiß", col=MHCOL["weiss"])
mh_colspin = mh_scene("MH Farbrotation", col=MHCOL["rotation"])
MH_COLORS = [mh_red, mh_green, mh_blue, mh_yellow, mh_white, mh_colspin]
mh_g1 = mh_scene("MH Gobo 1", col=MHCOL["blau"], gobo=MHGOBO["g1"])
mh_g3 = mh_scene("MH Gobo 3", col=MHCOL["gruen"], gobo=MHGOBO["g3"])
mh_g5 = mh_scene("MH Gobo 5", col=MHCOL["rot"], gobo=MHGOBO["g5"])
mh_g7 = mh_scene("MH Gobo 7", col=MHCOL["gelb"], gobo=MHGOBO["g7"])
mh_gspin = mh_scene("MH Gobo Rotation", col=MHCOL["weiss"], gobo=MHGOBO["rotation"])
MH_GOBOS = [mh_g1, mh_g3, mh_g5, mh_g7, mh_gspin]
mh_strobe = mh_scene("MH Strobe", col=MHCOL["weiss"], strobe=True)


# ── Spider-Themes ───────────────────────────────────────────────────────────────────
sp_rb = spider_theme("Spider Rot/Blau", RED, BLUE)
sp_gm = spider_theme("Spider Grün/Magenta", GREEN, MAGENTA)
sp_cw = spider_theme("Spider Cyan/Warm", CYAN, AMBER)
sp_pw = spider_theme("Spider Pink/Weiß", PINK, WHITE)
sp_white = spider_theme("Spider Weiß", WHITE, WHITE)
SP_THEMES = [sp_rb, sp_gm, sp_cw, sp_pw, sp_white]
sp_strobe = fm.new_scene("Spider Strobe")
for fid in spider_fids:
    for ch in attr_chs(fid, "intensity"):
        sp_strobe.set_value(fid, ch, 255)
    for ch in attr_chs(fid, "shutter"):
        sp_strobe.set_value(fid, ch, SP_STROBE)


# ── Voll-Looks (PAR+Spider) ─────────────────────────────────────────────────────────
look_red = look("Look Rot", RED)
look_green = look("Look Grün", GREEN)
look_blue = look("Look Blau", BLUE)
look_white = look("Look Weiß", WHITE)
VIVID = [look_red, look_green, look_blue, look_white]
LEFT, RIGHT = par_fids[:4], par_fids[4:]


def split_scene(name, lc, rc):
    sc = fm.new_scene(name)
    scene_color(sc, LEFT + [11], lc)
    scene_color(sc, RIGHT + [12], rc)
    return sc


sp_split_gb = split_scene("Grün links / Blau rechts", GREEN, BLUE)
sp_split_rw = split_scene("Rot links / Weiß rechts", RED, WHITE)
SPLITS = [sp_split_gb, sp_split_rw]


# ── Chaser ──────────────────────────────────────────────────────────────────────────
def chaser(name, step_ids, hold=BEAT, fade=0.0, speed=1.0, audio=False,
           beats_per_step=1, run_order=RunOrder.Loop, prio=0):
    c = fm.new_chaser(name)
    c.run_order, c.direction, c.speed = run_order, Direction.Forward, speed
    c.audio_triggered, c.beats_per_step = audio, beats_per_step
    c.priority = prio
    for sid in step_ids:
        c.steps.append(ChaserStep(function_id=sid, fade_in=fade, hold=hold, fade_out=0.0))
    return c


chase_looks = chaser("Chase Voll-Looks", [s.id for s in VIVID], hold=BAR, fade=0.2)
chase_mh_color = chaser("Chase MH-Farben", [s.id for s in MH_COLORS[:5]], hold=BEAT * 2, fade=0.05)
chase_spider = chaser("Chase Spider-Themes", [s.id for s in SP_THEMES], hold=BAR, fade=0.3)
auto_schema = chaser("Auto-Farbschema (Beat)", [mtx_rainbow.id, mtx_gradient.id, mtx_plasma.id],
                     audio=True, beats_per_step=16, fade=BAR)
drop_color = chaser("Drop Farbwechsel (Beat)",
                    [look_red.id, sp_split_gb.id, look_blue.id, sp_split_rw.id, look_white.id],
                    audio=True, beats_per_step=2, fade=0.04)
CHASERS = [chase_looks, chase_mh_color, chase_spider, auto_schema, drop_color]


# ── Tempo-synchrone Effekte (Master/Sub-Demo) ───────────────────────────────────────
sync_chase = color_matrix("Sync Chase >Bus A", RgbAlgorithm.CHASE, [RGB(BLUE), RGB(WHITE)],
                          params={"axis": "H", "movement": "normal", "color_cycle": True},
                          speed=1.0, bus="A", mult=1.0, prio=2)
sync_breathe = dimmer_matrix("Sync Atmen >Bus B (1/2)", RgbAlgorithm.BREATHE, speed=1.0, bus="B", mult=1.0, prio=3)
sync_strobe = dimmer_matrix("Sync Blitz >Bus C (x2)", RgbAlgorithm.STROBE, speed=1.0, bus="C", mult=1.0, prio=4)
sync_mh = efx("Sync MH-Kreis >Bus A", EfxAlgorithm.CIRCLE, mh_fids, phase_mode="fan", size=150, bus="A", mult=1.0)
SYNC_FX = [sync_chase, sync_breathe, sync_strobe, sync_mh]


# ── Misch-Ablaeufe (Farbe x Bewegung x Strobo) als Collections ──────────────────────
def collection(name, ids):
    c = fm.new_collection(name)
    c.function_ids = list(ids)
    return c


mix_party = collection("Mix: Party (Farbe+Bewegung)", [mtx_rainbow.id, efx_mh_fan.id, efx_spider_scissor.id])
mix_drop = collection("Mix: Drop (Strobo+Bewegung)", [dim_strobe.id, efx_mh_eight.id, sp_strobe.id])
mix_chill = collection("Mix: Chill (Verlauf+Atmen)", [mtx_gradient.id, dim_breathe.id, efx_mh_circle.id])
mix_theme = collection("Mix: Theme (Spider+Gobo)", [sp_gm.id, mh_g3.id, efx_spider_line.id])
MIXES = [mix_party, mix_drop, mix_chill, mix_theme]


# ── Live-Chase (per VCChaseBuilder/VCColorList bedienbar) ────────────────────────────
live_chase = fm.new_rgb_matrix("Live-Chase")
live_chase.algorithm = RgbAlgorithm.COLORFADE
live_chase.fixture_grid = list(rgb_fids)
live_chase.cols, live_chase.rows = len(rgb_fids), 1
live_chase.colors = ColorSequence([RGB(GREEN), RGB(WHITE), RGB(BLUE)])
live_chase.style = MatrixStyle.RGB
live_chase.drive_intensity = False
live_chase.matrix_speed = 1.0


# ════════════════════════════════════════════════════════════════════════════════
#  4) PLAYBACKS — Beat-Sync-Cuelisten
# ════════════════════════════════════════════════════════════════════════════════
def par_vals(rgbw, inten=255):
    r, g, b, w = rgbw
    out: dict[int, dict] = {}
    for fid in color_fids:
        v: dict = {}
        if attr_chs(fid, "intensity"):
            v["intensity"] = inten
        for a, val in (("color_r", r), ("color_g", g), ("color_b", b), ("color_w", w)):
            if attr_chs(fid, a):
                v[a] = val
        out[fid] = v
    return out


pb_warm = state.new_cue_stack("Aufwärmen")
pb_warm.mode = "loop"
for num, lbl, rgbw in [(1.0, "Grün", GREEN), (2.0, "Weiß", WHITE), (3.0, "Blau", BLUE)]:
    pb_warm.add_cue(Cue(number=num, label=lbl, fade_in=PHRASE, follow=PHRASE * 1.5,
                        values=par_vals(rgbw, inten=180)))

pb_drop = state.new_cue_stack("Drop-Sequenz")
pb_drop.mode = "loop"; pb_drop.beat_sync = True; pb_drop.beats_per_cue = 4
for num, lbl, rgbw in [(1.0, "Rot", RED), (2.0, "Weiß", WHITE), (3.0, "Blau", BLUE), (4.0, "Weiß", WHITE)]:
    pb_drop.add_cue(Cue(number=num, label=lbl, fade_in=0.05, follow=None, values=par_vals(rgbw)))

pb_color = state.new_cue_stack("Farb-Reise")
pb_color.mode = "loop"; pb_color.beat_sync = True; pb_color.beats_per_cue = 8
for num, lbl, rgbw in [(1.0, "Grün", GREEN), (2.0, "Cyan", CYAN), (3.0, "Blau", BLUE), (4.0, "Magenta", MAGENTA)]:
    pb_color.add_cue(Cue(number=num, label=lbl, fade_in=BEAT, follow=None, values=par_vals(rgbw)))

PLAYBACKS = [pb_warm, pb_drop, pb_color]
PB_PAGE = 6   # Bank 7 (0-basiert == Seite 6)
pe = state.playback_engine
for slot, pb in enumerate(PLAYBACKS, start=1):
    ex = pe.get_executor(slot, page=PB_PAGE)
    ex.stack = pb
    ex.label = pb.name
    ex.fader_function = "volume"


# ════════════════════════════════════════════════════════════════════════════════
#  5) AUTO-SHOW-KOPPLUNG
# ════════════════════════════════════════════════════════════════════════════════
state.music_autoshow = {
    "enabled": True,
    "function_ids": [auto_schema.id, efx_mh_circle.id],
    "bank": 0,
    "slots": {auto_schema.id: "par_show", efx_mh_circle.id: "mh_show"},
}


# ════════════════════════════════════════════════════════════════════════════════
#  6) VIRTUAL CONSOLE  (8 Baenke + universelle Leiste)
# ════════════════════════════════════════════════════════════════════════════════
PAD, GAP, X0, Y0 = 60, 6, 20, 70
STEP = PAD + GAP
GRID_BOTTOM = Y0 + 8 * STEP            # 598
TY = GRID_BOTTOM + 4                   # 602
Y_FAD = GRID_BOTTOM + 34              # 632
FAD_H = 142
RX = 620                              # rechte Spalte (frei von Pads + Master-Fader)
widgets: list[dict] = []
BANK_ALL = -1
(B_COLOR, B_DIM, B_FX, B_MH, B_SPIDER, B_BPM, B_MIX, B_PROG) = range(8)
PAGE_NAMES = ["Farb-Matrix", "Dimmer & Strobo", "Matrix-Effekte", "Moving Heads",
              "Spider", "BPM & Tempo", "Abläufe / Mischen", "Programmer"]


def note_rc(r, c):
    return (7 - r) * 8 + c


def pad_pos(note):
    row, col = note // 8, note % 8
    return X0 + col * STEP, Y0 + (7 - row) * STEP


def _add(w, x, y, ww, hh, bank):
    w.bank = bank
    w.setGeometry(x, y, ww, hh)
    widgets.append(w.to_dict())


def func_btn(fn, note, bank, accent, exclusive=False, clear_prog=False, style="pulse", edit_slot=""):
    b = VCButton(fn.name)
    b.action = ButtonAction.FUNCTION_TOGGLE
    b.function_id = fn.id
    b.pad_style = style
    b.exclusive = exclusive
    b.clear_programmer = clear_prog
    b.edit_slot = edit_slot
    b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, note
    b._bg_color.setNamedColor(accent)
    x, y = pad_pos(note)
    _add(b, x, y, PAD, PAD, bank)


def func_flash(fn, note, bank, accent):
    b = VCButton(fn.name)
    b.action = ButtonAction.FUNCTION_FLASH
    b.function_id = fn.id
    b.pad_style = "solid"
    b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, note
    b._bg_color.setNamedColor(accent)
    x, y = pad_pos(note)
    _add(b, x, y, PAD, PAD, bank)


def action_btn(name, action, note, bank, accent, tempo_bus_id=""):
    b = VCButton(name)
    b.action = action
    b.tempo_bus_id = tempo_bus_id
    b.pad_style = "solid"
    b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, note
    b._bg_color.setNamedColor(accent)
    x, y = pad_pos(note)
    _add(b, x, y, PAD, PAD, bank)


def effect_action_btn(name, note, bank, accent, key, function_id):
    b = VCButton(name)
    b.action = ButtonAction.EFFECT_ACTION
    b.effect_action_key = key
    b.function_id = function_id
    b.pad_style = "solid"
    b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, note
    b._bg_color.setNamedColor(accent)
    x, y = pad_pos(note)
    _add(b, x, y, PAD, PAD, bank)


def select_group_btn(name, group, note, bank, accent="#2a4a6a"):
    b = VCButton(name)
    b.action = ButtonAction.SELECT_GROUP
    b.group_name = group
    b.pad_style = "solid"
    b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, note
    b._bg_color.setNamedColor(accent)
    x, y = pad_pos(note)
    _add(b, x, y, PAD, PAD, bank)


def exec_go_btn(name, slot, note, bank, accent="#0d4f8b"):
    b = VCButton(name)
    b.action = ButtonAction.TOGGLE
    b.function_id = slot
    b.pad_style = "solid"
    b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, note
    b._bg_color.setNamedColor(accent)
    x, y = pad_pos(note)
    _add(b, x, y, PAD, PAD, bank)


def color_tile(name, note, bank, r, g, b, w=0, target=ColorTarget.ALL, function_id=None, with_intensity=True):
    c = VCColor(name)
    c.color_r, c.color_g, c.color_b, c.color_w = r, g, b, w
    c.with_intensity = with_intensity
    c.target = target
    c.function_id = function_id
    c.midi_type, c.midi_ch, c.midi_data1 = "note_on", 0, note
    x, y = pad_pos(note)
    _add(c, x, y, PAD, PAD, bank)


def fader(caption, col, bank, mode, function_ids=None, programmer_attr="intensity",
          programmer_scope="all", programmer_group="", param_key="speed", midi_cc=-1,
          value=0, submaster_slot=None, function_id=None, tempo_bus_id=""):
    s = VCSlider(caption)
    s.mode = mode
    s.function_id = function_id
    s.function_ids = list(function_ids or [])
    if submaster_slot is not None:
        s.function_id = submaster_slot
    s.programmer_attr = programmer_attr
    s.programmer_scope = programmer_scope
    s.programmer_group = programmer_group
    s.param_key = param_key
    s.tempo_bus_id = tempo_bus_id
    s.midi_cc, s.midi_ch = midi_cc, 0
    s._value = value
    x = X0 + col * STEP + 2
    _add(s, x, Y_FAD, 56, FAD_H, bank)


def pb_fader(caption, col, bank, slot, midi_cc, value=255):
    s = VCSlider(caption)
    s.mode = SliderMode.PLAYBACK
    s.function_id = slot
    s.midi_cc, s.midi_ch = midi_cc, 0
    s._value = value
    x = X0 + col * STEP + 2
    _add(s, x, Y_FAD, 56, FAD_H, bank)


def label(text, x, y, ww, bank, hh=18):
    _add(VCLabel(text), x, y, ww, hh, bank)


def song_info(x, y, bank, ww=300, hh=110, caption="Aktuelles Lied"):
    _add(VCSongInfo(caption), x, y, ww, hh, bank)


def bpm_display(x, y, bank, tempo_bus_id="", caption="TEMPO", ww=180, hh=96):
    w = VCBpmDisplay(caption)
    w.tempo_bus_id = tempo_bus_id
    _add(w, x, y, ww, hh, bank)


def bus_selector(x, y, bank, buses=("A", "B", "C", "D"), caption="Tempo-Bus", ww=240, hh=84):
    w = VCBusSelector(caption)
    w.buses = list(buses)
    _add(w, x, y, ww, hh, bank)


def speed_dial(caption, x, y, bank, target_mode=SpeedTarget.FUNCTION, function_id=None,
               tempo_bus_id="", role="master", parent_bus_id="", ww=160, hh=150):
    w = VCSpeedDial(caption)
    w.target_mode = target_mode
    w.function_id = function_id
    w.tempo_bus_id = tempo_bus_id
    w.role = role
    w.parent_bus_id = parent_bus_id
    _add(w, x, y, ww, hh, bank)


def eff_colors(caption, x, y, bank, function_id, ww=300, hh=84):
    w = VCEffectColors(caption)
    w.function_id = function_id
    _add(w, x, y, ww, hh, bank)


def color_list(caption, x, y, bank, function_id, ww=300, hh=84):
    w = VCColorList(caption)
    w.function_id = function_id
    _add(w, x, y, ww, hh, bank)


def chase_builder(caption, x, y, bank, function_id, ww=340, hh=250):
    w = VCChaseBuilder(caption)
    w.function_id = function_id
    _add(w, x, y, ww, hh, bank)


def xy_pad(caption, x, y, bank, fids, mode="position", efx_function_id=None, ww=200, hh=200):
    w = VCXYPad(caption)
    w.mode = mode
    w._fixture_ids = list(fids)
    w.bits16 = True
    if efx_function_id is not None:
        w.efx_function_id = efx_function_id
    _add(w, x, y, ww, hh, bank)


def cue_list(name, slot, x, y, bank, ww=240, hh=150):
    cl = VCCueList(name)
    cl.stack_slot = slot
    _add(cl, x, y, ww, hh, bank)


# ── Universell (BANK_ALL) ─────────────────────────────────────────────────────────
TRACK = [("Clear", ButtonAction.CLEAR, "#4a3a10"), ("Stop All", ButtonAction.STOP_ALL, "#4a1010"),
         ("Blackout", ButtonAction.BLACKOUT, "#2a0000"), ("Tap", ButtonAction.TAP, "#103a3a"),
         ("<< Lied", ButtonAction.MEDIA_PREV, "#3a2150"), (">/||", ButtonAction.MEDIA_PLAY_PAUSE, "#5a2080"),
         ("Lied >>", ButtonAction.MEDIA_NEXT, "#3a2150"), ("Musik-BPM", ButtonAction.AUDIO_BPM, "#103a4a")]
for i, (nm, act, col) in enumerate(TRACK):
    b = VCButton(nm)
    b.action = act
    b.pad_style = "solid"
    b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, 100 + i
    b._bg_color.setNamedColor(col)
    _add(b, X0 + i * 64, TY, 60, 26, BANK_ALL)
fader("Dimmer", 5, BANK_ALL, SliderMode.SUBMASTER, submaster_slot=0, midi_cc=53, value=255)
fader("Speed", 6, BANK_ALL, SliderMode.SPEED, midi_cc=54, value=64)
fader("Master", 8, BANK_ALL, SliderMode.GRANDMASTER, midi_cc=56, value=255)
label("EVENT-DEMO 2026  —  8 PAR + 2 MH + 2 Spider + APC mini.  SCENE-Tasten = Bank 1-8 "
      "(Farb-Matrix - Dimmer/Strobo - Matrix-Effekte - Moving Heads - Spider - BPM/Tempo - "
      "Abläufe/Mischen - Programmer).  > (Track 6) startet Musik + Auto-Show.",
      X0, 6, 1250, BANK_ALL)
label("Universell: Clear - Stop All - Blackout - Tap - << - >/|| - >> - Musik-BPM   |   "
      "Fader: F6 Dimmer - F7 Speed - F9 Master", X0, Y_FAD + FAD_H + 6, 1150, BANK_ALL)


# ── BANK 1 — FARB-MATRIX ────────────────────────────────────────────────────────────
song_info(RX, Y0, B_COLOR)
for i, m in enumerate(COLOR_MATRICES):                                     # R0 = 6 Farb-Matrizen
    func_btn(m, note_rc(0, i), B_COLOR, "#1f5a3a", exclusive=True, clear_prog=True)
for i, fn in enumerate(VIVID):                                             # R1 = Voll-Looks
    func_btn(fn, note_rc(1, i), B_COLOR, "#333333", style="solid")
COLORS16 = [
    ("Rot", 255, 0, 0, 0), ("Orange", 255, 90, 0, 0), ("Amber", 255, 160, 0, 0), ("Gelb", 255, 220, 0, 0),
    ("Limette", 160, 255, 0, 0), ("Grün", 0, 255, 0, 0), ("Türkis", 0, 230, 150, 0), ("Cyan", 0, 255, 255, 0),
    ("Hellblau", 0, 140, 255, 0), ("Blau", 0, 0, 255, 0), ("Violett", 140, 0, 255, 0), ("Magenta", 255, 0, 255, 0),
    ("Pink", 255, 0, 120, 0), ("Warmweiß", 255, 130, 40, 60), ("Weiß", 255, 255, 255, 255), ("Aus", 0, 0, 0, 0),
]
for i, (nm, r, g, b, w) in enumerate(COLORS16):                            # R2-3 = 16 Farb-Kacheln
    color_tile(nm, note_rc(2 + i // 8, i % 8), B_COLOR, r, g, b, w, target=ColorTarget.ALL)
for i, (nm, grp) in enumerate([("Alle PAR", "Alle PAR"), ("PAR L", "PAR Links"), ("PAR R", "PAR Rechts"),
                               ("Spider", "Spider"), ("Alles", "Alles")]):  # R4 = Gruppen
    select_group_btn(nm, grp, note_rc(4, i), B_COLOR)
eff_colors("Matrix-Farben (Verlauf)", RX, Y0 + 120, B_COLOR, mtx_gradient.id)
color_list("Farb-Sequenz", RX, Y0 + 214, B_COLOR, mtx_fade.id)
fader("Matrix-Master", 0, B_COLOR, SliderMode.EFFECT_INTENSITY, midi_cc=48, value=255)
fader("Matrix-Speed", 1, B_COLOR, SliderMode.EFFECT_SPEED, midi_cc=49, value=80)
fader("Weiß-Anteil", 2, B_COLOR, SliderMode.EFFECT_PARAM, param_key="white_amount", midi_cc=50, value=255)
fader("PAR-Dim", 3, B_COLOR, SliderMode.GROUP_DIMMER, programmer_group="Alle PAR", midi_cc=51, value=255)
label("BANK 1  FARB-MATRIX  —  R0: Regenbogen/Verlauf/Chase/Fade/Plasma/Windrad (exklusiv). "
      "R1: Voll-Looks. R2-3: 16 Farb-Kacheln. R4: Gruppen. Rechts: Farb-Editor. Fader links.",
      X0, 28, 1250, B_COLOR)


# ── BANK 2 — DIMMER & STROBO ────────────────────────────────────────────────────────
for i, m in enumerate(DIMMER_MATRICES):                                   # R0 = 5 Dimmer-Matrizen
    func_btn(m, note_rc(0, i), B_DIM, "#1f3a6a")
func_flash(dim_strobe, note_rc(0, 7), B_DIM, "#551111")                   # Strobe als Flash
dim_l = dim_scene("Dim Links", LEFT)
dim_r = dim_scene("Dim Rechts", RIGHT)
dim_odd = dim_scene("Dim ungerade", [par_fids[i] for i in range(0, 8, 2)])
dim_even = dim_scene("Dim gerade", [par_fids[i] for i in range(1, 8, 2)])
for i, fn in enumerate([dim_l, dim_r, dim_odd, dim_even]):                # R1 = Helligkeits-Splits
    func_btn(fn, note_rc(1, i), B_DIM, "#2a3a5a", style="solid")
func_flash(sp_strobe, note_rc(1, 7), B_DIM, "#551111")                    # Spider-Strobe Flash
fader("Dimmer-Master", 0, B_DIM, SliderMode.EFFECT_INTENSITY, midi_cc=48, value=255)
fader("Dimmer-Speed", 1, B_DIM, SliderMode.EFFECT_SPEED, midi_cc=49, value=80)
fader("PAR-Dim", 3, B_DIM, SliderMode.GROUP_DIMMER, programmer_group="Alle PAR", midi_cc=51, value=255)
label("BANK 2  DIMMER & STROBO  —  R0: Atmen/Welle/Aufbau/Blitz/Funkeln (Dimmer-Matrix, legt sich "
      "UEBER die Farbe; F8=Strobe-Flash). R1: Helligkeits-Splits + Spider-Strobe. Fader links.",
      X0, 28, 1250, B_DIM)


# ── BANK 3 — MATRIX-EFFEKTE ─────────────────────────────────────────────────────────
FX_ACCENT = ["#6a2f1f", "#1f4a6a", "#1f6a3a", "#5a1f6a", "#6a6a1f", "#1f5a6a"]
for i, m in enumerate(FX_MATRICES):                                       # R0 = 6 Matrix-Effekte
    func_btn(m, note_rc(0, i), B_FX, FX_ACCENT[i], exclusive=True, clear_prog=True)
for i, (nm, grp) in enumerate([("Alle PAR", "Alle PAR"), ("Spider", "Spider"), ("Alles", "Alles")]):
    select_group_btn(nm, grp, note_rc(1, i), B_FX)
fader("FX-Master", 0, B_FX, SliderMode.EFFECT_INTENSITY, midi_cc=48, value=255)
fader("FX-Speed", 1, B_FX, SliderMode.EFFECT_SPEED, midi_cc=49, value=80)
fader("PAR-Dim", 3, B_FX, SliderMode.GROUP_DIMMER, programmer_group="Alle PAR", midi_cc=51, value=255)
label("BANK 3  MATRIX-EFFEKTE  —  R0: Feuer/Regen/Radar/Spirale/Wisch/Welle (exklusiv). "
      "R1: Gruppen. Fader: FX-Master/Speed + PAR-Dim.", X0, 28, 1250, B_FX)


# ── BANK 4 — MOVING HEADS (Farbe + Gobo + Bewegung) ─────────────────────────────────
for i, fn in enumerate(MH_COLORS):                                        # R0 = MH-Farben
    func_btn(fn, note_rc(0, i), B_MH, "#3a5a1f", exclusive=True, clear_prog=True)
for i, fn in enumerate(MH_GOBOS):                                         # R1 = MH-Gobos
    func_btn(fn, note_rc(1, i), B_MH, "#5a3a1f", style="solid")
func_flash(mh_strobe, note_rc(1, 7), B_MH, "#551111")
for i, fn in enumerate(EFX_MH):                                           # R2 = MH-Bewegungen
    func_btn(fn, note_rc(2, i), B_MH, "#1f3a6a", edit_slot="mh_show")
effect_action_btn("Gegenläufig", note_rc(3, 0), B_MH, "#7a6500", "toggle_counter", efx_mh_circle.id)
effect_action_btn("Spiegeln", note_rc(3, 1), B_MH, "#334455", "toggle_mirror", efx_mh_circle.id)
effect_action_btn("Richtung", note_rc(3, 2), B_MH, "#445566", "reverse_direction", efx_mh_circle.id)
effect_action_btn("Neustart", note_rc(3, 3), B_MH, "#553010", "restart", efx_mh_circle.id)
select_group_btn("MH wählen", "Moving Heads", note_rc(4, 0), B_MH)
xy_pad("MH zielen (Pan/Tilt)", RX, Y0, B_MH, mh_fids, mode="position")
fader("MH-Speed", 0, B_MH, SliderMode.EFFECT_SPEED, function_ids=[e.id for e in EFX_MH], midi_cc=48, value=80)
fader("MH-Größe", 1, B_MH, SliderMode.EFFECT_PARAM, function_ids=[e.id for e in EFX_MH], param_key="size", midi_cc=49, value=150)
fader("MH-Dim", 3, B_MH, SliderMode.GROUP_DIMMER, programmer_group="Moving Heads", midi_cc=51, value=255)
label("BANK 4  MOVING HEADS  —  R0: Farbrad (exklusiv). R1: Gobos + Strobe. R2: Bewegung (Kreis/"
      "Fächer/Acht/Lissajous/Rechteck/Pfad). R3: Gegenläufig/Spiegeln/Richtung/Neustart. "
      "Rechts: XY-Pad zum Zielen. Fader: Speed/Größe/Dim.", X0, 28, 1250, B_MH)


# ── BANK 5 — SPIDER (Themes + Bewegung) ─────────────────────────────────────────────
for i, fn in enumerate(SP_THEMES):                                        # R0 = Spider-Themes
    func_btn(fn, note_rc(0, i), B_SPIDER, "#1f5a5a", exclusive=True, clear_prog=True)
for i, fn in enumerate(EFX_SPIDER):                                       # R1 = Spider-Bewegung
    func_btn(fn, note_rc(1, i), B_SPIDER, "#1f3a6a")
func_btn(efx_all, note_rc(1, 2), B_SPIDER, "#3a1f6a")
func_flash(sp_strobe, note_rc(1, 7), B_SPIDER, "#551111")
effect_action_btn("Richtung", note_rc(2, 0), B_SPIDER, "#445566", "reverse_direction", efx_spider_scissor.id)
effect_action_btn("Neustart", note_rc(2, 1), B_SPIDER, "#553010", "restart", efx_spider_scissor.id)
select_group_btn("Spider wählen", "Spider", note_rc(3, 0), B_SPIDER)
fader("Spider-Speed", 0, B_SPIDER, SliderMode.EFFECT_SPEED, function_ids=[e.id for e in EFX_SPIDER], midi_cc=48, value=90)
fader("Spider-Größe", 1, B_SPIDER, SliderMode.EFFECT_PARAM, function_ids=[e.id for e in EFX_SPIDER], param_key="size", midi_cc=49, value=200)
fader("Spider-Dim", 3, B_SPIDER, SliderMode.GROUP_DIMMER, programmer_group="Spider", midi_cc=51, value=255)
label("BANK 5  SPIDER  —  R0: Farb-Themes pro Bar (exklusiv). R1: Bewegung (Schere/Wippe/Alle). "
      "R2: Richtung/Neustart. Fader: Speed/Größe/Dim.", X0, 28, 1250, B_SPIDER)


# ── BANK 6 — BPM & TEMPO (Master/Sub-Geschwindigkeiten + BPM-Erkennung) ─────────────
# R0: BPM-Bedienung
action_btn("Tap Tempo", ButtonAction.TAP, note_rc(0, 0), B_BPM, "#103a3a")
action_btn("Musik-BPM", ButtonAction.AUDIO_BPM, note_rc(0, 1), B_BPM, "#103a4a")
action_btn("BPM +", ButtonAction.BPM_NUDGE_UP, note_rc(0, 2), B_BPM, "#1f5a3a")
action_btn("BPM -", ButtonAction.BPM_NUDGE_DOWN, note_rc(0, 3), B_BPM, "#5a1f1f")
action_btn("BPM-Modus", ButtonAction.BPM_MODE_TOGGLE, note_rc(0, 4), B_BPM, "#3a3a1f")
# R1: Tempo-Bus-Bedienung (Tap/Sync/Arm pro Bus)
action_btn("Tap Bus A", ButtonAction.TAP_BUS, note_rc(1, 0), B_BPM, "#1f3a6a", tempo_bus_id="A")
action_btn("Sync Bus A", ButtonAction.SYNC_BUS, note_rc(1, 1), B_BPM, "#1f4a6a", tempo_bus_id="A")
action_btn("Arm Bus", ButtonAction.ARM_BUS, note_rc(1, 2), B_BPM, "#5a3a1f", tempo_bus_id="A")
# R2: Tempo-synchrone Effekte starten (zeigen Master/Sub-Wirkung)
func_btn(sync_chase, note_rc(2, 0), B_BPM, "#1f5a3a")
func_btn(sync_breathe, note_rc(2, 1), B_BPM, "#1f3a6a")
func_btn(sync_strobe, note_rc(2, 2), B_BPM, "#5a1f1f")
func_btn(sync_mh, note_rc(2, 3), B_BPM, "#3a1f6a")
# Rechts: Anzeige + Buswahl + Speed-Knoten (Master/Sub)
bpm_display(RX, Y0, B_BPM, tempo_bus_id="", caption="GLOBAL BPM")
bpm_display(RX + 196, Y0, B_BPM, tempo_bus_id="A", caption="BUS A (Master)")
bus_selector(RX, Y0 + 106, B_BPM)
speed_dial("Master A", RX, Y0 + 200, B_BPM, target_mode=SpeedTarget.SPEED_NODE, tempo_bus_id="A", role="master")
speed_dial("Sub B (1/2)", RX + 176, Y0 + 200, B_BPM, target_mode=SpeedTarget.SPEED_NODE,
           tempo_bus_id="B", role="sub", parent_bus_id="A")
speed_dial("Sub C (x2)", RX + 352, Y0 + 200, B_BPM, target_mode=SpeedTarget.SPEED_NODE,
           tempo_bus_id="C", role="sub", parent_bus_id="A")
fader("Tempo Bus A", 0, B_BPM, SliderMode.TEMPO_BUS, tempo_bus_id="A", midi_cc=48, value=100)
fader("Tempo Bus D", 1, B_BPM, SliderMode.TEMPO_BUS, tempo_bus_id="D", midi_cc=49, value=85)
fader("BPM global", 3, B_BPM, SliderMode.BPM, midi_cc=51, value=100)
label("BANK 6  BPM & TEMPO  —  R0: Tap/Musik-BPM/+/-/Modus (BPM-Erkennung). R1: Tap/Sync/Arm Bus. "
      "R2: tempo-synchrone Effekte (Bus A=voll, B=halb, C=doppelt). Rechts: BPM-Anzeige + Bus-Wahl + "
      "Master/Sub-Speed-Knoten. Fader: Tempo-Buses + BPM.", X0, 28, 1250, B_BPM)


# ── BANK 7 — ABLAEUFE / MISCHEN (Farbe x Bewegung x Strobo) ─────────────────────────
MIX_ACCENT = ["#6a1f4a", "#5a1f1f", "#1f5a3a", "#1f3a6a"]
for i, fn in enumerate(MIXES):                                            # R0 = Misch-Collections
    func_btn(fn, note_rc(0, i), B_MIX, MIX_ACCENT[i], exclusive=True, clear_prog=True)
for i, fn in enumerate(CHASERS):                                          # R1 = Chaser
    func_btn(fn, note_rc(1, i), B_MIX, "#3a3a5a")
for i, pb in enumerate(PLAYBACKS):                                        # R2 = GO Cuelisten
    exec_go_btn(f"GO {pb.name}", i, note_rc(2, i), B_MIX, ["#1f4a28", "#8b0d4f", "#0d4f8b"][i])
func_btn(live_chase, note_rc(3, 0), B_MIX, "#1f5a3a")                     # Live-Chase Start/Stop
effect_action_btn("Leeren", note_rc(3, 1), B_MIX, "#5a1010", "clear_colors", live_chase.id)
effect_action_btn("Farbe -", note_rc(3, 2), B_MIX, "#333355", "prev_color", live_chase.id)
effect_action_btn("Farbe +", note_rc(3, 3), B_MIX, "#333355", "next_color", live_chase.id)
LC_COLORS = [("Rot", 255, 0, 0), ("Orange", 255, 90, 0), ("Gelb", 255, 220, 0), ("Grün", 0, 255, 0),
             ("Cyan", 0, 255, 255), ("Blau", 0, 0, 255), ("Magenta", 255, 0, 255), ("Weiß", 255, 255, 255)]
for i, (nm, r, g, b) in enumerate(LC_COLORS):                             # R4 = Farben zur Live-Chase
    color_tile(nm, note_rc(4, i), B_MIX, r, g, b, target=ColorTarget.EFFECT_ADD, function_id=live_chase.id)
for i, pb in enumerate(PLAYBACKS):
    cue_list(pb.name, i, RX + i * 250 if i < 2 else RX, Y0 if i < 2 else Y0 + 158, B_MIX, ww=240, hh=150)
chase_builder("Chase-Builder (live)", RX + 500, Y0, B_MIX, live_chase.id)
for i, pb in enumerate(PLAYBACKS):
    pb_fader(f"Dim {i+1}", i, B_MIX, slot=i, midi_cc=48 + i, value=255)
label("BANK 7  ABLÄUFE / MISCHEN  —  R0: Misch-Collections (Party/Drop/Chill/Theme). R1: Chaser. "
      "R2: GO Cuelisten (Beat-Sync). R3: Live-Chase + Leeren/-/+. R4: Farben hinzufügen. "
      "Rechts: Cuelisten-Anzeige + Chase-Builder.", X0, 28, 1250, B_MIX)


# ── BANK 8 — PROGRAMMER ─────────────────────────────────────────────────────────────
for i, (nm, grp) in enumerate([("Alle PAR", "Alle PAR"), ("PAR L", "PAR Links"), ("PAR R", "PAR Rechts"),
                               ("Spider", "Spider"), ("Moving Heads", "Moving Heads"), ("Alles", "Alles")]):
    select_group_btn(nm, grp, note_rc(0, i), B_PROG)
fixt_full = look("Voll Weiß", WHITE)
func_btn(fixt_full, note_rc(1, 0), B_PROG, "#555555", style="solid")
fixt_strobe = fm.new_scene("Fixture-Strobe")
for fid in color_fids:
    for ch in attr_chs(fid, "shutter"):
        fixt_strobe.set_value(fid, ch, 200)
    for ch in attr_chs(fid, "intensity"):
        fixt_strobe.set_value(fid, ch, 255)
func_flash(fixt_strobe, note_rc(1, 1), B_PROG, "#551111")
COLORS_PROG = [("Rot", 255, 0, 0, 0), ("Grün", 0, 255, 0, 0), ("Blau", 0, 0, 255, 0), ("Gelb", 255, 220, 0, 0),
               ("Cyan", 0, 255, 255, 0), ("Magenta", 255, 0, 255, 0), ("Weiß", 255, 255, 255, 255), ("Aus", 0, 0, 0, 0)]
for i, (nm, r, g, b, w) in enumerate(COLORS_PROG):                        # R2 = Farb-Kacheln auf Selektion
    color_tile(nm, note_rc(2, i), B_PROG, r, g, b, w, target=ColorTarget.PROGRAMMER)
fader("Rot", 0, B_PROG, SliderMode.PROGRAMMER, programmer_attr="color_r", midi_cc=48, value=0)
fader("Grün", 1, B_PROG, SliderMode.PROGRAMMER, programmer_attr="color_g", midi_cc=49, value=0)
fader("Blau", 2, B_PROG, SliderMode.PROGRAMMER, programmer_attr="color_b", midi_cc=50, value=0)
fader("Weiß", 3, B_PROG, SliderMode.PROGRAMMER, programmer_attr="color_w", midi_cc=51, value=0)
fader("Intensität", 4, B_PROG, SliderMode.PROGRAMMER, programmer_attr="intensity", midi_cc=52, value=255)
fader("MH Pan", 7, B_PROG, SliderMode.PROGRAMMER, programmer_attr="pan", programmer_scope="group",
      programmer_group="Moving Heads", midi_cc=55, value=128)
label("BANK 8  PROGRAMMER  —  R0: Gruppe wählen. R1: Voll Weiß / Fixture-Strobe. R2: Farb-Kacheln "
      "auf Selektion. Fader: R/G/B/W/Intensität + MH-Pan (Pan/Tilt sonst via XY-Pad in Bank 4).",
      X0, 28, 1250, B_PROG)


state._vc_layout = {"widgets": widgets}

# ── Executor-Seiten benennen ────────────────────────────────────────────────────
try:
    for idx, nm in enumerate(PAGE_NAMES):
        if 0 <= idx < len(pe.page_names):
            pe.page_names[idx] = nm
    pe.set_page(0)
except Exception as e:
    print(f"[build] page name error: {e}")


# ════════════════════════════════════════════════════════════════════════════════
#  7) SPEICHERN + VERIFIKATION
# ════════════════════════════════════════════════════════════════════════════════
state.programmer = {}
state.show_name = "Event Demo 2026"
save_show(OUT)
print(f"Gespeichert: {OUT}")
ok, msg = load_show(OUT)
print("Load:", ok, msg)
assert ok, f"Show laedt nicht: {msg}"
state = get_state()
fm = get_function_manager()

from collections import Counter
fx = state.get_patched_fixtures()
assert len(fx) == 12, f"Fixtures: {len(fx)}"
print("Fixtures:", dict(Counter(f.fixture_type for f in fx)))

# Positionen: MH hinten (kleines y), Spider vorne (grosses y)
lvp = {int(k): v for k, v in state.live_view_positions.items()}
assert lvp[9][1] < lvp[1][1], "MH nicht hinten"
assert lvp[11][1] > lvp[1][1], "Spider nicht vorne"

vc = state._vc_layout.get("widgets", [])
banks = Counter(w.get("bank") for w in vc)
assert set(banks) == {0, 1, 2, 3, 4, 5, 6, 7, -1}, f"Banks: {sorted(banks)}"
types = Counter(w["type"] for w in vc)

# Matrizen
from src.core.engine.rgb_matrix import RgbMatrixInstance, MatrixStyle as MS
mats = [f for f in fm.all() if isinstance(f, RgbMatrixInstance)]
color_m = [m for m in mats if m.style == MS.RGB and not m.drive_intensity]
dim_m = [m for m in mats if m.style == MS.DIMMER]
assert len(color_m) >= 6 + 6, f"Farb/FX-Matrizen: {len(color_m)}"
assert len(dim_m) >= 5, f"Dimmer-Matrizen: {len(dim_m)}"

# EFX auf MH + Spider
from src.core.engine.efx import EfxInstance
efxs = [f for f in fm.all() if isinstance(f, EfxInstance)]
assert len(efxs) >= 8, f"EFX: {len(efxs)}"
assert any({x.fid for x in e.fixtures} & set(spider_fids) for e in efxs), "keine Spider-EFX"
assert any({x.fid for x in e.fixtures} & set(mh_fids) for e in efxs), "keine MH-EFX"
custom = [e for e in efxs if e.algorithm == EfxAlgorithm.CUSTOM]
assert custom and custom[0].path_data, "Custom-Path-EFX fehlt/leer"

# Tempo-Buses (Master/Sub) persistiert?
tbm2 = get_tempo_bus_manager()
named = {b.bus_id: b for b in tbm2.named_buses()}
assert set(["A", "B", "C", "D"]).issubset(named), f"Buses: {list(named)}"
assert named["A"].role == "master" and named["B"].role == "sub", "A/B Rollen falsch"
assert named["B"].parent_id == "A" and abs(named["B"].bus_multiplier - 0.5) < 1e-6, "Sub B falsch"
assert abs(named["C"].bus_multiplier - 2.0) < 1e-6, "Sub C falsch"
assert tbm2.grandmaster_bpm > 0, "Grand-Master-BPM fehlt"
# Effekte an Bus gebunden?
bus_bound = [f for f in fm.all() if getattr(f, "tempo_bus_id", "") in ("A", "B", "C", "D")]
assert len(bus_bound) >= 4, f"bus-gebundene Effekte: {len(bus_bound)}"

# MH-Farb/Gobo-Szenen schreiben color_wheel/gobo_wheel?
from src.core.engine.scene import Scene
mh_cw_ch = chan_of[9]["color_wheel"]
mh_gw_ch = chan_of[9]["gobo_wheel"]
sc_red = next(f for f in fm.all() if isinstance(f, Scene) and f.name == "MH Rot")
assert sc_red.get_value(9, mh_cw_ch) == MHCOL["rot"], "MH Rot Farbrad falsch"
sc_g1 = next(f for f in fm.all() if isinstance(f, Scene) and f.name == "MH Gobo 1")
assert sc_g1.get_value(9, mh_gw_ch) == MHGOBO["g1"], "MH Gobo 1 falsch"

# Spider-Theme: linke Bar != rechte Bar
sp_cols = [c for c in chans_full[11]
           if (c.attribute or "") in ("color_r", "color_g", "color_b", "color_w")]
sc_rb = next(f for f in fm.all() if isinstance(f, Scene) and f.name == "Spider Rot/Blau")
assert sc_rb.get_value(11, sp_cols[0].channel_number) == 255, "Spider linke Bar nicht rot"
assert sc_rb.get_value(11, sp_cols[4 + 2].channel_number) == 255, "Spider rechte Bar nicht blau"

# Collections (Misch-Ablaeufe)
from src.core.engine.collection import Collection
cols = [f for f in fm.all() if isinstance(f, Collection)]
assert len(cols) >= 4, f"Collections: {len(cols)}"

# Beat-Sync-Cuelisten
beat_stacks = [s for s in state.cue_stacks if getattr(s, "beat_sync", False)]
assert len(beat_stacks) == 2, [s.name for s in beat_stacks]

# Auto-Show gekoppelt
ma = state.music_autoshow
assert ma.get("enabled") is True, ma
fn_ids = {f.id for f in fm.all()}
assert ma.get("function_ids") and all(fid in fn_ids for fid in ma["function_ids"]), ma

# Playlist
assert len(state.playlist) == len(CURATED), f"Playlist: {len(state.playlist)}"

# VC-Plausibilitaet
new_widgets = {"VCSpeedDial", "VCBpmDisplay", "VCBusSelector", "VCEffectColors",
               "VCColorList", "VCChaseBuilder", "VCXYPad", "VCCueList", "VCSongInfo"}
for t in new_widgets:
    assert types.get(t, 0) >= 1, f"Widget fehlt: {t} ({dict(types)})"
maxy = max((w.get("y", 0) + w.get("h", 0)) for w in vc)
assert maxy < 820, f"zu hoch: {maxy}"

# Keine Ueberlappung interaktiver Widgets je Bank
_INTER = {"VCButton", "VCSlider", "VCColor", "VCXYPad", "VCCueList", "VCColorList",
          "VCChaseBuilder", "VCSpeedDial", "VCSongInfo", "VCBpmDisplay", "VCBusSelector",
          "VCEffectColors"}


def _rect(w):
    return (w.get("x", 0), w.get("y", 0), w.get("x", 0) + w.get("w", 0), w.get("y", 0) + w.get("h", 0))


def _overlap(a, b):
    ax0, ay0, ax1, ay1 = _rect(a)
    bx0, by0, bx1, by1 = _rect(b)
    return not (ax1 <= bx0 or bx1 <= ax0 or ay1 <= by0 or by1 <= ay0)


for bk in range(8):
    layer = [w for w in vc if w.get("bank") in (bk, -1) and w["type"] in _INTER]
    for a in range(len(layer)):
        for b in range(a + 1, len(layer)):
            assert not _overlap(layer[a], layer[b]), (
                f"Overlap Bank {bk}: {layer[a]['type']}@{_rect(layer[a])} "
                f"vs {layer[b]['type']}@{_rect(layer[b])}")

print(f"Funktionen: {len(fm.all())}  VC-Widgets: {len(vc)}")
print(f"  Banks: {dict(sorted(banks.items()))}  Max-Y={maxy}")
print(f"  Farb/FX-Matrizen={len(color_m)}  Dimmer-Matrizen={len(dim_m)}  EFX={len(efxs)}")
print(f"  Buses: {[f'{b.bus_id}:{b.role}x{b.bus_multiplier}' for b in tbm2.named_buses()]}  GM-BPM={tbm2.grandmaster_bpm}")
print(f"  Collections={len(cols)}  Beat-Cuelisten={[s.name for s in beat_stacks]}  Playlist={len(state.playlist)}")
print(f"  Widget-Typen={dict(types)}")
print("  [OK] 8 Baenke - Farb/Dimmer/FX-Matrix - MH Farbe+Gobo+Bewegung - Spider Themes+Bewegung - "
      "Tempo-Buses Master/Sub - BPM - Misch-Ablaeufe")
print("FERTIG")
