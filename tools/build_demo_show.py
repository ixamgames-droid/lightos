"""Erzeugt eine komplett vorprogrammierte Demo-Show (.lshow) fuer die 3 RGBW-PARs
und die APC mini mk2.

Konzept (passt zum zentralen Per-Frame-Renderer):
  - LOOKS & EFFEKTE = Scenes/Chaser (FunctionToggle-Buttons). Enthalten Intensitaet,
    laufen ueber die mittlere Render-Prioritaet und werden beim Loslassen sauber
    freigegeben (Per-Frame-Clear).
  - LIVE-FARBEN = VCColor-Kacheln (Programmer, hoechste Prioritaet) zum Umfaerben
    eines laufenden Looks.
  - APC-Pads: VC-Widgets liegen auf den FREIEN Notes 16-63 (0-15/64-71/82-89 sind
    schon vom MIDI-Mapper belegt -> kein Doppel-Trigger). Master-Fader (CC56) ist
    bereits auf grand_master gemappt.

Aufruf:  venv/Scripts/python.exe tools/build_demo_show.py
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
from src.core.engine.function_manager import get_function_manager
from src.core.engine.function import RunOrder
from src.ui.virtualconsole.vc_button import VCButton, ButtonAction
from src.ui.virtualconsole.vc_color import VCColor, ColorTarget
from src.ui.virtualconsole.vc_label import VCLabel

OUT = os.path.join("shows", "APC_Demo_Show.lshow")

state = get_state()
fm = get_function_manager()
fixtures = state.get_patched_fixtures()
fids = [f.fid for f in fixtures]

# Attribut -> 1-basierter Kanal-Offset (alle PARs gleicher Mode)
chan_of = {c.attribute: c.channel_number for c in get_channels_for_patched(fixtures[0])}


def scene(name, r=0, g=0, b=0, w=0, intensity=255, fade=0.0):
    """Erzeugt eine Scene, die ALLE Fixtures auf intensity + Farbe setzt."""
    s = fm.new_scene(name)
    s.fade_in = fade
    s.fade_out = fade
    for fid in fids:
        if "intensity" in chan_of:
            s.set_value(fid, chan_of["intensity"], intensity)
        for attr, val in (("color_r", r), ("color_g", g), ("color_b", b), ("color_w", w)):
            if attr in chan_of:
                s.set_value(fid, chan_of[attr], val)
    return s


def chaser(name, step_fids, hold=0.6, fade=0.2, order=RunOrder.Loop, speed=1.0):
    from src.core.engine.chaser import ChaserStep
    c = fm.new_chaser(name)
    c.run_order = order
    c.speed = speed
    for sid in step_fids:
        c.steps.append(ChaserStep(function_id=sid, fade_in=fade, hold=hold, fade_out=0.0))
    return c


# ── 1) Bestehende Funktionen leeren, neue bauen ────────────────────────────────
fm._functions.clear()

# Basis-Looks (Scenes) — diese erscheinen als Buttons UND dienen als Chaser-Steps
look_white  = scene("Open White", w=255, intensity=255)
look_warm   = scene("Warm",  r=255, g=110, b=20, w=40)
look_cold   = scene("Cold",  r=0,   g=60,  b=255)
look_red    = scene("Rot",     r=255)
look_green  = scene("Grün",   g=255)
look_blue   = scene("Blau",    b=255)
look_amber  = scene("Amber",   r=255, g=140)
look_magenta= scene("Magenta", r=255, b=255)
look_cyan   = scene("Cyan",    g=255, b=255)
look_off    = scene("Black",   intensity=0)  # fuer Strobe/Police

# Chaser / Effekte
ch_color  = chaser("Color Chase", [look_red.id, look_green.id, look_blue.id,
                                    look_magenta.id, look_cyan.id, look_amber.id],
                   hold=0.55, fade=0.25)
ch_rain   = chaser("Rainbow", [look_red.id, look_amber.id, look_green.id,
                               look_cyan.id, look_blue.id, look_magenta.id],
                   hold=0.35, fade=0.6)
ch_strobe = chaser("Strobe", [look_white.id, look_off.id], hold=0.04, fade=0.0)
ch_police = chaser("Police", [look_red.id, look_off.id, look_blue.id, look_off.id],
                   hold=0.12, fade=0.0)

# Reihenfolge der Funktions-Buttons auf den Pads
effect_funcs = [ch_color, ch_rain, ch_strobe, ch_police]
look_funcs   = [look_white, look_warm, look_cold, look_red, look_green,
                look_blue, look_amber, look_magenta, look_cyan]

# Live-Farb-Kacheln (VCColor, Ziel = alle Fixtures)
color_tiles = [
    ("Rot", 255, 0, 0), ("Grün", 0, 255, 0), ("Blau", 0, 0, 255),
    ("Weiß", 255, 255, 255), ("Amber", 255, 140, 0), ("Cyan", 0, 255, 255),
    ("Magenta", 255, 0, 255), ("Gelb", 255, 255, 0),
]

# ── 2) VC-Layout aufbauen (Pad-Raster, Notes 16-63) ────────────────────────────
PAD = 76
GAP = 6
X0 = 20
Y0 = 120
STEP = PAD + GAP

widgets = []


def pad_pos(note: int):
    """Canvas-Position fuer eine APC-Pad-Note (Reihe 0 = unten)."""
    row, col = note // 8, note % 8
    x = X0 + col * STEP
    y = Y0 + (7 - row) * STEP
    return x, y


def add_widget(w, x, y, ww, hh):
    w.setGeometry(x, y, ww, hh)
    widgets.append(w.to_dict())


def label(text, x, y, ww=320, hh=22):
    lbl = VCLabel(text)
    add_widget(lbl, x, y, ww, hh)


# Funktions-Buttons (Effekte ab Note 16, Looks ab Note 24)
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


# Effekte: Notes 16-19 (Reihe 2 links)
for i, fn in enumerate(effect_funcs):
    func_button(fn, 16 + i, "#3a2150")

# Looks: Notes 24-32 (Reihe 3 + 1)
for i, fn in enumerate(look_funcs):
    func_button(fn, 24 + i, "#11304a")

# Live-Farben (VCColor): Notes 40-47 (Reihe 5)
for i, (cname, r, g, b) in enumerate(color_tiles):
    note = 40 + i
    c = VCColor(cname)
    c.color_r, c.color_g, c.color_b = r, g, b
    c.target = ColorTarget.ALL
    c.midi_type = "note_on"
    c.midi_ch = 0
    c.midi_data1 = note
    x, y = pad_pos(note)
    add_widget(c, x, y, PAD, PAD)

# Beschriftungen
label("LightOS — APC Demo Show", X0, 16, 600, 28)
label("EFFEKTE (Reihe 3)   ·   LOOKS (Reihe 4)   ·   LIVE-FARBEN (Reihe 6)", X0, 50, 700, 20)
label("Master-Fader (rechts) = Grand Master / Gesamthelligkeit", X0, 74, 700, 20)

vc_layout = {"widgets": widgets}

# ── 3) Programmer leeren (Blackout-Start), Show benennen, speichern ────────────
state.programmer = {}
state._vc_layout = vc_layout
state.show_name = "APC Demo Show"

from src.core.show.show_file import save_show, load_show
save_show(OUT)
print(f"Gespeichert: {OUT}")

# ── 4) Verifikation: frisch laden und Inhalte zaehlen ──────────────────────────
ok, msg = load_show(OUT)
print("Load:", ok, msg)
funcs = fm.all()
print(f"Funktionen geladen: {len(funcs)}")
for f in funcs:
    print(f"   #{f.id} {f.function_type.value:8} {f.name}")
vc = state._vc_layout.get("widgets", [])
btns = [w for w in vc if w["type"] == "VCButton"]
cols = [w for w in vc if w["type"] == "VCColor"]
print(f"VC-Widgets: {len(vc)} (Buttons={len(btns)}, Color={len(cols)}, "
      f"Labels={sum(1 for w in vc if w['type']=='VCLabel')})")
print("Pad-Bindungen Buttons:", sorted(w["midi_data1"] for w in btns))
print("Pad-Bindungen Colors :", sorted(w["midi_data1"] for w in cols))
print("FERTIG")
