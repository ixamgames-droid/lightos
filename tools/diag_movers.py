r"""Diagnose: bewegen die EFX die Mover auf DMX-Ebene? (headless, kein Output-Thread)

Laedt VC_Test_2026.lshow, startet 'MH Kreis' + 'Spider Kreis', rendert Frames und
zeigt, welche DMX-Kanaele sich aendern. So trennt sich Engine-Bug (Kanaele aendern
sich NICHT) von Hardware/Adresse/Modus (Kanaele aendern sich, Geraet folgt nicht).

Aufruf: venv\Scripts\python.exe tools\diag_movers.py
"""
from __future__ import annotations
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["LIGHTOS_SHOW_DB"] = os.path.join(os.environ.get("TEMP", "."), "lightos_vctest.db")
os.environ["LIGHTOS_NO_OUTPUT_THREAD"] = "1"
os.environ["LIGHTOS_NO_AUDIO_AUTOSTART"] = "1"

from PySide6.QtWidgets import QApplication
_app = QApplication.instance() or QApplication([])

from src.core.app_state import get_state, get_channels_for_patched
from src.core.engine.function_manager import get_function_manager
from src.core.show.show_file import load_show

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "shows", "VC_Test_2026.lshow")
ok, msg = load_show(OUT)
print("Load:", ok, msg)
state = get_state()
fm = get_function_manager()

# Patch-Adressen zeigen
print("\n-- Patch --")
for f in sorted(state.get_patched_fixtures(), key=lambda x: x.address):
    print(f"  fid={f.fid:2d} addr={f.address:3d} ch={f.channel_count:2d}  {f.label}")

# Kanal-Attribut-Karte der Mover (welcher absolute Kanal = pan/tilt/intensity/shutter/speed)
print("\n-- Mover-Kanaele (absolut) --")
for f in state.get_patched_fixtures():
    if f.fixture_type == "moving_head":
        chans = get_channels_for_patched(f)
        rel = {(c.attribute or "?"): c.channel_number for c in chans}
        print(f"  {f.label} @ {f.address}: " +
              ", ".join(f"{a}={n}" for a, n in rel.items()
                        if a in ("pan", "tilt", "pan_fine", "tilt_fine",
                                 "intensity", "shutter", "speed")))

# Mover-EFX starten
started = []
for f in fm.all():
    if f.name in ("MH Kreis", "Spider Kreis"):
        fm.start(f.id)
        started.append(f.name)
print("\nGestartet:", started)


def snap():
    u = state.universes.get(1)
    return [int(u.get_channel(c)) if u else 0 for c in range(1, 130)]


for _ in range(3):
    state._render_frame(1 / 44.0)
a = snap()
for _ in range(25):
    state._render_frame(1 / 44.0)
b = snap()

print("\n-- DMX 60..114 (Frame 3 -> Frame 28) --")
for c in range(60, 115):
    av, bv = a[c - 1], b[c - 1]
    if av or bv:
        mark = "  <== AENDERT SICH (Bewegung/Effekt)" if av != bv else ""
        print(f"  CH{c:3d}: {av:3d} -> {bv:3d}{mark}")
print("\nFERTIG")
