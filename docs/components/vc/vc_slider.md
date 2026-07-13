# vc_slider (VCSlider)

> Vertikaler Fader der Virtuellen Konsole: regelt je nach Modus einen DMX-Kanal,
> einen Executor, einen Sub-/Grandmaster, ein Programmer-Attribut, das globale
> Tempo/einen Tempo-Bus oder Intensität/Speed/Parameter eines Effekts.

## Zweck

`VCSlider` ist das Universal-Regelelement der VC. Der Fader-Hub 0..255 wird über
`SliderMode` auf ein Ziel abgebildet und optional per `range_min`/`range_max`
sowie `invert` auf ein Teilband begrenzt. Er reagiert auf Maus-Drag und einen
absoluten MIDI-CC (mit optionalem Soft-Takeover/„Pickup" für nicht-motorisierte
Controller). Erbt von `VCWidget` (Geometrie, MIDI-Teach-Rahmen, Solo).

## Bedienung / Optionen

### Modi (`SliderMode`)

Der Modus wird im Editor über deutsche Labels (`SLIDER_MODE_LABELS`) gewählt.

| Modus (Enum) | Label | Wirkung | Trägt Bindung |
|---|---|---|---|
| `LEVEL` | DMX-Kanal (Level) | Setzt einen rohen DMX-Kanal | `dmx_channel`, `dmx_universe` |
| `PLAYBACK` | Playback (Executor) | Fadet den Executor in `playback_slot` | `playback_slot` |
| `SUBMASTER` | Submaster | Eigener Submaster-Slot (`id(self)`) im OutputManager | — |
| `GRANDMASTER` | Grand Master | Globale Gesamthelligkeit | — |
| `PROGRAMMER` | Programmer-Attribut | Setzt `programmer_attr` mit Scope all/selected/group | `programmer_attr`, `programmer_scope`, `programmer_group`, `programmer_min/max` |
| `BPM` | Tempo (BPM) | Globales Tempo (Beat-Effekte folgen) | — |
| `SPEED` | Speed (alle Effekte) | Geschwindigkeit ALLER laufenden Effekte | — |
| `EFFECT_INTENSITY` | Effekt-Helligkeit | Helligkeits-Master eines/mehrerer Effekte | `function_id`/`function_ids`/`edit_slot` |
| `EFFECT_SPEED` | Effekt-Tempo | Tempo-Master eines/mehrerer Effekte | `function_id`/`function_ids`/`edit_slot` |
| `EFFECT_PARAM` | Effekt-Parameter | Bildet 0..255 auf die ParamSpec von `param_key` ab | `param_key` (+ `param_keys_per_id`) |
| `GROUP_DIMMER` | Gruppen-Dimmer | Multiplikativer Dimmer einer Fixture-Gruppe | `programmer_group` |
| `FEATURE_DIMMER` | Feature-Dimmer (Gruppe) | Dimmt eine Feature-Gruppe (`feature_attr`) effekt-unabhängig | `feature_attr` |
| `TEMPO_BUS` | Tempo-Bus (BPM) | BPM eines benannten Tempo-Bus (A/B/C/D) | `tempo_bus_id` |

### Weitere Felder

- **Wert-Leitplanken:** `range_min`/`range_max` (Teilband, vertauschte Grenzen
  werden toleriert) und `invert` (Richtung drehen).
- **Effekt-Autostart** (`effect_autostart`, nur `EFFECT_*`): `True` = Wert > 0
  startet den/die Ziel-Effekte, Wert == 0 stoppt sie wirklich.
- **Multi-Effekt (Phase E):** `function_ids` regeln mehrere Effekte gemeinsam;
  `param_keys_per_id` gibt je Effekt einen eigenen Parameter im `EFFECT_PARAM`-Modus.
- **MIDI:** `midi_cc`/`midi_ch` (0 = alle Kanäle); Soft-Takeover global über
  `soft_takeover` (Toolbar) mit Laufzeitzustand `_pickup_armed`/`_last_cc`.

## Verknüpfungen

- **AppState / Engine:** `get_state()` für Programmer, `output_manager`
  (Submaster/Grandmaster), `playback_engine.executors`, `feature_dimmers`.
- **Effekt-Live:** `src/core/engine/effect_live` für `EFFECT_*`-Modi
  (Intensität/Speed/Parameter, `edit_slot` als Live-Bearbeitungsziel).
- **Tempo/BPM:** `bpm_manager` (BPM-Modus) und `tempo_bus` (TEMPO_BUS-Modus).
- **Slot-Aufräumen:** beim Löschen/Moduswechsel räumen `_clear_submaster_slot`
  und `_clear_feature_dimmer_slot` den zugehörigen Slot (kein Geister-Dimmer).
- **Serialisierung:** `to_dict()`/`apply_dict()` schreiben/lesen alle Felder.
  `apply_dict` validiert den Modus gegen `_VALID_SLIDER_MODES` (Fallback `LEVEL`),
  migriert Alt-`PLAYBACK`-Slots aus `function_id`, klemmt den Wert defensiv und
  setzt persistente Modi (Group-/Feature-Dimmer, Submaster) beim Laden aktiv.

## Zugehörige Tests

- `tests/test_vc_slider_group_scope.py` — Programmer-Scope all/selected/group.
- `tests/test_vc_slider_playback_slot.py` — dediziertes `playback_slot` + Migration.
- `tests/test_vc_slider_range_invert.py` — Range-/Invert-Leitplanken.
- `tests/test_vc_slider_soft_takeover.py` — Pickup/Soft-Takeover-Logik.
- `tests/test_vcslider_mode_sync_chain.py` — Moduswechsel/Sync-Kette.
- `tests/test_slider_sync.py` — Wert-Synchronisierung.

Headless ausführen:

```
QT_QPA_PLATFORM=offscreen venv/Scripts/python.exe -m pytest tests/test_vc_slider_range_invert.py -q -p no:cacheprovider
```

## Quelle (file:line)

- `src/ui/virtualconsole/vc_slider.py:78` — Klasse `VCSlider`
- `src/ui/virtualconsole/vc_slider.py:31` — `SliderMode` (Modi)
- `src/ui/virtualconsole/vc_slider.py:57` — `SLIDER_MODE_LABELS` (UI-Labels)
- `src/ui/virtualconsole/vc_slider.py:207` — `_apply` (Modus-Dispatch)
- `src/ui/virtualconsole/vc_slider.py:501` — `handle_midi` (CC + Soft-Takeover)
- `src/ui/virtualconsole/vc_slider.py:1072` — `to_dict` · `:1100` — `apply_dict`
