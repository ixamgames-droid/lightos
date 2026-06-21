"""TESTSHOW 2026 — komplette musik-synchrone Show für Davids reales Rig.

Rig (Adressierung): 8× RGBW-PAR (ZQ01424, 8ch) → 2× Moving Head (ZQ02001, 11ch)
→ 2× Spider (SPIDER14, 14ch, RGBW + Pan/Tilt aus eigener Bibliothek).

Look-Idee (Davids Wunsch): mit FARB-MATRIZEN spielen (grün/weiß → blau/weiß →
grün/blau) und DIMMER-MATRIZEN drüberlegen; dazu EFX/Effekte inkl. räumlicher
Looks („grün links / weiß rechts"). Alles zur Musik (BP-Party-Stil, 150 BPM) und
komplett über das APC mini steuerbar.

Bänke (APC-SCENE = Bank/Seite):
  Bank 1  FARBSCHEMATA   3 Farb-Matrizen (grün/weiß · blau/weiß · grün/blau) als
                         Exklusiv-Toggle + 16 Farb-Kacheln + Looks + Auto-Show-Play.
  Bank 2  DIMMER-EFFEKTE Dimmer-Matrizen (Atmen/Blitz/Aufbau/Welle) zum Drüberlegen.
  Bank 3  EFX & MOVER    MH/Spider-Bewegungen (Kreis/Fächer/Acht/Lissajous), fan/
                         gegenläufig + Speed/Größe-Fader.
  Bank 4  RÄUMLICHE LOOKS Szenen „grün links / weiß rechts" u.ä. + Gruppen + 2 Beat-
                         Sync-Cuelisten (GO) + Solo.
  Bank 5  RGBW-PROGRAMMER R/G/B/W/Intensität-Fader (Programmer) + Fixture-Strobe/Macro.
  Bank 6  LIVE-CHASE     Farb-Kacheln (Farbe hinzufügen) + Start/Clear/±/Speed.

Aufruf:  venv/Scripts/python.exe tools/build_testshow_2026.py
Erzeugt: shows/Testshow_2026.lshow
"""
from __future__ import annotations
import os
import sys
import glob

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
_app = QApplication.instance() or QApplication([])

import json
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
from src.core.engine.cue import Cue
from src.core.show.show_file import reset_show, save_show, load_show
from src.core.audio.media_player import clean_title, guess_genre_bpm
from src.ui.virtualconsole.vc_button import VCButton, ButtonAction
from src.ui.virtualconsole.vc_color import VCColor, ColorTarget
from src.ui.virtualconsole.vc_label import VCLabel
from src.ui.virtualconsole.vc_cuelist import VCCueList
from src.ui.virtualconsole.vc_song_info import VCSongInfo
from src.ui.virtualconsole.vc_slider import VCSlider, SliderMode

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(_ROOT, "shows", "Testshow_2026.lshow")
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
#  0) BASIS + PATCH  (8 PAR → 2 MH → 2 Spider, Universe 1, 114 Kanäle)
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

mh_fids = [9, 10]
for fid, lbl, a in ((9, "MH Links", 65), (10, "MH Rechts", 76)):
    state.add_fixture(PatchedFixture(
        fid=fid, label=lbl, fixture_profile_id=MH_PID, mode_name="11-Kanal",
        universe=1, address=a, channel_count=11, manufacturer_name="U King",
        fixture_name="ZQ02001 Mini Moving Head", fixture_type="moving_head"), undoable=False)

spider_fids = [11, 12]
for fid, lbl, a in ((11, "Spider Links", 87), (12, "Spider Rechts", 101)):
    state.add_fixture(PatchedFixture(
        fid=fid, label=lbl, fixture_profile_id=SPIDER_PID, mode_name="14-Kanal",
        universe=1, address=a, channel_count=14, manufacturer_name="U King",
        fixture_name="Spider 14ch", fixture_type="moving_head"), undoable=False)

mover_fids = mh_fids + spider_fids                  # alle mit Pan/Tilt (für EFX)
color_fids = par_fids + spider_fids                 # alle mit RGB(W) (für Farb-Matrix)

fixtures = state.get_patched_fixtures()
fx_of = {f.fid: f for f in fixtures}
chans_full = {f.fid: get_channels_for_patched(f) for f in fixtures}


def attr_chs(fid: int, attr: str) -> list[int]:
    """ALLE Kanalnummern eines Attributs (Spider hat color_r doppelt → beide Bänke)."""
    return [c.channel_number for c in chans_full[fid] if (c.attribute or "").lower() == attr]


# Grundhelligkeit: PAR + Spider leuchten standardmäßig (Farb-Matrix sichtbar ohne Dimmer-Matrix).
state.base_levels = {fid: {"intensity": 255} for fid in color_fids}
state._rebuild_render_plan()

# ── Gruppen ───────────────────────────────────────────────────────────────────
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
    s.add(FixtureGroup(name="Farb-Matrix", cols=10, rows=1,
                       positions_json=json.dumps({f"{i},0": color_fids[i] for i in range(10)})))
    s.commit()


# ════════════════════════════════════════════════════════════════════════════════
#  1) MUSIK-PLAYLIST (BP-Party-Ordner; Player liest die Original-Pfade)
# ════════════════════════════════════════════════════════════════════════════════
CURATED = [
    ("mr. brightside",      "Bounce",   150),
    ("angels (jesse bloch", "Bounce",   150),
    ("i need a hero",       None,       None),
    ("africa (rayvolt",     None,       None),
    ("major tom",           None,       None),
    ("gym hardstyle",       None,       None),
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
    playlist.append({
        "path": p, "title": clean_title(p),
        "genre": g_over or genre,
        "bpm": float(b_over if b_over is not None else bpm),
    })
state.playlist = playlist
if missing:
    print(f"[build] WARNUNG: {missing} Track(s) nicht gefunden — Platzhalter eingetragen "
          f"(Ordner {MUSIC_DIR}).")


# ════════════════════════════════════════════════════════════════════════════════
#  2) FUNKTIONS-BIBLIOTHEK
# ════════════════════════════════════════════════════════════════════════════════
# ── Farben (RGBW-Tupel) ──────────────────────────────────────────────────────────
GREEN, WHITE, BLUE = (0, 255, 0, 0), (255, 255, 255, 255), (0, 0, 255, 0)
GREEN_RGB, WHITE_RGB, BLUE_RGB = (0, 255, 0), (255, 255, 255), (0, 0, 255)


def scene_color(sc, fids, rgbw, inten=255):
    """Setzt Farbe+Intensität+offenen Shutter auf eine Fixture-Liste (Spider: beide Bänke)."""
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


def dim_scene(name, on_fids):
    """Helligkeits-Look: nur die genannten PAR/Spider an (weiß-neutral via Intensität)."""
    sc = fm.new_scene(name)
    on = set(on_fids)
    for fid in color_fids:
        for ch in attr_chs(fid, "intensity"):
            sc.set_value(fid, ch, 255 if fid in on else 0)
    return sc


# ── Farb-Matrizen (RGB-Style, drive_intensity=False → reine Farbebene) ────────────
def color_matrix(name, algo, colors, params=None, speed=2.0):
    m = fm.new_rgb_matrix(name)
    m.algorithm = algo
    m.fixture_grid = list(color_fids)
    m.cols, m.rows = len(color_fids), 1
    m.colors = ColorSequence([tuple(c) for c in colors])
    m.style = MatrixStyle.RGB
    m.drive_intensity = False
    m.matrix_speed = speed
    if params:
        m.params = dict(params)
    return m


mtx_gw = color_matrix("Farbe Grün+Weiß", RgbAlgorithm.WAVE, [GREEN_RGB, WHITE_RGB],
                      params={"origin": "radial", "density": 1.0, "spread": 1.0}, speed=1.2)
mtx_bw = color_matrix("Farbe Blau+Weiß", RgbAlgorithm.GRADIENT, [BLUE_RGB, WHITE_RGB],
                      params={"axis": "H", "blend": "smooth"}, speed=0.7)
mtx_gb = color_matrix("Farbe Grün+Blau", RgbAlgorithm.GRADIENT, [GREEN_RGB, BLUE_RGB],
                      params={"axis": "H", "blend": "smooth"}, speed=0.8)
COLOR_MATRICES = [mtx_gw, mtx_bw, mtx_gb]


# ── Dimmer-Matrizen (Dimmer-Style; schreiben NUR den Dimmer → über Farbe legbar) ──
def dimmer_matrix(name, algo, params=None, speed=1.5, imin=0, imax=255, priority=1):
    m = fm.new_rgb_matrix(name)
    m.algorithm = algo
    m.fixture_grid = list(color_fids)
    m.cols, m.rows = len(color_fids), 1
    m.colors = ColorSequence([(255, 255, 255)])
    m.style = MatrixStyle.DIMMER
    m.drive_intensity = False
    m.intensity_min, m.intensity_max = imin, imax
    m.matrix_speed = speed
    m.priority = priority
    if params:
        m.params = dict(params)
    return m


dim_breathe = dimmer_matrix("Dimmer Atmen", RgbAlgorithm.BREATHE, speed=0.8)
dim_strobe = dimmer_matrix("Dimmer Blitz", RgbAlgorithm.STROBE, speed=6.0)
dim_fill = dimmer_matrix("Dimmer Aufbau", RgbAlgorithm.FILL,
                         params={"fill_mode": "up", "loop_mode": "reverse"}, speed=1.5)
dim_wave = dimmer_matrix("Dimmer Welle", RgbAlgorithm.WAVE,
                         params={"origin": "left", "density": 1.0}, speed=1.5)
DIMMER_MATRICES = [dim_breathe, dim_strobe, dim_fill, dim_wave]


# ── EFX (Bewegung; alle Mover haben Pan/Tilt) ─────────────────────────────────────
def efx(name, algo, fids, phase_mode="fan", spread=1.0, counter=False, mirror=False,
        x=128.0, y=128.0, size=110.0, speed_hz=0.5, xf=3.0, yf=2.0):
    e = fm.new_efx(name)
    e.algorithm = algo
    e.fixtures = [EfxFixture(fid=f) for f in fids]
    e.speed_hz, e.spread, e.open_beam = speed_hz, spread, True
    e.x_offset, e.y_offset = x, y
    e.width = e.height = size
    e.phase_mode, e.counter_rotate, e.mirror = phase_mode, counter, mirror
    e.x_freq, e.y_freq = xf, yf
    return e


efx_mh_circle = efx("MH Kreis", EfxAlgorithm.CIRCLE, mh_fids, phase_mode="sync", size=110, speed_hz=0.5)
efx_mh_fan = efx("MH Fächer", EfxAlgorithm.CIRCLE, mh_fids, phase_mode="fan",
                 spread=1.0, counter=True, size=150, speed_hz=0.45)
efx_mh_eight = efx("MH Acht", EfxAlgorithm.EIGHT, mh_fids, phase_mode="sync", size=120, speed_hz=0.4)
efx_spider = efx("Spider Kreis", EfxAlgorithm.CIRCLE, spider_fids, phase_mode="offset",
                 counter=True, size=130, speed_hz=0.6)
efx_all_lissa = efx("Alle Lissajous", EfxAlgorithm.LISSAJOUS, mover_fids, phase_mode="fan",
                    size=150, speed_hz=0.5, xf=3.0, yf=2.0)
efx_all_fan = efx("Alle Mover Fächer", EfxAlgorithm.CIRCLE, mover_fids, phase_mode="fan",
                  spread=1.0, counter=True, size=140, speed_hz=0.5)
EFX_FUNCS = [efx_mh_circle, efx_mh_fan, efx_mh_eight, efx_spider, efx_all_lissa, efx_all_fan]


# ── Räumliche Looks (Szenen; „nur grün links / nur weiß rechts" etc.) ─────────────
LEFT, RIGHT = par_fids[:4], par_fids[4:]


def split_scene(name, left_rgbw, right_rgbw, left_fids=LEFT, right_fids=RIGHT,
                spider_left=None, spider_right=None):
    sc = fm.new_scene(name)
    scene_color(sc, left_fids, left_rgbw)
    scene_color(sc, right_fids, right_rgbw)
    if spider_left is not None:
        scene_color(sc, [11], spider_left)
    if spider_right is not None:
        scene_color(sc, [12], spider_right)
    return sc


sp_gl_wr = split_scene("Grün links · Weiß rechts", GREEN, WHITE, spider_left=GREEN, spider_right=WHITE)
sp_wl_gr = split_scene("Weiß links · Grün rechts", WHITE, GREEN, spider_left=WHITE, spider_right=GREEN)
sp_gl_br = split_scene("Grün links · Blau rechts", GREEN, BLUE, spider_left=GREEN, spider_right=BLUE)
sp_bl_gr = split_scene("Blau links · Grün rechts", BLUE, GREEN, spider_left=BLUE, spider_right=GREEN)
only_green_l = dim_scene("Nur Links (grün)", LEFT)          # nur linke Seite an
look_only_green_l = look("Look Links Grün", GREEN, fids=LEFT)
only_spider = look("Nur Spider", BLUE, fids=spider_fids)
SPATIAL = [sp_gl_wr, sp_wl_gr, sp_gl_br, sp_bl_gr, look_only_green_l, only_spider]

# ── Voll-Looks + Schema-Looks (für Chaser-Schritte / Instant-Recall) ──────────────
look_green = look("Look Grün", GREEN)
look_white = look("Look Weiß", WHITE)
look_blue = look("Look Blau", BLUE)
VIVID = [look_green, look_white, look_blue]


def chaser(name, step_ids, hold=BEAT, fade=0.0, speed=1.0,
           audio=False, beats_per_step=1, run_order=RunOrder.Loop):
    c = fm.new_chaser(name)
    c.run_order, c.direction, c.speed = run_order, Direction.Forward, speed
    c.audio_triggered, c.beats_per_step = audio, beats_per_step
    for sid in step_ids:
        c.steps.append(ChaserStep(function_id=sid, fade_in=fade, hold=hold, fade_out=0.0))
    return c


# Auto-Show: Farbschema wechselt im 4-Takt-Raster zur Musik (grün/weiß → blau/weiß → grün/blau).
auto_schema = chaser("Auto-Farbschema (Beat)", [mtx_gw.id, mtx_bw.id, mtx_gb.id],
                     audio=True, beats_per_step=16, fade=BAR)
# Drop: harte Farbwechsel jeden halben Takt (Voll-Looks + Splits).
drop_color = chaser("Drop Farbwechsel (Beat)",
                    [look_green.id, sp_gl_wr.id, look_blue.id, sp_bl_gr.id,
                     look_white.id, sp_gl_br.id],
                    audio=True, beats_per_step=2, fade=0.04)
# Kontinuierlicher MH-Orbit als Auto-Show-Bewegung.
auto_orbit = efx_mh_circle


# ════════════════════════════════════════════════════════════════════════════════
#  3) PLAYBACKS — 2 Beat-Sync-Cuelisten (taktgenau zur Musik) + 1 Zeit-Loop
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
pb_drop.mode = "loop"
pb_drop.beat_sync = True
pb_drop.beats_per_cue = 4
for num, lbl, rgbw in [(1.0, "Grün", GREEN), (2.0, "Weiß", WHITE),
                       (3.0, "Blau", BLUE), (4.0, "Weiß", WHITE)]:
    pb_drop.add_cue(Cue(number=num, label=lbl, fade_in=0.05, follow=None, values=par_vals(rgbw)))

pb_color = state.new_cue_stack("Farb-Reise")
pb_color.mode = "loop"
pb_color.beat_sync = True
pb_color.beats_per_cue = 8
for num, lbl, rgbw in [(1.0, "Grün", GREEN), (2.0, "Cyan", (0, 255, 200, 0)),
                       (3.0, "Blau", BLUE), (4.0, "Weiß", WHITE)]:
    pb_color.add_cue(Cue(number=num, label=lbl, fade_in=BEAT, follow=None, values=par_vals(rgbw)))

PLAYBACKS = [pb_warm, pb_drop, pb_color]
PB_PAGE = 3   # Bank 4 (0-basiert == Seite 3): GO-Pads liegen dort.
pe = state.playback_engine
for slot, pb in enumerate(PLAYBACKS, start=1):
    ex = pe.get_executor(slot, page=PB_PAGE)
    ex.stack = pb
    ex.label = pb.name
    ex.fader_function = "volume"


# ════════════════════════════════════════════════════════════════════════════════
#  4) AUTO-SHOW-KOPPLUNG — was beim ▶ im Musik-Player automatisch startet
# ════════════════════════════════════════════════════════════════════════════════
SLOT_PAR, SLOT_MH = "par_show", "mh_show"
state.music_autoshow = {
    "enabled": True,
    "function_ids": [auto_schema.id, auto_orbit.id],
    "bank": 0,
    "slots": {auto_schema.id: SLOT_PAR, auto_orbit.id: SLOT_MH},
}


# ════════════════════════════════════════════════════════════════════════════════
#  5) VIRTUAL CONSOLE  (6 Bänke + universelle Leiste)
# ════════════════════════════════════════════════════════════════════════════════
PAD, GAP, X0, Y0 = 60, 6, 20, 70
STEP = PAD + GAP
GRID_BOTTOM = Y0 + 8 * STEP
TY = GRID_BOTTOM + 4
Y_FAD = GRID_BOTTOM + 34
FAD_H = 142
widgets: list[dict] = []
BANK_ALL = -1
B_COLOR, B_DIM, B_EFX, B_SPACE, B_PROG, B_CHASE = range(6)
PAGE_NAMES = ["Farbschemata", "Dimmer-Effekte", "EFX & Mover", "Räumliche Looks",
              "RGBW-Programmer", "Live-Chase"]


def note_rc(r, c):
    """APC-Note für visuelle Position (Zeile 0 = oben, Spalte 0 = links)."""
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


def action_btn(name, action, note, bank, accent):
    b = VCButton(name)
    b.action = action
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


def color_tile(name, note, bank, r, g, b, w=0, target=ColorTarget.ALL,
               function_id=None, with_intensity=True):
    c = VCColor(name)
    c.color_r, c.color_g, c.color_b, c.color_w = r, g, b, w
    c.with_intensity = with_intensity
    c.target = target
    c.function_id = function_id
    c.midi_type, c.midi_ch, c.midi_data1 = "note_on", 0, note
    x, y = pad_pos(note)
    _add(c, x, y, PAD, PAD, bank)


def fader(caption, col, bank, mode, function_ids=None, programmer_attr="intensity",
          programmer_scope="all", programmer_group="", param_key="speed",
          midi_cc=-1, value=0, submaster_slot=None, function_id=None):
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


# ── Universell (BANK_ALL) — 8 Track-Tasten + Master-Fader + Kopf-Label ──
TRACK = [("Clear", ButtonAction.CLEAR, "#4a3a10"), ("Stop All", ButtonAction.STOP_ALL, "#4a1010"),
         ("Blackout", ButtonAction.BLACKOUT, "#2a0000"), ("Tap", ButtonAction.TAP, "#103a3a"),
         ("◄◄ Lied", ButtonAction.MEDIA_PREV, "#3a2150"), ("▶ / ❚❚", ButtonAction.MEDIA_PLAY_PAUSE, "#5a2080"),
         ("Lied ►►", ButtonAction.MEDIA_NEXT, "#3a2150"), ("Musik-BPM", ButtonAction.AUDIO_BPM, "#103a4a")]
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
label("TESTSHOW 2026  —  8 PAR + 2 MH + 2 Spider + APC mini.  SCENE-Tasten = Bank 1-6.  "
      "▶ (Track-Taste 6 / Musik-Tab) startet Musik + Auto-Lichtshow (Farbschema wechselt im Takt).",
      X0, 6, 1250, BANK_ALL)
label("Universell: Clear · Stop All · Blackout · Tap · ◄◄ · ▶/❚❚ · ►► · Musik-BPM   |   "
      "Fader: F6 Dimmer · F7 Speed · F9 Master", X0, Y_FAD + FAD_H + 6, 1150, BANK_ALL)


# ── BANK 1 — FARBSCHEMATA (grün/weiß · blau/weiß · grün/blau + Farben + Auto-Show) ──
song = VCSongInfo("Aktuelles Lied")
_add(song, X0, Y0, 4 * STEP - 6, 2 * STEP - 6, B_COLOR)               # R0-1, Spalten 0-3
# R0 cols 4-6: die drei Farb-Matrizen (exklusiv → immer nur ein Schema aktiv).
for i, m in enumerate(COLOR_MATRICES):
    func_btn(m, note_rc(0, 4 + i), B_COLOR, "#1f5a3a", exclusive=True, clear_prog=True)
# R0 col 7 / R1 col 7: Auto-Show-Schema + Drop-Farbwechsel (beat-getriggert).
func_btn(auto_schema, note_rc(0, 7), B_COLOR, "#7a5b00", edit_slot=SLOT_PAR)
func_btn(drop_color, note_rc(1, 7), B_COLOR, "#7a3b00", edit_slot=SLOT_PAR)
# R1 cols 4-6: Voll-Looks Grün/Weiß/Blau (einfrieren).
for i, fn in enumerate(VIVID):
    func_btn(fn, note_rc(1, 4 + i), B_COLOR, "#333333", style="solid", edit_slot=SLOT_PAR)
# R2-3: 16 Farb-Kacheln (Programmer/ALL) — manuelle Farbe auf alles.
COLORS16 = [
    ("Rot", 255, 0, 0, 0), ("Orange", 255, 90, 0, 0), ("Amber", 255, 160, 0, 0), ("Gelb", 255, 220, 0, 0),
    ("Limette", 160, 255, 0, 0), ("Grün", 0, 255, 0, 0), ("Türkis", 0, 230, 150, 0), ("Cyan", 0, 255, 255, 0),
    ("Hellblau", 0, 140, 255, 0), ("Blau", 0, 0, 255, 0), ("Violett", 140, 0, 255, 0), ("Magenta", 255, 0, 255, 0),
    ("Pink", 255, 0, 120, 0), ("Warmweiß", 255, 130, 40, 60), ("Weiß", 255, 255, 255, 255), ("Aus", 0, 0, 0, 0),
]
for i, (nm, r, g, b, w) in enumerate(COLORS16):
    color_tile(nm, note_rc(2 + i // 8, i % 8), B_COLOR, r, g, b, w, target=ColorTarget.ALL)
# R4: Gruppen-Auswahl.
for i, (nm, grp) in enumerate([("Alle PAR", "Alle PAR"), ("PAR L", "PAR Links"), ("PAR R", "PAR Rechts"),
                               ("MH", "Moving Heads"), ("Spider", "Spider")]):
    select_group_btn(nm, grp, note_rc(4, i), B_COLOR)
fader("Matrix-Master", 0, B_COLOR, SliderMode.EFFECT_INTENSITY, midi_cc=48, value=255)
fader("Matrix-Speed", 1, B_COLOR, SliderMode.EFFECT_SPEED, midi_cc=49, value=80)
fader("Weiß-Anteil", 2, B_COLOR, SliderMode.EFFECT_PARAM, param_key="white_amount", midi_cc=50, value=255)
fader("PAR-Dim", 3, B_COLOR, SliderMode.GROUP_DIMMER, programmer_group="Alle PAR", midi_cc=51, value=255)
label("BANK 1  FARBSCHEMATA  —  R0: grün/weiß · blau/weiß · grün/blau (exklusiv) + Auto-Schema/Drop. "
      "R1: Voll-Looks. R2-3: 16 Farb-Kacheln (auf alles). R4: Gruppen. Fader: Matrix-Master/Speed/Weiß/Dim.",
      X0, 28, 1250, B_COLOR)


# ── BANK 2 — DIMMER-EFFEKTE (zum Drüberlegen über die Farb-Matrix) ────────────────
for i, m in enumerate(DIMMER_MATRICES):                              # R0 = 4 Dimmer-Matrizen
    func_btn(m, note_rc(0, i), B_DIM, "#1f3a6a")
func_flash(dim_strobe, note_rc(0, 7), B_DIM, "#551111")              # Strobe als Flash
# R1: Helligkeits-Splits als schnelle Dimmer-Szenen.
dim_l = dim_scene("Dim Links", LEFT)
dim_r = dim_scene("Dim Rechts", RIGHT)
dim_odd = dim_scene("Dim ungerade", [par_fids[i] for i in range(0, 8, 2)])
dim_even = dim_scene("Dim gerade", [par_fids[i] for i in range(1, 8, 2)])
for i, fn in enumerate([dim_l, dim_r, dim_odd, dim_even]):
    func_btn(fn, note_rc(1, i), B_DIM, "#2a3a5a", style="solid")
fader("Dimmer-Master", 0, B_DIM, SliderMode.EFFECT_INTENSITY, midi_cc=48, value=255)
fader("Dimmer-Speed", 1, B_DIM, SliderMode.EFFECT_SPEED, midi_cc=49, value=80)
fader("PAR-Dim", 3, B_DIM, SliderMode.GROUP_DIMMER, programmer_group="Alle PAR", midi_cc=51, value=255)
label("BANK 2  DIMMER-EFFEKTE  —  R0: Atmen · Blitz · Aufbau · Welle (Dimmer-Matrix, legt sich ÜBER "
      "die Farbe; F8=Strobe-Flash). R1: Helligkeits-Splits. Fader: Dimmer-Master/Speed.",
      X0, 28, 1250, B_DIM)


# ── BANK 3 — EFX & MOVER (MH + Spider Bewegung) ───────────────────────────────────
EFX_ACCENT = ["#1f3a6a", "#1f3a6a", "#1f3a6a", "#3a1f6a", "#6a1f4a", "#1f6a4a"]
for i, fn in enumerate(EFX_FUNCS):                                   # R0 = 6 EFX
    func_btn(fn, note_rc(0, i), B_EFX, EFX_ACCENT[i], edit_slot=SLOT_MH)
# R1: Effekt-Aktionen.
effect_action_btn("Spiegeln", note_rc(1, 0), B_EFX, "#334455", "toggle_mirror", None)
effect_action_btn("Gegenläufig", note_rc(1, 1), B_EFX, "#7a6500", "toggle_counter", None)
effect_action_btn("Richtung", note_rc(1, 2), B_EFX, "#445566", "reverse_direction", None)
effect_action_btn("Neustart", note_rc(1, 3), B_EFX, "#553010", "restart", None)
# R2: Gruppen-Auswahl + Mover-Looks.
for i, (nm, grp) in enumerate([("MH", "Moving Heads"), ("Spider", "Spider"), ("Alle Mover", "Alle Mover")]):
    select_group_btn(nm, grp, note_rc(2, i), B_EFX)
fader("EFX-Speed", 0, B_EFX, SliderMode.EFFECT_SPEED, midi_cc=48, value=80)
fader("EFX-Größe", 1, B_EFX, SliderMode.EFFECT_PARAM, param_key="size", midi_cc=49, value=130)
fader("EFX-Rotation", 2, B_EFX, SliderMode.EFFECT_PARAM, param_key="rotation", midi_cc=50, value=0)
fader("MH-Dim", 3, B_EFX, SliderMode.GROUP_DIMMER, programmer_group="Moving Heads", midi_cc=51, value=255)
label("BANK 3  EFX & MOVER  —  R0: MH Kreis/Fächer/Acht · Spider · Alle Lissajous/Fächer. "
      "R1: Spiegeln/Gegenläufig/Richtung/Neustart. R2: Gruppen. Fader: Speed/Größe/Rotation/MH-Dim.",
      X0, 28, 1250, B_EFX)


# ── BANK 4 — RÄUMLICHE LOOKS (grün links/weiß rechts …) + Beat-Sync-Cuelisten ─────
SPATIAL_ACCENT = ["#1f5a3a", "#3a5a1f", "#1f3a6a", "#3a1f6a", "#1f5a3a", "#3a1f5a"]
for i, fn in enumerate(SPATIAL):                                     # R0 = räumliche Szenen
    func_btn(fn, note_rc(0, i), B_SPACE, SPATIAL_ACCENT[i], style="solid", exclusive=True, clear_prog=True)
# R1-2: Cuelisten-Anzeige (Beat-Sync läuft taktgenau).
for i, pb in enumerate(PLAYBACKS):
    cl = VCCueList(pb.name)
    cl.stack_slot = i
    _add(cl, X0 + i * 250, Y0 + STEP, 240, 110, B_SPACE)
PB_ACCENT = ["#1f4a28", "#8b0d4f", "#0d4f8b"]
for i, pb in enumerate(PLAYBACKS):                                   # R3 = GO
    exec_go_btn(f"GO {pb.name[:8]}", i, note_rc(3, i), B_SPACE, PB_ACCENT[i])
# R4: Gruppen-Auswahl.
for i, (nm, grp) in enumerate([("PAR L", "PAR Links"), ("PAR R", "PAR Rechts"), ("Spider", "Spider")]):
    select_group_btn(nm, grp, note_rc(4, i), B_SPACE)
for i, pb in enumerate(PLAYBACKS):
    pb_fader(f"Dim {i+1}", i, B_SPACE, slot=i, midi_cc=48 + i, value=255)
label("BANK 4  RÄUMLICHE LOOKS  —  R0: grün links/weiß rechts u.ä. (exklusiv). R1-2: 3 Cuelisten "
      "(Aufwärmen=Zeit · Drop-Sequenz=Beat 1 Takt · Farb-Reise=Beat 2 Takte), GO unten. Fader=Dimmer.",
      X0, 28, 1250, B_SPACE)


# ── BANK 5 — RGBW-PROGRAMMER (manuelle Feinmischung) ──────────────────────────────
for i, (nm, grp) in enumerate([("Alle PAR", "Alle PAR"), ("PAR L", "PAR Links"), ("PAR R", "PAR Rechts"),
                               ("Spider", "Spider"), ("Alle Mover", "Alle Mover")]):
    select_group_btn(nm, grp, note_rc(0, i), B_PROG)
# R1: Fixture-Funktionen (Strobe / Voll).
fixt_strobe = fm.new_scene("Fixture-Strobe")
for fid in color_fids:
    for ch in attr_chs(fid, "shutter"):
        fixt_strobe.set_value(fid, ch, 200)
    for ch in attr_chs(fid, "intensity"):
        fixt_strobe.set_value(fid, ch, 255)
full_white = look("Voll Weiß", WHITE)
func_flash(fixt_strobe, note_rc(1, 0), B_PROG, "#551111")
func_btn(full_white, note_rc(1, 1), B_PROG, "#555555", style="solid")
fader("Rot", 0, B_PROG, SliderMode.PROGRAMMER, programmer_attr="color_r", midi_cc=48, value=0)
fader("Grün", 1, B_PROG, SliderMode.PROGRAMMER, programmer_attr="color_g", midi_cc=49, value=0)
fader("Blau", 2, B_PROG, SliderMode.PROGRAMMER, programmer_attr="color_b", midi_cc=50, value=0)
fader("Weiß", 3, B_PROG, SliderMode.PROGRAMMER, programmer_attr="color_w", midi_cc=51, value=0)
fader("Intensität", 4, B_PROG, SliderMode.PROGRAMMER, programmer_attr="intensity", midi_cc=52, value=255)
label("BANK 5  RGBW-PROGRAMMER  —  R0: Gruppe wählen, dann R/G/B/W/Intensität-Fader mischen. "
      "R1: Fixture-Strobe (Flash) · Voll Weiß. Wirkt auf die gewählte Gruppe/Selektion.",
      X0, 28, 1250, B_PROG)


# ── BANK 6 — LIVE-CHASE (eigene Farbsequenz live zusammenklicken) ─────────────────
live_chase = fm.new_rgb_matrix("Live-Chase")
live_chase.algorithm = RgbAlgorithm.COLORFADE
live_chase.fixture_grid = list(color_fids)
live_chase.cols, live_chase.rows = len(color_fids), 1
live_chase.colors = ColorSequence([GREEN_RGB, WHITE_RGB, BLUE_RGB])
live_chase.style = MatrixStyle.RGB
live_chase.drive_intensity = False
live_chase.matrix_speed = 1.0
LC_COLORS = [("Rot", 255, 0, 0), ("Orange", 255, 90, 0), ("Gelb", 255, 220, 0), ("Grün", 0, 255, 0),
             ("Türkis", 0, 230, 150), ("Cyan", 0, 255, 255), ("Blau", 0, 0, 255), ("Violett", 140, 0, 255),
             ("Magenta", 255, 0, 255), ("Pink", 255, 0, 120), ("Warmweiß", 255, 130, 40), ("Weiß", 255, 255, 255)]
for i, (nm, r, g, b) in enumerate(LC_COLORS):                        # R0-1 = Farben hinzufügen
    color_tile(nm, note_rc(i // 8, i % 8), B_CHASE, r, g, b,
               target=ColorTarget.EFFECT_ADD, function_id=live_chase.id)
func_btn(live_chase, note_rc(3, 0), B_CHASE, "#1f5a3a")              # Start/Stop
effect_action_btn("Leeren", note_rc(3, 1), B_CHASE, "#5a1010", "clear_colors", live_chase.id)
effect_action_btn("Farbe −", note_rc(3, 2), B_CHASE, "#333355", "prev_color", live_chase.id)
effect_action_btn("Farbe +", note_rc(3, 3), B_CHASE, "#333355", "next_color", live_chase.id)
fader("Chase-Speed", 0, B_CHASE, SliderMode.EFFECT_SPEED, function_ids=[live_chase.id], midi_cc=48, value=80)
fader("Übergang", 1, B_CHASE, SliderMode.EFFECT_PARAM, function_ids=[live_chase.id],
      param_key="hold", midi_cc=49, value=0)
label("BANK 6  LIVE-CHASE  —  R0-1: Farb-Kacheln tippen = Farbe zur Sequenz hinzufügen. "
      "R4: Start/Stop · Leeren · Farbe −/+. Fader: Chase-Speed · Übergang (0=weich, hoch=hart).",
      X0, 28, 1250, B_CHASE)


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
#  6) SPEICHERN + VERIFIKATION
# ════════════════════════════════════════════════════════════════════════════════
state.programmer = {}
state.show_name = "Testshow 2026"
save_show(OUT)
print(f"Gespeichert: {OUT}")
ok, msg = load_show(OUT)
print("Load:", ok, msg)
assert ok, f"Show laedt nicht: {msg}"
state = get_state()

from collections import Counter
fx = state.get_patched_fixtures()
assert len(fx) == 12, f"Fixtures: {len(fx)}"
types_fx = Counter(f.fixture_type for f in fx)
print("Fixtures:", dict(types_fx))

vc = state._vc_layout.get("widgets", [])
banks = Counter(w.get("bank") for w in vc)
assert set(banks) == {0, 1, 2, 3, 4, 5, -1}, f"Banks: {sorted(banks)}"
types = Counter(w["type"] for w in vc)

# Farb-Matrizen (RGB, drive_intensity False) + Dimmer-Matrizen (DIMMER) vorhanden?
from src.core.engine.rgb_matrix import RgbMatrixInstance, MatrixStyle as MS
mats = [f for f in fm.all() if isinstance(f, RgbMatrixInstance)]
color_m = [m for m in mats if m.style == MS.RGB and not m.drive_intensity]
dim_m = [m for m in mats if m.style == MS.DIMMER]
assert len(color_m) >= 3, f"Farb-Matrizen: {len(color_m)}"
assert len(dim_m) >= 4, f"Dimmer-Matrizen: {len(dim_m)}"
# Schema-Matrizen haben 2 Farben?
by_name = {m.name: m for m in mats}
for nm in ("Farbe Grün+Weiß", "Farbe Blau+Weiß", "Farbe Grün+Blau"):
    assert nm in by_name and len(by_name[nm].colors) >= 2, nm

# EFX auf MH + Spider?
from src.core.engine.efx import EfxInstance
efxs = [f for f in fm.all() if isinstance(f, EfxInstance)]
assert len(efxs) >= 6, f"EFX: {len(efxs)}"
spider_efx = [e for e in efxs if {x.fid for x in e.fixtures} & set(spider_fids)]
assert spider_efx, "keine Spider-EFX"

# Auto-Show gekoppelt + beat-getriggert?
ma = state.music_autoshow
assert ma.get("enabled") is True, ma
fn_ids = {f.id for f in fm.all()}
assert ma.get("function_ids") and all(fid in fn_ids for fid in ma["function_ids"]), ma
from src.core.engine.chaser import Chaser
par_master = fm.get(ma["function_ids"][0])
assert isinstance(par_master, Chaser) and par_master.audio_triggered, par_master

# 2 Beat-Sync-Cuelisten?
beat_stacks = [s for s in state.cue_stacks if getattr(s, "beat_sync", False)]
assert len(beat_stacks) == 2, [s.name for s in beat_stacks]
by_cs = {s.name: s for s in state.cue_stacks}
assert by_cs["Drop-Sequenz"].beats_per_cue == 4 and by_cs["Farb-Reise"].beats_per_cue == 8

# Playlist erhalten?
assert len(state.playlist) == len(CURATED), f"Playlist: {len(state.playlist)}"
assert all(t.get("bpm", 0) > 0 for t in state.playlist), state.playlist

# VC-Plausibilität: Farb-Kacheln, Media-Pads, GO-Pads, RGBW-Fader.
color_tiles = [w for w in vc if w.get("type") == "VCColor"]
assert len(color_tiles) >= 16 + 12, f"Farb-Kacheln: {len(color_tiles)}"
media_pads = [w for w in vc if w.get("action") in ("MediaPlayPause", "MediaNext", "MediaPrev")]
assert len(media_pads) == 3, f"Media-Pads: {len(media_pads)}"
go_pads = [w for w in vc if w.get("action") == "Toggle"]
assert len(go_pads) == 3, f"GO-Pads: {len(go_pads)}"
prog_faders = [w for w in vc if w.get("type") == "VCSlider" and w.get("mode") == "Programmer"]
assert len(prog_faders) == 5, f"Programmer-Fader: {len(prog_faders)}"
maxy = max((w.get("y", 0) + w.get("h", 0)) for w in vc)
assert maxy < 820, f"zu hoch: {maxy}"

# Keine Überlappung interaktiver Widgets je Bank (Bank-Layer + BANK_ALL).
_INTER = {"VCButton", "VCSlider", "VCColor", "VCXYPad", "VCCueList",
          "VCColorList", "VCChaseBuilder", "VCSpeedDial", "VCSongInfo"}


def _rect(w):
    return (w.get("x", 0), w.get("y", 0), w.get("x", 0) + w.get("w", 0), w.get("y", 0) + w.get("h", 0))


def _overlap(a, b):
    ax0, ay0, ax1, ay1 = _rect(a)
    bx0, by0, bx1, by1 = _rect(b)
    return not (ax1 <= bx0 or bx1 <= ax0 or ay1 <= by0 or by1 <= ay0)


for bk in range(6):
    layer = [w for w in vc if w.get("bank") in (bk, -1) and w["type"] in _INTER]
    for a in range(len(layer)):
        for b in range(a + 1, len(layer)):
            assert not _overlap(layer[a], layer[b]), (
                f"Overlap Bank {bk}: {layer[a]['type']}@{_rect(layer[a])} "
                f"vs {layer[b]['type']}@{_rect(layer[b])}")

print(f"Funktionen: {len(fm.all())}  VC-Widgets: {len(vc)}  Typen={dict(types)}")
print(f"Banks: {dict(sorted(banks.items()))}  Max-Y={maxy}")
print(f"  Farb-Matrizen={len(color_m)}  Dimmer-Matrizen={len(dim_m)}  EFX={len(efxs)} (Spider-EFX={len(spider_efx)})")
print(f"  Auto-Show: enabled={ma['enabled']}  fn_ids={ma['function_ids']}  slots={ma['slots']}")
print(f"  Beat-Sync: {[s.name for s in beat_stacks]}  Playlist={len(state.playlist)}")
print(f"  Farb-Kacheln={len(color_tiles)}  Media-Pads={len(media_pads)}  GO={len(go_pads)}  RGBW-Fader={len(prog_faders)}")
print("  [OK] 6 Bänke · 3 Farb-Matrizen · 4 Dimmer-Matrizen · 6 EFX (MH+Spider) · Auto-Show an Musik gekoppelt")
print("FERTIG")
