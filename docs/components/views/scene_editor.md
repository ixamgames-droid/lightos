# scene_editor (SceneEditor)

> Editor einer `Scene`-Funktion: feste Kanalwerte je Fixture in einer
> Fixture×Kanal-Tabelle bearbeiten.

## Zweck

Bearbeitet die statischen Kanalwerte einer Szene. Baut pro Fixture eine Zeile und
je Kanal eine Spalte; Werte lassen sich direkt setzen oder aus dem aktuellen
Programmer-Stand importieren. Zum Prüfen können die Szenenwerte direkt auf DMX
geschrieben werden.

## Bedienung / Optionen

| Bedienung | Wirkung |
|---|---|
| Werte-Tabelle | Kanalwert je (Fixture, Kanal) setzen |
| Aus Programmer importieren | Aktuellen Programmer-Stand in die Szene übernehmen |
| Auf DMX schreiben | Szenenwerte direkt ausgeben (Vorschau) |

## Verknüpfungen

- **Scene-Funktion:** editiert das `Scene`-Objekt; Engine-Typ dokumentiert unter
  [`../engine/scene.md`](../engine/scene.md).
- **Programmer:** Import übernimmt Programmer-Werte
  ([`programmer_view`](programmer_view.md)).
- **FunctionManager:** eingebettet über
  [`function_manager_view`](function_manager_view.md).

## Zugehörige Tests

- `tests/test_scene_editor.py` — Tabellen-Aufbau, Import, DMX-Write.
- `tests/test_multihead_sequence_scene.py` — Mehrkopf-Kanäle.

## Quelle (file:line)

- `src/ui/views/scene_editor.py:14` — Klasse `SceneEditor`
- `src/ui/views/scene_editor.py:198` — Zeilen-/Spalten-Aufbau
- `src/ui/views/scene_editor.py:270` — Programmer-Import · `:288` — DMX-Write
