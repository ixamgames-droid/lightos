# vc_button (VCButton)

> Platzierbarer Pad-/Taster der Virtuellen Konsole: löst je nach eingestellter
> Aktion eine Funktion, einen Snap, eine Tempo-/Laser-/Media-Aktion oder eine
> globale Show-Aktion aus — per Maus, MIDI-Pad oder Tastatur-Hotkey.

## Zweck

`VCButton` ist das Universal-Bedienelement der VC. Ein Button trägt **eine
Primär-Aktion** (`ButtonAction`) und optional eine Kette von **Zusatz-Aktionen**
(BTN-01). Er kann an Funktionen/Effekte, Bibliothek-Snaps, Snapshots, Tempo-Buses,
Laser-Output oder den Media-Player gebunden werden und reagiert einheitlich auf
physischen Druck, MIDI-Note/CC und Hotkey. Neu angelegte Buttons sind quadratische
Pads (`DEFAULT_BUTTON_SIZE = 72`, grid-aligned) im APC-Look.

Erbt von `VCWidget` (Basisklasse: Geometrie, MIDI-/Key-Teach-Rahmen, Solo, Farb-
Kachel-Look) und zeigt zusätzlich ein animiertes **Farb-Vorschau-Badge** (oben
rechts) sowie ggf. ein **Gobo-Icon**, wenn die gebundene Funktion/der Snap Farbe
bzw. ein Gobo setzt.

## Bedienung / Optionen

### Aktions-Kinds (`ButtonAction`)

Die Aktion wird im Button-Editor über deutsche Labels
(`BUTTON_ACTION_LABELS`) gewählt; der gespeicherte Wert ist der Enum-`value`.

| Aktion (Enum) | Label | Wirkung | Trägt Bindung |
|---|---|---|---|
| `FUNCTION_TOGGLE` | Funktion an/aus | Startet/stoppt die gebundene Funktion(sgruppe) | `function_id` (+ `function_ids`) |
| `FUNCTION_FLASH` | Funktion (nur gehalten) | Startet bei Druck, stoppt bei Loslassen | `function_id` (+ `function_ids`) |
| `EFFECT_ACTION` | Effekt-Aktion (Live) | Ruft `effect_live.do_action(effect_action_key, fid)` auf | `function_id` / `edit_slot`, `effect_action_key` |
| `SELECT_GROUP` | Gruppe auswählen | `state.select_group_by_name(group_name)` in den Programmer | `group_name` |
| `LIBRARY_SNAP` | Bibliothek-Farbe/Snap | Schreibt Snap-Werte in den Programmer; `snap_mode` steuert Halten/Bleiben/Toggle | `snap_id` (+ `snap_ids`), `snap_mode` |
| `SNAPSHOT` | Snapshot abrufen | Lädt Snapshot `snapshot_index` aus `snapshots.json` | `snapshot_index` |
| `CLEAR` | Programmer leeren | `state.clear_programmer()` | — |
| `STOP_ALL` | Alles stoppen | `playback_engine.stop_all()` | — |
| `STOP_EFFECTS` | Effekte stoppen (Tempo bleibt) | `function_manager.stop_all()` | — |
| `BLACKOUT` | Blackout | `output_manager.set_blackout(press)` (gehalten) | — |
| `TOGGLE` / `FLASH` | Executor: Go / Flash | Wirkt auf `playback_engine.executors[function_id]` | `function_id` = Executor-Slot |
| `ALL_WHITE` | Alles Weiß (gehalten) | Flasht die gebundene Weiß-Szene(n) | `function_id`(s) |
| `FREEZE` | Freeze (BPM einfrieren) | `tempo_bus.toggle_freeze()` | — |
| `AUTO_SYNC` | Auto-Sync an/aus | `tempo_bus.set_auto_sync(...)` | — |
| `TAP` | Tap-Tempo | `bpm_manager.tap()` (globaler Leader) | — |
| `AUDIO_BPM` | Musik-BPM | `bpm_manager.use_audio_source(...)` | — |
| `BPM_NUDGE_UP` / `BPM_NUDGE_DOWN` | BPM ±1 | `bpm_manager.nudge(±1.0)` → MANUAL | — |
| `BPM_MODE_TOGGLE` | BPM-Modus AUTO/MANUAL | `bpm_manager.set_mode(...)` | — |
| `TAP_BUS` / `SYNC_BUS` / `ARM_BUS` | Tempo-Bus tap/sync/arm | Wirkt auf benannten Bus `tempo_bus_id` | `tempo_bus_id` |
| `MEDIA_PLAY_PAUSE` / `MEDIA_NEXT` / `MEDIA_PREV` | Musik-Player | `media_player.toggle/next/prev()` | — |
| `LASER_ARM` | Laser scharf/unscharf | `LaserOutputManager.set_armed(...)` (Safety-Toggle) | — |
| `LASER_ESTOP` | Laser NOT-AUS | `estop_all()` + entwaffnen | — |
| `LASER_PATTERN` | Laser-Muster abrufen | Wendet `PaletteType.LASER`-Palette auf ihre Fixtures an | `laser_palette` |

### Start-Modifikatoren (nur `FUNCTION_TOGGLE`/`FLASH`)

| Option | Wirkung | Default |
|---|---|---|
| `exclusive` | Stoppt beim Start alle anderen Funktionen (nur 1 aktiv) | `False` |
| `solo_fixtures` | Stoppt nur Effekte auf denselben Fixtures (chirurgisch) | `False` |
| `clear_programmer` | Leert vor dem Start den Programmer | `False` |
| `edit_slot` | Macht den gestarteten Effekt zum Live-Edit-Ziel dieses Slots | `""` |
| `long_press_editor` | Long-Press (~500 ms) öffnet den Effekt-Mini-Editor | `False` |

### Weitere Felder

- **Multi-Funktion / Multi-Snap:** `function_ids` / `snap_ids` koppeln zusätzliche
  Ziele; das Primärziel (`function_id`/`snap_id`) bleibt zuerst, Duplikate werden
  raus­gefiltert.
- **Zusatz-Aktionen (`actions`):** Liste von Dicts, die bei Druck **nach** der
  Primär-Aktion laufen (`type`, optional `delay`), Typen u. a. `function`,
  `effect_action`, `snapshot`, `library_snap`, `blackout`, `stop_all`, `clear`,
  `clear_non_vc`, `tap`.
- **Bindungen:** `midi_ch`/`midi_data1`/`midi_type` (Note/CC, `midi_ch=0` = alle
  Kanäle), `key_binding` (z. B. `"Ctrl+F5"`). CC ≥ 64 gilt als Druck.
- **Pad-Anzeige:** `pad_style` (`mirror`/`solid`/`pulse`/`alternate`/`wave`),
  `pad_color2`.

## Verknüpfungen

- **AppState / Engine:** greift über `get_state()` auf `function_manager`,
  `playback_engine`, `output_manager`, `select_group_by_name`, Programmer-Werte zu.
- **Effekt-Live:** `src/core/engine/effect_live` für `EFFECT_ACTION`, `edit_slot`
  (Live-Bearbeitungsziel), Farb-Sequenz des Badges.
- **Snap-Bibliothek:** `src/core/engine/snap_library.get_snap_library()` für
  `LIBRARY_SNAP`; `_snap_prev` merkt vorherige Programmer-Werte für Restore.
- **Tempo/BPM:** `src/core/engine/bpm_manager` und `tempo_bus` (Freeze/AutoSync/Bus).
- **Laser:** `state.ensure_laser_output()` (LaserOutputManager) + `palette`.
- **Solo-Frame:** `vc_frame.VCFrame` ruft `deactivate_for_solo()`, wenn im selben
  Solo-Container ein anderer Button gedrückt wird.
- **Serialisierung:** `to_dict()`/`apply_dict()` schreiben/lesen **alle** obigen
  Felder in die `.lshow`-Datei. `apply_dict` castet IDs defensiv auf `int`
  (float-Schutz gegen `executors[float]`-Crash), fällt bei unbekannter Aktion auf
  `TOGGLE` zurück (Vorwärts-Kompat) und setzt Snap-Laufzeitzustand
  (`_snap_active`/`_snap_prev`) zurück. Beim Wechsel **weg** von `LIBRARY_SNAP`
  wird `snap_id` über `_snap_binding_for_action` verworfen (kein Phantom-Snap).

## Zugehörige Tests

- `tests/test_vc_button_fields.py` — Feld-/Serialisierungs-Rundlauf (`to_dict`/`apply_dict`).
- `tests/test_vc_button_color_badge.py` — Farb-Vorschau-Badge (Auflösung, Cache, Cycle).
- `tests/test_vc_button_running_feedback.py` — Lauf-/Aktiv-Zustandsanzeige.

Headless ausführen:

```
QT_QPA_PLATFORM=offscreen venv/Scripts/python.exe -m pytest tests/test_vc_button_fields.py -q -p no:cacheprovider
```

## Quelle (file:line)

- `src/ui/virtualconsole/vc_button.py:124` — Klasse `VCButton`
- `src/ui/virtualconsole/vc_button.py:24` — `ButtonAction` (Aktions-Kinds)
- `src/ui/virtualconsole/vc_button.py:72` — `BUTTON_ACTION_LABELS` (UI-Reihenfolge/Labels)
- `src/ui/virtualconsole/vc_button.py:833` — `_trigger_primary` (Aktions-Dispatch)
- `src/ui/virtualconsole/vc_button.py:284` — `_start_function_group` (exclusive/solo/edit_slot)
- `src/ui/virtualconsole/vc_button.py:1970` — `to_dict` · `:2008` — `apply_dict`
