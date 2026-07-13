# vc_speedial (VCSpeedDial)

> Dreh-Regler der Virtuellen Konsole für Tempo: setzt per Rad/Tap die BPM eines
> Executors, einer Funktion, eines Tempo-Bus oder wirkt als Speed-Knoten
> (Master/Sub mit Faktor-Gitter).

## Zweck

`VCSpeedDial` verbindet ein rundes BPM-Rad mit einem Tap-Tempo-Button und einer
digitalen BPM-Anzeige. Je nach `target_mode` treibt er ein Executor-/Funktions-Tempo,
die BPM eines benannten Tempo-Bus, einen Effekt-Multiplikator (×0.5/1/2/4) oder
agiert als QLC+-artiger Speed-Knoten (Master mit eigener BPM, oder Sub, der einem
Master × Faktor folgt). Auto-Refresh (~10 Hz) verfolgt extern wechselnde Master-BPM.
Erbt von `VCWidget`.

## Bedienung / Optionen

### Ziel-Modi (`SpeedTarget`)

| Modus (Enum) | Wirkung | Bindung |
|---|---|---|
| `FUNCTION` | Setzt das Tempo einer Funktion/eines Effekts nach Name (Default) | `function_id`/`function_ids` |
| `EXECUTOR` | Setzt das Tempo eines Executor-Slots | `function_id` = Slot |
| `TEMPO_BUS` | Setzt die BPM eines benannten Tempo-Bus | `tempo_bus_id` |
| `TEMPO_BUS_MULT` | Setzt den `tempo_multiplier` der Ziel-Effekte (×-Faktor) | `function_ids` |
| `SPEED_NODE` | Dial IST ein Speed-Knoten: Master (eigene BPM) oder Sub (Faktor-Gitter) | `role`, `parent_bus_id` |

### Weitere Felder

| Feld | Wirkung | Default |
|---|---|---|
| `_bpm` / `_min_bpm` / `_max_bpm` | Aktuelle BPM + Bereich | 120 / 20 / 600 |
| `multiplier_mode` / `_mult` | Faktor-Modus statt absoluter BPM | `False` / 1.0 |
| `invert` | Höherer Dial-Wert = langsamer | `False` |
| `role` / `parent_bus_id` | Speed-Knoten: `master`/`sub`, Master-Bus für Sub | `master` / `""` |
| `factor_buttons` / `_active_factor` | Faktor-Gitter (Sub) und aktive Wahl | ¼ ½ 1 2 4 / 1.0 |
| `param_keys_per_id` | Je gekoppeltem Effekt ein Parameter (Phase E) | `{}` |
| `show_dial`/`show_tap`/`show_factors`/`show_sync`/`show_bpm` | Sichtbarkeit der Panel-Teile | `True` |

Bedienung: Drag am Rad ändert die BPM, Mausrad feiner; Tap-Button für Tap-Tempo,
Sync-Button (Sub) setzt den Downbeat neu. Faktor-Gitter per Klick (`_set_factor`).

## Verknüpfungen

- **Tempo/BPM:** `src/core/engine/tempo_bus` (Bus-BPM, Sub-Kopplung) und der
  globale BPM-Leader (Sound-BPM-Probe).
- **Effekt-Live:** `src/core/engine/effect_live` (Tempo/Multiplier/Parameter der
  gekoppelten Effekte, je-Effekt-Key über `param_keys_per_id`).
- **Executor:** `playback_engine.executors` (EXECUTOR-Modus).
- **Serialisierung:** `to_dict()`/`apply_dict()` schreiben/lesen alle Felder
  inkl. BPM-Bereich (VCB-12) und Speed-Knoten-Konfiguration; `apply_dict` coerct
  `bpm` robust nach float (VCB-28) und wendet die Bus-Rolle nach dem Laden an.

## Zugehörige Tests

- `tests/test_speed_dial.py` — Rad/Tap/BPM-Grundverhalten.
- `tests/test_vc_speeddial_factor.py` — Faktor-/Multiplikator-Modus.
- `tests/test_vc_speed_node.py` — Speed-Knoten (Master/Sub, Faktor-Gitter).

Headless ausführen:

```
QT_QPA_PLATFORM=offscreen venv/Scripts/python.exe -m pytest tests/test_speed_dial.py -q -p no:cacheprovider
```

## Quelle (file:line)

- `src/ui/virtualconsole/vc_speedial.py:60` — Klasse `VCSpeedDial`
- `src/ui/virtualconsole/vc_speedial.py:14` — `SpeedTarget` (Ziel-Modi)
- `src/ui/virtualconsole/vc_speedial.py:201` — `_apply` (Ziel-Dispatch)
- `src/ui/virtualconsole/vc_speedial.py:283` — `sync` · `:327` — `_tap`
- `src/ui/virtualconsole/vc_speedial.py:970` — `to_dict` · `:997` — `apply_dict`
