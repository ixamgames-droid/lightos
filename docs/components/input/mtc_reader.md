# mtc_reader

`src/core/timecode/mtc_reader.py`

## Zweck

Liest **MIDI Time Code** von einem MIDI-Eingang und gibt die laufende Zeit als
`(h, m, s, f)` an Subscriber. App-weites **Singleton** über `get_mtc_reader()`;
angebunden und angezeigt in der MTC-Box der `src/ui/views/midi_view.py`.

Braucht `rtmidi` (`RTMIDI_OK`); fehlt es, bleibt der Reader ein No-op
(`attach_midi_input` liefert `False`, `subscribe` feuert nie). Anders als der
[midi_manager.md](midi_manager.md) öffnet der Reader seinen **eigenen**
rtmidi-Input, weil er SysEx/Timing nicht ignorieren darf.

## Unterstützte Nachrichten / Adressen

Zwei MTC-Transportformen:

1. **Quarter-Frame** (`0xF1`): 8 Pakete ergeben ein volles Frame → effektive
   Update-Rate ist halb so schnell wie die fps. Jedes Byte trägt oben 3 Bit
   Piece-Typ, unten 4 Bit Nibble-Wert.
2. **Full-Frame SysEx** (`F0 7F cc 01 01 hh mm ss ff F7`): setzt die Zeit direkt.

FPS-Codes: `0=24`, `1=25`, `2=29.97 (drop)`, `3=30` (`FPS_MAP`). Beim Attach
werden Timing/SysEx **nicht** ignoriert (`ignore_types(sysex=False,
timing=False, active_sense=True)`).

## Mapping- / Learn-Mechanik

Kein Mapping/Learn — der Reader dekodiert nur und feuert `cb(h, m, s, f)`.

**MTC-02-Robustheit (Quarter-Frame):** Eine Bitmaske `_qf_seen` merkt, welche der
8 Pieces seit dem letzten Feuern kamen. Es wird **nur** gefeuert, wenn beim
letzten Piece (7) alle Bits gesetzt sind (`_qf_seen == 0xFF`). So entsteht bei
Mid-Stream-Attach oder verlorenem Piece kein Frame aus gemischten alten+neuen
Nibbles; das unvollständige Fenster wird verworfen. Der gemeldete Frame wird um
+2 korrigiert (die 8 Quarter-Frames dauern 2 Frames).

## Gekoppelte VC-/Engine-Teile

- **`src/ui/views/midi_view.py`** — `_build_mtc_box`/`_on_mtc`: Port-Auswahl,
  Verbinden, Zeit-/fps-Label; der Reader-Callback wird thread-sicher per Signal
  in den UI-Thread marshallt.
- Eigenständig vom [midi_manager.md](midi_manager.md) (separater rtmidi-Input),
  daher keine Kopplung an dessen Dispatch.

## Tests

- `tests/test_osc_mtc_robustness.py` — Quarter-Frame-Zusammenbau, MTC-02
  (kein Feuern bei unvollständigem Satz), SysEx-Full-Frame, fps-Codes.

Siehe auch [../../OSC_TIMECODE_AUDIT_2026_07_08.md](../../OSC_TIMECODE_AUDIT_2026_07_08.md).

## Quelle (`file:line`)

- `FPS_MAP` — `src/core/timecode/mtc_reader.py:22`
- `MTCReader` (+ `_qf_seen`) — `src/core/timecode/mtc_reader.py:25`
- `attach_midi_input()` — `src/core/timecode/mtc_reader.py:61`
- `_handle_quarter_frame()` (MTC-02) — `src/core/timecode/mtc_reader.py:116`
- `_handle_sysex()` (Full-Frame) — `src/core/timecode/mtc_reader.py:149`
- `subscribe()` / `time()` / `fps()` — `src/core/timecode/mtc_reader.py:173`
- Singleton `get_mtc_reader()` — `src/core/timecode/mtc_reader.py:194`
