# vc_bus_selector (VCBusSelector)

> Chip-Reihe der Virtuellen Konsole: wählt den aktiven Tempo-Bus — global (für
> Tap/Sync/Tempo-Widgets) oder direkt für einen gebundenen Effekt.

## Zweck

`VCBusSelector` zeigt die benannten Tempo-Buses (Default A/B/C/D) als Chips mit
Live-BPM. Ohne Effekt-Bindung schaltet ein Klick den globalen `armed_bus_id`
scharf — alle Tap/Sync/Tempo-Widgets mit leerem `tempo_bus_id` wirken danach auf
diesen Bus. Mit gebundenen Effekten (`function_id`/`function_ids`) hängt ein Klick
ALLE taktgleich auf den gewählten Bus. Erbt von `VCWidget`.

## Bedienung / Optionen

| Feld | Wirkung | Default |
|---|---|---|
| `buses` | Liste der Bus-IDs (Chips) | `["A","B","C","D"]` |
| `function_id` | Primärer gebundener Effekt (leer = globaler Modus) | `None` |
| `function_ids` | Weitere gekoppelte Effekte (taktgleich zuweisen) | `[]` |

Bedienung: Links-Klick auf einen Chip. Der aktive/„scharfe" Bus wird hervorgehoben;
pro Chip wird die aktuelle Bus-BPM dezent eingeblendet (Schnappschuss beim Zeichnen).

## Verknüpfungen

- **Tempo-Bus:** `src/core/engine/tempo_bus.get_tempo_bus_manager()`
  (`armed_bus_id`, `assign_effects_to_bus`, `get(bus)` für Live-BPM).
- **Effekt-Live:** `src/core/engine/effect_live.get_param("tempo_bus_id", …)`
  (aktueller Bus eines gebundenen Effekts).
- **Serialisierung:** `to_dict()`/`apply_dict()` schreiben/lesen `buses`,
  `function_id` und `function_ids` (defensiv nach int gecastet).

## Zugehörige Tests

- `tests/test_vc_tempo_widgets.py` — Bus-Auswahl/Scharfschalten in der Widget-Gruppe.
- `tests/test_vc_tempo_live_coupling.py` — Effekt-Kopplung an Buses.
- `tests/test_tempo_sync_vc_persistence.py` — Persistenz der Bus-Bindung.

Headless ausführen:

```
QT_QPA_PLATFORM=offscreen venv/Scripts/python.exe -m pytest tests/test_vc_tempo_widgets.py -q -p no:cacheprovider
```

## Quelle (file:line)

- `src/ui/virtualconsole/vc_bus_selector.py:20` — Klasse `VCBusSelector`
- `src/ui/virtualconsole/vc_bus_selector.py:42` — `_effect_ids` (gekoppelte IDs)
- `src/ui/virtualconsole/vc_bus_selector.py:88` — `mousePressEvent` (Chip-Klick/Zuweisung)
- `src/ui/virtualconsole/vc_bus_selector.py:210` — `to_dict` · `:217` — `apply_dict`
