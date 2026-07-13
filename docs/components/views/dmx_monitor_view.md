# dmx_monitor_view (DmxMonitorView)

> DMX-Monitor: alle 512 Kanäle eines Universe als 32×16-Farbraster mit
> Patch-Kontext je Adresse.

## Zweck

Vollständige DMX-Landkarte. `DmxGrid` malt alle 512 Kanäle als farbcodiertes
Raster (32 Spalten × 16 Zeilen); die Farbe kodiert den aktuellen Wert. Über den
Patch-Kontext (U-4/SD-03) blendet jede Zelle Geräte-Kürzel + Attribut ein und
liefert einen Tooltip — man sieht sofort, welches Fixture welchen Kanal belegt.

## Bedienung / Optionen

| Bereich | Wirkung |
|---|---|
| Kanal-Raster (`DmxGrid`) | 512 Zellen, Farbe = Wert |
| Patch-Kontext | Geräte-Kürzel + Attribut je belegter Adresse (Tooltip) |
| Universe-Auswahl | Betrachtetes Universe umschalten |

## Verknüpfungen

- **OutputManager:** liest den gemergten DMX-Puffer
  ([`../output/output_manager.md`](../output/output_manager.md)).
- **Patch:** Adress→Fixture-Zuordnung aus dem Patch (`patch_view`).
- **Abgrenzung:** schwerer/informativer als [`output_view`](output_view.md).

## Zugehörige Tests

- `tests/test_dmx_monitor_patch_context.py` — Patch-Kontext/Tooltip je Adresse.

## Quelle (file:line)

- `src/ui/views/dmx_monitor_view.py:148` — Klasse `DmxMonitorView`
- `src/ui/views/dmx_monitor_view.py:20` — `DmxGrid` (512-Kanal-Raster)
- `src/ui/views/dmx_monitor_view.py:50` — Patch-Kontext (U-4/SD-03)
- `src/ui/views/dmx_monitor_view.py:14` — Grid-Konstanten (`COLS/ROWS`)
