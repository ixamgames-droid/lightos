# vc_tempo_bus_controller (VCTempoBusController)

> All-in-One-Panel der Virtuellen Konsole zum Steuern EINES Tempo-Bus: Bus-Wahl,
> Quelle (Sound/Tap/Fix), Faktor-Gitter und gekoppelte Effekte samt SYNC in einem Widget.

## Zweck

`VCTempoBusController` vereint, was bisher auf mehrere Widgets
([`vc_speedial`](vc_speedial.md)-Multiplier + [`vc_bus_selector`](vc_bus_selector.md)
+ Speed-Knoten) verteilt war, in einem grafisch verschachtelten Panel. Es steuert
genau einen Tempo-Bus (`tempo_bus_id`, „" = Haupt-BPM): setzt dessen Quelle,
den Effekt-Faktor und weist gekoppelte Effekte taktgleich zu. Ein 120-ms-Poll hält
die Live-BPM aktuell. Erbt von `VCWidget`.

## Bedienung / Optionen

| Feld | Wirkung | Default |
|---|---|---|
| `tempo_bus_id` | Gesteuerter Bus („" = Haupt-BPM, sonst A/B/C/D) | `A` |
| `source` | Bus-Antrieb: `sound` (folgt Audio-Haupt-BPM), `tap`, `fix` (feste BPM) | `sound` |
| `fixed_bpm` | Feste BPM im `fix`-Modus (Rad/Eigenschaften, 20..600) | 128.0 |
| `factor` | `tempo_multiplier` der gekoppelten Effekte (¼ ½ 1 2 4) | 1.0 |
| `factor_buttons` | Faktor-Gitter | ¼ ½ 1 2 4 |
| `function_id` / `function_ids` | Gekoppelte Effekte (Drop-Ziel) | `None` / `[]` |
| `param_keys_per_id` | Je Effekt gesteuerter Parameter (Default `tempo_multiplier`) | `{}` |

Bedienung: Kopf-Zeile Bus-Dropdown + Live-BPM; Quelle-Buttons; Tempo-Faktor-Gitter
mit Reset; Effekt-Zeile als Drop-Ziel (koppelt zusätzlich) mit „SYNC jetzt"
(alle Effekte gemeinsam auf die Eins). Im `fix`-Modus verstellt das Mausrad die BPM.

## Verknüpfungen

- **Tempo-Bus:** `src/core/engine/tempo_bus.get_tempo_bus_manager()` (Bus setzen,
  `assign_effects_to_bus`, Tap, Sync, Live-BPM).
- **Effekt-Live:** `src/core/engine/effect_live` (Faktor/Parameter der Effekte,
  je-Effekt-Key über `param_keys_per_id`).
- **Ziel-Editor:** `target_list_editor` (Effekte per Name im Eigenschaften-Dialog).
- **Serialisierung:** `to_dict()`/`apply_dict()` schreiben/lesen alle Felder;
  `apply_dict` klemmt `fixed_bpm`/`factor` und dedupliziert die Effekt-IDs defensiv.

## Zugehörige Tests

- `tests/test_vc_tempo_bus_controller.py` — Bus-Steuerung, Quelle, Faktor, SYNC.
- `tests/test_vc_tempo_live_coupling.py` — Live-Kopplung der Effekte an den Bus.
- `tests/test_vc_tempo_widgets.py` — Tempo-Widget-Gruppe insgesamt.

Headless ausführen:

```
QT_QPA_PLATFORM=offscreen venv/Scripts/python.exe -m pytest tests/test_vc_tempo_bus_controller.py -q -p no:cacheprovider
```

## Quelle (file:line)

- `src/ui/virtualconsole/vc_tempo_bus_controller.py:56` — Klasse `VCTempoBusController`
- `src/ui/virtualconsole/vc_tempo_bus_controller.py:124` — `_apply_source` (Bus-Antrieb)
- `src/ui/virtualconsole/vc_tempo_bus_controller.py:156` — `_apply_factor` (Effekt-Faktor)
- `src/ui/virtualconsole/vc_tempo_bus_controller.py:188` — `_sync_now` (gemeinsame Eins)
- `src/ui/virtualconsole/vc_tempo_bus_controller.py:552` — `to_dict` · `:564` — `apply_dict`
