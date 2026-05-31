"""Baut fertige SNAPSHOT-Looks (Programmer-basiert) + eine Virtual Console, die
die Snaps auf die APC-Pads legt. Snapshots wenden direkt Programmer-Werte an —
genau der Pfad, der beim manuellen Steuern nachweislich Licht macht.

Aufruf: venv/Scripts/python.exe tools/build_snaps_show.py
"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
_app = QApplication.instance() or QApplication([])

from src.core.app_state import get_state, get_channels_for_patched
from src.ui.virtualconsole.vc_button import VCButton, ButtonAction
from src.ui.virtualconsole.vc_label import VCLabel

SNAP_FILE = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")),
                         "LightOS", "snapshots.json")
SHOW_OUT = os.path.join("shows", "APC_Demo_Show.lshow")
AUTO_SAVE = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")),
                         "LightOS", "auto_save.lshow")
SNAPSHOT_TOTAL = 48

state = get_state()
fids = [f.fid for f in state.get_patched_fixtures()]
attrs_present = {c.attribute for c in get_channels_for_patched(state.get_patched_fixtures()[0])}

# ── Looks: (Name, intensity, r, g, b, w) ───────────────────────────────────────
looks = [
    ("Open White", 255, 255, 255, 255, 255),
    ("Warm",       255, 255, 110,  20,  40),
    ("Cold",       255,   0,  60, 255,   0),
    ("Rot",        255, 255,   0,   0,   0),
    ("Gruen",      255,   0, 255,   0,   0),
    ("Blau",       255,   0,   0, 255,   0),
    ("Amber",      255, 255, 140,   0,   0),
    ("Magenta",    255, 255,   0, 255,   0),
    ("Cyan",       255,   0, 255, 255,   0),
    ("Pink",       255, 255,  60, 120,   0),
    ("Halb (50%)", 128, 255, 255, 255, 128),
    ("Blackout",     0,   0,   0,   0,   0),
]


def look_values(intensity, r, g, b, w) -> dict:
    """Programmer-Werte je Fixture fuer einen Look (nur vorhandene Kanaele)."""
    vals = {}
    base = {"intensity": intensity, "color_r": r, "color_g": g,
            "color_b": b, "color_w": w}
    for fid in fids:
        fx_vals = {a: v for a, v in base.items() if a in attrs_present}
        vals[str(fid)] = fx_vals
    return vals


# ── 1) snapshots.json schreiben (48 Slots, vorne befuellt) ─────────────────────
snaps = []
for i in range(SNAPSHOT_TOTAL):
    if i < len(looks):
        name, inten, r, g, b, w = looks[i]
        snaps.append({"name": name, "values": look_values(inten, r, g, b, w)})
    else:
        snaps.append({"name": "", "values": {}})

os.makedirs(os.path.dirname(SNAP_FILE), exist_ok=True)
with open(SNAP_FILE, "w", encoding="utf-8") as f:
    json.dump(snaps, f, indent=2, ensure_ascii=False)
print(f"Snapshots geschrieben: {SNAP_FILE} ({len(looks)} Looks)")

# ── 2) Virtual Console: APC-Pads -> Snapshot-Recall ────────────────────────────
PAD, GAP, X0, Y0 = 76, 6, 20, 120
STEP = PAD + GAP
widgets = []


def pad_pos(note):
    row, col = note // 8, note % 8
    return X0 + col * STEP, Y0 + (7 - row) * STEP


def add(w, x, y, ww, hh):
    w.setGeometry(x, y, ww, hh)
    widgets.append(w.to_dict())


# Snap-Buttons auf den freien Pads ab Note 16 (untere 2 Reihen sind Mapper-belegt)
for i, (name, *_rest) in enumerate(looks):
    note = 16 + i
    b = VCButton(name)
    b.action = ButtonAction.SNAPSHOT
    b.snapshot_index = i
    b.midi_type = "note_on"
    b.midi_ch = 0
    b.midi_data1 = note
    if name == "Blackout":
        b._bg_color.setNamedColor("#3a1111")
    x, y = pad_pos(note)
    add(b, x, y, PAD, PAD)

for text, x, y in [
    ("LightOS — Snap-Show (Programmer-Looks)", X0, 16),
    ("Pads ab Reihe 3 = Looks nacheinander abrufen · letzter Pad = Blackout", X0, 50),
]:
    lbl = VCLabel(text)
    add(lbl, x, y, 640, 24)

state._vc_layout = {"widgets": widgets}
state.programmer = {}
state.show_name = "APC Snap Show"

from src.core.show.show_file import save_show, load_show
save_show(SHOW_OUT)
import shutil
shutil.copyfile(SHOW_OUT, AUTO_SAVE)
print(f"Show gespeichert: {SHOW_OUT} (+ auto_save)")

# ── 3) Verifikation ────────────────────────────────────────────────────────────
ok, msg = load_show(SHOW_OUT)
vc = state._vc_layout.get("widgets", [])
snapbtns = [w for w in vc if w.get("type") == "VCButton" and w.get("action") == "Snapshot"]
print("Load:", ok)
print(f"Snapshot-Buttons im Show-VC: {len(snapbtns)} (Pads {sorted(w['midi_data1'] for w in snapbtns)})")
with open(SNAP_FILE, encoding="utf-8") as f:
    chk = json.load(f)
filled = [s for s in chk if s.get("values")]
print(f"snapshots.json: {len(filled)} belegte Slots: {[s['name'] for s in filled]}")
print("Beispiel Look 'Rot' fid1:", chk[3]["values"].get(str(fids[0])))
print("FERTIG")
