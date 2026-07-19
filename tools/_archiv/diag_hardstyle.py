r"""Headless-Verifikation der Hardstyle-Show: laedt sie, treibt den Tempo-Bus,
prueft Beat-Blink (R,R,R,W pro Beat), Spider-Bar-Farben und Gobo-Szene."""
from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["LIGHTOS_NO_OUTPUT_THREAD"] = "1"
os.environ["LIGHTOS_NO_AUDIO_AUTOSTART"] = "1"

from PySide6.QtWidgets import QApplication
_app = QApplication.instance() or QApplication([])

from src.core.app_state import get_state
from src.core.engine.function_manager import get_function_manager
from src.core.engine.bpm_manager import get_bpm_manager
from src.core.engine.tempo_bus import get_tempo_bus_manager
from src.core.show.show_file import load_show

SHOW = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "shows", "Hardstyle_Show.lshow")
ok, msg = load_show(SHOW)
print("Load:", ok, msg)
state = get_state(); fm = get_function_manager()
u = state.universes.get(1) or state.output_manager.add_universe(1)
state.universes[1] = u
print("Funktionen:", [(f.id, f.name) for f in sorted(fm.all(), key=lambda x: x.id)])

# BPM global auf 150 -> Tempo-Bus 'hardstyle' (source bpm_global) laeuft.
get_bpm_manager().request_bpm(150.0, "diag")
print("BPM global:", get_bpm_manager().bpm)

def render_beats(beats, steps_per_beat=20):
    dt = (60.0 / 150.0) / steps_per_beat
    for _ in range(int(beats * steps_per_beat)):
        state._render_frame(dt)

def par1_rgb():
    return (u.get_channel(2), u.get_channel(3), u.get_channel(4))  # PAR1 R,G,B

# ── 1) Beat-Blink RRRW ───────────────────────────────────────────────────────
fm.stop_all()
blink = next(f for f in fm.all() if f.name == "Beat-Blink RRRW")
fm.start(blink.id)
render_beats(0.5)  # einschwingen bis Mitte Beat 0
bus = get_tempo_bus_manager().get("hardstyle")
print("\n-- Beat-Blink RRRW (Farbe je Beat, PAR1 RGB) --   Bus-BPM:", round(bus.bpm,1) if bus else None)
seen = []
for beat in range(8):
    rgb = par1_rgb(); seen.append(rgb)
    is_red = rgb[0] > 150 and rgb[1] < 80 and rgb[2] < 80
    is_white = rgb[0] > 150 and rgb[1] > 150 and rgb[2] > 150
    tag = "ROT" if is_red else ("WEISS" if is_white else "??")
    print(f"  Beat {beat}: RGB={rgb}  -> {tag}")
    render_beats(1.0)
fm.stop_all()

# ── 2) Spider Bar-Farben (L-Rot R-Blau) ──────────────────────────────────────
sp = next(f for f in fm.all() if f.name == "Spider L-Rot R-Blau")
fm.start(sp.id); render_beats(0.3)
# fid11 addr87: BarL R=rel6->abs92, BarR R=rel10->abs96, BarR B=rel12->abs98
print("\n-- Spider L-Rot R-Blau (fid11 @87) --")
print(f"  Bar L  R(ch92)={u.get_channel(92)}  G(93)={u.get_channel(93)}  B(94)={u.get_channel(94)}")
print(f"  Bar R  R(ch96)={u.get_channel(96)}  G(97)={u.get_channel(97)}  B(98)={u.get_channel(98)}")
print(f"  Dimmer(ch90)={u.get_channel(90)}  Shutter(ch91)={u.get_channel(91)}")
fm.stop_all()

# ── 3) Gobo-Szene (Ring) ─────────────────────────────────────────────────────
go = next(f for f in fm.all() if f.name == "Gobo Ring")
fm.start(go.id); render_beats(0.3)
# MH fid9 addr65: gobo rel6->abs70, intensity rel8->abs72
print("\n-- Gobo Ring (MH fid9 @65) --")
print(f"  gobo_wheel(ch70)={u.get_channel(70)}  intensity(ch72)={u.get_channel(72)}")
fm.stop_all()
print("\nFERTIG")
