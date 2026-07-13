# show_manager_view (ShowManagerView)

> Timeline-Editor für Show-Funktionen: Tracks + Funktions-Blöcke auf einer
> Zeitachse, mit Transport-Leiste und Track-Steuerung.

## Zweck

Baut zeitbasierte Shows: `TimelineCanvas` malt Tracks und die darauf platzierten
`ShowFunction`-Blöcke als farbige Balken; `TrackLabelPanel` zeigt links
Track-Namen + Mute-Buttons. Funktionen werden per Drag aus dem
FunctionManager auf die Zeitachse gezogen und starten zu ihrer Startzeit.

## Bedienung / Optionen

| Bedienung | Wirkung |
|---|---|
| Timeline (`TimelineCanvas`) | Blöcke verschieben/skalieren auf der Zeitachse |
| Zoom (`PX_PER_SEC`) | Pixel pro Sekunde |
| Track-Panel (`TrackLabelPanel`) | Track umbenennen, muten |
| Transport-Leiste | Play/Pause/Stop der Show |
| Drop aus FunctionManager | Funktion als Show-Block einfügen |

## Verknüpfungen

- **Show-Funktion:** editiert eine `Show`-Funktion; Engine-Typ dokumentiert unter
  [`../engine/show.md`](../engine/show.md).
- **FunctionManager:** Quelle der Blöcke (Drop-Ziel); Show-Liste wird
  nachgezogen, wenn neue Shows entstehen.
- **PlaybackEngine:** Transport treibt die Show-Wiedergabe.

## Zugehörige Tests

- `tests/test_show_manager_new_show.py` — neue Show anlegen.
- `tests/test_show_manager_transport.py` — Transport (Play/Pause/Stop).

## Quelle (file:line)

- `src/ui/views/show_manager_view.py:302` — Klasse `ShowManagerView`
- `src/ui/views/show_manager_view.py:23` — `TimelineCanvas`
- `src/ui/views/show_manager_view.py:238` — `TrackLabelPanel`
- `src/ui/views/show_manager_view.py:17` — Layout-Konstanten (`PX_PER_SEC` …)
