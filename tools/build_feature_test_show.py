"""FEATURE-TEST-SHOW — spielt ALLE neuen Funktionen vom 2026-06-12 durch.

Davids Setup (4 PAR ZQ01424 + 2 MH ZQ02001 + APC mini mk2). Jede APC-SCENE-Taste
(rechts) = eine Test-Seite mit EINEM Schwerpunkt, damit man die neuen Features
gezielt auf der Hardware ausprobieren kann:

  Seite 1  MATRIX BUILDER   #3 Form +/- (durch alle Algorithmen blättern),
                            #5 Live-Recolor color1/2/3 + Sequence,
                            #6 Feedback-Fenster der Color-Sequence.
  Seite 2  CHASE BAUEN      #2 echter Szenen-Chaser live: Look in den Programmer
                            legen -> „Schritt aufnehmen" -> Start. Letzten/Alle
                            löschen, Feedback zeigt die Schritt-Zahl.
  Seite 3  MOVING HEADS     #7 relative Bewegung (erst zielen, dann Acht relativ
                            um den Punkt) + #8 XY-Feld aufziehen (EFX fährt im Feld).
  Seite 4  FARBE & KONTEXT  #4 PAR-Dim-Fader fest auf die PAR-Gruppe,
                            #9 Farb-Kacheln grauen aus, wenn die Matrix die Farbe besitzt.

Universell: Track-Tasten Clear/Stop All/Blackout; Fader F6 Dimmer, F7 Speed, F9 Master.

Aufruf:  venv/Scripts/python.exe tools/build_feature_test_show.py
Erzeugt: shows/Feature_Test.lshow
"""
from __future__ import annotations
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
_app = QApplication.instance() or QApplication([])

from sqlalchemy import select, delete
from sqlalchemy.orm import Session
from src.core.app_state import get_state, get_channels_for_patched
from src.core.database.fixture_db import engine as fdb_engine
from src.core.database.models import PatchedFixture, FixtureProfile, FixtureGroup
from src.core.engine.function_manager import get_function_manager
from src.core.engine.rgb_matrix import RgbAlgorithm, ColorSequence
from src.core.engine.efx import EfxFixture, EfxAlgorithm
from src.core.show.show_file import reset_show, save_show, load_show
from src.ui.virtualconsole.vc_button import VCButton, ButtonAction
from src.ui.virtualconsole.vc_color import VCColor, ColorTarget
from src.ui.virtualconsole.vc_slider import VCSlider, SliderMode
from src.ui.virtualconsole.vc_label import VCLabel
from src.ui.virtualconsole.vc_color_list import VCColorList
from src.ui.virtualconsole.vc_xypad import VCXYPad

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(_ROOT, "shows", "Feature_Test.lshow")
TRACK0 = 100   # APC mini mk2


def profile_id(short: str) -> int:
    with Session(fdb_engine()) as s:
        pid = s.execute(
            select(FixtureProfile.id).where(FixtureProfile.short_name == short)
        ).scalar_one_or_none()
    if pid is None:
        raise SystemExit(f"Profil '{short}' fehlt — bitte App einmal starten.")
    return int(pid)


# ── 0) Basis ────────────────────────────────────────────────────────────────
reset_show()
state = get_state()
fm = get_function_manager()
PAR_PID = profile_id("ZQ01424")
MH_PID = profile_id("ZQ02001")

# ── 1) Patch ──────────────────────────────────────────────────────────────────
par_fids: list[int] = []
addr = 1
for i in range(4):
    fid = i + 1
    state.add_fixture(PatchedFixture(
        fid=fid, label=f"PAR {i + 1}", fixture_profile_id=PAR_PID,
        mode_name="8-Kanal RGBW", universe=1, address=addr, channel_count=8,
        manufacturer_name="Generic", fixture_name="Stage Light ZQ01424",
        fixture_type="par"), undoable=False)
    par_fids.append(fid)
    addr += 8

mh_left, mh_right = 5, 6
for fid, label_, a in ((mh_left, "MH Links", 33), (mh_right, "MH Rechts", 44)):
    state.add_fixture(PatchedFixture(
        fid=fid, label=label_, fixture_profile_id=MH_PID,
        mode_name="11-Kanal", universe=1, address=a, channel_count=11,
        manufacturer_name="U King", fixture_name="ZQ02001 Mini Moving Head",
        fixture_type="moving_head"), undoable=False)
mh_fids = [mh_left, mh_right]

fixtures = state.get_patched_fixtures()
chan_of = {f.fid: {c.attribute: c.channel_number
                   for c in get_channels_for_patched(f)} for f in fixtures}
state.base_levels = {fid: {"intensity": 255} for fid in par_fids}
state._rebuild_render_plan()

# ── 2) Gruppen ────────────────────────────────────────────────────────────────
with state._session() as s:
    s.execute(delete(FixtureGroup))
    s.add(FixtureGroup(name="PAR-Reihe", cols=4, rows=1,
                       positions_json=json.dumps({f"{i},0": par_fids[i] for i in range(4)})))
    s.add(FixtureGroup(name="Moving Heads", cols=2, rows=1,
                       positions_json=json.dumps({"0,0": mh_left, "1,0": mh_right})))
    s.commit()


# ════════════════════════════════════════════════════════════════════════════
#  3) FUNKTIONEN
# ════════════════════════════════════════════════════════════════════════════

def matrix(name, algo, c1=(255, 0, 0), c2=(0, 0, 255), c3=(0, 255, 0), speed=3.0, params=None):
    m = fm.new_rgb_matrix(name)
    m.algorithm = algo; m.fixture_grid = list(par_fids); m.cols = len(par_fids); m.rows = 1
    m.color1, m.color2, m.color3 = c1, c2, c3; m.matrix_speed = speed
    if params:
        m.params = params
    return m


# Seite 1: EINE Builder-Matrix (Form +/- blättert durch alle Algorithmen).
matrix_builder = matrix("Matrix-Builder", RgbAlgorithm.CHASE, speed=3.0,
                        params={"axis": "H", "movement": "normal"})
matrix_builder.colors = ColorSequence([(255, 0, 0), (0, 0, 255), (0, 255, 0)])

# Seite 2: echter Szenen-Chaser, der LIVE aufgenommen wird (startet leer).
live_chaser = fm.new_chaser("Live-Chaser")
live_chaser.speed = 1.0

# Seite 3: zwei EFX — einer relativ (orbitet die gezielte Position), einer fürs Feld.
efx_rel = fm.new_efx("MH Acht (relativ)")
efx_rel.algorithm = EfxAlgorithm.EIGHT
efx_rel.fixtures = [EfxFixture(fid=mh_left), EfxFixture(fid=mh_right)]
efx_rel.speed_hz = 0.4; efx_rel.spread = 0.0; efx_rel.open_beam = True
efx_rel.relative = True; efx_rel.width = efx_rel.height = 90.0

efx_area = fm.new_efx("MH Kreis (Feld)")
efx_area.algorithm = EfxAlgorithm.CIRCLE
efx_area.fixtures = [EfxFixture(fid=mh_left), EfxFixture(fid=mh_right)]
efx_area.speed_hz = 0.4; efx_area.spread = 0.0; efx_area.open_beam = True
efx_area.relative = False; efx_area.width = efx_area.height = 80.0

# Seite 4: Regenbogen-Matrix (besitzt die Farbe -> Farb-Kacheln grauen aus, #9).
mx_rainbow = matrix("Mtx Regenbogen", RgbAlgorithm.RAINBOW, speed=1.5)


# ════════════════════════════════════════════════════════════════════════════
#  4) VIRTUAL CONSOLE
# ════════════════════════════════════════════════════════════════════════════
PAD, GAP, X0, Y0 = 60, 6, 20, 70
STEP = PAD + GAP
GRID_BOTTOM = Y0 + 8 * STEP
TY = GRID_BOTTOM + 4
Y_FAD = GRID_BOTTOM + 34
FAD_H = 142
RIGHT_X = X0 + 8 * STEP + 16
widgets: list[dict] = []

BANK_ALL = -1
P_MATRIX, P_CHASE, P_MH, P_COLOR = range(4)
PAGE_NAMES = ["Matrix Builder", "Chase bauen", "Moving Heads", "Farbe & Kontext"]


def pad_pos(note):
    row, col = note // 8, note % 8
    return X0 + col * STEP, Y0 + (7 - row) * STEP


def slot_note(s: int) -> int:
    r, c = s // 8, s % 8
    return (7 - r) * 8 + c


def _add(w, x, y, ww, hh, bank):
    w.bank = bank
    w.setGeometry(x, y, ww, hh)
    widgets.append(w.to_dict())


def func_btn(fn, note, bank, accent, flash=False, exclusive=False, clear_prog=False):
    b = VCButton(fn.name)
    b.action = ButtonAction.FUNCTION_FLASH if flash else ButtonAction.FUNCTION_TOGGLE
    b.function_id = fn.id
    b.pad_style = "pulse"; b.exclusive = exclusive; b.clear_programmer = clear_prog
    b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, note
    b._bg_color.setNamedColor(accent)
    x, y = pad_pos(note); _add(b, x, y, PAD, PAD, bank)


def action_btn(name, action, note, bank, accent):
    b = VCButton(name)
    b.action = action; b.pad_style = "solid"
    b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, note
    b._bg_color.setNamedColor(accent)
    x, y = pad_pos(note); _add(b, x, y, PAD, PAD, bank)


def effect_action_btn(name, note, bank, accent, key, function_id):
    b = VCButton(name)
    b.action = ButtonAction.EFFECT_ACTION; b.effect_action_key = key
    b.function_id = function_id; b.pad_style = "solid"
    b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, note
    b._bg_color.setNamedColor(accent)
    x, y = pad_pos(note); _add(b, x, y, PAD, PAD, bank)


def color_tile(name, note, bank, r, g, b, w=0, target=ColorTarget.ALL,
               function_id=None, with_intensity=False):
    c = VCColor(name)
    c.color_r, c.color_g, c.color_b, c.color_w = r, g, b, w
    c.with_intensity = with_intensity; c.target = target; c.function_id = function_id
    c.midi_type, c.midi_ch, c.midi_data1 = "note_on", 0, note
    x, y = pad_pos(note); _add(c, x, y, PAD, PAD, bank)


def fader(caption, col, bank, mode, function_id=None, function_ids=None,
          programmer_attr="intensity", programmer_scope="all", programmer_group="",
          param_key="speed", midi_cc=-1, value=0, submaster_slot=None):
    s = VCSlider(caption)
    s.mode = mode; s.function_id = function_id; s.function_ids = list(function_ids or [])
    if submaster_slot is not None:
        s.function_id = submaster_slot
    s.programmer_attr = programmer_attr; s.programmer_scope = programmer_scope
    s.programmer_group = programmer_group; s.param_key = param_key
    s.midi_cc, s.midi_ch = midi_cc, 0; s._value = value
    x = X0 + col * STEP + 2; _add(s, x, Y_FAD, 56, FAD_H, bank)


def label(text, x, y, ww, bank, hh=20):
    _add(VCLabel(text), x, y, ww, hh, bank)


def color_list(name, x, y, ww, hh, bank, function_id):
    cl = VCColorList(name); cl.function_id = function_id
    _add(cl, x, y, ww, hh, bank)


def xypad(name, x, y, size, bank, mode="position", fids=None, efx_id=None):
    p = VCXYPad(name); p.mode = mode
    if fids:
        p._fixture_ids = list(fids)
    p.efx_function_id = efx_id
    _add(p, x, y, size, size, bank)


# ── Universell ────────────────────────────────────────────────────────────────
for i, (nm, act, col) in enumerate([
        ("Clear", ButtonAction.CLEAR, "#4a3a10"),
        ("Stop All", ButtonAction.STOP_ALL, "#4a1010"),
        ("Blackout", ButtonAction.BLACKOUT, "#2a0000"),
        ("Tap", ButtonAction.TAP, "#103a3a")]):
    b = VCButton(nm); b.action = act; b.pad_style = "solid"
    b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, TRACK0 + i
    b._bg_color.setNamedColor(col)
    _add(b, X0 + i * 64, TY, 60, 26, BANK_ALL)

fader("Dimmer", 5, BANK_ALL, SliderMode.SUBMASTER, submaster_slot=0, midi_cc=53, value=255)
fader("Speed", 6, BANK_ALL, SliderMode.SPEED, midi_cc=54, value=64)
fader("Master", 8, BANK_ALL, SliderMode.GRANDMASTER, midi_cc=56, value=255)
label("FEATURE-TEST  —  SCENE-Tasten rechts = Seite 1-4.  Track-Tasten unten: "
      "Clear / Stop All / Blackout / Tap.  F6 Dimmer | F7 Speed | F9 Master.",
      X0, 6, 1150, BANK_ALL, hh=18)
for i, nm in enumerate(PAGE_NAMES):
    label(f"Scene {i + 1}: {nm}", RIGHT_X, Y0 + i * 26, 200, BANK_ALL, hh=22)


# ── SEITE 1 — MATRIX BUILDER (#3/#5/#6) ─────────────────────────────────────
MB = matrix_builder.id
func_btn(matrix_builder, 0, P_MATRIX, "#7a5b00", clear_prog=True)
effect_action_btn("Form -", 1, P_MATRIX, "#5a4a00", "prev_algorithm", MB)
effect_action_btn("Form +", 2, P_MATRIX, "#7a6500", "next_algorithm", MB)
effect_action_btn("Richtung", 3, P_MATRIX, "#335533", "reverse_direction", MB)
effect_action_btn("Freeze", 4, P_MATRIX, "#553333", "toggle_freeze", MB)
effect_action_btn("Reset", 5, P_MATRIX, "#5a3010", "clear_live_override", MB)
effect_action_btn("Commit", 6, P_MATRIX, "#1d4d2d", "commit_live", MB)
_RECOLOR = [("Rot", 255, 0, 0), ("Grün", 0, 255, 0), ("Blau", 0, 0, 255), ("Weiß", 255, 255, 255)]
for s, (nm, r, g, b) in enumerate(_RECOLOR):
    color_tile(f"C1 {nm}", slot_note(8 + s), P_MATRIX, r, g, b, target=ColorTarget.EFFECT_C1, function_id=MB)
for s, (nm, r, g, b) in enumerate(_RECOLOR):
    color_tile(f"C2 {nm}", slot_note(16 + s), P_MATRIX, r, g, b, target=ColorTarget.EFFECT_C2, function_id=MB)
for s, (nm, r, g, b) in enumerate(_RECOLOR):
    color_tile(f"Seq {nm}", slot_note(24 + s), P_MATRIX, r, g, b, target=ColorTarget.EFFECT, function_id=MB)
fader("Speed", 0, P_MATRIX, SliderMode.EFFECT_SPEED, function_ids=[MB], midi_cc=48, value=64)
fader("Master", 1, P_MATRIX, SliderMode.EFFECT_INTENSITY, function_ids=[MB], midi_cc=49, value=255)
color_list("Matrix-Farben", RIGHT_X, Y0 + 4 * 26 + 8, 210, 92, P_MATRIX, MB)
label("SEITE 1  MATRIX BUILDER  -  Pad unten links startet; 'Form -/+' blättert durch "
      "ALLE Algorithmen.  Reihe 2 = color1, Reihe 3 = color2, Reihe 4 = Sequence-Farbe.",
      X0, 28, 1100, P_MATRIX)
label("color1/2 wirken bei Feuer/Plasma/Windrad/Lauflicht; Sequence-Farbe bei Color-Fade. "
      "Rechts: Live-Feedback der Farben.", X0, 48, 1100, P_MATRIX)


# ── SEITE 2 — CHASE BAUEN (#2 echter Szenen-Chaser live) ────────────────────
LC = live_chaser.id
# Looks in den Programmer legen (Farbe + volle Helligkeit), dann als Schritt aufnehmen.
_LOOKS = [("Rot", 255, 0, 0, 0), ("Grün", 0, 255, 0, 0), ("Blau", 0, 0, 255, 0),
          ("Amber", 255, 140, 0, 0), ("Cyan", 0, 255, 255, 0), ("Magenta", 255, 0, 255, 0),
          ("Weiß", 255, 255, 255, 255), ("Warm", 255, 130, 40, 60)]
for s, (nm, r, g, b, w) in enumerate(_LOOKS):
    color_tile(nm, slot_note(s), P_CHASE, r, g, b, w,
               target=ColorTarget.PROGRAMMER, with_intensity=True)
# Bau-Steuerung (untere Reihe).
effect_action_btn("Schritt+", 0, P_CHASE, "#1d4d2d", "capture_step", LC)
effect_action_btn("Letzten -", 1, P_CHASE, "#5a3010", "remove_last_step", LC)
effect_action_btn("Alle -", 2, P_CHASE, "#5a1010", "clear_steps", LC)
func_btn(live_chaser, 3, P_CHASE, "#1f6a4a")
effect_action_btn("Richtung", 4, P_CHASE, "#335533", "reverse_direction", LC)
effect_action_btn("Ping-Pong", 5, P_CHASE, "#335533", "toggle_bounce", LC)
action_btn("Clear", ButtonAction.CLEAR, 6, P_CHASE, "#4a3a10")
fader("Tempo", 0, P_CHASE, SliderMode.EFFECT_SPEED, function_ids=[LC], midi_cc=48, value=80)
color_list("Chaser-Schritte", RIGHT_X, Y0 + 4 * 26 + 8, 210, 92, P_CHASE, LC)
label("SEITE 2  CHASE BAUEN (echter Szenen-Chaser)  -  1) oben eine Farbe tippen "
      "(geht in den Programmer)  2) 'Schritt+' nimmt den Look als Schritt auf.",
      X0, 28, 1100, P_CHASE)
label("Wiederholen -> Start (Pad 4) spielt die aufgenommenen Looks ab.  'Letzten -/Alle -' "
      "korrigieren, 'Clear' leert den Programmer.  Rechts: Anzahl Schritte.",
      X0, 48, 1100, P_CHASE)


# ── SEITE 3 — MOVING HEADS (#7 relativ + #8 Feld) ───────────────────────────
REL, AREA = efx_rel.id, efx_area.id
# Links: zielen (XY-Position-Pad auf die MHs).  Pads: relativ + Start/Neustart.
xypad("MH zielen", X0, Y0, 230, P_MH, mode="position", fids=mh_fids)
effect_action_btn("Relativ", slot_note(4), P_MH, "#7a6500", "toggle_relative", REL)
effect_action_btn("Neustart", slot_note(5), P_MH, "#5a3010", "restart", REL)
func_btn(efx_rel, slot_note(6), P_MH, "#1f3a6a")
func_btn(efx_area, slot_note(7), P_MH, "#1f3a6a")
# Rechts: Feld-Pad (EFX-Bereich aufziehen, gebunden an efx_area).
xypad("Feld → Kreis", RIGHT_X, Y0, 200, P_MH, mode="area", efx_id=AREA)
label("SEITE 3  MOVING HEADS  -  LINKS zielen (XY): bewegt die MHs.  Dann 'Relativ' an + "
      "'MH Acht' starten -> die Acht läuft RELATIV um die gezielte Position (#7).",
      X0, 28, 1100, P_MH)
label("RECHTS 'Feld': ein Rechteck aufziehen -> 'MH Kreis' fährt seinen Kreis in genau "
      "diesem Feld (#8).  Nach neuem Zielen 'Neustart' drücken.",
      X0, 48, 1100, P_MH)


# ── SEITE 4 — FARBE & KONTEXT (#4 Gruppen-Dimmer + #9 Farb-Lock) ────────────
# Farb-Kacheln auf den Programmer (grauen aus, sobald die Matrix die Farbe besitzt).
_COLS = [("Rot", 255, 0, 0, 0), ("Grün", 0, 255, 0, 0), ("Blau", 0, 0, 255, 0),
         ("Weiß", 255, 255, 255, 255), ("Amber", 255, 140, 0, 0), ("Cyan", 0, 255, 255, 0),
         ("Magenta", 255, 0, 255, 0), ("Warm", 255, 130, 40, 60)]
for s, (nm, r, g, b, w) in enumerate(_COLS):
    color_tile(nm, slot_note(s), P_COLOR, r, g, b, w,
               target=ColorTarget.PROGRAMMER, with_intensity=True)
func_btn(mx_rainbow, slot_note(8), P_COLOR, "#7a5b00", clear_prog=True)
action_btn("Clear", ButtonAction.CLEAR, 0, P_COLOR, "#4a3a10")
action_btn("Stop All", ButtonAction.STOP_ALL, 1, P_COLOR, "#4a1010")
# #4: PAR-Dim fest auf die PAR-Gruppe (keine Vorauswahl nötig).
fader("PAR-Dim", 3, P_COLOR, SliderMode.PROGRAMMER, programmer_attr="intensity",
      programmer_scope="group", programmer_group="PAR-Reihe", midi_cc=51, value=255)
label("SEITE 4  FARBE & KONTEXT  -  Farb-Kacheln (oben) färben die PARs im Programmer. "
      "F4 'PAR-Dim' dimmt fest die PAR-Gruppe (ohne Vorauswahl, #4).",
      X0, 28, 1100, P_COLOR)
label("'Mtx Regenbogen' starten -> die Farb-Kacheln grauen aus + zeigen 🔒 (der Effekt "
      "besitzt jetzt die Farbe, #9).  Stop -> Kacheln wieder aktiv.",
      X0, 48, 1100, P_COLOR)

state._vc_layout = {"widgets": widgets}

# ── Executor-Seiten benennen ────────────────────────────────────────────────
pe = getattr(state, "playback_engine", None)
if pe is not None:
    try:
        for idx, nm in enumerate(PAGE_NAMES):
            if 0 <= idx < len(pe.page_names):
                pe.page_names[idx] = nm
        pe.set_page(0)
    except Exception as e:
        print(f"[build] page name error: {e}")

# ── 5) Speichern + Verifikation ─────────────────────────────────────────────
state.programmer = {}
state.show_name = "Feature Test"
save_show(OUT)
print(f"Gespeichert: {OUT}")
ok, msg = load_show(OUT)
print("Load:", ok, msg)
assert ok, f"Show laedt nicht: {msg}"

fixtures2 = state.get_patched_fixtures()
assert len(fixtures2) == 6, "6 Fixtures erwartet"

from collections import Counter
vc = state._vc_layout.get("widgets", [])
banks = Counter(w.get("bank") for w in vc)
assert set(banks) == {0, 1, 2, 3, -1}, f"Banks: {sorted(banks)}"


def keys_on(bank, action):
    return {w.get("effect_action_key") for w in vc
            if w.get("bank") == bank and w.get("action") == action}


# Feature-Asserts (jede neue Funktion ist in der Show vertreten):
# #3 Matrix Form +/-
assert {"next_algorithm", "prev_algorithm"} <= keys_on(P_MATRIX, "EffectAction"), "Form +/-"
# #5 Recolor color1/2/3
slot_tiles = [w for w in vc if w.get("bank") == P_MATRIX
              and w.get("target") in (ColorTarget.EFFECT_C1, ColorTarget.EFFECT_C2)]
assert len(slot_tiles) == 8, f"Recolor-Kacheln: {len(slot_tiles)}"
# #2 Chaser capture
assert "capture_step" in keys_on(P_CHASE, "EffectAction"), "capture_step fehlt"
# #6 Feedback-Fenster (Matrix + Chaser)
cls = [w for w in vc if w.get("type") == "VCColorList"]
assert len(cls) == 2, f"VCColorList: {len(cls)}"
# #7 relative toggle
assert "toggle_relative" in keys_on(P_MH, "EffectAction"), "toggle_relative fehlt"
# #8 XY-Feld-Pad
xy_area = [w for w in vc if w.get("type") == "VCXYPad" and w.get("mode") == "area"]
assert len(xy_area) == 1 and xy_area[0].get("efx_function_id") == AREA, "XY-Feld-Pad fehlt"
xy_pos = [w for w in vc if w.get("type") == "VCXYPad" and w.get("mode") == "position"]
assert len(xy_pos) == 1, "XY-Positions-Pad fehlt"
# #4 PROGRAMMER-Fader feste Gruppe
grp_faders = [w for w in vc if w.get("bank") == P_COLOR and w.get("mode") == "Programmer"
              and w.get("programmer_scope") == "group" and w.get("programmer_group") == "PAR-Reihe"]
assert len(grp_faders) == 1, "Gruppen-Dimmer-Fader fehlt"

print(f"Funktionen: {len(fm.all())}  VC-Widgets: {len(vc)}  "
      f"Typen={dict(Counter(w['type'] for w in vc))}")
print(f"Banks: {dict(sorted(banks.items()))}  Max-Y={max((w.get('y',0)+w.get('h',0)) for w in vc)}")
print("  [OK] #2 capture_step  #3 Form+/-  #4 Gruppen-Dimmer  #5 Recolor")
print("  [OK] #6 Feedback x2  #7 relativ  #8 XY-Feld  #9 Regenbogen+Farb-Lock")
print("FERTIG")
