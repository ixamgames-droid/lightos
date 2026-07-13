# function_manager_view (FunctionManagerView)

> Funktions-Browser im QLC+-Stil: baumartige Übersicht aller Funktionen
> (Szenen, Chaser, Sequenzen, EFX, Matrix, Script …) + eingebetteter Editor.

## Zweck

Zentrale Verwaltung aller Show-Funktionen. Links ein `_FunctionTree`
(verschachtelte Ordner, Typ-gruppiert, laufende Funktionen fett), rechts der
passende Editor für die gewählte Funktion (Scene/Chaser/Sequence/Collection/
Script/Carousel/LayeredEffect …). Ein geführter Assistent kann Szenen+Chaser
in einem Rutsch erzeugen. Der Baum ist Drag-Quelle für den ShowManager.

## Bedienung / Optionen

| Bedienung | Wirkung |
|---|---|
| Baum (`_FunctionTree`) | Funktionen auswählen, in Ordner sortieren, starten |
| Neu-Buttons (`_TYPE_ORDER`) | Funktion je Typ anlegen (Labels `_TYPE_LABELS`) |
| Eingebetteter Editor | Passenden Editor je Funktionstyp öffnen |
| Assistent | Szenen + Chaser geführt erzeugen und selektieren |
| Drag zum ShowManager | MIME `application/x-lightos-function` |

## Verknüpfungen

- **FunctionManager:** Quelle/Ziel aller Funktionen; Rebuild erhält Auswahl,
  laufende Funktionen werden fett markiert.
- **Editoren:** delegiert an [`scene_editor`](scene_editor.md),
  [`chaser_editor`](chaser_editor.md), [`sequence_editor`](sequence_editor.md),
  [`collection_editor`](collection_editor.md), [`script_editor`](script_editor.md),
  [`carousel_editor`](carousel_editor.md), [`effect_layer_editor`](effect_layer_editor.md).
- **ShowManager:** [`show_manager_view`](show_manager_view.md) nimmt gezogene
  Funktionen als Timeline-Blöcke an.

## Zugehörige Tests

- Funktionstyp-Tests unter `tests/test_scene_editor.py`, `test_chaser_*`,
  `test_sequence_*`, `test_collection_editor.py` sichern die eingebetteten Editoren.

## Quelle (file:line)

- `src/ui/views/function_manager_view.py:97` — Klasse `FunctionManagerView`
- `src/ui/views/function_manager_view.py:20` — `_FunctionTree` (Drag-Quelle)
- `src/ui/views/function_manager_view.py:625` — Editor-Fabrik je Funktionstyp
- `src/ui/views/function_manager_view.py:355` — Szenen+Chaser-Assistent
