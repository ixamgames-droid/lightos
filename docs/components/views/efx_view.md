# efx_view (EfxView)

> EFX-Editor: Liste der EFX-Bewegungseffekte + Editor + Live-Vorschau zum
> Erstellen und Bearbeiten von Pan/Tilt-Bewegungsmustern.

## Zweck

Verwaltet die EFX-Funktionen (mathematische Bewegungsmuster für Moving Heads /
Spider). Links die EFX-Liste (nach Gruppen-Kontext gefiltert), rechts der
Parameter-Editor mit einer interaktiven `EfxPreviewWidget` (Bounding-Box direkt
mit der Maus ziehbar) bzw. `SpiderEfxPreview` für Scheren-Effekte.

## Bedienung / Optionen

| Parameter | Wirkung |
|---|---|
| Muster/Shape | Kreis, Acht, Linie, Pattern … als Bewegungsbahn |
| Richtung (`DIRECTION_LABELS`) | Laufrichtung des Musters |
| Phasen-Modus (`PHASE_MODE_LABELS`) | Phasenverteilung über die Fixtures (Fan/Spread) |
| Geometrie (interaktiv) | Bounding-Box/Größe/Position per Maus in der Vorschau |
| Spider-Muster (`SPIDER_PATTERNS`) | Vordefinierte Scheren-Bewegungen |

## Verknüpfungen

- **FunctionManager:** EFX-Instanzen kommen aus `function_manager` (stabile
  Reihenfolge); Start/Stop läuft über den Manager.
- **Bus:** abonniert `GROUP_CHANGED`, um im Folge-Modus das Grid/Ziel aus der
  aktuellen Gruppenauswahl neu zu setzen.
- **Gruppen-Scope:** arbeitet auf der aktiven Fixture-Gruppe (Name + alle
  Gruppen-Namen für die Listen-Filterung).
- **Engine-Typ:** dokumentiert unter [`../engine/efx.md`](../engine/efx.md).

## Zugehörige Tests

- `tests/test_efx_interactive_geometry.py` — Maus-Geometrie in der Vorschau.
- `tests/test_efx_circle_shape.py`, `test_efx_path.py`, `test_efx_16bit.py`.
- `tests/test_efx_group_scope.py`, `test_efx_follow_no_clobber.py`,
  `test_efx_autoassign.py`, `test_efx_relative.py`.

## Quelle (file:line)

- `src/ui/views/efx_view.py:471` — Klasse `EfxView`
- `src/ui/views/efx_view.py:33` — `EfxPreviewWidget` (interaktive Vorschau)
- `src/ui/views/efx_view.py:390` — `SpiderEfxPreview`
- `src/ui/views/efx_view.py:19` — `DIRECTION_LABELS` · `:26` — `PHASE_MODE_LABELS`
