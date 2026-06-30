"""VC-Elemente-Schaukasten: legt JEDEN der 15 VC-Widget-Typen einmal beschriftet
in ein Raster auf Bank 1 — als saubere Vorlage fuer die bebilderte Referenz.

Aufruf:  venv/Scripts/python.exe tools/build_vc_elements_showcase.py
Erzeugt: shows/VC_Elemente_Showcase.lshow
"""
from __future__ import annotations
import os, sys
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
from src.ui.virtualconsole.vc_button import VCButton, ButtonAction
from src.ui.virtualconsole.vc_slider import VCSlider, SliderMode
from src.ui.virtualconsole.vc_color import VCColor, ColorTarget
from src.ui.virtualconsole.vc_label import VCLabel
from src.ui.virtualconsole.vc_cuelist import VCCueList
from src.ui.virtualconsole.vc_speedial import VCSpeedDial, SpeedTarget
from src.ui.virtualconsole.vc_encoder import VCEncoder
from src.ui.virtualconsole.vc_color_list import VCColorList
from src.ui.virtualconsole.vc_song_info import VCSongInfo
from src.ui.virtualconsole.vc_bpm_display import VCBpmDisplay
from src.ui.virtualconsole.vc_bus_selector import VCBusSelector
from src.ui.virtualconsole.vc_effect_colors import VCEffectColors
from src.ui.virtualconsole.vc_xypad import VCXYPad
from src.ui.virtualconsole.vc_frame import VCFrame

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(_ROOT, "shows", "VC_Elemente_Showcase.lshow")

reset_show()
state = get_state()
fm = get_function_manager()
with Session(fdb_engine()) as s:
    par_pid = s.execute(select(FixtureProfile.id).where(FixtureProfile.short_name == "ZQ01424")).scalar_one()
addr = 1
par_fids = []
for i in range(4):
    state.add_fixture(PatchedFixture(fid=i + 1, label=f"PAR {i+1}", fixture_profile_id=par_pid,
                      mode_name="8-Kanal RGBW", universe=1, address=addr, channel_count=8,
                      manufacturer_name="Generic", fixture_name="Stage Light ZQ01424",
                      fixture_type="par"), undoable=False)
    par_fids.append(i + 1); addr += 8
state.base_levels = {f: {"intensity": 255} for f in par_fids}
state._rebuild_render_plan()

# Dummy-Effekt (fuer Farb-/Chase-/Effekt-Farben-Widgets) + Cueliste (fuer VCCueList)
mtx = fm.new_rgb_matrix("Demo-Chase")
mtx.algorithm = RgbAlgorithm.COLORFADE
mtx.fixture_grid = list(par_fids); mtx.cols, mtx.rows = len(par_fids), 1
mtx.colors = ColorSequence([(255, 0, 0), (0, 255, 0), (0, 0, 255)])
mtx.matrix_speed = 1.5
pb = state.new_cue_stack("Demo-Cueliste"); pb.mode = "loop"
pb.add_cue(Cue(number=1.0, label="Rot", fade_in=1.0, values={par_fids[0]: {"color_r": 255, "intensity": 255}}))
pb.add_cue(Cue(number=2.0, label="Blau", fade_in=1.0, values={par_fids[0]: {"color_b": 255, "intensity": 255}}))
pe = state.playback_engine
ex = pe.get_executor(1, page=0); ex.stack = pb; ex.label = pb.name; ex.fader_function = "volume"

widgets: list[dict] = []


def place(w, caption, x, y, ww, hh, type_label):
    """Widget + Typ-Label darueber ablegen."""
    lbl = VCLabel(type_label)
    lbl.bank = 0; lbl.setGeometry(x, y, max(ww, 150), 20)
    widgets.append(lbl.to_dict())
    w.bank = 0
    try:
        w.caption = caption
    except Exception:
        pass
    w.setGeometry(x, y + 24, ww, hh)
    widgets.append(w.to_dict())


# Kompaktes 5x3-Raster (passt auf einen Bildschirm, ohne Scrollen / Sidebar).
COL = [20, 250, 480, 710, 940]    # 5 Spalten-x
ROWY = [40, 290, 540]             # 3 Reihen-y

# Reihe 0
b = VCButton("Effekt an/aus"); b.action = ButtonAction.FUNCTION_TOGGLE; b.function_id = mtx.id
place(b, "Effekt an/aus", COL[0], ROWY[0], 150, 60, "VCButton — Steuertaste")
sl = VCSlider("Tempo"); sl.mode = SliderMode.EFFECT_SPEED; sl.function_id = mtx.id
place(sl, "Tempo", COL[1], ROWY[0], 56, 150, "VCSlider — Fader")
co = VCColor("Rot"); co.color_r, co.color_g, co.color_b = 255, 0, 0; co.target = ColorTarget.ALL
place(co, "Rot", COL[2], ROWY[0], 80, 80, "VCColor — Farb-Kachel")
xy = VCXYPad("Pan/Tilt"); xy.mode = "position"; xy._fixture_ids = list(par_fids)
place(xy, "Pan/Tilt", COL[3], ROWY[0], 150, 150, "VCXYPad — XY-Feld")
sd = VCSpeedDial("Tempo-Knoten"); sd.target_mode = SpeedTarget.SPEED_NODE; sd.tempo_bus_id = "A"; sd.role = "master"
place(sd, "Tempo-Knoten", COL[4], ROWY[0], 150, 140, "VCSpeedDial — Tempo-Rad")
# Reihe 1
en = VCEncoder("Groesse"); en.param_key = "size"; en.function_id = mtx.id
place(en, "Groesse", COL[0], ROWY[1], 96, 110, "VCEncoder — Drehgeber")
cl = VCCueList("Cueliste"); cl.stack_slot = 0
place(cl, "Cueliste", COL[1], ROWY[1], 200, 150, "VCCueList — Cue-Transport")
si = VCSongInfo("Musik")
place(si, "Musik", COL[2], ROWY[1], 210, 90, "VCSongInfo — Musik-Info")
ccl = VCColorList("Farb-Sequenz"); ccl.function_id = mtx.id
place(ccl, "Farb-Sequenz", COL[3], ROWY[1], 210, 72, "VCColorList — Farb-Sequenz")
# Reihe 2
ec = VCEffectColors("Effekt-Farben"); ec.function_id = mtx.id
place(ec, "Effekt-Farben", COL[0], ROWY[2], 210, 80, "VCEffectColors — Farb-Editor")
bpm = VCBpmDisplay("BPM"); bpm.tempo_bus_id = ""
place(bpm, "BPM", COL[1], ROWY[2], 180, 90, "VCBpmDisplay — Tempo-Anzeige")
bs = VCBusSelector("Tempo-Bus"); bs.buses = ["A", "B", "C", "D"]
place(bs, "Tempo-Bus", COL[2], ROWY[2], 200, 80, "VCBusSelector — Bus-Wahl")
exl = VCLabel("Beschriftung / Titel")
place(exl, "Beschriftung / Titel", COL[3], ROWY[2], 210, 40, "VCLabel — Text")
fr = VCFrame("Rahmen / Gruppe")
place(fr, "Rahmen / Gruppe", COL[4], ROWY[2], 220, 140, "VCFrame — Container")

state._vc_layout = {"widgets": widgets}
state.programmer = {}
state.show_name = "VC Elemente Showcase"
save_show(OUT)
print("Gespeichert:", OUT)
ok, msg = load_show(OUT); print("Load:", ok, msg); assert ok
state = get_state()
vc = state._vc_layout.get("widgets", [])
from collections import Counter
types = Counter(w["type"] for w in vc)
print("Widget-Typen:", dict(types))
# Jeder der 15 Typen genau einmal (VCLabel mehrfach: 14 Typ-Labels + 1 Beispiel)
need = {"VCButton","VCSlider","VCColor","VCXYPad","VCSpeedDial","VCEncoder","VCCueList",
        "VCSongInfo","VCColorList","VCEffectColors","VCBpmDisplay",
        "VCBusSelector","VCFrame","VCLabel"}
missing = need - set(types)
assert not missing, f"fehlend: {missing}"
print("FERTIG — alle 14 Typen vorhanden")
