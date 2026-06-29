"""HOCHZEIT KOMPLETT 2026 — erschoepfende Feature-Demo auf Davids Hochzeits-Rig.

Baut EINE Show, die NACHWEISLICH alles vorfuehrt (Assert-Gate erzwingt es):
  * alle 18 RGB-Matrix-Algorithmen (Plain..Regen) als reine Farbe (RGB-Style)
  * alle 4 Matrix-Styles  RGB / RGBW (echtes Weiss via rgbw_split) / Dimmer / Shutter
  * reine Dimmer-Effekte (Dimmer-Matrix, legt sich disjunkt UEBER die Farbe)
  * alle 10 EFX-Bewegungsfiguren (Kreis..Custom-Pfad) auf MH + Spider
  * Chaser, Beat-Sync-Cuelisten (+ Follow), Collections (Misch-Ablaeufe)
  * Tempo-Buses Master/Sub A/B/C/D + Grandmaster, effekt-gekoppelt
  * Musik-Playlist + Auto-Show (MusicShowDirector startet bei Play)
  * ALLE 19 VC-Widget-Typen aus dem WIDGET_REGISTRY, auf 8 APC-Baenke verteilt

Rig = exakt Davids Hochzeitsshow (shows/hochzeit.lshow), Universe 1, 137 Kanaele:
  fid 1  ADJ Dotz TPar System  18ch  led_bar  (4 RGB-Zellen + Master-Dim/Shutter) @ 1
  fid 2-5  ADJ Flat Par QWH12X  8ch  par  (RGBW)                                   @ 19/27/35/43
  fid 6-11 Generic ZQ01424      8ch  par  (RGBW)                                   @ 51/59/67/75/83/91
  fid 12   U-King ZQ02001       11ch moving_head (Pan/Tilt + Farbrad + Gobo)       @ 99
  fid 13-14 U-King Spider       14ch moving_head (Dual-Tilt, RGBW-Doppelbank)      @ 113/127

Aufruf:  venv/Scripts/python.exe tools/build_hochzeit_komplett.py
Erzeugt: shows/Hochzeit_Komplett_2026.lshow
"""
from __future__ import annotations
import os
import sys
import glob
import json
# Windows-Spawn-Schutz: Startet der OutputManager seine Serial-Isolation per
# multiprocessing-Spawn, re-importiert der Kindprozess dieses Skript als
# "__mp_main__" (NICHT "__main__") und wuerde die ganze Show ein zweites Mal
# bauen -> zwei Prozesse rennen auf current_show.db, der FLD-FID-Guard in
# add_fixture vergibt verwaiste fids neu und der Patch wird korrupt. Im
# re-importierten Kind sofort aussteigen; nur der echte __main__ baut.
if __name__ != "__main__":
    sys.exit(0)

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
from src.ui.virtualconsole.vc_encoder import VCEncoder
from src.ui.virtualconsole.vc_stepper import VCStepper
from src.ui.virtualconsole.vc_tempo_bus_controller import VCTempoBusController
from src.ui.virtualconsole.vc_frame import VCFrame
from src.ui.virtualconsole.vc_effect_editor import VCEffectEditor
from src.ui.virtualconsole.vc_effect_display import VCEffectDisplay

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(_ROOT, "shows", "Hochzeit_Komplett_2026.lshow")
MUSIC_DIR = r"C:/Users/David/Desktop/Musik/BP Party"

BPM = 128.0
BEAT = 60.0 / BPM
BAR = 4 * BEAT
PHRASE = 8 * BEAT


def profile_id(short: str) -> int:
    with Session(fdb_engine()) as s:
        pid = s.execute(select(FixtureProfile.id).where(
            FixtureProfile.short_name == short)).scalar_one_or_none()
    if pid is None:
        raise SystemExit(f"Profil '{short}' fehlt — bitte App einmal starten (ensure_builtins).")
    return int(pid)


# ════════════════════════════════════════════════════════════════════════════════
#  0) BASIS + PATCH  (exakt das Hochzeits-Rig)
# ════════════════════════════════════════════════════════════════════════════════
reset_show()
state = get_state()
state.clear_patch()   # verwaiste current_show.db-Zeilen hart entfernen (FLD-FID-Schutz)
fm = get_function_manager()
DOTZ_PID = profile_id("DOTZTPAR")
FLAT_PID = profile_id("FPQWH12X")
ZQ_PID = profile_id("ZQ01424")
MH_PID = profile_id("ZQ02001")
SP_PID = profile_id("Speider")

state.add_fixture(PatchedFixture(
    fid=1, label="Tor (Dotz-Bar)", fixture_profile_id=DOTZ_PID,
    mode_name="18-Kanal 4x RGB Voll", universe=1, address=1, channel_count=18,
    manufacturer_name="ADJ", fixture_name="Dotz TPar System",
    fixture_type="led_bar"), undoable=False)
dotz_fid = 1

flat_fids: list[int] = []
for i, a in enumerate((19, 27, 35, 43)):
    fid = 2 + i
    state.add_fixture(PatchedFixture(
        fid=fid, label=f"Flat Par {i + 1}", fixture_profile_id=FLAT_PID,
        mode_name="8-Kanal Voll", universe=1, address=a, channel_count=8,
        manufacturer_name="ADJ", fixture_name="Flat Par QWH12X",
        fixture_type="par"), undoable=False)
    flat_fids.append(fid)

par_fids: list[int] = []
for i, a in enumerate((51, 59, 67, 75, 83, 91)):
    fid = 6 + i
    state.add_fixture(PatchedFixture(
        fid=fid, label=f"PAR {i + 1}", fixture_profile_id=ZQ_PID,
        mode_name="8-Kanal RGBW", universe=1, address=a, channel_count=8,
        manufacturer_name="Generic", fixture_name="Stage Light ZQ01424",
        fixture_type="par"), undoable=False)
    par_fids.append(fid)

state.add_fixture(PatchedFixture(
    fid=12, label="Moving Head", fixture_profile_id=MH_PID, mode_name="11-Kanal",
    universe=1, address=99, channel_count=11, manufacturer_name="U King",
    fixture_name="ZQ02001 Mini Moving Head", fixture_type="moving_head"), undoable=False)
mh_fids = [12]

spider_fids: list[int] = []
for i, a in enumerate((113, 127)):
    fid = 13 + i
    state.add_fixture(PatchedFixture(
        fid=fid, label=f"Spider {i + 1}", fixture_profile_id=SP_PID, mode_name="14ch",
        universe=1, address=a, channel_count=14, manufacturer_name="U-King",
        fixture_name="Speider", fixture_type="moving_head",
        spider_mirrored=True), undoable=False)
    spider_fids.append(fid)

# ── Sammel-Listen (was kann was) ────────────────────────────────────────────────
front_fids = [dotz_fid] + flat_fids + par_fids       # 11 Frontlichter (RGB-Farbe)
color_fids = front_fids + spider_fids                # 13 mit RGB-Farbe (ohne MH-Farbrad)
rgbw_fids = flat_fids + par_fids + spider_fids        # 12 mit echtem Weiss-Chip (NICHT Dotz)
mover_fids = mh_fids + spider_fids                    # 3 mit Pan/Tilt-Bewegung (EFX)
all_fids = front_fids + mh_fids + spider_fids         # 14

# Matrix-Raster
GRID_FRONT = list(front_fids)        # 1x11 — Hauptflaeche fuer die 18 Algorithmen
GRID_PAR = list(par_fids)            # 1x6  — saubere RGBW-Reihe
GRID_RGBW = list(rgbw_fids)          # 1x12 — RGBW-Style (echtes Weiss)
GRID_SPIDER = list(spider_fids)      # 1x2  — kleine 2D-Flaeche

fixtures = state.get_patched_fixtures()
fx_of = {f.fid: f for f in fixtures}
chans_full = {f.fid: get_channels_for_patched(f) for f in fixtures}
chan_of = {f.fid: {c.attribute: c.channel_number for c in chans_full[f.fid]} for f in fixtures}


def attr_chs(fid: int, attr: str) -> list[int]:
    """ALLE Kanalnummern eines Attributs (Dotz: color_r/g/b 4x = 4 Zellen;
    Spider: color_r/g/b/w 2x = 2 Baenke). So bekommt jede Zelle/Bank ihre Farbe."""
    return [c.channel_number for c in chans_full[fid] if (c.attribute or "").lower() == attr]


# Grundhelligkeit: alle Farbfixtures leuchten (Farb-Matrix ohne Dimmer sichtbar).
state.base_levels = {fid: {"intensity": 255} for fid in color_fids}
state._rebuild_render_plan()

# ── 2D-Live-View + 3D-Positionen ─────────────────────────────────────────────────
PXF = {front_fids[i]: 170.0 + i * 80.0 for i in range(len(front_fids))}     # Frontreihe
lv = {fid: (PXF[fid], 430.0) for fid in front_fids}
lv[12] = (520.0, 250.0)                       # MH hinten/mittig
lv[13] = (PXF[front_fids[0]], 600.0)          # Spider links vorne
lv[14] = (PXF[front_fids[-1]], 600.0)         # Spider rechts vorne
state.live_view_positions = {fid: list(p) for fid, p in lv.items()}
state.live_view_meta = {"zoom": 1.0, "grid_size": 20, "snap": True,
                        "grid_visible": True, "world_w": 1200, "world_h": 800}
vz = {fid: ((PXF[fid] - 600.0) / 80.0, 0.0, 0.0) for fid in front_fids}
vz[12] = (-1.0, 6.0, -1.8)
vz[13] = (vz[front_fids[0]][0], 0.6, 1.8)
vz[14] = (vz[front_fids[-1]][0], 0.6, 1.8)
state.visualizer_positions = {fid: tuple(p) for fid, p in vz.items()}
state.active_stage_name = "simple"

# ── Fixture-Gruppen ──────────────────────────────────────────────────────────────
with state._session() as s:
    s.execute(delete(FixtureGroup))
    s.add(FixtureGroup(name="Alle Front", cols=len(front_fids), rows=1,
                       positions_json=json.dumps({f"{i},0": front_fids[i] for i in range(len(front_fids))})))
    s.add(FixtureGroup(name="PAR-Reihe", cols=6, rows=1,
                       positions_json=json.dumps({f"{i},0": par_fids[i] for i in range(6)})))
    s.add(FixtureGroup(name="Flat-Pars", cols=4, rows=1,
                       positions_json=json.dumps({f"{i},0": flat_fids[i] for i in range(4)})))
    s.add(FixtureGroup(name="Dotz-Bar", cols=1, rows=1,
                       positions_json=json.dumps({"0,0": dotz_fid})))
    s.add(FixtureGroup(name="Moving Head", cols=1, rows=1,
                       positions_json=json.dumps({"0,0": 12})))
    s.add(FixtureGroup(name="Spider", cols=2, rows=1,
                       positions_json=json.dumps({"0,0": 13, "1,0": 14})))
    s.add(FixtureGroup(name="Alle Mover", cols=len(mover_fids), rows=1,
                       positions_json=json.dumps({f"{i},0": mover_fids[i] for i in range(len(mover_fids))})))
    s.add(FixtureGroup(name="Alles", cols=len(all_fids), rows=1,
                       positions_json=json.dumps({f"{i},0": all_fids[i] for i in range(len(all_fids))})))
    s.commit()


# ════════════════════════════════════════════════════════════════════════════════
#  1) MUSIK-PLAYLIST
# ════════════════════════════════════════════════════════════════════════════════
CURATED = [
    ("perfect", "Hochzeit", 95), ("thinking out loud", "Hochzeit", 79),
    ("dancing queen", None, None), ("mr. brightside", "Party", 148),
    ("i need a hero", None, None), ("major tom", None, None),
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
#  2) TEMPO-BUSES + GRAND-MASTER
# ════════════════════════════════════════════════════════════════════════════════
tbm = get_tempo_bus_manager()
tbm.load_dict([])
bus_a = tbm.ensure_bus("A"); bus_a.set_role("master"); bus_a.set_bpm(BPM)
bus_b = tbm.ensure_bus("B"); bus_b.set_role("sub"); bus_b.set_parent("A"); bus_b.set_bus_multiplier(0.5)
bus_c = tbm.ensure_bus("C"); bus_c.set_role("sub"); bus_c.set_parent("A"); bus_c.set_bus_multiplier(2.0)
bus_d = tbm.ensure_bus("D"); bus_d.set_role("master"); bus_d.set_bpm(140.0)
tbm.set_grandmaster_bpm(BPM)
tbm.set_grandmaster_armed(False)


# ════════════════════════════════════════════════════════════════════════════════
#  3) FUNKTIONS-BIBLIOTHEK
# ════════════════════════════════════════════════════════════════════════════════
RED, GREEN, BLUE = (255, 0, 0, 0), (0, 255, 0, 0), (0, 0, 255, 0)
YELLOW, CYAN, MAGENTA = (255, 220, 0, 0), (0, 255, 255, 0), (255, 0, 255, 0)
WHITE, AMBER, PINK = (255, 255, 255, 255), (255, 120, 0, 0), (255, 0, 120, 0)
ROSE, GOLD = (255, 120, 150, 40), (255, 170, 30, 30)
RGB = lambda t: (t[0], t[1], t[2])

# MH-Farbrad / Gobo / Shutter (ZQ02001-Slots — Profil id wie Event-Demo)
MHCOL = {"weiss": 4, "rot": 14, "gruen": 24, "blau": 34, "gelb": 44,
         "orange": 54, "hellblau": 64, "rosa": 74, "rotation": 150}
MHGOBO = {"offen": 3, "g1": 11, "g2": 19, "g3": 27, "g4": 35, "g5": 43,
          "g6": 51, "g7": 59, "rotation": 190}
MH_OPEN, MH_STROBE = 4, 130


def scene_color(sc, fids, rgbw, inten=255):
    """Farbe + Intensitaet + offener Shutter (alle Kanalnummern -> alle Zellen/Baenke)."""
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
    """Spider: Bank 1 (LEDs vorne) Farbe A, Bank 2 (hinten) Farbe B — beide Spider."""
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
            sc.set_value(fid, ch, open_value_for(fx_of[fid], "shutter"))
    return sc


def dim_scene(name, on_fids):
    sc = fm.new_scene(name)
    on = set(on_fids)
    for fid in color_fids:
        for ch in attr_chs(fid, "intensity"):
            sc.set_value(fid, ch, 255 if fid in on else 0)
    return sc


# ── Matrix-Universalfabrik (RGB / RGBW / Dimmer / Shutter) ──────────────────────────
def matrix(name, algo, colors, *, style=MatrixStyle.RGB, grid=None, params=None,
           speed=1.2, prio=0, bus="", mult=1.0, imin=0, imax=255):
    m = fm.new_rgb_matrix(name)
    m.algorithm = algo
    g = grid if grid is not None else GRID_FRONT
    m.fixture_grid = list(g)
    m.cols, m.rows = len(g), 1
    m.colors = ColorSequence([tuple(c) for c in colors])
    m.style = style
    m.drive_intensity = False
    m.intensity_min, m.intensity_max = imin, imax
    m.matrix_speed = speed
    m.priority = prio
    if bus:
        m.tempo_bus_id = bus
        m.tempo_multiplier = mult
        m.sync_group = "hochzeit"
    if params:
        m.params = dict(params)
    return m


# ── ALLE 18 RGB-Algorithmen (reine Farbebene) ──────────────────────────────────────
m_plain    = matrix("01 Plain (Vollflaeche)", RgbAlgorithm.PLAIN, [RGB(AMBER)], speed=0.6)
m_chase    = matrix("02 Chase (Lauflicht)", RgbAlgorithm.CHASE, [RGB(BLUE), RGB(WHITE)],
                    params={"axis": "H", "movement": "normal", "runner_count": 1,
                            "runner_width": 1, "after_fade": 35.0, "color_cycle": True}, speed=3.0)
m_wipe     = matrix("03 Wipe (Wisch)", RgbAlgorithm.WIPE, [RGB(WHITE), RGB(BLUE)],
                    params={"axis": "H", "movement": "bounce", "edge_fade": 0.25}, speed=1.4)
m_wave     = matrix("04 Wave (Welle)", RgbAlgorithm.WAVE, [RGB(BLUE), RGB(CYAN)],
                    params={"origin": "left", "density": 1.5, "spread": 1.0}, speed=1.5)
m_gradient = matrix("05 Gradient (Verlauf)", RgbAlgorithm.GRADIENT, [RGB(BLUE), RGB(MAGENTA), RGB(CYAN)],
                    params={"axis": "H", "blend": "smooth"}, speed=0.6)
m_rainbow  = matrix("06 Rainbow (Regenbogen)", RgbAlgorithm.RAINBOW, [RGB(RED)],
                    params={"movement": "linear", "spread": 1.5, "saturation": 1.0, "value": 1.0}, speed=1.0)
m_fill     = matrix("07 Fill (Aufbau)", RgbAlgorithm.FILL, [RGB(GOLD), RGB(WHITE)],
                    params={"fill_mode": "target", "fill_dir": "left", "loop_mode": "reverse"}, speed=1.4)
m_colfade  = matrix("08 Color Fade (Farbreise)", RgbAlgorithm.COLORFADE, [RGB(RED), RGB(GREEN), RGB(BLUE)],
                    params={"hold": 0.2}, speed=0.8)
LINEAR_MATRICES = [m_plain, m_chase, m_wipe, m_wave, m_gradient, m_rainbow, m_fill, m_colfade]

m_random   = matrix("09 Random (Zufall)", RgbAlgorithm.RANDOM, [RGB(RED), RGB(GREEN), RGB(BLUE), RGB(MAGENTA)],
                    params={"mode": "color", "count": 4, "rate": 3.0, "no_repeat": True}, speed=2.0)
m_strobe   = matrix("10 Strobe (Farbblitz)", RgbAlgorithm.STROBE, [RGB(WHITE)], speed=6.0)
m_checker  = matrix("11 Schachbrett", RgbAlgorithm.CHECKER, [RGB(RED), RGB(BLUE)],
                    params={"tile": 1, "blink": True}, speed=1.0)
m_radar    = matrix("12 Radar", RgbAlgorithm.RADAR, [RGB(GREEN)],
                    params={"beam_width": 0.18, "fade": 0.3}, speed=1.0)
m_spiral   = matrix("13 Spirale", RgbAlgorithm.SPIRAL, [RGB(MAGENTA), RGB(CYAN)],
                    params={"turns": 2.0, "beam_width": 0.15}, speed=1.0)
m_plasma   = matrix("14 Sine Plasma", RgbAlgorithm.SINEPLASMA, [RGB(MAGENTA), RGB(CYAN)], speed=0.5)
m_pinwheel = matrix("15 Windrad", RgbAlgorithm.PINWHEEL, [RGB(RED), RGB(BLUE)],
                    params={"runner_count": 3}, speed=1.0)
m_breathe  = matrix("16 Atmen (Puls)", RgbAlgorithm.BREATHE, [RGB(AMBER)], speed=0.8)
m_fire     = matrix("17 Feuer", RgbAlgorithm.FIRE, [RGB(RED), RGB(YELLOW)], speed=1.4)
m_rain     = matrix("18 Regen", RgbAlgorithm.RAIN, [RGB(CYAN)], params={"fade": 0.45}, speed=1.6)
TEXTURE_MATRICES = [m_random, m_strobe, m_checker, m_radar, m_spiral, m_plasma,
                    m_pinwheel, m_breathe, m_fire, m_rain]
RGB_MATRICES = LINEAR_MATRICES + TEXTURE_MATRICES   # alle 18 Algorithmen

# ── RGBW-Style (echtes Weiss via rgbw_split — nutzt den W-Chip) ─────────────────────
m_rgbw_white = matrix("RGBW Reines Weiss", RgbAlgorithm.PLAIN, [RGB(WHITE)],
                      style=MatrixStyle.RGBW, grid=GRID_RGBW, speed=0.5)
m_rgbw_rb    = matrix("RGBW Regenbogen", RgbAlgorithm.RAINBOW, [RGB(RED)],
                      style=MatrixStyle.RGBW, grid=GRID_RGBW,
                      params={"movement": "linear", "spread": 1.0}, speed=0.9)
m_rgbw_spark = matrix("RGBW Funkeln (Spider)", RgbAlgorithm.RANDOM, [RGB(WHITE), RGB(CYAN)],
                      style=MatrixStyle.RGBW, grid=GRID_SPIDER,
                      params={"mode": "sparkle", "count": 2, "rate": 5.0}, speed=2.0)
RGBW_MATRICES = [m_rgbw_white, m_rgbw_rb, m_rgbw_spark]

# ── Dimmer-Style (reiner Dimmer — legt sich disjunkt UEBER die Farbe) ────────────────
d_breathe = matrix("Dim Atmen", RgbAlgorithm.BREATHE, [RGB(WHITE)],
                   style=MatrixStyle.DIMMER, prio=1, speed=0.8, imin=20, imax=255)
d_wave    = matrix("Dim Welle", RgbAlgorithm.WAVE, [RGB(WHITE)], style=MatrixStyle.DIMMER, prio=1,
                   params={"origin": "left", "density": 1.0}, speed=1.5, imin=0, imax=255)
d_chase   = matrix("Dim Chase (Sequenz)", RgbAlgorithm.CHASE, [RGB(WHITE)], style=MatrixStyle.DIMMER, prio=1,
                   params={"axis": "H", "movement": "normal", "dimmer_cycle": True,
                           "dimmer_sequence": [255, 128, 64]}, speed=2.5)
d_fill    = matrix("Dim Aufbau", RgbAlgorithm.FILL, [RGB(WHITE)], style=MatrixStyle.DIMMER, prio=1,
                   params={"fill_mode": "up", "fill_dir": "left", "loop_mode": "reverse"}, speed=1.4)
d_random  = matrix("Dim Funkeln", RgbAlgorithm.RANDOM, [RGB(WHITE)], style=MatrixStyle.DIMMER, prio=1,
                   params={"mode": "sparkle", "count": 3, "rate": 4.0}, speed=2.0)
DIMMER_MATRICES = [d_breathe, d_wave, d_chase, d_fill, d_random]

# ── Shutter-Style (Strobe ueber den echten Shutter-Kanal) ───────────────────────────
s_strobe = matrix("Shutter Strobe", RgbAlgorithm.STROBE, [RGB(WHITE)],
                  style=MatrixStyle.SHUTTER, prio=2, speed=8.0)

# Grundfarbe fuer die Dimmer/Shutter-Demos (damit man im Dunkeln was sieht)
base_amber = matrix("Grundfarbe Amber", RgbAlgorithm.PLAIN, [RGB(AMBER)], prio=0, speed=0.4)


# ── EFX (Bewegung) — alle 10 Figuren ────────────────────────────────────────────────
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
        e.sync_group = "hochzeit"
    return e


efx_circle   = efx("Kreis", EfxAlgorithm.CIRCLE, mover_fids, phase_mode="fan", counter=True, size=150, speed_hz=0.5)
efx_eight    = efx("Acht", EfxAlgorithm.EIGHT, mh_fids, phase_mode="sync", size=140, speed_hz=0.4)
efx_line     = efx("Linie (Spider Wippe)", EfxAlgorithm.LINE, spider_fids, phase_mode="offset", size=220, speed_hz=0.7)
efx_diamond  = efx("Raute", EfxAlgorithm.DIAMOND, mh_fids, phase_mode="sync", size=150, speed_hz=0.4)
efx_square   = efx("Rechteck", EfxAlgorithm.SQUARE, mh_fids, phase_mode="sync", size=150, speed_hz=0.35)
efx_trapez   = efx("Trapez", EfxAlgorithm.TRAPEZ, mh_fids, phase_mode="sync", size=160, speed_hz=0.35)
efx_triangle = efx("Dreieck", EfxAlgorithm.TRIANGLE, mh_fids, phase_mode="sync", size=150, speed_hz=0.4)
efx_lissa    = efx("Lissajous", EfxAlgorithm.LISSAJOUS, mh_fids, phase_mode="fan", size=170, speed_hz=0.4, xf=3.0, yf=2.0)
efx_random   = efx("Zufall (Mover)", EfxAlgorithm.RANDOM, mover_fids, phase_mode="offset", size=180, speed_hz=0.6)
EFX_BASE = [efx_circle, efx_eight, efx_line, efx_diamond, efx_square,
            efx_trapez, efx_triangle, efx_lissa, efx_random]

# Custom-Path-EFX (selbst gezeichnete Bahn)
paths = get_efx_path_library()
zig = paths.add(EfxPath("Zickzack", [(0.1, 0.3), (0.35, 0.75), (0.6, 0.3), (0.9, 0.75)],
                        mode="linear", closed=False))
efx_custom = fm.new_efx("Custom-Pfad (Zickzack)")
efx_custom.fixtures = [EfxFixture(fid=f) for f in mover_fids]
efx_custom.set_custom_path(zig)
efx_custom.open_beam = True
efx_custom.width = efx_custom.height = 180.0
EFX_ALL = EFX_BASE + [efx_custom]   # alle 10 EfxAlgorithm-Werte

# ── MH-Farb-/Gobo-/Strobe-Szenen ────────────────────────────────────────────────────
mh_red = mh_scene("MH Rot", col=MHCOL["rot"])
mh_green = mh_scene("MH Gruen", col=MHCOL["gruen"])
mh_blue = mh_scene("MH Blau", col=MHCOL["blau"])
mh_white = mh_scene("MH Weiss", col=MHCOL["weiss"])
mh_colspin = mh_scene("MH Farbrotation", col=MHCOL["rotation"])
MH_COLORS = [mh_red, mh_green, mh_blue, mh_white, mh_colspin]
mh_g1 = mh_scene("MH Gobo 1", col=MHCOL["blau"], gobo=MHGOBO["g1"])
mh_g3 = mh_scene("MH Gobo 3", col=MHCOL["gruen"], gobo=MHGOBO["g3"])
mh_g5 = mh_scene("MH Gobo 5", col=MHCOL["rot"], gobo=MHGOBO["g5"])
mh_gspin = mh_scene("MH Gobo Rotation", col=MHCOL["weiss"], gobo=MHGOBO["rotation"])
MH_GOBOS = [mh_g1, mh_g3, mh_g5, mh_gspin]
mh_strobe = mh_scene("MH Strobe", col=MHCOL["weiss"], strobe=True)

# ── Spider-Themes ───────────────────────────────────────────────────────────────────
sp_rb = spider_theme("Spider Rot/Blau", RED, BLUE)
sp_gm = spider_theme("Spider Gruen/Magenta", GREEN, MAGENTA)
sp_cw = spider_theme("Spider Cyan/Warm", CYAN, AMBER)
sp_pw = spider_theme("Spider Pink/Weiss", PINK, WHITE)
SP_THEMES = [sp_rb, sp_gm, sp_cw, sp_pw]
sp_strobe = fm.new_scene("Spider Strobe")
for fid in spider_fids:
    for ch in attr_chs(fid, "intensity"):
        sp_strobe.set_value(fid, ch, 255)
    for ch in attr_chs(fid, "shutter"):
        sp_strobe.set_value(fid, ch, 70)

# ── Voll-Looks + statische Empfangslooks ────────────────────────────────────────────
look_warm = look("Empfang Warm", AMBER)
look_candle = look("Kerzenlicht", GOLD)
look_rose = look("Rosa Traum", ROSE)
look_white = look("Voll Weiss", WHITE)
look_blue = look("Voll Blau", BLUE)
VIVID = [look_warm, look_candle, look_rose, look_white]
LEFT = front_fids[:6]
RIGHT = front_fids[6:]


def split_scene(name, lc, rc):
    sc = fm.new_scene(name)
    scene_color(sc, LEFT + [13], lc)
    scene_color(sc, RIGHT + [14], rc)
    return sc


sp_split_gb = split_scene("Gruen links / Blau rechts", GREEN, BLUE)
sp_split_rw = split_scene("Rot links / Weiss rechts", RED, WHITE)
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


chase_looks = chaser("Chase Voll-Looks", [s.id for s in VIVID], hold=BAR, fade=0.3)
chase_mh_color = chaser("Chase MH-Farben", [s.id for s in MH_COLORS], hold=BEAT * 2, fade=0.05)
chase_spider = chaser("Chase Spider-Themes", [s.id for s in SP_THEMES], hold=BAR, fade=0.3)
auto_schema = chaser("Auto-Farbschema (Beat)", [m_rainbow.id, m_gradient.id, m_plasma.id],
                     audio=True, beats_per_step=16, fade=BAR)
drop_color = chaser("Drop Farbwechsel (Beat)",
                    [look_white.id, sp_split_gb.id, look_blue.id, sp_split_rw.id],
                    audio=True, beats_per_step=2, fade=0.04)
CHASERS = [chase_looks, chase_mh_color, chase_spider, auto_schema, drop_color]


# ── Tempo-synchrone Effekte (Master/Sub-Demo) ───────────────────────────────────────
sync_chase = matrix("Sync Chase >Bus A", RgbAlgorithm.CHASE, [RGB(BLUE), RGB(WHITE)],
                    params={"axis": "H", "movement": "normal", "color_cycle": True},
                    speed=1.0, bus="A", mult=1.0, prio=3)
sync_breathe = matrix("Sync Atmen >Bus B (1/2)", RgbAlgorithm.BREATHE, [RGB(WHITE)],
                      style=MatrixStyle.DIMMER, speed=1.0, bus="B", mult=1.0, prio=4)
sync_strobe = matrix("Sync Blitz >Bus C (x2)", RgbAlgorithm.STROBE, [RGB(WHITE)],
                     style=MatrixStyle.DIMMER, speed=1.0, bus="C", mult=1.0, prio=5)
sync_mh = efx("Sync MH-Kreis >Bus A", EfxAlgorithm.CIRCLE, mh_fids, phase_mode="fan", size=150, bus="A", mult=1.0)
SYNC_FX = [sync_chase, sync_breathe, sync_strobe, sync_mh]


# ── Misch-Ablaeufe (Collections) ────────────────────────────────────────────────────
def collection(name, ids):
    c = fm.new_collection(name)
    c.function_ids = list(ids)
    return c


mix_party = collection("Mix: Party", [m_rainbow.id, efx_circle.id, efx_random.id])
mix_drop = collection("Mix: Drop", [d_random.id, efx_eight.id, sp_strobe.id])
mix_chill = collection("Mix: Chill", [m_gradient.id, d_breathe.id, efx_circle.id])
mix_theme = collection("Mix: Spider+Gobo", [sp_gm.id, mh_g3.id, efx_line.id])
MIXES = [mix_party, mix_drop, mix_chill, mix_theme]

# ── Live-Chase (per VCChaseBuilder/VCColorList bedienbar) ────────────────────────────
live_chase = matrix("Live-Chase", RgbAlgorithm.COLORFADE, [RGB(GREEN), RGB(WHITE), RGB(BLUE)],
                    grid=GRID_FRONT, speed=1.0)


# ════════════════════════════════════════════════════════════════════════════════
#  4) PLAYBACKS — Cuelisten (Beat-Sync + Follow)
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


pb_warm = state.new_cue_stack("Aufwaermen (Follow)")
pb_warm.mode = "loop"
for num, lbl, rgbw in [(1.0, "Amber", AMBER), (2.0, "Rosa", ROSE), (3.0, "Weiss", WHITE)]:
    pb_warm.add_cue(Cue(number=num, label=lbl, fade_in=PHRASE, follow=PHRASE * 1.5,
                        values=par_vals(rgbw, inten=180)))

pb_drop = state.new_cue_stack("Drop-Sequenz (Beat)")
pb_drop.mode = "loop"; pb_drop.beat_sync = True; pb_drop.beats_per_cue = 4
for num, lbl, rgbw in [(1.0, "Rot", RED), (2.0, "Weiss", WHITE), (3.0, "Blau", BLUE), (4.0, "Weiss", WHITE)]:
    pb_drop.add_cue(Cue(number=num, label=lbl, fade_in=0.05, follow=None, values=par_vals(rgbw)))

pb_color = state.new_cue_stack("Farb-Reise (Beat)")
pb_color.mode = "loop"; pb_color.beat_sync = True; pb_color.beats_per_cue = 8
for num, lbl, rgbw in [(1.0, "Gruen", GREEN), (2.0, "Cyan", CYAN), (3.0, "Blau", BLUE), (4.0, "Magenta", MAGENTA)]:
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
    "function_ids": [auto_schema.id, efx_circle.id],
    "bank": 0,
    "slots": {auto_schema.id: "front_show", efx_circle.id: "mover_show"},
}


# ════════════════════════════════════════════════════════════════════════════════
#  6) VIRTUAL CONSOLE  (8 Baenke + universelle Leiste)
# ════════════════════════════════════════════════════════════════════════════════
PAD, GAP, X0, Y0 = 60, 6, 20, 70
STEP = PAD + GAP
GRID_BOTTOM = Y0 + 8 * STEP
TY = GRID_BOTTOM + 4
Y_FAD = GRID_BOTTOM + 34
FAD_H = 142
RX = 620
widgets: list[dict] = []
BANK_ALL = -1
(B_LOOK, B_MTXA, B_MTXB, B_DIM, B_MOVE, B_BPM, B_FLOW, B_MUSIC) = range(8)
PAGE_NAMES = ["Empfang & Looks", "Matrix-Algos A", "Matrix-Algos B (+RGBW)", "Dimmer & Strobo",
              "Bewegung (EFX)", "BPM & Tempo", "Ablaeufe / Mischen", "Musik & Auto-Show"]


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


def chase_builder(caption, x, y, bank, function_id, ww=340, hh=240):
    w = VCChaseBuilder(caption)
    w.function_id = function_id
    _add(w, x, y, ww, hh, bank)


def xy_pad(caption, x, y, bank, fids, mode="position", efx_function_id=None, ww=190, hh=190):
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


def encoder(caption, col, bank, function_id, param_key, step=5.0):
    """Endlos-Drehknopf fuer einen Effekt-Parameter — in der Fader-Reihe (Spalte)."""
    w = VCEncoder(caption)
    w.function_id = function_id
    w.param_key = param_key
    w.step = step
    x = X0 + col * STEP + 2
    _add(w, x, Y_FAD, 56, FAD_H, bank)


def stepper(caption, col, bank, function_id, param_key, step=1):
    """Schrittweiser +/- Wert fuer einen Effekt-Parameter — in der Fader-Reihe (Spalte)."""
    w = VCStepper(caption)
    w.function_id = function_id
    w.param_key = param_key
    w.step = int(step)
    x = X0 + col * STEP + 2
    _add(w, x, Y_FAD, 56, FAD_H, bank)


def tempo_ctrl(caption, x, y, bank, tempo_bus_id="A", ww=300, hh=150):
    w = VCTempoBusController(caption)
    w.tempo_bus_id = tempo_bus_id
    _add(w, x, y, ww, hh, bank)


def frame(caption, x, y, bank, ww=360, hh=150, show_header=True):
    w = VCFrame(caption)
    w.show_header = show_header
    _add(w, x, y, ww, hh, bank)


def effect_editor(caption, x, y, bank, effect_id, ww=340, hh=250):
    w = VCEffectEditor(caption)
    w.effect_id = effect_id
    _add(w, x, y, ww, hh, bank)


def effect_display(caption, x, y, bank, function_id, ww=260, hh=130):
    w = VCEffectDisplay(caption)
    w.function_id = function_id
    _add(w, x, y, ww, hh, bank)


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
label("HOCHZEIT KOMPLETT 2026  —  1 Dotz-Bar + 4 Flat-Par + 6 PAR + 1 Moving Head + 2 Spider (14 Fixtures, "
      "137 Kanaele).  SCENE-Tasten = Bank 1-8 (Looks - Matrix A - Matrix B/RGBW - Dimmer/Strobo - "
      "Bewegung - BPM/Tempo - Ablaeufe - Musik).  > (Track 6) startet Musik + Auto-Show.",
      X0, 6, 1300, BANK_ALL)
label("Universell: Clear - Stop All - Blackout - Tap - << - >/|| - >> - Musik-BPM   |   "
      "Fader: F6 Dimmer - F7 Speed - F9 Master", X0, Y_FAD + FAD_H + 6, 1150, BANK_ALL)


# ── BANK 1 — EMPFANG & LOOKS ────────────────────────────────────────────────────────
song_info(RX, Y0, B_LOOK)
for i, fn in enumerate(VIVID):                                            # R0 = statische Looks
    func_btn(fn, note_rc(0, i), B_LOOK, "#5a4020", exclusive=True, clear_prog=True, style="solid")
func_btn(m_plain, note_rc(0, 5), B_LOOK, "#1f5a3a", exclusive=True, clear_prog=True)   # reine RGB-Flaeche
func_btn(m_rgbw_white, note_rc(0, 6), B_LOOK, "#888888", exclusive=True, clear_prog=True)  # reines RGBW-Weiss
COLORS16 = [
    ("Rot", 255, 0, 0, 0), ("Orange", 255, 90, 0, 0), ("Amber", 255, 160, 0, 0), ("Gelb", 255, 220, 0, 0),
    ("Limette", 160, 255, 0, 0), ("Gruen", 0, 255, 0, 0), ("Tuerkis", 0, 230, 150, 0), ("Cyan", 0, 255, 255, 0),
    ("Hellblau", 0, 140, 255, 0), ("Blau", 0, 0, 255, 0), ("Violett", 140, 0, 255, 0), ("Magenta", 255, 0, 255, 0),
    ("Pink", 255, 0, 120, 0), ("Warmweiss", 255, 130, 40, 60), ("Weiss", 255, 255, 255, 255), ("Aus", 0, 0, 0, 0),
]
for i, (nm, r, g, b, w) in enumerate(COLORS16):                           # R1-2 = 16 Farb-Kacheln
    color_tile(nm, note_rc(1 + i // 8, i % 8), B_LOOK, r, g, b, w, target=ColorTarget.ALL)
for i, (nm, grp) in enumerate([("Alle Front", "Alle Front"), ("PAR-Reihe", "PAR-Reihe"),
                               ("Flat-Pars", "Flat-Pars"), ("Spider", "Spider"), ("Alles", "Alles")]):
    select_group_btn(nm, grp, note_rc(3, i), B_LOOK)                      # R3 = Gruppen
action_btn("Alle Weiss", ButtonAction.ALL_WHITE, note_rc(4, 0), B_LOOK, "#777777")
eff_colors("Verlauf-Farben", RX, Y0 + 120, B_LOOK, m_gradient.id)
color_list("Farb-Sequenz", RX, Y0 + 214, B_LOOK, m_colfade.id)
fader("Master", 0, B_LOOK, SliderMode.EFFECT_INTENSITY, midi_cc=48, value=255)
fader("Front-Dim", 3, B_LOOK, SliderMode.GROUP_DIMMER, programmer_group="Alle Front", midi_cc=51, value=255)
label("BANK 1  EMPFANG & LOOKS  —  R0: Looks + reine RGB-Flaeche + reines RGBW-Weiss (Flat-Par/Spider W-Chip). "
      "R1-2: 16 Farb-Kacheln. R3: Gruppen. Rechts: Farb-Editor.", X0, 28, 1300, B_LOOK)


# ── BANK 2 — MATRIX-ALGOS A (linear) ────────────────────────────────────────────────
LIN_ACCENT = ["#1f5a3a", "#1f4a6a", "#3a4a6a", "#1f5a6a", "#3a1f6a", "#6a3a1f", "#5a5a1f", "#6a1f4a"]
for i, m in enumerate(LINEAR_MATRICES):                                   # R0 = 8 lineare Algos
    func_btn(m, note_rc(0, i), B_MTXA, LIN_ACCENT[i], exclusive=True, clear_prog=True)
for i, (nm, grp) in enumerate([("Alle Front", "Alle Front"), ("PAR-Reihe", "PAR-Reihe"), ("Spider", "Spider")]):
    select_group_btn(nm, grp, note_rc(1, i), B_MTXA)
effect_display("Live-Vorschau", RX, Y0, B_MTXA, m_chase.id)
chase_builder("Chase-Builder (live)", RX, Y0 + 142, B_MTXA, live_chase.id)
encoder("Tempo", 4, B_MTXA, m_chase.id, "speed", step=0.25)
stepper("Lauflichter", 7, B_MTXA, m_chase.id, "runner_count", step=1)
fader("Matrix-Master", 0, B_MTXA, SliderMode.EFFECT_INTENSITY, midi_cc=48, value=255)
fader("Matrix-Speed", 1, B_MTXA, SliderMode.EFFECT_SPEED, midi_cc=49, value=80)
fader("Weiss-Anteil", 2, B_MTXA, SliderMode.EFFECT_PARAM, param_key="white_amount", midi_cc=50, value=255)
label("BANK 2  MATRIX-ALGOS A  —  R0: Plain/Chase/Wipe/Wave/Gradient/Rainbow/Fill/ColorFade (exklusiv, reine "
      "Farbe RGB). Rechts: Live-Vorschau + Chase-Builder. Encoder Tempo, Stepper Lauflichter.", X0, 28, 1300, B_MTXA)


# ── BANK 3 — MATRIX-ALGOS B (Textur/2D) + RGBW ──────────────────────────────────────
TEX_ACCENT = ["#6a6a1f", "#5a1f1f", "#3a3a5a", "#1f6a3a", "#5a1f6a", "#1f5a6a",
              "#3a1f6a", "#6a4a1f", "#6a2f1f", "#1f4a6a"]
for i, m in enumerate(TEXTURE_MATRICES):                                  # R0-1 = 10 Textur-Algos
    func_btn(m, note_rc(i // 8, i % 8), B_MTXB, TEX_ACCENT[i], exclusive=True, clear_prog=True)
func_btn(m_rgbw_rb, note_rc(2, 0), B_MTXB, "#888888")                     # RGBW-Style Regenbogen
func_btn(m_rgbw_spark, note_rc(2, 1), B_MTXB, "#aaaaaa")                  # RGBW-Style Funkeln (Spider)
eff_colors("Effekt-Farben", RX, Y0, B_MTXB, m_spiral.id)
color_list("Plasma-Farben", RX, Y0 + 94, B_MTXB, m_plasma.id)
effect_display("Vorschau Feuer", RX, Y0 + 188, B_MTXB, m_fire.id)
encoder("Dichte", 7, B_MTXB, m_rain.id, "density", step=0.25)
fader("FX-Master", 0, B_MTXB, SliderMode.EFFECT_INTENSITY, midi_cc=48, value=255)
fader("FX-Speed", 1, B_MTXB, SliderMode.EFFECT_SPEED, midi_cc=49, value=80)
label("BANK 3  MATRIX-ALGOS B  —  R0-1: Random/Strobe/Schachbrett/Radar/Spirale/Plasma/Windrad/Atmen/Feuer/"
      "Regen. R2: RGBW-Style (echtes Weiss). Rechts: Effekt-Farben + Vorschau.", X0, 28, 1300, B_MTXB)


# ── BANK 4 — DIMMER & STROBO ────────────────────────────────────────────────────────
func_btn(base_amber, note_rc(0, 0), B_DIM, "#6a4a1f", style="solid")      # Grundfarbe an
for i, m in enumerate(DIMMER_MATRICES):                                   # R1 = 5 Dimmer-Matrizen
    func_btn(m, note_rc(1, i), B_DIM, "#1f3a6a")
func_btn(s_strobe, note_rc(1, 6), B_DIM, "#5a1f1f")                       # Shutter-Strobe
func_flash(s_strobe, note_rc(1, 7), B_DIM, "#551111")
dim_l = dim_scene("Dim Links", LEFT)
dim_r = dim_scene("Dim Rechts", RIGHT)
dim_odd = dim_scene("Dim ungerade", [front_fids[i] for i in range(0, len(front_fids), 2)])
dim_even = dim_scene("Dim gerade", [front_fids[i] for i in range(1, len(front_fids), 2)])
for i, fn in enumerate([dim_l, dim_r, dim_odd, dim_even]):                # R2 = Helligkeits-Splits
    func_btn(fn, note_rc(2, i), B_DIM, "#2a3a5a", style="solid")
func_flash(sp_strobe, note_rc(2, 7), B_DIM, "#551111")
stepper("Dimmer-Level", 7, B_DIM, base_amber.id, "intensity_max", step=16)
fader("Dimmer-Master", 0, B_DIM, SliderMode.EFFECT_INTENSITY, midi_cc=48, value=255)
fader("Dimmer-Speed", 1, B_DIM, SliderMode.EFFECT_SPEED, midi_cc=49, value=80)
fader("Front-Dim", 3, B_DIM, SliderMode.GROUP_DIMMER, programmer_group="Alle Front", midi_cc=51, value=255)
fader("Programmer-Dim", 4, B_DIM, SliderMode.PROGRAMMER, programmer_attr="intensity", midi_cc=52, value=255)
label("BANK 4  DIMMER & STROBO  —  R0: Grundfarbe. R1: Atmen/Welle/Chase/Aufbau/Funkeln (Dimmer-Matrix, legt "
      "sich UEBER die Farbe) + Shutter-Strobe. R2: Helligkeits-Splits + Spider-Strobe.", X0, 28, 1300, B_DIM)


# ── BANK 5 — BEWEGUNG (alle 10 EFX-Figuren) ─────────────────────────────────────────
for i, e in enumerate(EFX_ALL[:8]):                                       # R0 = 8 Figuren
    func_btn(e, note_rc(0, i), B_MOVE, "#1f3a6a", edit_slot="mover_show")
for i, e in enumerate(EFX_ALL[8:]):                                       # R1 = Rest (Zufall + Custom)
    func_btn(e, note_rc(1, i), B_MOVE, "#3a1f6a", edit_slot="mover_show")
for i, fn in enumerate(MH_COLORS):                                        # R2 = MH-Farben
    func_btn(fn, note_rc(2, i), B_MOVE, "#3a5a1f", style="solid")
for i, fn in enumerate(MH_GOBOS):                                         # R3 = MH-Gobos
    func_btn(fn, note_rc(3, i), B_MOVE, "#5a3a1f", style="solid")
func_flash(mh_strobe, note_rc(3, 7), B_MOVE, "#551111")
effect_action_btn("Gegenlaeufig", note_rc(4, 0), B_MOVE, "#7a6500", "toggle_counter", efx_circle.id)
effect_action_btn("Spiegeln", note_rc(4, 1), B_MOVE, "#334455", "toggle_mirror", efx_circle.id)
effect_action_btn("Richtung", note_rc(4, 2), B_MOVE, "#445566", "reverse_direction", efx_circle.id)
effect_action_btn("Neustart", note_rc(4, 3), B_MOVE, "#553010", "restart", efx_circle.id)
select_group_btn("Mover", "Alle Mover", note_rc(4, 4), B_MOVE)
xy_pad("MH zielen (Pan/Tilt)", RX, Y0, B_MOVE, mh_fids, mode="position")
xy_pad("EFX-Feld aufziehen", RX + 210, Y0, B_MOVE, mover_fids, mode="area", efx_function_id=efx_circle.id)
encoder("EFX-Tempo", 7, B_MOVE, efx_circle.id, "speed_hz", step=0.05)
fader("Mover-Speed", 0, B_MOVE, SliderMode.EFFECT_SPEED, function_ids=[e.id for e in EFX_ALL], midi_cc=48, value=80)
fader("Mover-Groesse", 1, B_MOVE, SliderMode.EFFECT_PARAM, function_ids=[e.id for e in EFX_ALL], param_key="size", midi_cc=49, value=150)
fader("Mover-Dim", 3, B_MOVE, SliderMode.GROUP_DIMMER, programmer_group="Alle Mover", midi_cc=51, value=255)
label("BANK 5  BEWEGUNG  —  R0-1: alle 10 EFX-Figuren (Kreis/Acht/Linie/Raute/Rechteck/Trapez/Dreieck/"
      "Lissajous/Zufall/Custom-Pfad). R2: MH-Farbrad. R3: MH-Gobos. R4: Gegenlaeufig/Spiegeln/Richtung/Neustart. "
      "Rechts: XY-Pad (Position + Feld).", X0, 28, 1300, B_MOVE)


# ── BANK 6 — BPM & TEMPO ────────────────────────────────────────────────────────────
action_btn("Tap Tempo", ButtonAction.TAP, note_rc(0, 0), B_BPM, "#103a3a")
action_btn("Musik-BPM", ButtonAction.AUDIO_BPM, note_rc(0, 1), B_BPM, "#103a4a")
action_btn("BPM +", ButtonAction.BPM_NUDGE_UP, note_rc(0, 2), B_BPM, "#1f5a3a")
action_btn("BPM -", ButtonAction.BPM_NUDGE_DOWN, note_rc(0, 3), B_BPM, "#5a1f1f")
action_btn("BPM-Modus", ButtonAction.BPM_MODE_TOGGLE, note_rc(0, 4), B_BPM, "#3a3a1f")
action_btn("Tap Bus A", ButtonAction.TAP_BUS, note_rc(1, 0), B_BPM, "#1f3a6a", tempo_bus_id="A")
action_btn("Sync Bus A", ButtonAction.SYNC_BUS, note_rc(1, 1), B_BPM, "#1f4a6a", tempo_bus_id="A")
action_btn("Arm Bus", ButtonAction.ARM_BUS, note_rc(1, 2), B_BPM, "#5a3a1f", tempo_bus_id="A")
for i, fn in enumerate(SYNC_FX):                                          # R2 = bus-gekoppelte Effekte
    func_btn(fn, note_rc(2, i), B_BPM, ["#1f5a3a", "#1f3a6a", "#5a1f1f", "#3a1f6a"][i])
bpm_display(RX, Y0, B_BPM, tempo_bus_id="", caption="GLOBAL BPM")
bpm_display(RX + 196, Y0, B_BPM, tempo_bus_id="A", caption="BUS A (Master)")
bus_selector(RX, Y0 + 106, B_BPM)
tempo_ctrl("Tempo-Bus-Panel A", RX, Y0 + 200, B_BPM, tempo_bus_id="A")
speed_dial("Master A", RX + 390, Y0, B_BPM, target_mode=SpeedTarget.SPEED_NODE, tempo_bus_id="A", role="master")
speed_dial("Sub B (1/2)", RX + 390, Y0 + 160, B_BPM, target_mode=SpeedTarget.SPEED_NODE,
           tempo_bus_id="B", role="sub", parent_bus_id="A")
fader("Tempo Bus A", 0, B_BPM, SliderMode.TEMPO_BUS, tempo_bus_id="A", midi_cc=48, value=100)
fader("Tempo Bus D", 1, B_BPM, SliderMode.TEMPO_BUS, tempo_bus_id="D", midi_cc=49, value=85)
fader("BPM global", 3, B_BPM, SliderMode.BPM, midi_cc=51, value=100)
label("BANK 6  BPM & TEMPO  —  R0: Tap/Musik-BPM/+/-/Modus. R1: Tap/Sync/Arm Bus. R2: tempo-synchrone Effekte "
      "(Bus A=voll, B=halb, C=doppelt). Rechts: BPM-Anzeige + Bus-Wahl + Tempo-Panel + Master/Sub-Knoten.",
      X0, 28, 1300, B_BPM)


# ── BANK 7 — ABLAEUFE / MISCHEN ─────────────────────────────────────────────────────
MIX_ACCENT = ["#6a1f4a", "#5a1f1f", "#1f5a3a", "#1f3a6a"]
for i, fn in enumerate(MIXES):                                            # R0 = Misch-Collections
    func_btn(fn, note_rc(0, i), B_FLOW, MIX_ACCENT[i], exclusive=True, clear_prog=True)
for i, fn in enumerate(CHASERS):                                          # R1 = Chaser
    func_btn(fn, note_rc(1, i), B_FLOW, "#3a3a5a")
for i, pb in enumerate(PLAYBACKS):                                        # R2 = GO Cuelisten
    exec_go_btn(f"GO {pb.name[:7]}", i, note_rc(2, i), B_FLOW, ["#1f4a28", "#8b0d4f", "#0d4f8b"][i])
func_btn(live_chase, note_rc(3, 0), B_FLOW, "#1f5a3a")                    # Live-Chase
effect_action_btn("Leeren", note_rc(3, 1), B_FLOW, "#5a1010", "clear_colors", live_chase.id)
effect_action_btn("Farbe -", note_rc(3, 2), B_FLOW, "#333355", "prev_color", live_chase.id)
effect_action_btn("Farbe +", note_rc(3, 3), B_FLOW, "#333355", "next_color", live_chase.id)
LC_COLORS = [("Rot", 255, 0, 0), ("Orange", 255, 90, 0), ("Gelb", 255, 220, 0), ("Gruen", 0, 255, 0),
             ("Cyan", 0, 255, 255), ("Blau", 0, 0, 255), ("Magenta", 255, 0, 255), ("Weiss", 255, 255, 255)]
for i, (nm, r, g, b) in enumerate(LC_COLORS):                            # R4 = Farben zur Live-Chase
    color_tile(nm, note_rc(4, i), B_FLOW, r, g, b, target=ColorTarget.EFFECT_ADD, function_id=live_chase.id)
cue_list(pb_warm.name, 0, RX, Y0, B_FLOW, ww=230, hh=146)
cue_list(pb_drop.name, 1, RX + 240, Y0, B_FLOW, ww=230, hh=146)
frame("Solo-Rahmen (Container)", RX, Y0 + 156, B_FLOW, ww=300, hh=110, show_header=True)
effect_editor("Effekt-Editor (All-in-One)", RX + 320, Y0 + 156, B_FLOW, live_chase.id, ww=330, hh=240)
for i, pb in enumerate(PLAYBACKS):
    pb_fader(f"Dim {i + 1}", i, B_FLOW, slot=i, midi_cc=48 + i, value=255)
label("BANK 7  ABLAEUFE / MISCHEN  —  R0: Misch-Collections. R1: Chaser. R2: GO Cuelisten (Beat-Sync). "
      "R3: Live-Chase + Leeren/-/+. R4: Farben hinzufuegen. Rechts: Cuelisten + Frame + Effekt-Editor.",
      X0, 28, 1300, B_FLOW)


# ── BANK 8 — MUSIK & AUTO-SHOW ──────────────────────────────────────────────────────
action_btn("<< Lied", ButtonAction.MEDIA_PREV, note_rc(0, 0), B_MUSIC, "#3a2150")
action_btn(">/|| Play", ButtonAction.MEDIA_PLAY_PAUSE, note_rc(0, 1), B_MUSIC, "#5a2080")
action_btn("Lied >>", ButtonAction.MEDIA_NEXT, note_rc(0, 2), B_MUSIC, "#3a2150")
action_btn("Musik-BPM", ButtonAction.AUDIO_BPM, note_rc(0, 3), B_MUSIC, "#103a4a")
func_btn(auto_schema, note_rc(1, 0), B_MUSIC, "#1f5a3a")                  # Auto-Show-Funktionen
func_btn(efx_circle, note_rc(1, 1), B_MUSIC, "#1f3a6a")
song_info(RX, Y0, B_MUSIC, ww=320, hh=120)
label("Auto-Show ist AN: Beim Start des Lieds (>) startet der MusicShowDirector automatisch das "
      "Auto-Farbschema + den MH-Kreis. Auto-Show pro Lied in Eingabe/Ausgabe > Musik.", RX, Y0 + 130, 320, B_MUSIC, hh=60)
fader("Lautstaerke", 0, B_MUSIC, SliderMode.PLAYBACK, function_id=1, midi_cc=48, value=255)
label("BANK 8  MUSIK & AUTO-SHOW  —  R0: Lied-Steuerung + Musik-BPM. R1: Auto-Show-Funktionen. "
      "Rechts: Song-Info-Anzeige. > startet Musik + Auto-Show.", X0, 28, 1300, B_MUSIC)


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
#  7) SPEICHERN + ERSCHOEPFENDE VERIFIKATION (Assert-Gate)
# ════════════════════════════════════════════════════════════════════════════════
state.programmer = {}
state.show_name = "Hochzeit Komplett 2026"
save_show(OUT)
print(f"Gespeichert: {OUT}")
ok, msg = load_show(OUT)
print("Load:", ok, msg)
assert ok, f"Show laedt nicht: {msg}"
state = get_state()
fm = get_function_manager()

from collections import Counter
from src.core.engine.rgb_matrix import RgbMatrixInstance, MatrixStyle as MS
from src.core.engine.efx import EfxInstance
from src.core.engine.scene import Scene
from src.core.engine.collection import Collection
from src.ui.virtualconsole.vc_canvas import WIDGET_REGISTRY

fx = state.get_patched_fixtures()
assert len(fx) == 14, f"Fixtures: {len(fx)} (erwartet 14)"
total_ch = sum(f.channel_count for f in fx)
assert total_ch == 137, f"DMX-Kanäle: {total_ch} (erwartet 137)"
print("Fixtures:", dict(Counter(f.fixture_type for f in fx)), "| Kanaele:", total_ch)

# VC-Layout
vc = state._vc_layout.get("widgets", [])
banks = Counter(w.get("bank") for w in vc)
assert set(banks) == {0, 1, 2, 3, 4, 5, 6, 7, -1}, f"Banks: {sorted(banks)}"
types = Counter(w["type"] for w in vc)
# ALLE 19 Registry-Widget-Typen muessen vorkommen
expected_widgets = set(WIDGET_REGISTRY.keys())
present = set(types)
missing_w = expected_widgets - present
assert not missing_w, f"Widget-Typen fehlen: {sorted(missing_w)}"

# Matrizen: alle 18 Algorithmen + alle 4 Styles
mats = [f for f in fm.all() if isinstance(f, RgbMatrixInstance)]
algos_present = {m.algorithm for m in mats}
all_algos = set(RgbAlgorithm)
missing_a = all_algos - algos_present
assert not missing_a, f"Matrix-Algorithmen fehlen: {[a.name for a in missing_a]}"
styles_present = {m.style for m in mats}
missing_s = set(MatrixStyle) - styles_present
assert not missing_s, f"Matrix-Styles fehlen: {[s.name for s in missing_s]}"
rgb_color = [m for m in mats if m.style == MS.RGB]
dim_m = [m for m in mats if m.style == MS.DIMMER]
assert len(rgb_color) >= 18, f"RGB-Farbmatrizen: {len(rgb_color)}"
assert len(dim_m) >= 5, f"Dimmer-Matrizen: {len(dim_m)}"

# EFX: alle 10 Figuren + Custom mit Pfad
efxs = [f for f in fm.all() if isinstance(f, EfxInstance)]
efx_present = {e.algorithm for e in efxs}
missing_e = set(EfxAlgorithm) - efx_present
assert not missing_e, f"EFX-Figuren fehlen: {[a.name for a in missing_e]}"
custom = [e for e in efxs if e.algorithm == EfxAlgorithm.CUSTOM]
assert custom and custom[0].path_data, "Custom-Path-EFX fehlt/leer"
assert any({x.fid for x in e.fixtures} & set(spider_fids) for e in efxs), "keine Spider-EFX"
assert any({x.fid for x in e.fixtures} & set(mh_fids) for e in efxs), "keine MH-EFX"

# Tempo-Buses Master/Sub
tbm2 = get_tempo_bus_manager()
named = {b.bus_id: b for b in tbm2.named_buses()}
assert {"A", "B", "C", "D"}.issubset(named), f"Buses: {list(named)}"
assert named["A"].role == "master" and named["B"].role == "sub", "A/B Rollen falsch"
assert named["B"].parent_id == "A" and abs(named["B"].bus_multiplier - 0.5) < 1e-6, "Sub B falsch"
assert abs(named["C"].bus_multiplier - 2.0) < 1e-6, "Sub C falsch"
assert tbm2.grandmaster_bpm > 0, "Grand-Master-BPM fehlt"
bus_bound = [f for f in fm.all() if getattr(f, "tempo_bus_id", "") in ("A", "B", "C", "D")]
assert len(bus_bound) >= 4, f"bus-gebundene Effekte: {len(bus_bound)}"

# MH-Farbrad/Gobo + Spider-Bank-Trennung + RGBW-Weiss
mh_cw_ch = chan_of[12]["color_wheel"]
mh_gw_ch = chan_of[12]["gobo_wheel"]
sc_red = next(f for f in fm.all() if isinstance(f, Scene) and f.name == "MH Rot")
assert sc_red.get_value(12, mh_cw_ch) == MHCOL["rot"], "MH Rot Farbrad falsch"
sc_g1 = next(f for f in fm.all() if isinstance(f, Scene) and f.name == "MH Gobo 1")
assert sc_g1.get_value(12, mh_gw_ch) == MHGOBO["g1"], "MH Gobo 1 falsch"
sp_cols = [c for c in chans_full[13]
           if (c.attribute or "") in ("color_r", "color_g", "color_b", "color_w")]
sc_rb = next(f for f in fm.all() if isinstance(f, Scene) and f.name == "Spider Rot/Blau")
assert sc_rb.get_value(13, sp_cols[0].channel_number) == 255, "Spider linke Bank nicht rot"
assert sc_rb.get_value(13, sp_cols[4 + 2].channel_number) == 255, "Spider rechte Bank nicht blau"

# Collections + Beat-Sync-Cuelisten + Auto-Show + Playlist
cols = [f for f in fm.all() if isinstance(f, Collection)]
assert len(cols) >= 4, f"Collections: {len(cols)}"
chasers = [f for f in fm.all() if type(f).__name__ == "Chaser"]
assert len(chasers) >= 5, f"Chaser: {len(chasers)}"
beat_stacks = [s for s in state.cue_stacks if getattr(s, "beat_sync", False)]
assert len(beat_stacks) == 2, [s.name for s in beat_stacks]
ma = state.music_autoshow
assert ma.get("enabled") is True, ma
fn_ids = {f.id for f in fm.all()}
assert ma.get("function_ids") and all(fid in fn_ids for fid in ma["function_ids"]), ma
assert len(state.playlist) == len(CURATED), f"Playlist: {len(state.playlist)}"

# VC-Geometrie: nicht zu hoch + keine Ueberlappung klassischer interaktiver Widgets
maxy = max((w.get("y", 0) + w.get("h", 0)) for w in vc)
assert maxy < 820, f"zu hoch: {maxy}"
_INTER = {"VCButton", "VCSlider", "VCColor", "VCXYPad", "VCCueList", "VCColorList",
          "VCChaseBuilder", "VCSpeedDial", "VCSongInfo", "VCBpmDisplay", "VCBusSelector",
          "VCEffectColors", "VCEffectDisplay", "VCEncoder"}


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

print(f"Funktionen: {len(fm.all())}  VC-Widgets: {len(vc)}  Max-Y={maxy}")
print(f"  Matrix-Algorithmen: {len(algos_present)}/18  Styles: {sorted(s.name for s in styles_present)}")
print(f"  EFX-Figuren: {len(efx_present)}/10  RGB-Matrizen={len(rgb_color)}  Dimmer={len(dim_m)}")
print(f"  Widget-Typen ({len(present)}/19): alle vorhanden")
print(f"  Buses: {[f'{b.bus_id}:{b.role}x{b.bus_multiplier}' for b in tbm2.named_buses()]}  GM-BPM={tbm2.grandmaster_bpm}")
print(f"  Collections={len(cols)}  Chaser={len(chasers)}  Beat-Cuelisten={[s.name for s in beat_stacks]}  Playlist={len(state.playlist)}")
print("  [OK] 14 Fixtures - alle 18 Algos - alle 4 Styles - alle 10 EFX - alle 19 Widgets - Tempo-Buses - Auto-Show")
print("FERTIG")
