# rgb_matrix_view (RgbMatrixView)

> Matrix-Editor: LED-Grid-Effekte (RGB/RGBW/Dimmer/Shutter) mit Live-Vorschau des
> LED-Rasters.

## Zweck

Verwaltet RGB-Matrix-Funktionen für LED-Wände/Pixel-Arrays. Links die
Matrix-Liste (gruppen-kontext-gefiltert), rechts der Parameter-Editor mit einer
`MatrixPreview` (live gemaltes LED-Grid) und `ColorButton`-Swatches für die
Farbwahl. Kopf über der Liste zeigt an, für welche Auswahl die Matrix gerade
gilt.

## Bedienung / Optionen

| Parameter | Wirkung |
|---|---|
| Algorithmus | Pattern-Generator (Fade, Wipe, Plasma …) |
| Farben (`ColorButton`) | Farb-Swatches per Farb-Dialog setzen |
| Promoted-Params (`_PROMOTED_PARAM_KEYS`) | Häufige Params (`color_cycle`, `dimmer_cycle`) prominent |
| Dimmer/Shutter | Helligkeit/Blitz je Zelle |

## Verknüpfungen

- **FunctionManager:** Matrizen kommen aus `function_manager` (stabile
  Reihenfolge); Start/Stop über den Manager.
- **Bus:** abonniert `GROUP_CHANGED` — im Folge-Modus wird das Grid aus der
  (ggf. geänderten) Auswahl neu gebaut.
- **Gruppen-Scope:** arbeitet auf der aktiven Fixture-Gruppe/Auswahl.
- **Engine-Typ:** dokumentiert unter [`../engine/rgbmatrix.md`](../engine/rgbmatrix.md).

## Zugehörige Tests

- `tests/test_rgb_matrix_view_controls.py` — Editor-Controls.
- `tests/test_rgb_matrix_style_visibility.py`, `test_rgb_matrix_gaps.py`.
- Algorithmen: `tests/test_matrix_algorithms.py`, `test_matrix_algo_cycle.py`,
  `test_matrix_colorfade.py`, `test_matrix_dimmer_master.py`.

## Quelle (file:line)

- `src/ui/views/rgb_matrix_view.py:122` — Klasse `RgbMatrixView`
- `src/ui/views/rgb_matrix_view.py:29` — `MatrixPreview` (LED-Grid-Vorschau)
- `src/ui/views/rgb_matrix_view.py:93` — `ColorButton`
- `src/ui/views/rgb_matrix_view.py:25` — `_PROMOTED_PARAM_KEYS`
