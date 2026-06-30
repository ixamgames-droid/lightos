"""PARTY DEMO 2026 — BPM-getaktete Party-Show + Musik-Playlist.

Davids reales Setup: Akai APC mini + 8× RGBW-PAR (ZQ01424, 8ch) + 2× Moving Head
(ZQ02001, 11ch).  Passend zu seiner Party-Musik (Ordner „BP Party": HBz-Bounce /
Hardstyle / Hypertechno / Frenchcore, ~150 BPM).

Inhalt (5 Banks, APC-SCENE = Bank/Seite, gekoppelt an die Playback-Seite):
  Bank 1  LIVE/PARTY   16 Farben (Programmer) + 16 Beat-Effekte (PAR) + 8 MH-Formen
                       + Looks/Gruppen/Flashes + Track-Reihe (Clear/Stop/Blackout/
                       Tap/Musik-BPM + Media Prev/Play/Next).  Fader passen sich an.
  Bank 2  MATRIX-LOOKS Alle 16 RGB-Matrix-Algorithmen auf den 8 PARs.
  Bank 3  MOVING HEADS XY-Pad (16-bit) + alle 8 EFX-Formen + Relativ/Spiegeln/Neustart.
  Bank 4  PLAYBACK     4 gespeicherte, BPM-getaktete Playbacks (Cuelisten) auf
                       Executoren: „Warmup"(loop) · „Drop/Peak"(Auto-Follow) ·
                       „Hands-Up"(bounce, beat) · „MH-Sweep"(bounce).  GO-Pads + Fader.
  Bank 5  MUSIK        VCSongInfo (aktuelles/nächstes Lied) + Media-Transport-Pads +
                       Musik-BPM.  Die Playlist ist in der Show gespeichert.

BPM: Die genaue Taktung kommt im Betrieb von VirtualDJ → OS2L (Menü „Ausgabe →
OS2L-Server").  Die hier eingebackenen Nominal-BPM (aus Genre/Titel) sind Effekt-Takt-
Vorgabe und Fallback.

Aufruf:  venv/Scripts/python.exe tools/build_party_demo_show.py
Erzeugt: shows/Party_Demo_2026.lshow
"""
from __future__ import annotations
import os
import sys
import glob
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import _gen_env  # noqa: F401  # DEMO-02: spawn-sichere Env-Schalter vor src.core (tools/_gen_env.py)
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
from src.core.engine.rgb_matrix import RgbAlgorithm
from src.core.engine.carousel import CarouselPattern
from src.core.engine.efx import EfxFixture, EfxAlgorithm
from src.core.engine.cue import Cue
from src.core.show.show_file import reset_show, save_show, load_show
from src.core.audio.media_player import clean_title, guess_genre_bpm
from src.ui.virtualconsole.vc_button import VCButton, ButtonAction
from src.ui.virtualconsole.vc_color import VCColor, ColorTarget
from src.ui.virtualconsole.vc_label import VCLabel
from src.ui.virtualconsole.vc_xypad import VCXYPad
from src.ui.virtualconsole.vc_cuelist import VCCueList
from src.ui.virtualconsole.vc_speedial import VCSpeedDial, SpeedTarget
from src.ui.virtualconsole.vc_song_info import VCSongInfo

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(_ROOT, "shows", "Party_Demo_2026.lshow")
MUSIC_DIR = r"C:/Users/David/Desktop/Musik/BP Party"

# Repräsentative Party-BPM für die Effekt-Taktung (Bounce/Hardstyle ~150).
BPM = 150.0
BEAT = 60.0 / BPM          # 0.40 s
BAR = 4 * BEAT             # 1.60 s
PHRASE = 8 * BEAT          # 3.20 s


def profile_id(short: str) -> int:
    with Session(fdb_engine()) as s:
        pid = s.execute(select(FixtureProfile.id).where(
            FixtureProfile.short_name == short)).scalar_one_or_none()
    if pid is None:
        raise SystemExit(f"Profil '{short}' fehlt — bitte App einmal starten.")
    return int(pid)


# ── 0) Basis + Patch (8 PAR + 2 MH) ─────────────────────────────────────────────
reset_show()
state = get_state()
fm = get_function_manager()
PAR_PID, MH_PID = profile_id("ZQ01424"), profile_id("ZQ02001")

par_fids: list[int] = []
addr = 1
for i in range(8):
    fid = i + 1
    state.add_fixture(PatchedFixture(
        fid=fid, label=f"PAR {i + 1}", fixture_profile_id=PAR_PID,
        mode_name="8-Kanal RGBW", universe=1, address=addr, channel_count=8,
        manufacturer_name="Generic", fixture_name="Stage Light ZQ01424",
        fixture_type="par"), undoable=False)
    par_fids.append(fid); addr += 8

mh_left, mh_right = 9, 10
for fid, lbl, a in ((mh_left, "MH Links", 65), (mh_right, "MH Rechts", 76)):
    state.add_fixture(PatchedFixture(
        fid=fid, label=lbl, fixture_profile_id=MH_PID, mode_name="11-Kanal",
        universe=1, address=a, channel_count=11, manufacturer_name="U King",
        fixture_name="ZQ02001 Mini Moving Head", fixture_type="moving_head"), undoable=False)
mh_fids = [mh_left, mh_right]

fixtures = state.get_patched_fixtures()
fx_of = {f.fid: f for f in fixtures}
chan_of = {f.fid: {c.attribute: c.channel_number
                   for c in get_channels_for_patched(f)} for f in fixtures}
state.base_levels = {fid: {"intensity": 255} for fid in par_fids}
state._rebuild_render_plan()

with state._session() as s:
    s.execute(delete(FixtureGroup))
    s.add(FixtureGroup(name="PAR-Reihe", cols=8, rows=1,
                       positions_json=json.dumps({f"{i},0": par_fids[i] for i in range(8)})))
    s.add(FixtureGroup(name="PAR Links", cols=4, rows=1,
                       positions_json=json.dumps({f"{i},0": par_fids[i] for i in range(4)})))
    s.add(FixtureGroup(name="PAR Rechts", cols=4, rows=1,
                       positions_json=json.dumps({f"{i},0": par_fids[4 + i] for i in range(4)})))
    s.add(FixtureGroup(name="Moving Heads", cols=2, rows=1,
                       positions_json=json.dumps({"0,0": mh_left, "1,0": mh_right})))
    s.add(FixtureGroup(name="Alle", cols=10, rows=1,
                       positions_json=json.dumps({f"{i},0": (par_fids + mh_fids)[i] for i in range(10)})))
    s.commit()

SHUT_OPEN = open_value_for(fx_of[mh_left], "shutter")   # offener Shutter (ZQ02001 = 4)


# ════════════════════════════════════════════════════════════════════════════════
#  1) MUSIK-PLAYLIST (in der Show gespeichert; Player liest die Original-Pfade)
# ════════════════════════════════════════════════════════════════════════════════
# (Keyword, Genre-Override|None, BPM-Override|None) — Arc Warmup → Peak → Hard → Ausklang.
CURATED = [
    ("mr. brightside",     "Bounce",   150),
    ("pompeii",            None,       None),   # Hypertechno 150
    ("angels (jesse bloch", "Bounce",  150),
    ("major tom",          None,       None),   # HBz-Bounce 155
    ("i need a hero",      None,       None),   # Psy-Bounce 150
    ("vaskan hardstyle",   None,       None),   # Hardstyle 150
    ("gym hardstyle",      None,       None),   # Hardstyle 150
    ("africa (rayvolt",    None,       None),   # Frenchcore 185
    ("sweet about me",     None,       None),   # Frenchcore 205
    ("lieder (ebbyman",    "Dance",    128),
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
    if p is None:                       # Fallback-Eintrag (Ordner/Datei fehlt)
        missing += 1
        p = os.path.join(MUSIC_DIR, kw + ".mp3")
    name = os.path.basename(p)
    genre, bpm = guess_genre_bpm(name)
    playlist.append({
        "path": p,
        "title": clean_title(p),
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
def par_dim(name, on_fids):
    sc = fm.new_scene(name); on = set(on_fids)
    for fid in par_fids:
        if "intensity" in chan_of[fid]:
            sc.set_value(fid, chan_of[fid]["intensity"], 255 if fid in on else 0)
    return sc


def par_look(name, r=0, g=0, b=0, w=0):
    sc = fm.new_scene(name)
    for fid in par_fids:
        cm = chan_of[fid]
        if "intensity" in cm:
            sc.set_value(fid, cm["intensity"], 255)
        for attr, val in (("color_r", r), ("color_g", g), ("color_b", b), ("color_w", w)):
            if attr in cm:
                sc.set_value(fid, cm[attr], val)
    return sc


def chaser(name, step_ids, hold=BEAT, fade=0.0, speed=1.0):
    c = fm.new_chaser(name)
    c.run_order, c.direction, c.speed = RunOrder.Loop, Direction.Forward, speed
    for sid in step_ids:
        c.steps.append(ChaserStep(function_id=sid, fade_in=fade, hold=hold, fade_out=0.0))
    return c


def matrix(name, algo, speed=3.0, params=None, c1=(255, 0, 0), c2=(0, 0, 255), c3=(0, 255, 0)):
    m = fm.new_rgb_matrix(name)
    m.algorithm = algo; m.fixture_grid = list(par_fids); m.cols = len(par_fids); m.rows = 1
    m.color1, m.color2, m.color3 = c1, c2, c3; m.matrix_speed = speed
    if params:
        m.params = params
    return m


def mh_efx(name, algo, relative=False, spread=0.0):
    e = fm.new_efx(name); e.algorithm = algo
    e.fixtures = [EfxFixture(fid=mh_left), EfxFixture(fid=mh_right)]
    e.speed_hz = 0.5; e.spread = spread; e.open_beam = True; e.relative = relative
    e.width = e.height = 110.0
    return e


# Dimmer-/Beat-Effekte (kombinierbar mit Farbe -> kein clear_programmer)
st = [par_dim(f"Dim P{i+1}", [par_fids[i]]) for i in range(8)]
st_all, st_off = par_dim("Dim alle", par_fids), par_dim("Dim aus", [])
st_odd = par_dim("Dim ungerade", [par_fids[i] for i in range(0, 8, 2)])
st_even = par_dim("Dim gerade", [par_fids[i] for i in range(1, 8, 2)])
st_l, st_r = par_dim("Dim links", par_fids[:4]), par_dim("Dim rechts", par_fids[4:])
st_b = [par_dim(f"Build {i+1}", par_fids[:i + 1]) for i in range(8)]

dim_run = chaser("Lauflicht", [s.id for s in st], hold=BEAT, fade=0.05)
dim_ping = chaser("Ping-Pong", [s.id for s in st] + [s.id for s in st[-2:0:-1]], hold=BEAT / 2, fade=0.03)
dim_pairs = chaser("2er-Chase", [st_odd.id, st_even.id], hold=BEAT, fade=0.06)
dim_sides = chaser("L-R-Chase", [st_l.id, st_r.id], hold=BAR / 2, fade=0.1)
dim_strobe = chaser("Strobe", [st_all.id, st_off.id], hold=0.045)
dim_build = chaser("Build-Up", [s.id for s in st_b] + [st_off.id], hold=BEAT, fade=0.04)
dim_pulse = fm.new_carousel("Pulse"); dim_pulse.pattern = CarouselPattern.PULSE
dim_pulse.fixture_ids = list(par_fids); dim_pulse.speed = 1.0
dim_wave = fm.new_carousel("Wave"); dim_wave.pattern = CarouselPattern.WAVE
dim_wave.fixture_ids = list(par_fids); dim_wave.speed = 1.0

lk = [par_look("Rot", r=255), par_look("Grün", g=255), par_look("Blau", b=255),
      par_look("Amber", r=255, g=140), par_look("Cyan", g=255, b=255), par_look("Magenta", r=255, b=255),
      par_look("Warmweiß", r=255, g=130, b=40, w=60), par_look("Weiß", r=255, g=255, b=255, w=255)]
look_warm, look_white = lk[6], lk[7]
ch_color = chaser("Color-Chase", [c.id for c in lk[:6]], hold=BAR / 2, fade=BEAT)

# Alle 16 RGB-Matrix-Algorithmen.
MTX_SPECS = [
    ("Mtx Regenbogen", RgbAlgorithm.RAINBOW, 1.5), ("Mtx Feuer", RgbAlgorithm.FIRE, 2.0),
    ("Mtx Plasma", RgbAlgorithm.SINEPLASMA, 1.2), ("Mtx Regen", RgbAlgorithm.RAIN, 1.6),
    ("Mtx Pinwheel", RgbAlgorithm.PINWHEEL, 1.4), ("Mtx Atem", RgbAlgorithm.BREATHE, 1.0),
    ("Mtx Spirale", RgbAlgorithm.SPIRAL, 1.5), ("Mtx Radar", RgbAlgorithm.RADAR, 1.5),
    ("Mtx Wipe", RgbAlgorithm.WIPE, 2.0), ("Mtx Welle", RgbAlgorithm.WAVE, 1.8),
    ("Mtx Gradient", RgbAlgorithm.GRADIENT, 1.2), ("Mtx Color-Fade", RgbAlgorithm.COLORFADE, 1.0),
    ("Mtx Chase", RgbAlgorithm.CHASE, 3.0), ("Mtx Fill", RgbAlgorithm.FILL, 2.0),
    ("Mtx Strobe", RgbAlgorithm.STROBE, 6.0), ("Mtx Zufall", RgbAlgorithm.RANDOM, 2.0),
]
mtx = [matrix(nm, algo, speed=sp) for nm, algo, sp in MTX_SPECS]
by_name = {f.name: f for f in fm.all()}

# Alle EFX-Formen für die Moving Heads.
EFX_SPECS = [
    ("MH Kreis", EfxAlgorithm.CIRCLE), ("MH Acht", EfxAlgorithm.EIGHT),
    ("MH Dreieck", EfxAlgorithm.TRIANGLE), ("MH Zufall", EfxAlgorithm.RANDOM),
    ("MH Linie", EfxAlgorithm.LINE), ("MH Raute", EfxAlgorithm.DIAMOND),
    ("MH Quadrat", EfxAlgorithm.SQUARE), ("MH Lissajous", EfxAlgorithm.LISSAJOUS),
]
efx = [mh_efx(nm, algo) for nm, algo in EFX_SPECS]
efx_rel = mh_efx("MH Acht relativ", EfxAlgorithm.EIGHT, relative=True)

# LIVE-Bank Effekt-Mix (16 Pads): 8 Dimmer/Beat + 8 Matrix.
LIVE_FX = [dim_run, dim_ping, dim_pairs, dim_sides, dim_build, dim_pulse, dim_wave, ch_color,
           by_name["Mtx Regenbogen"], by_name["Mtx Feuer"], by_name["Mtx Plasma"], by_name["Mtx Chase"],
           by_name["Mtx Strobe"], by_name["Mtx Wipe"], by_name["Mtx Welle"], by_name["Mtx Atem"]]
COLOR_FX_IDS = {ch_color.id} | {m.id for m in mtx}


# ════════════════════════════════════════════════════════════════════════════════
#  3) PLAYBACKS — BPM-getaktete Cuelisten auf Executoren (Bank 4 + Playback-Tab)
# ════════════════════════════════════════════════════════════════════════════════
def par_vals(r, g, b, w=0, inten=255):
    out = {}
    for fid in par_fids:
        cm = chan_of[fid]; v = {}
        if "intensity" in cm:
            v["intensity"] = inten
        for a, val in (("color_r", r), ("color_g", g), ("color_b", b), ("color_w", w)):
            if a in cm:
                v[a] = val
        out[fid] = v
    return out


def mh_vals(pan, tilt, inten=255):
    out = {}
    for fid in mh_fids:
        cm = chan_of[fid]; v = {}
        if "pan" in cm:
            v["pan"] = pan
        if "tilt" in cm:
            v["tilt"] = tilt
        if "intensity" in cm:
            v["intensity"] = inten
        if "shutter" in cm:
            v["shutter"] = SHUT_OPEN
        out[fid] = v
    return out


def merge(*dicts):
    res: dict[int, dict] = {}
    for d in dicts:
        for fid, v in d.items():
            res.setdefault(fid, {}).update(v)
    return res


# Playback 1 — Warmup: ruhige Farbstimmungen, Loop mit Auto-Follow (langsames Atmen).
pb_warm = state.new_cue_stack("Warmup")
pb_warm.mode = "loop"
for num, lbl, (r, g, b) in [
    (1.0, "Bernstein", (255, 140, 0)), (2.0, "Magenta", (255, 0, 150)),
    (3.0, "Cyan", (0, 200, 220)), (4.0, "Tiefblau", (0, 40, 255)),
]:
    pb_warm.add_cue(Cue(number=num, label=lbl, fade_in=PHRASE, follow=PHRASE * 1.5,
                        values=par_vals(r, g, b, inten=180)))

# Playback 2 — Drop/Peak: einmal GO, läuft per Auto-Follow durch (Build → Peak → Bursts).
pb_drop = state.new_cue_stack("Drop/Peak")
pb_drop.mode = "single"
for num, lbl, vals, fin, fol in [
    (1.0, "Build",   merge(par_vals(0, 30, 255, inten=120), mh_vals(110, 90, 120)),   BAR, BAR),
    (2.0, "Peak",    merge(par_vals(255, 255, 255, 255),    mh_vals(40, 200, 255)),   0.05, BEAT),
    (3.0, "Burst 1", merge(par_vals(255, 0, 180),           mh_vals(200, 60, 255)),   0.05, BEAT),
    (4.0, "Burst 2", merge(par_vals(0, 255, 120),           mh_vals(60, 200, 255)),   0.05, BEAT),
    (5.0, "Halten",  merge(par_vals(255, 0, 0),             mh_vals(128, 128, 255)),  BEAT, None),
]:
    pb_drop.add_cue(Cue(number=num, label=lbl, fade_in=fin, follow=fol, values=vals))

# Playback 3 — Hands-Up: schneller Farb-Chase auf dem Beat, Bounce + Auto-Follow.
pb_hands = state.new_cue_stack("Hands-Up")
pb_hands.mode = "bounce"
for num, lbl, (r, g, b) in [
    (1.0, "Rot", (255, 0, 0)), (2.0, "Gelb", (255, 200, 0)),
    (3.0, "Cyan", (0, 255, 230)), (4.0, "Magenta", (255, 0, 200)),
]:
    pb_hands.add_cue(Cue(number=num, label=lbl, fade_in=0.04, follow=BEAT, values=par_vals(r, g, b)))

# Playback 4 — MH-Sweep: Moving-Head-Fahrt über die Phrase, Bounce + Auto-Follow.
pb_mh = state.new_cue_stack("MH-Sweep")
pb_mh.mode = "bounce"
_amber = par_vals(255, 120, 0, inten=120)
for num, lbl, (pan, tilt) in [
    (1.0, "Mitte", (128, 128)), (2.0, "Links unten", (50, 210)),
    (3.0, "Rechts oben", (210, 50)), (4.0, "Weit", (230, 230)),
]:
    pb_mh.add_cue(Cue(number=num, label=lbl, fade_in=BAR, follow=BAR,
                      values=merge(_amber, mh_vals(pan, tilt))))

PLAYBACKS = [pb_warm, pb_drop, pb_hands, pb_mh]
PB_PAGE = 3   # Bank 4 (0-basiert) — Bank-Index == Playback-Seite (gekoppelt)
pe = state.playback_engine
for slot, pb in enumerate(PLAYBACKS, start=1):
    ex = pe.get_executor(slot, page=PB_PAGE)
    ex.stack = pb
    ex.label = pb.name
    ex.fader_function = "volume"


# ════════════════════════════════════════════════════════════════════════════════
#  4) VIRTUAL CONSOLE
# ════════════════════════════════════════════════════════════════════════════════
PAD, GAP, X0, Y0 = 60, 6, 20, 70
STEP = PAD + GAP
GRID_BOTTOM = Y0 + 8 * STEP
TY = GRID_BOTTOM + 4
Y_FAD = GRID_BOTTOM + 34
FAD_H = 142
RIGHT_X = X0 + 8 * STEP + 16
widgets: list[dict] = []
BANK_ALL = -1
B_LIVE, B_MTX, B_MH, B_PLAY, B_MUSIC = range(5)
PAGE_NAMES = ["LIVE/Party", "Matrix-Looks", "Moving Heads", "Playback", "Musik"]


def note_rc(r, c):
    """APC-Note für visuelle Position (Zeile 0 = oben, Spalte 0 = links)."""
    return (7 - r) * 8 + c


def pad_pos(note):
    row, col = note // 8, note % 8
    return X0 + col * STEP, Y0 + (7 - row) * STEP


def slot_note(s):
    return note_rc(s // 8, s % 8)


def _add(w, x, y, ww, hh, bank):
    w.bank = bank; w.setGeometry(x, y, ww, hh); widgets.append(w.to_dict())


def func_btn(fn, note, bank, accent, exclusive=False, clear_prog=False, style="pulse"):
    b = VCButton(fn.name)
    b.action = ButtonAction.FUNCTION_TOGGLE; b.function_id = fn.id; b.pad_style = style
    b.exclusive = exclusive; b.clear_programmer = clear_prog
    b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, note
    b._bg_color.setNamedColor(accent)
    x, y = pad_pos(note); _add(b, x, y, PAD, PAD, bank)


def func_flash(fn, note, bank, accent):
    b = VCButton(fn.name); b.action = ButtonAction.FUNCTION_FLASH
    b.function_id = fn.id; b.pad_style = "solid"
    b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, note
    b._bg_color.setNamedColor(accent)
    x, y = pad_pos(note); _add(b, x, y, PAD, PAD, bank)


def action_btn(name, action, note, bank, accent):
    b = VCButton(name); b.action = action; b.pad_style = "solid"
    b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, note
    b._bg_color.setNamedColor(accent)
    x, y = pad_pos(note); _add(b, x, y, PAD, PAD, bank)


def effect_action_btn(name, note, bank, accent, key, function_id):
    b = VCButton(name); b.action = ButtonAction.EFFECT_ACTION; b.effect_action_key = key
    b.function_id = function_id; b.pad_style = "solid"
    b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, note
    b._bg_color.setNamedColor(accent)
    x, y = pad_pos(note); _add(b, x, y, PAD, PAD, bank)


def select_group_btn(name, group, note, bank, accent="#2a4a6a"):
    b = VCButton(name); b.action = ButtonAction.SELECT_GROUP; b.group_name = group
    b.pad_style = "solid"
    b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, note
    b._bg_color.setNamedColor(accent)
    x, y = pad_pos(note); _add(b, x, y, PAD, PAD, bank)


def exec_go_btn(name, slot, note, bank, accent="#0d4f8b"):
    b = VCButton(name); b.action = ButtonAction.TOGGLE; b.function_id = slot
    b.pad_style = "solid"
    b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, note
    b._bg_color.setNamedColor(accent)
    x, y = pad_pos(note); _add(b, x, y, PAD, PAD, bank)


def exec_flash_btn(name, slot, note, bank, accent="#3a2150"):
    b = VCButton(name); b.action = ButtonAction.FLASH; b.function_id = slot
    b.pad_style = "solid"
    b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, note
    b._bg_color.setNamedColor(accent)
    x, y = pad_pos(note); _add(b, x, y, PAD, PAD, bank)


def color_tile(name, note, bank, r, g, b, w=0, target=ColorTarget.PROGRAMMER,
               function_id=None, with_intensity=True):
    c = VCColor(name); c.color_r, c.color_g, c.color_b, c.color_w = r, g, b, w
    c.with_intensity = with_intensity; c.target = target; c.function_id = function_id
    c.midi_type, c.midi_ch, c.midi_data1 = "note_on", 0, note
    x, y = pad_pos(note); _add(c, x, y, PAD, PAD, bank)


def fader(caption, col, bank, mode, function_ids=None, programmer_attr="intensity",
          programmer_scope="all", programmer_group="", param_key="speed",
          midi_cc=-1, value=0, submaster_slot=None, function_id=None):
    from src.ui.virtualconsole.vc_slider import VCSlider, SliderMode  # noqa: F401
    s = VCSlider(caption); s.mode = mode; s.function_id = function_id
    s.function_ids = list(function_ids or [])
    if submaster_slot is not None:
        s.function_id = submaster_slot
    s.programmer_attr = programmer_attr; s.programmer_scope = programmer_scope
    s.programmer_group = programmer_group; s.param_key = param_key
    s.midi_cc, s.midi_ch = midi_cc, 0; s._value = value
    x = X0 + col * STEP + 2; _add(s, x, Y_FAD, 56, FAD_H, bank)


def pb_fader(caption, col, bank, slot, midi_cc, value=255):
    from src.ui.virtualconsole.vc_slider import VCSlider, SliderMode
    s = VCSlider(caption); s.mode = SliderMode.PLAYBACK; s.function_id = slot
    s.midi_cc, s.midi_ch = midi_cc, 0; s._value = value
    x = X0 + col * STEP + 2; _add(s, x, Y_FAD, 56, FAD_H, bank)


def label(text, x, y, ww, bank, hh=18):
    _add(VCLabel(text), x, y, ww, hh, bank)


from src.ui.virtualconsole.vc_slider import SliderMode

# ── Universell (BANK_ALL) — Track-Tasten + Master-Fader + Kopf-Labels ──
for i, (nm, act, col) in enumerate([
        ("Clear", ButtonAction.CLEAR, "#4a3a10"), ("Stop All", ButtonAction.STOP_ALL, "#4a1010"),
        ("Blackout", ButtonAction.BLACKOUT, "#2a0000"), ("Tap", ButtonAction.TAP, "#103a3a")]):
    b = VCButton(nm); b.action = act; b.pad_style = "solid"
    b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, 100 + i
    b._bg_color.setNamedColor(col)
    _add(b, X0 + i * 64, TY, 60, 26, BANK_ALL)
fader("Dimmer", 5, BANK_ALL, SliderMode.SUBMASTER, submaster_slot=0, midi_cc=53, value=255)
fader("Speed", 6, BANK_ALL, SliderMode.SPEED, midi_cc=54, value=64)
fader("Master", 8, BANK_ALL, SliderMode.GRANDMASTER, midi_cc=56, value=255)
label("PARTY DEMO 2026  —  8 PAR + 2 MH + APC mini.  ~150 BPM.  Track unten: Clear/Stop/Blackout/Tap.  "
      "Genaue BPM via VirtualDJ→OS2L (Menü Ausgabe).", X0, 6, 1200, BANK_ALL)
label("SCENE-Tasten = Bank 1-5 (= Playback-Seite):  1 LIVE/Party · 2 Matrix-Looks · 3 Moving Heads · "
      "4 Playback · 5 Musik", X0, Y_FAD + FAD_H + 6, 1100, BANK_ALL)


# ── BANK 1 — LIVE/PARTY ──────────────────────────────────────────────────────────
COLORS16 = [
    ("Rot", 255, 0, 0, 0), ("Orange", 255, 90, 0, 0), ("Amber", 255, 160, 0, 0), ("Gelb", 255, 220, 0, 0),
    ("Limette", 160, 255, 0, 0), ("Grün", 0, 255, 0, 0), ("Türkis", 0, 230, 150, 0), ("Cyan", 0, 255, 255, 0),
    ("Hellblau", 0, 140, 255, 0), ("Blau", 0, 0, 255, 0), ("Violett", 140, 0, 255, 0), ("Magenta", 255, 0, 255, 0),
    ("Pink", 255, 0, 120, 0), ("Warmweiß", 255, 130, 40, 60), ("Weiß", 255, 255, 255, 255), ("Aus", 0, 0, 0, 0),
]
for i, (nm, r, g, b, w) in enumerate(COLORS16):     # Reihen 0-1 = 16 Farben (Programmer)
    color_tile(nm, note_rc(i // 8, i % 8), B_LIVE, r, g, b, w)
for i, fn in enumerate(LIVE_FX):                    # Reihen 2-3 = 16 Beat-Effekte
    is_color = fn.id in COLOR_FX_IDS
    accent = "#7a5b00" if fn.name.startswith("Mtx") else "#1f4a28"
    func_btn(fn, note_rc(2 + i // 8, i % 8), B_LIVE, accent, exclusive=True, clear_prog=is_color)
for i, e in enumerate(efx):                          # Reihe 4 = 8 MH-Formen (layern)
    func_btn(e, note_rc(4, i), B_LIVE, "#1f3a6a", exclusive=False)
for i, sc in enumerate(lk):                          # Reihe 5 = 8 Looks (Szenen)
    func_btn(sc, note_rc(5, i), B_LIVE, "#222222", exclusive=False, style="solid")
GROUPS5 = [("Alle", "Alle"), ("PARs", "PAR-Reihe"), ("PAR L", "PAR Links"),
           ("PAR R", "PAR Rechts"), ("MH", "Moving Heads")]
for i, (nm, grp) in enumerate(GROUPS5):             # Reihe 6 = Gruppen-Auswahl + Flashes
    select_group_btn(nm, grp, note_rc(6, i), B_LIVE)
func_flash(dim_strobe, note_rc(6, 5), B_LIVE, "#551111")
func_flash(look_white, note_rc(6, 6), B_LIVE, "#555555")
func_flash(look_warm, note_rc(6, 7), B_LIVE, "#553010")
action_btn("Clear", ButtonAction.CLEAR, note_rc(7, 0), B_LIVE, "#4a3a10")   # Reihe 7 = Track
action_btn("Stop All", ButtonAction.STOP_ALL, note_rc(7, 1), B_LIVE, "#4a1010")
action_btn("Blackout", ButtonAction.BLACKOUT, note_rc(7, 2), B_LIVE, "#2a0000")
action_btn("Tap", ButtonAction.TAP, note_rc(7, 3), B_LIVE, "#103a3a")
action_btn("Musik-BPM", ButtonAction.AUDIO_BPM, note_rc(7, 4), B_LIVE, "#103a4a")
action_btn("◄ Lied", ButtonAction.MEDIA_PREV, note_rc(7, 5), B_LIVE, "#3a2150")
action_btn("Play/Pause", ButtonAction.MEDIA_PLAY_PAUSE, note_rc(7, 6), B_LIVE, "#4a2060")
action_btn("Lied ►", ButtonAction.MEDIA_NEXT, note_rc(7, 7), B_LIVE, "#3a2150")
fader("FX-Speed", 0, B_LIVE, SliderMode.EFFECT_SPEED, midi_cc=48, value=80)
fader("FX-Master", 1, B_LIVE, SliderMode.EFFECT_INTENSITY, midi_cc=49, value=255)
fader("FX-Param", 2, B_LIVE, SliderMode.EFFECT_PARAM, param_key="white_amount", midi_cc=50, value=0)
fader("PAR-Dim", 3, B_LIVE, SliderMode.GROUP_DIMMER, programmer_group="PAR-Reihe", midi_cc=51, value=255)
fader("MH-Dim", 4, B_LIVE, SliderMode.GROUP_DIMMER, programmer_group="Moving Heads", midi_cc=52, value=255)
label("BANK 1  LIVE/PARTY  —  R1-2 Farben · R3-4 Beat-Effekte (exklusiv) · R5 MH-Formen (layern) · "
      "R6 Looks · R7 Gruppen+Flash · R8 Track+Musik.  Gelayerte PAR+MH-Looks: Bank 4 Playbacks.",
      X0, 28, 1200, B_LIVE)


# ── BANK 2 — MATRIX-LOOKS (alle 16 Algorithmen auf 8 PARs) ──────────────────────
for i, m in enumerate(mtx):
    func_btn(m, slot_note(i), B_MTX, "#7a5b00", exclusive=True, clear_prog=True)
fader("FX-Speed", 0, B_MTX, SliderMode.EFFECT_SPEED, midi_cc=48, value=80)
fader("FX-Master", 1, B_MTX, SliderMode.EFFECT_INTENSITY, midi_cc=49, value=255)
fader("PAR-Dim", 3, B_MTX, SliderMode.GROUP_DIMMER, programmer_group="PAR-Reihe", midi_cc=51, value=255)
label("BANK 2  MATRIX-LOOKS  —  alle 16 RGB-Matrix-Algorithmen auf den 8 PARs, exklusiv. "
      "FX-Speed/FX-Master wirken auf den laufenden Look.", X0, 28, 1100, B_MTX)


# ── BANK 3 — MOVING HEADS ───────────────────────────────────────────────────────
xy_pos = VCXYPad("MH zielen"); xy_pos.mode = "position"; xy_pos._fixture_ids = list(mh_fids)
xy_pos.bits16 = True
_add(xy_pos, X0, Y0, 224, 224, B_MH)
for i, e in enumerate(efx):
    func_btn(e, note_rc(0, 4 + i % 4) if i < 4 else note_rc(1, 4 + (i - 4)), B_MH, "#1f3a6a", exclusive=True)
effect_action_btn("Relativ", note_rc(2, 4), B_MH, "#7a6500", "toggle_relative", efx_rel.id)
effect_action_btn("Neustart", note_rc(2, 5), B_MH, "#553010", "restart", None)
effect_action_btn("Spiegeln", note_rc(2, 6), B_MH, "#334455", "toggle_mirror", None)
func_btn(efx_rel, note_rc(2, 7), B_MH, "#1f6a4a", exclusive=False)
fader("EFX-Speed", 0, B_MH, SliderMode.EFFECT_SPEED, midi_cc=48, value=80)
fader("EFX-Größe", 1, B_MH, SliderMode.EFFECT_PARAM, param_key="size", midi_cc=49, value=110)
fader("MH-Dim", 3, B_MH, SliderMode.GROUP_DIMMER, programmer_group="Moving Heads", midi_cc=51, value=255)
label("BANK 3  MOVING HEADS  —  LINKS zielen (16-bit XY).  Rechts: 8 EFX-Formen (Kreis/Acht/Dreieck/"
      "Zufall/Linie/Raute/Quadrat/Lissajous), 'Relativ'/'Spiegeln'/'Neustart'.", X0, 28, 1150, B_MH)


# ── BANK 4 — PLAYBACK (4 Cuelisten) ─────────────────────────────────────────────
for i, pb in enumerate(PLAYBACKS):
    cl = VCCueList(pb.name); cl.stack_slot = i
    _add(cl, X0 + i * 250, Y0, 240, 196, B_PLAY)
PB_ACCENT = ["#1f4a28", "#8b0d4f", "#0d4f8b", "#7a5b00"]
for i, pb in enumerate(PLAYBACKS):
    exec_go_btn(f"GO {pb.name[:7]}", i, note_rc(4, i), B_PLAY, PB_ACCENT[i])
    exec_flash_btn(f"Flash {i+1}", i, note_rc(5, i), B_PLAY, "#333355")
sd = VCSpeedDial("Drop-Rate"); sd.target_mode = SpeedTarget.EXECUTOR
sd.function_id = 1; sd.multiplier_mode = True
_add(sd, X0 + 5 * STEP, pad_pos(note_rc(4, 5))[1], 150, 110, B_PLAY)
for i, pb in enumerate(PLAYBACKS):
    pb_fader(f"Dim {i+1}", i, B_PLAY, slot=i, midi_cc=48 + i, value=255)
label("BANK 4  PLAYBACK  —  4 BPM-getaktete Playbacks: Warmup(Loop) · Drop/Peak(einmal GO, Auto-Follow) · "
      "Hands-Up(Bounce, Beat) · MH-Sweep(Bounce).  Pads R5=GO, R6=Flash, Fader F1-F4=Dimmer.",
      X0, 28, 1200, B_PLAY)


# ── BANK 5 — MUSIK ──────────────────────────────────────────────────────────────
song = VCSongInfo("Aktuelles Lied")
_add(song, X0, Y0, 4 * STEP - 6, 2 * STEP - 6, B_MUSIC)            # R1-2, Spalten 0-3
for i, (nm, r, g, b, w) in enumerate(COLORS16[:8]):                 # R1-2, Spalten 4-7
    color_tile(nm, note_rc(i // 4, 4 + i % 4), B_MUSIC, r, g, b, w)
for i, sc in enumerate(lk):                                         # R3 = Looks
    func_btn(sc, note_rc(2, i), B_MUSIC, "#222222", exclusive=False, style="solid")
# R4 = große Media-Transport-Reihe.
action_btn("◄◄ Lied", ButtonAction.MEDIA_PREV, note_rc(3, 0), B_MUSIC, "#3a2150")
action_btn("► / ❚❚", ButtonAction.MEDIA_PLAY_PAUSE, note_rc(3, 1), B_MUSIC, "#4a2060")
action_btn("Lied ►►", ButtonAction.MEDIA_NEXT, note_rc(3, 2), B_MUSIC, "#3a2150")
action_btn("Musik-BPM", ButtonAction.AUDIO_BPM, note_rc(3, 3), B_MUSIC, "#103a4a")
action_btn("Tap", ButtonAction.TAP, note_rc(3, 4), B_MUSIC, "#103a3a")
action_btn("Clear", ButtonAction.CLEAR, note_rc(3, 5), B_MUSIC, "#4a3a10")
action_btn("Blackout", ButtonAction.BLACKOUT, note_rc(3, 6), B_MUSIC, "#2a0000")
func_flash(dim_strobe, note_rc(3, 7), B_MUSIC, "#551111")
fader("PAR-Dim", 3, B_MUSIC, SliderMode.GROUP_DIMMER, programmer_group="PAR-Reihe", midi_cc=51, value=255)
fader("MH-Dim", 4, B_MUSIC, SliderMode.GROUP_DIMMER, programmer_group="Moving Heads", midi_cc=52, value=255)
label("BANK 5  MUSIK  —  Anzeige aktuelles/nächstes Lied.  R4: ◄◄ ►/❚❚ ►► steuern den In-App-Player "
      "(auch im Tab 'Musik').  Genaue BPM: VirtualDJ → OS2L starten (Menü Ausgabe).",
      X0, 28, 1200, B_MUSIC)
label("Playlist (in der Show gespeichert) — Doppelklick im Musik-Tab spielt ab; ►/❚❚ hier startet/pausiert.",
      X0, 48, 1200, B_MUSIC)


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
#  5) Speichern + Verifikation
# ════════════════════════════════════════════════════════════════════════════════
state.programmer = {}
state.show_name = "Party Demo 2026"
save_show(OUT)
print(f"Gespeichert: {OUT}")
ok, msg = load_show(OUT)
print("Load:", ok, msg)
assert ok, f"Show laedt nicht: {msg}"
state = get_state()
assert len(state.get_patched_fixtures()) == 10, len(state.get_patched_fixtures())

from collections import Counter
vc = state._vc_layout.get("widgets", [])
banks = Counter(w.get("bank") for w in vc)
assert set(banks) == {0, 1, 2, 3, 4, -1}, f"Banks: {sorted(banks)}"
types = Counter(w["type"] for w in vc)

# Playlist erhalten?
assert len(state.playlist) == 10, f"Playlist: {len(state.playlist)}"
assert all(t.get("path") and t.get("bpm", 0) > 0 for t in state.playlist), state.playlist
# MediaPlayer aus der geladenen Show gefüllt?
from src.core.audio.media_player import get_media_player
assert len(get_media_player().tracks) == 10, len(get_media_player().tracks)

# Playbacks erhalten + an Executoren gebunden?
assert len(state.cue_stacks) == 4, f"Cue-Stacks: {len(state.cue_stacks)}"
names = {s.name for s in state.cue_stacks}
assert names == {"Warmup", "Drop/Peak", "Hands-Up", "MH-Sweep"}, names
by = {s.name: s for s in state.cue_stacks}
assert by["Drop/Peak"].mode == "single" and len(by["Drop/Peak"].cues) == 5
assert by["Warmup"].mode == "loop" and by["Hands-Up"].mode == "bounce" and by["MH-Sweep"].mode == "bounce"
pe2 = state.playback_engine
bound = [pe2.get_executor(s, page=PB_PAGE).stack for s in (1, 2, 3, 4)]
assert all(b is not None for b in bound), f"Executoren ungebunden: {bound}"
assert {b.name for b in bound} == names, [b.name for b in bound]

# VC-Fenster-Widgets vorhanden?
assert types.get("VCSongInfo", 0) == 1, f"VCSongInfo: {types.get('VCSongInfo')}"
assert types.get("VCCueList", 0) == 4, f"VCCueList: {types.get('VCCueList')}"
assert types.get("VCXYPad", 0) == 1, f"VCXYPad: {types.get('VCXYPad')}"
assert types.get("VCSpeedDial", 0) == 1, "VCSpeedDial fehlt"
# Media-Transport-Pads vorhanden (LIVE + MUSIK)?
media_pads = [w for w in vc if w.get("action") in ("MediaPlayPause", "MediaNext", "MediaPrev")]
assert len(media_pads) == 6, f"Media-Pads: {len(media_pads)}"
# 16 Programmer-Farben in LIVE
prog_colors = [w for w in vc if w.get("bank") == B_LIVE and w.get("type") == "VCColor"
               and w.get("target") == ColorTarget.PROGRAMMER]
assert len(prog_colors) == 16, f"LIVE-Farben: {len(prog_colors)}"
# 16 Matrix-Looks in Bank 2
mtx_pads = [w for w in vc if w.get("bank") == B_MTX and w.get("action") == "FunctionToggle"
            and w.get("exclusive")]
assert len(mtx_pads) == 16, f"Matrix-Looks: {len(mtx_pads)}"
# GO-Pads (4)
go_pads = [w for w in vc if w.get("bank") == B_PLAY and w.get("action") == "Toggle"]
assert len(go_pads) == 4, f"GO-Pads: {len(go_pads)}"
maxy = max((w.get("y", 0) + w.get("h", 0)) for w in vc)
assert maxy < 820, f"zu hoch: {maxy}"

# Keine Überlappung interaktiver Widgets je Bank (Bank-Layer + BANK_ALL).
_INTER = {"VCButton", "VCSlider", "VCColor", "VCXYPad", "VCCueList",
          "VCColorList", "VCSpeedDial", "VCSongInfo"}


def _rect(w):
    return (w.get("x", 0), w.get("y", 0), w.get("x", 0) + w.get("w", 0), w.get("y", 0) + w.get("h", 0))


def _overlap(a, b):
    ax0, ay0, ax1, ay1 = _rect(a); bx0, by0, bx1, by1 = _rect(b)
    return not (ax1 <= bx0 or bx1 <= ax0 or ay1 <= by0 or by1 <= ay0)


for bk in (0, 1, 2, 3, 4):
    layer = [w for w in vc if w.get("bank") in (bk, -1) and w["type"] in _INTER]
    for a in range(len(layer)):
        for b in range(a + 1, len(layer)):
            assert not _overlap(layer[a], layer[b]), (
                f"Overlap Bank {bk}: {layer[a]['type']}@{_rect(layer[a])} "
                f"vs {layer[b]['type']}@{_rect(layer[b])}")

print(f"Funktionen: {len(get_function_manager().all())}  VC-Widgets: {len(vc)}  Typen={dict(types)}")
print(f"Banks: {dict(sorted(banks.items()))}  Max-Y={maxy}")
print(f"  Playlist={len(state.playlist)}  Playbacks={len(state.cue_stacks)} {sorted(names)}  "
      f"LIVE-Farben={len(prog_colors)}  Matrix-Looks={len(mtx_pads)}  Media-Pads={len(media_pads)}  GO={len(go_pads)}")
print("  Playlist-Arc:")
for t in state.playlist:
    print(f"    {t['bpm']:>5.0f} BPM  [{t['genre']:<11}] {t['title']}")
print("  [OK] 5 Banks · APC mini · 8 PAR + 2 MH · BPM-getaktet · Musik-Playlist + VCSongInfo")
print("FERTIG")
