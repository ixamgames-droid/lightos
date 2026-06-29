"""Erzeugt eine KOMPLETT vorprogrammierte Test-Show (.lshow) zum Anschauen aller
Funktionsarten nach dem Programmer-Umbau.

Inhalt:
  - PATCH: 6× RGBW-PAR (Intensity+RGBW) + 4× Moving-Head-Wash (Pan/Tilt+RGB).
  - SNAPS: Farb-Looks in der Bibliothek (gelb), in Ordnern.
  - SCENES: Basis-Looks (Open White, Warm, Cold, Farben, Black).
  - CHASER: Color Chase, Rainbow, Strobe, Police (aus Scene-Steps).
  - RGB-MATRIX (NEU als echte Funktion): Lauflicht/Regenbogen/Wipe direkt auf der
    PAR-Gruppe — der „Matrix-Style auf Strahler" ohne separate Matrix.
  - EFX (NEU als echte Funktion): Kreis/Acht auf den Moving Heads (Pan/Tilt).
  - VIRTUAL CONSOLE: Buttons (Funktion-Toggle) + Live-Farb-Kacheln + FADER
    (Grand Master + Effekt-Intensität), alles mit MIDI-Bindung (APC mini).

Aufruf:  venv/Scripts/python.exe tools/build_test_show.py
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# DEMO-02: spawn-sichere Env-Schalter setzen, BEVOR app_state importiert wird.
# Ohne diese Zeile re-importiert ein multiprocessing-'spawn'-Kindprozess dieses
# guardlose Skript als __mp_main__ und baut die Show ein zweites Mal -> halber
# Patch. Siehe tools/_gen_env.py.
import _gen_env  # noqa: F401
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
_app = QApplication.instance() or QApplication([])

from src.core.app_state import get_state, get_channels_for_patched
from src.core.database.models import PatchedFixture
from src.core.engine.function_manager import get_function_manager
from src.core.engine.function import RunOrder
from src.core.engine.rgb_matrix import RgbAlgorithm
from src.core.engine.efx import EfxAlgorithm, EfxFixture
from src.core.engine.snap_library import get_snap_library
from src.ui.virtualconsole.vc_button import VCButton, ButtonAction
from src.ui.virtualconsole.vc_color import VCColor, ColorTarget
from src.ui.virtualconsole.vc_slider import VCSlider, SliderMode
from src.ui.virtualconsole.vc_label import VCLabel

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(_ROOT, "shows", "Test_Show_Komplett.lshow")

state = get_state()
fm = get_function_manager()
lib = get_snap_library()

# ── 1) PATCH neu aufbauen ──────────────────────────────────────────────────────
for f in list(state.get_patched_fixtures()):
    try:
        state.remove_fixture(f.fid, undoable=False)
    except Exception:
        pass

PAR_PROFILE, PAR_MODE, PAR_CH = 17, "8-Kanal RGBW", 8        # Generic Stage Light ZQ01424
MH_PROFILE,  MH_MODE,  MH_CH  = 10, "7-Kanal",      7        # Generic Moving Head Wash RGB

par_fids: list[int] = []
mh_fids:  list[int] = []
addr = 1
fid = 1
for i in range(6):  # 6 PARs
    state.add_fixture(PatchedFixture(
        fid=fid, label=f"PAR {i+1}", fixture_profile_id=PAR_PROFILE,
        mode_name=PAR_MODE, universe=1, address=addr, channel_count=PAR_CH,
        manufacturer_name="Generic", fixture_name="Stage Light ZQ01424",
        fixture_type="color"), undoable=False)
    par_fids.append(fid); addr += PAR_CH; fid += 1
for i in range(4):  # 4 Moving Heads
    state.add_fixture(PatchedFixture(
        fid=fid, label=f"Head {i+1}", fixture_profile_id=MH_PROFILE,
        mode_name=MH_MODE, universe=1, address=addr, channel_count=MH_CH,
        manufacturer_name="Generic", fixture_name="Moving Head Wash RGB 7ch",
        fixture_type="moving_head"), undoable=False)
    mh_fids.append(fid); addr += MH_CH; fid += 1

fixtures = state.get_patched_fixtures()
all_fids = [f.fid for f in fixtures]
# Attribut -> 1-basierter Kanal je Fixture (PAR und MH haben verschiedene Maps)
chan_of = {f.fid: {c.attribute: c.channel_number
                   for c in get_channels_for_patched(f)} for f in fixtures}


# ── 2) SCENES (Basis-Looks) ────────────────────────────────────────────────────
def scene(name, r=0, g=0, b=0, w=0, intensity=255, fade=0.0, fids=None):
    """Setzt Intensity/Shutter offen + Farbe auf den angegebenen Fixtures."""
    s = fm.new_scene(name)
    s.fade_in = fade
    s.fade_out = fade
    for f_id in (fids if fids is not None else all_fids):
        cm = chan_of[f_id]
        if "intensity" in cm:
            s.set_value(f_id, cm["intensity"], intensity)
        if "shutter" in cm:
            s.set_value(f_id, cm["shutter"], 255)  # Shutter offen
        for attr, val in (("color_r", r), ("color_g", g),
                          ("color_b", b), ("color_w", w)):
            if attr in cm:
                s.set_value(f_id, cm[attr], val)
    return s


look_white = scene("Open White", w=255, intensity=255)
look_warm  = scene("Warm",  r=255, g=110, b=20, w=40)
look_cold  = scene("Cold",  r=0,   g=60,  b=255)
look_red   = scene("Rot",     r=255)
look_green = scene("Grün",   g=255)
look_blue  = scene("Blau",    b=255)
look_amber = scene("Amber",   r=255, g=140)
look_mag   = scene("Magenta", r=255, b=255)
look_cyan  = scene("Cyan",    g=255, b=255)
look_off   = scene("Black",   intensity=0)

look_funcs = [look_white, look_warm, look_cold, look_red, look_green,
              look_blue, look_amber, look_mag]


# ── 3) CHASER (aus Scene-Steps) ─────────────────────────────────────────────────
def chaser(name, step_fids, hold=0.5, fade=0.2, order=RunOrder.Loop, speed=1.0):
    from src.core.engine.chaser import ChaserStep
    c = fm.new_chaser(name)
    c.run_order = order
    c.speed = speed
    for sid in step_fids:
        c.steps.append(ChaserStep(function_id=sid, fade_in=fade, hold=hold, fade_out=0.0))
    return c


ch_color  = chaser("Color Chase", [look_red.id, look_green.id, look_blue.id,
                                    look_mag.id, look_cyan.id, look_amber.id],
                   hold=0.55, fade=0.25)
ch_rain   = chaser("Rainbow", [look_red.id, look_amber.id, look_green.id,
                               look_cyan.id, look_blue.id, look_mag.id],
                   hold=0.35, fade=0.6)
ch_strobe = chaser("Strobe", [look_white.id, look_off.id], hold=0.04, fade=0.0)
ch_police = chaser("Police", [look_red.id, look_off.id, look_blue.id, look_off.id],
                   hold=0.12, fade=0.0)
chaser_funcs = [ch_color, ch_rain, ch_strobe, ch_police]


# ── 4) RGB-MATRIX als echte Funktion — Matrix-Style auf die PAR-GRUPPE ──────────
def matrix(name, algo, fids, c1=(255, 0, 0), c2=(0, 0, 255), c3=(0, 255, 0), speed=2.0):
    m = fm.new_rgb_matrix(name)
    m.algorithm = algo
    m.fixture_grid = list(fids)
    m.cols = len(fids)
    m.rows = 1
    m.color1, m.color2, m.color3 = c1, c2, c3
    m.matrix_speed = speed
    return m


mx_chase = matrix("Matrix Lauflicht (PARs)", RgbAlgorithm.CHASE, par_fids,
                  c1=(255, 0, 0), speed=3.0)
mx_rain  = matrix("Matrix Regenbogen (PARs)", RgbAlgorithm.RAINBOW, par_fids, speed=1.5)
mx_wipe  = matrix("Matrix Wipe (alle)", RgbAlgorithm.WIPE, all_fids,
                  c1=(0, 200, 255), c2=(255, 0, 120), speed=1.0)
matrix_funcs = [mx_chase, mx_rain, mx_wipe]


# ── 5) EFX als echte Funktion — Pan/Tilt-Bewegung auf den Moving Heads ──────────
def efx(name, algo, fids, speed_hz=0.5, width=120, height=120):
    e = fm.new_efx(name)
    e.algorithm = algo
    e.speed_hz = speed_hz
    e.width = width
    e.height = height
    n = len(fids)
    for i, f_id in enumerate(fids):
        e.fixtures.append(EfxFixture(fid=f_id, start_offset=i / max(n, 1)))
    return e


efx_circle = efx("EFX Kreis (Heads)", EfxAlgorithm.CIRCLE, mh_fids, speed_hz=0.4)
efx_eight  = efx("EFX Acht (Heads)", EfxAlgorithm.EIGHT, mh_fids, speed_hz=0.3)
efx_funcs = [efx_circle, efx_eight]


# ── 6) SNAPS in der Bibliothek (gelb), in Ordnern ───────────────────────────────
lib.clear()
lib.add_folder("Farben")
lib.add_folder("Intros")


def snap(name, folder, r, g, b, w=0, intensity=255, fids=None):
    values = {}
    for f_id in (fids if fids is not None else all_fids):
        cm = chan_of[f_id]
        d = {}
        if "intensity" in cm:
            d["intensity"] = intensity
        for attr, val in (("color_r", r), ("color_g", g),
                          ("color_b", b), ("color_w", w)):
            if attr in cm:
                d[attr] = val
        values[f_id] = d
    lib.add_snap(name, folder, values)


snap("Blau warm", "Farben", 0, 40, 255, intensity=200)
snap("Rot voll",  "Farben", 255, 0, 0)
snap("Grün voll", "Farben", 0, 255, 0)
snap("Intro Soft", "Intros", 80, 0, 160, w=20, intensity=120)


# ── 7) VIRTUAL CONSOLE: Pads (Notes 16-47) + Fader (CC) ────────────────────────
PAD = 70
GAP = 6
X0 = 20
Y0 = 110
STEP = PAD + GAP
widgets = []


def pad_pos(note: int):
    row, col = note // 8, note % 8
    x = X0 + col * STEP
    y = Y0 + (7 - row) * STEP
    return x, y


def add_widget(w, x, y, ww, hh):
    w.setGeometry(x, y, ww, hh)
    widgets.append(w.to_dict())


def func_button(fn, note, accent):
    b = VCButton(fn.name)
    b.action = ButtonAction.FUNCTION_TOGGLE
    b.function_id = fn.id
    b.midi_type = "note_on"
    b.midi_ch = 0
    b.midi_data1 = note
    b._bg_color.setNamedColor(accent)
    x, y = pad_pos(note)
    add_widget(b, x, y, PAD, PAD)


def color_tile(name, note, r, g, b):
    c = VCColor(name)
    c.color_r, c.color_g, c.color_b = r, g, b
    c.target = ColorTarget.ALL
    c.midi_type = "note_on"
    c.midi_ch = 0
    c.midi_data1 = note
    x, y = pad_pos(note)
    add_widget(c, x, y, PAD, PAD)


def fader(caption, x, mode, function_id=None, midi_cc=-1, value=255):
    s = VCSlider(caption)
    s.mode = mode
    s.function_id = function_id
    s.midi_cc = midi_cc
    s.midi_ch = 0
    s._value = value
    add_widget(s, x, Y0, 56, 240)


# Chaser-Effekte: Notes 16-19 (Reihe 3)
for i, fn in enumerate(chaser_funcs):
    func_button(fn, 16 + i, "#3a2150")
# RGB-Matrix: Notes 20-22 (Reihe 3 rechts) — Headline-Feature, gold
for i, fn in enumerate(matrix_funcs):
    func_button(fn, 20 + i, "#7a5b00")
# EFX: Notes 24-25 (Reihe 4) — gruen
for i, fn in enumerate(efx_funcs):
    func_button(fn, 24 + i, "#13402a")
# Scenes/Looks: Notes 32-39 (Reihe 5) — blau
for i, fn in enumerate(look_funcs):
    func_button(fn, 32 + i, "#11304a")
# Live-Farben (VCColor): Notes 40-47 (Reihe 6)
color_tiles = [
    ("Rot", 255, 0, 0), ("Grün", 0, 255, 0), ("Blau", 0, 0, 255),
    ("Weiß", 255, 255, 255), ("Amber", 255, 140, 0), ("Cyan", 0, 255, 255),
    ("Magenta", 255, 0, 255), ("Gelb", 255, 255, 0),
]
for i, (cname, r, g, b) in enumerate(color_tiles):
    color_tile(cname, 40 + i, r, g, b)

# Fader (rechts neben dem Pad-Raster). APC: CC48-55 = Executor-Fader (ungenutzt ->
# kein Konflikt), CC56 = Grand Master.
FX0 = X0 + 8 * STEP + 24
fader("Master", FX0, SliderMode.GRANDMASTER, midi_cc=56, value=255)
fader("Lauflicht", FX0 + 70, SliderMode.EFFECT_INTENSITY, function_id=mx_chase.id, midi_cc=48)
fader("Regenbogen", FX0 + 140, SliderMode.EFFECT_INTENSITY, function_id=mx_rain.id, midi_cc=49)
fader("EFX Kreis", FX0 + 210, SliderMode.EFFECT_INTENSITY, function_id=efx_circle.id, midi_cc=50)
fader("Color Chase", FX0 + 280, SliderMode.EFFECT_INTENSITY, function_id=ch_color.id, midi_cc=51)

# Beschriftungen
labels = [
    ("LightOS — Test-Show (Komplett)", X0, 16, 640, 28),
    ("Reihe3: Chaser + RGB-MATRIX (gold)  ·  Reihe4: EFX  ·  Reihe5: Looks  ·  Reihe6: Live-Farben",
     X0, 50, 1000, 20),
    ("Fader rechts: Grand Master (CC56) + Effekt-Intensitäten (CC48-51)", X0, 74, 1000, 20),
]
for text, x, y, ww, hh in labels:
    lbl = VCLabel(text)
    add_widget(lbl, x, y, ww, hh)

state._vc_layout = {"widgets": widgets}

# ── 8) Blackout-Start, benennen, speichern ─────────────────────────────────────
state.programmer = {}
state.show_name = "Test-Show Komplett"

from src.core.show.show_file import save_show, load_show
save_show(OUT)
print(f"Gespeichert: {OUT}")

# ── 9) Verifikation: frisch laden und Inhalte zaehlen ──────────────────────────
ok, msg = load_show(OUT)
print("Load:", ok, msg)
funcs = fm.all()
from src.core.engine.function import FunctionType
by = {}
for f in funcs:
    by.setdefault(f.function_type.value, []).append(f.name)
print(f"Funktionen geladen: {len(funcs)}")
for t, names in sorted(by.items()):
    print(f"   {t:10} ({len(names)}): {', '.join(names)}")
print(f"Patch: {len(state.get_patched_fixtures())} Fixtures "
      f"(PARs={len(par_fids)}, Heads={len(mh_fids)})")
print(f"Snaps in Bibliothek: {len(get_snap_library().snaps())} "
      f"in Ordnern {sorted(get_snap_library().folders())}")
vc = state._vc_layout.get("widgets", [])
counts = {}
for w in vc:
    counts[w["type"]] = counts.get(w["type"], 0) + 1
print(f"VC-Widgets: {len(vc)}  {counts}")
btn_notes = sorted(w["midi_data1"] for w in vc if w["type"] == "VCButton")
col_notes = sorted(w["midi_data1"] for w in vc if w["type"] == "VCColor")
ccs = sorted(w["midi_cc"] for w in vc if w["type"] == "VCSlider")
print("Button-Notes:", btn_notes)
print("Color-Notes :", col_notes)
print("Fader-CCs   :", ccs)
print("FERTIG")
