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


# ── Automatischer Umbruch statt handgesetzter Reihen (CDX, Codex zu PR #571) ──
#
# ⚠️ **Die Reihen waren von Hand gesetzt, und fuenf Bereiche ueberlappten sich.**
# Aufgefallen ist einer davon: der Speed-Dial (190 px hoch, y=78..268) lag unter
# der ab y=210 beginnenden Chase-Liste, und im fertigen `VCSpeedDial.png`
# fehlten dadurch SYNC und die BPM-Zeile — beide zeichnet das Widget an seiner
# UNTERKANTE. Die anderen vier fand erst die maschinelle Pruefung
# (`tests/test_vc_widgets_showcase_layout.py`), und sie haben alle dieselbe
# Ursache:
#
#     lbl.setGeometry(x, y, max(ww, 150), 20)
#                            ^^^^^^^^^^^
# Das TYP-LABEL ist mindestens 150 px breit, auch wenn das Widget schmaler ist.
# Der Fader ist 60 px breit, sein Label 150 — wer die Reihe nach den WIDGETS
# ausrichtet, laesst die Labels ineinanderlaufen. Betroffen waren Fader, Farbe,
# Encoder, Stepper und die Cue-Liste. Kein Bild war offensichtlich kaputt; sie
# trugen nur alle ein Stueck vom Nachbarn am Rand.
#
# **Platz war nie das Problem.** Am Kalibrier-Quadrat im Vollbild nachgemessen:
# der Zuschnitt laeuft 1:1 und der aufgenommene Bereich reicht logisch bis
# 1600x900 — belegt waren 990x808. Die Ueberlappungen waren also reine
# Handarbeit, nicht Platznot.
#
# Deshalb rechnet das Layout die Reihen jetzt selbst: Umbruch bei `_MAX_X`,
# Zeilenhoehe = hoechstes Widget der Reihe. Ein neues Widget kann damit keine
# Ueberlappung mehr erzeugen, egal wo es eingefuegt wird.
_MAX_X = 1560          # letzter belegbarer x (gemessen: sichtbar bis 1600)
_START_X, _START_Y = 30, 54    # y=54: unter den Kalibrier-Kacheln (CAL_SIZE=40)
# ⚠️ Die Luecke muss GROESSER sein als der doppelte Zuschnitt-Rand.
# `crop_vc_widgets.py` gibt jedem Bild `pad` Pixel Luft (Default 8) — auf BEIDEN
# Seiten. Bei 10 px Abstand griffen zwei Ausschnitte deshalb 6 px ineinander,
# und jedes Bild trug einen schmalen Streifen seines Nachbarn am Rand. Das fiel
# nicht auf, weil dieser Streifen meist leerer Hintergrund ist — bis er es
# einmal nicht ist. 24 > 2*8 laesst auch bei erhoehtem `pad` noch Luft.
_LUECKE, _REIHEN_ABSTAND = 24, 20

_cursor = {"x": _START_X, "y": _START_Y, "hoehe": 0}


def reihe(w, key, title, ww, hh):
    """Wie `place`, aber die Position rechnet sich aus dem bisherigen Lauf.

    Reihenfolge = Aufrufreihenfolge; sie bleibt damit thematisch lesbar
    (Bedienelemente, dann Anzeigen, dann Container) und nicht nach Groesse
    sortiert.
    """
    breite = max(ww, 150)                 # das Label ist der breitere Teil
    if _cursor["x"] + breite > _MAX_X:
        _cursor["y"] += 24 + _cursor["hoehe"] + _REIHEN_ABSTAND
        _cursor["x"] = _START_X
        _cursor["hoehe"] = 0
    place(w, key, title, _cursor["x"], _cursor["y"], ww, hh)
    _cursor["x"] += breite + _LUECKE
    _cursor["hoehe"] = max(_cursor["hoehe"], hh)


# ── Kalibrier-Kacheln (reine Farben, an festen Canvas-Koordinaten) ───────────
#
# ⚠️ Die logische Groesse muss mindestens so gross sein, wie das Widget WIRKLICH
# gerendert wird. Mit den urspruenglichen 14x14 belegte die Kachel real 40x30 px
# (VCColor hat eine Mindestgroesse) — sie ragte damit in die erste Widget-Reihe
# und stand als magenta Streifen in jedem VCButton-Bild. Ausserdem war die
# Eigengroesse dadurch als Massstab unbrauchbar; `crop_vc_widgets.py` kalibriert
# seither ueber den ABSTAND der beiden Kacheln, was von Mindestgroessen
# unabhaengig ist. Die Groesse hier ist trotzdem angehoben, damit die Geometrie
# den Platz einplant, den die Kachel tatsaechlich braucht.
CAL1 = (255, 0, 255)   # Magenta  @ (4,4)
CAL2 = (0, 255, 255)   # Cyan     @ (1304,4)
CAL_SIZE = 40
c1 = VCColor(""); c1.color_r, c1.color_g, c1.color_b = CAL1; c1.with_intensity = False
c1.target = ColorTarget.PROGRAMMER; c1.bank = 0; c1.setGeometry(4, 4, CAL_SIZE, CAL_SIZE)
widgets.append(c1.to_dict())
c2 = VCColor(""); c2.color_r, c2.color_g, c2.color_b = CAL2; c2.with_intensity = False
c2.target = ColorTarget.PROGRAMMER; c2.bank = 0; c2.setGeometry(1304, 4, CAL_SIZE, CAL_SIZE)
widgets.append(c2.to_dict())

# ── Bedienelemente ───────────────────────────────────────────────────────────
# Reihenfolge = Anordnung; den Umbruch rechnet `reihe()` (s. oben).
b = VCButton("Effekt an/aus"); b.action = ButtonAction.FUNCTION_TOGGLE; b.function_id = mtx.id
reihe(b, "VCButton", "Button (VCButton)", 160, 64)
sl = VCSlider("Tempo"); sl.mode = SliderMode.EFFECT_SPEED; sl.function_id = mtx.id
reihe(sl, "VCSlider", "Fader (VCSlider)", 60, 160)
co = VCColor("Rot"); co.color_r, co.color_g, co.color_b = 220, 30, 30; co.target = ColorTarget.ALL
reihe(co, "VCColor", "Farbe (VCColor)", 90, 90)
en = VCEncoder("Groesse"); en.param_key = ENC_KEY; en.function_id = ENC_FID
reihe(en, "VCEncoder", "Encoder (VCEncoder)", 100, 120)
st = VCStepper("Anzahl"); st.param_key = STEP_KEY; st.function_id = STEP_FID
reihe(st, "VCStepper", "Stepper (VCStepper)", 120, 80)
sd = VCSpeedDial("Tempo-Knoten"); sd.target_mode = SpeedTarget.SPEED_NODE; sd.tempo_bus_id = "A"; sd.role = "master"
reihe(sd, "VCSpeedDial", "Speed-Dial (VCSpeedDial)", 160, 190)
xy = VCXYPad("Pan/Tilt"); xy.mode = "position"; xy._fixture_ids = list(par_fids)
reihe(xy, "VCXYPad", "XY-Pad (VCXYPad)", 160, 160)
cl = VCCueList("Cueliste"); cl.stack_slot = 0
reihe(cl, "VCCueList", "Cue-Liste (VCCueList)", 210, 160)

# ── Listen & Anzeigen ────────────────────────────────────────────────────────
ccl = VCColorList("Farb-Sequenz"); ccl.function_id = mtx.id
reihe(ccl, "VCColorList", "Chase-Liste (VCColorList)", 230, 80)
ec = VCEffectColors("Effekt-Farben"); ec.function_id = mtx.id
reihe(ec, "VCEffectColors", "Effekt-Farben (VCEffectColors)", 230, 86)
bpm = VCBpmDisplay("BPM"); bpm.tempo_bus_id = ""
reihe(bpm, "VCBpmDisplay", "BPM-Anzeige (VCBpmDisplay)", 190, 96)
bs = VCBusSelector("Tempo-Bus"); bs.buses = ["A", "B", "C", "D"]
reihe(bs, "VCBusSelector", "Tempo-Bus (VCBusSelector)", 210, 86)
si = VCSongInfo("Musik")
reihe(si, "VCSongInfo", "Musik-Info (VCSongInfo)", 220, 96)
exl = VCLabel("Beschriftung / Titel")
reihe(exl, "VCLabel", "Text-Label (VCLabel)", 220, 44)

# ── Container & Editor ───────────────────────────────────────────────────────
ed = VCEffectDisplay("Effekt-Anzeige"); ed.function_id = mtx.id
reihe(ed, "VCEffectDisplay", "Effekt-Anzeige (VCEffectDisplay)", 210, 124)
fr = VCFrame("Rahmen / Gruppe")
reihe(fr, "VCFrame", "Container (VCFrame)", 240, 150)
ee = VCEffectEditor("Effekt-Editor"); ee.set_effect(mtx.id)
reihe(ee, "VCEffectEditor", "Effekt-Editor-Box (VCEffectEditor)", 380, 224)

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
