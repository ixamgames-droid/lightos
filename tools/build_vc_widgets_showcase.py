"""VC-Widgets-Schaukasten (Doku) — legt JEDEN der 18 VC-Widget-Typen einmal
beschriftet in ein klares Raster auf Bank 1 (active_bank 0), bindet sie an einen
Demo-Effekt (damit Farb-/Chase-/Vorschau-Widgets Inhalt zeigen) und legt zwei
KALIBRIER-Kacheln (reines Magenta/Cyan) an bekannten Canvas-Koordinaten ab.

Erzeugt zusaetzlich ein Geometrie-Sidecar (JSON) mit allen Widget-Rechtecken
(logische Canvas-Pixel) + Kalibrier-Farben/-Positionen. Damit kann ein Cropper
aus EINEM Vollbild-Screenshot pixelgenau jedes Widget ausschneiden.

Aufruf:  venv/Scripts/python.exe tools/build_vc_widgets_showcase.py
Erzeugt: shows/VC_Widgets_Showcase.lshow
         docs/anleitung_vc_widgets/_capture/geometry.json
"""
from __future__ import annotations
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import _gen_env  # noqa: F401  # DEMO-02: spawn-sichere Env-Schalter vor src.core (tools/_gen_env.py)
from PySide6.QtWidgets import QApplication
_app = QApplication.instance() or QApplication([])

from sqlalchemy import select
from sqlalchemy.orm import Session
from src.core.app_state import get_state
from src.core.database.fixture_db import engine as fdb_engine
from src.core.database.models import PatchedFixture, FixtureProfile
from src.core.engine.function_manager import get_function_manager
from src.core.engine.rgb_matrix import RgbAlgorithm, ColorSequence
from src.core.engine.cue import Cue
from src.core.show.show_file import reset_show, save_show, load_show
from src.core.engine import effect_live

from src.ui.virtualconsole.vc_button import VCButton, ButtonAction
from src.ui.virtualconsole.vc_slider import VCSlider, SliderMode
from src.ui.virtualconsole.vc_color import VCColor, ColorTarget
from src.ui.virtualconsole.vc_label import VCLabel
from src.ui.virtualconsole.vc_cuelist import VCCueList
from src.ui.virtualconsole.vc_speedial import VCSpeedDial, SpeedTarget
from src.ui.virtualconsole.vc_encoder import VCEncoder
from src.ui.virtualconsole.vc_stepper import VCStepper
from src.ui.virtualconsole.vc_color_list import VCColorList
from src.ui.virtualconsole.vc_song_info import VCSongInfo
from src.ui.virtualconsole.vc_bpm_display import VCBpmDisplay
from src.ui.virtualconsole.vc_bus_selector import VCBusSelector
from src.ui.virtualconsole.vc_effect_colors import VCEffectColors
from src.ui.virtualconsole.vc_xypad import VCXYPad
from src.ui.virtualconsole.vc_frame import VCFrame
from src.ui.virtualconsole.vc_effect_editor import VCEffectEditor
from src.ui.virtualconsole.vc_effect_display import VCEffectDisplay

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(_ROOT, "shows", "VC_Widgets_Showcase.lshow")
CAP_DIR = os.path.join(_ROOT, "docs", "anleitung_vc_widgets", "_capture")
os.makedirs(CAP_DIR, exist_ok=True)
GEO = os.path.join(CAP_DIR, "geometry.json")

# ── Demo-Rig + Effekte ───────────────────────────────────────────────────────
reset_show()
state = get_state()
fm = get_function_manager()
with Session(fdb_engine()) as s:
    par_pid = s.execute(select(FixtureProfile.id).where(FixtureProfile.short_name == "ZQ01424")).scalar_one()
addr = 1
par_fids = []
for i in range(6):
    state.add_fixture(PatchedFixture(fid=i + 1, label=f"PAR {i+1}", fixture_profile_id=par_pid,
                      mode_name="8-Kanal RGBW", universe=1, address=addr, channel_count=8,
                      manufacturer_name="Generic", fixture_name="Stage Light ZQ01424",
                      fixture_type="par"), undoable=False)
    par_fids.append(i + 1); addr += 8
state.base_levels = {f: {"intensity": 255} for f in par_fids}
state._rebuild_render_plan()

# COLORFADE-Matrix (Farb-Sequenz) — fuer Farb-/Chase-/Vorschau-Widgets.
mtx = fm.new_rgb_matrix("Demo-Chase")
mtx.algorithm = RgbAlgorithm.COLORFADE
mtx.fixture_grid = list(par_fids); mtx.cols, mtx.rows = len(par_fids), 1
mtx.colors = ColorSequence([(255, 0, 0), (255, 180, 0), (0, 200, 60), (0, 120, 255), (170, 0, 255)])
mtx.matrix_speed = 1.5

# Zweite Matrix mit Laeufer-Parametern (runner_count/size) — fuer Encoder/Stepper.
run = fm.new_rgb_matrix("Demo-Runner")
for algo in (getattr(RgbAlgorithm, "RUNNER", None), getattr(RgbAlgorithm, "CHASE", None),
             getattr(RgbAlgorithm, "COMET", None)):
    if algo is not None:
        run.algorithm = algo
        break
run.fixture_grid = list(par_fids); run.cols, run.rows = len(par_fids), 1
run.matrix_speed = 1.0

# Verfuegbare Parameter-Keys ermitteln (defensiv: passende fuer Encoder/Stepper waehlen).
def _param_keys(fid):
    try:
        return {s.key: s for s in effect_live.list_params(fid)}
    except Exception:
        return {}

run_params = _param_keys(run.id)
mtx_params = _param_keys(mtx.id)
print("Runner-Params:", list(run_params))
print("Chase-Params :", list(mtx_params))

def _pick(params, prefer, kinds):
    for k in prefer:
        if k in params and getattr(params[k], "kind", "") in kinds:
            return k
    for k, sp in params.items():
        if getattr(sp, "kind", "") in kinds:
            return k
    return prefer[0]

ENC_FID, ENC_KEY = (run.id, _pick(run_params, ["size", "speed", "hold"], ("int", "float"))) if run_params \
    else (mtx.id, _pick(mtx_params, ["speed", "hold"], ("int", "float")))
STEP_FID, STEP_KEY = (run.id, _pick(run_params, ["runner_count", "runner_width", "size"], ("int",))) if run_params \
    else (run.id, "runner_count")
print(f"Encoder -> fid={ENC_FID} key={ENC_KEY} ; Stepper -> fid={STEP_FID} key={STEP_KEY}")

# Cueliste (fuer VCCueList).
pb = state.new_cue_stack("Demo-Cueliste"); pb.mode = "loop"
pb.add_cue(Cue(number=1.0, label="Rot",  fade_in=1.0, values={par_fids[0]: {"color_r": 255, "intensity": 255}}))
pb.add_cue(Cue(number=2.0, label="Gruen", fade_in=1.0, values={par_fids[0]: {"color_g": 255, "intensity": 255}}))
pb.add_cue(Cue(number=3.0, label="Blau", fade_in=1.0, values={par_fids[0]: {"color_b": 255, "intensity": 255}}))
pe = state.playback_engine
ex = pe.get_executor(1, page=0); ex.stack = pb; ex.label = pb.name; ex.fader_function = "volume"

# ── Layout ───────────────────────────────────────────────────────────────────
widgets: list[dict] = []
geometry: dict[str, dict] = {}


def place(w, key, title, x, y, ww, hh):
    """Widget + Typ-Label darueber; Geometrie (logische Canvas-px) merken."""
    lbl = VCLabel(title)
    lbl.bank = 0; lbl.setGeometry(x, y, max(ww, 150), 20)
    widgets.append(lbl.to_dict())
    w.bank = 0
    w.setGeometry(x, y + 24, ww, hh)
    widgets.append(w.to_dict())
    geometry[key] = {"title": title, "x": x, "y": y, "w": max(ww, 150),
                     "h": (y + 24 + hh) - y, "wx": x, "wy": y + 24, "ww": ww, "wh": hh}


# ── Kalibrier-Kacheln (reine Farben, an festen Canvas-Koordinaten) ───────────
CAL1 = (255, 0, 255)   # Magenta  @ (4,4)
CAL2 = (0, 255, 255)   # Cyan     @ (1304,4)
CAL_SIZE = 14
c1 = VCColor(""); c1.color_r, c1.color_g, c1.color_b = CAL1; c1.with_intensity = False
c1.target = ColorTarget.PROGRAMMER; c1.bank = 0; c1.setGeometry(4, 4, CAL_SIZE, CAL_SIZE)
widgets.append(c1.to_dict())
c2 = VCColor(""); c2.color_r, c2.color_g, c2.color_b = CAL2; c2.with_intensity = False
c2.target = ColorTarget.PROGRAMMER; c2.bank = 0; c2.setGeometry(1304, 4, CAL_SIZE, CAL_SIZE)
widgets.append(c2.to_dict())

# ── Reihe 0 (y=24) ──────────────────────────────────────────────────────────
b = VCButton("Effekt an/aus"); b.action = ButtonAction.FUNCTION_TOGGLE; b.function_id = mtx.id
place(b, "VCButton", "Button (VCButton)", 30, 24, 160, 64)
sl = VCSlider("Tempo"); sl.mode = SliderMode.EFFECT_SPEED; sl.function_id = mtx.id
place(sl, "VCSlider", "Fader (VCSlider)", 230, 24, 60, 160)
co = VCColor("Rot"); co.color_r, co.color_g, co.color_b = 220, 30, 30; co.target = ColorTarget.ALL
place(co, "VCColor", "Farbe (VCColor)", 330, 24, 90, 90)
en = VCEncoder("Groesse"); en.param_key = ENC_KEY; en.function_id = ENC_FID
place(en, "VCEncoder", "Encoder (VCEncoder)", 460, 24, 100, 120)
st = VCStepper("Anzahl"); st.param_key = STEP_KEY; st.function_id = STEP_FID
place(st, "VCStepper", "Stepper (VCStepper)", 600, 24, 120, 80)
sd = VCSpeedDial("Tempo-Knoten"); sd.target_mode = SpeedTarget.SPEED_NODE; sd.tempo_bus_id = "A"; sd.role = "master"
place(sd, "VCSpeedDial", "Speed-Dial (VCSpeedDial)", 760, 24, 160, 150)

# ── Reihe 1 (y=210) ─────────────────────────────────────────────────────────
xy = VCXYPad("Pan/Tilt"); xy.mode = "position"; xy._fixture_ids = list(par_fids)
place(xy, "VCXYPad", "XY-Pad (VCXYPad)", 30, 210, 160, 160)
cl = VCCueList("Cueliste"); cl.stack_slot = 0
place(cl, "VCCueList", "Cue-Liste (VCCueList)", 230, 210, 210, 160)
ccl = VCColorList("Farb-Sequenz"); ccl.function_id = mtx.id
place(ccl, "VCColorList", "Chase-Liste (VCColorList)", 750, 210, 230, 80)
ec = VCEffectColors("Effekt-Farben"); ec.function_id = mtx.id
place(ec, "VCEffectColors", "Effekt-Farben (VCEffectColors)", 750, 316, 230, 86)

# ── Reihe 2 (y=426) ─────────────────────────────────────────────────────────
bpm = VCBpmDisplay("BPM"); bpm.tempo_bus_id = ""
place(bpm, "VCBpmDisplay", "BPM-Anzeige (VCBpmDisplay)", 30, 426, 190, 96)
bs = VCBusSelector("Tempo-Bus"); bs.buses = ["A", "B", "C", "D"]
place(bs, "VCBusSelector", "Tempo-Bus (VCBusSelector)", 260, 426, 210, 86)
si = VCSongInfo("Musik")
place(si, "VCSongInfo", "Musik-Info (VCSongInfo)", 510, 426, 220, 96)
exl = VCLabel("Beschriftung / Titel")
place(exl, "VCLabel", "Text-Label (VCLabel)", 770, 426, 220, 44)
ed = VCEffectDisplay("Effekt-Anzeige"); ed.function_id = mtx.id
place(ed, "VCEffectDisplay", "Effekt-Anzeige (VCEffectDisplay)", 770, 516, 210, 124)

# ── Reihe 3 (y=560) ─────────────────────────────────────────────────────────
fr = VCFrame("Rahmen / Gruppe")
place(fr, "VCFrame", "Container (VCFrame)", 30, 560, 240, 150)
ee = VCEffectEditor("Effekt-Editor"); ee.set_effect(mtx.id)
place(ee, "VCEffectEditor", "Effekt-Editor-Box (VCEffectEditor)", 320, 560, 380, 224)

# ── Speichern ────────────────────────────────────────────────────────────────
state._vc_layout = {"widgets": widgets}
state.programmer = {}
state.show_name = "VC Widgets Showcase"
save_show(OUT)
print("Gespeichert:", OUT)

geo_out = {
    "calibration": {
        "cal1": {"color": list(CAL1), "x": 4, "y": 4, "w": CAL_SIZE, "h": CAL_SIZE},
        "cal2": {"color": list(CAL2), "x": 1304, "y": 4, "w": CAL_SIZE, "h": CAL_SIZE},
    },
    "widgets": geometry,
}
with open(GEO, "w", encoding="utf-8") as f:
    json.dump(geo_out, f, indent=2, ensure_ascii=False)
print("Geometrie:", GEO)

# ── Verifikation ─────────────────────────────────────────────────────────────
ok, msg = load_show(OUT); print("Load:", ok, msg); assert ok
state = get_state()
vc = state._vc_layout.get("widgets", [])
from collections import Counter
types = Counter(w["type"] for w in vc)
print("Widget-Typen:", dict(types))
need = {"VCButton", "VCSlider", "VCColor", "VCXYPad", "VCSpeedDial", "VCEncoder", "VCStepper",
        "VCCueList", "VCSongInfo", "VCColorList", "VCEffectColors",
        "VCBpmDisplay", "VCBusSelector", "VCFrame", "VCLabel", "VCEffectEditor", "VCEffectDisplay"}
missing = need - set(types)
assert not missing, f"fehlend: {missing}"
print("FERTIG — alle 17 Typen vorhanden")
