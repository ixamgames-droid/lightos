"""Start LightOS with CQ6136 pre-patched on Enttec COM4."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
app = QApplication(sys.argv)

from src.core.app_state import get_state
from src.core.database.models import PatchedFixture
from src.core.database.fixture_db import get_fixtures_by_manufacturer, get_all_manufacturers, get_modes

state = get_state()
state.open_show()

# Ensure universe 1 exists
if 1 not in state.universes:
    state.universes[1] = state.output_manager.add_universe(1)

# Connect Enttec on COM4
try:
    state.output_manager.add_enttec(1, "COM4")
    print("Enttec COM4 verbunden -> Universe 1")
except Exception as e:
    print(f"Enttec Fehler: {e}")

# Suche CQ6136 in der Datenbank
from src.core.database.fixture_db import search_fixtures
results = search_fixtures("CQ6136")
profile_id = 1
mode_name = "6-Kanal RGBWAUV"
ch_count = 6

if results:
    fx = results[0]
    profile_id = fx.id
    modes = get_modes(fx.id)
    # Bevorzuge 7-Kanal Mode (RGBWAUV+Strobe — getestet und bestaetigt)
    mode = next((m for m in modes if "7" in m.name), modes[0] if modes else None)
    if mode:
        mode_name = mode.name
        ch_count = mode.channel_count
    print(f"Fixture-Profil: {fx.name} Mode={mode_name} ({ch_count}ch)")
else:
    print("CQ6136 nicht in DB — nutze Generic")

# Check if already patched at address 1
already = any(f.address == 1 and f.universe == 1 for f in state.get_patched_fixtures())
if not already:
    pf = PatchedFixture(
        fid=1,
        label="Stage Light (CQ6136)",
        fixture_profile_id=profile_id,
        mode_name=mode_name,
        universe=1,
        address=1,
        channel_count=ch_count,
    )
    state.add_fixture(pf)
    print(f"Gepacht: Stage Light (CQ6136) @ Adr.1 Universe 1 ({ch_count}ch)")
else:
    print("Fixture bereits gepacht")

# Channel-Modifier laden (Curves pro DMX-Channel)
try:
    from src.core.engine.channel_modifier import get_modifier_manager
    get_modifier_manager().load("data/channel_modifiers.json")
    n = len(get_modifier_manager().all())
    if n:
        print(f"Channel-Modifier geladen: {n}")
except Exception as e:
    print(f"Modifier-Load Fehler: {e}")

# Start playback engine and DMX output
state.start_playback()
state.output_manager.start()
print("DMX-Ausgabe gestartet (44 Hz)")

# ── Auto-Setup: 4 Cuelisten fuer ZQ01424 + APC mini binden ────────────────────
try:
    from src.core.engine.cue import Cue
    zq_fixtures = [f for f in state.get_patched_fixtures()
                    if "ZQ01424" in (f.label or "")]
    if zq_fixtures and len(state.cue_stacks) < 4:
        colors = [
            ("Rot",   {"color_r": 255, "color_g": 0,   "color_b": 0,   "color_w": 0,   "intensity": 255}),
            ("Gruen", {"color_r": 0,   "color_g": 255, "color_b": 0,   "color_w": 0,   "intensity": 255}),
            ("Blau",  {"color_r": 0,   "color_g": 0,   "color_b": 255, "color_w": 0,   "intensity": 255}),
            ("Weiss", {"color_r": 0,   "color_g": 0,   "color_b": 0,   "color_w": 255, "intensity": 255}),
        ]
        for i in range(4 - len(state.cue_stacks)):
            idx = len(state.cue_stacks) + 1
            stack = state.new_cue_stack(f"ZQ Stack {idx}")
            name, vals = colors[(idx - 1) % 4]
            cue_values = {f.fid: vals for f in zq_fixtures}
            stack.add_cue(Cue(number=1.0, label=name, fade_in=1.5, values=cue_values))

        for i, stack in enumerate(state.cue_stacks[:4]):
            ex = state.playback_engine.get_executor(i + 1)
            ex.stack = stack
            ex.label = stack.name
        print(f"Auto-Setup: {len(zq_fixtures)} ZQ01424 in 4 Cuestacks (R/G/B/W) auf Executoren 1-4")
except Exception as e:
    print(f"Auto-Setup Cues Fehler: {e}")

# ── APC mini: Port oeffnen + MIDI-Mappings laden ─────────────────────────────
try:
    from src.core.midi.midi_manager import get_midi_manager
    from src.core.midi.midi_mapper import MidiMapper
    midi = get_midi_manager()
    ports = midi.list_inputs()
    apc = next((p for p in ports if "APC" in p), None)
    if apc:
        midi.open_input(apc)
        print(f"APC mini verbunden: {apc}")
        # Mappings laden + global zuweisen
        if not hasattr(state, "midi_mapper"):
            state.midi_mapper = MidiMapper(state)
        if os.path.exists("data/midi_mappings.json"):
            state.midi_mapper.load("data/midi_mappings.json")
            print(f"MIDI-Mappings geladen: {len(state.midi_mapper.get_mappings())} aktiv")
    else:
        print(f"APC mini nicht gefunden. Verfuegbar: {ports}")
except Exception as e:
    print(f"APC Setup Fehler: {e}")

print()
print("Die Software startet jetzt...")
print("Enttec COM4 -> Universe 1 -> CQ6136 @ Adresse 1 + 4x ZQ01424 @ Adr 5-28")

from src.ui.main_window import MainWindow
win = MainWindow()
win.show()

sys.exit(app.exec())
