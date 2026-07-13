# vc_stepper (VCStepper)

> +/−-Schrittwahl der Virtuellen Konsole: verstellt einen diskreten Effekt-Parameter
> (int/select/bool) absolut über zwei Tasten plus Wertanzeige.

## Zweck

Für diskrete Zähl-Parameter (z. B. `runner_count`, `runner_width`), Auswahlwerte
und boolesche Schalter, wo ein Fader unpräzise ist. Zwei Tasten [−]/[+] plus der
aktuelle Wert; der Wert wird ABSOLUT über den Dispatcher
(`effect_live.set_param`, server-seitig auf den ParamSpec-Bereich geklemmt) gesetzt.
Binde-Plumbing analog zum [`vc_encoder`](vc_encoder.md). Erbt von `VCWidget`.

## Bedienung / Optionen

| Feld | Wirkung | Default |
|---|---|---|
| `param_key` | Diskreter Effekt-Parameter (int/select/bool) | `runner_count` |
| `function_id` / `edit_slot` | Ziel-Effekt (leer = aktiver Effekt / Slot-Ziel) | `None` / `""` |
| `function_ids` | Weitere gekoppelte Effekte (Phase E) | `[]` |
| `param_keys_per_id` | Je gekoppeltem Effekt ein eigener Parameter | `{}` |
| `step` | Schrittweite je Tastendruck (ganzzahlig) | 1 |
| `midi_cc` / `midi_ch` | Relativer MIDI-CC (ch 0 = alle) | -1 / 0 |

Bedienung: linkes Drittel = −, rechtes Drittel = +. `step_by` klemmt je nach
Parameter-Art (`select`: Index im Options-Feld, `bool`: Toggle, `int`: min/max).
Relativer MIDI-CC (1..63 = +, 65..127 = −). Erschöpfte Enden werden ausgegraut.

## Verknüpfungen

- **Effekt-Live:** `src/core/engine/effect_live` (`set_param`, `get_param`,
  `list_params` für die ParamSpec/`kind`, `get_edit_target`).
- **VCWidget-Contract:** MIDI-Teach (`supports_midi_teach`, `apply_midi_binding`).
- **Serialisierung:** `to_dict()`/`apply_dict()` schreiben/lesen alle Felder
  (inkl. `param_keys_per_id` mit String-Keys).

## Zugehörige Tests

- `tests/test_vc_stepper.py` — Schritt-/Klemm-Logik (int/select/bool), MIDI, Serialisierung.

Headless ausführen:

```
QT_QPA_PLATFORM=offscreen venv/Scripts/python.exe -m pytest tests/test_vc_stepper.py -q -p no:cacheprovider
```

## Quelle (file:line)

- `src/ui/virtualconsole/vc_stepper.py:18` — Klasse `VCStepper`
- `src/ui/virtualconsole/vc_stepper.py:93` — `step_by` (absolut, je Ziel geklemmt)
- `src/ui/virtualconsole/vc_stepper.py:137` — `handle_midi` (relativer CC)
- `src/ui/virtualconsole/vc_stepper.py:315` — `to_dict` · `:327` — `apply_dict`
