# `Script` (`ScriptFunction`) — textbasierter Befehls-Interpreter

Teil der [Engine-Funktionstypen](README.md) · `FunctionType.Script`

> **Typ-Besonderheit:** `ScriptFunction.function_type` ist aus
> Speicher-Kompatibilität `FunctionType.Scene`
> (`src/core/engine/script_func.py:23`). In `to_dict` wird jedoch
> `"type": "Script"` gesetzt und der Loader dispatcht über genau diesen String
> (`src/core/engine/function_manager.py:497`). Der Enum-Wert `Script` existiert
> also, wird aber über den serialisierten Typ-String erreicht, nicht über das
> Klassen-Attribut.

## Zweck / Verhalten

Eine ScriptFunction führt Text-Befehle Zeile für Zeile aus (`#` = Kommentar).
Unterstützte Befehle:

| Befehl | Wirkung |
|---|---|
| `wait <sekunden>` | pausiert N Sekunden |
| `setdmx <universe> <channel> <value>` | setzt einen DMX-Kanal direkt |
| `setfixture <fid> <attribute> <value>` | setzt einen Fixture-Kanal per Attribut |
| `start function <fid>` | startet eine andere Funktion |
| `stop function <fid>` | stoppt eine andere Funktion |
| `blackout on\|off` | nullt alle Universen |

Unbekannte Zeilen werden ignoriert (protokolliert). Pro Frame werden bis zu 50
Zeilen abgearbeitet, bis ein `wait` oder das Skript-Ende erreicht ist.

## Parameter

**Instanzfelder** (`ScriptFunction.__init__`, `src/core/engine/script_func.py:25`):

| Feld | Typ | Bedeutung |
|---|---|---|
| `script` | `str` | der Befehlstext (eine Anweisung je Zeile) |
| `is_script` | `bool` | Marker für Editoren |
| `_line_idx`, `_wait_until`, `_lines` | intern | Ausführungszustand |

Keine `list_params`/`set_param` — Bearbeitung über den Script-Editor.

## Render-Beitrag

`ScriptFunction.write` (`src/core/engine/script_func.py:48`): treibt `_elapsed`,
respektiert eine laufende `wait`-Periode und führt sonst bis zu 50 Zeilen aus
(`_execute_line`). Je nach Befehl schreibt es direkt in Universen
(`setdmx`/`setfixture`/`blackout`) oder startet/stoppt andere Funktionen über die
`function_registry`. Am Skript-Ende stoppt es sich selbst.

## Serialisierung

`to_dict` (`src/core/engine/script_func.py:134`) setzt `type` explizit auf
`"Script"` und ergänzt `script`. `from_dict` (`:140`). Loader über den
`"Script"`-String **oder** `FunctionType.Script.value`
(`src/core/engine/function_manager.py:497`).

## Gekoppelte Module

- `src/core/app_state.py` — `get_channels_for_patched` (für `setfixture`)
- `src/core/engine/function_manager.py` — `function_registry` (start/stop function)
- `src/ui/views/script_editor.py` — UI-Editor

## Tests

- `tests/test_script_editor.py`

## Quelle

`src/core/engine/script_func.py:22` (Klasse) · `:48` (`write`) · `:134` (`to_dict`)
