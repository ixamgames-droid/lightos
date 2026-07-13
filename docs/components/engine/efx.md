# `EFX` (`EfxInstance`) — Pan/Tilt-Bewegungsmuster

Teil der [Engine-Funktionstypen](README.md) · `FunctionType.EFX`
(`tempo_sync_default = True`)

> **Typ-Tag geteilt:** `FunctionType.EFX` wird auch von `LayeredEffect` und
> `Carousel` serialisiert. Der Loader unterscheidet über die Keys
> (`motion`/`speed_hz` → `EfxInstance`). Diese Doc beschreibt den
> Pan/Tilt-Bewegungseffekt `EfxInstance`.

## Zweck / Verhalten

Ein EFX fährt eine geometrische Figur (Kreis, Acht, Linie, Raute, Quadrat,
Trapez, Lissajous, Random, Dreieck, Custom Path) als Pan/Tilt-Bewegung über eine
Gruppe von Movern/Spidern. Verteilung über die Gruppe per Fächer/Sync/Offset,
optional gegenläufig, gespiegelt, relativ (um die aktuelle Position), 16-bit
(Fine-Kanäle), und tempo-bus-synchron.

## Parameter

**Instanzfelder** (`EfxInstance.__init__`, `src/core/engine/efx.py:107`, Auswahl):
`algorithm: EfxAlgorithm`, `fixtures: list[EfxFixture]`, Geometrie
`width`/`height`/`x_offset`/`y_offset`/`rotation`/`x_freq`/`y_freq`/`x_phase`/`y_phase`,
Timing `speed_hz`/`direction`/`loop`, Verteilung
`spread`/`mirror`/`phase_mode`/`phase_offset_deg`/`counter_rotate`/`head_spread`,
`open_beam`, `bit16`, `relative`, `random_seed`, Custom-Path `path_id`/`path_data`.

**Dataclass** `EfxFixture` (`src/core/engine/efx.py:54`): `fid`, `start_offset`
(Phase 0–1), `pan_attr` (`"pan"`), `tilt_attr` (`"tilt"`).

**Live-`set_param`-Keys** (`list_params`/`set_param`,
`src/core/engine/efx.py:694`/`:785`) — **Achtung Namensfalle:**

| Key | Bereich | mappt auf |
|---|---|---|
| `speed` | 0.01–10 Hz | **`speed_hz`** (nicht `Function.speed`!) |
| `intensity` | 0–1 | Per-Effekt-Master |
| `size` | 0–255 | setzt `width` **und** `height` |
| `width` / `height` | 0–255 | Pan-/Tilt-Hub |
| `x_offset` / `y_offset` | 0–255 | Zentrum Pan/Tilt |
| `rotation` | 0–360 | Drehung der Figur |
| `spread` | 0–1 | Fächer-Verteilung |
| `head_spread` | 0–1 | Welle über Spider-Köpfe |
| `phase_mode` | select | `sync`/`fan`/`offset` |
| `phase_offset_deg` | 0–360 | nur bei `offset` |
| `counter_rotate` / `mirror` / `relative` / `open_beam` / `loop` / `bit16` | bool | Schalter |
| `direction` | select | `forward`/`backward`/`bounce` |
| `algorithm` | select | Figur (`EfxAlgorithm`) |
| `path` | select | Custom Path aus der `EfxPathLibrary` |
| `tempo_bus_id` | select | `Global`/``/`A`–`D` |
| `tempo_multiplier` | 0.0625–16 | Bus-Verhältnis |
| `phase_offset` | 0–1 Beats | Bus-Versatz |

**Live-Aktionen** (`do_action`/`list_actions`, `src/core/engine/efx.py:876`):
`restart`, `toggle_loop`, `reverse_direction`, `toggle_bounce`,
`next_path`/`prev_path`, `next_algorithm`/`prev_algorithm`, `toggle_mirror`,
`toggle_counter`, `toggle_relative`, `reseed`, `toggle_open_beam`,
`toggle_bit16`, `apply_selection`, `tap`.

## Render-Beitrag

`EfxInstance.write` (`src/core/engine/efx.py:524`): treibt die Phase
(`_advance` → bei Bus-Sync `_sync_from_bus`, sonst `speed_hz × Function.speed ×
dt`), berechnet je Gerät Pan/Tilt (`_values`/`_calc`), wendet
Pan/Tilt-Invert/Swap (`apply_pan_tilt_orientation`) und ggf. Beam-Öffnen an,
verteilt Spider-Kopf-Tilts (`_spider_head_tilts`), löst Kanäle
mehrkopf-bewusst (`resolve_attr_channels`) auf und schreibt coarse (+ fine bei
`bit16`) ins Universum.

## Serialisierung

`to_dict` (`src/core/engine/efx.py:977`) ergänzt `motion: True` (Diskriminator),
`algorithm`, `source_group`, `fixtures`, sämtliche Geometrie-/Timing-/
Verteilungsfelder, `speed_hz`, `random_seed`, `loop`, `path_id`/`path`.
`from_dict` (`:1006`). Loader: `FunctionType.EFX.value` mit Keys-Diskriminator
(`src/core/engine/function_manager.py:512`).

## Gekoppelte Module

- `src/core/app_state.py` — `get_channels_for_patched`, `resolve_attr_channels`,
  `apply_pan_tilt_orientation`, `open_value_for`, `mover_fids`
- `src/core/engine/efx_path.py` — Custom Paths
- `src/core/engine/tempo_bus.py`, `bpm_manager.py` — Bus-/Tap-Sync
- `src/core/engine/rgb_matrix_meta.py` — `ParamSpec`
- `src/core/engine/effect_live.py` — VC/MIDI-Dispatch
- `src/ui/views/efx_view.py` — Editor/Vorschau (`advance_phase`/`_fan_for` geteilt)

## Tests

- `tests/test_efx_circle_shape.py`, `tests/test_efx_hard_edges.py`
- `tests/test_efx_16bit.py`, `tests/test_efx_relative.py`
- `tests/test_efx_relationship.py`, `tests/test_efx_triangle_random.py`
- `tests/test_efx_autoassign.py`, `tests/test_efx_path.py`

## Quelle

`src/core/engine/efx.py:97` (Klasse) · `:524` (`write`) · `:977` (`to_dict`)
