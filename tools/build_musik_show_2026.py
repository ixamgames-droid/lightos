"""MUSIK SHOW 2026 — Auto-Lichtshow, die zur Musik im BPM-Takt mitläuft.

Davids reales Setup: Akai APC mini + 8× RGBW-PAR (ZQ01424, 8ch) + 2× Moving Head
(ZQ02001, 11ch). Passend zu seiner Party-Musik (Ordner „BP Party").

Das Besondere gegenüber Party_Demo_2026: die Show **läuft automatisch zur Musik**.
Drückst du im In-App-Player (oder am Bank-1-Play-Pad) auf ▶, startet der
MusicShowDirector die Auto-Show (``state.music_autoshow``) — beat-getriggerte
Effekte, die mit dem Live-BPM (VirtualDJ→OS2L / Tap / Audio, sonst Nominal-Fallback)
weiterschalten. Pause/Stop stoppt sie wieder.

Banks (APC-SCENE = Bank/Seite, gekoppelt an die Playback-Seite):
  Bank 1  AUTO-SHOW    Songanzeige + Transport; PAR-Sektionen (Warmup/Build/Drop/
                       Chill, beat-getriggert) + MH-Formen; Gruppen/Flashes.
                       Beim Play läuft Drop+MH-Orbit automatisch, taktgenau.
  Bank 2  STANDARD     16 anpassbare Farb-Kacheln + Standard-Matrix-Looks + Chases/
                       Color-Chases + volle Fader (Speed/Intensity/Param/Dim).
  Bank 3  MEINE SHOWS  4 gespeicherte Cuelisten an Executoren (GO/Flash); 2 davon
                       mit Beat-Sync → laufen taktgenau zur Musik.
  Bank 4  MH-STAGE     XY-Pad zum Anvisieren; Orbits auf Bühnen-Zonen (Mitte/Links/
                       Rechts/Publikum/Hoch) + relative Formen; Spiegeln/Gegenläufig.
  Bank 5  MUSIK        Player-Transport + Songanzeige; Auto-Show-Schalter im Tab „Musik".

Aufruf:  venv/Scripts/python.exe tools/build_musik_show_2026.py
Erzeugt: shows/Musik_Show_2026.lshow
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
from src.ui.virtualconsole.vc_slider import VCSlider, SliderMode

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(_ROOT, "shows", "Musik_Show_2026.lshow")
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
CURATED = [
    ("mr. brightside",     "Bounce",   150),
    ("pompeii",            None,       None),
    ("angels (jesse bloch", "Bounce",  150),
    ("major tom",          None,       None),
    ("i need a hero",      None,       None),
    ("vaskan hardstyle",   None,       None),
    ("gym hardstyle",      None,       None),
    ("africa (rayvolt",    None,       None),
    ("sweet about me",     None,       None),
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
    if p is None:
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
def par_dim(name, on_fids, inten=255):
    sc = fm.new_scene(name); on = set(on_fids)
    for fid in par_fids:
        if "intensity" in chan_of[fid]:
            sc.set_value(fid, chan_of[fid]["intensity"], inten if fid in on else 0)
    return sc


def par_look(name, r=0, g=0, b=0, w=0, inten=255):
    """Voll-Look: alle PARs eine Farbe."""
    sc = fm.new_scene(name)
    for fid in par_fids:
        cm = chan_of[fid]
        if "intensity" in cm:
            sc.set_value(fid, cm["intensity"], inten)
        for attr, val in (("color_r", r), ("color_g", g), ("color_b", b), ("color_w", w)):
            if attr in cm:
                sc.set_value(fid, cm[attr], val)
    return sc


def par_split(name, odd, even, inten=255):
    """Geteilter Look: ungerade PARs Farbe `odd`, gerade Farbe `even` (je RGBW-Tupel)."""
    sc = fm.new_scene(name)
    for i, fid in enumerate(par_fids):
        cm = chan_of[fid]
        r, g, b, w = odd if i % 2 == 0 else even
        if "intensity" in cm:
            sc.set_value(fid, cm["intensity"], inten)
        for attr, val in (("color_r", r), ("color_g", g), ("color_b", b), ("color_w", w)):
            if attr in cm:
                sc.set_value(fid, cm[attr], val)
    return sc


def chaser(name, step_ids, hold=BEAT, fade=0.0, speed=1.0,
           audio=False, beats_per_step=1, run_order=RunOrder.Loop):
    c = fm.new_chaser(name)
    c.run_order, c.direction, c.speed = run_order, Direction.Forward, speed
    c.audio_triggered = audio
    c.beats_per_step = beats_per_step
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


def mh_efx(name, algo, relative=False, spread=1.0, x=128.0, y=128.0, size=110.0, speed_hz=0.5):
    e = fm.new_efx(name); e.algorithm = algo
    e.fixtures = [EfxFixture(fid=mh_left), EfxFixture(fid=mh_right)]
    e.speed_hz = speed_hz; e.spread = spread; e.open_beam = True; e.relative = relative
    e.x_offset, e.y_offset = x, y
    e.width = e.height = size
    return e


def mh_aim(name, pan, tilt):
    """Szene, die beide Moving Heads auf eine Bühnen-Position richtet (offener Beam)."""
    sc = fm.new_scene(name)
    for fid in mh_fids:
        cm = chan_of[fid]
        for attr, val in (("pan", pan), ("tilt", tilt), ("intensity", 255), ("shutter", SHUT_OPEN)):
            if attr in cm:
                sc.set_value(fid, cm[attr], val)
    return sc


# ── Voll-Looks (für die Auto-Show-Chaser-Schritte) ───────────────────────────────
RED, ORANGE, GREEN, CYAN, BLUE, MAGENTA, AMBER, WHITE = (
    (255, 0, 0, 0), (255, 90, 0, 0), (0, 255, 0, 0), (0, 255, 255, 0),
    (0, 0, 255, 0), (255, 0, 255, 0), (255, 160, 0, 0), (255, 255, 255, 255))

look_red = par_look("Look Rot", *RED)
look_grn = par_look("Look Grün", *GREEN)
look_cyan = par_look("Look Cyan", *CYAN)
look_blue = par_look("Look Blau", *BLUE)
look_mag = par_look("Look Magenta", *MAGENTA)
look_amber = par_look("Look Amber", *AMBER)
look_white = par_look("Look Weiß", *WHITE)
look_warm = par_look("Look Warmweiß", 255, 130, 40, 60)
look_teal = par_look("Look Türkis", 0, 230, 150, 0)
look_deepblue = par_look("Look Tiefblau", 0, 40, 255, 0)
VIVID = [look_red, look_grn, look_cyan, look_blue, look_mag, look_amber, look_white, look_warm]
split_rb = par_split("Split Rot/Blau", RED, BLUE)
split_cm = par_split("Split Cyan/Magenta", CYAN, MAGENTA)
split_gw = par_split("Split Grün/Weiß", GREEN, WHITE)

# Build-Szenen (1..8 PARs an, weiß) für den Build-Up-Chaser.
build_steps = [par_dim(f"Build {i+1}", par_fids[:i + 1]) for i in range(8)]

# ── AUTO-SHOW-Sektionen — beat-getriggerte PAR-Chaser (folgen dem Live-BPM) ───────
par_drop = chaser("Drop (Beat)",
                  [look_red.id, split_rb.id, look_grn.id, split_cm.id,
                   look_amber.id, look_cyan.id, split_gw.id, look_white.id],
                  audio=True, beats_per_step=2, fade=0.04)            # halber Takt
par_warm = chaser("Warmup (Beat)",
                  [look_warm.id, look_amber.id, look_mag.id, look_deepblue.id],
                  audio=True, beats_per_step=8, fade=BEAT)            # alle 2 Takte
par_build = chaser("Build-Up (Beat)",
                   [s.id for s in build_steps] + [par_dim("Build aus", []).id],
                   audio=True, beats_per_step=1, fade=0.03)           # jeder Beat
par_chill = chaser("Chill (Beat)",
                   [look_deepblue.id, look_teal.id],
                   audio=True, beats_per_step=8, fade=BEAT)

# ── AUTO-SHOW MH — kontinuierliche EFX-Orbits (animieren selbst, eigenes Tempo) ───
mh_orbit = mh_efx("MH Orbit", EfxAlgorithm.CIRCLE, size=110.0, speed_hz=0.5)
mh_eight = mh_efx("MH Acht", EfxAlgorithm.EIGHT, size=120.0, speed_hz=0.45)
mh_wide = mh_efx("MH Weit", EfxAlgorithm.LINE, size=200.0, speed_hz=0.5)

# ── Standard-Effekte (Bank 2) ────────────────────────────────────────────────────
st = [par_dim(f"Dim P{i+1}", [par_fids[i]]) for i in range(8)]
st_odd = par_dim("Dim ungerade", [par_fids[i] for i in range(0, 8, 2)])
st_even = par_dim("Dim gerade", [par_fids[i] for i in range(1, 8, 2)])
st_l, st_r = par_dim("Dim links", par_fids[:4]), par_dim("Dim rechts", par_fids[4:])
st_all, st_off = par_dim("Dim alle", par_fids), par_dim("Dim aus", [])

ch_run = chaser("Lauflicht", [s.id for s in st], hold=BEAT, fade=0.05)
ch_ping = chaser("Ping-Pong", [s.id for s in st] + [s.id for s in st[-2:0:-1]], hold=BEAT / 2, fade=0.03)
ch_pairs = chaser("2er-Chase", [st_odd.id, st_even.id], hold=BEAT, fade=0.06)
ch_sides = chaser("L-R-Chase", [st_l.id, st_r.id], hold=BAR / 2, fade=0.1)
ch_strobe = chaser("Strobe", [st_all.id, st_off.id], hold=0.045)
ch_color = chaser("Color-Chase", [look_red.id, look_amber.id, look_grn.id,
                                   look_cyan.id, look_blue.id, look_mag.id], hold=BAR / 2, fade=BEAT)
ch_color2 = chaser("Pastell-Chase", [look_warm.id, look_teal.id, look_deepblue.id, look_white.id],
                   hold=BAR, fade=BAR / 2)

MTX_SPECS = [
    ("Mtx Regenbogen", RgbAlgorithm.RAINBOW, 1.5), ("Mtx Feuer", RgbAlgorithm.FIRE, 2.0),
    ("Mtx Plasma", RgbAlgorithm.SINEPLASMA, 1.2), ("Mtx Welle", RgbAlgorithm.WAVE, 1.8),
    ("Mtx Atem", RgbAlgorithm.BREATHE, 1.0), ("Mtx Color-Fade", RgbAlgorithm.COLORFADE, 1.0),
    ("Mtx Chase", RgbAlgorithm.CHASE, 3.0), ("Mtx Strobe", RgbAlgorithm.STROBE, 6.0),
]
mtx = [matrix(nm, algo, speed=sp) for nm, algo, sp in MTX_SPECS]

# ── MH Stage-Ausrichtung (Bank 4) ────────────────────────────────────────────────
# Orbits, deren Zentrum auf eine Bühnen-Zone zeigt (Bewegung passend zur Stage).
mh_zone_mitte = mh_efx("Orbit Mitte", EfxAlgorithm.CIRCLE, x=128, y=128, size=90)
mh_zone_links = mh_efx("Orbit Links", EfxAlgorithm.CIRCLE, x=60, y=120, size=80)
mh_zone_rechts = mh_efx("Orbit Rechts", EfxAlgorithm.CIRCLE, x=200, y=120, size=80)
mh_zone_pub = mh_efx("Orbit Publikum", EfxAlgorithm.EIGHT, x=128, y=205, size=90)
mh_zone_hoch = mh_efx("Orbit Hoch", EfxAlgorithm.CIRCLE, x=128, y=55, size=80)
mh_rel_circle = mh_efx("Kreis relativ", EfxAlgorithm.CIRCLE, relative=True, size=70)
mh_rel_eight = mh_efx("Acht relativ", EfxAlgorithm.EIGHT, relative=True, size=80)
AIMS = [mh_aim("Ziel Mitte", 128, 128), mh_aim("Ziel Links", 60, 120),
        mh_aim("Ziel Rechts", 200, 120), mh_aim("Ziel Publikum", 128, 205),
        mh_aim("Ziel Hoch", 128, 55)]


# ════════════════════════════════════════════════════════════════════════════════
#  3) PLAYBACKS — Bank 3: meine Shows (2 davon Beat-Sync → taktgenau zur Musik)
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


# PB 1 — Aufwärmen: ruhige Stimmungen, Zeit-Follow (Loop). (NICHT beat-sync — Vergleich)
pb_warm = state.new_cue_stack("Aufwärmen")
pb_warm.mode = "loop"
for num, lbl, (r, g, b) in [
    (1.0, "Bernstein", (255, 140, 0)), (2.0, "Magenta", (255, 0, 150)),
    (3.0, "Cyan", (0, 200, 220)), (4.0, "Tiefblau", (0, 40, 255)),
]:
    pb_warm.add_cue(Cue(number=num, label=lbl, fade_in=PHRASE, follow=PHRASE * 1.5,
                        values=par_vals(r, g, b, inten=180)))

# PB 2 — Drop-Sequenz: BEAT-SYNC, alle 4 Beats (1 Takt) eine Cue weiter (Loop).
pb_drop = state.new_cue_stack("Drop-Sequenz")
pb_drop.mode = "loop"
pb_drop.beat_sync = True
pb_drop.beats_per_cue = 4
for num, lbl, vals in [
    (1.0, "Build",  merge(par_vals(0, 30, 255, inten=160), mh_vals(110, 90))),
    (2.0, "Peak",   merge(par_vals(255, 255, 255, 255),    mh_vals(40, 200))),
    (3.0, "Burst 1", merge(par_vals(255, 0, 180),          mh_vals(200, 60))),
    (4.0, "Burst 2", merge(par_vals(0, 255, 120),          mh_vals(60, 200))),
]:
    pb_drop.add_cue(Cue(number=num, label=lbl, fade_in=0.05, follow=None, values=vals))

# PB 3 — Farb-Reise: BEAT-SYNC, alle 8 Beats (2 Takte) eine Cue weiter (Loop).
pb_color = state.new_cue_stack("Farb-Reise")
pb_color.mode = "loop"
pb_color.beat_sync = True
pb_color.beats_per_cue = 8
for num, lbl, (r, g, b) in [
    (1.0, "Rot", (255, 0, 0)), (2.0, "Gelb", (255, 200, 0)),
    (3.0, "Grün", (0, 255, 60)), (4.0, "Cyan", (0, 255, 230)),
    (5.0, "Blau", (0, 40, 255)), (6.0, "Magenta", (255, 0, 200)),
]:
    pb_color.add_cue(Cue(number=num, label=lbl, fade_in=BEAT, follow=None, values=par_vals(r, g, b)))

# PB 4 — MH-Fahrt: Moving-Head-Bewegung, Zeit-Follow (Bounce). (NICHT beat-sync)
pb_mh = state.new_cue_stack("MH-Fahrt")
pb_mh.mode = "bounce"
_amber = par_vals(255, 120, 0, inten=120)
for num, lbl, (pan, tilt) in [
    (1.0, "Mitte", (128, 128)), (2.0, "Links unten", (50, 210)),
    (3.0, "Rechts oben", (210, 50)), (4.0, "Weit", (230, 230)),
]:
    pb_mh.add_cue(Cue(number=num, label=lbl, fade_in=BAR, follow=BAR,
                      values=merge(_amber, mh_vals(pan, tilt))))

PLAYBACKS = [pb_warm, pb_drop, pb_color, pb_mh]
PB_PAGE = 2   # Bank 3 (0-basiert) — Bank-Index == Playback-Seite (gekoppelt)
pe = state.playback_engine
for slot, pb in enumerate(PLAYBACKS, start=1):
    ex = pe.get_executor(slot, page=PB_PAGE)
    ex.stack = pb
    ex.label = pb.name
    ex.fader_function = "volume"


# ════════════════════════════════════════════════════════════════════════════════
#  4) AUTO-SHOW-KOPPLUNG — was beim Play im Musik-Player automatisch startet
# ════════════════════════════════════════════════════════════════════════════════
SLOT_PAR, SLOT_MH = "par_show", "mh_show"
state.music_autoshow = {
    "enabled": True,
    "function_ids": [par_drop.id, mh_orbit.id],   # Standard: Drop-Beat + MH-Orbit
    "bank": 0,
    "slots": {par_drop.id: SLOT_PAR, mh_orbit.id: SLOT_MH},
}


# ════════════════════════════════════════════════════════════════════════════════
#  5) VIRTUAL CONSOLE
# ════════════════════════════════════════════════════════════════════════════════
PAD, GAP, X0, Y0 = 60, 6, 20, 70
STEP = PAD + GAP
GRID_BOTTOM = Y0 + 8 * STEP
TY = GRID_BOTTOM + 4
Y_FAD = GRID_BOTTOM + 34
FAD_H = 142
widgets: list[dict] = []
BANK_ALL = -1
B_AUTO, B_STD, B_SHOWS, B_MH, B_MUSIC = range(5)
PAGE_NAMES = ["Auto-Show", "Standard", "Meine Shows", "MH-Stage", "Musik"]


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


def func_btn(fn, note, bank, accent, exclusive=False, clear_prog=False, style="pulse",
             edit_slot=""):
    b = VCButton(fn.name)
    b.action = ButtonAction.FUNCTION_TOGGLE; b.function_id = fn.id; b.pad_style = style
    b.exclusive = exclusive; b.clear_programmer = clear_prog; b.edit_slot = edit_slot
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
    s = VCSlider(caption); s.mode = mode; s.function_id = function_id
    s.function_ids = list(function_ids or [])
    if submaster_slot is not None:
        s.function_id = submaster_slot
    s.programmer_attr = programmer_attr; s.programmer_scope = programmer_scope
    s.programmer_group = programmer_group; s.param_key = param_key
    s.midi_cc, s.midi_ch = midi_cc, 0; s._value = value
    x = X0 + col * STEP + 2; _add(s, x, Y_FAD, 56, FAD_H, bank)


def pb_fader(caption, col, bank, slot, midi_cc, value=255):
    s = VCSlider(caption); s.mode = SliderMode.PLAYBACK; s.function_id = slot
    s.midi_cc, s.midi_ch = midi_cc, 0; s._value = value
    x = X0 + col * STEP + 2; _add(s, x, Y_FAD, 56, FAD_H, bank)


def label(text, x, y, ww, bank, hh=18):
    _add(VCLabel(text), x, y, ww, hh, bank)


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
label("MUSIK SHOW 2026  —  8 PAR + 2 MH + APC mini.  ▶ im Musik-Tab (oder Bank-1-Play-Pad) startet "
      "Musik UND Auto-Lichtshow; Effekte schalten im BPM-Takt weiter.  Genaue BPM via VirtualDJ→OS2L.",
      X0, 6, 1250, BANK_ALL)
label("SCENE-Tasten = Bank 1-5 (= Playback-Seite):  1 Auto-Show · 2 Standard · 3 Meine Shows · "
      "4 MH-Stage · 5 Musik", X0, Y_FAD + FAD_H + 6, 1150, BANK_ALL)


# ── BANK 1 — AUTO-SHOW ────────────────────────────────────────────────────────────
song = VCSongInfo("Aktuelles Lied")
_add(song, X0, Y0, 4 * STEP - 6, 2 * STEP - 6, B_AUTO)            # R0-1, Spalten 0-3
# R0 cols 4-7: Media-Transport.
action_btn("◄◄ Lied", ButtonAction.MEDIA_PREV, note_rc(0, 4), B_AUTO, "#3a2150")
action_btn("▶ / ❚❚", ButtonAction.MEDIA_PLAY_PAUSE, note_rc(0, 5), B_AUTO, "#5a2080")
action_btn("Lied ►►", ButtonAction.MEDIA_NEXT, note_rc(0, 6), B_AUTO, "#3a2150")
action_btn("Musik-BPM", ButtonAction.AUDIO_BPM, note_rc(0, 7), B_AUTO, "#103a4a")
# R1 cols 4-7: Tap + Utilities.
action_btn("Tap", ButtonAction.TAP, note_rc(1, 4), B_AUTO, "#103a3a")
action_btn("Clear", ButtonAction.CLEAR, note_rc(1, 5), B_AUTO, "#4a3a10")
action_btn("Stop All", ButtonAction.STOP_ALL, note_rc(1, 6), B_AUTO, "#4a1010")
action_btn("Blackout", ButtonAction.BLACKOUT, note_rc(1, 7), B_AUTO, "#2a0000")
# R2 cols 0-3: PAR-Sektionen (beat-getriggert, Slot par_show → sauber wechseln).
for i, fn in enumerate([par_warm, par_build, par_drop, par_chill]):
    accent = "#1f6a4a" if fn is par_drop else "#1f4a28"
    func_btn(fn, note_rc(2, i), B_AUTO, accent, edit_slot=SLOT_PAR)
# R2 cols 4-7: Moving-Head-Formen (Slot mh_show) + Strobe-Flash.
for i, fn in enumerate([mh_orbit, mh_eight, mh_wide]):
    func_btn(fn, note_rc(2, 4 + i), B_AUTO, "#1f3a6a", edit_slot=SLOT_MH)
func_flash(ch_strobe, note_rc(2, 7), B_AUTO, "#551111")
# R3 cols 0-7: Instant-Looks (Slot par_show — friert die laufende Show auf eine Farbe).
for i, fn in enumerate(VIVID):
    func_btn(fn, note_rc(3, i), B_AUTO, "#333333", style="solid", edit_slot=SLOT_PAR)
# R4: Gruppen-Auswahl + Flashes.
for i, (nm, grp) in enumerate([("Alle", "Alle"), ("PARs", "PAR-Reihe"), ("PAR L", "PAR Links"),
                               ("PAR R", "PAR Rechts"), ("MH", "Moving Heads")]):
    select_group_btn(nm, grp, note_rc(4, i), B_AUTO)
func_flash(look_white, note_rc(4, 6), B_AUTO, "#555555")
func_flash(look_warm, note_rc(4, 7), B_AUTO, "#553010")
fader("Master-Dim", 0, B_AUTO, SliderMode.SUBMASTER, submaster_slot=0, midi_cc=48, value=255)
fader("FX-Speed", 1, B_AUTO, SliderMode.EFFECT_SPEED, midi_cc=49, value=80)
fader("FX-Master", 2, B_AUTO, SliderMode.EFFECT_INTENSITY, midi_cc=50, value=255)
fader("PAR-Dim", 3, B_AUTO, SliderMode.GROUP_DIMMER, programmer_group="PAR-Reihe", midi_cc=51, value=255)
fader("MH-Dim", 4, B_AUTO, SliderMode.GROUP_DIMMER, programmer_group="Moving Heads", midi_cc=52, value=255)
label("BANK 1  AUTO-SHOW  —  ▶/❚❚ startet Musik + Auto-Lichtshow (Drop-Beat + MH-Orbit, taktet zur BPM). "
      "R2: Sektionen (Warmup/Build/Drop/Chill) + MH-Formen · R3: Looks (einfrieren) · R4: Gruppen/Flash.",
      X0, 28, 1250, B_AUTO)


# ── BANK 2 — STANDARD (Farben + Matrix + Chases, volle Kontrolle) ─────────────────
COLORS16 = [
    ("Rot", 255, 0, 0, 0), ("Orange", 255, 90, 0, 0), ("Amber", 255, 160, 0, 0), ("Gelb", 255, 220, 0, 0),
    ("Limette", 160, 255, 0, 0), ("Grün", 0, 255, 0, 0), ("Türkis", 0, 230, 150, 0), ("Cyan", 0, 255, 255, 0),
    ("Hellblau", 0, 140, 255, 0), ("Blau", 0, 0, 255, 0), ("Violett", 140, 0, 255, 0), ("Magenta", 255, 0, 255, 0),
    ("Pink", 255, 0, 120, 0), ("Warmweiß", 255, 130, 40, 60), ("Weiß", 255, 255, 255, 255), ("Aus", 0, 0, 0, 0),
]
for i, (nm, r, g, b, w) in enumerate(COLORS16):     # R0-1 = 16 anpassbare Farb-Kacheln
    color_tile(nm, note_rc(i // 8, i % 8), B_STD, r, g, b, w)
for i, m in enumerate(mtx):                          # R2 = 8 Standard-Matrix-Looks (exklusiv)
    func_btn(m, note_rc(2, i), B_STD, "#7a5b00", exclusive=True, clear_prog=True)
STD_CHASES = [ch_run, ch_ping, ch_pairs, ch_sides, ch_color, ch_color2]
for i, fn in enumerate(STD_CHASES):                  # R3 = Chases + Color-Chases
    accent = "#1f4a28" if fn in (ch_color, ch_color2) else "#2a3a5a"
    func_btn(fn, note_rc(3, i), B_STD, accent, exclusive=True, clear_prog=(fn in (ch_color, ch_color2)))
func_flash(ch_strobe, note_rc(3, 6), B_STD, "#551111")
func_flash(st_all, note_rc(3, 7), B_STD, "#555555")
fader("FX-Speed", 0, B_STD, SliderMode.EFFECT_SPEED, midi_cc=48, value=80)
fader("FX-Master", 1, B_STD, SliderMode.EFFECT_INTENSITY, midi_cc=49, value=255)
fader("FX-Param", 2, B_STD, SliderMode.EFFECT_PARAM, param_key="white_amount", midi_cc=50, value=0)
fader("PAR-Dim", 3, B_STD, SliderMode.GROUP_DIMMER, programmer_group="PAR-Reihe", midi_cc=51, value=255)
label("BANK 2  STANDARD  —  R1-2 Farben (anpassbar, Programmer) · R3 Matrix-Looks · R4 Chases/Color-Chases. "
      "Fader: Speed/Master/Param/Dim wirken auf den laufenden Effekt.", X0, 28, 1200, B_STD)


# ── BANK 3 — MEINE SHOWS (Cuelisten, 2 mit Beat-Sync) ─────────────────────────────
for i, pb in enumerate(PLAYBACKS):
    cl = VCCueList(pb.name); cl.stack_slot = i
    _add(cl, X0 + i * 250, Y0, 240, 196, B_SHOWS)
PB_ACCENT = ["#1f4a28", "#8b0d4f", "#0d4f8b", "#7a5b00"]
for i, pb in enumerate(PLAYBACKS):
    exec_go_btn(f"GO {pb.name[:8]}", i, note_rc(4, i), B_SHOWS, PB_ACCENT[i])
    exec_flash_btn(f"Flash {i+1}", i, note_rc(5, i), B_SHOWS, "#333355")
sd = VCSpeedDial("Tempo"); sd.target_mode = SpeedTarget.EXECUTOR
sd.function_id = 2; sd.multiplier_mode = True
_add(sd, X0 + 5 * STEP, pad_pos(note_rc(4, 5))[1], 150, 110, B_SHOWS)
for i, pb in enumerate(PLAYBACKS):
    pb_fader(f"Dim {i+1}", i, B_SHOWS, slot=i, midi_cc=48 + i, value=255)
label("BANK 3  MEINE SHOWS  —  4 Cuelisten: Aufwärmen(Zeit) · Drop-Sequenz(Beat-Sync, 1 Takt) · "
      "Farb-Reise(Beat-Sync, 2 Takte) · MH-Fahrt(Zeit).  R5=GO, R6=Flash, Fader=Dimmer.  "
      "Beat-Sync läuft taktgenau zur BPM (Drehrad=Tempo).", X0, 28, 1250, B_SHOWS)


# ── BANK 4 — MH-STAGE (Ausrichtung, Bewegung passend zur Bühne) ───────────────────
xy_pos = VCXYPad("MH zielen"); xy_pos.mode = "position"; xy_pos._fixture_ids = list(mh_fids)
xy_pos.bits16 = True
_add(xy_pos, X0, Y0, 224, 224, B_MH)                              # R0-2, Spalten 0-2
# R0 cols 4-7 + R1 col 4: Zonen-Orbits (Bewegung auf Bühnen-Zone ausgerichtet).
for i, fn in enumerate([mh_zone_mitte, mh_zone_links, mh_zone_rechts, mh_zone_pub, mh_zone_hoch]):
    note = note_rc(0, 4 + i) if i < 4 else note_rc(1, 4)
    func_btn(fn, note, B_MH, "#1f3a6a", edit_slot=SLOT_MH)
# R1 cols 5-7: relative Formen + reine Ausrichtung.
func_btn(mh_rel_circle, note_rc(1, 5), B_MH, "#1f6a4a", edit_slot=SLOT_MH)
func_btn(mh_rel_eight, note_rc(1, 6), B_MH, "#1f6a4a", edit_slot=SLOT_MH)
func_flash(AIMS[0], note_rc(1, 7), B_MH, "#444444")
# R2 cols 4-7 + R3 col 4: Ziel-Szenen (Programmer-Aim für die relativen Formen).
for i, fn in enumerate(AIMS):
    note = note_rc(2, 4 + i) if i < 4 else note_rc(3, 4)
    func_btn(fn, note, B_MH, "#333333", style="solid", edit_slot="mh_aim")
# R3 cols 5-7: Effekt-Aktionen.
effect_action_btn("Spiegeln", note_rc(3, 5), B_MH, "#334455", "toggle_mirror", None)
effect_action_btn("Gegenläufig", note_rc(3, 6), B_MH, "#7a6500", "toggle_counter", None)
effect_action_btn("Neustart", note_rc(3, 7), B_MH, "#553010", "restart", None)
fader("EFX-Speed", 0, B_MH, SliderMode.EFFECT_SPEED, midi_cc=48, value=80)
fader("EFX-Größe", 1, B_MH, SliderMode.EFFECT_PARAM, param_key="size", midi_cc=49, value=110)
fader("MH-Dim", 3, B_MH, SliderMode.GROUP_DIMMER, programmer_group="Moving Heads", midi_cc=51, value=255)
label("BANK 4  MH-STAGE  —  LINKS frei zielen (16-bit XY).  Orbit-Pads richten die Bewegung auf eine "
      "Bühnen-Zone aus (Mitte/Links/Rechts/Publikum/Hoch).  Relative Formen orbiten das aktuelle Ziel; "
      "Spiegeln/Gegenläufig/Neustart.", X0, 28, 1250, B_MH)


# ── BANK 5 — MUSIK ────────────────────────────────────────────────────────────────
song2 = VCSongInfo("Aktuelles Lied")
_add(song2, X0, Y0, 4 * STEP - 6, 2 * STEP - 6, B_MUSIC)          # R0-1, Spalten 0-3
for i, (nm, r, g, b, w) in enumerate(COLORS16[:8]):               # R0-1, Spalten 4-7
    color_tile(nm, note_rc(i // 4, 4 + i % 4), B_MUSIC, r, g, b, w)
for i, fn in enumerate(VIVID):                                    # R2 = Looks
    func_btn(fn, note_rc(2, i), B_MUSIC, "#333333", style="solid", edit_slot=SLOT_PAR)
# R3 = große Media-Transport-Reihe.
action_btn("◄◄ Lied", ButtonAction.MEDIA_PREV, note_rc(3, 0), B_MUSIC, "#3a2150")
action_btn("▶ / ❚❚", ButtonAction.MEDIA_PLAY_PAUSE, note_rc(3, 1), B_MUSIC, "#5a2080")
action_btn("Lied ►►", ButtonAction.MEDIA_NEXT, note_rc(3, 2), B_MUSIC, "#3a2150")
action_btn("Musik-BPM", ButtonAction.AUDIO_BPM, note_rc(3, 3), B_MUSIC, "#103a4a")
action_btn("Tap", ButtonAction.TAP, note_rc(3, 4), B_MUSIC, "#103a3a")
action_btn("Clear", ButtonAction.CLEAR, note_rc(3, 5), B_MUSIC, "#4a3a10")
action_btn("Blackout", ButtonAction.BLACKOUT, note_rc(3, 6), B_MUSIC, "#2a0000")
func_flash(ch_strobe, note_rc(3, 7), B_MUSIC, "#551111")
fader("PAR-Dim", 3, B_MUSIC, SliderMode.GROUP_DIMMER, programmer_group="PAR-Reihe", midi_cc=51, value=255)
fader("MH-Dim", 4, B_MUSIC, SliderMode.GROUP_DIMMER, programmer_group="Moving Heads", midi_cc=52, value=255)
label("BANK 5  MUSIK  —  Anzeige aktuelles/nächstes Lied.  R4: ◄◄ ▶/❚❚ ►► steuern den In-App-Player "
      "(auch im Tab 'Musik').  Der ▶-Schalter dort koppelt die Auto-Lichtshow.  Genaue BPM: VirtualDJ→OS2L.",
      X0, 28, 1250, B_MUSIC)


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
#  6) Speichern + Verifikation
# ════════════════════════════════════════════════════════════════════════════════
state.programmer = {}
state.show_name = "Musik Show 2026"
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
from src.core.audio.media_player import get_media_player
assert len(get_media_player().tracks) == 10, len(get_media_player().tracks)

# Auto-Show-Kopplung erhalten + verweist auf existierende Funktionen?
ma = state.music_autoshow
assert ma.get("enabled") is True, ma
fn_ids = {f.id for f in get_function_manager().all()}
assert ma.get("function_ids") and all(fid in fn_ids for fid in ma["function_ids"]), ma
assert len(ma["function_ids"]) == 2, ma["function_ids"]
# Master-PAR-Funktion ist beat-getriggert?
from src.core.engine.chaser import Chaser
par_master = get_function_manager().get(ma["function_ids"][0])
assert isinstance(par_master, Chaser) and par_master.audio_triggered, par_master
# Slots gesetzt (für sauberes Ablösen durch Bank-Pads)?
assert set(int(k) for k in ma.get("slots", {})) == set(ma["function_ids"]), ma.get("slots")

# Mindestens 2 Cuelisten beat-sync?
assert len(state.cue_stacks) == 4, f"Cue-Stacks: {len(state.cue_stacks)}"
beat_stacks = [s for s in state.cue_stacks if getattr(s, "beat_sync", False)]
assert len(beat_stacks) == 2, [s.name for s in beat_stacks]
assert all(s.beats_per_cue >= 1 for s in beat_stacks)
by = {s.name: s for s in state.cue_stacks}
assert by["Drop-Sequenz"].beat_sync and by["Drop-Sequenz"].beats_per_cue == 4
assert by["Farb-Reise"].beat_sync and by["Farb-Reise"].beats_per_cue == 8
assert not by["Aufwärmen"].beat_sync and not by["MH-Fahrt"].beat_sync
# Executoren gebunden?
pe2 = state.playback_engine
bound = [pe2.get_executor(s, page=PB_PAGE).stack for s in (1, 2, 3, 4)]
assert all(b is not None for b in bound), f"Executoren ungebunden: {bound}"
assert {b.name for b in bound} == set(by), [b.name for b in bound]

# Mindestens eine relative MH-EFX (Bank 4)?
from src.core.engine.efx import EfxInstance
rel_efx = [f for f in get_function_manager().all()
           if isinstance(f, EfxInstance) and f.relative]
assert len(rel_efx) >= 1, "keine relative EFX"

# VC-Fenster-Widgets vorhanden?
assert types.get("VCSongInfo", 0) == 2, f"VCSongInfo: {types.get('VCSongInfo')}"
assert types.get("VCCueList", 0) == 4, f"VCCueList: {types.get('VCCueList')}"
assert types.get("VCXYPad", 0) == 1, f"VCXYPad: {types.get('VCXYPad')}"
assert types.get("VCSpeedDial", 0) == 1, "VCSpeedDial fehlt"
media_pads = [w for w in vc if w.get("action") in ("MediaPlayPause", "MediaNext", "MediaPrev")]
assert len(media_pads) == 6, f"Media-Pads: {len(media_pads)}"
std_colors = [w for w in vc if w.get("bank") == B_STD and w.get("type") == "VCColor"
              and w.get("target") == ColorTarget.PROGRAMMER]
assert len(std_colors) == 16, f"Standard-Farben: {len(std_colors)}"
go_pads = [w for w in vc if w.get("bank") == B_SHOWS and w.get("action") == "Toggle"]
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
print(f"  Auto-Show: enabled={ma['enabled']}  fn_ids={ma['function_ids']}  slots={ma['slots']}")
print(f"  Beat-Sync-Cuelisten: {[s.name for s in beat_stacks]}  relative EFX: {len(rel_efx)}")
print(f"  Playlist={len(state.playlist)}  Standard-Farben={len(std_colors)}  Media-Pads={len(media_pads)}  GO={len(go_pads)}")
print("  Playlist-Arc:")
for t in state.playlist:
    print(f"    {t['bpm']:>5.0f} BPM  [{t['genre']:<11}] {t['title']}")
print("  [OK] 5 Banks · Auto-Show an Musik gekoppelt · beat-getriggerte Effekte · 2 Beat-Sync-Cuelisten · MH-Stage")
print("FERTIG")
