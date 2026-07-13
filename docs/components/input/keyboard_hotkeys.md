# keyboard_hotkeys

`src/core/input/keyboard_hotkeys.py`

## Zweck

App-weite **Tastatur-Hotkeys** für die Virtual Console (Feature „Keyboard-Patch").
Ein einziger `QApplication`-Event-Filter fängt KeyPress/KeyRelease, baut daraus
einen portablen Sequenz-String und verteilt ihn an Subscriber (die VC-Canvases) —
gleiche Architektur wie der MIDI-Pfad (`MidiManager → VCCanvas → widget.handle_midi`).
**Singleton** über `get_keyboard_hotkeys()`; installiert sich beim ersten
`subscribe()` selbst als Event-Filter.

## Unterstützte Nachrichten / Adressen

Portable Sequenz-Strings aus `QKeySequence`, z. B. `"F5"`, `"Ctrl+B"`,
`"Shift+Space"` (`sequence_from_event`). Reine Modifier-Tasten (Shift/Ctrl/Alt/
Meta/AltGr/Caps/Num/Scroll-Lock) erzeugen **keine** Sequenz.

Subscriber-Signatur: `cb(seq: str, pressed: bool) -> bool`. Gibt ein Subscriber
`True` zurück, gilt der Hotkey als **konsumiert** und das Key-Event wird nicht
weitergereicht (verhindert z. B. Scrollen per Leertaste).

**Schutzregeln (Live-Betrieb):**
- Kein Auslösen bei Fokus in Texteingabe (`QLineEdit`, `QTextEdit`,
  `QPlainTextEdit`, `QAbstractSpinBox`, editierbare `QComboBox`,
  `QKeySequenceEdit`).
- Kein Auslösen, solange ein modaler Dialog offen ist (Lern-/Sicherheitsdialoge).
- Auto-Repeat wird verschluckt (Halten feuert nicht mehrfach).
- Release wird zuverlässig zugestellt: die beim Press gesendete Sequenz wird pro
  Basis-Taste gemerkt (`_active[key]`) und beim Release wiederverwendet — auch
  wenn der Modifier zuerst losgelassen wurde (wichtig für Flash-Tasten).

## Mapping- / Learn-Mechanik

Das Modul selbst hält **kein** Mapping und keinen Learn-Modus — es liefert nur den
Sequenz-String. Die Zuordnung Taste→Widget passiert in den VC-Canvases
(`_on_hotkey` → an die Widgets der aktiven Bank), das eigentliche Lernen einer
Taste im VC-/Widget-UI. Bewusst **kein** OS-globaler Hook: Hotkeys feuern nur,
solange LightOS den Fokus hat, und Qt liefert **keine** Geräte-Unterscheidung
(eine zweite USB-Tastatur sendet dieselben Events) — beides dokumentiert in
[../../KEYBOARD_MAPPING.md](../../KEYBOARD_MAPPING.md).

## Gekoppelte VC-/Engine-Teile

- **`src/ui/virtualconsole/vc_canvas.py`** — `subscribe(self._on_hotkey)`; verteilt
  die Sequenz an die Widgets der aktiven Bank, analog `_handle_midi`.
- **`QApplication`** — der Filter hängt global (`installEventFilter`) und nutzt
  `activeModalWidget()` / `focusWidget()` für die Schutzregeln.

## Tests

- `tests/test_keyboard_mapping.py` — Sequenz-Bau, Text-Input-/Modal-Guards,
  Auto-Repeat-Unterdrückung, Release-Zustellung, Konsum-Rückgabe.
- `tests/conftest.py` — headless-Setup (QApplication) für den Event-Filter.

## Quelle (`file:line`)

- `_MODIFIER_KEYS` — `src/core/input/keyboard_hotkeys.py:35`
- `_is_text_input()` (Fokus-Guard) — `src/core/input/keyboard_hotkeys.py:42`
- `sequence_from_event()` — `src/core/input/keyboard_hotkeys.py:61`
- `KeyboardHotkeyFilter` — `src/core/input/keyboard_hotkeys.py:71`
- `eventFilter()` (Schutzregeln/Release) — `src/core/input/keyboard_hotkeys.py:109`
- Singleton `get_keyboard_hotkeys()` — `src/core/input/keyboard_hotkeys.py:159`
