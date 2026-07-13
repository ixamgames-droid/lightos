# vc_xypad (VCXYPad)

> 2D-Pad der Virtuellen Konsole für Pan/Tilt: fährt live die Position der
> Ziel-Fixtures, zieht einen EFX-Bereich auf oder zeichnet eine EFX-Bahn.

## Zweck

`VCXYPad` steuert zwei Achsen gleichzeitig. Im Standard treibt das Fadenkreuz
Pan/Tilt der Ziel-Fixtures live (8- oder 16-bit). Zusätzlich gibt es zwei
Effekt-Modi: ein aufgezogenes Feld setzt Zentrum + Größe eines Ziel-EFX, eine
gezeichnete Bahn wird als Custom-`EfxPath` auf den EFX gelegt. Erbt von `VCWidget`.

## Bedienung / Optionen

### Modi (`mode`)

| Modus | Wirkung | Ziel |
|---|---|---|
| `position` | Fadenkreuz treibt Pan/Tilt live | Fixtures (`fixture_ids` / Selektion / alle) |
| `area` | Rechteck aufziehen → `x_offset`/`y_offset`/`width`/`height` des EFX (0..255) | `efx_function_id` |
| `path` | Bahn zeichnen → Custom-`EfxPath` auf den EFX (≤48 Punkte) | `efx_function_id` |

### Weitere Felder

| Feld | Wirkung | Default |
|---|---|---|
| `pan_attr` / `tilt_attr` | Programmer-Attribute je Achse | `pan` / `tilt` |
| `bits16` | Schreibt zusätzlich `pan_fine`/`tilt_fine` (ruckelfreie Moving Heads) | `False` |
| `fixture_ids` | Feste Ziel-Fixtures (leer = Selektion, sonst alle gepatchten) | `[]` |
| `midi_cc_pan` / `midi_cc_tilt` / `midi_ch` | Zwei absolute CCs (nur Positions-Modus) | -1 / -1 / 0 |

`_MIN_AREA` erzwingt eine Mindest-Feldgröße (kein Punkt-Kollaps beim reinen Klick);
das Zentrum wird ins Pad geklemmt. 8-bit- und 16-bit-Schreibpfad runden statt
abzuschneiden (kein -0.5-LSB-Bias).

## Verknüpfungen

- **AppState:** `get_state()` für `set_programmer_value`, `get_selected_fids`,
  `get_patched_fixtures` (Ziel-Fixtures-Auflösung).
- **Effekt-Live:** `src/core/engine/effect_live` (`set_param` für Feld,
  `resolve_target` für Pfad).
- **EFX-Pfad:** `src/core/engine/efx_path.EfxPath` + `fn.set_custom_path` (path-Modus).
- **Ziel-Editor:** `target_list_editor.TargetListEditor` (EFX per Name wählen).
- **Serialisierung:** `to_dict()`/`apply_dict()` schreiben/lesen Position, Attribute,
  Modus, `bits16`, EFX-ID, MIDI-CCs und das markierte Feld (`area`); die gezeichnete
  Bahn (`_path_pts`) ist transient.

## Zugehörige Tests

- `tests/test_vc_xypad_16bit.py` — Fine-Kanal-Schreibpfad (16-bit).
- `tests/test_vc_xypad_area.py` — Feld-Modus (Zentrum/Größe des EFX).
- `tests/test_vc_xypad_midi.py` — Pan/Tilt-CC-Mapping.
- `tests/test_vc_xypad_minsize.py` — Mindest-Feldgröße / Klemmen.
- `tests/test_vc_xypad_path.py` — Bahn zeichnen → Custom-`EfxPath`.

Headless ausführen:

```
QT_QPA_PLATFORM=offscreen venv/Scripts/python.exe -m pytest tests/test_vc_xypad_area.py -q -p no:cacheprovider
```

## Quelle (file:line)

- `src/ui/virtualconsole/vc_xypad.py:9` — Klasse `VCXYPad`
- `src/ui/virtualconsole/vc_xypad.py:106` — `_apply_area` (Feld → EFX)
- `src/ui/virtualconsole/vc_xypad.py:126` — `_apply_path` (Bahn → EfxPath)
- `src/ui/virtualconsole/vc_xypad.py:153` — `_write_axis` (8-/16-bit)
- `src/ui/virtualconsole/vc_xypad.py:207` — `handle_midi`
- `src/ui/virtualconsole/vc_xypad.py:441` — `to_dict` · `:458` — `apply_dict`
