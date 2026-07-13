# `Sequence` — Cue-Liste auf einer festen Fixture-Selektion

Teil der [Engine-Funktionstypen](README.md) · `FunctionType.Sequence`
(`tempo_sync_default = True`)

## Zweck / Verhalten

Eine Sequence ist eine Chaser-Variante, die **direkt** auf einer Liste von
Fixtures (`bound_fixtures`) arbeitet, statt andere Funktionen zu verketten. Jeder
`SequenceStep` hält ein Dict `{fid: {attribute: value}}` mit eigenen
Zeitparametern. Die Werte werden mit Crossfade (Vorwert `_prev_values` → Ziel)
direkt in die Universen geschrieben. Laufordnung/Richtung/Tempo-Bus wie beim
Chaser.

## Parameter

**Instanzfelder** (`Sequence.__init__`, `src/core/engine/sequence.py:43`):
`steps: list[SequenceStep]`, `bound_fixtures: list[int]`, `run_order`,
`direction`, `speed`, `beats_per_step`.

**Dataclass** `SequenceStep` (`src/core/engine/sequence.py:18`): `values` (dict
`fid_str → {attribute_str: 0–255}`), `fade_in` (Default 0.5), `hold`,
`fade_out`, `note`, `fade_in_curve`, `fade_out_curve`.

**Builder:** `add_step_from_programmer(programmer, fade_in, hold, fade_out)`
nimmt die gebundenen Fixtures aus dem Programmer als neuen Schritt auf.

**Live-`set_param`-Keys** (`list_params`/`set_param`,
`src/core/engine/sequence.py:303`/`:395`): identisch zum Chaser — `speed`
(0.05–8.0), `step_duration`, `step_hold`, `step_fade`, `step_fade_in`,
`step_fade_out`, `direction`, `run_order`, `tempo_bus_id`, `tempo_multiplier`
(0.0625–16), `phase_offset` (0–1 Beats).

## Render-Beitrag

`Sequence.write` (`src/core/engine/sequence.py:193`): clampt `_step_idx`,
berechnet den Mix-Faktor über fade_in/hold/fade_out (kurvengeformt), löst je
Fixture die Kanäle mehrkopf-bewusst über `resolve_attr_channels`
(`app_state`) auf und schreibt `prev + (target - prev) * mix`. Fortschaltung
zeitbasiert oder bus-getrieben (`_bus_steps_to_advance`); der aktuelle Step wird
als `_prev_values` für den nächsten Crossfade gemerkt.

## Serialisierung

`to_dict` (`src/core/engine/sequence.py:444`) ergänzt `bound_fixtures`,
`run_order`, `direction`, `speed`, `beats_per_step`, `steps` (je Schritt
`values`/`fade_*`/`hold`/`note` + Kurven wenn abweichend).
`from_dict` (`:471`). Loader: `FunctionType.Sequence.value`
(`src/core/engine/function_manager.py:504`).

## Gekoppelte Module

- `src/core/app_state.py` — `get_channels_for_patched`, `resolve_attr_channels`
  (Mehrkopf-Auflösung `attr#N`)
- `src/core/engine/tempo_bus.py` — Bus-Sync
- `src/core/engine/fade_curve.py` — Schritt-Kurven
- `src/ui/views/sequence_editor.py` — UI-Editor

## Tests

- `tests/test_sequence_live_params.py`
- `tests/test_sequence_step_names.py`
- `tests/test_sequence_stepidx_clamp.py`
- `tests/test_sequence_tempo_sync.py`
- `tests/test_multihead_sequence_scene.py`

## Quelle

`src/core/engine/sequence.py:34` (Klasse) · `:193` (`write`) · `:444` (`to_dict`)
