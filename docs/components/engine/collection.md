# `Collection` — mehrere Funktionen gleichzeitig

Teil der [Engine-Funktionstypen](README.md) · `FunctionType.Collection`

## Zweck / Verhalten

Eine Collection startet und tickt eine Liste von Kind-Funktionen **gleichzeitig**
(paralleles Bündel). Jedes Kind erhält pro Frame denselben `write()`-Aufruf. Beim
Collection-Start werden die Kinder beim ersten Frame sauber gestartet
(Fade-In/Step-Reset), beim Stop werden sie ebenfalls gestoppt (sonst liefen sie
als „running" weiter).

## Parameter

**Instanzfelder** (`Collection.__init__`, `src/core/engine/collection.py:19`):

| Feld | Typ | Bedeutung |
|---|---|---|
| `function_ids` | `list[int]` | IDs der parallel laufenden Funktionen |
| `_registry` | `dict[int, Function]` \| None | zuletzt gesehene Funktions-Registry (für `stop`) |
| `_started` | `set[int]` | bereits gestartete Kinder (Tracking) |

**Management-API:** `add_function(function_id)`, `remove_function(function_id)`.

Collection hat keine `list_params`/`set_param` — sie ist ein reiner Container.
Der generische `Function`-Master (`intensity`/`env_*`) wirkt über
`FunctionManager.tick` auf die von der Collection **selbst** geschriebenen
Kanäle; die Kinder ticken jedoch direkt (siehe Render-Beitrag).

## Render-Beitrag

`Collection.write` (`src/core/engine/collection.py:54`): treibt `_elapsed`,
startet noch nicht gestartete Kinder (`child.start()`), und ruft für jedes Kind
`child.write(universes, patch_cache, dt, function_registry)`. Die Kinder
schreiben also selbst in dieselben Universen; die Collection fügt keinen eigenen
DMX-Wert hinzu, sondern orchestriert nur.

## Serialisierung

`to_dict` (`src/core/engine/collection.py:81`) ergänzt `function_ids`.
`from_dict` (`:86`). Loader: `FunctionType.Collection.value`
(`src/core/engine/function_manager.py:506`).

## Gekoppelte Module

- `src/core/engine/function_manager.py` — liefert die `function_registry` zur
  Kind-Auflösung
- beliebige Kind-Funktionstypen (Scene, Chaser, EFX, …)
- `src/ui/views/collection_editor.py` — UI-Editor

## Tests

- `tests/test_collection.py`
- `tests/test_collection_editor.py`

## Quelle

`src/core/engine/collection.py:11` (Klasse) · `:54` (`write`) · `:81` (`to_dict`)
