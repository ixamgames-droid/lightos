# vc_effect_display (VCEffectDisplay)

> Live-Vorschau der Virtuellen Konsole: rendert den gebundenen Effekt direkt auf
> der VC — für RGB-Matrizen die echten Pixel, sonst ein Platzhalter.

## Zweck

`VCEffectDisplay` zeigt den an `function_id` gebundenen Effekt LIVE (echter
Effekt-Zustand, nicht die generische Demo-Vorschau der Box). Für RGB-Matrizen
zeichnet es die `preview_pixels` (style-aware, mit Gap-Markierung); für
Nicht-Matrix-Effekte (EFX/Chaser/…) einen Platzhalter. Der ~16-Hz-Timer ist an die
Sichtbarkeit gekoppelt (off-bank/versteckt → Timer aus → keine CPU-Last).
Erbt von `VCWidget`.

## Bedienung / Optionen

| Feld | Wirkung | Default |
|---|---|---|
| `function_id` | Anzuzeigender Effekt (per ID oder Drag binden) | `None` |

Nicht-interaktiv (reine Anzeige). Kopfzeile zeigt Effektname · Algorithmus; ein
grüner Punkt oben rechts signalisiert „läuft". Doppel-Phasen-Falle vermieden:
läuft der Effekt bereits, treibt die Engine seinen `_step` (hier nur
`preview_pixels()` lesen); ist er gestoppt (Draft), treibt das Widget
`_advance_step` selbst.

## Verknüpfungen

- **Effekt-Live:** `src/core/engine/effect_live.resolve_target(function_id)`.
- **RGB-Matrix:** `src/core/engine/rgb_matrix.is_gap` (Gap-Pixel markieren); liest
  `fn.preview_pixels()`, `fn.cols/rows`, `fn.fixture_grid`, `fn._running`.
- **Effekt-Meta:** `vc_effect_meta.effect_name` (Label).
- **Serialisierung:** `to_dict()`/`apply_dict()` schreiben/lesen `function_id`.

## Zugehörige Tests

- `tests/test_vc_effect_display.py` — Live-Render/Pixel-Vorschau, Platzhalter, Timer.

Headless ausführen:

```
QT_QPA_PLATFORM=offscreen venv/Scripts/python.exe -m pytest tests/test_vc_effect_display.py -q -p no:cacheprovider
```

## Quelle (file:line)

- `src/ui/virtualconsole/vc_effect_display.py:21` — Klasse `VCEffectDisplay`
- `src/ui/virtualconsole/vc_effect_display.py:62` — `_refresh_state` (Draft vs. laufend)
- `src/ui/virtualconsole/vc_effect_display.py:102` — `paintEvent` (Pixel/Platzhalter)
- `src/ui/virtualconsole/vc_effect_display.py:168` — `to_dict` · `:173` — `apply_dict`
