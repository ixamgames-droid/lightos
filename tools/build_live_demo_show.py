"""Demo-Show fuer das LIVE-PROGRAMMING der RGB-Matrix (Phase 7 der Matrix-Initiative).

Fuehrt die neue Matrix-Engine UND die Live-Steuerung ueber die virtuelle Konsole
vor — genau die Features der Phasen 1–6:

  - PATCH: 14 RGBW-PARs, angeordnet als 8x2-Matrix MIT 2 bewussten LUECKEN
    (None im fixture_grid) -> demonstriert das Gap-Handling (#1/#2): die Luecken
    sind in der Vorschau sichtbar leer und werden von Ausgabe/Algorithmen/Random
    uebersprungen.
  - MATRIX-FUNKTIONEN: die konsolidierten Grundalgorithmen + die neuen Algorithmen
    (Chase, Wipe, Wave, Gradient, Rainbow, Fill, Random, ColorFade) plus ein paar
    bewusst eigenstaendige Texturen (Radar, Fire, Rain, Spiral, Pinwheel, Breathe).
    Jede mit eigener Color-Sequence; drive_intensity=True -> sofort sichtbar.
  - VIRTUAL CONSOLE (das Headline-Feature, Phase 6):
      * untere Pad-Reihe = Effekt waehlen (FunctionToggle, exklusiv) -> setzt den
        AKTIVEN Effekt, auf den die "aktiver Effekt"-Bindungen wirken.
      * EFFECT_PARAM-Fader: level / speed / count / rate / density / spread / hold
        (Fader 0..100 % -> Wertebereich der jeweiligen ParamSpec, live).
      * EFFECT_ACTION-Buttons: next/prev/add color, reverse, freeze, reset-live,
        commit, tap (loesen Aktionen auf dem aktiven Effekt aus).
      * VCColor (Ziel = Effekt): faerbt live die aktive Sequence-Farbe.
    Alles mit MIDI-Bindung (APC mini mk2): Pads = Notes, Fader = CC48..56.

Aufruf:  venv/Scripts/python.exe tools/build_live_demo_show.py
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
_app = QApplication.instance() or QApplication([])

from src.core.app_state import get_state, get_channels_for_patched
from src.core.database.models import PatchedFixture
from src.core.engine.function_manager import get_function_manager
from src.core.engine.rgb_matrix import RgbAlgorithm, ColorSequence
from src.ui.virtualconsole.vc_button import VCButton, ButtonAction
from src.ui.virtualconsole.vc_color import VCColor, ColorTarget
from src.ui.virtualconsole.vc_slider import VCSlider, SliderMode
from src.ui.virtualconsole.vc_encoder import VCEncoder, EncoderMidiMode
from src.ui.virtualconsole.vc_label import VCLabel

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(_ROOT, "shows", "Live_Programming_Demo.lshow")

state = get_state()
fm = get_function_manager()

# ── 1) PATCH: 14 RGBW-PARs ──────────────────────────────────────────────────────
for f in list(state.get_patched_fixtures()):
    try:
        state.remove_fixture(f.fid, undoable=False)
    except Exception:
        pass

PAR_PROFILE, PAR_MODE, PAR_CH = 17, "8-Kanal RGBW", 8        # Generic Stage Light ZQ01424
N_PAR = 14
par_fids: list[int] = []
addr = 1
for i in range(N_PAR):
    fid = i + 1
    state.add_fixture(PatchedFixture(
        fid=fid, label=f"PAR {i+1}", fixture_profile_id=PAR_PROFILE,
        mode_name=PAR_MODE, universe=1, address=addr, channel_count=PAR_CH,
        manufacturer_name="Generic", fixture_name="Stage Light ZQ01424",
        fixture_type="color"), undoable=False)
    par_fids.append(fid)
    addr += PAR_CH

# ── 1b) 8x2-MATRIX MIT 2 LUECKEN (row-major, idx = row*cols + col) ──────────────
# Reihe 0: PAR 1..8   ·   Reihe 1: PAR 9,10,11, [Luecke], [Luecke], 12,13,14
COLS, ROWS = 8, 2
GRID = [1, 2, 3, 4, 5, 6, 7, 8,
        9, 10, 11, None, None, 12, 13, 14]
assert len(GRID) == COLS * ROWS
GAP_COUNT = sum(1 for x in GRID if x is None)

# ── 2) MATRIX-FUNKTIONEN ─────────────────────────────────────────────────────────
def matrix(name, algo, *, colors=None, params=None, speed=2.0):
    """RGB-Matrix-Funktion auf dem gemeinsamen 8x2-Raster (mit Luecken).

    drive_intensity=True -> die Matrix treibt auch die Helligkeit, damit Farbe +
    Bewegung ohne separate Dimmer-Ebene sofort sichtbar sind (ideal fuer eine Demo).
    """
    m = fm.new_rgb_matrix(name)
    m.algorithm = algo
    m.fixture_grid = list(GRID)
    m.cols, m.rows = COLS, ROWS
    m.drive_intensity = True
    if colors is not None:
        m.colors = ColorSequence([tuple(c) for c in colors])
    if params:
        m.params = dict(params)
    m.matrix_speed = speed
    return m


# Die 8 Grund-/Neu-Algorithmen (untere Pad-Reihe) — je mit passender Color-Sequence:
mx_chase = matrix("Chase", RgbAlgorithm.CHASE, colors=[(255, 0, 0)],
                  params={"axis": "H", "movement": "normal", "runner_count": 1,
                          "runner_width": 1, "fade": 0.35}, speed=4.0)
mx_wipe = matrix("Wipe", RgbAlgorithm.WIPE, colors=[(0, 200, 255), (255, 0, 120)],
                 params={"axis": "H", "movement": "normal", "edge_fade": 0.2}, speed=1.2)
mx_wave = matrix("Wave", RgbAlgorithm.WAVE, colors=[(0, 80, 255), (0, 255, 200)],
                 params={"origin": "left", "density": 1.0, "spread": 1.0}, speed=1.5)
mx_grad = matrix("Gradient", RgbAlgorithm.GRADIENT,
                 colors=[(255, 0, 0), (0, 255, 0), (0, 0, 255)],
                 params={"axis": "H", "blend": "smooth"}, speed=2.0)
mx_rain = matrix("Rainbow", RgbAlgorithm.RAINBOW,
                 params={"movement": "linear", "spread": 1.0,
                         "saturation": 1.0, "value": 1.0}, speed=1.5)
mx_fill = matrix("Fill", RgbAlgorithm.FILL, colors=[(255, 160, 0), (60, 0, 120)],
                 params={"level": 60.0, "fill_dir": "left", "edge": "hard"}, speed=1.0)
mx_rand = matrix("Random", RgbAlgorithm.RANDOM,
                 colors=[(255, 255, 255), (255, 0, 80), (0, 160, 255)],
                 params={"mode": "color", "count": 3, "rate": 3.0,
                         "scope": "all", "no_repeat": True}, speed=1.0)
mx_fade = matrix("ColorFade", RgbAlgorithm.COLORFADE,
                 colors=[(255, 0, 0), (0, 255, 0), (0, 0, 255)],
                 params={"hold": 0.1, "pingpong": False}, speed=1.0)
main_funcs = [mx_chase, mx_wipe, mx_wave, mx_grad, mx_rain, mx_fill, mx_rand, mx_fade]

# Eigenstaendige Texturen (zweite Pad-Reihe):
mx_radar = matrix("Radar", RgbAlgorithm.RADAR, colors=[(255, 160, 0)], speed=2.0)
mx_fire = matrix("Fire", RgbAlgorithm.FIRE, colors=[(255, 80, 0), (255, 220, 0)], speed=2.0)
mx_drip = matrix("Rain", RgbAlgorithm.RAIN, colors=[(0, 180, 255)],
                 params={"fade": 0.4}, speed=2.5)
mx_spiral = matrix("Spiral", RgbAlgorithm.SPIRAL, colors=[(180, 0, 255)],
                   params={"turns": 1.5}, speed=2.0)
mx_pin = matrix("Pinwheel", RgbAlgorithm.PINWHEEL, colors=[(255, 0, 0), (0, 0, 255)], speed=2.0)
mx_breathe = matrix("Breathe", RgbAlgorithm.BREATHE, colors=[(255, 0, 200)], speed=1.0)
texture_funcs = [mx_radar, mx_fire, mx_drip, mx_spiral, mx_pin, mx_breathe]


# ── 3) VIRTUAL CONSOLE ─────────────────────────────────────────────────────────
PAD, GAP, X0, Y0 = 70, 6, 20, 130
STEP = PAD + GAP
widgets = []


def pad_pos(note):
    """note 0-7 = UNTERSTE Reihe, 56-63 = oberste (wie an der APC mini mk2)."""
    row, col = note // 8, note % 8
    return X0 + col * STEP, Y0 + (7 - row) * STEP


def add_widget(w, x, y, ww, hh):
    w.setGeometry(x, y, ww, hh)
    widgets.append(w.to_dict())


def effect_button(fn, note, accent):
    """FunctionToggle, EXKLUSIV (nur 1 Effekt aktiv) + Programmer leeren ->
    eindeutiger 'aktiver Effekt' fuer die Live-Bindungen."""
    b = VCButton(fn.name)
    b.action = ButtonAction.FUNCTION_TOGGLE
    b.function_id = fn.id
    b.exclusive = True
    b.clear_programmer = True
    b.pad_style = "pulse"
    b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, note
    b._bg_color.setNamedColor(accent)
    x, y = pad_pos(note)
    add_widget(b, x, y, PAD, PAD)


def action_button(name, action_key, note, accent):
    """EFFECT_ACTION auf dem AKTIVEN Effekt (function_id=None)."""
    b = VCButton(name)
    b.action = ButtonAction.EFFECT_ACTION
    b.effect_action_key = action_key
    b.function_id = None
    b.pad_style = "solid"
    b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, note
    b._bg_color.setNamedColor(accent)
    x, y = pad_pos(note)
    add_widget(b, x, y, PAD, PAD)


def color_tile(name, note, r, g, b):
    """VCColor mit Ziel = Effekt -> faerbt live die aktive Sequence-Farbe."""
    c = VCColor(name)
    c.color_r, c.color_g, c.color_b = r, g, b
    c.target = ColorTarget.EFFECT
    c.function_id = None
    c.midi_type, c.midi_ch, c.midi_data1 = "note_on", 0, note
    x, y = pad_pos(note)
    add_widget(c, x, y, PAD, PAD)


def param_fader(caption, col, param_key, function_id, midi_cc, value=128):
    s = VCSlider(caption)
    s.mode = SliderMode.EFFECT_PARAM
    s.param_key = param_key
    s.function_id = function_id      # None = aktiver Effekt
    s.midi_cc, s.midi_ch = midi_cc, 0
    s._value = value
    x = X0 + col * STEP + 4
    add_widget(s, x, Y_FAD, 62, FAD_H)


def mode_fader(caption, col, mode, midi_cc, value=255):
    s = VCSlider(caption)
    s.mode = mode
    s.midi_cc, s.midi_ch = midi_cc, 0
    s._value = value
    x = X0 + col * STEP + 4
    add_widget(s, x, Y_FAD, 62, FAD_H)


# Reihe 0 (notes 0-7): die 8 Grund-/Neu-Algorithmen — Effekt waehlen (gold)
for i, fn in enumerate(main_funcs):
    effect_button(fn, i, "#7a5b00")

# Reihe 1 (notes 8-13): eigenstaendige Texturen (violett)
for i, fn in enumerate(texture_funcs):
    effect_button(fn, 8 + i, "#3a2150")

# Reihe 2 (notes 16-23): LIVE-AKTIONEN auf dem aktiven Effekt (teal)
ACTIONS = [
    ("Farbe +", "next_color", 16), ("Farbe -", "prev_color", 17),
    ("+ Farbe", "add_color", 18), ("Umkehren", "reverse_direction", 19),
    ("Freeze", "toggle_freeze", 20), ("Reset Live", "clear_live_override", 21),
    ("Commit", "commit_live", 22), ("Tap", "tap", 23),
]
for name, key, note in ACTIONS:
    action_button(name, key, note, "#0d3b40")

# Reihe 6 (notes 48-55, OBEN): LIVE-FARBEN -> aktive Sequence-Farbe des Effekts
for i, (cname, r, g, b) in enumerate([
        ("Rot", 255, 0, 0), ("Grün", 0, 255, 0), ("Blau", 0, 0, 255),
        ("Weiß", 255, 255, 255), ("Amber", 255, 140, 0), ("Cyan", 0, 255, 255),
        ("Magenta", 255, 0, 255), ("Gelb", 255, 255, 0)]):
    color_tile(cname, 48 + i, r, g, b)

# ── Fader-Reihe direkt unter dem Grid (CC48..56 = die 9 APC-mini-Fader) ─────────
Y_FAD = Y0 + 8 * STEP + 12
FAD_H = 200
# Aktiver Effekt:
param_fader("Speed", 0, "speed", None, 48, value=128)            # aktiver Effekt
# Effekt-spezifisch (Label passt zum gebundenen Effekt):
param_fader("Fill-Lvl", 1, "level", mx_fill.id, 49, value=153)   # ~60 %
param_fader("Count", 2, "count", mx_rand.id, 50, value=64)
param_fader("Rate", 3, "rate", mx_rand.id, 51, value=64)
param_fader("Density", 4, "density", mx_wave.id, 52, value=64)
param_fader("Spread", 5, "spread", mx_rain.id, 53, value=64)     # Rainbow-Spread
param_fader("Hold", 6, "hold", mx_fade.id, 54, value=40)
# Global:
mode_fader("FX-Speed", 7, SliderMode.SPEED, 55, value=128)       # Tempo ALLER Effekte
mode_fader("Master", 8, SliderMode.GRANDMASTER, 56, value=255)


# ── Encoder (relativ, rechts neben den Fadern) ──────────────────────────────────
def encoder(caption, param_key, function_id, x, midi_cc, step=0.05):
    e = VCEncoder(caption)
    e.param_key = param_key
    e.function_id = function_id       # None = aktiver Effekt
    e.step = step
    e.midi_mode = EncoderMidiMode.RELATIVE
    e.midi_cc, e.midi_ch = midi_cc, 0
    add_widget(e, x, Y_FAD, 96, 110)


EX = X0 + 9 * STEP + 16
encoder("Speed", "speed", None, EX, 57)              # aktiver Effekt (relativ feinjustieren)
encoder("Count", "count", mx_rand.id, EX + 104, 58)  # Random-Count

# ── Beschriftungen ───────────────────────────────────────────────────────────────
for text, x, y, ww, hh in [
    ("LightOS — LIVE-PROGRAMMING Demo (RGB-Matrix)", X0, 12, 760, 26),
    ("Reihe 1 (unten): Effekt WÄHLEN (exklusiv) -> wird der 'aktive Effekt'.  "
     "Reihe 2: eigenstaendige Texturen.", X0, 42, 1100, 20),
    ("Reihe 3: LIVE-AKTIONEN (Farbe +/- , + Farbe, Umkehren, Freeze, Reset, Commit, Tap) "
     "auf dem aktiven Effekt.", X0, 64, 1100, 20),
    ("Obere Reihe: LIVE-FARBEN faerben die aktive Sequence-Farbe.  "
     "Fader: Speed/Fill-Lvl/Count/Rate/Density/Spread/Hold + FX-Speed + Master.  "
     "Encoder (rechts): relativ feinjustieren.", X0, 86, 1250, 20),
    ("So testen: 1) Effekt-Pad unten drücken  2) Fader/Buttons/Farben/Encoder bewegen -> wirkt SOFORT live.  "
     "Die 2 Matrix-Luecken bleiben leer.", X0, 108, 1250, 20),
]:
    add_widget(VCLabel(text), x, y, ww, hh)

state._vc_layout = {"widgets": widgets}

# ── 4) Blackout-Start, benennen, speichern ─────────────────────────────────────
state.programmer = {}
state.show_name = "Live-Programming Demo"

from src.core.show.show_file import save_show, load_show
save_show(OUT)
print(f"Gespeichert: {OUT}")

# ── 5) Verifikation: frisch laden und Inhalte pruefen ───────────────────────────
ok, msg = load_show(OUT)
print("Load:", ok, msg)

from src.core.engine.function import FunctionType
mats = [f for f in fm.all() if f.function_type == FunctionType.RGBMatrix]
print(f"Matrix-Funktionen: {len(mats)}")
for m in mats:
    seq = m.colors.all_colors() if hasattr(m, "colors") else []
    gaps = sum(1 for x in m.fixture_grid if x is None)
    print(f"   {m.name:10} algo={m.algorithm.value:9} grid={m.cols}x{m.rows} "
          f"gaps={gaps} colors={len(seq)} params={m.params}")

vc = state._vc_layout.get("widgets", [])
counts = {}
for w in vc:
    counts[w["type"]] = counts.get(w["type"], 0) + 1
print(f"VC-Widgets: {len(vc)}  {counts}")

# Live-Bindungen ueberpruefen (Phase-6-Kontrakt):
ep = [(w["caption"], w.get("param_key"), w.get("function_id"), w.get("midi_cc"))
      for w in vc if w["type"] == "VCSlider" and w.get("mode") == SliderMode.EFFECT_PARAM]
ea = [(w["caption"], w.get("effect_action_key"), w.get("midi_data1"))
      for w in vc if w["type"] == "VCButton" and w.get("action") == ButtonAction.EFFECT_ACTION.value]
ec = [(w["caption"], w.get("midi_data1")) for w in vc
      if w["type"] == "VCColor" and w.get("target") == ColorTarget.EFFECT]
en = [(w["caption"], w.get("param_key"), w.get("function_id"), w.get("midi_mode"))
      for w in vc if w["type"] == "VCEncoder"]
print(f"EFFECT_PARAM-Fader ({len(ep)}):", ep)
print(f"EFFECT_ACTION-Buttons ({len(ea)}):", ea)
print(f"EFFECT-Farb-Kacheln ({len(ec)}):", ec)
print(f"Encoder ({len(en)}):", en)
print(f"Patch: {len(state.get_patched_fixtures())} PARs · Grid {COLS}x{ROWS} mit {GAP_COUNT} Luecken")
print("FERTIG")
