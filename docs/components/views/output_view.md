# output_view (OutputView)

> Output-Monitor: zeigt die DMX-Kanalwerte in Echtzeit als Zellen-Raster.

## Zweck

Schlanke Kontrollansicht des tatsächlichen DMX-Outputs. Jede `DMXChannelCell`
zeigt den aktuellen Wert eines Kanals; die View aktualisiert sich laufend aus dem
gemergten DMX-Puffer. Dient dem schnellen „kommt das an, was ich erwarte?".

## Bedienung / Optionen

| Bereich | Wirkung |
|---|---|
| Kanal-Zellen (`DMXChannelCell`) | Live-Wert 0..255 je DMX-Kanal |
| Universe-Auswahl | Betrachtetes Universe umschalten |

Reines Anzeige-Widget — keine Werte-Eingabe. „Bearbeiten" — entfällt (Monitor).

## Verknüpfungen

- **OutputManager:** liest den gemergten DMX-Puffer pro Universe
  ([`../output/output_manager.md`](../output/output_manager.md),
  [`../output/universe.md`](../output/universe.md)).
- **Abgrenzung:** [`dmx_monitor_view`](dmx_monitor_view.md) zeigt alle 512 Kanäle
  als 32×16-Grid mit Patch-Kontext; `output_view` ist die schlanke Zellen-Liste.

## Zugehörige Tests

- `tests/test_output_view.py` — Zellen-Aufbau und Werte-Update.

## Quelle (file:line)

- `src/ui/views/output_view.py:53` — Klasse `OutputView`
- `src/ui/views/output_view.py:12` — `DMXChannelCell`
