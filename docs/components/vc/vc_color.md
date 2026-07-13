# vc_color (VCColor)

> Farb-Kachel der Virtuellen Konsole: hält eine feste RGB(+W/A/UV)-Farbe und
> wendet sie per Klick/MIDI auf Programmer, alle Fixtures oder die Farben eines
> Ziel-Effekts an.

## Zweck

`VCColor` ist das Farb-Bedienelement der VC. Die Kachel zeigt ihre Farbe direkt
an; ein Klick (oder gebundene MIDI-Note/CC) legt sie je nach `target` auf die
Programmer-Selektion, alle gepatchten Fixtures oder die Color-Sequence bzw.
festen Farbslots eines Effekts. Doppelklick öffnet einen nicht-modalen
Farbwähler, der im Run-Modus live umfärbt. Erbt von `VCWidget`; MIDI-Bindung und
-Teach funktionieren identisch zum `vc_button`.

## Bedienung / Optionen

### Ziele (`ColorTarget`)

| Ziel (Enum) | Label | Wirkung |
|---|---|---|
| `PROGRAMMER` | Programmer/Selektion | Färbt die Programmer-Auswahl (Fallback: alle) |
| `ALL` | Alle Fixtures | Färbt alle gepatchten Fixtures |
| `EFFECT` | Effekt (aktive Farbe) | Setzt die aktuell aktive Sequence-Farbe live |
| `EFFECT_ADD` | Effekt (Farbe hinzufügen) | Hängt die Farbe an die Color-Sequence an (Live-Chase-Bau) |
| `EFFECT_C1/2/3` | Effekt Farbe 1/2/3 | Setzt feste `color1/2/3` (Feuer/Plasma/Windrad) |

### Weitere Felder

| Option | Wirkung | Default |
|---|---|---|
| `color_r/g/b` | Grundfarbe RGB | 255/255/255 |
| `color_w/a/uv` | Zusatzkanäle (nur gesendet wenn > 0, `color_w` immer) | 0 |
| `with_intensity` | Setzt zusätzlich `intensity` (Farbe immer sichtbar) | `True` |
| `intensity` | Helligkeitswert bei `with_intensity` | 255 |
| `head` | Ziel-Kopf/Bar bei Mehrkopf-Geräten (Spider) | 0 |
| `function_id` / `edit_slot` | Ziel-Effekt für `EFFECT*`-Ziele (leer = aktiver Effekt) | — |
| `midi_ch`/`midi_data1`/`midi_type` | MIDI-Bindung (Note/CC, ch 0 = alle) | -1 |

Anzeige-Overlays: additiv gefalteter Weißanteil (`rgbw_to_display`) für den
Swatch/Picker; ein Schloss-Symbol, wenn ein laufender Effekt die Farbkanäle
besitzt (`_color_overridden`, Programmer/ALL wirkungslos).

## Verknüpfungen

- **AppState:** `get_state()` für Programmer-Werte, `get_patched_fixtures`,
  `set_programmer_value` (inkl. `head`).
- **Effekt-Live:** `src/core/engine/effect_live` für `EFFECT*`-Ziele
  (`begin_live_edit`, `set_selected_color`, `do_action("add_color")`,
  `set_param`, `color_is_effect_driven`); `_notify_effect_colors_changed` (UI-14b).
- **Farb-Utils:** `src/core/color_utils.rgbw_to_display`.
- **Paletten:** `src/core/engine/palette` (gespeicherte Farb-Paletten im Editor).
- **APC-Feedback:** `apc_mk2_feedback.py` färbt das gebundene Pad in dieser Farbe.
- **Serialisierung:** `to_dict()`/`apply_dict()` schreiben/lesen alle Felder;
  `normalize_color_target` faltet Alt-ASCII-Ziele (vor Umlaut-Cleanup) auf den
  heutigen kanonischen Wert (kein stiller Default-Fallback bei Alt-Shows).

## Zugehörige Tests

- `tests/test_vc_color_float_picker.py` — Float-Picker/Live-Umfärben der Kachel.
- `tests/test_color_context_lock.py` — Schloss-Overlay bei effekt-getriebener Farbe.
- `tests/test_multihead_spider.py` — Kopf-/Bar-Färbung bei Mehrkopf-Geräten.
- `tests/test_fx_features_color_vc.py` — Effekt-Farb-Ziele (Sequence/Slots).

Headless ausführen:

```
QT_QPA_PLATFORM=offscreen venv/Scripts/python.exe -m pytest tests/test_vc_color_float_picker.py -q -p no:cacheprovider
```

## Quelle (file:line)

- `src/ui/virtualconsole/vc_color.py:80` — Klasse `VCColor`
- `src/ui/virtualconsole/vc_color.py:19` — `ColorTarget` (Ziele)
- `src/ui/virtualconsole/vc_color.py:61` — `normalize_color_target` (Alt-Show-Migration)
- `src/ui/virtualconsole/vc_color.py:178` — `_apply` (Ziel-Dispatch)
- `src/ui/virtualconsole/vc_color.py:253` — `handle_midi`
- `src/ui/virtualconsole/vc_color.py:574` — `to_dict` · `:593` — `apply_dict`
