# collection_editor (CollectionEditor)

> Editor einer `Collection`-Funktion: Liste von Funktionen, die parallel (gleichzeitig)
> laufen.

## Zweck

Bearbeitet eine Collection — ein Bündel von Funktionen, das beim Start **alle
Mitglieder gleichzeitig** startet (im Gegensatz zum sequenziellen Chaser). Der
Editor zeigt die Mitglieder-Liste zum Hinzufügen/Entfernen/Umordnen.

## Bedienung / Optionen

| Bedienung | Wirkung |
|---|---|
| Funktion hinzufügen | Mitglied in die Collection aufnehmen |
| Entfernen/Umordnen | Mitglieder-Liste pflegen |

Weitere Parameter — entfällt (Collection ist reine Parallel-Gruppe).

## Verknüpfungen

- **Collection-Funktion:** editiert das `Collection`-Objekt; Engine-Typ unter
  [`../engine/collection.md`](../engine/collection.md).
- **FunctionManager:** Mitglieder stammen aus der Funktions-Registry
  ([`function_manager_view`](function_manager_view.md)).

## Zugehörige Tests

- `tests/test_collection_editor.py` — Editor (Mitglieder pflegen).
- `tests/test_collection.py` — Collection-Ausführung (parallel).

## Quelle (file:line)

- `src/ui/views/collection_editor.py:13` — Klasse `CollectionEditor`
