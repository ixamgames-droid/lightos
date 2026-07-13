# vc_effect_colors (VCEffectColors)

> Farb-Editor der Virtuellen Konsole: zeigt die ColorSequence eines Matrix-Effekts
> als Swatch-Reihe und färbt einzelne Slots live um.

## Zweck

`VCEffectColors` hält KEINE eigenen Farben, sondern spiegelt die lebende
`ColorSequence` des gebundenen Effekts (`effect_live.get_param("colors", fid)`).
Änderungen wirken sofort — der Renderer liest die Sequence jeden Frame. Wird per
Smart-Drop eines Matrix-Effekts erzeugt und an ihn gebunden. Erbt von `VCWidget`.

## Bedienung / Optionen

| Aktion (Run-Modus) | Wirkung |
|---|---|
| Links-Klick auf Swatch | Farbwähler → färbt diesen Slot live um |
| Rechts-Klick auf Swatch | Slot aktiv/inaktiv (Fade überspringt inaktive Farben) |

| Feld | Wirkung | Default |
|---|---|---|
| `function_id` | Fester Ziel-Effekt | `None` |
| `edit_slot` | Alternativ: Effekt aus einem Live-Edit-Slot (ohne feste ID) | `""` |

Im Edit-Modus verhält sich das Widget normal (Verschieben/Skalieren/Eigenschaften).
Der Editor bietet den Effekt sowohl per ID als auch per Namens-Combo (nur Funktionen
mit `colors`).

## Verknüpfungen

- **Effekt-Live:** `src/core/engine/effect_live` (`get_param("colors")`,
  `get_edit_target`, `begin_live_edit`); `_notify_effect_colors_changed` (UI-14b).
- **Effekt-Modell:** liest/schreibt die `ColorSequence` (`color_at`, `set_color`,
  `toggle`, `active_index`, `entries`).
- **AppState:** `get_state().function_manager.all()` (Namens-Combo im Editor).
- **Serialisierung:** `to_dict()`/`apply_dict()` schreiben/lesen `function_id` und
  `edit_slot`; die Farben gehören dem Effekt und werden NICHT gespeichert.

## Zugehörige Tests

- `tests/test_vc_effect_colors.py` — Spiegelung/Live-Umfärben, Slot-Toggle, Bindung.

Headless ausführen:

```
QT_QPA_PLATFORM=offscreen venv/Scripts/python.exe -m pytest tests/test_vc_effect_colors.py -q -p no:cacheprovider
```

## Quelle (file:line)

- `src/ui/virtualconsole/vc_effect_colors.py:24` — Klasse `VCEffectColors`
- `src/ui/virtualconsole/vc_effect_colors.py:37` — `_fid` · `:51` — `_seq` (Ziel-Auflösung)
- `src/ui/virtualconsole/vc_effect_colors.py:88` — `mousePressEvent` (Live-Umfärben/Toggle)
- `src/ui/virtualconsole/vc_effect_colors.py:217` — `to_dict` · `:223` — `apply_dict`
