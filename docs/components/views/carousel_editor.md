# carousel_editor (CarouselEditor)

> Editor einer `Carousel`-Funktion: beat-synchronisierte Pattern (z. B. rotierende
> Farb-/Positions-Muster).

## Zweck

Bearbeitet einen Carousel — ein beat-synchronisiertes Muster, das im Takt durch
eine Reihe von Zuständen (z. B. Farben/Positionen) rotiert. Der Editor pflegt die
Pattern-Schritte/Parameter und kann in ein großes, scrollbares Fenster
ausgekoppelt werden.

## Bedienung / Optionen

| Bedienung | Wirkung |
|---|---|
| Pattern-Schritte | Zustände des rotierenden Musters pflegen |
| Beat-Sync-Parameter | Rotation an den Takt/BPM koppeln |
| Auskoppeln | Editor in großes Fenster verschieben / zurückholen |

## Verknüpfungen

- **Carousel-Funktion:** editiert das `Carousel`-Objekt (Engine-Funktionstyp).
- **Tempo/BPM:** Rotation folgt dem Tempo-Bus/BPM
  ([`bpm_manager_view`](bpm_manager_view.md)).
- **FunctionManager:** eingebettet über
  [`function_manager_view`](function_manager_view.md).

## Zugehörige Tests

- `tests/test_carousel_editor.py` — Editor.
- `tests/test_carousel_color.py`, `test_carousel_colorwheel.py` — Farb-Pattern.

## Quelle (file:line)

- `src/ui/views/carousel_editor.py:13` — Klasse `CarouselEditor`
- `src/ui/views/carousel_editor.py:192` — Auskoppeln in großes Fenster
