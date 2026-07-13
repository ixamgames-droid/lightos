# `MappedChannelChange` — Live-Position auf beliebige Ziel-Kanäle abbilden

Teil der [Engine-Funktionstypen](README.md) · `FunctionType.MappedChannelChange`

## Zweck / Verhalten

Statt Werte fest zu setzen, lässt ein `MappedChannelChange` einen Ziel-Kanal
**live** einer Positions-Quelle folgen. Beispiel: „je höher der Tilt, desto
röter" — Tilt 0–255 wird auf `color_r` 40–255 abgebildet. Die Funktion liest den
aktuellen Quellwert aus dem committeten Live-Universe (folgt also Hand-Eingabe,
EFX-Bewegung oder VC gleichermaßen) und schreibt den gemappten Ausgangswert ins
Scratch — der Programmer überschreibt diese Kanäle dann nicht mehr
(`func_driven`).

## Parameter

**Instanzfelder** (`MappedChannelChange.__init__`,
`src/core/engine/mapped_channel.py:180`): `fids: list[int]` (betroffene Geräte),
`rules: list[MappedRule]`.

**Dataclass** `MappedRule` (`src/core/engine/mapped_channel.py:69`):

| Feld | Bedeutung |
|---|---|
| `source` | Quelle: `tilt`/`pan`/`xy` (radiale Auslenkung aus 128,128) |
| `target` | Ziel-Attribut (z. B. `color_r`) |
| `mode` | `value` (ein Kanal `out_min..out_max`) oder `gradient` (Farbverlauf `color_a`→`color_b`) |
| `in_min`/`in_max` | Eingangs-Bereich (DMX) |
| `out_min`/`out_max` | Ausgangs-Bereich (bei `value`) |
| `color_a`/`color_b` | RGB-Endpunkte (bei `gradient`) |
| `curve` | Übergangsform (`CURVE_NAMES`, z. B. `linear`/`scurve`/`snap`) |
| `invert` | Eingang spiegeln |
| `per_head` | bei Mehrkopf jeden Kopf aus **seiner** Quell-Position mappen |

`MappedRule.evaluate(src_value)` liefert `{"value": int}` oder `{"rgb": (r,g,b)}`
und wird auch von der UI-Live-Vorschau genutzt (kein Drift).

**Live-`set_param`-Keys** (`src/core/engine/mapped_channel.py:279`): nur
`intensity` (0–1, Per-Effekt-Master). Die Regeln selbst werden über den Editor
gepflegt.

## Render-Beitrag

`MappedChannelChange.write` (`src/core/engine/mapped_channel.py:222`): liest je
Fixture die Quell-Position (`_read_source`, mit `xy`-Radial-Kombination), wertet
jede Regel aus (`per_head` löst je Kopf `#N` auf), setzt `value`- bzw.
`gradient`-Ergebnisse zusammen (`color_attrs_for_fixture`/`adapt_color_payload`)
und schreibt sie vorkommens-bewusst (`attr#N`-Logik wie EFX) in die Universen.

## Serialisierung

`to_dict` (`src/core/engine/mapped_channel.py:299`) ergänzt `mapped: True`
(Klarheits-Diskriminator), `fids`, `rules` (jede `MappedRule.to_dict`).
`from_dict` (`:308`). Loader: `FunctionType.MappedChannelChange.value`
(`src/core/engine/function_manager.py:525`) — eigener Typ, keine
Diskriminator-Falle.

## Gekoppelte Module

- `src/core/app_state.py` — `get_state`, `get_channels_for_patched`,
  `get_programmer_value` (Quellwert-Lesung)
- `src/core/color_utils.py` — `color_attrs_for_fixture`, `adapt_color_payload`
- `src/core/engine/fade_curve.py` — `eval_named`, `CURVE_NAMES`
- `src/ui/widgets/mapped_channel_editor.py` — UI-Editor

## Tests

- `tests/test_multihead_sweep.py` (nutzt `MappedChannelChange`)

## Quelle

`src/core/engine/mapped_channel.py:171` (Klasse) · `:222` (`write`) · `:299` (`to_dict`)
