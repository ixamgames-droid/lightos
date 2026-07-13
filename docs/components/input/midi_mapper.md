# midi_mapper

`src/core/midi/midi_mapper.py`

## Zweck

Bidirektionale Mapping-Engine: übersetzt eingehende MIDI-Nachrichten in
LightOS-Aktionen (Inbound) und spiegelt den Ziel-Zustand als LED-/Controller-
Feedback zurück (Outbound). App-weites **Singleton** über
`get_midi_mapper(app_state)`, in der App gehalten als `app_state.midi_mapper`.

Beim Erzeugen abonniert es den [midi_manager.md](midi_manager.md) und hakt sich
in Zustandsquellen ein (Grand Master). Persistenz nach `data/midi_mappings.json`
(geladen in `AppState`).

## Unterstützte Nachrichten / Adressen

Eingehend: `note_on`/`note_off`/`cc` (Note- und CC-Trigger). Ein
`MidiInBinding.matches(msg)` filtert nach:

| Feld | Regel |
|------|-------|
| `device` | Substring-Match gegen `msg.port_name` (leer = alle) |
| `channel` | exakt, `0` = beliebiger Kanal |
| `trigger_id` | exakt (`msg.data1`: Note-/CC-Nummer) |
| `message_type` | `note` (note_on+note_off) oder `cc` |

Ausgehend (`MidiOutFeedback`): Note oder CC mit `state_off`/`state_on`,
optionalem `brightness`-Cap und `aux_channel`.

**Aktionen** (`target_id`-Form `"<action>[:<param>]"`):
`executor_go` · `executor_back` · `executor_flash` · `executor_fader` ·
`programmer_value` · `grand_master` · `page_select` · `page_next` · `page_prev` ·
`function` (`function:<id>` → Scene/Chaser starten/stoppen) · `effect_param`
(continuous → `effect_live.set_param_normalized`) · `effect_action` (button →
`effect_live.do_action`) · `none`. Der `effect_*`-Param nimmt `"<key>"` (aktiver
Effekt) oder `"<key>@<function_id>"` (fester Effekt).

## Mapping- / Learn-Mechanik

**Button-Modi** (aus der Aktion abgeleitet oder explizit): `continuous`
(Fader/Wert 0..1, skaliert über `continuous_min`/`continuous_max`), `flash`
(Press/Release feuert, z. B. Effekt-Aktion einmal pro Druck) und `toggle`
(Umschalten bei Press). Press/Release wird für Notes über `data2>0` bzw. für CC
über die 64er-Schwelle erkannt.

**Learn-Modus:** `start_learn(callback)` setzt ein Flag; die nächste
note/cc-Nachricht wird direkt an den Callback gereicht (kein Mapping-Durchlauf),
danach ist Learn wieder aus. `MidiMapping.set_from_learn_message(msg)` /
`MidiInBinding.from_message(msg)` bauen das Binding aus der gelernten Nachricht.

**Feedback-Engine:** eigener Daemon-Thread `MidiFeedbackEngine` pollt alle 100 ms
den Ziel-Zustand (`_read_mapping_state`) und sendet bei Änderung Note/CC zurück;
mit Dedupe (gleicher Wert < 50 ms wird verworfen) und Auto-Öffnen des
Feedback-Ausgangs. `subscribe_state()` liefert UI/VC denselben Zustand als
`mapping_state_changed`-Event.

**Persistenz:** `save(path)`/`load(path)` als JSON; modernes Schema
(`from_config_dict`) und Legacy-Flachfelder werden beide gelesen.

## Gekoppelte VC-/Engine-Teile

- **`app_state.playback_engine`** — Executoren (`get_executor(slot)`, `press_btn`,
  `fader_value`), Pages (`set_page`/`current_page`).
- **`app_state.output_manager`** — `set_grand_master`, `subscribe_grand_master`.
- **`app_state.function_manager`** — `start`/`stop`/`is_running` für `function:`.
- **`app_state.set_programmer_value` / `get_patched_fixtures`** — `programmer_value`.
- **`src/core/engine/effect_live.py`** — `effect_param`/`effect_action` teilen sich
  denselben Dispatcher mit der virtuellen Konsole (Phase-6-Kopplung).
- **`src/ui/views/midi_view.py`**, **`src/ui/widgets/midi_teach_dialog.py`**,
  **`src/ui/widgets/input_profile_editor.py`** — Editor/Learn-UI.

## Tests

- `tests/test_midi_mapper.py` — Bindings, Button-Modi, Aktionsausführung, Feedback.
- `tests/test_midi_learn_thread_marshal.py` — Learn-Callback thread-korrekt.
- `tests/test_midi_view.py`, `tests/test_vc_xypad_midi.py`, `tests/test_vc_encoder.py`.

## Quelle (`file:line`)

- Aktions-Konstanten — `src/core/midi/midi_mapper.py:15`
- `MidiInBinding.matches()` — `src/core/midi/midi_mapper.py:87`
- `MidiOutFeedback` — `src/core/midi/midi_mapper.py:129`
- `MidiMapping` (+ Legacy-Sync) — `src/core/midi/midi_mapper.py:172`
- `MidiMapper` (Konstruktor/Threads) — `src/core/midi/midi_mapper.py:263`
- `start_learn()` / `_on_midi()` — `src/core/midi/midi_mapper.py:318`
- `_handle_inbound_mapping()` (Modi) — `src/core/midi/midi_mapper.py:342`
- `_execute_binary()` / `_execute_continuous()` — `src/core/midi/midi_mapper.py:378`
- `_feedback_loop()` — `src/core/midi/midi_mapper.py:511`
- `save()` / `load()` — `src/core/midi/midi_mapper.py:643`
- Singleton `get_midi_mapper()` — `src/core/midi/midi_mapper.py:673`
