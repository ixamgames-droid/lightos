# Komponenten-Doku: Input / Remote (DOC-07)

Referenz-Dokumentation der **Eingabe-/Fernsteuer-Module** von LightOS — je Modul
eine Seite. Zweck: schnell verstehen, welche Nachrichten/Adressen ein Modul
annimmt, wie das Mapping/Learn funktioniert und an welchen VC-/Engine-Teilen es
hängt, ohne erst den Code durchzulesen.

## Einheitliches Schema je Seite

Jede Modul-Seite folgt demselben Aufbau:

1. **Zweck** — was das Modul tut, wann es lebt (Singleton/Lifecycle).
2. **Unterstützte Nachrichten / Adressen** — welche MIDI-/OSC-/Tasten-/Timecode-
   Ereignisse verstanden werden.
3. **Mapping- / Learn-Mechanik** — wie eine Eingabe zu einer Aktion wird
   (Bindings, Learn-Modus, Persistenz).
4. **Gekoppelte VC-/Engine-Teile** — welche UI-Views und Engine-Objekte das
   Modul benutzen oder von ihm gefüttert werden.
5. **Tests** — die headless-Tests, die das Modul absichern.
6. **Quelle (`file:line`)** — Einstiegspunkte im Code.

## Module

| Seite | Modul | Kurz |
|-------|-------|------|
| [midi_manager.md](midi_manager.md) | `src/core/midi/midi_manager.py` | MIDI-Geräte auflisten/öffnen, RX-Dispatch, senden, virtuelle Ports |
| [midi_mapper.md](midi_mapper.md) | `src/core/midi/midi_mapper.py` | MIDI→Aktion-Mapping, Learn-Modus, LED-Feedback |
| [midi_backend_winmm.md](midi_backend_winmm.md) | `src/core/midi/midi_backend_winmm.py` | ctypes-WinMM-Backend (ARM64, kein Compiler) |
| [osc_server.md](osc_server.md) | `src/core/osc/osc_server.py` | OSC-Empfang (TouchOSC/Lemur) + Sender |
| [mtc_reader.md](mtc_reader.md) | `src/core/timecode/mtc_reader.py` | MIDI Time Code (Quarter-Frame + SysEx) |
| [keyboard_hotkeys.md](keyboard_hotkeys.md) | `src/core/input/keyboard_hotkeys.py` | App-weite Tastatur-Hotkeys für die VC |
| [profile.md](profile.md) | `src/core/input/profile.py` | Input-Profile (Mapping-Sammlungen je Gerät) |

## Verwandte Doku

- [../../KEYBOARD_MAPPING.md](../../KEYBOARD_MAPPING.md) — Keyboard-Patch aus Nutzersicht + technische Grenzen.
- [../../OSC_TIMECODE_AUDIT_2026_07_08.md](../../OSC_TIMECODE_AUDIT_2026_07_08.md) — Audit von OSC- und Timecode-Pfad.
- [../../DMX_INPUT_AUDIT_2026_07_08.md](../../DMX_INPUT_AUDIT_2026_07_08.md) — DMX-Input (separater Eingabepfad, nicht in dieser Sammlung).
