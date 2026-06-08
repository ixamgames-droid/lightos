"""Bühnen-Show für Davids REALE Hardware (keine Moving Heads):
  - 1× RGBW-Controller auf DMX 1-4 (Generic LED PAR RGBW 4ch, color_r/g/b/w)
  - 3× Standard-PAR ab DMX 5 (Generic Stage Light ZQ01424, 8-Kanal RGBW)

NEUES, intuitives Layer-Prinzip (überarbeitet 2026-06-02):

  * BASIS-HELLIGKEIT: Die 3 PARs haben eine Grund-Intensität (state.base_levels).
    Dadurch ist eine reine FARBE sofort sichtbar — und ein Dimmer-Effekt
    ÜBERSCHREIBT die Basis und kann bis 0 dunkeln (echtes Lauflicht!).

  * FARB-EBENE (NUR Farbe, keine Helligkeit): Farb-Kacheln (oben) + R/G/B/W.
    -> Farbe wählen, dann Dimmer-Effekt starten = Effekt in dieser Farbe.
    -> Live Farbe wechseln, Effekt läuft weiter.

  * DIMMER-EFFEKTE (unterste Reihe, NUR Intensität, voll-abdeckend): jeder
    Schritt setzt ALLE PARs (an=255, aus=0) -> sauberes Dunkelwerden.
    Die 4 Fader links DARUNTER regeln die GESCHWINDIGKEIT dieser Effekte.

  * SELBST-FARBIGE EFFEKTE: RGB-Matrix bringen ihre Farben selbst mit
    (Farbe vorher mit 'Clear' freigeben, sonst überschreibt die Farb-Ebene).

  * FADER (9, direkt unter dem Pad-Grid wie an der echten APC):
      F1-F4 = Speed je Dimmer-Effekt (Lauflicht/Pulse/Wave/Strobe)
      F5    = Effekt-Helligkeit (alle Dimmer-Effekte gemeinsam)
      F6    = DIMMER (PAR-Grundhelligkeit, regelt bis 0)
      F7    = Speed GLOBAL (alle laufenden Effekte, großer Bereich)
      F8    = Matrix-Master (Helligkeit der Matrix-Effekte)
      F9    = GRAND MASTER

Aufruf:  venv/Scripts/python.exe tools/build_stage_show.py

WICHTIG (2026-06-02): Die ausgelieferte shows/Buehnen_Show.lshow wurde NACH der
Generierung mit tools/patch_stage_show_pages.py auf ein ZWEI-SEITEN-Layout
(VC-Banks) umgebaut und enthaelt inzwischen eine vom User gepflegte Library
(Farb-Snaps). Dieser Generator erzeugt nur das EINSEITIGE Grund-Layout OHNE
Library. Nicht blind neu generieren -> sonst gehen die Farb-Seite (Bank 2,
Fader 1-4 = RGBW) und die Library verloren. Nach einem Neu-Bau jeweils
tools/patch_stage_show_pages.py erneut ausfuehren.
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
from src.core.engine.function import RunOrder, Direction
from src.core.engine.chaser import ChaserStep
from src.core.engine.rgb_matrix import RgbAlgorithm
from src.core.engine.carousel import CarouselPattern
from src.core.engine.snap_library import get_snap_library
from src.ui.virtualconsole.vc_button import VCButton, ButtonAction
from src.ui.virtualconsole.vc_color import VCColor, ColorTarget
from src.ui.virtualconsole.vc_slider import VCSlider, SliderMode
from src.ui.virtualconsole.vc_label import VCLabel

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(_ROOT, "shows", "Buehnen_Show.lshow")

state = get_state()
fm = get_function_manager()
lib = get_snap_library()

# ── 1) PATCH: RGBW (1-4) + 3 PARs (ab 5) ───────────────────────────────────────
for f in list(state.get_patched_fixtures()):
    try:
        state.remove_fixture(f.fid, undoable=False)
    except Exception:
        pass

state.add_fixture(PatchedFixture(
    fid=1, label="RGBW LED (1-4)", fixture_profile_id=5, mode_name="4-Kanal RGBW",
    universe=1, address=1, channel_count=4,
    manufacturer_name="Generic", fixture_name="LED PAR RGBW 4ch",
    fixture_type="color"), undoable=False)

par_fids = []
addr = 5
for i in range(3):
    fid = 2 + i
    state.add_fixture(PatchedFixture(
        fid=fid, label=f"PAR {i+1}", fixture_profile_id=17, mode_name="8-Kanal RGBW",
        universe=1, address=addr, channel_count=8,
        manufacturer_name="Generic", fixture_name="Stage Light ZQ01424",
        fixture_type="color"), undoable=False)
    par_fids.append(fid)
    addr += 8

fixtures = state.get_patched_fixtures()
all_fids = [f.fid for f in fixtures]              # [1,2,3,4]  (RGBW + 3 PARs)
chan_of = {f.fid: {c.attribute: c.channel_number
                   for c in get_channels_for_patched(f)} for f in fixtures}

# ── 1b) BASIS-HELLIGKEIT: PARs "scharf" -> Farbe sofort sichtbar ────────────────
# Wird mit der Show gespeichert und in den Default-Frame gelegt. Dimmer-Effekte
# überschreiben diese Basis (können bis 0 dunkeln); der DIMMER-Fader (F6) regelt
# sie multiplikativ herunter.
state.base_levels = {fid: {"intensity": 255} for fid in par_fids}
state._rebuild_render_plan()


# ── 2) DIMMER-EFFEKTE: VOLL-ABDECKEND (jeder Schritt setzt ALLE PARs) ───────────
# So wird ein nicht aktiver PAR wirklich 0 (sauberes Lauflicht), statt auf der
# Basis-Helligkeit hängen zu bleiben. KEINE Farbe -> nehmen die gewählte Farbe an.
def dim_step(name, on_fids):
    s = fm.new_scene(name)
    on = set(on_fids)
    for fid in par_fids:
        if "intensity" in chan_of[fid]:
            s.set_value(fid, chan_of[fid]["intensity"], 255 if fid in on else 0)
    return s


st_p1 = dim_step("Dim nur P1", [2])
st_p2 = dim_step("Dim nur P2", [3])
st_p3 = dim_step("Dim nur P3", [4])
st_all = dim_step("Dim alle", par_fids)
st_off = dim_step("Dim aus", [])
st_b1 = dim_step("Build 1", [2])
st_b2 = dim_step("Build 2", [2, 3])
st_b3 = dim_step("Build 3", par_fids)


def chaser(name, steps, hold=0.4, fade=0.0, order=RunOrder.Loop,
           direction=Direction.Forward, speed=1.0):
    c = fm.new_chaser(name)
    c.run_order = order
    c.direction = direction
    c.speed = speed
    for sid in steps:
        c.steps.append(ChaserStep(function_id=sid, fade_in=fade, hold=hold, fade_out=0.0))
    return c


dim_run = chaser("Lauflicht", [st_p1.id, st_p2.id, st_p3.id], hold=0.4, fade=0.1)
dim_strobe = chaser("Strobe", [st_all.id, st_off.id], hold=0.04, fade=0.0)
dim_rev = chaser("Lauflicht <-", [st_p1.id, st_p2.id, st_p3.id],
                 hold=0.4, fade=0.1, direction=Direction.Backward)
dim_build = chaser("Build-Up", [st_b1.id, st_b2.id, st_b3.id, st_off.id], hold=0.35, fade=0.12)
dim_rand = chaser("Random", [st_p1.id, st_p2.id, st_p3.id, st_all.id],
                  hold=0.3, fade=0.0, order=RunOrder.Random)

# Pulse + Wave als frei laufende Carousels (modulieren ALLE PARs -> bis ~0).
dim_pulse = fm.new_carousel("Pulse")
dim_pulse.pattern = CarouselPattern.PULSE
dim_pulse.fixture_ids = list(par_fids)
dim_pulse.sync_to_beat = False
dim_pulse.speed = 1.0

dim_wave = fm.new_carousel("Wave")
dim_wave.pattern = CarouselPattern.WAVE
dim_wave.fixture_ids = list(par_fids)
dim_wave.sync_to_beat = False
dim_wave.speed = 1.0

dim_full = fm.new_scene("Full (alle an)")
for fid in par_fids:
    if "intensity" in chan_of[fid]:
        dim_full.set_value(fid, chan_of[fid]["intensity"], 255)

# Die 4 Effekte, deren Speed die Fader F1-F4 (unter ihnen) regeln:
speed_targets = [dim_run, dim_pulse, dim_wave, dim_strobe]
# Alle Dimmer-Effekte (für den gemeinsamen Effekt-Helligkeits-Fader F5):
dimmer_funcs = [dim_run, dim_pulse, dim_wave, dim_strobe, dim_rev, dim_build, dim_rand]


# ── 3) SELBST-FARBIGE EFFEKTE: RGB-Matrix auf der 4er-Gruppe ────────────────────
group = all_fids


def matrix(name, algo, c1=(255, 0, 0), c2=(0, 0, 255), c3=(0, 255, 0), speed=3.0):
    m = fm.new_rgb_matrix(name)
    m.algorithm = algo
    m.fixture_grid = list(group)
    m.cols = len(group)
    m.rows = 1
    m.color1, m.color2, m.color3 = c1, c2, c3
    m.matrix_speed = speed
    return m


# Phase-3-Konsolidierung: Color-Scroll/Multicolor sind jetzt Gradient/Chase + Parameter.
mx_scroll = matrix("Matrix 3-Farben", RgbAlgorithm.GRADIENT,
                   c1=(255, 0, 0), c2=(0, 255, 0), c3=(0, 0, 255), speed=2.5)
mx_scroll.params = {"axis": "H", "blend": "steps"}
mx_multi = matrix("Matrix Multicolor", RgbAlgorithm.CHASE,
                  c1=(255, 0, 0), c2=(0, 255, 0), c3=(0, 0, 255), speed=4.0)
mx_multi.params = {"axis": "H", "movement": "normal", "color_cycle": True}
mx_run = matrix("Matrix Lauflicht", RgbAlgorithm.CHASE, c1=(255, 255, 255), speed=4.0)
mx_rain = matrix("Matrix Regenbogen", RgbAlgorithm.RAINBOW, speed=1.5)
mx_wipe = matrix("Matrix Wipe", RgbAlgorithm.WIPE, c1=(0, 200, 255), c2=(255, 0, 120), speed=1.2)
mx_spark = matrix("Matrix Sparkle", RgbAlgorithm.RANDOM, c1=(255, 255, 255), speed=6.0)
mx_spark.params = {"mode": "sparkle", "count": 2, "rate": 3.0}
mx_radar = matrix("Matrix Radar", RgbAlgorithm.RADAR, c1=(255, 160, 0), speed=2.0)
matrix_funcs = [mx_scroll, mx_multi, mx_run, mx_rain, mx_wipe, mx_spark, mx_radar]


# ── 4) FARBIGE CHASER (bringen Farbe + Helligkeit selbst mit) ───────────────────
def look(name, r=0, g=0, b=0, w=0, intensity=255):
    s = fm.new_scene(name)
    for f_id in all_fids:
        cm = chan_of[f_id]
        if "intensity" in cm:
            s.set_value(f_id, cm["intensity"], intensity)
        if "shutter" in cm:
            s.set_value(f_id, cm["shutter"], 255)
        for attr, val in (("color_r", r), ("color_g", g), ("color_b", b), ("color_w", w)):
            if attr in cm:
                s.set_value(f_id, cm[attr], val)
    return s


lk_red = look("Rot", r=255)
lk_green = look("Gruen", g=255)
lk_blue = look("Blau", b=255)
lk_mag = look("Magenta", r=255, b=255)
lk_cyan = look("Cyan", g=255, b=255)
lk_amber = look("Amber", r=255, g=140)

ch_color = chaser("Color Chase",
                  [lk_red.id, lk_green.id, lk_blue.id, lk_mag.id, lk_cyan.id, lk_amber.id],
                  hold=0.55, fade=0.25)
ch_police = chaser("Police", [lk_red.id, lk_blue.id], hold=0.18, fade=0.0)
ch_rain = chaser("Regenbogen Chase",
                 [lk_red.id, lk_amber.id, lk_green.id, lk_cyan.id, lk_blue.id, lk_mag.id],
                 hold=0.35, fade=0.3)


# ── 5) FARB-PALETTEN (nur Farbe) als Snaps in der Bibliothek ────────────────────
lib.clear()
lib.add_folder("Farben")
for nm, (r, g, b) in [("Warmweiss", (255, 140, 40)), ("Tiefblau", (0, 30, 255)),
                      ("Pink", (255, 0, 140)), ("Tuerkis", (0, 220, 180))]:
    values = {f_id: {a: v for a, v in (("color_r", r), ("color_g", g), ("color_b", b))
                     if a in chan_of[f_id]} for f_id in all_fids}
    lib.add_snap(nm, "Farben", values)


# ── 6) VIRTUAL CONSOLE — Farben oben, Effekte unten, Fader unter dem Grid ───────
PAD, GAP, X0, Y0 = 70, 6, 20, 120
STEP = PAD + GAP
widgets = []


def pad_pos(note):
    """note 0-7 = UNTERSTE Reihe, 56-63 = oberste (wie an der APC mini mk2)."""
    row, col = note // 8, note % 8
    return X0 + col * STEP, Y0 + (7 - row) * STEP


def add_widget(w, x, y, ww, hh):
    w.setGeometry(x, y, ww, hh)
    widgets.append(w.to_dict())


def func_button(fn, note, accent, style="pulse"):
    b = VCButton(fn.name)
    b.action = ButtonAction.FUNCTION_TOGGLE
    b.function_id = fn.id
    b.pad_style = style                 # 'pulse' = blinkt/pulsiert wenn aktiv
    b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, note
    b._bg_color.setNamedColor(accent)
    x, y = pad_pos(note)
    add_widget(b, x, y, PAD, PAD)


def action_button(name, action, note, accent):
    b = VCButton(name)
    b.action = action
    b.pad_style = "solid"
    b.midi_type, b.midi_ch, b.midi_data1 = "note_on", 0, note
    b._bg_color.setNamedColor(accent)
    x, y = pad_pos(note)
    add_widget(b, x, y, PAD, PAD)


def color_tile(name, note, r, g, b, w=0):
    c = VCColor(name)
    c.color_r, c.color_g, c.color_b, c.color_w = r, g, b, w
    c.with_intensity = False            # NUR Farbe — Helligkeit kommt aus der Basis
    c.target = ColorTarget.ALL          # auf alle Fixtures (Farb-Ebene)
    c.midi_type, c.midi_ch, c.midi_data1 = "note_on", 0, note
    x, y = pad_pos(note)
    add_widget(c, x, y, PAD, PAD)


def fader(caption, col, mode, function_id=None, function_ids=None,
          programmer_attr="intensity", midi_cc=-1, value=0, submaster_slot=None):
    s = VCSlider(caption)
    s.mode = mode
    s.function_id = function_id
    s.function_ids = list(function_ids or [])
    if submaster_slot is not None:
        s.function_id = submaster_slot   # SUBMASTER nutzt function_id als Slot
    s.programmer_attr = programmer_attr
    s.midi_cc, s.midi_ch = midi_cc, 0
    s._value = value
    x = X0 + col * STEP + 4
    add_widget(s, x, Y_FAD, 62, FAD_H)


# ── Pad-Reihen ──────────────────────────────────────────────────────────────────
# Reihe 0 (notes 0-7, UNTEN): DIMMER-EFFEKTE (F1-F4 regeln Speed der ersten 4)
func_button(dim_run, 0, "#234a2a")
func_button(dim_pulse, 1, "#234a2a")
func_button(dim_wave, 2, "#234a2a")
func_button(dim_strobe, 3, "#234a2a")
func_button(dim_rev, 4, "#1d3d24")
func_button(dim_build, 5, "#1d3d24")
func_button(dim_rand, 6, "#1d3d24")
func_button(dim_full, 7, "#3a3a14")

# Reihe 1 (notes 8-15): STEUERUNG + FARB-CHASER
action_button("Clear", ButtonAction.CLEAR, 8, "#4a3a10")
action_button("Stop All", ButtonAction.STOP_ALL, 9, "#4a1010")
action_button("Blackout", ButtonAction.BLACKOUT, 10, "#2a0000")
func_button(ch_color, 12, "#3a2150")
func_button(ch_police, 13, "#3a2150")
func_button(ch_rain, 14, "#3a2150")

# Reihe 2 (notes 16-23): SELBST-FARBIGE MATRIX-Effekte (gold)
for i, fn in enumerate(matrix_funcs):
    func_button(fn, 16 + i, "#7a5b00")

# Reihe 6 (notes 48-55, OBEN): FARBEN (nur Farbe; mit Basis sofort sichtbar)
for i, (cname, r, g, b, w) in enumerate([
        ("Rot", 255, 0, 0, 0), ("Gruen", 0, 255, 0, 0), ("Blau", 0, 0, 255, 0),
        ("Weiss", 255, 255, 255, 0), ("Warmweiss", 255, 130, 40, 0),
        ("Amber", 255, 140, 0, 0), ("Cyan", 0, 255, 255, 0), ("Magenta", 255, 0, 255, 0)]):
    color_tile(cname, 48 + i, r, g, b, w)

# ── Fader-Reihe: direkt UNTER dem Grid, ausgerichtet unter den Spalten ──────────
Y_FAD = Y0 + 8 * STEP + 12
FAD_H = 200
# CC48-56 = die 9 Fader der APC mini mk2 (CC56 = Grand Master im Default-Profil).
fader("Sp Lauf", 0, SliderMode.EFFECT_SPEED, function_id=dim_run.id, midi_cc=48, value=60)
fader("Sp Pulse", 1, SliderMode.EFFECT_SPEED, function_id=dim_pulse.id, midi_cc=49, value=60)
fader("Sp Wave", 2, SliderMode.EFFECT_SPEED, function_id=dim_wave.id, midi_cc=50, value=60)
fader("Sp Strobe", 3, SliderMode.EFFECT_SPEED, function_id=dim_strobe.id, midi_cc=51, value=60)
fader("FX-Level", 4, SliderMode.EFFECT_INTENSITY,
      function_ids=[f.id for f in dimmer_funcs], midi_cc=52, value=255)
fader("Dimmer", 5, SliderMode.SUBMASTER, submaster_slot=0, midi_cc=53, value=255)
fader("Speed", 6, SliderMode.SPEED, midi_cc=54, value=60)
fader("Mtx-Mst", 7, SliderMode.EFFECT_INTENSITY,
      function_ids=[m.id for m in matrix_funcs], midi_cc=55, value=255)
fader("Master", 8, SliderMode.GRANDMASTER, midi_cc=56, value=255)

# ── Beschriftungen oben ─────────────────────────────────────────────────────────
for text, x, y, ww, hh in [
    ("LightOS — Bühnen-Show:  FARBEN oben · DIMMER-EFFEKTE unten · Fader = Speed/Dimmer", X0, 12, 980, 26),
    ("So testen: 1) Farbe wählen (oben)  2) Dimmer-Effekt starten (unten)  "
     "3) Speed mit Fader F1-F4 regeln  ·  'Clear' gibt die Farbe wieder frei", X0, 44, 1000, 20),
    ("Matrix-Effekte (gold) bringen eigene Farben mit -> vorher 'Clear' drücken. "
     "F6 = Dimmer (bis 0), F7 = Speed global, F9 = Master.", X0, 66, 1000, 20),
    ("Fader unter dem Grid:  F1-F4 Speed (Lauf/Pulse/Wave/Strobe) · F5 FX-Level · "
     "F6 Dimmer · F7 Speed global · F8 Matrix-Master · F9 Master", X0, 88, 1100, 20),
]:
    add_widget(VCLabel(text), x, y, ww, hh)

state._vc_layout = {"widgets": widgets}

# ── 7) Blackout-Start, benennen, speichern ─────────────────────────────────────
state.programmer = {}
state.show_name = "Buehnen-Show"

from src.core.show.show_file import save_show, load_show
save_show(OUT)
print(f"Gespeichert: {OUT}")

# ── 8) Verifikation ────────────────────────────────────────────────────────────
ok, msg = load_show(OUT)
print("Load:", ok, msg)
by = {}
for f in fm.all():
    by.setdefault(f.function_type.value, []).append(f.name)
print(f"Funktionen: {len(fm.all())}")
for t, names in sorted(by.items()):
    print(f"   {t:10} ({len(names)}): {', '.join(names)}")
print(f"Patch: {[(f.fid, f.label, f.address, f.channel_count) for f in state.get_patched_fixtures()]}")
print(f"Basis-Level: {state.base_levels}")
vc = state._vc_layout.get("widgets", [])
counts = {}
for w in vc:
    counts[w["type"]] = counts.get(w["type"], 0) + 1
print(f"VC: {len(vc)} {counts}")
print("FERTIG")
