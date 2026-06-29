"""LIVE-EDIT-SHOW — vordefinierte Effekte live einmappen & bearbeiten (Quadranten).

Davids Wunsch „Live-Bearbeitung statt Live-Programming": eine Bank, in 4×4-Quadranten
geteilt. Pro Quadrant wählt man oben einen laufenden Effekt; die Tasten/Farben/Fader
desselben Quadranten **bearbeiten dann genau diesen Effekt** (Edit-Slot-Mechanik):

  ┌───────────────────────┬───────────────────────┐
  │ TL  MOVING HEADS (MH) │ TR  MATRIX (MX)       │
  │ Reihe1: Effekt wählen │ Reihe1: Effekt wählen │
  │ Reihe2: Aktionen      │ Reihe2: Aktionen      │
  │ Reihe3/4: MH-Looks    │ Reihe3: color1-Recolor│
  │                       │ Reihe4: Sequence-Farbe│
  ├───────────────────────┼───────────────────────┤
  │ BL  PAR-Farben + Gr.  │ BR  Strobo/Utility    │
  └───────────────────────┴───────────────────────┘

Fader unten: F1 MH-Speed · F2 MH-Größe (Edit-Slot „MH") · F4 MX-Speed · F5 MX-Master
· F6 MX-Param (Edit-Slot „MX") · F8 Dimmer · F9 Master.

Setup: APC mini (mk2) + 4× PAR (ZQ01424) + 2× Moving Head (ZQ02001).
Aufruf:  venv/Scripts/python.exe tools/build_live_edit_show.py
Erzeugt: shows/Live_Edit.lshow
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
from src.core.app_state import get_state, get_channels_for_patched
from src.core.database.fixture_db import engine as fdb_engine
from src.core.database.models import PatchedFixture, FixtureProfile, FixtureGroup
from src.core.engine.function_manager import get_function_manager
from src.core.engine.function import RunOrder, Direction
from src.core.engine.chaser import ChaserStep
from src.core.engine.rgb_matrix import RgbAlgorithm, ColorSequence
from src.core.engine.efx import EfxFixture, EfxAlgorithm
from src.core.show.show_file import reset_show, save_show, load_show
from src.ui.virtualconsole.vc_button import VCButton, ButtonAction
from src.ui.virtualconsole.vc_color import VCColor, ColorTarget
from src.ui.virtualconsole.vc_slider import VCSlider, SliderMode
from src.ui.virtualconsole.vc_label import VCLabel

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(_ROOT, "shows", "Live_Edit.lshow")
TRACK0 = 100


def profile_id(short: str) -> int:
    with Session(fdb_engine()) as s:
        pid = s.execute(select(FixtureProfile.id).where(
            FixtureProfile.short_name == short)).scalar_one_or_none()
    if pid is None:
        raise SystemExit(f"Profil '{short}' fehlt — bitte App einmal starten.")
    return int(pid)


# ── Patch ──────────────────────────────────────────────────────────────────────
reset_show()
state = get_state()
fm = get_function_manager()
PAR_PID, MH_PID = profile_id("ZQ01424"), profile_id("ZQ02001")

par_fids: list[int] = []
addr = 1
for i in range(4):
    fid = i + 1
    state.add_fixture(PatchedFixture(
        fid=fid, label=f"PAR {i + 1}", fixture_profile_id=PAR_PID,
        mode_name="8-Kanal RGBW", universe=1, address=addr, channel_count=8,
        manufacturer_name="Generic", fixture_name="Stage Light ZQ01424",
        fixture_type="par"), undoable=False)
    par_fids.append(fid); addr += 8

mh_left, mh_right = 5, 6
for fid, lbl, a in ((mh_left, "MH Links", 33), (mh_right, "MH Rechts", 44)):
    state.add_fixture(PatchedFixture(
        fid=fid, label=lbl, fixture_profile_id=MH_PID, mode_name="11-Kanal",
        universe=1, address=a, channel_count=11, manufacturer_name="U King",
        fixture_name="ZQ02001 Mini Moving Head", fixture_type="moving_head"), undoable=False)
mh_fids = [mh_left, mh_right]

fixtures = state.get_patched_fixtures()
chan_of = {f.fid: {c.attribute: c.channel_number
                   for c in get_channels_for_patched(f)} for f in fixtures}
state.base_levels = {fid: {"intensity": 255} for fid in par_fids}
state._rebuild_render_plan()

with state._session() as s:
    s.execute(delete(FixtureGroup))
    s.add(FixtureGroup(name="PAR-Reihe", cols=4, rows=1,
                       positions_json=json.dumps({f"{i},0": par_fids[i] for i in range(4)})))
    s.add(FixtureGroup(name="Moving Heads", cols=2, rows=1,
                       positions_json=json.dumps({"0,0": mh_left, "1,0": mh_right})))
    s.commit()


# ── Funktionen ───────────────────────────────────────────────────────────────
def matrix(name, algo, speed=3.0, params=None):
    m = fm.new_rgb_matrix(name)
    m.algorithm = algo; m.fixture_grid = list(par_fids); m.cols = len(par_fids); m.rows = 1
    m.matrix_speed = speed
    m.colors = ColorSequence([(255, 0, 0), (0, 0, 255), (0, 255, 0)])
    if params:
        m.params = params
    return m


def mh_efx(name, algo):
    e = fm.new_efx(name); e.algorithm = algo
    e.fixtures = [EfxFixture(fid=mh_left), EfxFixture(fid=mh_right)]
    e.speed_hz = 0.4; e.spread = 0.0; e.open_beam = True; e.width = e.height = 110.0
    return e


def mh_scene(name, **attrs):
    sc = fm.new_scene(name)
    for fid in mh_fids:
        cm = chan_of[fid]
        for attr, val in attrs.items():
            if attr in cm:
                sc.set_value(fid, cm[attr], val)
    return sc


# MH-Effekte (Slot „MH")
mh_eight = mh_efx("MH Acht", EfxAlgorithm.EIGHT)
mh_circle = mh_efx("MH Kreis", EfxAlgorithm.CIRCLE)
mh_triangle = mh_efx("MH Dreieck", EfxAlgorithm.TRIANGLE)
mh_random = mh_efx("MH Random", EfxAlgorithm.RANDOM)
MH_FX = [mh_eight, mh_circle, mh_triangle, mh_random]
# MH-Looks (Position + Farbrad)
mh_looks = [mh_scene("Pos Center", pan=128, tilt=128, intensity=255, shutter=4),
            mh_scene("Pos Publikum", pan=128, tilt=180, intensity=255, shutter=4),
            mh_scene("MH Rot", color_wheel=14, intensity=255, shutter=4),
            mh_scene("MH Blau", color_wheel=34, intensity=255, shutter=4),
            mh_scene("MH Grün", color_wheel=54, intensity=255, shutter=4),
            mh_scene("MH Gelb", color_wheel=74, intensity=255, shutter=4),
            mh_scene("MH Weiß", color_wheel=0, intensity=255, shutter=4),
            mh_scene("Gobo", gobo_wheel=190, intensity=255, shutter=4)]

# Matrix-Effekte (Slot „MX")
mx_chase = matrix("Mtx Chase", RgbAlgorithm.CHASE, speed=4.0, params={"axis": "H", "movement": "normal"})
mx_fade = matrix("Mtx Color-Fade", RgbAlgorithm.COLORFADE, speed=1.0, params={"hold": 0.2})
mx_fire = matrix("Mtx Feuer", RgbAlgorithm.FIRE, speed=2.0)
mx_plasma = matrix("Mtx Plasma", RgbAlgorithm.SINEPLASMA, speed=1.2)
MX_FX = [mx_chase, mx_fade, mx_fire, mx_plasma]

# Strobe-Overlay (nur Dimmer/Intensität — überlagert eine Farb-Matrix als eigene Ebene)
st_all = fm.new_scene("Dim alle")
st_off = fm.new_scene("Dim aus")
for fid in par_fids:
    if "intensity" in chan_of[fid]:
        st_all.set_value(fid, chan_of[fid]["intensity"], 255)
        st_off.set_value(fid, chan_of[fid]["intensity"], 0)
strobe_overlay = fm.new_chaser("Strobe-Overlay")
strobe_overlay.run_order, strobe_overlay.direction = RunOrder.Loop, Direction.Forward
for sid in (st_all.id, st_off.id):
    strobe_overlay.steps.append(ChaserStep(function_id=sid, fade_in=0.0, hold=0.04, fade_out=0.0))


# ════════════════════════════════════════════════════════════════════════════
#  VIRTUAL CONSOLE — eine Bank, 4 Quadranten
# ════════════════════════════════════════════════════════════════════════════
PAD, GAP, X0, Y0 = 60, 6, 20, 70
STEP = PAD + GAP
GRID_BOTTOM = Y0 + 8 * STEP
TY = GRID_BOTTOM + 4
Y_FAD = GRID_BOTTOM + 34
FAD_H = 142
widgets: list[dict] = []
BANK_ALL = -1
B_MAIN = 0


def qnote(quadrant, qr, qc):
    """APC-Note für (Quadrant TL/TR/BL/BR, Zeile 0..3, Spalte 0..3)."""
    r = qr + (4 if quadrant in ("BL", "BR") else 0)
    c = qc + (4 if quadrant in ("TR", "BR") else 0)
    return (7 - r) * 8 + c


def pad_xy(note):
    row, col = note // 8, note % 8
    return X0 + col * STEP, Y0 + (7 - row) * STEP


def _add(w, x, y, ww, hh, bank):
    w.bank = bank; w.setGeometry(x, y, ww, hh); widgets.append(w.to_dict())


def fx_select(fn, note, accent, slot):
    """Effekt-Wahl-Pad: startet den Effekt UND macht ihn zum Edit-Ziel des Slots
    (pro Slot exklusiv über die Edit-Slot-Mechanik)."""
    b = VCButton(fn.name)
    b.action = ButtonAction.FUNCTION_TOGGLE; b.function_id = fn.id
    b.edit_slot = slot; b.pad_style = "pulse"; b.clear_programmer = fn.name.startswith("Mtx")
    b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, note
    b._bg_color.setNamedColor(accent)
    x, y = pad_xy(note); _add(b, x, y, PAD, PAD, B_MAIN)


def edit_action(name, note, accent, key, slot):
    b = VCButton(name); b.action = ButtonAction.EFFECT_ACTION
    b.effect_action_key = key; b.edit_slot = slot; b.pad_style = "solid"
    b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, note
    b._bg_color.setNamedColor(accent)
    x, y = pad_xy(note); _add(b, x, y, PAD, PAD, B_MAIN)


def func_toggle(fn, note, accent):
    b = VCButton(fn.name); b.action = ButtonAction.FUNCTION_TOGGLE; b.function_id = fn.id
    b.pad_style = "solid"
    b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, note
    b._bg_color.setNamedColor(accent)
    x, y = pad_xy(note); _add(b, x, y, PAD, PAD, B_MAIN)


def recolor_tile(name, note, r, g, b, target, slot):
    c = VCColor(name); c.color_r, c.color_g, c.color_b = r, g, b
    c.with_intensity = False; c.target = target; c.edit_slot = slot
    c.midi_type, c.midi_ch, c.midi_data1 = "note_on", 0, note
    x, y = pad_xy(note); _add(c, x, y, PAD, PAD, B_MAIN)


def par_color(name, note, r, g, b, w=0):
    c = VCColor(name); c.color_r, c.color_g, c.color_b, c.color_w = r, g, b, w
    c.with_intensity = True; c.target = ColorTarget.PROGRAMMER
    c.midi_type, c.midi_ch, c.midi_data1 = "note_on", 0, note
    x, y = pad_xy(note); _add(c, x, y, PAD, PAD, B_MAIN)


def select_group(name, group, note, accent="#2a4a6a"):
    b = VCButton(name); b.action = ButtonAction.SELECT_GROUP; b.group_name = group
    b.pad_style = "solid"
    b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, note
    b._bg_color.setNamedColor(accent)
    x, y = pad_xy(note); _add(b, x, y, PAD, PAD, B_MAIN)


def fader(caption, col, mode, edit_slot="", param_key="speed", midi_cc=-1, value=0,
          submaster_slot=None, bank=B_MAIN):
    s = VCSlider(caption); s.mode = mode; s.edit_slot = edit_slot; s.param_key = param_key
    if submaster_slot is not None:
        s.function_id = submaster_slot
    s.midi_cc, s.midi_ch = midi_cc, 0; s._value = value
    x = X0 + col * STEP + 2; _add(s, x, Y_FAD, 56, FAD_H, bank)


def label(text, x, y, ww, bank=B_MAIN, hh=18):
    _add(VCLabel(text), x, y, ww, hh, bank)


# ── TL — MOVING HEADS (Slot „MH") ───────────────────────────────────────────
for i, fn in enumerate(MH_FX):                       # Reihe 1: Effekt wählen
    fx_select(fn, qnote("TL", 0, i), "#1f3a6a", "MH")
for i, (nm, key) in enumerate([("Richtung", "reverse_direction"), ("Bounce", "toggle_bounce"),
                               ("Relativ", "toggle_relative"), ("Neustart", "restart")]):
    edit_action(nm, qnote("TL", 1, i), "#33506a", key, "MH")   # Reihe 2: Aktionen
for i, lk in enumerate(mh_looks[:4]):                # Reihe 3: Position/Look
    func_toggle(lk, qnote("TL", 2, i), "#2a3a5a")
for i, lk in enumerate(mh_looks[4:8]):               # Reihe 4: Farbrad/Gobo
    func_toggle(lk, qnote("TL", 3, i), "#2a3a5a")

# ── TR — MATRIX (Slot „MX") ─────────────────────────────────────────────────
for i, fn in enumerate(MX_FX):                       # Reihe 1: Effekt wählen
    fx_select(fn, qnote("TR", 0, i), "#7a5b00", "MX")
for i, (nm, key) in enumerate([("Form -", "prev_algorithm"), ("Form +", "next_algorithm"),
                               ("Freeze", "toggle_freeze"), ("Reset", "clear_live_override")]):
    edit_action(nm, qnote("TR", 1, i), "#5a4a00", key, "MX")   # Reihe 2: Aktionen
_RC = [("Rot", 255, 0, 0), ("Grün", 0, 255, 0), ("Blau", 0, 0, 255), ("Weiß", 255, 255, 255)]
for i, (nm, r, g, b) in enumerate(_RC):              # Reihe 3: color1-Recolor
    recolor_tile(f"C1 {nm}", qnote("TR", 2, i), r, g, b, ColorTarget.EFFECT_C1, "MX")
_SEQ = [("Rot", 255, 0, 0), ("Grün", 0, 255, 0), ("Blau", 0, 0, 255), ("Gelb", 255, 220, 0)]
for i, (nm, r, g, b) in enumerate(_SEQ):             # Reihe 4: Sequence-Farbe
    recolor_tile(f"Seq {nm}", qnote("TR", 3, i), r, g, b, ColorTarget.EFFECT, "MX")

# ── BL — PAR-Farben + Gruppen ────────────────────────────────────────────────
_PARCOL = [("Rot", 255, 0, 0, 0), ("Grün", 0, 255, 0, 0), ("Blau", 0, 0, 255, 0), ("Weiß", 255, 255, 255, 255),
           ("Amber", 255, 140, 0, 0), ("Cyan", 0, 255, 255, 0), ("Magenta", 255, 0, 255, 0), ("Warm", 255, 130, 40, 60)]
for i, (nm, r, g, b, w) in enumerate(_PARCOL):
    par_color(nm, qnote("BL", i // 4, i % 4), r, g, b, w)
select_group("Gr: PARs", "PAR-Reihe", qnote("BL", 2, 0))
select_group("Gr: MHs", "Moving Heads", qnote("BL", 2, 1))

# ── BR — Strobo-Overlay + Utility ───────────────────────────────────────────
func_toggle(strobe_overlay, qnote("BR", 0, 0), "#511")
b = VCButton("Blackout"); b.action = ButtonAction.BLACKOUT; b.pad_style = "solid"
b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, qnote("BR", 0, 1); b._bg_color.setNamedColor("#2a0000")
_x, _y = pad_xy(qnote("BR", 0, 1)); _add(b, _x, _y, PAD, PAD, B_MAIN)

# ── Fader (Edit-Slots) + global ──────────────────────────────────────────────
fader("MH-Speed", 0, SliderMode.EFFECT_SPEED, edit_slot="MH", midi_cc=48, value=64)
fader("MH-Größe", 1, SliderMode.EFFECT_PARAM, edit_slot="MH", param_key="size", midi_cc=49, value=110)
fader("MX-Speed", 3, SliderMode.EFFECT_SPEED, edit_slot="MX", midi_cc=51, value=64)
fader("MX-Master", 4, SliderMode.EFFECT_INTENSITY, edit_slot="MX", midi_cc=52, value=255)
fader("MX-Param", 5, SliderMode.EFFECT_PARAM, edit_slot="MX", param_key="white_amount", midi_cc=53, value=0)
fader("Dimmer", 7, SliderMode.SUBMASTER, submaster_slot=0, midi_cc=55, value=255, bank=BANK_ALL)
fader("Master", 8, SliderMode.GRANDMASTER, midi_cc=56, value=255, bank=BANK_ALL)

# ── Track-Tasten ─────────────────────────────────────────────────────────────
for i, (nm, act, col) in enumerate([
        ("Clear", ButtonAction.CLEAR, "#4a3a10"), ("Stop All", ButtonAction.STOP_ALL, "#4a1010"),
        ("Blackout", ButtonAction.BLACKOUT, "#2a0000"), ("Tap", ButtonAction.TAP, "#103a3a")]):
    tb = VCButton(nm); tb.action = act; tb.pad_style = "solid"
    tb.midi_type, tb.midi_ch, tb.midi_data1 = "note_on", 0, TRACK0 + i
    tb._bg_color.setNamedColor(col)
    _add(tb, X0 + i * 64, TY, 60, 26, BANK_ALL)

label("LIVE-EDIT  —  oben links Moving-Head-Effekt wählen, oben rechts Matrix-Effekt. "
      "Tasten/Farben/Fader des Quadranten bearbeiten GENAU den gewählten Effekt.",
      X0, 6, 1150, BANK_ALL)
label("◄ MOVING HEADS (Slot MH):  Reihe1 Effekt · Reihe2 Aktionen · Reihe3/4 Looks", X0, 30, 560)
label("MATRIX (Slot MX) ►:  Reihe1 Effekt · Reihe2 Form/Freeze · Reihe3 color1 · Reihe4 Sequence",
      X0 + 4 * STEP, 30, 560)
label("Fader: F1 MH-Speed · F2 MH-Größe | F4 MX-Speed · F5 MX-Master · F6 MX-Param | F8 Dimmer · F9 Master",
      X0, Y_FAD + FAD_H + 4, 1150, BANK_ALL)

state._vc_layout = {"widgets": widgets}

# ── Speichern + Verifikation ─────────────────────────────────────────────────
state.programmer = {}
state.show_name = "Live Edit"
save_show(OUT)
print(f"Gespeichert: {OUT}")
ok, msg = load_show(OUT)
print("Load:", ok, msg)
assert ok, f"Show laedt nicht: {msg}"

from collections import Counter
vc = state._vc_layout.get("widgets", [])
types = Counter(w["type"] for w in vc)

# Edit-Slot-Mechanik vertreten?
mh_sel = [w for w in vc if w.get("edit_slot") == "MH" and w.get("action") == "FunctionToggle"]
mx_sel = [w for w in vc if w.get("edit_slot") == "MX" and w.get("action") == "FunctionToggle"]
assert len(mh_sel) == 4 and len(mx_sel) == 4, (len(mh_sel), len(mx_sel))
mh_act = [w for w in vc if w.get("edit_slot") == "MH" and w.get("action") == "EffectAction"]
mx_act = [w for w in vc if w.get("edit_slot") == "MX" and w.get("action") == "EffectAction"]
assert len(mh_act) == 4 and len(mx_act) == 4, (len(mh_act), len(mx_act))
recolor = [w for w in vc if w.get("edit_slot") == "MX" and w.get("type") == "VCColor"]
assert len(recolor) == 8, f"Recolor-Kacheln (Slot MX): {len(recolor)}"
edit_faders = [w for w in vc if w.get("edit_slot") in ("MH", "MX")
               and w.get("mode", "").startswith("Effect")]
assert len(edit_faders) == 5, f"Edit-Fader: {len(edit_faders)}"
assert any(w.get("function_id") == strobe_overlay.id for w in vc), "Strobe-Overlay fehlt"
maxy = max((w.get("y", 0) + w.get("h", 0)) for w in vc)
assert maxy < 820, f"zu hoch: {maxy}"

print(f"Funktionen: {len(fm.all())}  VC-Widgets: {len(vc)}  Typen={dict(types)}")
print(f"  MH-Select={len(mh_sel)} MX-Select={len(mx_sel)}  MH-Akt={len(mh_act)} MX-Akt={len(mx_act)}  "
      f"Recolor(MX)={len(recolor)}  Edit-Fader={len(edit_faders)}")
print("  [OK] Quadranten-Live-Edit: Effekt wählen -> Slot-Ziel; Fader/Farben/Aktionen editieren den Slot")
print("FERTIG")
