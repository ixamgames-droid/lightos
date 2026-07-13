# midi_backend_winmm

`src/core/midi/midi_backend_winmm.py`

## Zweck

MIDI-Backend über die Windows-`winmm.dll` per **ctypes** — braucht keinen
Compiler und läuft auf **ARM64**, wo `python-rtmidi` oft fehlt. Wird vom
[midi_manager.md](midi_manager.md) nur als Fallback benutzt, wenn rtmidi nicht
verfügbar ist (`_USE_WINMM = not RTMIDI_OK and WINMM_OK`). Bietet dieselbe
Schnittstelle wie die rtmidi-Objekte (`close_port()`, `send_message(raw)`).

**Robustheits-Detail:** Beim Import wird `midiInGetNumDevs()` in einem
Worker-Thread **mit 2-s-Timeout** geprobt. Hängt das MIDI-Subsystem (klemmender
USB-MIDI-Treiber), wird `WINMM_OK = False` gesetzt und die App startet trotzdem
ohne MIDI — früher fror die App schon vor dem ersten Fenster ein.

## Unterstützte Nachrichten / Adressen

- **Eingang:** kurze MIDI-Messages (`_MIM_DATA = 0x3C3`). Die gepackten 3 Bytes
  aus `dwParam1` werden zu `[b0, b1, b2]` entpackt und an den `on_raw`-Callback
  des Managers gereicht (der sie dann in `MidiManager._decode` verarbeitet).
  SysEx/lange Nachrichten werden hier nicht behandelt.
- **Ausgang:** `send_message(raw)` packt bis zu 3 Bytes in `midiOutShortMsg`.
- **Geräte:** `list_inputs()` / `list_outputs()` über
  `midiInGetDevCapsW` / `midiOutGetDevCapsW` (Portname aus `szPname`).

## Mapping- / Learn-Mechanik

Keine — reine Transport-/Treiberschicht ohne Mapping oder Learn. Der
`_MidiInProc`-Callback (stdcall via `WINFUNCTYPE`) muss als ctypes-Objekt am
`WinMMInput` gehalten werden, sonst wird er vom GC eingezogen. Virtuelle Ports
kann WinMM **nicht** — der Manager verweist dafür auf loopMIDI.

## Gekoppelte VC-/Engine-Teile

- **[midi_manager.md](midi_manager.md)** — einziger regulärer Verbraucher; wählt
  das Backend und ruft `WinMMInput`/`WinMMOutput`/`list_*`.
- **`src/core/midi/apc_mini_feedback.py`**, **`apc_mk2_feedback.py`** — greifen für
  reines LED-Feedback direkt auf `WINMM_OK` + `WinMMOutput` zu.

## Tests

Kein eigener Unit-Test (plattform-/hardwarespezifische ctypes-DLL-Bindung;
`WINMM_OK` ist außerhalb von Windows mit angeschlossenem MIDI ohnehin `False`).
Indirekt über die `midi_manager`-Tests abgedeckt, die den Manager mit rtmidi bzw.
Fake-Backend fahren (`tests/test_midi_mapper.py`, `tests/conftest.py`).

## Quelle (`file:line`)

- Import-Probe mit Timeout (`WINMM_OK`) — `src/core/midi/midi_backend_winmm.py:22`
- `list_inputs()` / `list_outputs()` — `src/core/midi/midi_backend_winmm.py:93`
- `WinMMInput` (+ GC-sicherer Callback) — `src/core/midi/midi_backend_winmm.py:119`
- `WinMMOutput.send_message()` — `src/core/midi/midi_backend_winmm.py:162`
