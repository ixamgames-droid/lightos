# `Chaser` — Schrittkette über andere Funktionen

Teil der [Engine-Funktionstypen](README.md) · `FunctionType.Chaser`
(`tempo_sync_default = True`)

## Zweck / Verhalten

Ein Chaser läuft eine Liste von `ChaserStep`s ab, von denen jeder auf eine
**andere Funktion** (meist eine Scene) zeigt. Pro Schritt gelten eigene
Zeitparameter (`fade_in`/`hold`/`fade_out`) und Fade-Kurven. Unterstützte
Laufordnungen: `Loop`, `SingleShot`, `PingPong`, `Random`; Richtung
`Forward`/`Backward`. Der Chaser blendet **selbst** zwischen den Schritten über
(Crossfade `_from_values`→`_cur_output`), weil der Per-Frame-Clear im Renderer
ein Snapshotten in der Kind-Scene verhindert. Fortschaltung ist zeitbasiert,
per Beat (`audio_triggered`, `beats_per_step`) **oder** über einen Tempo-Bus
(`tempo_bus_id`, phasenkohärent, `tempo_multiplier`).

## Parameter

**Instanzfelder** (`Chaser.__init__`, `src/core/engine/chaser.py:38`):
`steps: list[ChaserStep]`, `run_order: RunOrder`, `direction: Direction`,
`speed` (Zeit-Multiplikator), `audio_triggered`, `beats_per_step`.

**Dataclass** `ChaserStep` (`src/core/engine/chaser.py:14`): `function_id`,
`fade_in`, `hold`, `fade_out`, `note`, `fade_in_curve`, `fade_out_curve`.

**Live-`set_param`-Keys** (`list_params`/`set_param`,
`src/core/engine/chaser.py:462`/`:557`):

| Key | Bereich | Wirkung |
|---|---|---|
| `speed` | 0.05–8.0 | Tempo-Faktor |
| `step_duration` | 0.05–60 s | Gesamtdauer je Schritt (skaliert Hold/Fades) |
| `step_hold` | 0–60 s | Haltezeit aller Schritte |
| `step_fade` | 0–10 s | setzt Fade-In **und** -Out aller Schritte |
| `step_fade_in` / `step_fade_out` | 0–10 s | einzeln |
| `direction` | select | `Forward`/`Backward` |
| `run_order` | select | `Loop`/`SingleShot`/`PingPong`/`Random` |
| `tempo_bus_id` | select | `Global`/``/`A`–`D` (leer = frei) |
| `tempo_multiplier` | 0.0625–16 | Verhältnis zum Bus |
| `phase_offset` | 0–1 Beats | Versatz auf dem Bus |

**Live-Aktionen** (`do_action`/`list_actions`, `src/core/engine/chaser.py:611`):
`capture_step`, `add_step`, `remove_last_step`, `clear_steps`,
`reverse_direction`, `toggle_bounce`, `restart`, `tap`. `capture_step` nimmt den
aktuellen Programmer als neue Scene auf und hängt sie an.

## Render-Beitrag

`Chaser.write` (`src/core/engine/chaser.py:223`): clampt `_step_idx`
(Re-Entrancy-/Live-Löschschutz), wählt Bus- vs. Audio- vs. Zeit-Pfad, rendert
den aktuellen Schritt zweifach gegen Hintergrund 0x00/0xFF, um die absolut
gesetzten Kind-Kanäle zu isolieren (`_render_child_target`), blendet sie über
`step.fade_in` ein und schreibt den Mischwert ins Universum. Ablauf einer
Schrittdauer schaltet über `_advance_step` weiter.

## Serialisierung

`to_dict` (`src/core/engine/chaser.py:669`) ergänzt `run_order`, `direction`,
`speed`, `audio_triggered`, `beats_per_step`, `steps` (je Schritt
`function_id`/`fade_*`/`hold`/`note` + Kurven, wenn abweichend).
`from_dict` (`:699`). Loader: `FunctionType.Chaser.value`
(`src/core/engine/function_manager.py:502`).

## Gekoppelte Module

- `src/core/engine/scene.py` — typische Schritt-Ziele
- `src/core/engine/tempo_bus.py`, `bpm_manager.py` — Bus-/Beat-Sync
- `src/core/engine/fade_curve.py` — Schritt-Kurven
- `src/core/engine/function_manager.py` — `function_registry` (Kind-Auflösung)
- `src/core/engine/effect_live.py` — VC/MIDI-Dispatch der `set_param`/`do_action`
- `src/ui/views/chaser_editor.py` — UI-Editor

## Tests

- `tests/test_chaser_crossfade.py`
- `tests/test_chaser_live_build.py`
- `tests/test_chaser_self_reference.py` (Re-Entrancy-Schutz)
- `tests/test_chaser_stepidx_clamp.py`
- `tests/test_chaser_tempo_sync.py`

## Quelle

`src/core/engine/chaser.py:29` (Klasse) · `:223` (`write`) · `:669` (`to_dict`)
