# vc_label (VCLabel)

> Statisches Text-Label der Virtuellen Konsole — nicht-interaktive Beschriftung
> zum Gliedern des VC-Layouts.

## Zweck

`VCLabel` zeichnet zentrierten, umbrechenden Text auf einer Kachel. Es hat keine
Aktion und keine Bindung — es dient zum Beschriften/Gruppieren von Bedienelementen
im VC-Canvas. Erbt von `VCWidget` (Geometrie, Edit-Rahmen).

## Bedienung / Optionen

| Feld | Wirkung | Default |
|---|---|---|
| `caption` | Angezeigter Text (zentriert, Wortumbruch) | „Label" |
| `_font_size` | Schriftgröße (6..48) | 10 |

`_bg_color`/`_fg_color` sind feste Look-Werte (kein Editor-Feld). Eingestellt wird
Text und Schriftgröße über den Eigenschaften-Dialog.

## Verknüpfungen

- **Keine Engine-Kopplung** — reines Anzeige-Widget ohne AppState-Zugriff.
- **Serialisierung:** `to_dict()`/`apply_dict()` schreiben/lesen `font_size`; der
  Text reist als `caption` über den `VCWidget`-Basis-`to_dict`.

## Zugehörige Tests

- `tests/test_views.py` — VC-View-Smoke inkl. `VCLabel`-Konstruktion.
- `tests/test_vc_drop_highlight.py` — Drop-/Layout-Verhalten mit Label-Widgets.

Headless ausführen:

```
QT_QPA_PLATFORM=offscreen venv/Scripts/python.exe -m pytest tests/test_views.py -q -p no:cacheprovider
```

## Quelle (file:line)

- `src/ui/virtualconsole/vc_label.py:9` — Klasse `VCLabel`
- `src/ui/virtualconsole/vc_label.py:19` — `paintEvent` (zentrierter Text)
- `src/ui/virtualconsole/vc_label.py:47` — `to_dict` · `:52` — `apply_dict`
