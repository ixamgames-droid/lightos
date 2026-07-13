# script_editor (ScriptEditor)

> Editor einer `ScriptFunction`: Befehle der LightOS-Skriptsprache mit
> Syntax-Hervorhebung bearbeiten.

## Zweck

Text-Editor für Skript-Funktionen. Der `ScriptHighlighter` hebt die Befehle der
LightOS-Skriptsprache farblich hervor; ein eingebauter Hilfetext (`HELP_TEXT`)
listet die verfügbaren Kommandos. Das Skript steuert sequenziell Funktionen,
Werte und Wartezeiten.

## Bedienung / Optionen

| Bedienung | Wirkung |
|---|---|
| Skript-Text | Befehle zeilenweise eingeben (syntaxhervorgehoben) |
| Hilfe (`HELP_TEXT`) | Verfügbare Kommandos nachschlagen |

## Verknüpfungen

- **ScriptFunction:** editiert das `ScriptFunction`-Objekt; Engine-Typ unter
  [`../engine/script.md`](../engine/script.md).
- **FunctionManager:** eingebettet über
  [`function_manager_view`](function_manager_view.md).

## Zugehörige Tests

- `tests/test_script_editor.py` — Editor + Highlighting + Parsing.

## Quelle (file:line)

- `src/ui/views/script_editor.py:83` — Klasse `ScriptEditor`
- `src/ui/views/script_editor.py:15` — `ScriptHighlighter`
- `src/ui/views/script_editor.py:57` — `HELP_TEXT` (Kommando-Referenz)
