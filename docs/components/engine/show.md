# `Show` — Timeline, die Kind-Funktionen zeitgesteuert triggert

Teil der [Engine-Funktionstypen](README.md) · `FunctionType.Show`

## Zweck / Verhalten

Eine Show ist eine Timeline aus mehreren Tracks. Jeder Track hält `ShowFunction`s
mit `start_time`/`duration`, die auf eine Kind-Funktion zeigen. Während des
Ablaufs startet die Show ein Kind, sobald die Playhead-Zeit dessen `start_time`
überquert, rendert es bis `end_time` und stoppt es dann. Am Ende
(`total_duration`) stoppt sie oder loopt.

## Parameter

**Instanzfelder** (`Show.__init__`, `src/core/engine/show_engine.py:56`):

| Feld | Typ | Bedeutung |
|---|---|---|
| `tracks` | `list[ShowTrack]` | Spuren der Timeline |
| `total_duration` | `float` s | Gesamtlänge (Default 60) |
| `loop` | `bool` | am Ende von vorn |

**Dataclass** `ShowFunction` (`src/core/engine/show_engine.py:12`):
`function_id`, `start_time`, `duration` (0 = natürliche Länge des Kindes),
`color` (Timeline-Farbe); interne `_started`/`_stopped`-Flags.
**Dataclass** `ShowTrack` (`:30`): `name`, `muted`, `show_functions` (via
`add_function`/`remove_function`, sortiert nach `start_time`).

**API:** `add_track(name)`, `remove_track(track)`, `recalc_duration()`.

Show bietet keine `list_params`/`set_param` — sie wird über den Show-Manager
bearbeitet.

## Render-Beitrag

`Show.write` (`src/core/engine/show_engine.py:106`): treibt `_elapsed`,
iteriert nicht gemutete Tracks und deren `ShowFunction`s. Beim Überqueren der
`start_time` wird `child.start()` gerufen, aktive Kinder werden per
`child.write(...)` gerendert, beim Erreichen der `end_time` `child.stop()`. Bei
`_elapsed >= total_duration` wird geloopt (Reset aller `ShowFunction`s) oder
gestoppt.

## Serialisierung

`to_dict` (`src/core/engine/show_engine.py:157`) ergänzt `total_duration`,
`loop`, `tracks` (je Track `name`/`muted`/`functions` mit
`function_id`/`start_time`/`duration`/`color`).
`from_dict` (`:181`). Loader: `FunctionType.Show.value`
(`src/core/engine/function_manager.py:508`).

## Gekoppelte Module

- `src/core/engine/function_manager.py` — `function_registry` (Kind-Auflösung)
  und `get()` im `_on_stop`-Pfad
- beliebige Kind-Funktionstypen (Scene, Chaser, EFX, Audio, …)
- `src/ui/views/show_manager_view.py` — Timeline-/Transport-UI

## Tests

- `tests/test_show_file.py`
- `tests/test_show_lint.py`
- `tests/test_show_manager_transport.py`
- `tests/test_show_roundtrip_identity.py`

## Quelle

`src/core/engine/show_engine.py:48` (Klasse) · `:106` (`write`) · `:157` (`to_dict`)
