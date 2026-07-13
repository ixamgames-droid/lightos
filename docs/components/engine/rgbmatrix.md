# `RGBMatrix` (`RgbMatrixInstance`) — Pixel-Animation über eine Fixture-Gruppe

Teil der [Engine-Funktionstypen](README.md) · `FunctionType.RGBMatrix`
(`tempo_sync_default = True`)

## Zweck / Verhalten

Eine RGB-Matrix bildet eine Fixture-Gruppe als `cols × rows`-Pixelraster
(`fixture_grid`, row-major, `None` = Lücke) ab und animiert Farben/Dimmer/Shutter
über verschiedene Algorithmen (Chase, Wipe, Wave, Gradient, Rainbow, Fill,
Random, Colorfade, Checker, …). Farben stammen aus einer live-editierbaren
`ColorSequence`; Stil (`MatrixStyle`) wählt, welche Kanäle bespielt werden
(RGB, RGBW, Dimmer, Shutter). Animationsrate ist `matrix_speed`.

## Parameter

**Instanzfelder** (`RgbMatrixInstance.__init__`, `src/core/engine/rgb_matrix.py:427`,
Auswahl): `cols`, `rows`, `fixture_grid`, `source_group`, `algorithm`,
`colors: ColorSequence` (`color1/2/3` sind Kompat-Properties), `matrix_speed`,
`direction`, `drive_intensity`, `style: MatrixStyle`, `intensity_min`/`_max`,
`shutter_min`/`_max`, `dimmer_levels: DimmerSequence`, `params: dict`.

**Live-`set_param`-Keys** (`list_params`/`set_param`,
`src/core/engine/rgb_matrix.py:1451`/`:1557`) — **Namensfalle:** der Key `speed`
mappt auf **`matrix_speed`** (nicht `Function.speed`). Weitere Keys u. a.
`algorithm`, `direction`, `style`, `drive_intensity`, `intensity`
(Function-Master), Farb-/Dimmer-Sequenz-Steuerung sowie
`tempo_bus_id`/`tempo_multiplier`/`phase_offset`. Der komplette, autoritative
Satz steht in `list_params` (`:1451`).

**Live-Aktionen** (`do_action`, `src/core/engine/rgb_matrix.py:1685`) u. a.
`toggle_freeze`, Algorithmus-/Farbwechsel; `_frozen` hält die Animation an
(Ausgabe bleibt).

## Render-Beitrag

`RgbMatrixInstance.write` (`src/core/engine/rgb_matrix.py:726`): schreitet
`_step` fort (`_advance_step` — bus-synchron oder `matrix_speed × Function.speed
× dt`, Freeze hält an), rendert das Grid (`_render(self._step)` → Liste von
`Color`), und schreibt je Pixel-Fixture die Kanäle abhängig vom `style`:
RGB/RGBW-Farbkanäle (mit RGBW-Weiß-Split), Farbrad-Fallback, Dimmer-/Shutter-
Style. `intensity` wird — je nach ob das Fixture einen eigenen Dimmer hat und
`drive_intensity` — entweder hier auf die Farben oder vom `FunctionManager.tick`
auf den Dimmer angewandt (kein Doppel-Dimmen).

## Serialisierung

`to_dict` (`src/core/engine/rgb_matrix.py:1805`) ergänzt `cols`/`rows`,
`fixture_grid`, `source_group`, `algorithm`, `color_sequence`/`color_active`,
`dimmer_sequence`/`dimmer_active`, `color1/2/3` (Alt-Leser), `matrix_speed`,
`direction`, `drive_intensity`, `style`, `white_amount`,
`intensity_min`/`_max`, `shutter_min`/`_max`, `params`. Geladen über `apply_dict`
(`:1838`, migriert Legacy-Algorithmusnamen; `matrix_speed` fällt auf alten
`speed`-Key zurück) und `from_dict` (`:1972`). Loader:
`FunctionType.RGBMatrix.value` (`src/core/engine/function_manager.py:523`).

## Gekoppelte Module

- `src/core/color_utils.py` — `rgbw_split`, `color_attrs_for_fixture`
- `src/core/app_state.py` — `get_channels_for_patched`
- `src/core/engine/rgb_matrix_meta.py` — `ParamSpec`, Style-/Algorithmus-Meta
- `src/core/engine/tempo_bus.py` — Bus-Sync
- `src/core/engine/effect_live.py` — VC/MIDI-Dispatch
- `src/ui/views/rgb_matrix_view.py`, `src/ui/widgets/color_sequence_editor.py`,
  `dimmer_sequence_editor.py` — UI

## Tests

- `tests/test_matrix_algorithms.py`, `tests/test_matrix_algorithms_v2.py`
- `tests/test_matrix_colorfade.py`, `tests/test_matrix_fill.py`
- `tests/test_matrix_dimmer_master.py`, `tests/test_matrix_live_vc.py`
- `tests/test_matrix_param_model.py`, `tests/test_matrix_algo_migration.py`

## Quelle

`src/core/engine/rgb_matrix.py:411` (Klasse) · `:726` (`write`) · `:1805` (`to_dict`)
