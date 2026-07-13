# palette_view (PaletteView)

> Paletten-Manager: Color-, Position- und Beam-Presets in Tabs, als anklickbare
> Swatch-Buttons.

## Zweck

Verwaltet wiederverwendbare Presets (Paletten) je Typ. Multi-Tab-Ansicht (Color,
Position, Beam, Effect); jede `PalettePage` zeigt ein scrollbares Raster von
`PaletteButton`-Swatches. Klick wendet die Palette auf die aktuelle
Programmer-Auswahl an; Paletten lassen sich in (verschachtelte) Ordner sortieren.

## Bedienung / Optionen

| Bedienung | Wirkung |
|---|---|
| Typ-Tabs (`PaletteType`) | Color / Position / Beam / Effect |
| Swatch-Button (`PaletteButton`) | Palette auf Programmer-Auswahl anwenden |
| Palette anlegen | Aktuellen Programmer-Stand als Palette speichern |
| Ordner (FLD-01c) | Palette einem Pfad (`/`-getrennt) zuordnen |

## Verknüpfungen

- **PaletteManager:** Quelle/Ziel aller Paletten (`PaletteManager`), inkl.
  Serialisierung in die Show.
- **Programmer:** wendet Werte auf die aktuelle Auswahl an (None = keine Auswahl).
- **Preset-Browser:** [`preset_browser_view`](preset_browser_view.md) durchsucht
  dieselben Paletten + Gruppen.

## Zugehörige Tests

- `tests/test_palette_curve_folders.py` — Ordner-Zuordnung (FLD-01c).

## Quelle (file:line)

- `src/ui/views/palette_view.py:226` — Klasse `PaletteView`
- `src/ui/views/palette_view.py:60` — `PalettePage` (Swatch-Raster je Typ)
- `src/ui/views/palette_view.py:12` — `PaletteButton`
- `src/ui/views/palette_view.py:210` — Ordner-Zuordnung (FLD-01c)
