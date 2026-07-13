# `Scene` — Kanal-Schnappschuss mit Fade

Teil der [Engine-Funktionstypen](README.md) · `FunctionType.Scene`

## Zweck / Verhalten

Eine Scene ist ein Schnappschuss fester Kanalwerte einer Fixture-Auswahl. Beim
Start wird der aktuelle DMX-Zustand der betroffenen Kanäle geschnappt und über
`fade_in` Sekunden linear (bzw. entlang `fade_in_curve`) auf die gespeicherten
Zielwerte interpoliert. Nach optionalem `hold` (0 = unendlich) blendet die Scene
über `fade_out` wieder aus und stoppt sich dann selbst. Scenes sind die
Grundbausteine, auf die Chaser- und (indirekt) Show-Schritte zeigen.

## Parameter

**Instanzfelder** (`Scene.__init__`, `src/core/engine/scene.py:28`)

| Feld | Typ | Bedeutung |
|---|---|---|
| `fade_in` | `float` s | Einblendzeit von Start-Snapshot zu Zielwert |
| `fade_out` | `float` s | Ausblendzeit nach `hold` (0 = sofort stoppen) |
| `hold` | `float` s | Haltezeit nach Einblende (0 = unendlich halten) |
| `fade_in_curve` | `FadeCurve` | Form der Ein-/Ausblende (Default linear) |
| `_values` | `list[SceneValue]` | die Werte `(fixture_id, channel, value)` |

**Dataclass** `SceneValue(fixture_id, channel, value)` — `channel` ist der
1-basierte Kanal-Offset im Fixture, `value` 0–255
(`src/core/engine/scene.py:13`).

**Werte-API:** `set_value(fixture_id, channel, value)`, `get_value(...)`,
`remove_value(...)`, `clear()`, Property `values`.

Scene stellt **kein** `list_params`/`set_param` bereit — sie ist statisch und
wird über den Scene-Editor, nicht über Live-Parameter bearbeitet. Der generische
`Function`-Master (`intensity`, `speed`, `env_*`) wirkt dennoch (siehe unten).

## Render-Beitrag

`Scene.write` (`src/core/engine/scene.py:77`): schnappt beim ersten Frame
(`_elapsed == 0`) die aktuellen DMX-Werte, treibt `_elapsed` um `dt`, berechnet
den Fade-Fortschritt `t` (kurvengeformt), multipliziert in der Ausblendphase mit
`out_factor` und schreibt `start + (ziel - start) * t` je Kanal ins Universum.
`intensity`/`env_factor` werden vom `FunctionManager.tick` obenauf angewandt.

## Serialisierung

`to_dict` (`src/core/engine/scene.py:147`) ergänzt die Basis um `fade_in`,
`fade_out`, `hold`, `values` (Liste `{fid, ch, val}`) sowie `fade_in_curve` (nur
wenn nicht Standard-Gerade). `from_dict` (`src/core/engine/scene.py:163`) baut
sie zurück. Geladen wird über `FunctionType.Scene.value` in
`FunctionManager.from_dict` (`src/core/engine/function_manager.py:500`).

## Gekoppelte Module

- `src/core/engine/fade_curve.py` — `FadeCurve` (Kurvenform)
- `src/core/app_state.py` — `PatchedFixture`-Auflösung (`_find_fixture`)
- `src/ui/views/scene_editor.py` — UI-Editor
- Ziel von Chaser-Schritten (`chaser.py`) und Show-Tracks (`show_engine.py`)

## Tests

- `tests/test_scene_editor.py`
- `tests/test_scene_adapters_fixes.py`
- `tests/test_laser_snap_scene.py`
- `tests/test_show_roundtrip_identity.py` (Save/Load-Identität)

## Quelle

`src/core/engine/scene.py:20` (Klasse) · `:77` (`write`) · `:147` (`to_dict`)
