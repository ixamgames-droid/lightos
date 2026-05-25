"""Setup: ZQ01424 4-in-1 PAR-Profil + 4 Patches + APC mini Standard-Belegung."""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
app = QApplication(sys.argv)

from sqlalchemy import select, delete
from sqlalchemy.orm import Session
from src.core.database.fixture_db import engine as fdb_engine, _add_fixture
from src.core.database.models import Manufacturer, FixtureProfile, FixtureMode, FixtureChannel, PatchedFixture
from src.core.app_state import get_state

state = get_state()

# ── 1. ZQ01424 Profil anlegen falls noch nicht da ─────────────────────────────
print("=== Fixture-Profil ZQ01424 ===")
with Session(fdb_engine()) as s:
    profile = s.execute(
        select(FixtureProfile).where(FixtureProfile.name == "ZQ01424 4in1 PAR")
    ).scalar_one_or_none()

    if profile:
        print(f"  Profil existiert bereits (id={profile.id})")
        profile_id = profile.id
    else:
        # Hersteller "Generic" suchen
        generic = s.execute(
            select(Manufacturer).where(Manufacturer.name == "Generic")
        ).scalar_one_or_none()
        if not generic:
            generic = Manufacturer(name="Generic", short_name="GEN")
            s.add(generic)
            s.flush()

        _add_fixture(s, generic, "ZQ01424 4in1 PAR", "ZQ01424", "par", 36, [
            ("4-Kanal RGBW", [
                ("Rot",   "color_r",  0, 255),
                ("Gruen", "color_g",  0, 255),
                ("Blau",  "color_b",  0, 255),
                ("Weiss", "color_w",  0, 255),
            ]),
            ("6-Kanal D+RGBW+Strobe", [
                ("Dimmer", "intensity", 0, 255),
                ("Rot",    "color_r",   0, 255),
                ("Gruen",  "color_g",   0, 255),
                ("Blau",   "color_b",   0, 255),
                ("Weiss",  "color_w",   0, 255),
                ("Strobe", "shutter",   0,   0),
            ]),
            ("8-Kanal Full", [
                ("Dimmer", "intensity", 0, 255),
                ("Rot",    "color_r",   0, 255),
                ("Gruen",  "color_g",   0, 255),
                ("Blau",   "color_b",   0, 255),
                ("Weiss",  "color_w",   0, 255),
                ("Strobe", "shutter",   0,   0),
                ("Makro",  "macro",     0,   0),
                ("Speed",  "speed",     0,   0),
            ]),
        ])
        s.commit()
        # ID nach Commit holen
        profile = s.execute(
            select(FixtureProfile).where(FixtureProfile.name == "ZQ01424 4in1 PAR")
        ).scalar_one()
        profile_id = profile.id
        print(f"  Profil neu angelegt (id={profile_id}) mit 3 Modes")

# ── 2. 4x ZQ01424 patchen ─────────────────────────────────────────────────────
print()
print("=== Patch 4x ZQ01424 (6-Kanal D+RGBW+Strobe) ===")

# Existierende ZQ01424-Patches loeschen damit wir sauber starten
state._reload_patch_cache()
existing = [f for f in state.get_patched_fixtures()
            if f.fixture_profile_id == profile_id]
for f in existing:
    print(f"  Loesche existierendes ZQ01424 fid={f.fid}")
    state.remove_fixture(f.fid)

# Adressen: CQ6136 ist auf 1-4 -> ZQ ab Adresse 5 mit je 6 Kanaelen
# ZQ#1 5-10, #2 11-16, #3 17-22, #4 23-28
next_fid = state.next_fid()
start_addr = 5
mode_name = "6-Kanal D+RGBW+Strobe"
ch_count = 6

for i in range(4):
    addr = start_addr + i * ch_count
    fid = next_fid + i
    pf = PatchedFixture(
        fid=fid,
        label=f"ZQ01424 #{i+1}",
        fixture_profile_id=profile_id,
        mode_name=mode_name,
        universe=1,
        address=addr,
        channel_count=ch_count,
    )
    state.add_fixture(pf)
    print(f"  ZQ01424 #{i+1} -> fid={fid} Universe 1 Adr {addr}-{addr+ch_count-1}")

# ── 3. APC mini MIDI-Standard-Belegung ─────────────────────────────────────────
print()
print("=== APC mini MIDI-Belegung ===")

# APC mini Layout (Standard MIDI Channel 1 = MIDI channel 0):
#   8x8 Grid Pads: notes 0..63 (note 0 = bottom-left)
#   Round buttons unter Grid (Track-Buttons):  notes 64..71
#   Side buttons rechts (Scene-Launch):         notes 82..89
#   Master Round Button (oben links): note 98
#   9 Faders: CC 48..56 (Master = CC 56)

from src.core.midi.midi_mapper import MidiMapping
import src.core.midi.midi_mapper as mm

# Action constants holen
ACTION_EXECUTOR_GO     = getattr(mm, "ACTION_EXECUTOR_GO", "executor_go")
ACTION_EXECUTOR_BACK   = getattr(mm, "ACTION_EXECUTOR_BACK", "executor_back")
ACTION_EXECUTOR_FLASH  = getattr(mm, "ACTION_EXECUTOR_FLASH", "executor_flash")
ACTION_EXECUTOR_FADER  = getattr(mm, "ACTION_EXECUTOR_FADER", "executor_fader")
ACTION_GRAND_MASTER    = getattr(mm, "ACTION_GRAND_MASTER", "grand_master")

# MidiMapper holen / erstellen
if not hasattr(state, "midi_mapper"):
    state.midi_mapper = mm.MidiMapper(state)
mapper = state.midi_mapper

# Bestehende APC mini Mappings entfernen (port_filter = APC)
mapper._mappings = [m for m in mapper.get_mappings() if "APC" not in (m.port_filter or "")]

PORT = "APC mini"

mappings = []

# 1. 8 Faders (CC 48-55) -> Executor 1-8 Fader
for i in range(8):
    mappings.append(MidiMapping(
        name=f"APC Fader {i+1}",
        msg_type="cc",
        channel=0,
        data1=48 + i,
        action=ACTION_EXECUTOR_FADER,
        param=str(i+1),
        port_filter=PORT,
    ))

# 2. Master-Fader (CC 56) -> Grand Master
mappings.append(MidiMapping(
    name="APC Master Fader",
    msg_type="cc",
    channel=0,
    data1=56,
    action=ACTION_GRAND_MASTER,
    param="",
    port_filter=PORT,
))

# 3. Grid Bottom-Row (notes 0..7) -> Executor 1-8 GO
for i in range(8):
    mappings.append(MidiMapping(
        name=f"APC Grid Bottom {i+1} GO",
        msg_type="note_on",
        channel=0,
        data1=i,
        action=ACTION_EXECUTOR_GO,
        param=str(i+1),
        port_filter=PORT,
    ))

# 4. Grid Row 2 (notes 8..15) -> Executor 1-8 Flash
for i in range(8):
    mappings.append(MidiMapping(
        name=f"APC Grid Row2 {i+1} Flash",
        msg_type="note_on",
        channel=0,
        data1=8 + i,
        action=ACTION_EXECUTOR_FLASH,
        param=str(i+1),
        port_filter=PORT,
    ))

# 5. Track Buttons (notes 64-71) -> Executor 1-8 BACK
for i in range(8):
    mappings.append(MidiMapping(
        name=f"APC Track Btn {i+1} BACK",
        msg_type="note_on",
        channel=0,
        data1=64 + i,
        action=ACTION_EXECUTOR_BACK,
        param=str(i+1),
        port_filter=PORT,
    ))

# 6. Side-Buttons (Scene-Launch, notes 82-89) -> Page 1-8 wechseln (T0.1)
ACTION_PAGE_SELECT = getattr(mm, "ACTION_PAGE_SELECT", "page_select")
for i in range(8):
    mappings.append(MidiMapping(
        name=f"APC Side Btn {i+1} -> Page {i+1}",
        msg_type="note_on",
        channel=0,
        data1=82 + i,
        action=ACTION_PAGE_SELECT,
        param=str(i+1),
        port_filter=PORT,
    ))

for m in mappings:
    mapper.add_mapping(m)

print(f"  {len(mappings)} Mappings hinzugefuegt (alle nur fuer Port mit 'APC' im Namen)")

# Speichern
mapping_path = os.path.join("data", "midi_mappings.json")
os.makedirs(os.path.dirname(mapping_path), exist_ok=True)
mapper.save(mapping_path)
print(f"  Gespeichert: {mapping_path}")

# ── 4. APC mini Port verbinden ────────────────────────────────────────────────
print()
print("=== APC mini Port-Check ===")
from src.core.midi.midi_manager import get_midi_manager
midi = get_midi_manager()
try:
    ports = midi.list_inputs()
    print(f"  Verfuegbare MIDI-Inputs: {ports}")
    apc_port = next((p for p in ports if "APC" in p), None)
    if apc_port:
        midi.open_input(apc_port)
        print(f"  APC mini Port geoeffnet: {apc_port}")
    else:
        print(f"  APC mini nicht gefunden - bitte in der MIDI-View oeffnen")
except Exception as e:
    print(f"  MIDI-Check Fehler: {e}")

# ── 5. Default Cuelisten/Executors anlegen damit was zum Triggern da ist ──────
print()
print("=== Default Cuelisten fuer Executoren 1-4 ===")
from src.core.engine.cue import Cue

if len(state.cue_stacks) < 4:
    for i in range(4 - len(state.cue_stacks)):
        idx = len(state.cue_stacks) + 1
        stack = state.new_cue_stack(f"Stack {idx}")
        # Eine Default-Cue: alle ZQ auf eine Farbe
        colors = [
            ("Rot",     {"color_r": 255, "color_g": 0,   "color_b": 0,   "color_w": 0,   "intensity": 255}),
            ("Gruen",   {"color_r": 0,   "color_g": 255, "color_b": 0,   "color_w": 0,   "intensity": 255}),
            ("Blau",    {"color_r": 0,   "color_g": 0,   "color_b": 255, "color_w": 0,   "intensity": 255}),
            ("Weiss",   {"color_r": 0,   "color_g": 0,   "color_b": 0,   "color_w": 255, "intensity": 255}),
        ]
        name, vals = colors[(idx - 1) % 4]
        cue_values = {}
        for f in state.get_patched_fixtures():
            if f.fixture_profile_id == profile_id:
                cue_values[f.fid] = vals
        stack.add_cue(Cue(number=1.0, label=name, fade_in=1.5, values=cue_values))

# Executoren binden
if state.playback_engine:
    for i, stack in enumerate(state.cue_stacks[:4]):
        ex = state.playback_engine.get_executor(i + 1)
        ex.stack = stack
        ex.label = stack.name
        print(f"  Executor {i+1} -> {stack.name} ({len(stack.cues)} Cues)")

print()
print("=== FERTIG ===")
print("APC mini Belegung:")
print("  Fader 1-8   -> Executor 1-8 Level")
print("  Fader 9     -> Grand Master")
print("  Pad Reihe 1 (unten) -> Executor 1-8 GO")
print("  Pad Reihe 2          -> Executor 1-8 Flash (halten)")
print("  Track-Buttons (8x)   -> Executor 1-8 BACK")
print()
print("Drueck Pad 1 (unten links) auf der APC um Stack 1 (Rot) zu starten!")
