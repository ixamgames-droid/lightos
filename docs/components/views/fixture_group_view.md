# fixture_group_view (FixtureGroupView)

> 2D-Raster, auf dem gepatchte Fixtures per Drag&Drop platziert und zu benannten
> Gruppen zusammengefasst werden.

## Zweck

Räumliche Gruppen-Verwaltung: links ein `FixtureTreeWithDrag` (Geräte nach
Universe-Ordnern), rechts das `FixtureGridWidget` — eine gemalte Rasterfläche, in
die Fixtures gezogen werden. Position und Zusammenstellung bilden Fixture-Gruppen,
die Programmer, EFX/Matrix und die VC als Auswahl-Ziele nutzen.

## Bedienung / Optionen

| Aktion | Wirkung |
|---|---|
| Fixture aus Baum ziehen | Platziert die FID in der Zielzelle (snappt an nächste freie Zelle) |
| Rastergröße (`_FloatingGridPanel`) | Spalten/Zeilen des Grids ändern (schwebendes Panel) |
| Mehrfach-Drop | `count` freie Zellen row-major belegen, Grid wächst bei Bedarf |
| Live-Highlight | Ziel-Highlight zieht beim Ziehen mit, zeigt Einrast-Zelle |

## Verknüpfungen

- **Bus:** abonniert Gruppen-/Auswahl-Events (`bus.subscribe`), spiegelt Gruppen
  in die restliche UI.
- **AppState-Gruppen:** liest/schreibt die Fixture-Gruppen; Programmer und
  Effekt-Views (`efx_view`, `rgb_matrix_view`) selektieren über diese Gruppen.
- **Patch:** Baum spiegelt den aktuellen Patch (Universe-Ordner + Geräte).

## Zugehörige Tests

- `tests/test_fixture_group_grid_ux.py` — Drop-/Einrast-/Grid-Verhalten.
- `tests/test_fixture_group_folders.py` — Ordner-/Universe-Struktur des Baums.

## Quelle (file:line)

- `src/ui/views/fixture_group_view.py:132` — `FixtureGridWidget` (Rasterfläche)
- `src/ui/views/fixture_group_view.py:423` — `FixtureTreeWithDrag` (Geräte-Baum)
- `src/ui/views/fixture_group_view.py:22` — `_FloatingGridPanel` (Rastergröße)
