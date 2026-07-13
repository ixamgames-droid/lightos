# vc_encoder (VCEncoder)

> Dreh-Encoder der Virtuellen Konsole: verstellt einen numerischen Effekt-Parameter
> *relativ* (Drag/Rad/relativer MIDI-CC) und zeigt stets den aktuellen Wert als Bogen.

## Zweck

Im Gegensatz zum absoluten `vc_slider` steuert `VCEncoder` einen Parameter ohne
Sprung: Drag nach oben/unten, Mausrad oder ein relativer MIDI-Encoder erhöhen/senken
den Wert um `step`-Anteile des Wertebereichs. Er nutzt denselben Dispatcher wie alle
Live-Bedienelemente (`effect_live.adjust_param` relativ, `set_param_normalized`
absolut) und rendert Wert + 270°-Bogen. Geeignet für numerische Parameter wie speed,
level, count, rate, density, spread. Erbt von `VCWidget`.

## Bedienung / Optionen

| Feld | Wirkung | Default |
|---|---|---|
| `param_key` | Gesteuerter Effekt-Parameter | `speed` |
| `function_id` / `edit_slot` | Ziel-Effekt (leer = aktiver Effekt / Slot-Ziel) | `None` / `""` |
| `function_ids` | Weitere gekoppelte Effekte (Phase E) | `[]` |
| `param_keys_per_id` | Je gekoppeltem Effekt ein eigener Parameter | `{}` |
| `step` | Schrittweite je Detent/Rad-Schritt (Anteil 0..1) | 0.05 |
| `midi_mode` | `RELATIVE` (Hardware-Encoder) oder `ABSOLUTE` (Poti 0..127) | `RELATIVE` |
| `midi_cc` / `midi_ch` | MIDI-CC-Bindung (ch 0 = alle) | -1 / 0 |

Bedienung: Drag ≈ 3px pro Schritt, Mausrad ein Schritt pro 120er-Delta. Relativer
MIDI-CC nutzt Zweierkomplement um 64 (1..63 = +, 65..127 = −). Der Run-Input-Lock
blockt auch das Mausrad.

## Verknüpfungen

- **Effekt-Live:** `src/core/engine/effect_live` (`adjust_param`,
  `set_param_normalized`, `get_param`, `list_params`, `get_edit_target`).
- **Effekt-Meta:** `vc_effect_meta.mappable_param_choices`/`effect_name`
  (Je-Effekt-Parameter-Combos im Editor).
- **VCWidget-Contract:** MIDI-Teach (`supports_midi_teach`, `apply_midi_binding`).
- **Serialisierung:** `to_dict()`/`apply_dict()` schreiben/lesen alle Felder;
  `apply_dict` validiert `midi_mode` gegen die bekannten Modi (Fallback `RELATIVE`).

## Zugehörige Tests

- `tests/test_vc_encoder.py` — relative/absolute Verstellung, Bindung, Serialisierung.
- `tests/test_vc_naming_and_encoder.py` — Benennung/Encoder-Verhalten.

Headless ausführen:

```
QT_QPA_PLATFORM=offscreen venv/Scripts/python.exe -m pytest tests/test_vc_encoder.py -q -p no:cacheprovider
```

## Quelle (file:line)

- `src/ui/virtualconsole/vc_encoder.py:29` — Klasse `VCEncoder`
- `src/ui/virtualconsole/vc_encoder.py:24` — `EncoderMidiMode`
- `src/ui/virtualconsole/vc_encoder.py:133` — `nudge` (relativ, alle Ziele)
- `src/ui/virtualconsole/vc_encoder.py:159` — `handle_midi`
- `src/ui/virtualconsole/vc_encoder.py:436` — `to_dict` · `:449` — `apply_dict`
