# midi_manager

`src/core/midi/midi_manager.py`

## Zweck

Zentrale MIDI-I/O-Schicht: Geräte auflisten, Ein-/Ausgänge öffnen, eingehende
Nachrichten thread-sicher an Subscriber verteilen und Nachrichten (Note/CC)
senden. App-weites **Singleton** über `get_midi_manager()`.

Es gibt zwei Backends mit fester Priorität:

1. **python-rtmidi** (plattformübergreifend, falls installiert).
2. **WinMM via ctypes** (`RTMIDI_OK == False and WINMM_OK == True` → Fallback für
   Windows ARM64 / kein Compiler; siehe [midi_backend_winmm.md](midi_backend_winmm.md)).

`available` ist `True`, sobald mindestens eines der Backends nutzbar ist.

## Unterstützte Nachrichten / Adressen

Rohbytes werden in `_decode()` zu einer `MidiMessage`-Dataclass:

| Feld | Bedeutung |
|------|-----------|
| `port_name` | Quell-Portname (bzw. `Virtual:<name>`) |
| `channel` | 1–16 |
| `msg_type` | `note_on`, `note_off`, `cc`, `pc`, `pitchbend` |
| `data1` | Note / CC-Nummer / PC-Nummer |
| `data2` | Velocity / CC-Wert / 0 |

Status-Nibbles: `0x90` note_on (`data2==0` → note_off), `0x80` note_off, `0xB0`
cc, `0xC0` pc, `0xE0` pitchbend. Unbekannte Statusbytes → `None` (verworfen).

**Senden:** `send_cc(channel, cc, value, virtual=False)`, `send_note(...)`,
`send_note_off(...)` — 7-bit-maskiert.

## Mapping- / Learn-Mechanik

Der Manager macht **kein** Mapping — er ist reine Transport-Schicht. Er hält eine
Callback-Liste (`subscribe`/`unsubscribe`); die eigentliche Zuordnung
Eingabe→Aktion und der Learn-Modus liegen im [midi_mapper.md](midi_mapper.md).

Eingehende Nachrichten laufen über eine `queue.Queue` (max 4096) und einen
Daemon-Thread `MidiDispatch`: Bei Überlast werden Events **gedroppt** statt den
Callback-Thread zu blockieren. Die Callback-Liste wird beim Feuern kopiert, damit
`subscribe`/`unsubscribe` aus dem UI-Thread während der Iteration sicher ist.

`open_all_inputs()` ist idempotent (überspringt offene Ports) und damit
Hot-Plug-tauglich (periodisch aufrufbar). Virtuelle Ports
(`open_virtual_input`/`open_virtual_output`) gibt es nur mit rtmidi; unter WinMM
wird auf loopMIDI verwiesen.

## Gekoppelte VC-/Engine-Teile

- **`src/ui/virtualconsole/vc_canvas.py`** — abonniert den Manager, marshallt die
  Nachricht per Signal in den UI-Thread (`_handle_midi`) und reicht sie an
  `widget.handle_midi(msg)` der aktiven Bank weiter.
- **[midi_mapper.md](midi_mapper.md)** — abonniert für Inbound-Aktionen und nutzt
  `send_cc`/`send_note` + `current_output_name()`/`open_output()` für LED-Feedback.
- **`src/ui/views/midi_view.py`** — Geräte-UI (Listen/Verbinden/Monitor).
- **`src/core/midi/apc_mini_feedback.py`**, **`apc_mk2_feedback.py`** — Controller-
  spezifisches LED-Feedback.
- **`src/ui/main_window.py`** — ruft beim Shutdown `close_all()`.

## Tests

- `tests/test_midi_mapper.py` — Dispatch + Aktionsausführung über den Manager.
- `tests/test_midi_view.py` — Geräte-View gegen den Manager.
- `tests/test_midi_learn_thread_marshal.py`, `tests/test_vc_encoder.py`,
  `tests/conftest.py` (Fake-/Stub-Manager für headless-Läufe).

## Quelle (`file:line`)

- `MidiMessage` — `src/core/midi/midi_manager.py:34`
- `_decode()` (Status→Typ) — `src/core/midi/midi_manager.py:43`
- `MidiManager` + RX-Thread — `src/core/midi/midi_manager.py:65`
- `open_all_inputs()` (Hot-Plug) — `src/core/midi/midi_manager.py:134`
- `send_cc()` / `send_note()` — `src/core/midi/midi_manager.py:262`
- `subscribe()` / `_rx_loop()` — `src/core/midi/midi_manager.py:286`
- Singleton `get_midi_manager()` — `src/core/midi/midi_manager.py:349`
