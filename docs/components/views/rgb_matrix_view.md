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
| **Zuordnung zeigen** | Legt je Vorschau-Zelle einen dünnen Rahmen über die Effektfarbe: **Farbton = Gerät, Helligkeit = Kopf** — dieselben Farben wie im Fixture-Gruppen-Editor (`src/ui/head_cell_colors.fixture_cell_color`, **eine** Quelle für beide Ansichten). Dazu die Legende „Farbe → Gerät" (ab 2 Geräten) und bei Kopf-Zellen die Kopfnummer, sofern die Zelle ≥ 16×14 px misst. Die Kopfzahl hinter dem Gerätenamen zählt die **belegten Kopf-Zellen** (`head_cell_colors.head_counts` — dieselbe Quelle wie im Fixture-Gruppen-Editor, damit beide Ansichten für dasselbe Raster nicht zwei Zahlen nennen); eine einzelne Kopf-Zelle heißt „(1 Kopf)". Default **aus** → Vorschau unverändert. Die Effektfarbe wird nie ersetzt: sie ist der Zweck der Vorschau. |
| Sprechblase auf der Vorschau | „Gerät · Kopf N" bzw. „Lücke" der überfahrenen Zelle (`assignment_text`/`cell_index_at` — Hit-Test spiegelt die Malgeometrie). |
| `head_mode`-Hinweis | Sichtbarer Warntext, wenn ein Gerät im Patch-Dialog auf „als eine Lampe" (`head_mode == "single"`) steht, das Raster es aber in Kopf-Zellen ansteuert. Wird **gemeldet, nicht automatisch aufgelöst** — das Raster ist handgebaut. |

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
