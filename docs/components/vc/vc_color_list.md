# vc_color_list (VCColorList)

> Anzeige-Widget der Virtuellen Konsole: spiegelt live die Color-Sequence eines
> Ziel-Effekts als Swatch-Reihe (aktive Farbe hervorgehoben) und lässt Farben per
> Klick an/aus schalten oder entfernen.

## Zweck

Beim Live-Bauen eines Farb-Chase (EFFECT_ADD-Kacheln + EFFECT_ACTION-Tasten) war
bisher nicht sichtbar, welche Farben in welcher Reihenfolge drin sind und welche
gerade läuft. `VCColorList` spiegelt die `colors`-Sequence des gebundenen
(oder des zuletzt gestarteten) Effekts: Swatches in Reihenfolge, aktive Farbe mit
goldenem Rahmen, deaktivierte durchgestrichen, plus „leer / gestoppt / läuft"-Status.
Effekte ohne Farbliste (z. B. Szenen-Chaser) zeigen stattdessen die Schrittzahl.
Selbst-Refresh mit 4 Hz; der Timer pausiert, wenn das Widget verdeckt ist.

## Bedienung / Optionen

| Aktion | Wirkung |
|---|---|
| Links-Klick auf Swatch | Farbe an/aus (`toggle_color`) |
| Rechts-Klick auf Swatch | Farbe entfernen (`remove_color`) |

| Feld | Wirkung | Default |
|---|---|---|
| `function_id` | Ziel-Effekt; leer/`None` = aktiver (zuletzt gestarteter) Effekt | `None` |

Beide Aktionen laufen thread-sicher über `effect_live.do_action` direkt am
Ziel-Effekt. Im Edit-Modus verhält sich das Widget normal (Drag/Select/Resize).

## Verknüpfungen

- **Effekt-Live:** `src/core/engine/effect_live.resolve_target` (Ziel auflösen)
  und `do_action("toggle_color"/"remove_color", …)`.
- **Function-Manager:** `src/core/engine/function_manager.get_function_manager().is_running`
  für den Lauf-Status.
- **Effekt-Modell:** liest `fn.colors.entries` (ColorSequence) bzw. `fn.steps`.
- **Serialisierung:** `to_dict()`/`apply_dict()` schreiben/lesen nur `function_id`;
  die Farben gehören dem Effekt und werden NICHT dupliziert.

## Zugehörige Tests

- `tests/test_vc_color_list.py` — Spiegelung/Status der Color-Sequence.
- `tests/test_vc_color_list_interactive.py` — Klick-Toggle/Entfernen + Hit-Test-Ränder.

Headless ausführen:

```
QT_QPA_PLATFORM=offscreen venv/Scripts/python.exe -m pytest tests/test_vc_color_list.py -q -p no:cacheprovider
```

## Quelle (file:line)

- `src/ui/virtualconsole/vc_color_list.py:22` — Klasse `VCColorList`
- `src/ui/virtualconsole/vc_color_list.py:76` — `_hit_swatch` (Rand-genaues Layout)
- `src/ui/virtualconsole/vc_color_list.py:108` — `_do_color_action` (Dispatch)
- `src/ui/virtualconsole/vc_color_list.py:115` — `mousePressEvent`
- `src/ui/virtualconsole/vc_color_list.py:234` — `to_dict` · `:239` — `apply_dict`
