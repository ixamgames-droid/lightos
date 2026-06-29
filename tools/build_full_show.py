"""Komplette Demo-Lightshow fuer 3 RGBW-PARs + APC mini mk2 (v4).

Neu in v4:
  - Mehr kreative Effekte: Theater, Twinkle, Fire, Disco, Wave, 2-Color.
  - Slider sind jetzt FUNKTIONAL und synchron zur APC (gleiche CC):
    R/G/B/W = Programmer-Tint, Dimmer + Master = Grand Master.
    Touch ODER Fader bewegen -> letzte Eingabe gewinnt, Anzeige folgt.
  - Aufgeraeumt: linke Sektions-Beschriftung, Trennlinien, mehr Labels.

APC-Pads (Note=Reihe*8+Spalte, Reihe 0 unten; untere 2 Reihen = MIDI-Mapper):
  R3 (16-23) EFFEKTE 1 | R4 (24-31) LOOKS | R5 (32-39) SNAPSHOTS
  R6 (40-47) FARBEN | R7 (48-49) CLEAR+TAP | R8 (56-61) EFFEKTE 2

Aufruf: venv/Scripts/python.exe tools/build_full_show.py
"""
import os, sys, json, shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import _gen_env  # noqa: F401  # DEMO-02: spawn-sichere Env-Schalter vor src.core (tools/_gen_env.py)
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor
_app = QApplication.instance() or QApplication([])

from src.core.app_state import get_state, get_channels_for_patched
from src.core.engine.function_manager import get_function_manager
from src.core.engine.function import RunOrder
from src.core.engine.chaser import ChaserStep
from src.ui.virtualconsole.vc_button import VCButton, ButtonAction
from src.ui.virtualconsole.vc_color import VCColor, ColorTarget
from src.ui.virtualconsole.vc_slider import VCSlider, SliderMode
from src.ui.virtualconsole.vc_label import VCLabel

APPDIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "LightOS")
SNAP_FILE = os.path.join(APPDIR, "snapshots.json")
AUTO_SAVE = os.path.join(APPDIR, "auto_save.lshow")
MIDIMAP = os.path.join("data", "midi_mappings.json")
SHOW_OUT = os.path.join("shows", "APC_Demo_Show.lshow")

st = get_state()
fm = get_function_manager()
fixtures = st.get_patched_fixtures()
fids = [f.fid for f in fixtures]
chan = {c.attribute: c.channel_number for c in get_channels_for_patched(fixtures[0])}


def scene(name, r=0, g=0, b=0, w=0, intensity=255, only=None):
    s = fm.new_scene(name)
    for fid in (only if only is not None else fids):
        if "intensity" in chan:
            s.set_value(fid, chan["intensity"], intensity)
        for a, v in (("color_r", r), ("color_g", g), ("color_b", b), ("color_w", w)):
            if a in chan:
                s.set_value(fid, chan[a], v)
    return s


def chaser(name, step_ids, hold=0.5, fade=0.2, order=RunOrder.Loop, beat=False):
    c = fm.new_chaser(name)
    c.run_order = order
    c.audio_triggered = beat
    c.beats_per_step = 1
    for sid in step_ids:
        c.steps.append(ChaserStep(function_id=sid, fade_in=fade, hold=hold, fade_out=0.0))
    return c


fm._functions.clear()
L = {
    "white": scene("Open White", w=255), "warm": scene("Warm", r=255, g=110, b=20, w=40),
    "cold": scene("Cold", g=60, b=255), "red": scene("Rot", r=255),
    "amber": scene("Amber", r=255, g=140), "green": scene("Grün", g=255),
    "blue": scene("Blau", b=255), "magenta": scene("Magenta", r=255, b=255),
    "cyan": scene("Cyan", g=255, b=255), "off": scene("Black", intensity=0),
}
has3 = len(fids) >= 3
p_white = [scene(f"Nur P{i+1}", w=255, only=[fid]) for i, fid in enumerate(fids)]
p_color = ([scene("P1 Rot", r=255, only=[fids[0]]), scene("P2 Grün", g=255, only=[fids[1]]),
            scene("P3 Blau", b=255, only=[fids[2]])] if has3
           else [scene("P1 Rot", r=255, only=[fids[0]])])
# Theater (Funktionsbereiche aufteilen): aussen / mitte
t_out = scene("Theater Aussen", w=255, only=[fids[0], fids[2]]) if has3 else p_white[0]
t_mid = scene("Theater Mitte", w=255, only=[fids[1]]) if has3 else L["off"]
# Fire-Flicker
fire = [scene("Fire1", r=255, g=80), scene("Fire2", r=255, g=140, intensity=180),
        scene("Fire3", r=200, g=40, intensity=110)]

# (Funktion, Pad-RGB) — Reihe 3 (Haupteffekte)
chasers_1 = [
    (chaser("Color Chase", [L["red"].id, L["amber"].id, L["green"].id, L["cyan"].id, L["blue"].id, L["magenta"].id], 0.5, 0.25, beat=True), (255, 255, 255)),
    (chaser("Rainbow", [L["red"].id, L["amber"].id, L["green"].id, L["cyan"].id, L["blue"].id, L["magenta"].id], 0.3, 0.7, beat=True), (255, 0, 255)),
    (chaser("Lauflicht", [s.id for s in p_white], 0.25, 0.1, beat=True), (0, 255, 255)),
    (chaser("Farb-Lauflicht", [s.id for s in p_color], 0.3, 0.15, beat=True), (255, 140, 0)),
    (chaser("Bounce", [s.id for s in p_white], 0.22, 0.08, RunOrder.PingPong, beat=True), (0, 255, 0)),
    (chaser("Pulse", [L["white"].id, L["off"].id], 0.5, 0.6), (0, 0, 255)),
    (chaser("Police", [L["red"].id, L["off"].id, L["blue"].id, L["off"].id], 0.13, 0.0, beat=True), (255, 0, 0)),
    (chaser("Strobe", [L["white"].id, L["off"].id], 0.05, 0.0), (255, 255, 255)),
]
# Reihe 8 (kreative Effekte v2)
chasers_2 = [
    (chaser("Theater", [t_out.id, t_mid.id], 0.3, 0.05, beat=True), (255, 220, 120)),
    (chaser("Twinkle", [s.id for s in p_white], 0.12, 0.04, RunOrder.Random), (200, 200, 255)),
    (chaser("Fire", [f.id for f in fire], 0.1, 0.06, RunOrder.Random), (255, 80, 0)),
    (chaser("Disco", [L["red"].id, L["green"].id, L["blue"].id, L["magenta"].id, L["cyan"].id, L["amber"].id], 0.18, 0.0, RunOrder.Random, beat=True), (255, 0, 200)),
    (chaser("Wave", [L["red"].id, L["amber"].id, L["green"].id, L["cyan"].id, L["blue"].id, L["magenta"].id], 0.2, 1.2), (0, 200, 255)),
    (chaser("2-Color", [L["magenta"].id, L["cyan"].id], 0.3, 0.1, beat=True), (255, 0, 255)),
]
looks = [(L["white"], (255, 255, 255)), (L["warm"], (255, 140, 40)), (L["cold"], (0, 80, 255)),
         (L["red"], (255, 0, 0)), (L["amber"], (255, 160, 0)), (L["green"], (0, 255, 0)),
         (L["blue"], (0, 0, 255)), (L["magenta"], (255, 0, 255))]

snap_looks = [("Open White", 255, 255, 255, 255, 255), ("Warm", 255, 255, 110, 20, 40),
              ("Cold", 255, 0, 60, 255, 0), ("Rot", 255, 255, 0, 0, 0),
              ("Amber", 255, 255, 140, 0, 0), ("Grün", 255, 0, 255, 0, 0),
              ("Blau", 255, 0, 0, 255, 0), ("Blackout", 0, 0, 0, 0, 0)]
ap = set(chan.keys())
def sv(inten, r, g, b, w):
    base = {"intensity": inten, "color_r": r, "color_g": g, "color_b": b, "color_w": w}
    return {str(fid): {a: v for a, v in base.items() if a in ap} for fid in fids}
snaps = [{"name": n, "values": sv(i, r, g, b, w)} for (n, i, r, g, b, w) in snap_looks]
snaps += [{"name": "", "values": {}} for _ in range(48 - len(snaps))]
os.makedirs(APPDIR, exist_ok=True)
json.dump(snaps, open(SNAP_FILE, "w", encoding="utf-8"), indent=2, ensure_ascii=False)

tiles = [("Rot", 255, 0, 0), ("Amber", 255, 140, 0), ("Gelb", 255, 255, 0), ("Grün", 0, 255, 0),
         ("Cyan", 0, 255, 255), ("Blau", 0, 0, 255), ("Magenta", 255, 0, 255), ("Weiß", 255, 255, 255)]

# ── Virtual Console ────────────────────────────────────────────────────────────
PAD, GAP, X0, Y0 = 76, 6, 150, 140      # X0 nach rechts -> Platz fuer Sektions-Labels links
STEP = PAD + GAP
widgets = []
def pad_pos(note):
    row, col = note // 8, note % 8
    return X0 + col * STEP, Y0 + (7 - row) * STEP
def row_y(row):
    return Y0 + (7 - row) * STEP
def add(w, x, y, ww, hh):
    w.setGeometry(x, y, ww, hh); widgets.append(w.to_dict())

def section_label(text, row, rgb=(120, 130, 150)):
    lbl = VCLabel(text)
    lbl._bg_color = QColor(28, 32, 40)
    lbl._fg_color = QColor(*rgb)
    add(lbl, 10, row_y(row) + PAD // 2 - 16, 132, 32)

def divider(row_above):
    """Duenne Trennlinie oberhalb einer Reihe (grenzt Bereiche ab)."""
    ln = VCLabel("")
    ln._bg_color = QColor(70, 80, 100)
    y = row_y(row_above) - GAP // 2 - 2
    add(ln, 8, y, X0 + 8 * STEP - 8, 3)

# Pad-Stil je Effekt zur Demonstration der neuen Anzeige-Modi
PAD_STYLE = {
    "Police": ("alternate", (0, 0, 255)),   # rot/blau im Wechsel auf dem Pad
    "Color Chase": ("wave", None),           # Dauer-Welle
    "Rainbow": ("wave", None),
    "Disco": ("wave", None),
    "Pulse": ("pulse", None),                # Hardware-Pulsieren
    "Strobe": ("solid", None),
}

def fbtn(fn, note, rgb):
    b = VCButton(fn.name)
    b.action = ButtonAction.FUNCTION_TOGGLE
    b.function_id = fn.id
    b.exclusive = True
    b.clear_programmer = True
    b.midi_type = "note_on"; b.midi_ch = 0; b.midi_data1 = note
    b._bg_color = QColor(*rgb)
    style = PAD_STYLE.get(fn.name)
    if style:
        b.pad_style = style[0]
        if style[1]:
            b.pad_color2 = style[1]
    x, y = pad_pos(note); add(b, x, y, PAD, PAD)

for i, (c, rgb) in enumerate(chasers_1):
    fbtn(c, 16 + i, rgb)
for i, (c, rgb) in enumerate(chasers_2):
    fbtn(c, 56 + i, rgb)
for i, (fn, rgb) in enumerate(looks):
    fbtn(fn, 24 + i, rgb)
for i, (n, inten, r, g, b, w) in enumerate(snap_looks):
    note = 32 + i
    btn = VCButton(n); btn.action = ButtonAction.SNAPSHOT; btn.snapshot_index = i
    btn.midi_type = "note_on"; btn.midi_ch = 0; btn.midi_data1 = note
    btn._bg_color = QColor(r, g, b) if (r or g or b) else QColor(50, 50, 50)
    x, y = pad_pos(note); add(btn, x, y, PAD, PAD)
for i, (n, r, g, b) in enumerate(tiles):
    note = 40 + i
    c = VCColor(n); c.color_r, c.color_g, c.color_b = r, g, b
    c.target = ColorTarget.ALL
    c.midi_type = "note_on"; c.midi_ch = 0; c.midi_data1 = note
    x, y = pad_pos(note); add(c, x, y, PAD, PAD)

clr = VCButton("CLEAR"); clr.action = ButtonAction.CLEAR
clr.midi_type = "note_on"; clr.midi_ch = 0; clr.midi_data1 = 48
clr._bg_color = QColor(200, 40, 40)
x, y = pad_pos(48); add(clr, x, y, PAD, PAD)
tap = VCButton("TAP\nTempo"); tap.action = ButtonAction.TAP
tap.midi_type = "note_on"; tap.midi_ch = 0; tap.midi_data1 = 49
tap._bg_color = QColor(60, 60, 160)
x, y = pad_pos(49); add(tap, x, y, PAD, PAD)

# Funktionale + synchrone Slider (gleiche CC wie die APC-Fader)
slider_x = X0 + 8 * STEP + 24
slider_defs = [
    ("R", SliderMode.PROGRAMMER, "color_r", 48), ("G", SliderMode.PROGRAMMER, "color_g", 49),
    ("B", SliderMode.PROGRAMMER, "color_b", 50), ("W", SliderMode.PROGRAMMER, "color_w", 51),
    ("Tempo", SliderMode.BPM, "", 53), ("FX-Speed", SliderMode.SPEED, "", 54),
    ("Dimmer", SliderMode.GRANDMASTER, "", 52), ("Master", SliderMode.GRANDMASTER, "", 56),
]
for i, (name, mode, attr, cc) in enumerate(slider_defs):
    s = VCSlider(name); s.mode = mode
    if attr:
        s.programmer_attr = attr
    s.midi_cc = cc; s.midi_ch = 0
    add(s, slider_x + i * 66, row_y(8) + 4, 58, 4 * STEP + PAD - 8)
lbl = VCLabel("FADER: R/G/B/W · Tempo · FX-Speed · Dimmer · Master  (Touch ODER APC)")
lbl._bg_color = QColor(28, 32, 40); lbl._fg_color = QColor(120, 130, 150)
add(lbl, slider_x, row_y(8) - 30, 8 * 66, 24)

# Sektions-Labels links + Trennlinien
section_label("EFFEKTE 2", 8, (200, 160, 255))
section_label("EFFEKTE 1", 3, (200, 160, 255))
section_label("LOOKS", 4, (120, 180, 255))
section_label("SNAPSHOTS", 5, (255, 200, 120))
section_label("FARBEN", 6, (255, 140, 180))
section_label("STEUERUNG", 7, (255, 120, 120))
divider(8); divider(4); divider(5); divider(6); divider(7)

# Kopf-Beschriftung
for text, y in [("LightOS — Demo-Lightshow v4", 12),
                ("Effekt/Look = nur EINER aktiv, raeumt manuelle Farbe frei", 40),
                ("CLEAR = manuelle Farbe loslassen · TAP = Tempo der Beat-Effekte", 64),
                ("Farb-Kacheln = volle Farbe (mit Intensität) · Fader synchron zur APC", 88)]:
    hl = VCLabel(text); hl._bg_color = QColor(20, 22, 28); hl._fg_color = QColor(180, 190, 205)
    add(hl, 10, y, 900, 22)

st._vc_layout = {"widgets": widgets}
st.programmer = {}
st.show_name = "APC Demo Lightshow"

# ── Fader-Mappings (Basis = Original .bak) ─────────────────────────────────────
try:
    if os.path.exists(MIDIMAP + ".bak"):
        base = json.load(open(MIDIMAP + ".bak", encoding="utf-8"))
    else:
        base = json.load(open(MIDIMAP, encoding="utf-8"))
        json.dump(base, open(MIDIMAP + ".bak", "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    targets = {48: "programmer_value:color_r", 49: "programmer_value:color_g",
               50: "programmer_value:color_b", 51: "programmer_value:color_w", 52: "grand_master"}
    names = {48: "Fader R", 49: "Fader G", 50: "Fader B", 51: "Fader W", 52: "Dimmer"}
    n = 0
    for m in base:
        mi = m.get("midi_in", {}); tid = mi.get("trigger_id")
        if mi.get("message_type") == "cc" and tid in targets:
            m["target"] = targets[tid]; m["name"] = names[tid]; n += 1
    json.dump(base, open(MIDIMAP, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print(f"midi_mappings: {n} Fader (R/G/B/W + Dimmer); Master=Grand Master")
except Exception as e:
    print(f"midi remap uebersprungen: {e}")

from src.core.show.show_file import save_show, load_show
save_show(SHOW_OUT)
shutil.copyfile(SHOW_OUT, AUTO_SAVE)

ok, _ = load_show(SHOW_OUT)
vc = st._vc_layout.get("widgets", [])
def cnt(t, a=None): return sum(1 for w in vc if w.get("type") == t and (a is None or w.get("action") == a))
beats = sum(1 for f in fm.all() if getattr(f, "audio_triggered", False))
print("Load:", ok, "| Funktionen:", len(fm.all()), "| Beat-Chaser:", beats,
      "| Effekte gesamt:", len(chasers_1) + len(chasers_2))
print(f"VC: Func={cnt('VCButton','FunctionToggle')} Snap={cnt('VCButton','Snapshot')} "
      f"Clear={cnt('VCButton','Clear')} Tap={cnt('VCButton','Tap')} Color={cnt('VCColor')} "
      f"Slider={cnt('VCSlider')} Label={cnt('VCLabel')}")
print("FERTIG ->", SHOW_OUT)
