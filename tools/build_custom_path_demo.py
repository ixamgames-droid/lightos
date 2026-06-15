"""DEMO: Custom Paths + EFX-Live-Steuerung + Keyboard-Mapping (2026-06-11).

Selbst-verifizierender Show-Generator für die neuen Features:

  * 2 Custom Paths in der Pfad-Bibliothek:
      - "Zickzack"     linear, offen     → EFX "Sweep Zickzack" (ONE-SHOT, kein Loop)
      - "Weiche Acht"  Spline, geschlossen → EFX "Acht weich" (Loop)
  * 1 klassischer Kreis-EFX (Regression: alte Algorithmen unverändert)
  * 1 RGB-Matrix + 1 Farb-Chaser (Regression: Matrix/Chaser-Mappings)
  * Virtual Console (1 Seite, APC mini mk2 + Tastatur):
      - Pads 0/1/2  = EFX-Start/Stop (FunctionToggle, MIDI-Note + Taste F5/F6/F7)
      - Pads 8/9/10 = EFX-Aktionen Neustart / Pfad+ / Loop an-aus
                      (EFFECT_ACTION, Tasten F8/F9/F10)
      - Fader CC48  = EFX-Speed, CC49 = Größe (EFFECT_PARAM, live)
      - Pad 3 = Chaser, Pad 4 = Matrix (Regression), Pad 7 = Blackout (Strg+B)
  * Gruppen "Moving Heads" + "PAR-Reihe" (zum Testen von „Gruppe bearbeiten")

Hardware wie Komplett_Demo: 4x ZQ01424-PAR (DMX 1/9/17/25) + 2x ZQ02001-MH
(33/44) + Akai APC mini mk2.

Aufruf:  venv/Scripts/python.exe tools/build_custom_path_demo.py
Erzeugt: shows/CustomPath_Demo.lshow   (Doku: docs/UPDATE_2026-06-11.md)
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
_app = QApplication.instance() or QApplication([])

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.core.app_state import get_state, get_channels_for_patched
from src.core.database.fixture_db import engine as fdb_engine
from src.core.database.models import FixtureGroup, FixtureProfile, PatchedFixture
from src.core.engine.chaser import ChaserStep
from src.core.engine.efx import EfxAlgorithm, EfxFixture, EfxInstance
from src.core.engine.efx_path import EfxPath, get_efx_path_library
from src.core.engine.function_manager import get_function_manager
from src.core.engine.rgb_matrix import ColorSequence, RgbAlgorithm
from src.core.show.show_file import load_show, reset_show, save_show
from src.ui.virtualconsole.vc_button import ButtonAction, VCButton
from src.ui.virtualconsole.vc_slider import SliderMode, VCSlider
from src.ui.virtualconsole.vc_label import VCLabel

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(_ROOT, "shows", "CustomPath_Demo.lshow")


def profile_id(short: str) -> int:
    with Session(fdb_engine()) as s:
        pid = s.execute(
            select(FixtureProfile.id).where(FixtureProfile.short_name == short)
        ).scalar_one_or_none()
    if pid is None:
        raise SystemExit(f"Profil '{short}' fehlt — bitte die App einmal starten.")
    return int(pid)


# ── 0) Leere Basis ───────────────────────────────────────────────────────────
reset_show()
state = get_state()
fm = get_function_manager()
paths = get_efx_path_library()

PAR_PID = profile_id("ZQ01424")
MH_PID = profile_id("ZQ02001")

# ── 1) Patch: 4 PAR + 2 MH ───────────────────────────────────────────────────
par_fids = []
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
for fid, label, a in ((mh_left, "MH Links", 33), (mh_right, "MH Rechts", 44)):
    state.add_fixture(PatchedFixture(
        fid=fid, label=label, fixture_profile_id=MH_PID,
        mode_name="11-Kanal", universe=1, address=a, channel_count=11,
        manufacturer_name="U King", fixture_name="ZQ02001 Mini Moving Head",
        fixture_type="moving_head"), undoable=False)

state.base_levels = {fid: {"intensity": 255} for fid in par_fids}

# ── 2) Gruppen (für „Gruppe bearbeiten" / EFX-auf-Gruppe) ────────────────────
with state._session() as s:
    s.execute(delete(FixtureGroup))
    s.add(FixtureGroup(name="PAR-Reihe", cols=4, rows=1,
                       positions_json=json.dumps({f"{i},0": par_fids[i] for i in range(4)})))
    s.add(FixtureGroup(name="Moving Heads", cols=2, rows=1,
                       positions_json=json.dumps({"0,0": mh_left, "1,0": mh_right})))
    s.commit()

# ── 3) Custom Paths ──────────────────────────────────────────────────────────
zigzag = paths.add(EfxPath(
    "Zickzack",
    [(0.10, 0.25), (0.35, 0.75), (0.60, 0.25), (0.90, 0.75)],
    mode="linear", closed=False))
soft8 = paths.add(EfxPath(
    "Weiche Acht",
    [(0.50, 0.15), (0.80, 0.35), (0.50, 0.55), (0.20, 0.75),
     (0.50, 0.90), (0.80, 0.75), (0.50, 0.55), (0.20, 0.35)],
    mode="spline", closed=True))

# ── 4) EFX-Funktionen ────────────────────────────────────────────────────────
def mk_efx(name, speed_hz=0.4):
    e = fm.new_efx(name)
    e.fixtures = [EfxFixture(fid=mh_left), EfxFixture(fid=mh_right)]
    e.speed_hz = speed_hz
    e.open_beam = True
    e.width = 170.0
    e.height = 150.0
    return e

efx_zigzag = mk_efx("Sweep Zickzack (One-Shot)", speed_hz=0.30)
efx_zigzag.set_custom_path(zigzag)
efx_zigzag.loop = False                      # Loop/No-Loop im Hauptfenster

efx_soft8 = mk_efx("Acht weich (Loop)", speed_hz=0.45)
efx_soft8.set_custom_path(soft8)
efx_soft8.loop = True
efx_soft8.spread = 0.5                       # Fan über die Gruppe

efx_circle = mk_efx("Kreis klassisch", speed_hz=0.40)
efx_circle.algorithm = EfxAlgorithm.CIRCLE   # Regression: Built-in-Form

# ── 5) Regression: Matrix + Chaser ──────────────────────────────────────────
mtx = fm.new_rgb_matrix("Matrix Regenbogen")
mtx.algorithm = RgbAlgorithm.RAINBOW
mtx.fixture_grid = list(par_fids)
mtx.cols, mtx.rows = len(par_fids), 1
mtx.matrix_speed = 2.0

chan_of = {f.fid: {c.attribute: c.channel_number
                   for c in get_channels_for_patched(f)}
           for f in state.get_patched_fixtures()}


def par_look(name, r=0, g=0, b=0):
    sc = fm.new_scene(name)
    for fid in par_fids:
        cm = chan_of[fid]
        if "intensity" in cm:
            sc.set_value(fid, cm["intensity"], 255)
        for attr, val in (("color_r", r), ("color_g", g), ("color_b", b)):
            if attr in cm:
                sc.set_value(fid, cm[attr], val)
    return sc


lk_r = par_look("Look Rot", r=255)
lk_g = par_look("Look Grün", g=255)
lk_b = par_look("Look Blau", b=255)

chaser = fm.new_chaser("Farb-Chaser")
for sc in (lk_r, lk_g, lk_b):
    chaser.steps.append(ChaserStep(function_id=sc.id, fade_in=0.2, hold=0.5))

# ── 6) Virtual Console (1 Seite, MIDI + Tastatur) ───────────────────────────
PAD, GAP, X0, Y0 = 60, 6, 20, 70
STEP = PAD + GAP
widgets: list[dict] = []


def _add(w, x, y, ww, hh):
    w.bank = -1
    w.setGeometry(x, y, ww, hh)
    widgets.append(w.to_dict())


def pad_pos(note):
    row, col = note // 8, note % 8
    return X0 + col * STEP, Y0 + (7 - row) * STEP


def func_btn(fn, note, key, accent):
    b = VCButton(fn.name)
    b.action = ButtonAction.FUNCTION_TOGGLE
    b.function_id = fn.id
    b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, note
    b.key_binding = key
    b._bg_color.setNamedColor(accent)
    x, y = pad_pos(note)
    _add(b, x, y, PAD, PAD)
    return b


def efx_action_btn(name, action_key, fn, note, key):
    b = VCButton(name)
    b.action = ButtonAction.EFFECT_ACTION
    b.effect_action_key = action_key
    b.function_id = fn.id
    b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, note
    b.key_binding = key
    x, y = pad_pos(note)
    _add(b, x, y, PAD, PAD)
    return b


title = VCLabel("CUSTOM-PATH-DEMO — EFX über MIDI (APC) + Tastatur (F5–F10)")
_add(title, X0, 16, 8 * STEP, 40)

func_btn(efx_zigzag, 0, "F5", "#1f6feb")
func_btn(efx_soft8, 1, "F6", "#a371f7")
func_btn(efx_circle, 2, "F7", "#3fb950")
func_btn(chaser, 3, "", "#f0883e")
func_btn(mtx, 4, "", "#db61a2")

efx_action_btn("Neustart", "restart", efx_zigzag, 8, "F8")
efx_action_btn("Pfad +", "next_path", efx_soft8, 9, "F9")
efx_action_btn("Loop an/aus", "toggle_loop", efx_soft8, 10, "F10")

bo = VCButton("BLACKOUT")
bo.action = ButtonAction.BLACKOUT
bo.midi_type, bo.midi_ch, bo.midi_data1 = "note_on", 0, 7
bo.key_binding = "Ctrl+B"
x, y = pad_pos(7)
_add(bo, x, y, PAD, PAD)

# Fader: Speed + Größe des Loop-EFX (EFFECT_PARAM → effect_live, live am Gerät)
Y_FAD = Y0 + 8 * STEP + 30
for i, (caption, pkey, cc) in enumerate(
        (("EFX Speed", "speed", 48), ("EFX Größe", "size", 49))):
    s = VCSlider(caption)
    s.mode = SliderMode.EFFECT_PARAM
    s.function_id = efx_soft8.id
    s.param_key = pkey
    s.midi_ch, s.midi_cc = 0, cc
    _add(s, X0 + i * STEP, Y_FAD, PAD, 150)

state._vc_layout = {"widgets": widgets}

# ── 7) Speichern, neu laden, verifizieren ────────────────────────────────────
save_show(OUT)
reset_show()
assert not get_efx_path_library().all(), "reset_show muss die Pfade leeren"
load_show(OUT)

fm = get_function_manager()
paths = get_efx_path_library()

# Pfad-Bibliothek
by_name = {p.name: p for p in paths.all()}
assert set(by_name) == {"Zickzack", "Weiche Acht"}, sorted(by_name)
assert by_name["Zickzack"].mode == "linear" and not by_name["Zickzack"].closed
assert by_name["Weiche Acht"].mode == "spline" and by_name["Weiche Acht"].closed
assert len(by_name["Weiche Acht"].points) == 8

# EFX-Funktionen
efxs = {f.name: f for f in fm.all() if isinstance(f, EfxInstance)}
assert set(efxs) == {"Sweep Zickzack (One-Shot)", "Acht weich (Loop)",
                     "Kreis klassisch"}, sorted(efxs)
zz = efxs["Sweep Zickzack (One-Shot)"]
assert zz.algorithm == EfxAlgorithm.CUSTOM and zz.loop is False
assert zz.path_id == by_name["Zickzack"].id and zz.path_data["mode"] == "linear"
s8 = efxs["Acht weich (Loop)"]
assert s8.algorithm == EfxAlgorithm.CUSTOM and s8.loop is True
assert s8.path_data["mode"] == "spline"
assert efxs["Kreis klassisch"].algorithm == EfxAlgorithm.CIRCLE
# Custom-Path-EFX rechnet sinnvolle Pan/Tilt-Werte
pan, tilt = s8._calc(0.25)
assert 0 <= pan <= 255 and 0 <= tilt <= 255
# Live-API erreichbar (VC/MIDI-Mapping-Ziel)
assert "path" in {p.key for p in s8.list_params()}
assert dict(s8.list_actions()).get("restart") == "Neustart"

# Matrix + Chaser (Regression)
names = {f.name for f in fm.all()}
assert {"Matrix Regenbogen", "Farb-Chaser"} <= names, sorted(names)

# VC: MIDI- und Tastatur-Bindungen persistiert
vc = state._vc_layout.get("widgets", [])
keymap = {w.get("caption"): w.get("key_binding") for w in vc
          if w.get("key_binding")}
assert keymap.get("Sweep Zickzack (One-Shot)") == "F5"
assert keymap.get("Acht weich (Loop)") == "F6"
assert keymap.get("Loop an/aus") == "F10"
assert keymap.get("BLACKOUT") == "Ctrl+B"
sliders = [w for w in vc if w.get("mode") == SliderMode.EFFECT_PARAM]
assert {w.get("param_key") for w in sliders} == {"speed", "size"}, sliders

print(f"OK: {OUT}")
print(f"   Pfade: {sorted(by_name)} | EFX: {sorted(efxs)} | "
      f"VC-Widgets: {len(vc)} (davon {len(keymap)} mit Tastatur-Bindung)")
