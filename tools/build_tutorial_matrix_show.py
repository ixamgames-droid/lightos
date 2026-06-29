"""TUTORIAL_MATRIX — Begleit-Show zur bebilderten Schritt-fuer-Schritt-Anleitung.

Setup: 8x "LED PAR Dimmer+RGB 4ch" (PARD) + 2x "Moving Head Spot 8ch" (MH8).

Demonstriert die Tutorial-Themen mit EBENEN-TRENNUNG, die nur dank des
Dimmer+RGB-Profils so sauber zeigbar ist (Dimmer auf eigenem Kanal, Farbe auf
R/G/B):

  * GRUPPEN      : "PAR-Matrix" (4x2) + "Moving Heads" (2x1)
  * FARB-MATRIX  : style=RGB, drive_intensity=False -> schreibt NUR R/G/B
                   (Regenbogen / Gradient / Lauflicht), laesst den Dimmer in Ruhe.
  * DIMMER-MATRIX: style=DIMMER -> schreibt NUR den Dimmer-Kanal (Helligkeits-
                   Welle), laesst die Farbe in Ruhe.
  * LAYERING     : Farb-Matrix + Dimmer-Matrix gleichzeitig = bewegte Farbe MIT
                   Helligkeits-Welle (zwei getrennte Ebenen, kein Konflikt).
  * CHASE        : "PAR-Lauflicht" — Chaser ueber 8 Intensitaets-Szenen.
  * MH-EFX       : "MH-Kreis" — CIRCLE-Bewegung auf den 2 Moving Heads.
  * VC           : Pads (FunctionToggle) mit exclusive / solo_fixtures, Speed-
                   Fader (EFFECT_SPEED) + SpeedDial (Funktion), Gruppen-Dimmer,
                   Master.  Zeigt Benennung + Layering.

Aufruf:  venv/Scripts/python.exe tools/build_tutorial_matrix_show.py
Erzeugt: shows/Tutorial_Matrix.lshow
"""
from __future__ import annotations
import os
import sys
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
from src.core.engine.rgb_matrix import RgbAlgorithm, MatrixStyle, ColorSequence
from src.core.engine.efx import EfxFixture, EfxAlgorithm
from src.core.show.show_file import reset_show, save_show, load_show
from src.ui.virtualconsole.vc_button import VCButton, ButtonAction
from src.ui.virtualconsole.vc_slider import VCSlider, SliderMode
from src.ui.virtualconsole.vc_label import VCLabel
from src.ui.virtualconsole.vc_speedial import VCSpeedDial, SpeedTarget

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(_ROOT, "shows", "Tutorial_Matrix.lshow")


def profile_id(short: str) -> int:
    with Session(fdb_engine()) as s:
        pid = s.execute(select(FixtureProfile.id).where(
            FixtureProfile.short_name == short)).scalar_one_or_none()
    if pid is None:
        raise SystemExit(f"Profil '{short}' fehlt — bitte App einmal starten (ensure_builtins).")
    return int(pid)


# ── 0) Basis + Patch ────────────────────────────────────────────────────────────
reset_show()
state = get_state()
fm = get_function_manager()
PAR_PID, MH_PID = profile_id("PARD"), profile_id("MH8")

COLS, ROWS = 4, 2
N_PAR = COLS * ROWS                          # 8
par_fids: list[int] = []
addr = 1
for i in range(N_PAR):
    fid = i + 1
    state.add_fixture(PatchedFixture(
        fid=fid, label=f"PAR {i + 1}", fixture_profile_id=PAR_PID,
        mode_name="4-Kanal Dimmer+RGB", universe=1, address=addr, channel_count=4,
        manufacturer_name="Generic", fixture_name="LED PAR Dimmer+RGB 4ch",
        fixture_type="par"), undoable=False)
    par_fids.append(fid); addr += 4

mh_left, mh_right = 9, 10
for fid, lbl, a in ((mh_left, "MH Links", 33), (mh_right, "MH Rechts", 41)):
    state.add_fixture(PatchedFixture(
        fid=fid, label=lbl, fixture_profile_id=MH_PID, mode_name="8-Kanal",
        universe=1, address=a, channel_count=8, manufacturer_name="Generic",
        fixture_name="Moving Head Spot 8ch", fixture_type="moving_head"), undoable=False)
mh_fids = [mh_left, mh_right]

fixtures = state.get_patched_fixtures()
fx_of = {f.fid: f for f in fixtures}
chan_of = {f.fid: {c.attribute: c.channel_number
                   for c in get_channels_for_patched(f)} for f in fixtures}

# Grund-Frame: PARs weiss @ voll (Farb-Matrix ueberschreibt R/G/B, Dimmer-Matrix
# ueberschreibt den Dimmer -> jede Ebene ist FUER SICH sichtbar).  MHs offen+hell.
base = {}
for fid in par_fids:
    cm = chan_of[fid]
    base[fid] = {"intensity": 255, "color_r": 255, "color_g": 255, "color_b": 255}
SHUT_OPEN = open_value_for(fx_of[mh_left], "shutter")
for fid in mh_fids:
    base[fid] = {"intensity": 255, "pan": 128, "tilt": 128, "shutter": SHUT_OPEN}
state.base_levels = base
state._rebuild_render_plan()

# ── 1) GRUPPEN ───────────────────────────────────────────────────────────────────
with state._session() as s:
    s.execute(delete(FixtureGroup))
    s.add(FixtureGroup(name="PAR-Matrix", cols=COLS, rows=ROWS,
                       positions_json=json.dumps(
                           {f"{i % COLS},{i // COLS}": par_fids[i] for i in range(N_PAR)})))
    s.add(FixtureGroup(name="Moving Heads", cols=2, rows=1,
                       positions_json=json.dumps({"0,0": mh_left, "1,0": mh_right})))
    s.commit()

# ── 2) POSITIONEN (Live View 2D + 3D) ────────────────────────────────────────────
lv = {}
for i in range(N_PAR):
    col, row = i % COLS, i // COLS
    lv[par_fids[i]] = [340 + col * 290, 470 + row * 150]
lv[mh_left] = [620, 200]
lv[mh_right] = [930, 200]
state.live_view_positions = {fid: list(p) for fid, p in lv.items()}
viz = {}
for i in range(N_PAR):
    col, row = i % COLS, i // COLS
    viz[par_fids[i]] = [(-3.0 + col * 2.0), 0.2, (-1.0 + row * 2.0)]
viz[mh_left] = [-1.5, 3.0, 0.0]
viz[mh_right] = [1.5, 3.0, 0.0]
state.visualizer_positions = {fid: tuple(p) for fid, p in viz.items()}

GRID = list(par_fids)   # row-major 4x2 -> [1..8]


# ── 3) FUNKTIONEN ────────────────────────────────────────────────────────────────
def color_matrix(name, algo, *, colors=None, speed=1.3, params=None):
    """REINE FARB-EBENE: style=RGB, drive_intensity=False -> nur R/G/B."""
    m = fm.new_rgb_matrix(name)
    m.algorithm = algo
    m.style = MatrixStyle.RGB
    m.drive_intensity = False
    m.fixture_grid = list(GRID); m.cols, m.rows = COLS, ROWS
    m.matrix_speed = speed
    if colors is not None:
        m.colors = ColorSequence([tuple(c) for c in colors])
    if params:
        m.params = dict(params)
    return m


def dimmer_matrix(name, algo, *, speed=1.2, params=None):
    """REINE DIMMER-EBENE: style=DIMMER -> nur der Dimmer-Kanal (Helligkeit)."""
    m = fm.new_rgb_matrix(name)
    m.algorithm = algo
    m.style = MatrixStyle.DIMMER
    m.fixture_grid = list(GRID); m.cols, m.rows = COLS, ROWS
    m.colors = ColorSequence([(255, 255, 255)])
    m.intensity_min, m.intensity_max = 0, 255
    m.matrix_speed = speed
    if params:
        m.params = dict(params)
    return m


# Farb-Ebene (3 Looks, in der VC exklusiv -> immer nur einer):
mx_rainbow = color_matrix("Farbe Regenbogen", RgbAlgorithm.RAINBOW,
                          params={"movement": "linear", "spread": 1.0,
                                  "saturation": 1.0, "value": 1.0}, speed=1.2)
mx_gradient = color_matrix("Farbe Gradient", RgbAlgorithm.GRADIENT,
                           colors=[(255, 0, 0), (0, 255, 0), (0, 0, 255)],
                           params={"axis": "H", "blend": "smooth"}, speed=1.0)
mx_chase = color_matrix("Farbe Lauflicht", RgbAlgorithm.CHASE,
                        colors=[(0, 180, 255), (255, 0, 120)],
                        params={"axis": "H", "movement": "normal",
                                "runner_count": 1, "runner_width": 1, "fade": 0.35},
                        speed=3.0)

# Dimmer-Ebene (Helligkeits-Welle, ohne Farbe):
mx_dim = dimmer_matrix("Dimmer-Welle", RgbAlgorithm.WAVE,
                       params={"origin": "left", "density": 1.0, "spread": 1.0}, speed=1.2)

# Chase (Lauflicht ueber die 8 PARs, je eine Szene pro PAR an):
chase_steps = []
for i, fid in enumerate(par_fids):
    sc = fm.new_scene(f"Step {i + 1}")
    for fid2 in par_fids:
        if "intensity" in chan_of[fid2]:
            sc.set_value(fid2, chan_of[fid2]["intensity"], 255 if fid2 == fid else 0)
    chase_steps.append(sc)
chaser = fm.new_chaser("PAR-Lauflicht")
chaser.run_order, chaser.direction, chaser.speed = RunOrder.Loop, Direction.Forward, 1.0
for sc in chase_steps:
    chaser.steps.append(ChaserStep(function_id=sc.id, fade_in=0.05, hold=0.30, fade_out=0.0))

# MH-EFX (Kreis auf beiden Moving Heads):
efx_circle = fm.new_efx("MH-Kreis")
efx_circle.algorithm = EfxAlgorithm.CIRCLE
efx_circle.fixtures = [EfxFixture(fid=mh_left), EfxFixture(fid=mh_right)]
efx_circle.speed_hz = 0.35
efx_circle.spread = 0.0
efx_circle.open_beam = True
efx_circle.width = efx_circle.height = 120.0


# ── 4) VIRTUAL CONSOLE ───────────────────────────────────────────────────────────
PAD, GAP, X0, Y0 = 92, 12, 30, 150
STEP = PAD + GAP
widgets: list[dict] = []


def _add(w, x, y, ww, hh):
    w.bank = 0
    w.setGeometry(x, y, ww, hh)
    widgets.append(w.to_dict())


def pad(name, fn, col, row, accent, *, exclusive=False, solo_fixtures=False, style="pulse"):
    b = VCButton(name)
    b.action = ButtonAction.FUNCTION_TOGGLE
    b.function_id = fn.id
    b.exclusive = exclusive
    b.solo_fixtures = solo_fixtures
    b.pad_style = style
    b._bg_color.setNamedColor(accent)
    _add(b, X0 + col * STEP, Y0 + row * STEP, PAD, PAD)


def fader(caption, col, mode, *, function_id=None, param_key="speed",
          programmer_group="", value=128):
    s = VCSlider(caption)
    s.mode = mode
    s.function_id = function_id
    s.param_key = param_key
    s.programmer_group = programmer_group
    s.midi_cc = -1
    s._value = value
    _add(s, X0 + col * STEP + 6, Y_FAD, 70, 230)


def label(text, x, y, ww, hh=22):
    _add(VCLabel(text), x, y, ww, hh)


# Reihe 0: FARB-LOOKS (exklusiv -> immer nur EIN Farb-Look aktiv)
pad("Regenbogen", mx_rainbow, 0, 0, "#6a3a00", exclusive=True)
pad("Gradient",   mx_gradient, 1, 0, "#6a3a00", exclusive=True)
pad("Lauflicht",  mx_chase,    2, 0, "#6a3a00", exclusive=True)
# Reihe 1: DIMMER-EBENE (NICHT exklusiv -> legt sich ueber den Farb-Look = Layering)
pad("Dimmer-Welle", mx_dim, 0, 1, "#11507a", style="pulse")
# PAR-Chase: solo_fixtures -> stoppt andere Effekte auf DENSELBEN PARs
pad("PAR-Chase", chaser, 1, 1, "#1f6a2a", solo_fixtures=True, style="solid")
# MH-Kreis: andere Geraete -> laeuft problemlos parallel
pad("MH-Kreis", efx_circle, 2, 1, "#5a2a6a", style="solid")

# Fader-Reihe darunter
Y_FAD = Y0 + 2 * STEP + 40
fader("FX-Speed", 0, SliderMode.EFFECT_SPEED, value=64)                       # aktiver Effekt
fader("Regenbogen-Speed", 1, SliderMode.EFFECT_SPEED, function_id=mx_rainbow.id, value=64)
fader("PAR-Dimmer", 3, SliderMode.GROUP_DIMMER, programmer_group="PAR-Matrix", value=255)
fader("Master", 5, SliderMode.GRANDMASTER, value=255)

# SpeedDial fuer die MH-Kreis-Geschwindigkeit (Funktion, Multiplikator)
sd = VCSpeedDial("MH-Kreis Tempo")
sd.target_mode = SpeedTarget.FUNCTION
sd.function_id = efx_circle.id
sd.multiplier_mode = True
_add(sd, X0 + 6 * STEP + 6, Y_FAD, 140, 120)

# Beschriftungen
label("LightOS — TUTORIAL: Matrix · Chase · Moving-Head-EFX · Virtuelle Konsole", X0, 18, 1200, 28)
label("Reihe 1 = FARB-Looks (exklusiv: immer nur EINER).  Reihe 2: Dimmer-Welle (Layer) · "
      "PAR-Chase (solo_fixtures) · MH-Kreis.", X0, 54, 1300)
label("Layering: Farb-Look + Dimmer-Welle gleichzeitig = bewegte Farbe MIT Helligkeits-Welle "
      "(zwei getrennte Ebenen).", X0, 86, 1300)
label("Fader: FX-Speed (aktiver Effekt) · Regenbogen-Speed · PAR-Dimmer (Gruppe) · Master.  "
      "Drehregler: MH-Kreis-Tempo.", X0, Y_FAD + 244, 1300)

state._vc_layout = {"widgets": widgets}

# ── 5) Speichern + Verifikation ──────────────────────────────────────────────────
state.programmer = {}
state.show_name = "Tutorial Matrix"
save_show(OUT)
print(f"Gespeichert: {OUT}")

ok, msg = load_show(OUT)
print("Load:", ok, msg)
assert ok, f"Show laedt nicht: {msg}"
state = get_state()
fm = get_function_manager()

from src.core.engine.function import FunctionType
pats = state.get_patched_fixtures()
assert len(pats) == 10, f"Patch: {len(pats)}"
pars = [f for f in pats if f.fixture_type == "par"]
mhs = [f for f in pats if f.fixture_type == "moving_head"]
assert len(pars) == 8 and len(mhs) == 2, (len(pars), len(mhs))

mats = [f for f in fm.all() if f.function_type == FunctionType.RGBMatrix]
rgb_looks = [m for m in mats if m.style == MatrixStyle.RGB]
dim_looks = [m for m in mats if m.style == MatrixStyle.DIMMER]
assert len(rgb_looks) == 3, f"Farb-Matrizen: {len(rgb_looks)}"
assert len(dim_looks) == 1, f"Dimmer-Matrizen: {len(dim_looks)}"
for m in rgb_looks:
    assert not m.drive_intensity, f"{m.name} treibt faelschlich den Dimmer"

chasers = [f for f in fm.all() if f.function_type == FunctionType.Chaser]
assert len(chasers) == 1 and len(chasers[0].steps) == 8, "Chaser/Steps falsch"
efxs = [f for f in fm.all() if f.function_type == FunctionType.EFX]
assert len(efxs) == 1 and len(efxs[0].fixtures) == 2, "EFX falsch"

# Gruppen
with state._session() as s:
    grps = {g.name: g for g in s.execute(select(FixtureGroup)).scalars().all()}
assert set(grps) == {"PAR-Matrix", "Moving Heads"}, set(grps)

vc = state._vc_layout.get("widgets", [])
from collections import Counter
types = Counter(w["type"] for w in vc)
excl = [w for w in vc if w["type"] == "VCButton" and w.get("exclusive")]
solo = [w for w in vc if w["type"] == "VCButton" and w.get("solo_fixtures")]
assert len(excl) == 3, f"exklusive Pads: {len(excl)}"
assert len(solo) == 1, f"solo_fixtures-Pads: {len(solo)}"
assert types.get("VCSpeedDial", 0) == 1, "SpeedDial fehlt"

print(f"Fixtures: {len(pars)} PAR + {len(mhs)} MH   Gruppen: {sorted(grps)}")
print(f"Matrizen: RGB={len(rgb_looks)} DIMMER={len(dim_looks)}   Chaser-Steps={len(chasers[0].steps)}   "
      f"EFX={efxs[0].algorithm.value}")
print(f"VC-Widgets: {len(vc)} {dict(types)}  exklusiv={len(excl)} solo_fixtures={len(solo)}")
print("FERTIG")
